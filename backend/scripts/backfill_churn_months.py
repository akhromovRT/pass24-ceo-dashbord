"""CLI: проставление churn_month для существующих CHURNED-клиентов.

Логика:
- Идёт только по клиентам в статусе CHURNED, у которых churn_month IS NULL.
- ACTIVE / SUSPENDED / PROSPECT — НЕ затрагиваются (требование выверенных
  активных клиентов).
- churn_month = месяц последнего платежа клиента (1-е число).
- Если у клиента 0 платежей — НЕ ставит, добавляет его в manual_review.
- Для проставленных вызывает ChargeService.rebuild_for_organization +
  AllocationService.recompute_for_organization.

Запуск: cd backend && python -m scripts.backfill_churn_months
        cd backend && python -m scripts.backfill_churn_months --dry-run
"""

from __future__ import annotations

import argparse
import json
from datetime import date

from sqlmodel import Session, create_engine, func, select

from app.core.config import settings
from app.models import DocType, Document, Organization, OrgStatus
from app.services.allocation_service import AllocationService
from app.services.charge_service import ChargeService


def _last_payment_month(session: Session, org_id) -> date | None:
    q = select(func.max(Document.doc_date)).where(
        Document.organization_id == org_id,
        Document.doc_type == DocType.PAYMENT,
        Document.doc_date.is_not(None),
    )
    last_dt = session.exec(q).one()
    if last_dt is None:
        return None
    return date(last_dt.year, last_dt.month, 1)


def backfill(session: Session, dry_run: bool = False) -> dict:
    candidates = list(
        session.exec(
            select(Organization).where(
                Organization.status == OrgStatus.CHURNED,
                Organization.churn_month.is_(None),
            )
        ).all()
    )

    processed: list[dict] = []
    manual_review: list[dict] = []
    charge_svc = ChargeService(session)
    alloc_svc = AllocationService(session)

    for org in candidates:
        last_month = _last_payment_month(session, org.id)
        if last_month is None:
            manual_review.append(
                {
                    "inn": org.inn,
                    "name": org.name_display or org.name_1c,
                    "reason": "0 платежей",
                }
            )
            continue

        if dry_run:
            processed.append(
                {
                    "inn": org.inn,
                    "name": org.name_display or org.name_1c,
                    "would_set_churn_month": last_month.isoformat(),
                }
            )
            continue

        org.churn_month = last_month
        session.add(org)
        session.flush()

        start = charge_svc.charge_start(org.id)
        if start is not None:
            charge_svc.rebuild_for_organization(
                org.id,
                start=start,
                through=date.today(),
            )
            alloc_svc.recompute_for_organization(org.id)

        processed.append(
            {
                "inn": org.inn,
                "name": org.name_display or org.name_1c,
                "churn_month": last_month.isoformat(),
            }
        )

    if not dry_run:
        session.commit()

    return {
        "candidates_total": len(candidates),
        "processed": processed,
        "manual_review": manual_review,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill churn_month для CHURNED-клиентов")
    parser.add_argument(
        "--dry-run", action="store_true", help="Только показать, что было бы сделано"
    )
    parser.add_argument("--json", action="store_true", help="Вывести результат в JSON")
    args = parser.parse_args()

    engine = create_engine(str(settings.DATABASE_URL), echo=False)
    with Session(engine) as session:
        result = backfill(session, dry_run=args.dry_run)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    mode = "DRY-RUN" if args.dry_run else "APPLY"
    print(f"=== Backfill churn_month [{mode}] ===")
    print(f"Кандидатов (CHURNED без churn_month): {result['candidates_total']}")
    print(f"Проставлено: {len(result['processed'])}")
    print(f"Требуют ручной проверки (0 платежей): {len(result['manual_review'])}")

    if result["processed"]:
        print("\n--- Проставлено ---")
        for r in result["processed"]:
            month = r.get("churn_month") or r.get("would_set_churn_month")
            print(f"  {r['inn']:<12} {month}  {r['name']}")

    if result["manual_review"]:
        print("\n--- Ручная проверка ---")
        for r in result["manual_review"]:
            print(f"  {r['inn']:<12} {r['reason']:<15}  {r['name']}")


if __name__ == "__main__":
    main()
