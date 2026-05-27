"""Backfill DebtSnapshot для существующего ImportRun.

Парсит исходный файл (тем же парсером, что и регулярный импорт), затем создаёт
DebtSnapshot + DebtSnapshotRow для каждой buyer/contract/document-строки и
связывает с уже существующими Organization/Contract/Document в БД.

Использование:
    python backend/scripts/backfill_debt_snapshot.py \
        --import-run-id <UUID> \
        --file /path/to/Задолженность.xls
"""
from __future__ import annotations

import argparse
import sys
import uuid
from decimal import Decimal
from pathlib import Path

# Запуск из корня репо или из backend/
HERE = Path(__file__).resolve()
BACKEND = HERE.parent.parent
sys.path.insert(0, str(BACKEND))

from sqlmodel import Session, select  # noqa: E402

from app.core.database import engine  # noqa: E402
from app.models import (  # noqa: E402
    Contract, DebtSnapshot, DebtSnapshotLevel, DebtSnapshotRow,
    Document, ImportRun, Organization,
)
from app.parser.debt_report import parse_debt_report  # noqa: E402


def _sum(buyers, field: str) -> Decimal | None:
    total = Decimal(0)
    seen = False
    for b in buyers:
        v = getattr(b, field, None)
        if v is not None:
            total += v
            seen = True
    return total if seen else None


def backfill(import_run_id: uuid.UUID, file_path: Path) -> dict:
    parse_result = parse_debt_report(file_path)
    print(f"Parser: buyers={parse_result.buyers_count} "
          f"contracts={parse_result.contracts_count} "
          f"documents={parse_result.documents_count} "
          f"errors={len(parse_result.errors)}")
    if parse_result.errors:
        print(f"WARN: {len(parse_result.errors)} ошибок парсера; backfill продолжается.")

    with Session(engine) as session:
        run = session.exec(
            select(ImportRun).where(ImportRun.id == import_run_id)
        ).first()
        if not run:
            raise SystemExit(f"ImportRun {import_run_id} не найден")

        existing = session.exec(
            select(DebtSnapshot).where(DebtSnapshot.import_run_id == import_run_id)
        ).first()
        if existing:
            raise SystemExit(
                f"DebtSnapshot для ImportRun {import_run_id} уже существует "
                f"(id={existing.id}). Backfill не нужен."
            )

        # Кеш Organization по ИНН, Contract по (org_id, contract_number),
        # Document по (org_id, doc_number, doc_date, doc_type/raw_name) —
        # последний пытаемся найти, но не критично если не сопоставлено.
        snapshot = DebtSnapshot(
            import_run_id=run.id,
            filename=run.filename,
            period_start=parse_result.period_start,
            period_end=parse_result.period_end,
            total_debt_start=_sum(parse_result.buyers, "debt_start"),
            total_advance_start=_sum(parse_result.buyers, "advance_start"),
            total_sold=_sum(parse_result.buyers, "sold"),
            total_paid=_sum(parse_result.buyers, "paid"),
            total_prepay_in=_sum(parse_result.buyers, "prepay_in"),
            total_prepay_used=_sum(parse_result.buyers, "prepay_used"),
            total_debt_end=_sum(parse_result.buyers, "debt_end"),
            total_advance_end=_sum(parse_result.buyers, "advance_end"),
            buyers_count=parse_result.buyers_count,
            contracts_count=parse_result.contracts_count,
            documents_count=parse_result.documents_count,
            buyers_no_inn_count=sum(1 for b in parse_result.buyers if not b.inn),
        )
        session.add(snapshot)
        session.flush()

        row_index = 0
        linked_orgs = linked_contracts = linked_docs = 0

        for buyer in parse_result.buyers:
            org = None
            if buyer.inn:
                org = session.exec(
                    select(Organization).where(Organization.inn == buyer.inn)
                ).first()
                if org:
                    linked_orgs += 1

            buyer_row = DebtSnapshotRow(
                snapshot_id=snapshot.id,
                parent_row_id=None,
                level=DebtSnapshotLevel.BUYER,
                row_index=row_index,
                raw_name=buyer.name,
                raw_inn=buyer.inn or None,
                debt_start=buyer.debt_start,
                advance_start=buyer.advance_start,
                sold=buyer.sold,
                paid=buyer.paid,
                prepay_in=buyer.prepay_in,
                prepay_used=buyer.prepay_used,
                debt_end=buyer.debt_end,
                advance_end=buyer.advance_end,
                organization_id=org.id if org else None,
            )
            session.add(buyer_row)
            session.flush()
            row_index += 1

            for parsed_contract in buyer.contracts:
                contract_db = None
                if org and parsed_contract.contract_number:
                    contract_db = session.exec(
                        select(Contract).where(
                            Contract.organization_id == org.id,
                            Contract.contract_number == parsed_contract.contract_number,
                        )
                    ).first()
                    if contract_db:
                        linked_contracts += 1

                contract_row = DebtSnapshotRow(
                    snapshot_id=snapshot.id,
                    parent_row_id=buyer_row.id,
                    level=DebtSnapshotLevel.CONTRACT,
                    row_index=row_index,
                    raw_name=parsed_contract.raw_name,
                    contract_number=parsed_contract.contract_number,
                    contract_date=parsed_contract.contract_date,
                    debt_start=parsed_contract.debt_start,
                    advance_start=parsed_contract.advance_start,
                    sold=parsed_contract.sold,
                    paid=parsed_contract.paid,
                    prepay_in=parsed_contract.prepay_in,
                    prepay_used=parsed_contract.prepay_used,
                    debt_end=parsed_contract.debt_end,
                    advance_end=parsed_contract.advance_end,
                    organization_id=org.id if org else None,
                    contract_id=contract_db.id if contract_db else None,
                )
                session.add(contract_row)
                session.flush()
                row_index += 1

                for parsed_doc in parsed_contract.documents:
                    doc_db = None
                    if contract_db and parsed_doc.doc_number and parsed_doc.doc_date:
                        doc_db = session.exec(
                            select(Document)
                            .where(Document.contract_id == contract_db.id)
                            .where(Document.doc_number == parsed_doc.doc_number)
                            .where(Document.doc_date == parsed_doc.doc_date)
                        ).first()
                        if doc_db:
                            linked_docs += 1

                    doc_row = DebtSnapshotRow(
                        snapshot_id=snapshot.id,
                        parent_row_id=contract_row.id,
                        level=DebtSnapshotLevel.DOCUMENT,
                        row_index=row_index,
                        raw_name=parsed_doc.raw_name,
                        doc_type=parsed_doc.doc_type,
                        doc_number=parsed_doc.doc_number,
                        doc_date=parsed_doc.doc_date,
                        debt_start=parsed_doc.debt_start,
                        advance_start=parsed_doc.advance_start,
                        sold=parsed_doc.sold,
                        paid=parsed_doc.paid,
                        prepay_in=parsed_doc.prepay_in,
                        prepay_used=parsed_doc.prepay_used,
                        debt_end=parsed_doc.debt_end,
                        advance_end=parsed_doc.advance_end,
                        organization_id=org.id if org else None,
                        contract_id=contract_db.id if contract_db else None,
                        document_id=doc_db.id if doc_db else None,
                    )
                    session.add(doc_row)
                    row_index += 1

        session.commit()

        return {
            "snapshot_id": str(snapshot.id),
            "rows_total": row_index,
            "linked_orgs": linked_orgs,
            "linked_contracts": linked_contracts,
            "linked_docs": linked_docs,
            "total_debt_end": str(snapshot.total_debt_end),
            "total_advance_end": str(snapshot.total_advance_end),
        }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--import-run-id", required=True)
    ap.add_argument("--file", required=True)
    args = ap.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        raise SystemExit(f"Файл не найден: {file_path}")

    result = backfill(uuid.UUID(args.import_run_id), file_path)
    import json
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
