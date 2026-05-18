"""Backfill: построение AR-леджера по существующим данным. Идемпотентно."""
from datetime import date

from sqlmodel import Session, select

from app.models import Document, DocType, Organization, TariffPeriod
from app.parser.period_extraction import extract_periods
from app.services.allocation_service import AllocationService
from app.services.charge_service import ChargeService


def _seed_tariffs(session: Session) -> int:
    """По строке tariff_period на клиента с monthly_ap > 0, если ещё нет."""
    created = 0
    orgs = session.exec(
        select(Organization).where(Organization.monthly_ap.is_not(None),
                                   Organization.monthly_ap > 0)
    ).all()
    for org in orgs:
        exists = session.exec(
            select(TariffPeriod).where(TariffPeriod.organization_id == org.id)
        ).first()
        if exists:
            continue
        start = ChargeService(session).charge_start(org.id) or date(2024, 1, 1)
        session.add(TariffPeriod(organization_id=org.id, valid_from=start,
                                 monthly_amount=org.monthly_ap))
        created += 1
    session.flush()
    return created


def _refresh_payment_periods(session: Session) -> int:
    """Переизвлекает period_year/period_month у банк-платежей по raw_name."""
    updated = 0
    payments = session.exec(
        select(Document).where(Document.doc_type == DocType.PAYMENT,
                               Document.amount > 0)
    ).all()
    for d in payments:
        ep = extract_periods(d.raw_name or "", d.doc_date or date.today())
        if ep.periods:
            d.period_year, d.period_month = ep.periods[0]
        else:
            d.period_year, d.period_month = None, None
        session.add(d)
        updated += 1
    session.flush()
    return updated


def build_ledger(session: Session) -> dict:
    """Полный backfill AR-леджера. Возвращает сводку."""
    tariffs = _seed_tariffs(session)
    refreshed = _refresh_payment_periods(session)
    charge_svc = ChargeService(session)
    alloc_svc = AllocationService(session)
    orgs = session.exec(select(Organization)).all()
    today = date.today()
    rebuilt = 0
    for org in orgs:
        start = charge_svc.charge_start(org.id)
        if start is None:
            continue
        charge_svc.rebuild_for_organization(org.id, start=start, through=today)
        alloc_svc.recompute_for_organization(org.id)
        rebuilt += 1
    session.commit()
    return {"tariffs_seeded": tariffs, "payments_refreshed": refreshed,
            "orgs_rebuilt": rebuilt}
