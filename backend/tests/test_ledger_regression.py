"""Регрессия: собираемость месяца не превышает начисление при платеже,
покрывающем несколько месяцев (аномалия марта 2026 — 127%)."""
from datetime import date
from decimal import Decimal

from sqlmodel import select

from app.models import (
    ChargeSource,
    Contract,
    ContractType,
    Document,
    DocType,
    MonthlyCharge,
    Organization,
    OrgStatus,
    PaymentAllocation,
    TariffPeriod,
)
from app.services.allocation_service import AllocationService


def test_advance_payment_does_not_inflate_target_month(db_session):
    org = Organization(inn="7700000099", name_1c="Регресс", status=OrgStatus.ACTIVE,
                       monthly_ap=Decimal("10000"))
    db_session.add(org)
    db_session.flush()
    db_session.add(TariffPeriod(organization_id=org.id, valid_from=date(2026, 1, 1),
                                monthly_amount=Decimal("10000")))
    contract = Contract(organization_id=org.id, contract_type=ContractType.OTHER,
                        contract_number="1C-PAYMENTS", raw_name="payments")
    db_session.add(contract)
    db_session.flush()
    for m in (1, 2, 3):
        db_session.add(MonthlyCharge(organization_id=org.id, year=2026, month=m,
                                     amount=Decimal("10000"),
                                     source=ChargeSource.SYNTHETIC_TARIFF))
    # в марте пришёл платёж на 30000 (март + 2 месяца авансом)
    db_session.add(Document(contract_id=contract.id, organization_id=org.id,
                            doc_type=DocType.PAYMENT, doc_date=date(2026, 3, 5),
                            amount=Decimal("30000"), raw_name="оплата по счёту № 1"))
    db_session.commit()

    AllocationService(db_session).recompute_for_organization(org.id)
    db_session.commit()

    march_charge = db_session.exec(
        select(MonthlyCharge).where(MonthlyCharge.year == 2026,
                                    MonthlyCharge.month == 3)).first()
    collected_march = sum(
        (a.allocated_amount for a in db_session.exec(
            select(PaymentAllocation).where(
                PaymentAllocation.monthly_charge_id == march_charge.id)).all()),
        Decimal("0"))
    assert collected_march <= march_charge.amount  # не 127%
