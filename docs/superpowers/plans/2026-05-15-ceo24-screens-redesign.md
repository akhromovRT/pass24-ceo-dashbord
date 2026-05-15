# CEO24 Screens Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Переработать 4 рабочих экрана CEO24 (Dashboard, Реестр клиентов, карточка клиента, Должники) в полезные для управленческих решений инструменты, добавив поддерживающие backend-эндпоинты.

**Architecture:** Backend — новые/расширенные FastAPI-роутеры поверх существующих моделей SQLModel, без миграций БД (все поля уже есть). Frontend — переписанные Vue 3 / PrimeVue / vue-echarts экраны + 3 общих компонента. Карточка клиента получает редактирование через `PATCH /organizations/{inn}`.

**Tech Stack:** Python 3.12, FastAPI, SQLModel, PostgreSQL 16 / pytest. Vue 3 + TypeScript, PrimeVue, vue-echarts, Pinia, Vite.

**Спецификация:** `docs/superpowers/specs/2026-05-15-ceo24-screens-redesign-design.md`

---

## File Structure

**Backend (модификации, без новых файлов):**
- `backend/app/api/v1/organizations.py` — +`PATCH /{inn}`, +`GET /{inn}/documents`, +схема `OrganizationUpdate`
- `backend/app/api/v1/dashboard.py` — расширить `summary`, +`collection-trend`, +`attention`
- `backend/app/api/v1/billing.py` — +`segments`, обогатить `debtors`
- `backend/app/api/v1/users.py` — +`GET /options`
- Тесты: `backend/tests/test_api_organizations.py`, `test_api_dashboard.py` (новый), `test_api_billing.py` (новый), `test_users_api.py`

**Frontend:**
- `frontend/src/components/KpiTile.vue` — новый
- `frontend/src/components/SegmentBand.vue` — новый
- `frontend/src/components/AttentionPanel.vue` — новый
- `frontend/src/stores/organizations.ts` — +`updateOrganization`
- `frontend/src/views/DashboardView.vue` — переписать
- `frontend/src/views/DebtorsView.vue` — переписать
- `frontend/src/views/BillingView.vue` — +шапка сегментов, +режим «Шахматка»
- `frontend/src/views/ClientCardView.vue` — переписать

---

## Task 1: PATCH /organizations/{inn} — редактирование организации

**Files:**
- Modify: `backend/app/api/v1/organizations.py`
- Test: `backend/tests/test_api_organizations.py`

- [ ] **Step 1: Написать падающие тесты**

Добавить в `backend/tests/test_api_organizations.py` в класс `TestOrganizationsAPI`:

```python
def test_patch_updates_editable_field(self, client, sample_org):
    resp = client.patch(
        "/api/v1/organizations/9717053891",
        json={"name_display": "Седьмое небо", "notes": "VIP"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name_display"] == "Седьмое небо"
    assert body["notes"] == "VIP"

def test_patch_change_status(self, client, sample_org):
    resp = client.patch(
        "/api/v1/organizations/9717053891", json={"status": "suspended"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "suspended"

def test_patch_partial_keeps_other_fields(self, client, sample_org):
    resp = client.patch("/api/v1/organizations/9717053891", json={"notes": "x"})
    assert resp.status_code == 200
    assert resp.json()["name_display"] == "7 НЕБО"

def test_patch_rejects_negative_monthly_ap(self, client, sample_org):
    resp = client.patch(
        "/api/v1/organizations/9717053891", json={"monthly_ap": -100}
    )
    assert resp.status_code == 422

def test_patch_ignores_readonly_inn(self, client, sample_org):
    resp = client.patch(
        "/api/v1/organizations/9717053891", json={"inn": "0000000000"}
    )
    assert resp.status_code == 200
    assert resp.json()["inn"] == "9717053891"

def test_patch_not_found(self, client):
    resp = client.patch("/api/v1/organizations/0000000000", json={"notes": "x"})
    assert resp.status_code == 404
```

- [ ] **Step 2: Запустить тесты — убедиться, что падают**

Run: `cd backend && python -m pytest tests/test_api_organizations.py -k patch -v`
Expected: FAIL (405 Method Not Allowed / эндпоинта нет)

- [ ] **Step 3: Реализовать схему и эндпоинт**

В `backend/app/api/v1/organizations.py` добавить импорты в начало файла:

```python
from datetime import UTC, date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field as PydField

from app.models import OrgType
```

И в конец файла:

```python
class OrganizationUpdate(BaseModel):
    """Частичное обновление. Read-only поля (inn, name_1c, total_debt,
    payment_score, *_raw) сюда не входят — источник истины импорт из 1С."""
    model_config = ConfigDict(extra="ignore")

    name_display: str | None = None
    org_type: OrgType | None = None
    status: OrgStatus | None = None
    manager_id: uuid.UUID | None = None
    client_since: date | None = None
    objects: int | None = None
    object_type: str | None = None
    cloud_url: str | None = None
    system_number: str | None = None
    equipment: str | None = None
    address: str | None = None
    city_region: str | None = None
    has_folder: bool | None = None
    monthly_ap: Decimal | None = PydField(default=None, ge=0)
    notes: str | None = None
    doc_exchange: str | None = None
    in_registry: bool | None = None
    excluded_from_analytics: bool | None = None
    excluded_reason: str | None = None


@router.patch("/{inn}")
def update_organization(
    inn: str,
    payload: OrganizationUpdate,
    session: Session = Depends(get_session),
):
    org = session.exec(
        select(Organization).where(Organization.inn == inn)
    ).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(org, key, value)
    org.updated_at = datetime.now(UTC)
    session.add(org)
    session.commit()
    session.refresh(org)
    return org
```

`PydField` — алиас pydantic-`Field`, чтобы не конфликтовать с `sqlmodel.Field`.

- [ ] **Step 4: Запустить тесты — убедиться, что проходят**

Run: `cd backend && python -m pytest tests/test_api_organizations.py -k patch -v`
Expected: PASS (6 тестов)

- [ ] **Step 5: Коммит**

```bash
git add backend/app/api/v1/organizations.py backend/tests/test_api_organizations.py
git commit -m "feat(api): PATCH /organizations/{inn} — редактирование организации"
```

---

## Task 2: GET /organizations/{inn}/documents — история платежей

**Files:**
- Modify: `backend/app/api/v1/organizations.py`
- Test: `backend/tests/test_api_organizations.py`

- [ ] **Step 1: Написать падающий тест**

Добавить тесты в класс `TestOrganizationsAPI`:

```python
def test_get_documents(self, client, db_session, sample_org):
    from datetime import date as _date
    from decimal import Decimal
    from app.models import Contract, Document, DocType
    contract = Contract(organization_id=sample_org.id, raw_name="Д-1")
    db_session.add(contract)
    db_session.commit()
    db_session.refresh(contract)
    db_session.add(Document(
        contract_id=contract.id, organization_id=sample_org.id,
        doc_type=DocType.PAYMENT, amount=Decimal("15000"),
        doc_date=_date(2026, 4, 10), raw_name="Платёж",
    ))
    db_session.add(Document(
        contract_id=contract.id, organization_id=sample_org.id,
        doc_type=DocType.SALE, amount=Decimal("15000"),
        doc_date=_date(2026, 5, 1), raw_name="Реализация",
    ))
    db_session.commit()
    resp = client.get("/api/v1/organizations/9717053891/documents")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 2
    assert rows[0]["doc_date"] == "2026-05-01"  # сортировка по убыванию

def test_get_documents_not_found(self, client):
    resp = client.get("/api/v1/organizations/0000000000/documents")
    assert resp.status_code == 404
```

Перед написанием проверить `backend/app/models/contract.py` — обязательные поля `Contract`; при необходимости дополнить fixture.

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `cd backend && python -m pytest tests/test_api_organizations.py -k documents -v`
Expected: FAIL (404 — роут не существует)

- [ ] **Step 3: Реализовать эндпоинт**

В `organizations.py` добавить `Document` в импорт из `app.models` и эндпоинт:

```python
@router.get("/{inn}/documents")
def get_organization_documents(inn: str, session: Session = Depends(get_session)):
    org = session.exec(
        select(Organization).where(Organization.inn == inn)
    ).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    docs = session.exec(
        select(Document)
        .where(Document.organization_id == org.id)
        .order_by(col(Document.doc_date).desc())
    ).all()
    return docs
```

`col` уже импортирован в `organizations.py`.

- [ ] **Step 4: Запустить — убедиться, что проходит**

Run: `cd backend && python -m pytest tests/test_api_organizations.py -k documents -v`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add backend/app/api/v1/organizations.py backend/tests/test_api_organizations.py
git commit -m "feat(api): GET /organizations/{inn}/documents — история документов"
```

---

## Task 3: GET /users/options — список менеджеров для дропдауна

**Files:**
- Modify: `backend/app/api/v1/users.py`
- Test: `backend/tests/test_users_api.py`

- [ ] **Step 1: Написать падающий тест**

В `test_users_api.py` добавить (использует `viewer_client` — проверяет доступ не-админу):

```python
def test_users_options_available_to_non_admin(viewer_client):
    resp = viewer_client.get("/api/v1/users/options")
    assert resp.status_code == 200
    rows = resp.json()
    assert isinstance(rows, list)
    assert all("id" in r and "name" in r for r in rows)
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `cd backend && python -m pytest tests/test_users_api.py -k options -v`
Expected: FAIL (404 или 403)

- [ ] **Step 3: Реализовать эндпоинт**

Сначала прочитать `backend/app/api/v1/users.py` целиком. Добавить эндпоинт, доступный любому аутентифицированному пользователю (НЕ под admin-guard):

```python
@router.get("/options", dependencies=[Depends(get_current_user)])
def list_user_options(session: Session = Depends(get_session)):
    users = session.exec(
        select(User).where(User.is_active == True)  # noqa: E712
    ).all()
    return [{"id": str(u.id), "name": u.name} for u in users]
```

Если роутер объявлен с router-level admin-guard — перенести guard с уровня роутера на конкретные admin-эндпоинты, а `/options` оставить только под `get_current_user`. Импортировать `get_current_user`, если ещё не импортирован.

- [ ] **Step 4: Запустить тесты users целиком**

Run: `cd backend && python -m pytest tests/test_users_api.py -v`
Expected: PASS (новый + существующие admin-only)

- [ ] **Step 5: Коммит**

```bash
git add backend/app/api/v1/users.py backend/tests/test_users_api.py
git commit -m "feat(api): GET /users/options — список менеджеров"
```

---

## Task 4: GET /dashboard/collection-trend — тренд сбора без пустых месяцев

**Files:**
- Modify: `backend/app/api/v1/dashboard.py`
- Test: `backend/tests/test_api_dashboard.py` (создать)

- [ ] **Step 1: Создать тестовый файл с падающим тестом**

Создать `backend/tests/test_api_dashboard.py`:

```python
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api.v1.auth import get_current_user
from app.core.database import get_session
from app.main import app
from app.models import (
    Contract, Document, DocType, Organization, OrgStatus, User, UserRole,
)


@pytest.fixture
def client(db_session: Session):
    def override_get_session():
        yield db_session

    def override_get_current_user():
        return User(name="T", email="t@t.ru", hashed_password="x",
                    role=UserRole.ADMIN, is_active=True)

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_get_current_user
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def org_with_payments(db_session: Session) -> Organization:
    org = Organization(inn="7700000001", name_1c="Орг",
                        status=OrgStatus.ACTIVE, monthly_ap=Decimal("10000"))
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    contract = Contract(organization_id=org.id, raw_name="Д")
    db_session.add(contract)
    db_session.commit()
    db_session.refresh(contract)
    for d, amt in [(date(2026, 1, 15), 10000), (date(2026, 3, 10), 8000)]:
        db_session.add(Document(
            contract_id=contract.id, organization_id=org.id,
            doc_type=DocType.PAYMENT, amount=Decimal(amt), doc_date=d,
        ))
    db_session.commit()
    return org


def test_collection_trend_only_months_with_data(client, org_with_payments):
    resp = client.get("/api/v1/dashboard/collection-trend")
    assert resp.status_code == 200
    rows = resp.json()
    labels = {r["label"] for r in rows}
    assert labels == {"01/2026", "03/2026"}  # пустые месяцы отсутствуют


def test_collection_trend_empty(client):
    resp = client.get("/api/v1/dashboard/collection-trend")
    assert resp.status_code == 200
    assert resp.json() == []
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `cd backend && python -m pytest tests/test_api_dashboard.py -k collection_trend -v`
Expected: FAIL (404)

- [ ] **Step 3: Реализовать эндпоинт**

В `backend/app/api/v1/dashboard.py` добавить:

```python
@router.get("/collection-trend")
def collection_trend(session: Session = Depends(get_session)):
    """Тренд сбора платежей: только месяцы, где есть хотя бы один PAYMENT."""
    plan_mrr = _plan_mrr_total(session)
    rows = session.exec(
        select(
            func.extract("year", Document.doc_date).label("y"),
            func.extract("month", Document.doc_date).label("m"),
            func.sum(Document.amount).label("fact"),
        )
        .join(Organization, Organization.id == Document.organization_id)
        .where(_excl(), Document.doc_type == DocType.PAYMENT,
               Document.doc_date.is_not(None))  # type: ignore[union-attr]
        .group_by("y", "m")
        .order_by("y", "m")
    ).all()
    out = []
    for y, m, fact in rows:
        y, m, fact = int(y), int(m), _f(fact)
        out.append({
            "year": y, "month": m, "label": f"{m:02d}/{y}",
            "plan": plan_mrr, "fact": fact,
            "ratio": round(fact / plan_mrr * 100, 1) if plan_mrr else None,
        })
    return out
```

- [ ] **Step 4: Запустить — убедиться, что проходит**

Run: `cd backend && python -m pytest tests/test_api_dashboard.py -k collection_trend -v`
Expected: PASS (2 теста)

- [ ] **Step 5: Коммит**

```bash
git add backend/app/api/v1/dashboard.py backend/tests/test_api_dashboard.py
git commit -m "feat(api): GET /dashboard/collection-trend — тренд без пустых месяцев"
```

---

## Task 5: GET /dashboard/attention — агрегация алертов по категориям

**Files:**
- Modify: `backend/app/api/v1/dashboard.py`
- Test: `backend/tests/test_api_dashboard.py`

- [ ] **Step 1: Написать падающий тест**

Добавить в `test_api_dashboard.py`:

```python
def test_attention_aggregates_open_alerts(client, db_session: Session):
    from app.models import Alert, AlertType, AlertSeverity, AlertStatus
    org = Organization(inn="7700000002", name_1c="О2", status=OrgStatus.ACTIVE)
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    db_session.add(Alert(
        organization_id=org.id, alert_type=AlertType.LARGE_DEBT,
        severity=AlertSeverity.CRITICAL, title="Долг", status=AlertStatus.OPEN,
        metric_value=500000.0))
    db_session.add(Alert(
        organization_id=org.id, alert_type=AlertType.LARGE_DEBT,
        severity=AlertSeverity.CRITICAL, title="Долг2", status=AlertStatus.OPEN,
        metric_value=300000.0))
    db_session.add(Alert(
        organization_id=org.id, alert_type=AlertType.NEW_CLIENT,
        severity=AlertSeverity.INFO, title="Новый", status=AlertStatus.RESOLVED))
    db_session.commit()
    resp = client.get("/api/v1/dashboard/attention")
    assert resp.status_code == 200
    rows = resp.json()
    debt = next(r for r in rows if r["type"] == "large_debt")
    assert debt["count"] == 2
    assert debt["amount"] == 800000.0
    assert all(r["type"] != "new_client" for r in rows)  # RESOLVED исключён
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `cd backend && python -m pytest tests/test_api_dashboard.py -k attention -v`
Expected: FAIL (404)

- [ ] **Step 3: Реализовать эндпоинт**

В `dashboard.py` добавить (проверить, что `AlertType`, `AlertStatus`, `Alert` импортированы — в шапке файла они есть):

```python
_ALERT_META = {
    "large_debt": ("Крупная просрочка", "/debtors", 3),
    "non_payment": ("Неоплата", "/debtors", 3),
    "churn_risk": ("Риск ухода клиента", "/billing", 2),
    "collectability_drop": ("Падение собираемости", "/billing", 2),
    "project_overdue": ("Просрочка проекта", "/billing", 2),
    "anomaly": ("Аномалия в данных", "/billing", 2),
    "unassigned_client": ("Клиент без менеджера", "/billing", 1),
    "phantom_deal": ("Фантомная сделка", "/billing", 1),
    "new_client": ("Новый клиент", "/billing", 1),
}


@router.get("/attention")
def attention(session: Session = Depends(get_session)):
    """Открытые алерты, сгруппированные по типу. Для панели «Требуют внимания»."""
    rows = session.exec(
        select(
            Alert.alert_type,
            func.count().label("cnt"),
            func.coalesce(func.sum(Alert.metric_value), 0).label("amount"),
        )
        .where(Alert.status == AlertStatus.OPEN)
        .group_by(Alert.alert_type)
    ).all()
    out = []
    for alert_type, cnt, amount in rows:
        key = alert_type.value if hasattr(alert_type, "value") else str(alert_type)
        label, route, weight = _ALERT_META.get(key, (key, "/billing", 1))
        out.append({
            "type": key, "label": label, "route": route,
            "count": int(cnt), "amount": _f(amount), "weight": weight,
        })
    out.sort(key=lambda r: (-r["weight"], -r["amount"]))
    return out
```

- [ ] **Step 4: Запустить — убедиться, что проходит**

Run: `cd backend && python -m pytest tests/test_api_dashboard.py -k attention -v`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add backend/app/api/v1/dashboard.py backend/tests/test_api_dashboard.py
git commit -m "feat(api): GET /dashboard/attention — агрегация алертов"
```

---

## Task 6: Расширение GET /dashboard/summary

**Files:**
- Modify: `backend/app/api/v1/dashboard.py`
- Test: `backend/tests/test_api_dashboard.py`

- [ ] **Step 1: Написать падающий тест**

Добавить в `test_api_dashboard.py`:

```python
def test_summary_has_current_month_fields(client, org_with_payments):
    resp = client.get("/api/v1/dashboard/summary")
    assert resp.status_code == 200
    body = resp.json()
    for key in ("current_month_label", "current_month_collected",
                "days_passed", "days_in_month",
                "debt_90plus_amount", "debt_90plus_share",
                "collection_rate_fact"):
        assert key in body
    assert 1 <= body["days_in_month"] <= 31
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `cd backend && python -m pytest tests/test_api_dashboard.py -k current_month -v`
Expected: FAIL (KeyError — полей нет)

- [ ] **Step 3: Реализовать расширение**

В `dashboard.py`, функция `dashboard_summary`. Вверху файла добавить импорт `import calendar`. Перед `return` добавить вычисления:

```python
    # --- текущий (незакрытый) месяц ---
    cur_collected = _fact_mrr_for_month(session, today.year, today.month)
    days_in_month = calendar.monthrange(today.year, today.month)[1]

    # --- доля корзины 90+ ---
    debt_90plus = 0.0
    orgs_debt = session.exec(
        select(Organization).where(
            _excl(),
            Organization.total_debt.is_not(None),  # type: ignore[union-attr]
            Organization.total_debt > 0,  # type: ignore[operator]
        )
    ).all()
    for o in orgs_debt:
        d = _f(o.total_debt)
        monthly = _f(o.monthly_ap) or 1
        if (d / monthly if monthly > 0 else 999) > 3:
            debt_90plus += d
    debt_90plus_share = round(debt_90plus / total_debt * 100, 1) if total_debt else 0.0
    collection_rate_fact = round(fact_mrr / plan_mrr * 100, 1) if plan_mrr else None
```

В возвращаемый словарь добавить ключи (существующие не убирать):

```python
        "current_month_label": f"{today.year}-{today.month:02d}",
        "current_month_collected": cur_collected,
        "days_passed": today.day,
        "days_in_month": days_in_month,
        "debt_90plus_amount": round(debt_90plus, 2),
        "debt_90plus_share": debt_90plus_share,
        "collection_rate_fact": collection_rate_fact,
```

- [ ] **Step 4: Запустить тесты dashboard целиком**

Run: `cd backend && python -m pytest tests/test_api_dashboard.py -v`
Expected: PASS (все)

- [ ] **Step 5: Коммит**

```bash
git add backend/app/api/v1/dashboard.py backend/tests/test_api_dashboard.py
git commit -m "feat(api): расширение dashboard/summary — текущий месяц, доля 90+"
```

---

## Task 7: GET /billing/segments — сегментация клиентов

**Files:**
- Modify: `backend/app/api/v1/billing.py`
- Test: `backend/tests/test_api_billing.py` (создать)

- [ ] **Step 1: Создать тестовый файл**

Создать `backend/tests/test_api_billing.py`:

```python
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api.v1.auth import get_current_user
from app.core.database import get_session
from app.main import app
from app.models import (
    Contract, Document, DocType, Organization, OrgStatus, User, UserRole,
)


@pytest.fixture
def client(db_session: Session):
    def override_get_session():
        yield db_session

    def override_get_current_user():
        return User(name="T", email="t@t.ru", hashed_password="x",
                    role=UserRole.ADMIN, is_active=True)

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_get_current_user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_segments_counts(client, db_session: Session):
    org = Organization(inn="7700000010", name_1c="Платит",
                        status=OrgStatus.ACTIVE, monthly_ap=Decimal("10000"),
                        in_registry=True, total_debt=Decimal("50000"))
    db_session.add(org)
    db_session.commit()
    resp = client.get("/api/v1/billing/segments")
    assert resp.status_code == 200
    body = resp.json()
    for key in ("total", "mrr_plan", "paying", "partial",
                "not_paying", "debtors"):
        assert key in body
    assert body["total"] == 1
    assert body["debtors"] == 1
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `cd backend && python -m pytest tests/test_api_billing.py -k segments -v`
Expected: FAIL (404)

- [ ] **Step 3: Реализовать эндпоинт**

В `backend/app/api/v1/billing.py` добавить импорты `from datetime import date`, `from app.models import Document, DocType` и эндпоинт:

```python
@router.get("/segments")
def segments(session: Session = Depends(get_session)):
    """Сегментация клиентов реестра по собираемости закрытого месяца."""
    today = date.today()
    prev_y, prev_m = ((today.year, today.month - 1) if today.month > 1
                      else (today.year - 1, 12))

    orgs = session.exec(
        select(Organization).where(
            Organization.excluded_from_analytics == False,  # noqa: E712
            Organization.in_registry == True,  # noqa: E712
        )
    ).all()
    org_ids = [o.id for o in orgs]

    paid_by_org: dict = {}
    if org_ids:
        rows = session.exec(
            select(Document.organization_id, func.sum(Document.amount))
            .where(
                Document.doc_type == DocType.PAYMENT,
                Document.organization_id.in_(org_ids),  # type: ignore[union-attr]
                func.extract("year", Document.doc_date) == prev_y,
                func.extract("month", Document.doc_date) == prev_m,
            )
            .group_by(Document.organization_id)
        ).all()
        paid_by_org = {oid: float(s or 0) for oid, s in rows}

    total = len(orgs)
    mrr_plan = sum(float(o.monthly_ap or 0) for o in orgs)
    paying = partial = not_paying = debtors = 0
    for o in orgs:
        plan = float(o.monthly_ap or 0)
        paid = paid_by_org.get(o.id, 0.0)
        ratio = (paid / plan * 100) if plan > 0 else 0
        if ratio >= 95:
            paying += 1
        elif ratio >= 1:
            partial += 1
        else:
            not_paying += 1
        if float(o.total_debt or 0) > 0:
            debtors += 1

    return {
        "total": total, "mrr_plan": round(mrr_plan, 2),
        "paying": paying, "partial": partial,
        "not_paying": not_paying, "debtors": debtors,
        "fact_month": f"{prev_y}-{prev_m:02d}",
    }
```

- [ ] **Step 4: Запустить — убедиться, что проходит**

Run: `cd backend && python -m pytest tests/test_api_billing.py -v`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add backend/app/api/v1/billing.py backend/tests/test_api_billing.py
git commit -m "feat(api): GET /billing/segments — сегментация клиентов"
```

---

## Task 8: Обогащение GET /billing/debtors aging-полями

**Files:**
- Modify: `backend/app/api/v1/billing.py`
- Test: `backend/tests/test_api_billing.py`

- [ ] **Step 1: Написать падающий тест**

Добавить в `test_api_billing.py`:

```python
def test_debtors_have_aging_fields(client, db_session: Session):
    org = Organization(inn="7700000020", name_1c="Должник",
                        status=OrgStatus.ACTIVE, monthly_ap=Decimal("10000"),
                        total_debt=Decimal("45000"))
    db_session.add(org)
    db_session.commit()
    resp = client.get("/api/v1/billing/debtors")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    row = rows[0]
    assert "months_overdue" in row
    assert "aging_bucket" in row
    assert row["aging_bucket"] == "90+"  # 45000 / 10000 = 4.5 > 3
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `cd backend && python -m pytest tests/test_api_billing.py -k aging -v`
Expected: FAIL (KeyError — полей нет)

- [ ] **Step 3: Изменить эндпоинт debtors**

В `billing.py` заменить тело `list_debtors`, чтобы возвращать словари с aging-полями:

```python
def _aging_bucket(months: float) -> str:
    if months <= 1:
        return "0-30"
    if months <= 2:
        return "31-60"
    if months <= 3:
        return "61-90"
    return "90+"


@router.get("/debtors")
def list_debtors(
    min_debt: float = Query(default=0, ge=0),
    session: Session = Depends(get_session),
):
    query = (
        select(Organization)
        .where(
            Organization.excluded_from_analytics == False,  # noqa: E712
            Organization.total_debt.is_not(None),  # type: ignore[union-attr]
            Organization.total_debt > min_debt,  # type: ignore[operator]
        )
        .order_by(Organization.total_debt.desc())  # type: ignore[union-attr]
    )
    debtors = session.exec(query).all()
    out = []
    for o in debtors:
        debt = float(o.total_debt or 0)
        monthly = float(o.monthly_ap or 0)
        months = debt / monthly if monthly > 0 else 999.0
        out.append({
            "id": str(o.id), "inn": o.inn,
            "name": o.name_display or o.name_1c,
            "monthly_ap": monthly or None,
            "total_debt": debt,
            "payment_score": o.payment_score,
            "status": o.status,
            "manager_id": str(o.manager_id) if o.manager_id else None,
            "months_overdue": round(months, 1) if monthly > 0 else None,
            "aging_bucket": _aging_bucket(months),
        })
    return out
```

- [ ] **Step 4: Запустить — убедиться, что проходит**

Run: `cd backend && python -m pytest tests/test_api_billing.py -v`
Expected: PASS

- [ ] **Step 5: Прогнать весь backend-набор**

Run: `cd backend && python -m pytest -q`
Expected: PASS — не меньше прежних 81 passed плюс новые тесты.

- [ ] **Step 6: Коммит**

```bash
git add backend/app/api/v1/billing.py backend/tests/test_api_billing.py
git commit -m "feat(api): обогащение /billing/debtors aging-полями"
```

---

## Task 9: Компонент KpiTile.vue

**Files:**
- Create: `frontend/src/components/KpiTile.vue`

- [ ] **Step 1: Создать компонент**

```vue
<script setup lang="ts">
defineProps<{
  label: string
  value: string
  sub?: string
  accent?: 'primary' | 'danger' | 'warn' | 'success' | 'neutral'
}>()
</script>

<template>
  <div class="kpi-tile" :class="accent || 'neutral'">
    <div class="kpi-label">{{ label }}</div>
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
}
.kpi-tile.primary { border-left-color: #6366f1; }
.kpi-tile.danger  { border-left-color: #ef4444; }
.kpi-tile.warn    { border-left-color: #f59e0b; }
.kpi-tile.success { border-left-color: #22c55e; }
.kpi-label {
  font-size: 0.72rem; color: #64748b;
  text-transform: uppercase; letter-spacing: 0.04em;
}
.kpi-value {
  font-size: 1.5rem; font-weight: 700; color: #1e293b;
  letter-spacing: -0.02em;
}
.kpi-sub { font-size: 0.78rem; color: #64748b; margin-top: auto; }
</style>
```

- [ ] **Step 2: Проверка типов**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: без ошибок по `KpiTile.vue`

- [ ] **Step 3: Коммит**

```bash
git add frontend/src/components/KpiTile.vue
git commit -m "feat(ui): компонент KpiTile"
```

---

## Task 10: Компонент SegmentBand.vue

**Files:**
- Create: `frontend/src/components/SegmentBand.vue`

Шапка-полоса: ряд числовых метрик + ряд кнопок-сегментов. Используется на Реестре и Должниках.

- [ ] **Step 1: Создать компонент**

```vue
<script setup lang="ts">
interface Metric { label: string; value: string }
interface Segment { key: string; label: string; count?: number }

defineProps<{
  metrics: Metric[]
  segments: Segment[]
  modelValue: string
}>()
defineEmits<{ 'update:modelValue': [value: string] }>()
</script>

<template>
  <div class="segment-band">
    <div class="metrics">
      <div class="metric" v-for="m in metrics" :key="m.label">
        <span class="m-value">{{ m.value }}</span>
        <span class="m-label">{{ m.label }}</span>
      </div>
    </div>
    <div class="segments">
      <button
        v-for="s in segments"
        :key="s.key"
        class="seg-btn"
        :class="{ active: modelValue === s.key }"
        @click="$emit('update:modelValue', s.key)"
      >
        {{ s.label }}
        <span class="seg-count" v-if="s.count != null">{{ s.count }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.segment-band {
  background: #fff; border: 1px solid #e2e8f0; border-radius: 8px;
  padding: 1rem 1.25rem; display: flex; flex-direction: column; gap: 0.85rem;
}
.metrics { display: flex; flex-wrap: wrap; gap: 1.75rem; }
.metric { display: flex; flex-direction: column; }
.m-value { font-size: 1.25rem; font-weight: 700; color: #1e293b; }
.m-label { font-size: 0.72rem; color: #64748b; text-transform: uppercase;
  letter-spacing: 0.04em; }
.segments { display: flex; flex-wrap: wrap; gap: 0.5rem; }
.seg-btn {
  border: 1px solid #cbd5e1; background: #f8fafc; border-radius: 6px;
  padding: 0.35rem 0.8rem; font-size: 0.85rem; cursor: pointer;
  color: #475569; display: inline-flex; align-items: center; gap: 0.4rem;
}
.seg-btn:hover { background: #f1f5f9; }
.seg-btn.active { background: #6366f1; border-color: #6366f1; color: #fff; }
.seg-count {
  background: rgba(0,0,0,0.08); border-radius: 10px;
  padding: 0 0.4rem; font-size: 0.75rem; font-weight: 600;
}
.seg-btn.active .seg-count { background: rgba(255,255,255,0.25); }
</style>
```

- [ ] **Step 2: Проверка типов**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: без новых ошибок

- [ ] **Step 3: Коммит**

```bash
git add frontend/src/components/SegmentBand.vue
git commit -m "feat(ui): компонент SegmentBand"
```

---

## Task 11: Компонент AttentionPanel.vue

**Files:**
- Create: `frontend/src/components/AttentionPanel.vue`

- [ ] **Step 1: Создать компонент**

```vue
<script setup lang="ts">
import { useRouter } from 'vue-router'

interface AttentionItem {
  type: string; label: string; route: string
  count: number; amount: number; weight: number
}
defineProps<{ items: AttentionItem[] }>()
const router = useRouter()

function fmtRub(v: number) {
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency', currency: 'RUB', maximumFractionDigits: 0,
  }).format(v)
}
function dotClass(weight: number) {
  return weight >= 3 ? 'crit' : weight === 2 ? 'warn' : 'info'
}
</script>

<template>
  <div class="attention">
    <div class="att-title">Требуют внимания</div>
    <div v-if="!items.length" class="att-empty">Открытых алертов нет.</div>
    <button
      v-for="it in items.slice(0, 5)"
      :key="it.type"
      class="att-row"
      @click="router.push(it.route)"
    >
      <span class="dot" :class="dotClass(it.weight)" />
      <span class="att-label">{{ it.label }}</span>
      <span class="att-count">{{ it.count }}</span>
      <span class="att-amount" v-if="it.amount > 0">{{ fmtRub(it.amount) }}</span>
      <span class="att-arrow">&rarr;</span>
    </button>
  </div>
</template>

<style scoped>
.attention {
  background: #fff; border: 1px solid #e2e8f0; border-radius: 8px;
  padding: 1rem 1.25rem;
}
.att-title { font-size: 0.95rem; font-weight: 600; color: #1e293b;
  margin-bottom: 0.6rem; }
.att-empty { color: #64748b; font-size: 0.85rem; padding: 0.5rem 0; }
.att-row {
  width: 100%; display: flex; align-items: center; gap: 0.75rem;
  padding: 0.55rem 0.4rem; border: none; background: none;
  border-bottom: 1px solid #f1f5f9; cursor: pointer; font-size: 0.9rem;
}
.att-row:hover { background: #f8fafc; }
.att-row:last-child { border-bottom: none; }
.dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
.dot.crit { background: #ef4444; }
.dot.warn { background: #f59e0b; }
.dot.info { background: #64748b; }
.att-label { color: #1e293b; }
.att-count {
  background: #f1f5f9; border-radius: 10px; padding: 0 0.5rem;
  font-size: 0.8rem; font-weight: 600; color: #475569;
}
.att-amount { color: #64748b; font-size: 0.85rem; }
.att-arrow { margin-left: auto; color: #94a3b8; }
</style>
```

- [ ] **Step 2: Проверка типов**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: без новых ошибок

- [ ] **Step 3: Коммит**

```bash
git add frontend/src/components/AttentionPanel.vue
git commit -m "feat(ui): компонент AttentionPanel"
```

---

## Task 12: Store — updateOrganization

**Files:**
- Modify: `frontend/src/stores/organizations.ts`

- [ ] **Step 1: Прочитать текущий store**

Прочитать `frontend/src/stores/organizations.ts` целиком — понять стиль (setup-store / options-store, импорт `api`).

- [ ] **Step 2: Добавить action**

Добавить функцию (адаптировать под стиль файла) и экспортировать её из `defineStore`:

```typescript
async function updateOrganization(inn: string, patch: Record<string, unknown>) {
  const res = await api.patch(`/organizations/${inn}`, patch)
  return res.data
}
```

- [ ] **Step 3: Проверка типов**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: без новых ошибок

- [ ] **Step 4: Коммит**

```bash
git add frontend/src/stores/organizations.ts
git commit -m "feat(ui): updateOrganization в store"
```

---

## Task 13: Переписать DashboardView.vue

**Files:**
- Modify: `frontend/src/views/DashboardView.vue`

Реализует раздел 5.1 спецификации. Один viewport: KPI-ряд (5 `KpiTile`), 2 графика, `AttentionPanel`. Шахматка удаляется.

- [ ] **Step 1: Переписать компонент**

`<script setup>`:
- Импорты: `KpiTile`, `AttentionPanel`, `VChart` + echarts (`BarChart`, `LineChart`, `GridComponent`, `TooltipComponent`, `LegendComponent`, `CanvasRenderer`), `api`, `useRouter`.
- `onMounted`: параллельно `GET /dashboard/summary`, `/dashboard/collection-trend`, `/dashboard/aging`, `/dashboard/attention`.
- Хелперы `fmtRub`, `fmt` — перенести из текущего файла.
- `collectionChartOption` (computed): `xAxis` категории = `label`; series bar `fact` (цвет по `ratio`: ≥95 `#22c55e`, ≥70 `#f59e0b`, иначе `#ef4444`), series line `plan` пунктиром `#94a3b8`.
- `agingChartOption` (computed): горизонтальные бары, `yAxis` категории в порядке `['90+','61-90','31-60','0-30']` (90+ сверху), цвета `{'90+':'#7f1d1d','61-90':'#ef4444','31-60':'#f59e0b','0-30':'#64748b'}`. Клик по бару → `router.push('/debtors?bucket=' + encodeURIComponent(bucket))`.

Шаблон:
- `.dash-header` — заголовок «Аналитика CEO» + подпись «факт за {summary.fact_month}».
- `.kpi-grid` (5 колонок) — 5 `<KpiTile>`:
  1. `label="MRR факт"` `value=fmtRub(summary.mrr_fact)` `sub="собрано {summary.collection_rate_fact}% от плана"` `accent="primary"`
  2. `label="MRR план"` `value=fmtRub(summary.mrr_plan)` `sub="база"` `accent="neutral"`
  3. `label="Сбор: {summary.current_month_label}"` `value=fmtRub(summary.current_month_collected)` `sub="{доля}% плана · день {days_passed}/{days_in_month}"` `accent="warn"`; долю считать `current_month_collected / mrr_plan * 100`.
  4. `label="Долг"` `value=fmtRub(summary.total_debt)` `sub="90+: {fmtRub(debt_90plus_amount)} ({debt_90plus_share}%)"` `accent="danger"`
  5. `label="Активные клиенты"` `value=fmt(summary.active_clients)` `sub="+{summary.new_30d} за 30 дней"` `accent="success"`
- `.charts-row` (grid 1fr 1fr): карточка «Сбор платежей — 2026» с `<v-chart :option="collectionChartOption">` или empty-state «Нет данных о платежах», если массив пуст; карточка «Структура долга» с aging-графиком.
- `<AttentionPanel :items="attention" />`.

CSS: переиспользовать `.dashboard`, `.dash-header`, `.charts-row`, `.chart-card`, `.chart-title` из текущего файла; `.kpi-grid` — `grid-template-columns: repeat(5, 1fr)` с media-запросами (`repeat(3,1fr)` ≤1200px, `repeat(2,1fr)` ≤700px). Удалить весь код шахматки (`matrix`, `matrixChartOption`, `HeatmapChart`, `VisualMapComponent`) и drawer aging (клик по aging теперь ведёт на `/debtors`).

- [ ] **Step 2: Проверка типов и сборка**

Run: `cd frontend && npx vue-tsc --noEmit && npm run build`
Expected: без ошибок, сборка успешна

- [ ] **Step 3: Коммит**

```bash
git add frontend/src/views/DashboardView.vue
git commit -m "feat(ui): редизайн Dashboard — KPI сбора, честные графики, панель внимания"
```

---

## Task 14: Переписать DebtorsView.vue

**Files:**
- Modify: `frontend/src/views/DebtorsView.vue`

Реализует раздел 5.4. Реестр должников: `SegmentBand` (метрики + фильтр по корзине), таблица с инлайн-сменой статуса.

- [ ] **Step 1: Переписать компонент**

`<script setup>`:
- Импорты: `SegmentBand`, `DataTable`, `Column`, `Tag`, `Select` (PrimeVue), `api`, `useRouter`, `useRoute`. Для уведомлений — см. Task 17 (если ToastService подключён, использовать `useToast`; иначе фолбэк).
- `onMounted`: `GET /billing/debtors`. Если `route.query.bucket` задан — выставить активный сегмент.
- `bucket` ref (`'all' | '0-30' | '31-60' | '61-90' | '90+'`), default `'all'` или из query.
- `filteredRows` computed — фильтр по `aging_bucket`.
- Метрики для `SegmentBand`: общий долг (`sum total_debt`), число должников, 90+ кол-во и сумма, средняя `months_overdue`.
- `segments`: `[{key:'all',label:'Все'}, {key:'0-30',...}, ...]` с `count` по корзине.
- `statusOptions = [{label:'Активен',value:'active'},{label:'Приостановлен',value:'suspended'},{label:'Отток',value:'churned'},{label:'Потенциальный',value:'prospect'}]`.
- `onStatusChange(row, newStatus)`: `api.patch('/organizations/' + row.inn, {status:newStatus})`, при успехе обновить `row.status` + уведомление; при ошибке — откат + уведомление.
- `openClient(inn)` → `router.push('/clients/' + inn)`.

Шаблон:
- Заголовок «Реестр должников».
- `<SegmentBand :metrics="..." :segments="..." v-model="bucket" />`.
- `<DataTable :value="filteredRows" sortField="total_debt" :sortOrder="-1" paginator :rows="25" stripedRows rowHover>` с колонками: Клиент (`name`, клик → карточка), ИНН, АП/мес (`fmtRub`), Долг (`<Tag severity="danger">`), Просрочка мес (`months_overdue`), Корзина (`aging_bucket`, `<Tag>` с цветом), Статус (`<Select>` с `@click.stop`, `@update:modelValue="v => onStatusChange(data, v)"`), Оценка (`payment_score`).
- Клик по строке вне `Select` → `openClient`.

- [ ] **Step 2: Проверка типов и сборка**

Run: `cd frontend && npx vue-tsc --noEmit && npm run build`
Expected: без ошибок

- [ ] **Step 3: Коммит**

```bash
git add frontend/src/views/DebtorsView.vue
git commit -m "feat(ui): редизайн Должников — реестр с aging-фильтром и сменой статуса"
```

---

## Task 15: BillingView — шапка сегментов + режим «Шахматка»

**Files:**
- Modify: `frontend/src/views/BillingView.vue`

Реализует раздел 5.2.

- [ ] **Step 1: Добавить сегментную шапку**

В `<script setup>`:
- Импорт `SegmentBand`.
- `segmentsData` ref, в `onMounted` догрузить `GET /billing/segments`.
- `activeSegment` ref `'all'`.
- Метрики для `SegmentBand`: всего (`total`), MRR (`fmtRub(mrr_plan)`).
- `segments`: `[{key:'all',label:'Все',count:total},{key:'paying',label:'Платят',count:paying},{key:'partial',label:'Частично',count:partial},{key:'not_paying',label:'Не платят',count:not_paying},{key:'debtors',label:'Должники',count:debtors}]`.
- Минимальная рабочая версия фильтрации: `activeSegment` влияет на режим «Таблица», для `debtors` фильтруя строки по `total_debt>0` (клиентская фильтрация загруженной страницы). Прочие сегменты остаются визуально активными. Не блокировать на серверной фильтрации — главное, чтобы шапка с числами отображалась.

В шаблоне добавить `<SegmentBand>` между `.billing-header` и таблицами.

- [ ] **Step 2: Добавить режим «Шахматка»**

- В `modeOptions` добавить `{ label: 'Шахматка', value: 'matrix' }`; тип `mode` расширить значением `'matrix'`.
- Перенести из старого `DashboardView.vue` логику heatmap: импорты `HeatmapChart`, `VisualMapComponent`, `VChart`; `matrix` ref; загрузку `GET /dashboard/payment-matrix?months=12` в `loadData` при `mode==='matrix'`; computed `matrixChartOption` и `matrixHeight`; обработчик `onMatrixClick` → переход в карточку клиента.
- В шаблоне добавить блок `v-else-if="mode === 'matrix'"` с `<v-chart>` либо empty-state.

- [ ] **Step 3: Проверка типов и сборка**

Run: `cd frontend && npx vue-tsc --noEmit && npm run build`
Expected: без ошибок

- [ ] **Step 4: Коммит**

```bash
git add frontend/src/views/BillingView.vue
git commit -m "feat(ui): Реестр — шапка сегментов и режим Шахматка"
```

---

## Task 16: Переписать ClientCardView.vue — редактируемая карточка

**Files:**
- Modify: `frontend/src/views/ClientCardView.vue`

Реализует раздел 5.3.

- [ ] **Step 1: Переписать компонент**

`<script setup>`:
- Импорты: `Tabs/TabList/Tab/TabPanels/TabPanel`, `DataTable`, `Column`, `Tag`, `VChart` + echarts (как сейчас), PrimeVue `InputText`, `InputNumber`, `Select`, `Checkbox`, `Textarea`, `DatePicker`, `Button`; `useOrganizationsStore`, `api`, `useRoute`.
- `onMounted`: параллельно `GET /organizations/{inn}`, `/snapshots`, `/contracts`, `/objects`, `/documents`, `/users/options`.
- `editMode` ref `false`; `form` ref — копия редактируемых полей `org`; `saving` ref.
- `statusOptions` (как в Task 14); `orgTypeOptions` — из enum `OrgType` (`TSN, OOO, AO, IP, KP, ZHK, SNT, NP, FL, Prochee`) с человекочитаемыми лейблами.
- `enterEdit()` — копировать поля `org` в `form`, `editMode=true`.
- `cancelEdit()` — `editMode=false`, сброс `form`.
- `save()` — собрать изменённые поля (сравнить `form` с `org`), `store.updateOrganization(inn, patch)`; при успехе обновить `org`, `editMode=false`, уведомление; при ошибке — уведомление, остаться в режиме.
- `changeStatus(newStatus)` — быстрый `updateOrganization(inn,{status:newStatus})`, доступен всегда.
- Read-only поля: `inn`, `name_1c`, `total_debt`, `payment_score`, `contract_1c_raw`, `active_doc_raw`.

Шаблон:
- Шапка: `name_display || name_1c`, ИНН, `<Select>` статуса (всегда активен, `@update:modelValue="changeStatus"`), инлайн-метрики (MRR план, долг, payment score). Кнопка «Редактировать»; в `editMode` — sticky-бар «Сохранить» (`:loading="saving"`) + «Отмена».
- Секции полей (раздел 5.3): *Реквизиты*, *Объект и система*, *Финансы*, *Заметки*, *Аналитика*. Каждое поле: в `editMode` — соответствующий инпут с `v-model="form.<field>"`; вне — текст. Read-only поля всегда текст (визуально серым).
- Вкладки: *История платежей* (`<DataTable :value="documents">` — дата, тип `<Tag>`, номер, сумма, период; сорт по дате убыв.), *Помесячно* (графики snapshots — сохранить из текущего файла), *Договоры*, *Объекты*.
- Маппинг типов документа: `{sale:'Реализация', payment:'Платёж', prepay_in:'Аванс получен', prepay_used:'Аванс зачтён'}`.

- [ ] **Step 2: Проверка типов и сборка**

Run: `cd frontend && npx vue-tsc --noEmit && npm run build`
Expected: без ошибок

- [ ] **Step 3: Коммит**

```bash
git add frontend/src/views/ClientCardView.vue
git commit -m "feat(ui): редизайн карточки клиента — редактируемый инструмент"
```

---

## Task 17: PrimeVue Toast (уведомления)

**Files:**
- Modify: `frontend/src/main.ts`, корневой layout (при необходимости)

- [ ] **Step 1: Проверить и подключить ToastService**

Прочитать `frontend/src/main.ts`. Если `ToastService` не подключён, а Tasks 14/16 используют уведомления — добавить:

```typescript
import ToastService from 'primevue/toastservice'
app.use(ToastService)
```

И один `<Toast />` в корневом layout-компоненте (`App.vue` или layout). Если решено не вводить ToastService — заменить уведомления в Tasks 14/16 на легковесный фолбэк и убрать связанные импорты. Главное — единообразие между Task 14 и Task 16.

- [ ] **Step 2: Проверка сборки**

Run: `cd frontend && npx vue-tsc --noEmit && npm run build`
Expected: без ошибок

- [ ] **Step 3: Коммит (если были изменения)**

```bash
git add frontend/src/main.ts frontend/src/App.vue
git commit -m "chore(ui): подключение ToastService"
```

---

## Task 18: Деплой и ручная проверка на production

**Files:**
- Modify: `agent_docs/development-history.md`, `agent_docs/backlog.md`

- [ ] **Step 1: Прогнать все backend-тесты**

Run: `cd backend && python -m pytest -q`
Expected: PASS, число passed ≥ прежних 81 + новые.

- [ ] **Step 2: Финальная сборка фронта**

Run: `cd frontend && npx vue-tsc --noEmit && npm run build`
Expected: без ошибок

- [ ] **Step 3: Деплой на VPS**

Согласно `agent_docs/guides/runbook.md`: запушить в `main`, на сервере `ssh ceo24`, в `/root/pass24-ceo-dashbord/` — `git pull`, `docker compose up -d --build`. Дождаться healthcheck. Деплой — операция на production; перед запуском подтвердить у пользователя.

- [ ] **Step 4: Ручная проверка в браузере**

Открыть `http://85.239.51.34`, войти. Проверить:
- Dashboard: 5 KPI заполнены, график сбора без пустых столбцов 2025, панель «Требуют внимания» кликабельна.
- Реестр: шапка сегментов с числами, режим «Шахматка» рисует heatmap.
- Должники: список отсортирован по долгу, фильтр по корзине работает, смена статуса в строке сохраняется (после перезагрузки сохранён).
- Карточка клиента: «Редактировать» → правка → «Сохранить» → значения сохранены; смена статуса из шапки; вкладка «История платежей» заполнена.
- Клик по aging-бару на дашборде открывает Должники с нужной корзиной.

- [ ] **Step 5: Запись в development-history и backlog**

Добавить запись в начало `agent_docs/development-history.md` (формат — как у предыдущих): дата 2026-05-15, что сделано, тесты, нюансы. В `agent_docs/backlog.md` добавить пункт «Разобрать аномалию марта 2026 (собираемость 127%) — вероятен задвоенный импорт платежей».

- [ ] **Step 6: Финальный коммит**

```bash
git add agent_docs/development-history.md agent_docs/backlog.md
git commit -m "docs: запись о редизайне рабочих экранов"
```

---

## Self-Review notes

- **Покрытие спеки:** разделы 4.1–4.8 → Tasks 1–8; 5.1 → Task 13; 5.2 → Task 15; 5.3 → Task 16; 5.4 → Task 14; общие компоненты → Tasks 9–12; обработка ошибок (раздел 6) → уведомления Tasks 14/16/17; тестирование (раздел 7) → Tasks 1–8 (pytest) + Task 18 (сборка + ручная проверка).
- **Аномалия марта 127%** — намеренно вне задач реализации; фиксируется в backlog в Task 18 Step 5.
- **Зависимости:** Tasks 13–16 зависят от Tasks 1–12. Backend (1–8) и компоненты (9–11) независимы — можно параллелить.
- **Согласованность типов:** `OrganizationUpdate` (Task 1) — поля совпадают с редактируемыми в Task 16; `aging_bucket`/`months_overdue` (Task 8) используются в Task 14; `collection-trend` поля `label/plan/fact/ratio` (Task 4) — в Task 13; `attention` поля `type/label/route/count/amount/weight` (Task 5) — в Task 11 `AttentionItem`.
