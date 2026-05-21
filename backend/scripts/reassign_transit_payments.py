"""Реассайн платежей транзитных плательщиков на конечных клиентов.

TRANSIT-организация — это юр.лицо, которое платило за другого клиента
(а не за себя) либо старая карточка после переоформления ИНН. Её платежи
должны висеть на конечном клиенте.

Алгоритм:
1) Все PAYMENT-документы транзитника (любые контракты).
2) Для каждого: найти/создать у target контракт с тем же contract_number
   и contract_type — сохраняем провенанс (1C-PAYMENTS / BANK-IMPORT).
3) Подменить Document.organization_id и Document.contract_id.
4) Удалить старые аллокации (на charges транзитника, остановленных).
5) Пересобрать charges + аллокации у target — AllocationService разнесёт
   подписочные платежи; не-периодические (монтаж, оборудование) останутся
   в `non_subscription` корзине Cash Inflow.

Usage:
  docker compose exec backend python -m scripts.reassign_transit_payments --dry-run
  docker compose exec backend python -m scripts.reassign_transit_payments --apply
"""
import argparse
import sys
from datetime import date
from decimal import Decimal

from sqlmodel import Session, select

from app.core.database import engine
from app.models import (
    Contract, DocType, Document, Organization, PaymentAllocation,
)
from app.services.allocation_service import AllocationService
from app.services.charge_service import ChargeService

REASSIGNMENTS = [
    ("5018126839",   "071513837810", "ПРОМСТРОЙХОЛДИНГ → Гаджикурбанов"),
    ("771872988874", "7751306500",   "Мораш Олеся → ГАРД-КОМФОРТ"),
    ("7707083893",   "5048023661",   "Сбербанк/Реутова → Белое озеро"),
    ("7730036250",   "7710176315",   "Автокомбинат №1 → ФЛЭТ И КО"),
    ("771819486660", "7751306500",   "Котельников → ГАРД-КОМФОРТ"),
]


def _find_org(session, inn):
    org = session.exec(select(Organization).where(Organization.inn == inn)).first()
    if org is None:
        raise SystemExit(f"Не найдена организация ИНН={inn}")
    return org


def _find_or_create_contract(session, org, contract_number, contract_type, raw_name):
    c = session.exec(
        select(Contract).where(
            Contract.organization_id == org.id,
            Contract.contract_number == contract_number,
        )
    ).first()
    if c is not None:
        return c
    c = Contract(
        organization_id=org.id,
        contract_number=contract_number,
        contract_type=contract_type,
        raw_name=raw_name or contract_number,
    )
    session.add(c)
    session.flush()
    return c


def reassign_one(session, transit_inn, target_inn, label, apply):
    transit = _find_org(session, transit_inn)
    target = _find_org(session, target_inn)
    if transit.id == target.id:
        raise SystemExit(f"transit и target совпадают: {transit_inn}")

    docs = list(session.exec(
        select(Document).where(
            Document.organization_id == transit.id,
            Document.doc_type == DocType.PAYMENT,
        )
    ).all())
    total = sum(Decimal(str(d.amount or 0)) for d in docs)

    contracts_seen = {}
    for d in docs:
        if d.contract_id not in contracts_seen:
            c = session.get(Contract, d.contract_id)
            if c is not None:
                contracts_seen[d.contract_id] = c.contract_number

    summary = {
        "label": label,
        "transit": {"inn": transit.inn, "name": transit.name_display or transit.name_1c},
        "target":  {"inn": target.inn,  "name": target.name_display or target.name_1c},
        "docs_count": len(docs),
        "total_amount": float(total),
        "contracts": sorted({v for v in contracts_seen.values() if v}),
        "dates": sorted({str(d.doc_date) for d in docs if d.doc_date})[:5],
    }

    if not apply or not docs:
        return summary

    # Удалим аллокации на этих документах (если есть)
    doc_ids = [d.id for d in docs]
    old_allocs = list(session.exec(
        select(PaymentAllocation).where(
            PaymentAllocation.payment_document_id.in_(doc_ids)  # type: ignore[union-attr]
        )
    ).all())
    for a in old_allocs:
        session.delete(a)
    summary["removed_allocs"] = len(old_allocs)

    # Реассайн: для каждого документа находим/создаём контракт того же
    # типа у target и подменяем organization_id + contract_id
    contract_map = {}  # transit_contract_id → target_contract_id
    for d in docs:
        orig_c = session.get(Contract, d.contract_id)
        if orig_c is None:
            raise SystemExit(f"Document {d.id} ссылается на несуществующий contract {d.contract_id}")
        if orig_c.id not in contract_map:
            target_c = _find_or_create_contract(
                session, target, orig_c.contract_number, orig_c.contract_type, orig_c.raw_name,
            )
            contract_map[orig_c.id] = target_c.id
        d.organization_id = target.id
        d.contract_id = contract_map[orig_c.id]
        session.add(d)
    session.flush()

    # Пересобрать charges + аллокации у target.
    # Перед rebuild удалим ВСЕ аллокации связанные с charges target — иначе
    # FK constraint на payment_allocations не даст удалить monthly_charges.
    from app.models import MonthlyCharge
    target_charge_ids = list(session.exec(
        select(MonthlyCharge.id).where(MonthlyCharge.organization_id == target.id)
    ).all())
    if target_charge_ids:
        target_allocs = list(session.exec(
            select(PaymentAllocation).where(
                PaymentAllocation.monthly_charge_id.in_(target_charge_ids)  # type: ignore[union-attr]
            )
        ).all())
        for a in target_allocs:
            session.delete(a)
        session.flush()

    charge_svc = ChargeService(session)
    start = charge_svc.charge_start(target.id)
    if start is not None:
        charge_svc.rebuild_for_organization(
            target.id, start=start, through=date.today(),
        )
        AllocationService(session).recompute_for_organization(target.id)

    return summary


def main():
    parser = argparse.ArgumentParser()
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--dry-run", action="store_true")
    grp.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== Транзитный реассайн платежей ({mode}) ===\n")

    grand_total = 0
    with Session(engine) as session:
        for transit_inn, target_inn, label in REASSIGNMENTS:
            try:
                s = reassign_one(session, transit_inn, target_inn, label,
                                 apply=args.apply)
            except Exception as e:
                print(f"  ✗ {label}: {e}")
                continue
            grand_total += s["total_amount"]
            print(f"▪ {s['label']}")
            print(f"    transit: {s['transit']['inn']:>14} {s['transit']['name'][:55]:55}")
            print(f"    target:  {s['target']['inn']:>14} {s['target']['name'][:55]:55}")
            amt = f"{s['total_amount']:,.0f}".replace(",", " ")
            print(f"    docs: {s['docs_count']}, sum: {amt} RUB")
            if s.get("contracts"):
                print(f"    contracts: {', '.join(s['contracts'])}")
            if s.get("dates"):
                print(f"    sample dates: {', '.join(s['dates'])}")
            if "removed_allocs" in s:
                print(f"    removed_allocs: {s['removed_allocs']}")
            print()

        gt = f"{grand_total:,.0f}".replace(",", " ")
        print(f"=== Σ переносим: {gt} RUB ===")

        if args.apply:
            session.commit()
            print("OK commit done")
        else:
            print("(dry-run — изменения не сохранены)")


if __name__ == "__main__":
    sys.exit(main())
