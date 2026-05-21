"""Регресс: rebuild_for_organization должен корректно удалять старые
monthly_charges, даже если на них висят payment_allocations.

В практике это происходит при реассайне: PATCH-обновление клиента
(или скрипт реассайна транзитов) пересобирает леджер у target,
у которого уже есть allocs."""
from datetime import date
from decimal import Decimal

from sqlmodel import Session

from app.models import (
    AllocationBasis,
    ChargeSource,
    Contract,
    ContractType,
    DocType,
    Document,
    MonthlyCharge,
    Organization,
    OrgStatus,
    PaymentAllocation,
    TariffPeriod,
)
from app.services.charge_service import ChargeService


def test_rebuild_clears_charges_with_existing_allocations(db_session: Session):
    """rebuild_for_organization не падает по FK, если у клиента уже есть
    payment_allocations на его monthly_charges."""
    org = Organization(inn="7700000999", name_1c="Test",
                       status=OrgStatus.ACTIVE, monthly_ap=Decimal("10000"))
    db_session.add(org)

    db_session.commit()

    db_session.refresh(org)

    db_session.add(TariffPeriod(
        organization_id=org.id, valid_from=date(2026, 1, 1),
        monthly_amount=Decimal("10000"),
    ))
    db_session.commit()

    # Старый charge + alloc на нём
    old_charge = MonthlyCharge(
        organization_id=org.id, year=2026, month=1,
        amount=Decimal("10000"), source=ChargeSource.SYNTHETIC_TARIFF,
    )
    db_session.add(old_charge)

    db_session.commit()

    db_session.refresh(old_charge)

    contract = Contract(organization_id=org.id,
                        contract_type=ContractType.SUBSCRIPTION,
                        raw_name="x")
    db_session.add(contract)

    db_session.commit()

    db_session.refresh(contract)
    doc = Document(contract_id=contract.id, organization_id=org.id,
                   doc_type=DocType.PAYMENT, doc_date=date(2026, 1, 10),
                   amount=Decimal("10000"))
    db_session.add(doc)

    db_session.commit()

    db_session.refresh(doc)
    db_session.add(PaymentAllocation(
        payment_document_id=doc.id, monthly_charge_id=old_charge.id,
        allocated_amount=Decimal("10000"),
        basis=AllocationBasis.EXPLICIT_PERIOD,
    ))
    db_session.commit()

    # Раньше падало с FK violation; теперь helper чистит allocs перед charges.
    svc = ChargeService(db_session)
    svc.rebuild_for_organization(
        org.id, start=date(2026, 1, 1), through=date(2026, 3, 1),
    )

    # Старый charge удалён, allocs тоже
    remaining = svc._charges(org.id)
    assert len(remaining) == 3  # январь, февраль, март
    assert old_charge.id not in {c.id for c in remaining}
