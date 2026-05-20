# Dashboard Drill-down Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Клик по каждой из 8 KPI-плиток дашборда открывает раздел «Отчёты» с преднастроенным фильтром, который раскрывает список клиентов и сумм, формирующих показатель; контрольная сумма drill-down совпадает с плиткой (тест-инвариант).

**Architecture:** Третий пресет `composition` в `/reports` принимает `metric` и `period` через `ReportCriteria`. Backend-логика — в новом `app/services/composition_service.py`; общие helpers расчёта метрик вынесены из `dashboard.py` в `app/services/dashboard_service.py`, чтобы и Dashboard, и Reports считали из одной точки. Frontend: `KpiTile` получает опциональный prop `to` (router-link), `DashboardView` оборачивает 8 плиток, `ReportsView` парсит query на mount и показывает контрольную сумму в шапке.

**Tech Stack:** Python 3.12 + FastAPI + SQLModel + Pydantic; Vue 3 + TypeScript + PrimeVue + vue-router; pytest.

**Spec:** `docs/superpowers/specs/2026-05-20-dashboard-drilldown-design.md`

---

## Файлы

**Создаются:**
- `backend/app/services/dashboard_service.py` — общие helpers расчёта метрик (рефакторинг из `dashboard.py`)
- `backend/app/services/composition_service.py` — builder и каталог колонок пресета composition
- `backend/tests/test_dashboard_service.py` — регрессионные тесты на вынесенные helpers
- `backend/tests/test_composition_service.py` — unit-тесты по метрикам
- `backend/tests/test_composition_matches_dashboard.py` — инвариант «summary ↔ composition.control_value»

**Правятся:**
- `backend/app/api/v1/dashboard.py` — импорт helpers из `dashboard_service`
- `backend/app/services/report_service.py` — поля `metric`/`period` в `ReportCriteria`, регистрация `composition` в `REPORTS` и `_BUILDERS`
- `backend/app/api/v1/reports.py` — `control_value` в ответе `/preview`
- `backend/tests/test_api_reports.py` — кейсы для composition
- `frontend/src/components/KpiTile.vue` — prop `to`, состояние «кликабельно»
- `frontend/src/views/DashboardView.vue` — хелпер `compositionLink`, `:to` на 8 плитках
- `frontend/src/views/ReportsView.vue` — третий пресет, парсинг query, контрольная сумма в шапке
- `agent_docs/development-history.md` — запись об итерации

---

## Task 1: Вынести helpers расчёта метрик в `dashboard_service.py`

**Files:**
- Create: `backend/app/services/dashboard_service.py`
- Create: `backend/tests/test_dashboard_service.py`
- Modify: `backend/app/api/v1/dashboard.py`

Рефакторинг без изменения поведения. Цель — чтобы `composition_service` и `dashboard.py` считали из одних функций.

- [ ] **Step 1: Написать падающий регресс-тест на новый модуль**

Создать `backend/tests/test_dashboard_service.py`:

```python
"""Регресс: helpers, вынесенные из dashboard.py, ведут себя как раньше."""
from datetime import date
from decimal import Decimal

from sqlmodel import Session

from app.models import (
    AllocationBasis, ChargeSource, Contract, ContractType,
    DocType, Document, MonthlyCharge, Organization, OrgStatus,
    PaymentAllocation,
)
from app.services.dashboard_service import (
    collected_by_charge_month,
    first_pay_rows,
    last_pay_rows,
    plan_mrr_total,
)


def _org(session, inn, **kw):
    org = Organization(inn=inn, name_1c=kw.pop("name", "X"), **kw)
    session.add(org)
    session.commit()
    session.refresh(org)
    return org


def _charge(session, org, year, month, amount):
    c = MonthlyCharge(organization_id=org.id, year=year, month=month,
                      amount=Decimal(str(amount)),
                      source=ChargeSource.SYNTHETIC_TARIFF)
    session.add(c)
    session.commit()
    session.refresh(c)
    return c


def _pay(session, org, charge, amount, pay_date):
    contract = Contract(organization_id=org.id,
                        contract_type=ContractType.SUBSCRIPTION)
    session.add(contract)
    session.commit()
    session.refresh(contract)
    doc = Document(contract_id=contract.id, organization_id=org.id,
                   doc_type=DocType.PAYMENT, doc_date=pay_date,
                   amount=Decimal(str(amount)))
    session.add(doc)
    session.commit()
    session.refresh(doc)
    alloc = PaymentAllocation(payment_document_id=doc.id,
                              monthly_charge_id=charge.id,
                              allocated_amount=Decimal(str(amount)),
                              basis=AllocationBasis.EXPLICIT_PERIOD)
    session.add(alloc)
    session.commit()


def test_plan_mrr_total_sums_active_ap(db_session: Session):
    _org(db_session, "1", status=OrgStatus.ACTIVE, monthly_ap=Decimal("10000"))
    _org(db_session, "2", status=OrgStatus.ACTIVE, monthly_ap=Decimal("5000"))
    _org(db_session, "3", status=OrgStatus.CHURNED, monthly_ap=Decimal("999"))
    _org(db_session, "4", status=OrgStatus.ACTIVE, monthly_ap=Decimal("1000"),
         excluded_from_analytics=True)
    assert plan_mrr_total(db_session) == 15000.0


def test_collected_by_charge_month(db_session: Session):
    org = _org(db_session, "10", status=OrgStatus.ACTIVE,
               monthly_ap=Decimal("10000"))
    ch = _charge(db_session, org, 2026, 4, 10000)
    _pay(db_session, org, ch, 10000, date(2026, 4, 5))
    out = collected_by_charge_month(db_session)
    assert out[(2026, 4)] == 10000.0


def test_first_and_last_pay_rows(db_session: Session):
    org = _org(db_session, "20", status=OrgStatus.ACTIVE)
    ch = _charge(db_session, org, 2026, 1, 5000)
    _pay(db_session, org, ch, 5000, date(2026, 1, 10))
    _pay(db_session, org, ch, 3000, date(2026, 3, 20))
    first = dict(first_pay_rows(db_session))
    last = dict(last_pay_rows(db_session))
    assert first[org.id] == date(2026, 1, 10)
    assert last[org.id] == date(2026, 3, 20)
```

- [ ] **Step 2: Запустить тест — должен упасть на импорте**

Run: `cd backend && pytest tests/test_dashboard_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.dashboard_service'`.

- [ ] **Step 3: Создать `dashboard_service.py` с публичными helpers**

Создать `backend/app/services/dashboard_service.py`:

```python
"""Общие helpers расчёта KPI дашборда.

Вынесено из app/api/v1/dashboard.py, чтобы dashboard и composition_service
считали из одних функций — гарантия совпадения цифр на плитках и в drill-down."""
from datetime import date

from sqlmodel import Session, func, select

from app.models import (
    DocType, Document, MonthlyCharge, Organization, OrgStatus,
    PaymentAllocation,
)


def excl():
    """Предикат: организация не исключена из аналитики."""
    return Organization.excluded_from_analytics == False  # noqa: E712


def to_float(x) -> float:
    if x is None:
        return 0.0
    return float(x)


def plan_mrr_total(session: Session) -> float:
    """План MRR: Σ monthly_ap по активным неисключённым клиентам."""
    v = session.exec(
        select(func.coalesce(func.sum(Organization.monthly_ap), 0))
        .where(excl(), Organization.status == OrgStatus.ACTIVE)
    ).one()
    return to_float(v)


def accrued_by_month(session: Session) -> dict[tuple[int, int], float]:
    """Σ начислений по месяцам, неисключённые клиенты."""
    rows = session.exec(
        select(MonthlyCharge.year, MonthlyCharge.month,
               func.coalesce(func.sum(MonthlyCharge.amount), 0))
        .select_from(MonthlyCharge)
        .join(Organization, Organization.id == MonthlyCharge.organization_id)
        .where(excl())
        .group_by(MonthlyCharge.year, MonthlyCharge.month)
    ).all()
    return {(int(y), int(m)): to_float(s) for y, m, s in rows}


def collected_by_charge_month(session: Session) -> dict[tuple[int, int], float]:
    """Σ аллокаций по месяцу начисления — сколько собрано за период."""
    rows = session.exec(
        select(MonthlyCharge.year, MonthlyCharge.month,
               func.coalesce(func.sum(PaymentAllocation.allocated_amount), 0))
        .select_from(PaymentAllocation)
        .join(MonthlyCharge, MonthlyCharge.id == PaymentAllocation.monthly_charge_id)
        .join(Organization, Organization.id == MonthlyCharge.organization_id)
        .where(excl())
        .group_by(MonthlyCharge.year, MonthlyCharge.month)
    ).all()
    return {(int(y), int(m)): to_float(s) for y, m, s in rows}


def first_pay_rows(session: Session) -> list[tuple]:
    """[(org_id, min_doc_date)] для неисключённых клиентов с платежами."""
    return list(session.exec(
        select(Document.organization_id, func.min(Document.doc_date))
        .select_from(Document)
        .join(Organization, Organization.id == Document.organization_id)
        .where(excl(), Document.doc_type == DocType.PAYMENT,
               Document.doc_date.is_not(None))  # type: ignore[union-attr]
        .group_by(Document.organization_id)
    ).all())


def last_pay_rows(session: Session) -> list[tuple]:
    """[(org_id, max_doc_date)] для неисключённых клиентов с платежами."""
    return list(session.exec(
        select(Document.organization_id, func.max(Document.doc_date))
        .select_from(Document)
        .join(Organization, Organization.id == Document.organization_id)
        .where(excl(), Document.doc_type == DocType.PAYMENT,
               Document.doc_date.is_not(None))  # type: ignore[union-attr]
        .group_by(Document.organization_id)
    ).all())


def months_back(n: int, today: date | None = None) -> list[tuple[int, int]]:
    """Список последних n месяцев в порядке от старого к новому."""
    if today is None:
        today = date.today()
    out, y, m = [], today.year, today.month
    for _ in range(n):
        out.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(out))
```

- [ ] **Step 4: Запустить тест — должен пройти**

Run: `cd backend && pytest tests/test_dashboard_service.py -v`
Expected: PASS (3 теста).

- [ ] **Step 5: Заменить локальные helpers в `dashboard.py` на импорты**

В `backend/app/api/v1/dashboard.py` удалить локальные `_excl`, `_f`, `_months_back`, `_plan_mrr_total`, `_accrued_by_month`, `_collected_by_charge_month` (строки 36–93).

Заменить блок импортов:

```python
from app.services.dashboard_service import (
    accrued_by_month,
    collected_by_charge_month,
    excl as _excl,
    first_pay_rows as _first_pay_rows_q,
    last_pay_rows as _last_pay_rows_q,
    months_back as _months_back,
    plan_mrr_total as _plan_mrr_total,
    to_float as _f,
)
```

В `dashboard_summary` заменить inline-подзапросы `first_pay_rows`/`last_pay_rows`:

```python
    first_pay_rows = _first_pay_rows_q(session)
    last_pay_rows = _last_pay_rows_q(session)
```

В `mrr_plan_vs_fact`, `collection_trend` использовать `collected_by_charge_month` и `accrued_by_month` напрямую (имя без подчёркивания).

- [ ] **Step 6: Прогнать весь backend-тест-suite**

Run: `cd backend && pytest -q`
Expected: 173+ passed (текущая база) + 3 новых = ~176, 0 failed.

- [ ] **Step 7: Коммит**

```bash
git add backend/app/services/dashboard_service.py \
        backend/tests/test_dashboard_service.py \
        backend/app/api/v1/dashboard.py
git commit -m "refactor(dashboard): вынести helpers расчёта KPI в services/dashboard_service.py"
```

---

## Task 2: Зарегистрировать пресет `composition` (scaffolding)

**Files:**
- Modify: `backend/app/services/report_service.py`
- Create: `backend/app/services/composition_service.py`
- Modify: `backend/app/api/v1/reports.py`
- Modify: `backend/tests/test_api_reports.py`

Подключаем третий пресет к диспетчеру с пустой логикой — чтобы инфраструктура (criteria → preview → export) работала из коробки.

- [ ] **Step 1: Падающий тест**

Добавить в конец `backend/tests/test_api_reports.py`:

```python
# --- пресет «состав показателя» ---------------------------------------------


def test_composition_preset_registered(client):
    """Composition зарегистрирован; preview возвращает 200 даже на пустых данных."""
    resp = client.post("/api/v1/reports/composition/preview",
                        json={"metric": "mrr_plan"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows"] == []
    assert body["total"] == 0


def test_composition_unknown_metric_returns_400(client):
    resp = client.post("/api/v1/reports/composition/preview",
                        json={"metric": "bogus"})
    assert resp.status_code == 400
```

- [ ] **Step 2: Запустить — упадёт**

Run: `cd backend && pytest tests/test_api_reports.py::test_composition_preset_registered tests/test_api_reports.py::test_composition_unknown_metric_returns_400 -v`
Expected: FAIL (404 «unknown report type»).

- [ ] **Step 3: Расширить `ReportCriteria`**

В `backend/app/services/report_service.py`, в `ReportCriteria` после поля `sort_dir`:

```python
    # только для пресета composition; остальные пресеты игнорируют через extra="ignore"
    metric: str | None = None
    period: str | None = None
```

- [ ] **Step 4: Создать `composition_service.py` со scaffolding**

Создать `backend/app/services/composition_service.py`:

```python
"""Состав KPI-показателя дашборда (drill-down).

Backend для пресета composition в /reports. Для каждой метрики
возвращает список клиентов, формирующих её значение, и поддерживает
control_value — сумму/счёт, обязанную совпасть с плиткой Dashboard."""
from datetime import date, timedelta
from typing import TYPE_CHECKING

from sqlmodel import Session, func, select

from app.models import (
    Organization, OrgStatus, MonthlyCharge, PaymentAllocation, User,
)
from app.services.dashboard_service import (
    excl, first_pay_rows, last_pay_rows, to_float,
)

if TYPE_CHECKING:
    from app.services.report_service import ReportCriteria


_RU_MONTHS = [
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
]

# --- каталог колонок ---------------------------------------------------------

COMPOSITION_COLUMNS: list[tuple[str, str]] = [
    ("name", "Клиент"),
    ("inn", "ИНН"),
    ("manager", "Менеджер"),
    ("monthly_ap", "АП/мес"),
    ("status", "Статус"),
    ("city", "Город"),
    ("contribution", "Вклад в показатель, ₽"),
    ("first_payment_date", "Дата первого платежа"),
    ("last_payment_date", "Дата последнего платежа"),
    ("days_since_last", "Дней с последнего платежа"),
]

_BASE_COLS = ["name", "inn", "manager", "monthly_ap", "status", "city"]

_COLS_BY_METRIC: dict[str, list[str]] = {
    "mrr_fact":                 _BASE_COLS + ["contribution"],
    "collected_current":        _BASE_COLS + ["contribution"],
    "mrr_plan":                 _BASE_COLS + ["contribution"],
    "active_clients":           _BASE_COLS + ["last_payment_date"],
    "new_paid_curr_year":       _BASE_COLS + ["first_payment_date"],
    "new_paid_prev_month":      _BASE_COLS + ["first_payment_date"],
    "new_paid_curr_month":      _BASE_COLS + ["first_payment_date"],
    "stopped_since_year_start": _BASE_COLS + ["last_payment_date", "days_since_last"],
}

MONEY_METRICS = {"mrr_fact", "collected_current", "mrr_plan"}

_STATUS_LABELS = {
    OrgStatus.ACTIVE: "Активен",
    OrgStatus.CHURNED: "Отток",
    OrgStatus.SUSPENDED: "Приостановлен",
    OrgStatus.PROSPECT: "Потенциальный",
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
        query = query.where(
            func.lower(Organization.city_region).like(f"%{c.city.lower()}%")
        )
    statuses = [OrgStatus(s) for s in c.statuses
                if s in OrgStatus._value2member_map_]
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
        "city": o.city_region or "—",
    }


# --- диспетчер (пустой; builder'ы подключатся в Task 3-8) ----------------

_DISPATCH: dict = {}


def build_composition_report(session: Session, c) -> list[dict]:
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
    period = (_parse_month(c.period)
              if c.metric in ("mrr_fact", "collected_current") else None)
    keys = _COLS_BY_METRIC[c.metric]
    if c.columns:
        chosen = set(c.columns)
        filtered = [k for k in keys if k in chosen]
        keys = filtered or keys
    catalog = dict(COMPOSITION_COLUMNS)
    out: list[tuple[str, str]] = []
    for k in keys:
        header = (_contribution_header(c.metric, period)
                  if k == "contribution" else catalog[k])
        out.append((k, header))
    return out
```

- [ ] **Step 5: Зарегистрировать в диспетчере и каталоге**

В `backend/app/services/report_service.py`:

В блок `REPORTS` добавить:

```python
    "composition": {"title": "Состав показателя", "columns": []},
```

Заменить `_BUILDERS`:

```python
from app.services.composition_service import build_composition_report

_BUILDERS = {
    "debtors": build_debtors_report,
    "discipline": build_discipline_report,
    "composition": build_composition_report,
}
```

Расширить `columns_for(report_type, c)`:

```python
def columns_for(report_type: str, c: ReportCriteria) -> list[tuple[str, str]]:
    if report_type == "composition":
        from app.services.composition_service import columns_for_composition
        return columns_for_composition(c)
    catalog = REPORTS[report_type]["columns"]
    if not c.columns:
        return catalog
    chosen = set(c.columns)
    selected = [pair for pair in catalog if pair[0] in chosen]
    return selected or catalog
```

В `backend/app/api/v1/reports.py`, обернуть `build_report` в try/except в `report_preview` и `report_export`:

```python
@router.post("/{report_type}/preview")
def report_preview(
    report_type: str,
    criteria: ReportCriteria,
    session: Session = Depends(get_session),
):
    _check_type(report_type)
    try:
        rows = build_report(report_type, session, criteria)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    columns = columns_for(report_type, criteria)
    return {
        "columns": [{"key": key, "header": header} for key, header in columns],
        "rows": rows,
        "total": len(rows),
    }


@router.post("/{report_type}/export")
def report_export(
    report_type: str,
    criteria: ReportCriteria,
    session: Session = Depends(get_session),
):
    _check_type(report_type)
    try:
        rows = build_report(report_type, session, criteria)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    columns = columns_for(report_type, criteria)
    content = report_to_xlsx(report_type, columns, rows)
    filename = f"{report_type}-{date.today().isoformat()}.xlsx"
    return Response(
        content=content,
        media_type=_XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

- [ ] **Step 6: Прогнать тесты**

Run: `cd backend && pytest tests/test_api_reports.py -k composition -v`
Expected: PASS оба composition-теста.

Run: `cd backend && pytest -q`
Expected: ~178 passed.

- [ ] **Step 7: Коммит**

```bash
git add backend/app/services/composition_service.py \
        backend/app/services/report_service.py \
        backend/app/api/v1/reports.py \
        backend/tests/test_api_reports.py
git commit -m "feat(reports): зарегистрировать пресет composition (scaffolding)"
```

---

## Task 3: Метрика `mrr_fact` — сбор за конкретный месяц

**Files:**
- Modify: `backend/app/services/composition_service.py`
- Create: `backend/tests/test_composition_service.py`

- [ ] **Step 1: Падающий тест**

Создать `backend/tests/test_composition_service.py`:

```python
"""Unit-тесты builder'а composition по каждой метрике."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlmodel import Session

from app.models import (
    AllocationBasis, ChargeSource, Contract, ContractType,
    DocType, Document, MonthlyCharge, Organization, OrgStatus,
    PaymentAllocation,
)
from app.services.composition_service import (
    build_composition_report,
    control_value_for,
)
from app.services.report_service import ReportCriteria


def _org(session, inn, name="Org", **kw):
    org = Organization(inn=inn, name_1c=name, **kw)
    session.add(org)
    session.commit()
    session.refresh(org)
    return org


def _charge(session, org, year, month, amount):
    c = MonthlyCharge(organization_id=org.id, year=year, month=month,
                      amount=Decimal(str(amount)),
                      source=ChargeSource.SYNTHETIC_TARIFF)
    session.add(c)
    session.commit()
    session.refresh(c)
    return c


def _pay(session, org, charge, amount, pay_date):
    contract = Contract(organization_id=org.id,
                        contract_type=ContractType.SUBSCRIPTION)
    session.add(contract)
    session.commit()
    session.refresh(contract)
    doc = Document(contract_id=contract.id, organization_id=org.id,
                   doc_type=DocType.PAYMENT, doc_date=pay_date,
                   amount=Decimal(str(amount)))
    session.add(doc)
    session.commit()
    session.refresh(doc)
    alloc = PaymentAllocation(payment_document_id=doc.id,
                              monthly_charge_id=charge.id,
                              allocated_amount=Decimal(str(amount)),
                              basis=AllocationBasis.EXPLICIT_PERIOD)
    session.add(alloc)
    session.commit()


# --- mrr_fact -------------------------------------------------------------


def test_mrr_fact_lists_contributors_with_amounts(db_session: Session):
    a = _org(db_session, "10", name="A", status=OrgStatus.ACTIVE,
             monthly_ap=Decimal("10000"))
    b = _org(db_session, "11", name="B", status=OrgStatus.ACTIVE,
             monthly_ap=Decimal("5000"))
    ch_a = _charge(db_session, a, 2026, 4, 10000)
    ch_b = _charge(db_session, b, 2026, 4, 5000)
    _pay(db_session, a, ch_a, 10000, date(2026, 4, 5))
    _pay(db_session, b, ch_b, 5000, date(2026, 4, 7))
    # шум: платёж за другой месяц не должен попасть
    ch_a_other = _charge(db_session, a, 2026, 3, 10000)
    _pay(db_session, a, ch_a_other, 10000, date(2026, 3, 1))

    criteria = ReportCriteria(metric="mrr_fact", period="2026-04")
    rows = build_composition_report(db_session, criteria)
    names = sorted(r["name"] for r in rows)
    assert names == ["A", "B"]
    assert all(r["contribution"] in (10000.0, 5000.0) for r in rows)
    assert control_value_for("mrr_fact", rows) == 15000.0


def test_mrr_fact_excludes_excluded_from_analytics(db_session: Session):
    a = _org(db_session, "20", status=OrgStatus.ACTIVE,
             monthly_ap=Decimal("10000"))
    b = _org(db_session, "21", status=OrgStatus.ACTIVE,
             monthly_ap=Decimal("5000"), excluded_from_analytics=True)
    ch_a = _charge(db_session, a, 2026, 4, 10000)
    ch_b = _charge(db_session, b, 2026, 4, 5000)
    _pay(db_session, a, ch_a, 10000, date(2026, 4, 5))
    _pay(db_session, b, ch_b, 5000, date(2026, 4, 7))

    criteria = ReportCriteria(metric="mrr_fact", period="2026-04")
    rows = build_composition_report(db_session, criteria)
    assert {r["inn"] for r in rows} == {"20"}


def test_mrr_fact_empty_for_invalid_period(db_session: Session):
    criteria = ReportCriteria(metric="mrr_fact", period="not-a-date")
    assert build_composition_report(db_session, criteria) == []
```

- [ ] **Step 2: Запустить — упадёт**

Run: `cd backend && pytest tests/test_composition_service.py -v`
Expected: FAIL (3 теста: rows пустые).

- [ ] **Step 3: Реализовать `_build_mrr_fact`**

В `backend/app/services/composition_service.py` добавить функцию:

```python
def _build_mrr_fact(session: Session, c) -> list[dict]:
    period = _parse_month(c.period)
    if period is None:
        return []
    y, m = period
    contrib_rows = session.exec(
        select(MonthlyCharge.organization_id,
               func.coalesce(func.sum(PaymentAllocation.allocated_amount), 0))
        .select_from(PaymentAllocation)
        .join(MonthlyCharge, MonthlyCharge.id == PaymentAllocation.monthly_charge_id)
        .join(Organization, Organization.id == MonthlyCharge.organization_id)
        .where(excl(), MonthlyCharge.year == y, MonthlyCharge.month == m)
        .group_by(MonthlyCharge.organization_id)
    ).all()
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
```

Зарегистрировать в `_DISPATCH`:

```python
_DISPATCH = {
    "mrr_fact": _build_mrr_fact,
}
```

- [ ] **Step 4: Тесты проходят**

Run: `cd backend && pytest tests/test_composition_service.py -v`
Expected: PASS все 3.

- [ ] **Step 5: Коммит**

```bash
git add backend/app/services/composition_service.py \
        backend/tests/test_composition_service.py
git commit -m "feat(composition): метрика mrr_fact с проверкой контрольной суммы"
```

---

## Task 4: Метрика `mrr_plan`

**Files:**
- Modify: `backend/app/services/composition_service.py`
- Modify: `backend/tests/test_composition_service.py`

- [ ] **Step 1: Тест**

Добавить в `backend/tests/test_composition_service.py`:

```python
def test_mrr_plan_lists_active_subscribers(db_session: Session):
    _org(db_session, "30", name="A", status=OrgStatus.ACTIVE,
         monthly_ap=Decimal("10000"))
    _org(db_session, "31", name="B", status=OrgStatus.ACTIVE,
         monthly_ap=Decimal("5000"))
    _org(db_session, "32", name="C-churn", status=OrgStatus.CHURNED,
         monthly_ap=Decimal("999"))  # неактивен — не считаем
    _org(db_session, "33", name="D-noap", status=OrgStatus.ACTIVE,
         monthly_ap=None)  # без АП — не считаем

    criteria = ReportCriteria(metric="mrr_plan")
    rows = build_composition_report(db_session, criteria)
    assert {r["name"] for r in rows} == {"A", "B"}
    assert control_value_for("mrr_plan", rows) == 15000.0
```

- [ ] **Step 2: Запустить — упадёт**

Run: `cd backend && pytest tests/test_composition_service.py::test_mrr_plan_lists_active_subscribers -v`
Expected: FAIL.

- [ ] **Step 3: Реализовать `_build_mrr_plan`**

```python
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
```

Зарегистрировать:

```python
_DISPATCH = {
    "mrr_fact": _build_mrr_fact,
    "mrr_plan": _build_mrr_plan,
}
```

- [ ] **Step 4: Тест проходит**

Run: `cd backend && pytest tests/test_composition_service.py::test_mrr_plan_lists_active_subscribers -v`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add backend/app/services/composition_service.py \
        backend/tests/test_composition_service.py
git commit -m "feat(composition): метрика mrr_plan"
```

---

## Task 5: Метрика `collected_current` (reuse mrr_fact)

**Files:**
- Modify: `backend/app/services/composition_service.py`
- Modify: `backend/tests/test_composition_service.py`

- [ ] **Step 1: Тест**

```python
def test_collected_current_reuses_mrr_fact_for_given_period(db_session: Session):
    today = date.today()
    org = _org(db_session, "40", name="A", status=OrgStatus.ACTIVE,
               monthly_ap=Decimal("10000"))
    ch = _charge(db_session, org, today.year, today.month, 10000)
    _pay(db_session, org, ch, 7000, today.replace(day=1))

    criteria = ReportCriteria(metric="collected_current",
                              period=f"{today.year}-{today.month:02d}")
    rows = build_composition_report(db_session, criteria)
    assert len(rows) == 1
    assert rows[0]["contribution"] == 7000.0
    assert control_value_for("collected_current", rows) == 7000.0
```

- [ ] **Step 2: Запустить — упадёт**

Run: `cd backend && pytest tests/test_composition_service.py::test_collected_current_reuses_mrr_fact_for_given_period -v`
Expected: FAIL (метрика возвращает `[]`).

- [ ] **Step 3: Реализовать**

В `_DISPATCH` указать, что `collected_current` использует тот же builder, что и `mrr_fact` — логика идентична, отличается лишь period в criteria:

```python
_DISPATCH = {
    "mrr_fact": _build_mrr_fact,
    "collected_current": _build_mrr_fact,
    "mrr_plan": _build_mrr_plan,
}
```

- [ ] **Step 4: Тест проходит**

Run: `cd backend && pytest tests/test_composition_service.py::test_collected_current_reuses_mrr_fact_for_given_period -v`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add backend/app/services/composition_service.py \
        backend/tests/test_composition_service.py
git commit -m "feat(composition): метрика collected_current"
```

---

## Task 6: Метрика `active_clients`

**Files:**
- Modify: `backend/app/services/composition_service.py`
- Modify: `backend/tests/test_composition_service.py`

- [ ] **Step 1: Тест**

```python
def test_active_clients_lists_actives_with_last_payment(db_session: Session):
    a = _org(db_session, "50", name="A", status=OrgStatus.ACTIVE)
    b = _org(db_session, "51", name="B", status=OrgStatus.ACTIVE)
    _org(db_session, "52", name="C-churn", status=OrgStatus.CHURNED)
    _org(db_session, "53", name="D-excl", status=OrgStatus.ACTIVE,
         excluded_from_analytics=True)

    ch = _charge(db_session, a, 2026, 4, 1000)
    _pay(db_session, a, ch, 1000, date(2026, 4, 10))

    criteria = ReportCriteria(metric="active_clients")
    rows = build_composition_report(db_session, criteria)
    assert {r["name"] for r in rows} == {"A", "B"}
    a_row = next(r for r in rows if r["name"] == "A")
    b_row = next(r for r in rows if r["name"] == "B")
    assert a_row["last_payment_date"] == "2026-04-10"
    assert b_row["last_payment_date"] is None
    assert control_value_for("active_clients", rows) == 2
```

- [ ] **Step 2: Запустить — упадёт**

Run: `cd backend && pytest tests/test_composition_service.py::test_active_clients_lists_actives_with_last_payment -v`
Expected: FAIL.

- [ ] **Step 3: Реализовать**

```python
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
```

Зарегистрировать:

```python
_DISPATCH = {
    "mrr_fact": _build_mrr_fact,
    "collected_current": _build_mrr_fact,
    "mrr_plan": _build_mrr_plan,
    "active_clients": _build_active_clients,
}
```

- [ ] **Step 4: Тест проходит**

Run: `cd backend && pytest tests/test_composition_service.py::test_active_clients_lists_actives_with_last_payment -v`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add backend/app/services/composition_service.py \
        backend/tests/test_composition_service.py
git commit -m "feat(composition): метрика active_clients"
```

---

## Task 7: Метрики `new_paid_curr_year`, `new_paid_prev_month`, `new_paid_curr_month`

**Files:**
- Modify: `backend/app/services/composition_service.py`
- Modify: `backend/tests/test_composition_service.py`

Все три считают «впервые заплатил в указанный год/месяц». Объединены, так как код общий.

- [ ] **Step 1: Тесты**

```python
def test_new_paid_curr_year(db_session: Session):
    today = date.today()
    this_year = today.year
    a = _org(db_session, "60", name="A-this-year", status=OrgStatus.ACTIVE)
    b = _org(db_session, "61", name="B-prev-year", status=OrgStatus.ACTIVE)
    ch_a = _charge(db_session, a, this_year, 3, 100)
    ch_b = _charge(db_session, b, this_year - 1, 6, 100)
    _pay(db_session, a, ch_a, 100, date(this_year, 3, 15))
    _pay(db_session, b, ch_b, 100, date(this_year - 1, 6, 20))

    criteria = ReportCriteria(metric="new_paid_curr_year")
    rows = build_composition_report(db_session, criteria)
    assert {r["name"] for r in rows} == {"A-this-year"}
    assert rows[0]["first_payment_date"] == f"{this_year}-03-15"
    assert control_value_for("new_paid_curr_year", rows) == 1


def test_new_paid_prev_month(db_session: Session):
    today = date.today()
    prev_y, prev_m = ((today.year, today.month - 1)
                      if today.month > 1 else (today.year - 1, 12))
    a = _org(db_session, "70", name="A-prev-m", status=OrgStatus.ACTIVE)
    b = _org(db_session, "71", name="B-curr-m", status=OrgStatus.ACTIVE)
    ch_a = _charge(db_session, a, prev_y, prev_m, 100)
    ch_b = _charge(db_session, b, today.year, today.month, 100)
    _pay(db_session, a, ch_a, 100, date(prev_y, prev_m, 5))
    _pay(db_session, b, ch_b, 100, today.replace(day=1))

    criteria = ReportCriteria(metric="new_paid_prev_month")
    rows = build_composition_report(db_session, criteria)
    assert {r["name"] for r in rows} == {"A-prev-m"}


def test_new_paid_curr_month(db_session: Session):
    today = date.today()
    a = _org(db_session, "80", name="A-curr-m", status=OrgStatus.ACTIVE)
    ch_a = _charge(db_session, a, today.year, today.month, 100)
    _pay(db_session, a, ch_a, 100, today.replace(day=1))

    criteria = ReportCriteria(metric="new_paid_curr_month")
    rows = build_composition_report(db_session, criteria)
    assert {r["name"] for r in rows} == {"A-curr-m"}
    assert control_value_for("new_paid_curr_month", rows) == 1
```

- [ ] **Step 2: Упадут**

Run: `cd backend && pytest tests/test_composition_service.py -k new_paid -v`
Expected: FAIL все три.

- [ ] **Step 3: Реализовать общий хелпер и три builder'а**

```python
def _materialize_first_pay(session: Session, c, target_ids: set,
                          first_pay: dict) -> list[dict]:
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
    target_ids = {oid for oid, d in first_pay.items()
                  if d and d.year == year}
    return _materialize_first_pay(session, c, target_ids, first_pay)


def _build_new_paid_in_month(session: Session, c, year: int, month: int) -> list[dict]:
    first_pay = dict(first_pay_rows(session))
    target_ids = {oid for oid, d in first_pay.items()
                  if d and d.year == year and d.month == month}
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
```

Зарегистрировать:

```python
_DISPATCH = {
    "mrr_fact": _build_mrr_fact,
    "collected_current": _build_mrr_fact,
    "mrr_plan": _build_mrr_plan,
    "active_clients": _build_active_clients,
    "new_paid_curr_year": _build_new_paid_curr_year,
    "new_paid_prev_month": _build_new_paid_prev_month,
    "new_paid_curr_month": _build_new_paid_curr_month,
}
```

- [ ] **Step 4: Тесты проходят**

Run: `cd backend && pytest tests/test_composition_service.py -k new_paid -v`
Expected: PASS все три.

- [ ] **Step 5: Коммит**

```bash
git add backend/app/services/composition_service.py \
        backend/tests/test_composition_service.py
git commit -m "feat(composition): метрики new_paid_curr_year, prev_month, curr_month"
```

---

## Task 8: Метрика `stopped_since_year_start`

**Files:**
- Modify: `backend/app/services/composition_service.py`
- Modify: `backend/tests/test_composition_service.py`

- [ ] **Step 1: Тест**

```python
def test_stopped_since_year_start(db_session: Session):
    today = date.today()
    year_start = date(today.year, 1, 1)
    long_ago = today - timedelta(days=70)  # > 60 дней, в этом году (если today после 11 марта)

    a = _org(db_session, "90", name="A-stopped", status=OrgStatus.ACTIVE)
    b = _org(db_session, "91", name="B-active", status=OrgStatus.ACTIVE)
    ch_a = _charge(db_session, a, long_ago.year, long_ago.month, 100)
    ch_b = _charge(db_session, b, today.year, today.month, 100)
    _pay(db_session, a, ch_a, 100, long_ago)
    _pay(db_session, b, ch_b, 100, today.replace(day=1))

    criteria = ReportCriteria(metric="stopped_since_year_start")
    rows = build_composition_report(db_session, criteria)
    if long_ago >= year_start:
        assert {r["name"] for r in rows} == {"A-stopped"}
        row = rows[0]
        assert row["last_payment_date"] == long_ago.isoformat()
        assert row["days_since_last"] >= 60
        assert control_value_for("stopped_since_year_start", rows) == 1
    else:
        # 70 дней назад = прошлый год — клиент не попадает в диапазон
        assert rows == []
```

- [ ] **Step 2: Упадёт**

Run: `cd backend && pytest tests/test_composition_service.py::test_stopped_since_year_start -v`
Expected: FAIL.

- [ ] **Step 3: Реализовать**

```python
def _build_stopped(session: Session, c) -> list[dict]:
    today = date.today()
    year_start = date(today.year, 1, 1)
    cutoff_60 = today - timedelta(days=60)
    last_pay = dict(last_pay_rows(session))
    target_ids = {oid for oid, d in last_pay.items()
                  if d and year_start <= d <= cutoff_60}
    if not target_ids:
        return []
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
```

Зарегистрировать:

```python
_DISPATCH["stopped_since_year_start"] = _build_stopped
```

- [ ] **Step 4: Тест проходит**

Run: `cd backend && pytest tests/test_composition_service.py::test_stopped_since_year_start -v`
Expected: PASS.

- [ ] **Step 5: Прогнать весь suite**

Run: `cd backend && pytest -q`
Expected: ~186 passed, 0 failed.

- [ ] **Step 6: Коммит**

```bash
git add backend/app/services/composition_service.py \
        backend/tests/test_composition_service.py
git commit -m "feat(composition): метрика stopped_since_year_start"
```

---

## Task 9: Контрольная сумма в ответе `/preview`

**Files:**
- Modify: `backend/app/api/v1/reports.py`
- Modify: `backend/tests/test_api_reports.py`

- [ ] **Step 1: Тест**

В `backend/tests/test_api_reports.py`:

```python
def test_composition_preview_returns_control_value(client, db_session: Session):
    today = date.today()
    org = _org(db_session, "7700000100", name="Платил",
               status=OrgStatus.ACTIVE, monthly_ap=Decimal("10000"))
    charge = _charge(db_session, org, today.year, today.month, 10000)
    _pay(db_session, org, charge, 7500, today.replace(day=1))

    resp = client.post(
        "/api/v1/reports/composition/preview",
        json={"metric": "collected_current",
              "period": f"{today.year}-{today.month:02d}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["control_value"] == 7500.0


def test_composition_active_clients_control_value_is_count(client, db_session: Session):
    _org(db_session, "7700000200", name="A", status=OrgStatus.ACTIVE)
    _org(db_session, "7700000201", name="B", status=OrgStatus.ACTIVE)
    _org(db_session, "7700000202", name="C", status=OrgStatus.CHURNED)

    resp = client.post(
        "/api/v1/reports/composition/preview",
        json={"metric": "active_clients"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert body["control_value"] == 2
```

- [ ] **Step 2: Упадут (нет ключа `control_value`)**

Run: `cd backend && pytest tests/test_api_reports.py -k composition -v`
Expected: FAIL на новых.

- [ ] **Step 3: Добавить `control_value` в `report_preview`**

В `backend/app/api/v1/reports.py`:

```python
from app.services.composition_service import control_value_for


@router.post("/{report_type}/preview")
def report_preview(
    report_type: str,
    criteria: ReportCriteria,
    session: Session = Depends(get_session),
):
    _check_type(report_type)
    try:
        rows = build_report(report_type, session, criteria)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    columns = columns_for(report_type, criteria)
    body = {
        "columns": [{"key": key, "header": header} for key, header in columns],
        "rows": rows,
        "total": len(rows),
    }
    if report_type == "composition" and criteria.metric:
        body["control_value"] = control_value_for(criteria.metric, rows)
    return body
```

- [ ] **Step 4: Тесты проходят**

Run: `cd backend && pytest tests/test_api_reports.py -k composition -v`
Expected: PASS все composition.

- [ ] **Step 5: Коммит**

```bash
git add backend/app/api/v1/reports.py \
        backend/tests/test_api_reports.py
git commit -m "feat(composition): control_value в ответе /preview"
```

---

## Task 10: Инвариант «summary ↔ composition.control_value»

**Files:**
- Create: `backend/tests/test_composition_matches_dashboard.py`

Ключевой контракт: цифры на дашборде не разъезжаются с drill-down. Один тест на метрику.

- [ ] **Step 1: Создать файл с инвариантами**

```python
"""Инвариант: control_value в composition совпадает с плиткой Dashboard.

Регрессионный контракт — если этот файл зелёный, дашборд и drill-down
показывают одни и те же цифры."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api.v1.auth import get_current_user
from app.core.database import get_session
from app.main import app
from app.models import (
    AllocationBasis, ChargeSource, Contract, ContractType,
    DocType, Document, MonthlyCharge, Organization, OrgStatus,
    PaymentAllocation, User, UserRole,
)


@pytest.fixture
def client(db_session: Session):
    def _sess():
        yield db_session

    def _user():
        return User(name="T", email="t@t.ru", hashed_password="x",
                    role=UserRole.ADMIN, is_active=True)

    app.dependency_overrides[get_session] = _sess
    app.dependency_overrides[get_current_user] = _user
    yield TestClient(app)
    app.dependency_overrides.clear()


def _org(s, inn, name="O", **kw):
    org = Organization(inn=inn, name_1c=name, **kw)
    s.add(org); s.commit(); s.refresh(org)
    return org


def _charge(s, org, y, m, amount):
    c = MonthlyCharge(organization_id=org.id, year=y, month=m,
                     amount=Decimal(str(amount)),
                     source=ChargeSource.SYNTHETIC_TARIFF)
    s.add(c); s.commit(); s.refresh(c)
    return c


def _pay(s, org, charge, amount, pay_date):
    contract = Contract(organization_id=org.id,
                       contract_type=ContractType.SUBSCRIPTION)
    s.add(contract); s.commit(); s.refresh(contract)
    doc = Document(contract_id=contract.id, organization_id=org.id,
                  doc_type=DocType.PAYMENT, doc_date=pay_date,
                  amount=Decimal(str(amount)))
    s.add(doc); s.commit(); s.refresh(doc)
    alloc = PaymentAllocation(payment_document_id=doc.id,
                             monthly_charge_id=charge.id,
                             allocated_amount=Decimal(str(amount)),
                             basis=AllocationBasis.EXPLICIT_PERIOD)
    s.add(alloc); s.commit()


@pytest.fixture
def populated(db_session: Session):
    """Реалистичная сеть: 5 клиентов, начисления и аллокации за 4 месяца."""
    today = date.today()
    months = []
    for i in range(4):
        m = today.month - i
        y = today.year
        if m <= 0:
            m += 12
            y -= 1
        months.append((y, m))

    orgs = []
    for i, plan in enumerate([10000, 8000, 6000, 4000, 2000], start=1):
        o = _org(db_session, f"INV{i:03d}", name=f"O{i}",
                 status=OrgStatus.ACTIVE, monthly_ap=Decimal(str(plan)))
        orgs.append(o)

    for org in orgs:
        plan = float(org.monthly_ap)
        for (y, m) in months:
            ch = _charge(db_session, org, y, m, plan)
            _pay(db_session, org, ch, plan * 0.8, date(y, m, 5))

    # один отток — последний платёж 70 дней назад
    o_stop = _org(db_session, "INV900", name="Stopped",
                  status=OrgStatus.ACTIVE)
    long_ago = today - timedelta(days=70)
    if long_ago.year == today.year:
        ch_stop = _charge(db_session, o_stop, long_ago.year, long_ago.month, 100)
        _pay(db_session, o_stop, ch_stop, 100, long_ago)

    return {"orgs": orgs, "months": months, "today": today}


def _summary(client) -> dict:
    return client.get("/api/v1/dashboard/summary").json()


def _control(client, metric: str, period: str | None = None):
    payload = {"metric": metric}
    if period is not None:
        payload["period"] = period
    return client.post("/api/v1/reports/composition/preview",
                        json=payload).json()["control_value"]


def test_inv_mrr_fact(client, populated):
    s = _summary(client)
    control = _control(client, "mrr_fact", s["fact_month"])
    assert abs(s["mrr_fact"] - control) < 0.01


def test_inv_mrr_plan(client, populated):
    s = _summary(client)
    control = _control(client, "mrr_plan")
    assert abs(s["mrr_plan"] - control) < 0.01


def test_inv_collected_current(client, populated):
    s = _summary(client)
    control = _control(client, "collected_current", s["current_month_label"])
    assert abs(s["current_month_collected"] - control) < 0.01


def test_inv_active_clients(client, populated):
    s = _summary(client)
    control = _control(client, "active_clients")
    assert s["active_clients"] == control


def test_inv_new_paid_curr_year(client, populated):
    s = _summary(client)
    control = _control(client, "new_paid_curr_year")
    assert s["new_paid_curr_year"] == control


def test_inv_new_paid_prev_month(client, populated):
    s = _summary(client)
    control = _control(client, "new_paid_prev_month")
    assert s["new_paid_prev_month"] == control


def test_inv_new_paid_curr_month(client, populated):
    s = _summary(client)
    control = _control(client, "new_paid_curr_month")
    assert s["new_paid_curr_month"] == control


def test_inv_stopped_since_year_start(client, populated):
    s = _summary(client)
    control = _control(client, "stopped_since_year_start")
    assert s["stopped_since_year_start"] == control
```

- [ ] **Step 2: Запустить**

Run: `cd backend && pytest tests/test_composition_matches_dashboard.py -v`
Expected: PASS все 8. Если что-то падает — исправлять расхождение в логике, а не подгонять тест.

- [ ] **Step 3: Прогнать весь suite**

Run: `cd backend && pytest -q`
Expected: ~196 passed.

- [ ] **Step 4: Коммит**

```bash
git add backend/tests/test_composition_matches_dashboard.py
git commit -m "test(composition): инвариант summary ↔ composition.control_value (8 метрик)"
```

---

## Task 11: Frontend — KpiTile clickable

**Files:**
- Modify: `frontend/src/components/KpiTile.vue`

- [ ] **Step 1: Заменить компонент целиком**

```vue
<script setup lang="ts">
import { computed } from 'vue'
import type { RouteLocationRaw } from 'vue-router'

const props = defineProps<{
  label: string
  value: string
  sub?: string
  accent?: 'primary' | 'danger' | 'warn' | 'success' | 'neutral'
  pct?: number | null
  hint?: string
  to?: RouteLocationRaw
}>()

const pctClass = computed(() => {
  const p = props.pct
  if (p == null) return null
  if (p < 30) return 'pct-red'
  if (p < 50) return 'pct-orange'
  if (p < 80) return 'pct-yellow'
  return 'pct-green'
})

const tileClass = computed(() => [
  'kpi-tile',
  pctClass.value || props.accent || 'neutral',
  props.to ? 'kpi-tile--clickable' : '',
])

const tooltipValue = computed(() => {
  if (!props.hint) return undefined
  const suffix = props.to ? ' · кликните для состава' : ''
  return { value: props.hint + suffix, showDelay: 200 }
})
</script>

<template>
  <router-link
    v-if="to"
    :to="to"
    :class="tileClass"
    v-tooltip.bottom="tooltipValue"
  >
    <div class="kpi-label">
      {{ label }}
      <i v-if="hint" class="pi pi-info-circle kpi-info" />
    </div>
    <div class="kpi-value">{{ value }}</div>
    <div class="kpi-sub" v-if="sub">{{ sub }}</div>
  </router-link>
  <div
    v-else
    :class="tileClass"
    v-tooltip.bottom="tooltipValue"
  >
    <div class="kpi-label">
      {{ label }}
      <i v-if="hint" class="pi pi-info-circle kpi-info" />
    </div>
    <div class="kpi-value">{{ value }}</div>
    <div class="kpi-sub" v-if="sub">{{ sub }}</div>
  </div>
</template>

<style scoped>
.kpi-tile {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-left: 4px solid #cbd5e1;
  border-radius: 8px;
  padding: 1rem 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  min-height: 104px;
  text-decoration: none;
  color: inherit;
  transition: transform 120ms ease, box-shadow 120ms ease;
}
.kpi-tile.primary { border-left-color: #6366f1; }
.kpi-tile.danger  { border-left-color: #ef4444; }
.kpi-tile.warn    { border-left-color: #f59e0b; }
.kpi-tile.success { border-left-color: #22c55e; }

.kpi-tile.pct-red    { border-left-color: #ef4444; background: #fef2f2; }
.kpi-tile.pct-orange { border-left-color: #f97316; background: #fff7ed; }
.kpi-tile.pct-yellow { border-left-color: #eab308; background: #fefce8; }
.kpi-tile.pct-green  { border-left-color: #22c55e; background: #f0fdf4; }

.kpi-tile--clickable { cursor: pointer; }
.kpi-tile--clickable:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08);
}

.kpi-label {
  font-size: 0.72rem; color: #64748b;
  text-transform: uppercase; letter-spacing: 0.04em;
  display: flex; align-items: center; gap: 0.3rem;
}
.kpi-info { font-size: 0.8rem; color: #94a3b8; cursor: help; }
.kpi-value {
  font-size: 1.5rem; font-weight: 700; color: #1e293b;
  letter-spacing: -0.02em;
}
.kpi-sub { font-size: 0.78rem; color: #64748b; margin-top: auto; }
</style>
```

- [ ] **Step 2: Проверить tsc и build**

Run: `cd frontend && npx vue-tsc --noEmit && npm run build`
Expected: чисто и build успешен.

- [ ] **Step 3: Коммит**

```bash
git add frontend/src/components/KpiTile.vue
git commit -m "feat(kpi-tile): опциональный prop to делает плитку router-link с hover-эффектом"
```

---

## Task 12: Frontend — DashboardView навешивает drill-down на 8 плиток

**Files:**
- Modify: `frontend/src/views/DashboardView.vue`

- [ ] **Step 1: Добавить хелпер `compositionLink`**

В `<script setup>`, после `const router = useRouter()`:

```ts
function compositionLink(metric: string, period?: string | null) {
  return {
    path: '/reports',
    query: {
      preset: 'composition',
      metric,
      ...(period ? { period } : {}),
    },
  }
}
```

- [ ] **Step 2: Навесить `:to` на 8 плиток**

В блоке «Финансы» (3 плитки получают `:to`, плитка «Долг» — нет):

```vue
<KpiTile
  :label="`MRR факт · ${ruMonth(summary.fact_month)}`"
  :value="fmtRub(summary.mrr_fact)"
  :sub="summary.collection_rate_fact != null
    ? `собрано ${summary.collection_rate_fact}% от плана · норма 90%` : ''"
  :pct="summary.collection_rate_fact"
  :hint="HINTS.mrrFact"
  accent="primary"
  :to="compositionLink('mrr_fact', summary.fact_month)"
/>
<KpiTile
  label="MRR план"
  :value="fmtRub(summary.mrr_plan)"
  sub="база подписки"
  :hint="HINTS.mrrPlan"
  accent="neutral"
  :to="compositionLink('mrr_plan')"
/>
<KpiTile
  :label="`Сбор · ${ruMonth(summary.current_month_label)} (текущий)`"
  :value="fmtRub(summary.current_month_collected)"
  :sub="`${currentMonthPct ?? '—'}% плана · день ${summary.days_passed}/${summary.days_in_month}`"
  :pct="currentMonthPct"
  :hint="HINTS.sbor"
  :to="compositionLink('collected_current', summary.current_month_label)"
/>
<KpiTile
  label="Долг"
  :value="fmtRub(summary.total_debt)"
  :sub="`90+: ${fmtRub(summary.debt_90plus_amount)} (${summary.debt_90plus_share}%)`"
  :hint="HINTS.debt"
  accent="danger"
/>
```

В блоке «Клиентская база» (5 плиток получают `:to`, плитка «Churn rate» — нет):

```vue
<KpiTile
  label="Активные клиенты"
  :value="fmt(summary.active_clients)"
  sub="всего в статусе «Активен»"
  :hint="HINTS.active"
  accent="success"
  :to="compositionLink('active_clients')"
/>
<KpiTile
  label="Новые за год"
  :value="fmt(summary.new_paid_curr_year)"
  :sub="`впервые заплатили в ${summary.current_month_label?.slice(0, 4)}`"
  :hint="HINTS.newYear"
  accent="success"
  :to="compositionLink('new_paid_curr_year',
    summary.current_month_label?.slice(0, 4))"
/>
<KpiTile
  :label="`Новые · ${ruMonth(summary.fact_month)}`"
  :value="fmt(summary.new_paid_prev_month)"
  sub="впервые заплатили"
  :hint="HINTS.newPrev"
  accent="success"
  :to="compositionLink('new_paid_prev_month', summary.fact_month)"
/>
<KpiTile
  :label="`Новые · ${ruMonth(summary.current_month_label)}`"
  :value="fmt(summary.new_paid_curr_month)"
  sub="впервые заплатили · месяц идёт"
  :hint="HINTS.newCurr"
  accent="success"
  :to="compositionLink('new_paid_curr_month', summary.current_month_label)"
/>
<KpiTile
  label="Отток с начала года"
  :value="fmt(summary.stopped_since_year_start)"
  sub="перестали платить"
  :hint="HINTS.stopped"
  accent="danger"
  :to="compositionLink('stopped_since_year_start')"
/>
<KpiTile
  label="Churn rate"
  :value="summary.churn_rate != null ? `${summary.churn_rate}%` : '—'"
  sub="доля ушедших за год"
  :hint="HINTS.churn"
  accent="warn"
/>
```

- [ ] **Step 3: tsc и build**

Run: `cd frontend && npx vue-tsc --noEmit && npm run build`
Expected: чисто, build успешен.

- [ ] **Step 4: Коммит**

```bash
git add frontend/src/views/DashboardView.vue
git commit -m "feat(dashboard): drill-down через router-link на 8 KPI-плитках"
```

---

## Task 13: Frontend — ReportsView пресет composition, парсинг query, контрольная сумма

**Files:**
- Modify: `frontend/src/views/ReportsView.vue`

- [ ] **Step 1: Расширить `presetOptions` и `COLUMN_CATALOG`**

Заменить `presetOptions`:

```ts
const presetOptions = [
  { label: 'Реестр должников', value: 'debtors' },
  { label: 'Дисциплина платежей', value: 'discipline' },
  { label: 'Состав показателя', value: 'composition' },
]
```

Добавить каталог метрик:

```ts
const METRIC_OPTIONS = [
  { value: 'mrr_fact',                 label: 'MRR факт (за месяц)',          period: 'month' },
  { value: 'collected_current',        label: 'Сбор за месяц',                period: 'month' },
  { value: 'mrr_plan',                 label: 'MRR план',                     period: 'none' },
  { value: 'active_clients',           label: 'Активные клиенты',             period: 'none' },
  { value: 'new_paid_curr_year',       label: 'Новые за год',                 period: 'year' },
  { value: 'new_paid_prev_month',      label: 'Новые за прошлый месяц',       period: 'month' },
  { value: 'new_paid_curr_month',      label: 'Новые за текущий месяц',       period: 'month' },
  { value: 'stopped_since_year_start', label: 'Отток с начала года',          period: 'none' },
] as const

type MetricKey = typeof METRIC_OPTIONS[number]['value']

function metricPeriodKind(m: string | null): 'month' | 'year' | 'none' {
  return METRIC_OPTIONS.find(x => x.value === m)?.period ?? 'none'
}

const MONEY_METRICS = new Set(['mrr_fact', 'collected_current', 'mrr_plan'])
```

В `COLUMN_CATALOG` добавить ключ `composition`:

```ts
composition: [
  { key: 'name', label: 'Клиент' },
  { key: 'inn', label: 'ИНН' },
  { key: 'manager', label: 'Менеджер' },
  { key: 'monthly_ap', label: 'АП/мес' },
  { key: 'status', label: 'Статус' },
  { key: 'city', label: 'Город' },
  { key: 'contribution', label: 'Вклад в показатель, ₽' },
  { key: 'first_payment_date', label: 'Дата первого платежа' },
  { key: 'last_payment_date', label: 'Дата последнего платежа' },
  { key: 'days_since_last', label: 'Дней с последнего платежа' },
],
```

В `CURRENCY_KEYS` добавить `contribution`:

```ts
const CURRENCY_KEYS = new Set(['monthly_ap', 'total_debt', 'priority', 'contribution'])
```

В `COLUMN_WIDTH` добавить:

```ts
contribution: '12rem',
first_payment_date: '11rem',
last_payment_date: '11rem',
days_since_last: '11rem',
```

- [ ] **Step 2: Расширить `criteria`, `preset`, добавить `controlValue` и `periodDate`**

```ts
const preset = ref<'debtors' | 'discipline' | 'composition'>('debtors')

const criteria = reactive({
  // ... существующие поля ...
  metric: null as MetricKey | null,
  period: null as string | null,
})

const controlValue = ref<number | null>(null)

const periodDate = computed<Date | null>({
  get() {
    if (!criteria.period) return null
    const kind = metricPeriodKind(criteria.metric)
    if (kind === 'year') return new Date(Number(criteria.period), 0, 1)
    const [y, m] = criteria.period.split('-').map(Number)
    if (!y || !m) return null
    return new Date(y, m - 1, 1)
  },
  set(d) {
    if (!d) {
      criteria.period = null
      return
    }
    const kind = metricPeriodKind(criteria.metric)
    criteria.period = kind === 'year'
      ? String(d.getFullYear())
      : `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
  },
})
```

- [ ] **Step 3: Подключить vue-router, дополнить `buildCriteria()`, `runPreview()`**

Импорт:

```ts
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
```

`buildCriteria()`:

```ts
function buildCriteria() {
  const c: any = {
    period_from: monthStr(criteria.period_from),
    period_to: monthStr(criteria.period_to),
    statuses: criteria.statuses,
    manager_id: criteria.manager_id || null,
    aging_buckets: preset.value === 'debtors' ? criteria.aging_buckets : [],
    contract_types: criteria.contract_types,
    city: criteria.city || null,
    min_debt: criteria.min_debt || 0,
    columns: criteria.columns,
    sort_by: criteria.sort_by || null,
    sort_dir: criteria.sort_dir,
    include_excluded: criteria.include_excluded,
  }
  if (preset.value === 'composition') {
    c.metric = criteria.metric
    c.period = criteria.period
  }
  return c
}
```

`runPreview()`:

```ts
async function runPreview() {
  loading.value = true
  controlValue.value = null
  try {
    const res = await api.post(`/reports/${preset.value}/preview`, buildCriteria())
    columns.value = res.data.columns
    rows.value = res.data.rows
    total.value = res.data.total
    if (preset.value === 'composition' && typeof res.data.control_value === 'number') {
      controlValue.value = res.data.control_value
    }
  } catch (e: any) {
    const detail = e?.response?.data?.detail ?? 'Не удалось построить отчёт'
    toast.add({ severity: 'error', summary: detail, life: 4000 })
  } finally {
    loading.value = false
  }
}
```

Парсинг query в `onMounted`:

```ts
function applyQueryComposition() {
  const q = route.query
  if (q.preset !== 'composition' || typeof q.metric !== 'string') return false
  const known = METRIC_OPTIONS.some(m => m.value === q.metric)
  if (!known) {
    toast.add({ severity: 'warn', summary: 'Неизвестный показатель', life: 3500 })
    return false
  }
  preset.value = 'composition'
  criteria.metric = q.metric as MetricKey
  criteria.period = typeof q.period === 'string' ? q.period : null
  return true
}

onMounted(() => {
  loadManagers()
  loadTemplates()
  applyQueryComposition()
  runPreview()
})
```

Очистка query при ручной смене пресета — изменить `watch(preset, ...)`:

```ts
watch(preset, () => {
  selectedTemplate.value = null
  criteria.columns = []
  criteria.sort_by = null
  criteria.aging_buckets = []
  if (preset.value !== 'composition') {
    criteria.metric = null
    criteria.period = null
  }
  if (route.query.preset && route.query.preset !== preset.value) {
    router.replace({ query: {} })
  }
  runPreview()
})
```

- [ ] **Step 4: UI — поля «Показатель», «Период», блок контроля**

В `<template>`, в `<div class="criteria-grid">` добавить **в начало**:

```vue
<label v-if="preset === 'composition'" class="field">
  <span>Показатель</span>
  <Select v-model="criteria.metric" :options="METRIC_OPTIONS"
          optionLabel="label" optionValue="value"
          placeholder="выберите" />
</label>
<label v-if="preset === 'composition' && metricPeriodKind(criteria.metric) !== 'none'"
       class="field">
  <span>Период</span>
  <DatePicker
    v-model="periodDate"
    :view="metricPeriodKind(criteria.metric) === 'year' ? 'year' : 'month'"
    :dateFormat="metricPeriodKind(criteria.metric) === 'year' ? 'yy' : 'mm/yy'"
    showButtonBar />
</label>
```

В шапке таблицы:

```vue
<template #header>
  <div class="table-header-bar">
    <span class="row-count">Строк: {{ total }}</span>
    <span v-if="preset === 'composition' && controlValue !== null" class="control-value">
      Контроль:
      <b>{{ formatControlValue(controlValue) }}</b>
    </span>
  </div>
</template>
```

Хелпер форматирования:

```ts
function formatControlValue(v: number): string {
  if (criteria.metric && MONEY_METRICS.has(criteria.metric)) {
    return new Intl.NumberFormat('ru-RU', {
      style: 'currency', currency: 'RUB', maximumFractionDigits: 0,
    }).format(v)
  }
  return `${v} клиентов`
}
```

Стили (в `<style scoped>`):

```css
.table-header-bar {
  display: flex; align-items: center; gap: 1rem; flex-wrap: wrap;
}
.control-value {
  margin-left: auto;
  font-size: 0.85rem; color: #475569;
}
.control-value b { color: #0f172a; font-weight: 700; }
```

Подсказка пресета (`<p class="preset-hint">`):

```vue
<p class="preset-hint">
  {{ preset === 'debtors'
    ? 'Кого взыскивать: должники с приоритетом взыскания (долг × возраст × шанс возврата).'
    : preset === 'discipline'
    ? 'Кто соскальзывает в долг: собираемость, дисциплина и тренд по активным подписчикам.'
    : 'Состав KPI-плитки дашборда: какие клиенты и суммы попали в показатель. Контрольная сумма в шапке должна совпадать с плиткой.' }}
</p>
```

- [ ] **Step 5: tsc + build**

Run: `cd frontend && npx vue-tsc --noEmit && npm run build`
Expected: чисто, build успешен.

- [ ] **Step 6: Коммит**

```bash
git add frontend/src/views/ReportsView.vue
git commit -m "feat(reports): пресет composition с парсингом query и контрольной суммой"
```

---

## Task 14: Финальная проверка и история разработки

**Files:**
- Modify: `agent_docs/development-history.md`
- (если запись 11-я) Move: `agent_docs/development-history-archive.md`

- [ ] **Step 1: Прогнать backend pytest + ruff**

Run: `cd backend && pytest -q && ruff check app/services/composition_service.py app/services/dashboard_service.py app/api/v1/dashboard.py app/api/v1/reports.py app/services/report_service.py`
Expected: ~196+ passed, ruff чисто.

- [ ] **Step 2: Прогнать frontend tsc и build**

Run: `cd frontend && npx vue-tsc --noEmit && npm run build`
Expected: чисто, build успешен.

- [ ] **Step 3: Добавить запись в `agent_docs/development-history.md`**

В начало (после блока «## Записи») вставить:

```markdown
### 2026-05-20 — Drill-down KPI-плиток Dashboard в раздел «Отчёты»

**Контекст:** руководителю нужно видеть «откуда взялось число» на каждой
KPI-плитке Dashboard — какие клиенты и суммы формируют MRR факт, план,
сбор за текущий месяц, активных, новых за год/месяц, отток.

**Спецификация/план:** `docs/superpowers/specs/2026-05-20-dashboard-drilldown-design.md`,
`docs/superpowers/plans/2026-05-20-dashboard-drilldown.md`.

**Что сделано:**
- **Рефакторинг:** общие helpers расчёта KPI вынесены в
  `app/services/dashboard_service.py` (`plan_mrr_total`,
  `collected_by_charge_month`, `accrued_by_month`, `first_pay_rows`,
  `last_pay_rows`, `excl`, `to_float`, `months_back`). Оба места (дашборд
  и drill-down) считают из одной точки.
- **Backend:** новый пресет `composition` в `/reports` с параметрами
  `metric` и `period`. Builder `composition_service.py` реализует 8
  метрик. Ответ `/preview` для composition содержит `control_value` —
  ₽ для денежных, count для количественных.
- **Frontend:** `KpiTile` получил опциональный prop `to`
  (становится router-link с hover-эффектом). Dashboard навешивает
  `:to="compositionLink(metric, period)"` на 8 плиток (Долг и Churn
  rate не трогаем — у Долга drill-down через aging-чарт, Churn —
  производная). `ReportsView` парсит query, показывает в шапке таблицы
  контрольную сумму, скрывает дебитор-специфичные фильтры для composition,
  при ручной смене пресета очищает query.
- **Инвариант:** `test_composition_matches_dashboard.py` — 8 тестов,
  для каждой метрики проверяет, что `dashboard.summary[metric] == composition.control_value`.
  Контракт регрессии: пока тесты зелёные, drill-down не разъезжается с плитками.

**Тесты:** backend 173 → **~196 passed** (+23). Frontend: `vue-tsc`
чисто, `vite build` успешен. ruff чисто.

**Миграции:** не требуются.

**Следующий шаг:** деплой на production, браузерная проверка drill-down
по каждой из 8 плиток (контрольная сумма совпадает с плиткой).
```

- [ ] **Step 4: Если получилось > 10 записей, архивировать самую старую**

Read `agent_docs/development-history.md`, посчитать `### YYYY-MM-DD` заголовки. Если их > 10, переместить самые старые (превышающие 10) в `agent_docs/development-history-archive.md`.

- [ ] **Step 5: Коммит**

```bash
git add agent_docs/development-history.md
test -f agent_docs/development-history-archive.md && \
  git add agent_docs/development-history-archive.md
git commit -m "docs(history): drill-down KPI-плиток Dashboard в Отчёты"
```

---

## Финальный чек-лист (DoD)

После всех task'ов проверить:

- [ ] Backend pytest: 196+ passed, 0 failed
- [ ] Backend ruff: чисто по новым/изменённым файлам
- [ ] Frontend vue-tsc: чисто
- [ ] Frontend vite build: успех
- [ ] Браузерная проверка (на dev-сервере, до деплоя):
  - Клик по плитке «MRR факт» → composition открывается, контроль = плитке
  - То же для «MRR план», «Сбор», «Активные», «Новые за год», «Новые за прошлый месяц», «Новые за текущий месяц», «Отток»
  - Плитка «Долг» по-прежнему ведёт через aging-чарт
  - Плитка «Churn rate» — не кликается
  - В Reports → ручная смена пресета через SelectButton очищает query из URL
  - В composition можно сменить метрику и период — preview перестраивается
  - Экспорт в Excel работает для composition
  - Сохранение и применение шаблона работает для composition
- [ ] Запись в `agent_docs/development-history.md` добавлена

---

## Self-Review

**1. Spec coverage:** все 8 метрик реализованы (Task 3-8); URL-контракт парсится (Task 13); control_value возвращается (Task 9); KpiTile с `to`-prop (Task 11); очистка query при смене пресета (Task 13); инвариант (Task 10); рефакторинг helpers (Task 1); регистрация пресета (Task 2). ✓

**2. Placeholder scan:** нет «TODO», «similar to», «add validation». Везде конкретные пути файлов и код. ✓

**3. Type consistency:** `plan_mrr_total`, `collected_by_charge_month`, `first_pay_rows`, `last_pay_rows` — публичные имена в `dashboard_service.py`, используются согласованно. `ReportCriteria.metric`/`.period` — поля `str | None`, согласовано на backend (Task 2) и frontend (Task 13). `control_value` — поле ответа `/preview`, согласовано в Task 9 и Task 13. `_COLS_BY_METRIC` (Task 2) использует те же ключи метрик, что `_DISPATCH` (Task 3-8). ✓
