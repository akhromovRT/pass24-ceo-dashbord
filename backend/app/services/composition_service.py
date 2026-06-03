"""Состав KPI-показателя дашборда (drill-down).

Backend для пресета composition в /reports. Для каждой метрики
возвращает список клиентов, формирующих её значение, и поддерживает
control_value — сумму/счёт, обязанную совпасть с плиткой Dashboard."""

from datetime import date

from sqlmodel import Session, func, select

from app.models import (
    MonthlyCharge,
    Organization,
    OrgStatus,
    PaymentAllocation,
    User,
)
from app.services.dashboard_service import (
    active_overdue_ids,
    churned_this_year_ids,
    excl,
    first_pay_rows,
    last_pay_rows,
    to_float,
)

_RU_MONTHS = [
    "январь",
    "февраль",
    "март",
    "апрель",
    "май",
    "июнь",
    "июль",
    "август",
    "сентябрь",
    "октябрь",
    "ноябрь",
    "декабрь",
]

# --- каталог колонок ---------------------------------------------------------

COMPOSITION_COLUMNS: list[tuple[str, str]] = [
    ("name", "Клиент"),
    ("inn", "ИНН"),
    ("manager", "Менеджер"),
    ("monthly_ap", "АП/мес"),
    ("status", "Статус"),
    ("churn_month", "Месяц отключения"),
    ("city", "Город"),
    ("contribution", "Вклад в показатель, ₽"),
    ("first_payment_date", "Дата первого платежа"),
    ("last_payment_date", "Дата последнего платежа"),
    ("days_since_last", "Дней с последнего платежа"),
]

_BASE_COLS = ["name", "inn", "manager", "monthly_ap", "status", "churn_month", "city"]

_COLS_BY_METRIC: dict[str, list[str]] = {
    "mrr_fact": _BASE_COLS + ["contribution"],
    "collected_current": _BASE_COLS + ["contribution"],
    "mrr_plan": _BASE_COLS + ["contribution"],
    "active_clients": _BASE_COLS + ["last_payment_date"],
    "new_paid_curr_year": _BASE_COLS + ["first_payment_date"],
    "new_paid_prev_month": _BASE_COLS + ["first_payment_date"],
    "new_paid_curr_month": _BASE_COLS + ["first_payment_date"],
    "stopped_since_year_start": _BASE_COLS + ["last_payment_date"],
    "active_overdue": _BASE_COLS + ["last_payment_date", "days_since_last"],
}

MONEY_METRICS = {"mrr_fact", "collected_current", "mrr_plan"}

_STATUS_LABELS = {
    OrgStatus.ACTIVE: "Активен",
    OrgStatus.CHURNED: "Отток",
    OrgStatus.SUSPENDED: "Приостановлен",
    OrgStatus.PROSPECT: "Потенциальный",
    OrgStatus.TRANSIT: "Транзит",
}


def _parse_month(s: str | None) -> tuple[int, int] | None:
    if not s or "-" not in s:
        return None
    try:
        y, m = s.split("-")[:2]
        yi, mi = int(y), int(m)
        if 1 <= mi <= 12:
            return (yi, mi)
    except ValueError:
        return None
    return None


def _ru_month_label(period: tuple[int, int] | None) -> str:
    if not period:
        return ""
    y, m = period
    return f"{_RU_MONTHS[m - 1]} {y}"


def _contribution_header(metric: str, period: tuple[int, int] | None) -> str:
    if metric in ("mrr_fact", "collected_current"):
        return f"Собрано за {_ru_month_label(period)}, ₽" if period else "Собрано, ₽"
    if metric == "mrr_plan":
        return "АП/мес, ₽"
    return "Вклад в показатель, ₽"


def _managers(session: Session) -> dict:
    return {u.id: u.name for u in session.exec(select(User)).all()}


def _apply_org_filters(query, c):
    """Общие фильтры (excluded, manager, city, statuses) на запрос Organization."""
    if not c.include_excluded:
        query = query.where(excl())
    if c.manager_id:
        query = query.where(Organization.manager_id == c.manager_id)
    if c.city:
        query = query.where(func.lower(Organization.city_region).like(f"%{c.city.lower()}%"))
    statuses = [OrgStatus(s) for s in c.statuses if s in OrgStatus._value2member_map_]
    if statuses:
        query = query.where(Organization.status.in_(statuses))  # type: ignore[union-attr]
    return query


def _org_row(o: Organization, managers: dict) -> dict:
    return {
        "name": o.name_display or o.name_1c,
        "inn": o.inn,
        "manager": managers.get(o.manager_id, "—"),
        "monthly_ap": round(to_float(o.monthly_ap), 2) if o.monthly_ap else None,
        "status": _STATUS_LABELS.get(o.status, str(o.status)),
        "churn_month": (
            f"{_RU_MONTHS[o.churn_month.month - 1]} {o.churn_month.year}" if o.churn_month else ""
        ),
        "city": o.city_region or "—",
    }


# --- metric builders --------------------------------------------------------


def _build_mrr_fact(session: Session, c) -> list[dict]:
    period = _parse_month(c.period)
    if period is None:
        return []
    y, m = period
    contrib_query = (
        select(
            MonthlyCharge.organization_id,
            func.coalesce(func.sum(PaymentAllocation.allocated_amount), 0),
        )
        .select_from(PaymentAllocation)
        .join(MonthlyCharge, MonthlyCharge.id == PaymentAllocation.monthly_charge_id)
        .where(MonthlyCharge.year == y, MonthlyCharge.month == m)
        .group_by(MonthlyCharge.organization_id)
    )
    if not c.include_excluded:
        contrib_query = contrib_query.join(
            Organization, Organization.id == MonthlyCharge.organization_id
        ).where(excl())
    contrib_rows = session.exec(contrib_query).all()
    contrib = {oid: to_float(s) for oid, s in contrib_rows if to_float(s) > 0}
    if not contrib:
        return []
    org_query = select(Organization).where(Organization.id.in_(list(contrib)))  # type: ignore[union-attr]
    org_query = _apply_org_filters(org_query, c)
    orgs = list(session.exec(org_query).all())
    managers = _managers(session)
    out: list[dict] = []
    for o in orgs:
        row = _org_row(o, managers)
        row["contribution"] = round(contrib[o.id], 2)
        out.append(row)
    out.sort(key=lambda r: r["contribution"], reverse=True)
    return out


def _build_mrr_plan(session: Session, c) -> list[dict]:
    base = select(Organization).where(
        Organization.status == OrgStatus.ACTIVE,
        Organization.monthly_ap.is_not(None),  # type: ignore[union-attr]
        Organization.monthly_ap > 0,  # type: ignore[operator]
    )
    base = _apply_org_filters(base, c)
    orgs = list(session.exec(base).all())
    managers = _managers(session)
    out: list[dict] = []
    for o in orgs:
        row = _org_row(o, managers)
        row["contribution"] = round(to_float(o.monthly_ap), 2)
        out.append(row)
    out.sort(key=lambda r: r["contribution"], reverse=True)
    return out


def _build_active_clients(session: Session, c) -> list[dict]:
    base = select(Organization).where(Organization.status == OrgStatus.ACTIVE)
    base = _apply_org_filters(base, c)
    orgs = list(session.exec(base).all())
    managers = _managers(session)
    last_pay = dict(last_pay_rows(session))
    out: list[dict] = []
    for o in orgs:
        row = _org_row(o, managers)
        lp = last_pay.get(o.id)
        row["last_payment_date"] = lp.isoformat() if lp else None
        out.append(row)
    out.sort(key=lambda r: r.get("monthly_ap") or 0, reverse=True)
    return out


def _materialize_first_pay(session: Session, c, target_ids: set, first_pay: dict) -> list[dict]:
    if not target_ids:
        return []
    base = select(Organization).where(Organization.id.in_(list(target_ids)))  # type: ignore[union-attr]
    base = _apply_org_filters(base, c)
    orgs = list(session.exec(base).all())
    managers = _managers(session)
    out: list[dict] = []
    for o in orgs:
        row = _org_row(o, managers)
        fp = first_pay.get(o.id)
        row["first_payment_date"] = fp.isoformat() if fp else None
        out.append(row)
    out.sort(key=lambda r: r["first_payment_date"] or "", reverse=True)
    return out


def _build_new_paid_in_year(session: Session, c, year: int) -> list[dict]:
    first_pay = dict(first_pay_rows(session))
    target_ids = {oid for oid, d in first_pay.items() if d and d.year == year}
    return _materialize_first_pay(session, c, target_ids, first_pay)


def _build_new_paid_in_month(session: Session, c, year: int, month: int) -> list[dict]:
    first_pay = dict(first_pay_rows(session))
    target_ids = {oid for oid, d in first_pay.items() if d and d.year == year and d.month == month}
    return _materialize_first_pay(session, c, target_ids, first_pay)


def _build_new_paid_curr_year(session: Session, c) -> list[dict]:
    return _build_new_paid_in_year(session, c, date.today().year)


def _build_new_paid_prev_month(session: Session, c) -> list[dict]:
    today = date.today()
    if today.month > 1:
        return _build_new_paid_in_month(session, c, today.year, today.month - 1)
    return _build_new_paid_in_month(session, c, today.year - 1, 12)


def _build_new_paid_curr_month(session: Session, c) -> list[dict]:
    today = date.today()
    return _build_new_paid_in_month(session, c, today.year, today.month)


def _materialize_overdue_like(session: Session, c, target_ids: set) -> list[dict]:
    """Общая материализация для оттока и активных с просрочкой:
    строка клиента + дата последнего платежа + дней с него."""
    today = date.today()
    if not target_ids:
        return []
    last_pay = dict(last_pay_rows(session))
    base = select(Organization).where(Organization.id.in_(list(target_ids)))  # type: ignore[union-attr]
    base = _apply_org_filters(base, c)
    orgs = list(session.exec(base).all())
    managers = _managers(session)
    out: list[dict] = []
    for o in orgs:
        row = _org_row(o, managers)
        lp = last_pay.get(o.id)
        row["last_payment_date"] = lp.isoformat() if lp else None
        row["days_since_last"] = (today - lp).days if lp else None
        out.append(row)
    out.sort(key=lambda r: r.get("days_since_last") or 0, reverse=True)
    return out


def _build_churned(session: Session, c) -> list[dict]:
    """Отток — статус-driven (CHURNED этого года, выверено по 1С, ADR-024)."""
    return _materialize_overdue_like(session, c, churned_this_year_ids(session, date.today()))


def _build_active_overdue(session: Session, c) -> list[dict]:
    """Активные с просрочкой — сигнал для взыскания (не отток)."""
    return _materialize_overdue_like(session, c, active_overdue_ids(session, date.today()))


# --- dispatcher -------------------------------------------------------------

_DISPATCH: dict = {
    "mrr_fact": _build_mrr_fact,
    "collected_current": _build_mrr_fact,
    "mrr_plan": _build_mrr_plan,
    "active_clients": _build_active_clients,
    "new_paid_curr_year": _build_new_paid_curr_year,
    "new_paid_prev_month": _build_new_paid_prev_month,
    "new_paid_curr_month": _build_new_paid_curr_month,
    "stopped_since_year_start": _build_churned,
    "active_overdue": _build_active_overdue,
}


def build_composition_report(session: Session, c) -> list[dict]:
    if c.metric is None:
        raise ValueError("metric is required for composition preset")
    if c.metric not in _COLS_BY_METRIC:
        raise ValueError(f"unknown composition metric: {c.metric}")
    builder = _DISPATCH.get(c.metric)
    if builder is None:
        return []  # зарегистрировано в каталоге, ещё не реализовано
    return builder(session, c)


def control_value_for(metric: str, rows: list[dict]) -> float | int:
    if metric in MONEY_METRICS:
        return round(sum(float(r.get("contribution") or 0) for r in rows), 2)
    return len(rows)


def columns_for_composition(c) -> list[tuple[str, str]]:
    if c.metric not in _COLS_BY_METRIC:
        return COMPOSITION_COLUMNS
    period = _parse_month(c.period) if c.metric in ("mrr_fact", "collected_current") else None
    keys = _COLS_BY_METRIC[c.metric]
    if c.columns:
        chosen = set(c.columns)
        filtered = [k for k in keys if k in chosen]
        keys = filtered or keys
    catalog = dict(COMPOSITION_COLUMNS)
    out: list[tuple[str, str]] = []
    for k in keys:
        header = _contribution_header(c.metric, period) if k == "contribution" else catalog[k]
        out.append((k, header))
    return out
