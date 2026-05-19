from datetime import date
from decimal import Decimal

from sqlmodel import select

from app.models import (
    AllocationBasis,
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


def _setup_client(session, monthly="10000"):
    org = Organization(inn="7700000002", name_1c="Клиент", status=OrgStatus.ACTIVE,
                       monthly_ap=Decimal(monthly))
    session.add(org)
    session.flush()
    contract = Contract(organization_id=org.id, contract_type=ContractType.OTHER,
                        contract_number="1C-PAYMENTS", raw_name="payments")
    session.add(contract)
    session.flush()
    return org, contract


def _charge(session, org_id, year, month, amount="10000"):
    c = MonthlyCharge(organization_id=org_id, year=year, month=month,
                      amount=Decimal(amount), source=ChargeSource.SYNTHETIC_TARIFF)
    session.add(c)
    session.flush()
    return c


def _payment(session, org_id, contract_id, doc_date, amount, raw_name=""):
    d = Document(contract_id=contract_id, organization_id=org_id,
                 doc_type=DocType.PAYMENT, doc_date=doc_date,
                 amount=Decimal(amount), raw_name=raw_name)
    session.add(d)
    session.flush()
    return d


def _allocs(session, org_id):
    return list(session.exec(
        select(PaymentAllocation, MonthlyCharge)
        .join(MonthlyCharge, MonthlyCharge.id == PaymentAllocation.monthly_charge_id)
        .where(MonthlyCharge.organization_id == org_id)
    ).all())


def test_fifo_fills_oldest_first(db_session):
    org, contract = _setup_client(db_session)
    _charge(db_session, org.id, 2026, 1)
    _charge(db_session, org.id, 2026, 2)
    _payment(db_session, org.id, contract.id, date(2026, 3, 5), "15000",
             raw_name="оплата по счёту № 100")
    db_session.commit()
    AllocationService(db_session).recompute_for_organization(org.id)
    db_session.commit()
    pairs = {(mc.year, mc.month): a.allocated_amount for a, mc in _allocs(db_session, org.id)}
    assert pairs[(2026, 1)] == Decimal("10000")
    assert pairs[(2026, 2)] == Decimal("5000")


def test_explicit_period_overrides_fifo(db_session):
    org, contract = _setup_client(db_session)
    _charge(db_session, org.id, 2026, 1)
    _charge(db_session, org.id, 2026, 2)
    _payment(db_session, org.id, contract.id, date(2026, 2, 10), "10000",
             raw_name="оплата за февраль 2026 за доступ")
    db_session.commit()
    AllocationService(db_session).recompute_for_organization(org.id)
    db_session.commit()
    pairs = {(mc.year, mc.month): (a.allocated_amount, a.basis)
             for a, mc in _allocs(db_session, org.id)}
    assert pairs[(2026, 2)][0] == Decimal("10000")
    assert pairs[(2026, 2)][1] == AllocationBasis.EXPLICIT_PERIOD
    assert (2026, 1) not in pairs


def test_advance_creates_future_charges(db_session):
    org, contract = _setup_client(db_session)
    db_session.add(TariffPeriod(organization_id=org.id, valid_from=date(2026, 1, 1),
                                monthly_amount=Decimal("10000")))
    _charge(db_session, org.id, 2026, 1)
    _payment(db_session, org.id, contract.id, date(2026, 1, 20), "30000",
             raw_name="оплата по счёту № 5")
    db_session.commit()
    AllocationService(db_session).recompute_for_organization(org.id)
    db_session.commit()
    pairs = {(mc.year, mc.month): a.allocated_amount
             for a, mc in _allocs(db_session, org.id)}
    assert pairs[(2026, 1)] == Decimal("10000")
    assert pairs[(2026, 2)] == Decimal("10000")
    assert pairs[(2026, 3)] == Decimal("10000")


def test_manual_allocation_preserved_on_recompute(db_session):
    org, contract = _setup_client(db_session)
    c1 = _charge(db_session, org.id, 2026, 1)
    pay = _payment(db_session, org.id, contract.id, date(2026, 3, 1), "10000",
                   raw_name="оплата")
    db_session.add(PaymentAllocation(payment_document_id=pay.id, monthly_charge_id=c1.id,
                                     allocated_amount=Decimal("10000"),
                                     basis=AllocationBasis.MANUAL, is_manual=True))
    db_session.commit()
    AllocationService(db_session).recompute_for_organization(org.id)
    db_session.commit()
    rows = list(db_session.exec(select(PaymentAllocation).where(
        PaymentAllocation.payment_document_id == pay.id)).all())
    assert len(rows) == 1
    assert rows[0].is_manual is True


def test_recompute_is_idempotent(db_session):
    org, contract = _setup_client(db_session)
    _charge(db_session, org.id, 2026, 1)
    _payment(db_session, org.id, contract.id, date(2026, 1, 10), "7000",
             raw_name="оплата по счёту № 9")
    db_session.commit()
    svc = AllocationService(db_session)
    svc.recompute_for_organization(org.id)
    db_session.commit()
    first = sorted((a.allocated_amount for a, _ in _allocs(db_session, org.id)))
    svc.recompute_for_organization(org.id)
    db_session.commit()
    second = sorted((a.allocated_amount for a, _ in _allocs(db_session, org.id)))
    assert first == second


def test_non_subscription_payment_not_allocated(db_session):
    org, contract = _setup_client(db_session)
    _charge(db_session, org.id, 2026, 1)
    _payment(db_session, org.id, contract.id, date(2026, 1, 10), "50000",
             raw_name="оплата за оборудование и монтаж системы")
    db_session.commit()
    AllocationService(db_session).recompute_for_organization(org.id)
    db_session.commit()
    assert _allocs(db_session, org.id) == []


def test_period_manual_overrides_regex_extraction(db_session):
    """Платёж с period_manual=True разносится на указанный месяц (EXPLICIT_PERIOD),
    игнорируя regex из raw_name."""
    org, contract = _setup_client(db_session, monthly="10000")

    # Начисление за май 2026
    charge_may = _charge(db_session, org.id, 2026, 5)

    # Документ с period_manual=True — указан 5/2026
    # raw_name содержит "за 03/2026" — regex нашёл бы 3/2026, но period_manual побеждает
    doc = Document(
        contract_id=contract.id,
        organization_id=org.id,
        doc_type=DocType.PAYMENT,
        doc_date=date(2026, 5, 18),
        amount=Decimal("10000"),
        raw_name="за 03/2026 доступ",
        period_year=2026,
        period_month=5,
        period_manual=True,
    )
    db_session.add(doc)
    db_session.flush()

    svc = AllocationService(db_session)
    svc.recompute_for_organization(org.id)
    db_session.flush()

    pairs = [(a, mc) for a, mc in _allocs(db_session, org.id)]
    assert len(pairs) == 1
    assert pairs[0][0].monthly_charge_id == charge_may.id
    assert pairs[0][0].basis == AllocationBasis.EXPLICIT_PERIOD
