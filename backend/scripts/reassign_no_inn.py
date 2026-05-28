"""CEO24 — переназначить платежи без ИНН на целевую организацию.

Use case: банк-выписка содержит платежи от ФЛ через СБП — банк не передаёт ИНН
плательщика, эти записи попадают в `ImportRun.errors[type=no_inn]`. Этот скрипт
повторно парсит исходный файл выписки, находит платежи без ИНН по подстроке в
counterparty, и привязывает их к организации по указанному ИНН.

Использование:
    python scripts/reassign_no_inn.py \
        --file /tmp/bank.xlsx \
        --counterparty-like "ГОНЦОВА" \
        --target-inn 773179504256 \
        --import-run-id 0a92e084-c713-45c3-82bb-d52214506885
        [--dry-run]
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid

# Make `app` importable when invoked as a file.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from sqlmodel import Session, select

from app.core.database import engine
from app.models import (
    Contract,
    ContractStatus,
    ContractType,
    DocType,
    Document,
    ImportRun,
    Organization,
)
from app.parser.bank_statement import parse_bank_statement

_BANK_SYNTH_CONTRACT_NUMBER = "BANK-IMPORT"


def main() -> int:
    p = argparse.ArgumentParser(description="Reassign no-INN bank payments to a target org")
    p.add_argument("--file", required=True, help="Path to original bank statement xlsx/xls")
    p.add_argument(
        "--counterparty-like",
        required=True,
        help="Substring to match in counterparty (case-insensitive)",
    )
    p.add_argument("--target-inn", required=True, help="Target organization INN")
    p.add_argument(
        "--import-run-id", required=True, help="Original ImportRun UUID to attach payments to"
    )
    p.add_argument("--dry-run", action="store_true", help="Show what would be done without writing")
    args = p.parse_args()

    # Parse the file
    result = parse_bank_statement(args.file)
    pattern = args.counterparty_like.upper()

    candidates = [
        pp
        for pp in result.payments
        if not (pp.inn or "").strip() and pattern in (pp.counterparty or "").upper()
    ]

    if not candidates:
        print(
            f"No no-INN payments matching counterparty contains '{args.counterparty_like}'",
            file=sys.stderr,
        )
        return 1

    print(f"Found {len(candidates)} no-INN payments matching '{args.counterparty_like}':")
    for pp in candidates:
        print(f"  {pp.date}  amount={pp.amount}  counterparty={pp.counterparty}")
    print(f"\nTarget INN: {args.target_inn}")
    print(f"Target ImportRun: {args.import_run_id}\n")

    with Session(engine) as session:
        org = session.exec(select(Organization).where(Organization.inn == args.target_inn)).first()
        if not org:
            print(f"ERROR: organization with INN={args.target_inn} not found", file=sys.stderr)
            return 2
        print(f"Target org: {org.name_1c} ({org.id})")

        try:
            run_uuid = uuid.UUID(args.import_run_id)
        except ValueError:
            print("ERROR: invalid import-run-id UUID", file=sys.stderr)
            return 2

        import_run = session.get(ImportRun, run_uuid)
        if not import_run:
            print(f"ERROR: ImportRun {args.import_run_id} not found", file=sys.stderr)
            return 2

        # Find or create synthetic contract
        contract = session.exec(
            select(Contract).where(
                Contract.organization_id == org.id,
                Contract.contract_number == _BANK_SYNTH_CONTRACT_NUMBER,
            )
        ).first()
        if not contract:
            print(f"Creating synthetic BANK-IMPORT contract for {org.name_1c}")
            if not args.dry_run:
                contract = Contract(
                    organization_id=org.id,
                    contract_number=_BANK_SYNTH_CONTRACT_NUMBER,
                    contract_type=ContractType.OTHER,
                    classification_source="bank_import",
                    classification_rule="synthetic",
                    raw_name="Платежи из банк-выписки без привязки к договору 1С",
                    status=ContractStatus.ACTIVE,
                )
                session.add(contract)
                session.flush()

        created = 0
        for pp in candidates:
            doc = Document(
                contract_id=contract.id if contract else uuid.uuid4(),
                organization_id=org.id,
                doc_type=DocType.PAYMENT,
                doc_number=pp.doc_number or None,
                doc_date=pp.date,
                amount=pp.amount,
                period_year=pp.payment_info.period_year if pp.payment_info else None,
                period_month=pp.payment_info.period_month if pp.payment_info else None,
                import_run_id=import_run.id,
                raw_name=(
                    pp.description or f"Reassigned no-INN payment, counterparty: {pp.counterparty}"
                )[:500],
            )
            if not args.dry_run:
                session.add(doc)
            created += 1
            print(f"  + Document: {pp.date} {pp.amount} '{(pp.description or '')[:60]}'")

        # Update import_run counters
        if not args.dry_run:
            # Decrease errors[] entries with matching counterparty + same date+amount
            new_errors = []
            removed = 0
            for e in import_run.errors or []:
                if e.get("type") == "no_inn" and pattern in (e.get("counterparty") or "").upper():
                    removed += 1
                    continue
                new_errors.append(e)
            import_run.errors = new_errors or None
            import_run.documents_count = (import_run.documents_count or 0) + created
            # Update delta_summary
            if import_run.delta_summary and "skipped_no_inn" in import_run.delta_summary:
                ds = dict(import_run.delta_summary)
                ds["skipped_no_inn"] = max(0, ds.get("skipped_no_inn", 0) - removed)
                ds.setdefault("reassigned", 0)
                ds["reassigned"] += created
                import_run.delta_summary = ds
            session.add(import_run)
            session.commit()
            print(
                f"\nOK: reassigned {created} payment(s). Removed {removed} error(s) from ImportRun."
            )
        else:
            print(f"\n[DRY-RUN] Would reassign {created} payment(s).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
