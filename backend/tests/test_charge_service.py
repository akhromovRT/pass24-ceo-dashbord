from datetime import date
from decimal import Decimal

from app.models import (
    Contract,
    ContractType,
    DocType,
    Document,
    Organization,
    OrgStatus,
    TariffPeriod,
)
from app.models.monthly_charge import ChargeSource
from app.services.charge_service import ChargeService


def _org(session, monthly_ap="10000"):
    org = Organization(
        inn="7700000001", name_1c="Тест", status=OrgStatus.ACTIVE, monthly_ap=Decimal(monthly_ap)
    )
    session.add(org)
    session.flush()
    return org


def test_synthetic_charges_from_tariff(db_session):
    org = _org(db_session)
    db_session.add(
        TariffPeriod(
            organization_id=org.id, valid_from=date(2026, 1, 1), monthly_amount=Decimal("10000")
        )
    )
    db_session.commit()
    svc = ChargeService(db_session)
    svc.rebuild_for_organization(org.id, start=date(2026, 1, 1), through=date(2026, 3, 31))
    charges = svc._charges(org.id)
    assert {(c.year, c.month) for c in charges} == {(2026, 1), (2026, 2), (2026, 3)}
    assert all(c.amount == Decimal("10000") for c in charges)
    assert all(c.source == ChargeSource.SYNTHETIC_TARIFF for c in charges)


def test_realization_overrides_synthetic(db_session):
    org = _org(db_session)
    db_session.add(
        TariffPeriod(
            organization_id=org.id, valid_from=date(2026, 1, 1), monthly_amount=Decimal("10000")
        )
    )
    c = Contract(
        organization_id=org.id, contract_type=ContractType.SUBSCRIPTION, raw_name="Договор подписки"
    )
    db_session.add(c)
    db_session.flush()
    db_session.add(
        Document(
            contract_id=c.id,
            organization_id=org.id,
            doc_type=DocType.SALE,
            doc_date=date(2026, 2, 1),
            amount=Decimal("11500"),
        )
    )
    db_session.commit()
    svc = ChargeService(db_session)
    svc.rebuild_for_organization(org.id, start=date(2026, 1, 1), through=date(2026, 3, 31))
    by_month = {(c.year, c.month): c for c in svc._charges(org.id)}
    assert by_month[(2026, 2)].amount == Decimal("11500")
    assert by_month[(2026, 2)].source == ChargeSource.REALIZATION_1C
    assert by_month[(2026, 1)].source == ChargeSource.SYNTHETIC_TARIFF


def test_charge_range_from_first_activity(db_session):
    org = _org(db_session)
    db_session.add(
        TariffPeriod(
            organization_id=org.id, valid_from=date(2025, 11, 1), monthly_amount=Decimal("10000")
        )
    )
    c = Contract(
        organization_id=org.id, contract_type=ContractType.SUBSCRIPTION, raw_name="Договор"
    )
    db_session.add(c)
    db_session.flush()
    db_session.add(
        Document(
            contract_id=c.id,
            organization_id=org.id,
            doc_type=DocType.SALE,
            doc_date=date(2025, 12, 1),
            amount=Decimal("10000"),
        )
    )
    db_session.commit()
    svc = ChargeService(db_session)
    start = svc.charge_start(org.id)
    assert start == date(2025, 11, 1)
