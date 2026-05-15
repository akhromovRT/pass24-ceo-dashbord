# P3.1 — Сверка платежей с банком: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development или superpowers:executing-plans для пошаговой реализации. Шаги — чекбоксы (`- [ ]`).

**Goal:** Дать руководителю и бухгалтеру инструмент сверки: какие банковские платежи не имеют соответствующей реализации из 1С, и какие реализации не оплачены.

**Architecture:** Импорт банковской выписки уже реализован (`source_type=bank` в `/import/upload`, платежи сохраняются как `Document` типа `PAYMENT` на синтетический «банковский договор» организации). Остаётся добавить **сервис сверки**, сопоставляющий PAYMENT-документы с SALE-документами по `(ИНН, период, сумма)`, эндпоинт для результата и вкладку «Сверка» в `ImportView`.

**Tech Stack:** Python 3.12, FastAPI, SQLModel / pytest. Vue 3 + TypeScript, PrimeVue.

**Уточнение scope относительно `agent_docs/backlog.md` P3.1:** на момент написания плана (2026-05-15) импорт банка уже подключён к UI (коммит `0eea2e5`). Поэтому из backlog-описания исключается «подключить парсер к UI» — остаётся только логика матчинга и экран сверки.

---

## File Structure

**Backend:**
- `backend/app/services/reconciliation.py` — новый: сервис сверки PAYMENT и SALE
- `backend/app/api/v1/reconciliation.py` — новый роутер `GET /reconciliation`
- `backend/app/main.py` — подключить роутер
- Тесты: `backend/tests/test_reconciliation.py` — новый

**Frontend:**
- `frontend/src/views/ImportView.vue` — добавить вкладку «Сверка»

---

## Task 1: Сервис сверки — модель результата и матчинг по периоду

**Files:**
- Create: `backend/app/services/reconciliation.py`
- Create: `backend/tests/test_reconciliation.py`

Логика матчинга: для каждой организации сгруппировать `Document` по `(period_year, period_month)`. Для пары (год, месяц) сравнить сумму PAYMENT и сумму SALE. Статус периода:
- `matched` — `abs(sum_payment - sum_sale) <= 1` рубля и оба > 0
- `payment_without_sale` — есть PAYMENT, нет SALE (платёж без реализации)
- `sale_without_payment` — есть SALE, нет PAYMENT (реализация не оплачена)
- `amount_mismatch` — оба > 0, но расходятся больше чем на 1 рубль

- [ ] **Step 1: Написать падающий тест**

Создать `backend/tests/test_reconciliation.py`:

```python
from datetime import date
from decimal import Decimal

from sqlmodel import Session

from app.models import Contract, Document, DocType, Organization, OrgStatus
from app.services.reconciliation import reconcile


def _org(session: Session, inn: str) -> Organization:
    org = Organization(inn=inn, name_1c="Орг", status=OrgStatus.ACTIVE)
    session.add(org)
    session.commit()
    session.refresh(org)
    contract = Contract(organization_id=org.id, raw_name="Д")
    session.add(contract)
    session.commit()
    session.refresh(contract)
    org._contract_id = contract.id
    return org


def _doc(session, org, doc_type, amount, py, pm):
    session.add(Document(
        contract_id=org._contract_id, organization_id=org.id,
        doc_type=doc_type, amount=Decimal(amount),
        doc_date=date(py, pm, 15), period_year=py, period_month=pm,
    ))
    session.commit()


def test_matched_period(db_session: Session):
    org = _org(db_session, "7700000100")
    _doc(db_session, org, DocType.SALE, 10000, 2026, 3)
    _doc(db_session, org, DocType.PAYMENT, 10000, 2026, 3)
    rows = reconcile(db_session)
    period = [r for r in rows if r["inn"] == "7700000100"][0]
    assert period["status"] == "matched"


def test_payment_without_sale(db_session: Session):
    org = _org(db_session, "7700000101")
    _doc(db_session, org, DocType.PAYMENT, 5000, 2026, 3)
    rows = reconcile(db_session)
    period = [r for r in rows if r["inn"] == "7700000101"][0]
    assert period["status"] == "payment_without_sale"


def test_sale_without_payment(db_session: Session):
    org = _org(db_session, "7700000102")
    _doc(db_session, org, DocType.SALE, 7000, 2026, 3)
    rows = reconcile(db_session)
    period = [r for r in rows if r["inn"] == "7700000102"][0]
    assert period["status"] == "sale_without_payment"


def test_amount_mismatch(db_session: Session):
    org = _org(db_session, "7700000103")
    _doc(db_session, org, DocType.SALE, 10000, 2026, 3)
    _doc(db_session, org, DocType.PAYMENT, 8000, 2026, 3)
    rows = reconcile(db_session)
    period = [r for r in rows if r["inn"] == "7700000103"][0]
    assert period["status"] == "amount_mismatch"
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `cd backend && python -m pytest tests/test_reconciliation.py -v`
Expected: FAIL (ModuleNotFoundError: app.services.reconciliation)

- [ ] **Step 3: Реализовать сервис**

Создать `backend/app/services/reconciliation.py`:

```python
"""Сверка платежей и реализаций по периодам.

Группирует Document по (period_year, period_month) для каждой организации
и сравнивает суммы PAYMENT и SALE. Документы без периода группируются
в отдельный ключ (None, None) — «период не определён»."""
from sqlmodel import Session, select

from app.models import Document, DocType, Organization

_TOLERANCE = 1.0  # рубль


def reconcile(session: Session) -> list[dict]:
    orgs = {o.id: o for o in session.exec(select(Organization)).all()}
    docs = session.exec(select(Document)).all()

    buckets: dict = {}
    for d in docs:
        key = (d.organization_id, d.period_year, d.period_month)
        b = buckets.setdefault(key, {"sale": 0.0, "payment": 0.0})
        if d.doc_type == DocType.SALE:
            b["sale"] += float(d.amount or 0)
        elif d.doc_type == DocType.PAYMENT:
            b["payment"] += float(d.amount or 0)

    out = []
    for (org_id, year, month), b in buckets.items():
        org = orgs.get(org_id)
        if org is None:
            continue
        sale, payment = b["sale"], b["payment"]
        if sale > 0 and payment > 0:
            status = ("matched" if abs(sale - payment) <= _TOLERANCE
                      else "amount_mismatch")
        elif payment > 0:
            status = "payment_without_sale"
        elif sale > 0:
            status = "sale_without_payment"
        else:
            continue
        out.append({
            "org_id": str(org_id),
            "inn": org.inn,
            "name": org.name_display or org.name_1c,
            "period_year": year,
            "period_month": month,
            "sale": round(sale, 2),
            "payment": round(payment, 2),
            "diff": round(payment - sale, 2),
            "status": status,
        })
    out.sort(key=lambda r: (r["status"] != "amount_mismatch", -abs(r["diff"])))
    return out
```

- [ ] **Step 4: Запустить — убедиться, что проходит**

Run: `cd backend && python -m pytest tests/test_reconciliation.py -v`
Expected: PASS (4 теста)

- [ ] **Step 5: Коммит**

```bash
git add backend/app/services/reconciliation.py backend/tests/test_reconciliation.py
git commit -m "feat(reconciliation): сервис сверки платежей и реализаций"
```

---

## Task 2: Эндпоинт GET /reconciliation

**Files:**
- Create: `backend/app/api/v1/reconciliation.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_reconciliation.py`

- [ ] **Step 1: Написать падающий тест**

Добавить в `test_reconciliation.py` фикстуру `client` (скопировать из `tests/test_api_dashboard.py`) и тесты:

```python
def test_reconciliation_endpoint(client, db_session: Session):
    org = _org(db_session, "7700000110")
    _doc(db_session, org, DocType.PAYMENT, 5000, 2026, 3)
    resp = client.get("/api/v1/reconciliation")
    assert resp.status_code == 200
    rows = resp.json()
    assert any(r["inn"] == "7700000110" for r in rows)


def test_reconciliation_filter_status(client, db_session: Session):
    org = _org(db_session, "7700000111")
    _doc(db_session, org, DocType.PAYMENT, 5000, 2026, 4)
    resp = client.get("/api/v1/reconciliation?status=payment_without_sale")
    assert resp.status_code == 200
    rows = resp.json()
    assert all(r["status"] == "payment_without_sale" for r in rows)
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `cd backend && python -m pytest tests/test_reconciliation.py -k endpoint -v`
Expected: FAIL (404)

- [ ] **Step 3: Создать роутер и подключить**

Создать `backend/app/api/v1/reconciliation.py`:

```python
from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.api.v1.auth import get_current_user
from app.core.database import get_session
from app.services.reconciliation import reconcile

router = APIRouter(
    prefix="/reconciliation",
    tags=["reconciliation"],
    dependencies=[Depends(get_current_user)],
)


@router.get("")
def get_reconciliation(
    status: str | None = Query(default=None),
    session: Session = Depends(get_session),
):
    rows = reconcile(session)
    if status:
        rows = [r for r in rows if r["status"] == status]
    return rows
```

В `backend/app/main.py` добавить импорт и `app.include_router(...)` по образцу остальных роутеров (с префиксом `/api/v1`).

- [ ] **Step 4: Запустить — убедиться, что проходит**

Run: `cd backend && python -m pytest tests/test_reconciliation.py -v`
Expected: PASS (все 6)

- [ ] **Step 5: Коммит**

```bash
git add backend/app/api/v1/reconciliation.py backend/app/main.py backend/tests/test_reconciliation.py
git commit -m "feat(api): GET /reconciliation — эндпоинт сверки"
```

---

## Task 3: Вкладка «Сверка» в ImportView.vue

**Files:**
- Modify: `frontend/src/views/ImportView.vue`

- [ ] **Step 1: Прочитать текущий ImportView**

Прочитать `frontend/src/views/ImportView.vue` целиком — понять структуру (есть ли `Tabs`, как устроена история импортов).

- [ ] **Step 2: Добавить вкладку «Сверка»**

- Если в файле уже есть `Tabs` — добавить новый `Tab` «Сверка»; иначе обернуть существующий контент и новую вкладку в `Tabs/TabList/TabPanels`.
- `<script setup>`: ref `reconRows`, ref `reconStatus` (`'all' | 'payment_without_sale' | 'sale_without_payment' | 'amount_mismatch'`), функция `loadRecon()` — запрос `GET /reconciliation` (при `reconStatus !== 'all'` передавать `?status=`).
- Загружать при первом открытии вкладки.
- Таблица (`DataTable`): колонки Клиент (`name`), ИНН, Период (`{period_month}/{period_year}` или «—»), Реализация (`sale`, `fmtRub`), Платёж (`payment`, `fmtRub`), Расхождение (`diff`, `fmtRub`, цвет красный при `diff != 0`), Статус (`<Tag>` с маппингом лейблов).
- Маппинг статусов: `{matched:'Сверено', payment_without_sale:'Платёж без реализации', sale_without_payment:'Не оплачено', amount_mismatch:'Расхождение сумм'}`; severity тега: `matched`→success, `amount_mismatch`→danger, остальное→warn.
- Фильтр по статусу — `SelectButton` или кнопки над таблицей.
- Клик по строке — переход `router.push('/clients/' + row.inn)`.

- [ ] **Step 3: Проверка типов и сборка**

Run: `cd frontend && npx vue-tsc --noEmit && npm run build`
Expected: без ошибок

- [ ] **Step 4: Коммит**

```bash
git add frontend/src/views/ImportView.vue
git commit -m "feat(ui): вкладка Сверка в ImportView"
```

---

## Task 4: Деплой и проверка

**Files:**
- Modify: `agent_docs/development-history.md`, `agent_docs/backlog.md`

- [ ] **Step 1: Все backend-тесты**

Run: `cd backend && python -m pytest -q`
Expected: PASS

- [ ] **Step 2: Сборка фронта**

Run: `cd frontend && npx vue-tsc --noEmit && npm run build`
Expected: без ошибок

- [ ] **Step 3: Деплой**

По `agent_docs/guides/runbook.md`. Деплой на production — подтвердить у пользователя перед запуском.

- [ ] **Step 4: Ручная проверка**

Открыть `/import`, вкладка «Сверка»: таблица заполнена, фильтр по статусу работает, клик ведёт в карточку клиента.

- [ ] **Step 5: Документация**

Запись в `agent_docs/development-history.md`; в `agent_docs/backlog.md` отметить P3.1 как выполненный.

- [ ] **Step 6: Коммит**

```bash
git add agent_docs/development-history.md agent_docs/backlog.md
git commit -m "docs: P3.1 сверка платежей завершена"
```

---

## Self-Review notes

- **Покрытие:** сервис матчинга — Task 1; эндпоинт — Task 2; UI «Сверка» — Task 3; деплой/доки — Task 4.
- **Согласованность типов:** поля строки результата (`org_id, inn, name, period_year, period_month, sale, payment, diff, status`) определены в Task 1 и используются без изменений в Task 2 (фильтр по `status`) и Task 3 (колонки таблицы).
- **Известное ограничение:** матчинг идёт по агрегату периода `(ИНН, год, месяц)`, не по отдельным счетам. Платежи без распознанного периода группируются в бакет «период не определён» и видны в таблице как пустой период.
- **Алерт `payment_without_document`** из backlog не реализуется отдельной задачей: статус `payment_without_sale` в таблице сверки выполняет эту функцию визуально. Автогенерацию `Alert` можно добавить позже (зависит от P3.4).
