"""Тесты на поведение churn_month: ChargeService обрезает по месяцу отключения,
ACTIVE-клиенты не затронуты."""
from datetime import date
from decimal import Decimal

from app.models import Organization, OrgStatus, TariffPeriod
from app.services.charge_service import ChargeService


def _org(session, status=OrgStatus.ACTIVE, churn_month=None, inn="7700000111"):
    org = Organization(
        inn=inn, name_1c="Тест", status=status,
        churn_month=churn_month, monthly_ap=Decimal("10000"),
    )
    session.add(org)
    session.flush()
    return org


def test_churned_with_churn_month_truncates_charges(db_session):
    """CHURNED + churn_month=2025-06-01 → начисления только до июня 2025 вкл."""
    org = _org(db_session, status=OrgStatus.CHURNED, churn_month=date(2025, 6, 1))
    db_session.add(TariffPeriod(
        organization_id=org.id, valid_from=date(2025, 1, 1),
        monthly_amount=Decimal("10000"),
    ))
    db_session.commit()

    svc = ChargeService(db_session)
    svc.rebuild_for_organization(
        org.id, start=date(2025, 1, 1), through=date(2025, 12, 31),
    )
    months = {(c.year, c.month) for c in svc._charges(org.id)}
    assert months == {(2025, m) for m in range(1, 7)}, (
        "После churn_month=июнь начисления не должны создаваться"
    )


def test_active_client_not_affected_by_churn_month_field(db_session):
    """Если status=ACTIVE, поле churn_month НЕ должно влиять на начисления.
    Это критично: активные клиенты выверены вручную, их леджер неприкосновенен."""
    org = _org(
        db_session, status=OrgStatus.ACTIVE,
        churn_month=date(2025, 3, 1),  # стороннее значение, не должно сработать
        inn="7700000222",
    )
    db_session.add(TariffPeriod(
        organization_id=org.id, valid_from=date(2025, 1, 1),
        monthly_amount=Decimal("10000"),
    ))
    db_session.commit()

    svc = ChargeService(db_session)
    svc.rebuild_for_organization(
        org.id, start=date(2025, 1, 1), through=date(2025, 12, 31),
    )
    months = {(c.year, c.month) for c in svc._charges(org.id)}
    assert months == {(2025, m) for m in range(1, 13)}, (
        "ACTIVE-клиент должен начислять весь период независимо от churn_month"
    )


def test_churned_without_churn_month_no_truncation(db_session):
    """CHURNED + churn_month=None → ведёт себя как раньше (полный период)."""
    org = _org(
        db_session, status=OrgStatus.CHURNED, churn_month=None,
        inn="7700000333",
    )
    db_session.add(TariffPeriod(
        organization_id=org.id, valid_from=date(2025, 1, 1),
        monthly_amount=Decimal("10000"),
    ))
    db_session.commit()

    svc = ChargeService(db_session)
    svc.rebuild_for_organization(
        org.id, start=date(2025, 1, 1), through=date(2025, 12, 31),
    )
    months = {(c.year, c.month) for c in svc._charges(org.id)}
    assert months == {(2025, m) for m in range(1, 13)}


def test_churn_month_before_start_yields_empty_ledger(db_session):
    """CHURNED, churn_month < start → лента пуста (защита от мусора)."""
    org = _org(
        db_session, status=OrgStatus.CHURNED,
        churn_month=date(2024, 6, 1), inn="7700000444",
    )
    db_session.add(TariffPeriod(
        organization_id=org.id, valid_from=date(2025, 1, 1),
        monthly_amount=Decimal("10000"),
    ))
    db_session.commit()

    svc = ChargeService(db_session)
    svc.rebuild_for_organization(
        org.id, start=date(2025, 1, 1), through=date(2025, 12, 31),
    )
    assert svc._charges(org.id) == []
