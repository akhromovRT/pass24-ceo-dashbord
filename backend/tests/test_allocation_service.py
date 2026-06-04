from datetime import date
from decimal import Decimal

from sqlmodel import select

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
from app.services.allocation_service import AllocationService


def _setup_client(session, monthly="10000"):
    org = Organization(
        inn="7700000002", name_1c="Клиент", status=OrgStatus.ACTIVE, monthly_ap=Decimal(monthly)
    )
    session.add(org)
    session.flush()
    contract = Contract(
        organization_id=org.id,
        contract_type=ContractType.OTHER,
        contract_number="1C-PAYMENTS",
        raw_name="payments",
    )
    session.add(contract)
    session.flush()
    return org, contract


def _charge(session, org_id, year, month, amount="10000"):
    c = MonthlyCharge(
        organization_id=org_id,
        year=year,
        month=month,
        amount=Decimal(amount),
        source=ChargeSource.SYNTHETIC_TARIFF,
    )
    session.add(c)
    session.flush()
    return c


def _payment(session, org_id, contract_id, doc_date, amount, raw_name=""):
    d = Document(
        contract_id=contract_id,
        organization_id=org_id,
        doc_type=DocType.PAYMENT,
        doc_date=doc_date,
        amount=Decimal(amount),
        raw_name=raw_name,
    )
    session.add(d)
    session.flush()
    return d


def _allocs(session, org_id):
    return list(
        session.exec(
            select(PaymentAllocation, MonthlyCharge)
            .join(MonthlyCharge, MonthlyCharge.id == PaymentAllocation.monthly_charge_id)
            .where(MonthlyCharge.organization_id == org_id)
        ).all()
    )


def test_fifo_fills_oldest_first(db_session):
    org, contract = _setup_client(db_session)
    _charge(db_session, org.id, 2026, 1)
    _charge(db_session, org.id, 2026, 2)
    _payment(
        db_session, org.id, contract.id, date(2026, 3, 5), "15000", raw_name="оплата по счёту № 100"
    )
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
    _payment(
        db_session,
        org.id,
        contract.id,
        date(2026, 2, 10),
        "10000",
        raw_name="оплата за февраль 2026 за доступ",
    )
    db_session.commit()
    AllocationService(db_session).recompute_for_organization(org.id)
    db_session.commit()
    pairs = {
        (mc.year, mc.month): (a.allocated_amount, a.basis) for a, mc in _allocs(db_session, org.id)
    }
    assert pairs[(2026, 2)][0] == Decimal("10000")
    assert pairs[(2026, 2)][1] == AllocationBasis.EXPLICIT_PERIOD
    assert (2026, 1) not in pairs


def test_advance_creates_future_charges(db_session):
    org, contract = _setup_client(db_session)
    db_session.add(
        TariffPeriod(
            organization_id=org.id, valid_from=date(2026, 1, 1), monthly_amount=Decimal("10000")
        )
    )
    _charge(db_session, org.id, 2026, 1)
    _payment(
        db_session, org.id, contract.id, date(2026, 1, 20), "30000", raw_name="оплата по счёту № 5"
    )
    db_session.commit()
    AllocationService(db_session).recompute_for_organization(org.id)
    db_session.commit()
    pairs = {(mc.year, mc.month): a.allocated_amount for a, mc in _allocs(db_session, org.id)}
    assert pairs[(2026, 1)] == Decimal("10000")
    assert pairs[(2026, 2)] == Decimal("10000")
    assert pairs[(2026, 3)] == Decimal("10000")


def test_manual_allocation_preserved_on_recompute(db_session):
    org, contract = _setup_client(db_session)
    c1 = _charge(db_session, org.id, 2026, 1)
    pay = _payment(db_session, org.id, contract.id, date(2026, 3, 1), "10000", raw_name="оплата")
    db_session.add(
        PaymentAllocation(
            payment_document_id=pay.id,
            monthly_charge_id=c1.id,
            allocated_amount=Decimal("10000"),
            basis=AllocationBasis.MANUAL,
            is_manual=True,
        )
    )
    db_session.commit()
    AllocationService(db_session).recompute_for_organization(org.id)
    db_session.commit()
    rows = list(
        db_session.exec(
            select(PaymentAllocation).where(PaymentAllocation.payment_document_id == pay.id)
        ).all()
    )
    assert len(rows) == 1
    assert rows[0].is_manual is True


def test_recompute_is_idempotent(db_session):
    org, contract = _setup_client(db_session)
    _charge(db_session, org.id, 2026, 1)
    _payment(
        db_session, org.id, contract.id, date(2026, 1, 10), "7000", raw_name="оплата по счёту № 9"
    )
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
    _payment(
        db_session,
        org.id,
        contract.id,
        date(2026, 1, 10),
        "50000",
        raw_name="оплата за оборудование и монтаж системы",
    )
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


def test_bank_parser_filled_period_used_without_period_manual(db_session):
    """Регресс: банк-парсер разбил один входящий платёж на N Document с
    заполненными period_year/period_month, но period_manual=False. До
    fix'а 2026-05-29 AllocationService игнорировал эти поля и тащил
    периоды regex'ом из raw_name → 0 аллокаций (инцидент ООО «Веста»).
    """
    org, contract = _setup_client(db_session, monthly="12693.45")

    # Charges за дек'25 + янв–май'26 (то же что у Весты, без июня)
    charges = {}
    for y, m in [(2025, 12), (2026, 1), (2026, 2), (2026, 3), (2026, 4), (2026, 5)]:
        charges[(y, m)] = _charge(
            db_session,
            org.id,
            y,
            m,
            amount="10990" if (y, m) == (2025, 12) else "12693.45",
        )

    # 7 Document'ов от банк-парсера (одна транзакция, 7 строк с period_year/month).
    # period_manual=False — это автоматический парсер, не ручной ввод.
    common_raw = (
        "ОПЛАТА ПО ДОГОВОРУ №10297-/10/2024 ОТ 21.10.2024 ЗА ДОСТУП К СИСТЕМЕ "
        "PASS24.ONLINE ЗА ПЕРИОД ДЕКАБРЬ 2025 — ИЮНЬ 2026 СУММА 87 150,70 РУБ"
    )
    for y, m, amt in [
        (2025, 12, "10990"),
        (2026, 1, "12693.45"),
        (2026, 2, "12693.45"),
        (2026, 3, "12693.45"),
        (2026, 4, "12693.45"),
        (2026, 5, "12693.45"),
        (2026, 6, "12693.45"),  # за июнь — для charge не будет
    ]:
        d = Document(
            contract_id=contract.id,
            organization_id=org.id,
            doc_type=DocType.PAYMENT,
            doc_date=date(2026, 5, 27),
            amount=Decimal(amt),
            raw_name=common_raw,
            period_year=y,
            period_month=m,
            period_manual=False,  # ← важно: бан-парсер не ставит manual
        )
        db_session.add(d)
    db_session.flush()

    AllocationService(db_session).recompute_for_organization(org.id)
    db_session.flush()

    # Главное для бизнеса: 6 charges (дек'25 — май'26) закрыты полностью.
    # Платёж за июнь'26 — без charge, попадает в ADVANCE (нормально).
    # До fix'а 2026-05-29 ни одна аллокация не создавалась (AllocationService
    # игнорировал BANK-IMPORT платежи).
    all_allocs = db_session.exec(
        select(PaymentAllocation)
        .join(Document, Document.id == PaymentAllocation.payment_document_id)
        .where(Document.organization_id == org.id)
    ).all()
    total_allocated_to_charges = sum(
        a.allocated_amount for a in all_allocs if a.monthly_charge_id is not None
    )
    expected_total = sum(c.amount for c in charges.values())
    assert total_allocated_to_charges == expected_total, (
        f"должно быть разнесено {expected_total} (сумма всех charges), "
        f"разнесено {total_allocated_to_charges}"
    )
    # Все 6 charges должны быть закрыты (хотя бы одной аллокацией)
    closed_charges = {a.monthly_charge_id for a in all_allocs if a.monthly_charge_id is not None}
    assert (
        len(closed_charges) == 6
    ), f"должны быть закрыты все 6 charges, закрыто {len(closed_charges)}"


def test_total_debt_not_overwritten_by_ledger(db_session):
    """ADR-025: источник истины для Organization.total_debt — импорт
    долгового отчёта 1С, а НЕ AR-леджер. recompute_for_organization
    пересобирает аллокации, но total_debt не трогает.

    Регресс на дрейф 2026-06-04: P3.0.5.1 (`_sync_total_debt`) перезаписывал
    total_debt суммой непогашенных charges леджера, который завышал долг
    (фантомные начисления вперёд, незахваченные зачёты 1С) — дашборд уехал
    с 3,98M до 8,22M. 1С — master финансов, total_debt = его значение."""
    org, contract = _setup_client(db_session, monthly="10000")
    # total_debt из импорта 1С-отчёта — единственный авторитетный источник
    org.total_debt = Decimal("99999.99")
    db_session.add(org)
    db_session.flush()

    # 2 charges, оплачен только первый: леджер посчитал бы долг 10000,
    # но total_debt должен остаться 1С-значением, не подмениться леджером.
    _charge(db_session, org.id, 2026, 1, amount="10000")
    _charge(db_session, org.id, 2026, 2, amount="10000")
    _payment(
        db_session,
        org.id,
        contract.id,
        date(2026, 1, 10),
        "10000",
        raw_name="оплата за январь 2026",
    )
    db_session.flush()

    AllocationService(db_session).recompute_for_organization(org.id)
    db_session.commit()
    db_session.refresh(org)
    # Леджер НЕ перезаписал total_debt — осталось значение из 1С-импорта.
    assert org.total_debt == Decimal("99999.99")
