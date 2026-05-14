"""CEO24 — однострочный аудит и очистка дубликатов в БД.

Цели:
  1) Слить организации с одинаковым нормализованным ИНН (например leading-0)
  2) Удалить дубль-Documents по (contract_id, doc_number, doc_date, amount, doc_type) — оставляем самый ранний
  3) Удалить дубль-ClientObjects по (organization_id, LOWER(name)) — оставляем самый ранний

Запуск (внутри backend-контейнера):
    python -m scripts.dedupe_db --audit       # только показать, ничего не менять
    python -m scripts.dedupe_db --apply       # реально удалить дубликаты

Дополнительные опции:
    --skip-merge   — не сливать организации (полезно если хотите проверять руками)
"""
from __future__ import annotations

import argparse
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from sqlalchemy import text
from sqlmodel import Session

from app.core.database import engine


def audit(session: Session) -> dict:
    counts = {}
    counts["dup_org_by_trimmed_inn"] = session.exec(text("""
        SELECT COUNT(*) FROM (
          SELECT trimmed_inn FROM (
            SELECT TRIM(LEADING '0' FROM TRIM(inn)) AS trimmed_inn FROM organizations
          ) t GROUP BY trimmed_inn HAVING COUNT(*) > 1
        ) g
    """)).scalar() or 0

    counts["dup_documents"] = session.exec(text("""
        SELECT COALESCE(SUM(n - 1), 0) FROM (
          SELECT COUNT(*) AS n FROM documents
          GROUP BY contract_id, COALESCE(doc_number,''), doc_date, amount, doc_type
          HAVING COUNT(*) > 1
        ) g
    """)).scalar() or 0

    counts["dup_client_objects"] = session.exec(text("""
        SELECT COALESCE(SUM(n - 1), 0) FROM (
          SELECT COUNT(*) AS n FROM client_objects
          GROUP BY organization_id, LOWER(name)
          HAVING COUNT(*) > 1
        ) g
    """)).scalar() or 0

    return counts


def merge_orgs_by_trimmed_inn(session: Session) -> int:
    """Сливает пары организаций где один INN имеет leading-0, другой — нет.
    Канонический — тот, чей ИНН валидной длины (10 или 12)."""
    pairs = session.exec(text("""
        SELECT TRIM(LEADING '0' FROM TRIM(inn)) AS trimmed, ARRAY_AGG(id::text ORDER BY LENGTH(inn) DESC) AS ids
        FROM organizations
        GROUP BY trimmed
        HAVING COUNT(*) > 1
    """)).all()

    merged = 0
    for trimmed, ids in pairs:
        # First id has the longer (more digits) INN — likely canonical (with leading 0)
        canonical_id, *dup_ids = ids
        canonical = session.exec(text("SELECT id, inn, monthly_ap, total_debt, in_registry FROM organizations WHERE id = :i").bindparams(i=canonical_id)).one()
        for dup_id in dup_ids:
            dup = session.exec(text("SELECT id, inn, monthly_ap, total_debt, in_registry FROM organizations WHERE id = :i").bindparams(i=dup_id)).one()
            print(f"  merging org {dup.inn} -> {canonical.inn} (id {dup_id} -> {canonical_id})")
            # Migrate FK references
            session.exec(text("UPDATE contracts SET organization_id = :c WHERE organization_id = :d")
                         .bindparams(c=canonical_id, d=dup_id))
            session.exec(text("UPDATE documents SET organization_id = :c WHERE organization_id = :d")
                         .bindparams(c=canonical_id, d=dup_id))
            session.exec(text("UPDATE monthly_snapshots SET organization_id = :c WHERE organization_id = :d")
                         .bindparams(c=canonical_id, d=dup_id))
            session.exec(text("UPDATE alerts SET organization_id = :c WHERE organization_id = :d")
                         .bindparams(c=canonical_id, d=dup_id))
            session.exec(text("UPDATE client_objects SET organization_id = :c WHERE organization_id = :d")
                         .bindparams(c=canonical_id, d=dup_id))
            # Copy non-empty financial fields if canonical missing them
            if canonical.monthly_ap is None and dup.monthly_ap is not None:
                session.exec(text("UPDATE organizations SET monthly_ap = :v WHERE id = :i")
                             .bindparams(v=dup.monthly_ap, i=canonical_id))
            if (canonical.total_debt is None or canonical.total_debt == 0) and dup.total_debt is not None:
                session.exec(text("UPDATE organizations SET total_debt = :v WHERE id = :i")
                             .bindparams(v=dup.total_debt, i=canonical_id))
            if not canonical.in_registry and dup.in_registry:
                session.exec(text("UPDATE organizations SET in_registry = TRUE WHERE id = :i")
                             .bindparams(i=canonical_id))
            # Delete the duplicate org
            session.exec(text("DELETE FROM organizations WHERE id = :i").bindparams(i=dup_id))
            merged += 1
    session.commit()
    return merged


def dedupe_documents(session: Session) -> int:
    """Удаляет дубль-Documents, оставляя самый ранний (created_at ASC) на каждую группу."""
    result = session.exec(text("""
        WITH ranked AS (
          SELECT id, ROW_NUMBER() OVER (
            PARTITION BY contract_id, COALESCE(doc_number,''), doc_date, amount, doc_type
            ORDER BY created_at ASC, id ASC
          ) AS rn FROM documents
        )
        DELETE FROM documents WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
    """))
    session.commit()
    return result.rowcount or 0


def dedupe_client_objects(session: Session) -> int:
    result = session.exec(text("""
        WITH ranked AS (
          SELECT id, ROW_NUMBER() OVER (
            PARTITION BY organization_id, LOWER(name)
            ORDER BY created_at ASC, id ASC
          ) AS rn FROM client_objects
        )
        DELETE FROM client_objects WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
    """))
    session.commit()
    return result.rowcount or 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--audit", action="store_true", help="Show only, do not modify")
    p.add_argument("--apply", action="store_true", help="Apply cleanup")
    p.add_argument("--skip-merge", action="store_true", help="Don't merge org duplicates")
    args = p.parse_args()

    if not args.audit and not args.apply:
        print("Specify --audit or --apply", file=sys.stderr)
        return 1

    with Session(engine) as session:
        print("=== BEFORE ===")
        before = audit(session)
        for k, v in before.items():
            print(f"  {k:30s} {v}")

        if args.audit:
            return 0

        if not args.skip_merge:
            print("\n=== Merging organizations ===")
            merged = merge_orgs_by_trimmed_inn(session)
            print(f"  merged: {merged}")

        print("\n=== Dedup documents ===")
        d = dedupe_documents(session)
        print(f"  deleted: {d}")

        print("\n=== Dedup client_objects ===")
        c = dedupe_client_objects(session)
        print(f"  deleted: {c}")

        print("\n=== AFTER ===")
        after = audit(session)
        for k, v in after.items():
            print(f"  {k:30s} {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
