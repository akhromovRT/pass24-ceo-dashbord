# Import Manual Payment Period — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить двухфазный импорт для bank и payments источников, чтобы пользователь вручную указывал период для платежей, у которых он не распознан автоматически.

**Architecture:** Превью парсит файл и возвращает список платежей без периода с file_hash; БД не затрагивается. Коммит принимает файл повторно плюс period_overrides_json (JSON-строка в form-поле), сверяет file_hash, применяет оверрайды к PaymentInfo перед записью — Document.period_manual=True для таких строк. AllocationService читает этот флаг и ставит ручной период в приоритет над regex. Существующий /import/upload остаётся нетронутым для debt/registry.

**Tech Stack:** FastAPI, SQLModel, Alembic (PostgreSQL), openpyxl, Vue 3 + TypeScript, PrimeVue 4

---

## Файловая карта

| Файл | Действие | Ответственность |
|---|---|---|
| `backend/app/parser/period_extraction.py` | Modify | Добавить `_DOT_RE` для формата `MM.YYYYГ` |
| `backend/app/parser/bank_statement.py` | Modify | `period_manual: bool = False` в `PaymentInfo` |
| `backend/app/models/document.py` | Modify | Колонка `period_manual: bool` |
| `backend/alembic/versions/a2e7c3b1d0f5_add_period_manual.py` | Create | Миграция ADD COLUMN |
| `backend/app/services/import_service.py` | Modify | Параметр `period_overrides`, запись `period_manual` в Document |
| `backend/app/services/allocation_service.py` | Modify | Приоритет `period_manual` над regex |
| `backend/app/api/v1/imports.py` | Modify | Эндпоинты `/import/preview` и `/import/commit` |
| `backend/tests/test_period_extraction.py` | Modify | Тест `MM.YYYYГ` формата |
| `backend/tests/test_bank_import_service.py` | Modify | Тесты period_manual в Document |
| `backend/tests/test_allocation_service.py` | Modify | Тест приоритета period_manual |
| `backend/tests/test_api_import_preview.py` | Create | API-тесты preview и commit |
| `frontend/src/views/ImportView.vue` | Modify | Двухфазный поток плюс шаг ревью |

---

## Task 1: Фикс парсера периодов — формат MM.YYYY

**Files:**
- Modify: `backend/app/parser/period_extraction.py`
- Modify: `backend/tests/test_period_extraction.py`

- [ ] **Step 1.1: Написать падающий тест**

Открыть `backend/tests/test_period_extraction.py`, добавить в конец файла:

```python
def test_dot_format_period():
    """ЗА 05.2026Г — формат с точкой, встречается в реальных выписках."""
    r = extract_periods(
        'ОПЛАТА ПО СЧЁТУ № БП-546 ОТ 20.04.2026 ЗА ДОСТУП НА МЕСЯЦ К СИСТЕМЕ "PASS24.ONLINE" ТАРИФ БИЗНЕС ЗА 05.2026Г.',
        date(2026, 5, 6),
    )
    assert (2026, 5) in r.periods


def test_dot_format_not_match_ddmmyyyy():
    """Дата 20.04.2026 внутри фразы не должна давать ложный период."""
    r = extract_periods("ОТ 20.04.2026 ГОДА без явного периода", date(2026, 5, 6))
    # 04 окружён точками с обеих сторон — lookbehind/lookahead блокируют
    assert (2026, 4) not in r.periods


def test_dot_format_not_match_contract_number():
    """Дата 05.04.2024 в тексте не даёт 04/2024 через dot-regexp."""
    r = extract_periods(
        "ОПЛАТА ЗА УСЛУГИ ПО СЧЕТУ NБП-604 ОТ 20.04.2026 ПО ДОГОВОРУ N10239-/04/2024",
        date(2026, 5, 6),
    )
    assert (2024, 4) not in r.periods
```

- [ ] **Step 1.2: Запустить — убедиться что падает**

```bash
cd backend && .venv/bin/pytest tests/test_period_extraction.py::test_dot_format_period -v
```

Ожидаем: `FAILED` — `(2026, 5)` не найден в `r.periods`.

- [ ] **Step 1.3: Добавить `_DOT_RE` в парсер**

Открыть `backend/app/parser/period_extraction.py`.

После строки с `_SLASH_RE = re.compile(...)` (строка примерно 15) добавить:

```python
# Формат "MM.YYYY" с точкой: "ЗА 05.2026Г"
# Lookbehind (?<![\d/\-.]) — не матчим внутри "20.04.2026" (перед 04 стоит точка)
# Lookahead (?![\d/.]) — не матчим внутри цепочек дат
_DOT_RE = re.compile(r"(?<![\d/\-.])(\d{1,2})\s*\.\s*(20\d{2})(?![\d/.])")
```

В теле функции `extract_periods`, сразу после блока slash-формата, добавить:

```python
    # Точечный формат "05.2026" / "05.2026Г"
    for m in _DOT_RE.finditer(text):
        month, year = int(m.group(1)), int(m.group(2))
        if _valid(year, month):
            found.add((year, month))
```

- [ ] **Step 1.4: Запустить все тесты парсера**

```bash
cd backend && .venv/bin/pytest tests/test_period_extraction.py -v
```

Ожидаем: все тесты `PASSED`.

- [ ] **Step 1.5: Убедиться что общий suite не сломался**

```bash
cd backend && .venv/bin/pytest -q --ignore=tests/test_bank_parser.py
```

Ожидаем: 155 passed или больше, 0 failed.

- [ ] **Step 1.6: Commit**

```bash
git add backend/app/parser/period_extraction.py backend/tests/test_period_extraction.py
git commit -m "fix(parser): распознавать формат MM.YYYY с точкой в назначении платежа"
```

---

## Task 2: period_manual в PaymentInfo и Document плюс миграция

**Files:**
- Modify: `backend/app/parser/bank_statement.py`
- Modify: `backend/app/models/document.py`
- Create: `backend/alembic/versions/a2e7c3b1d0f5_add_period_manual.py`

- [ ] **Step 2.1: Добавить поле period_manual в PaymentInfo**

Открыть `backend/app/parser/bank_statement.py`.

В dataclass `PaymentInfo` добавить поле после `payment_kind`:

```python
@dataclass
class PaymentInfo:
    invoice_number: str | None = None
    contract_number: str | None = None
    period_month: int | None = None
    period_year: int | None = None
    tariff: str | None = None
    periods: list = field(default_factory=list)
    coverage_months: int | None = None
    payment_kind: str = "subscription"
    period_manual: bool = False
```

- [ ] **Step 2.2: Добавить колонку period_manual в модель Document**

Открыть `backend/app/models/document.py`.

Добавить поле после `raw_name`:

```python
class Document(SQLModel, table=True):
    __tablename__ = "documents"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    contract_id: uuid.UUID = Field(foreign_key="contracts.id", index=True)
    organization_id: uuid.UUID = Field(foreign_key="organizations.id", index=True)
    doc_type: DocType
    doc_number: str | None = None
    doc_date: date | None = None
    amount: Decimal = Field(max_digits=12, decimal_places=2)
    period_year: int | None = None
    period_month: int | None = None
    import_run_id: uuid.UUID | None = Field(default=None, foreign_key="import_runs.id")
    raw_name: str | None = None
    period_manual: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

- [ ] **Step 2.3: Создать файл миграции**

Создать `backend/alembic/versions/a2e7c3b1d0f5_add_period_manual.py`:

```python
"""add period_manual to documents

Revision ID: a2e7c3b1d0f5
Revises: f811cf0c2c38
Create Date: 2026-05-19 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a2e7c3b1d0f5'
down_revision: Union[str, Sequence[str], None] = 'f811cf0c2c38'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'documents',
        sa.Column('period_manual', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    )


def downgrade() -> None:
    op.drop_column('documents', 'period_manual')
```

- [ ] **Step 2.4: Проверить что тесты проходят**

SQLite в тестах создаёт таблицы через SQLModel metadata — новое поле подхватится автоматически, миграция для тестов не нужна.

```bash
cd backend && .venv/bin/pytest -q --ignore=tests/test_bank_parser.py
```

Ожидаем: 155+ passed, 0 failed.

- [ ] **Step 2.5: Commit**

```bash
git add backend/app/parser/bank_statement.py backend/app/models/document.py \
  backend/alembic/versions/a2e7c3b1d0f5_add_period_manual.py
git commit -m "feat(model): period_manual в PaymentInfo и Document плюс миграция"
```

---

## Task 3: ImportService — применение оверрайдов и запись period_manual

**Files:**
- Modify: `backend/app/services/import_service.py`
- Modify: `backend/tests/test_bank_import_service.py`

- [ ] **Step 3.1: Написать падающие тесты**

Открыть `backend/tests/test_bank_import_service.py`, добавить в конец класса `TestBankImport`:

```python
    def test_period_override_sets_period_manual_true(self, db_session: Session):
        """Оверрайд периода → Document.period_manual=True, period_year/month по оверрайду."""
        payment = ParsedPayment(
            date=date(2026, 5, 18),
            doc_number="542",
            amount=Decimal("12387.38"),
            counterparty='ООО "Агростройкомплекс"',
            inn="5024039775",
            description="Доступ на месяц 2026г. к системе PASS24.online",
            payment_info=PaymentInfo(),
        )
        result = _make_result([payment])

        svc = ImportService(db_session)
        svc.process_bank_import(
            result,
            file_hash="xyz",
            period_overrides={0: (2026, 5)},
        )

        docs = db_session.exec(select(Document)).all()
        assert len(docs) == 1
        assert docs[0].period_manual is True
        assert docs[0].period_year == 2026
        assert docs[0].period_month == 5

    def test_no_override_period_manual_false(self, db_session: Session):
        """Без оверрайда Document.period_manual остаётся False."""
        payment = _make_payment(date(2026, 5, 6), 12387.38, "X", "5024039775")
        result = _make_result([payment])

        svc = ImportService(db_session)
        svc.process_bank_import(result, file_hash="qqq")

        docs = db_session.exec(select(Document)).all()
        assert docs[0].period_manual is False
```

- [ ] **Step 3.2: Запустить — убедиться что падают**

```bash
cd backend && .venv/bin/pytest tests/test_bank_import_service.py::TestBankImport::test_period_override_sets_period_manual_true -v
```

Ожидаем: `FAILED` — `period_overrides` не принимается или `period_manual` не проставлен.

- [ ] **Step 3.3: Обновить process_bank_import**

Открыть `backend/app/services/import_service.py`.

**Изменение 1 — сигнатура метода** (добавить параметр `period_overrides`):

```python
    def process_bank_import(
        self,
        bank_result: BankStatementResult,
        file_hash: str,
        synthetic_contract: str = _BANK_SYNTH_CONTRACT_NUMBER,
        source_label: str = "bank_statement",
        period_overrides: dict[int, tuple[int, int]] | None = None,
    ) -> ImportRun:
```

**Изменение 2 — замена цикла** `for p in bank_result.payments:` на:

```python
        for idx, p in enumerate(bank_result.payments):
            # Применить ручной оверрайд периода
            if period_overrides and idx in period_overrides:
                year, month = period_overrides[idx]
                if p.payment_info is None:
                    from app.parser.bank_statement import PaymentInfo as PI
                    p.payment_info = PI()
                p.payment_info.period_year = year
                p.payment_info.period_month = month
                p.payment_info.periods = [(year, month)]
                p.payment_info.period_manual = True

            inn = _normalize_inn(p.inn)
```

**Изменение 3 — добавить period_manual** в создание Document (найти блок `doc = Document(`):

```python
            doc = Document(
                contract_id=contract.id,
                organization_id=org.id,
                doc_type=DocType.PAYMENT,
                doc_number=p.doc_number or None,
                doc_date=p.date,
                amount=p.amount,
                period_year=p.payment_info.period_year if p.payment_info else None,
                period_month=p.payment_info.period_month if p.payment_info else None,
                period_manual=p.payment_info.period_manual if p.payment_info else False,
                import_run_id=import_run.id,
                raw_name=(p.description or "")[:500],
            )
```

**Изменение 4 — process_payments_report** добавить параметр `period_overrides`:

```python
    def process_payments_report(
        self, result: BankStatementResult, file_hash: str,
        period_overrides: dict[int, tuple[int, int]] | None = None,
    ) -> ImportRun:
        """Импорт реестра «Оплата от покупателей» из 1С."""
        return self.process_bank_import(
            result, file_hash,
            synthetic_contract=_PAYMENTS_SYNTH_CONTRACT_NUMBER,
            source_label="payments_report",
            period_overrides=period_overrides,
        )
```

- [ ] **Step 3.4: Запустить тесты import service**

```bash
cd backend && .venv/bin/pytest tests/test_bank_import_service.py -v
```

Ожидаем: 11 passed (9 старых + 2 новых).

- [ ] **Step 3.5: Полный suite**

```bash
cd backend && .venv/bin/pytest -q --ignore=tests/test_bank_parser.py
```

Ожидаем: 157+ passed, 0 failed.

- [ ] **Step 3.6: Commit**

```bash
git add backend/app/services/import_service.py backend/tests/test_bank_import_service.py
git commit -m "feat(import): period_overrides в process_bank_import, period_manual в Document"
```

---

## Task 4: AllocationService — приоритет period_manual

**Files:**
- Modify: `backend/app/services/allocation_service.py`
- Modify: `backend/tests/test_allocation_service.py`

- [ ] **Step 4.1: Написать падающий тест**

Открыть `backend/tests/test_allocation_service.py`, добавить в конец файла:

```python
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

    allocs = db_session.exec(select(PaymentAllocation)).all()
    assert len(allocs) == 1
    assert allocs[0].monthly_charge_id == charge_may.id
    assert allocs[0].basis == AllocationBasis.EXPLICIT_PERIOD
```

- [ ] **Step 4.2: Запустить — убедиться что падает**

```bash
cd backend && .venv/bin/pytest tests/test_allocation_service.py::test_period_manual_overrides_regex_extraction -v
```

Ожидаем: `FAILED` — платёж попадёт на 3/2026 (из raw_name) вместо 5/2026.

- [ ] **Step 4.3: Обновить recompute_for_organization**

Открыть `backend/app/services/allocation_service.py`.

В методе `recompute_for_organization`, в блоке `for payment in payments:`, сразу после строки `ep = extract_periods(payment.raw_name or "", ...)` добавить:

```python
            ep = extract_periods(payment.raw_name or "",
                                 payment.doc_date or date.today())

            # Ручной ввод приоритетнее regex-результата
            if payment.period_manual and payment.period_year and payment.period_month:
                ep.periods = [(payment.period_year, payment.period_month)]

            # 1. явные периоды из назначения
```

- [ ] **Step 4.4: Запустить тесты allocation service**

```bash
cd backend && .venv/bin/pytest tests/test_allocation_service.py -v
```

Ожидаем: все тесты `PASSED`.

- [ ] **Step 4.5: Полный suite**

```bash
cd backend && .venv/bin/pytest -q --ignore=tests/test_bank_parser.py
```

Ожидаем: 158+ passed, 0 failed.

- [ ] **Step 4.6: Commit**

```bash
git add backend/app/services/allocation_service.py backend/tests/test_allocation_service.py
git commit -m "feat(ledger): period_manual=True имеет приоритет над regex в AllocationService"
```

---

## Task 5: Backend API — /import/preview и /import/commit

**Files:**
- Modify: `backend/app/api/v1/imports.py`
- Create: `backend/tests/test_api_import_preview.py`

- [ ] **Step 5.1: Написать тесты API**

Создать `backend/tests/test_api_import_preview.py`:

```python
"""Тесты /import/preview и /import/commit."""
import hashlib
import io
import json
from datetime import UTC, datetime
from decimal import Decimal

import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.api.v1.auth import get_current_user
from app.core.database import get_session
from app.main import app
from app.models import Document, ImportRun, ImportStatus, Organization, User, UserRole


@pytest.fixture
def client(db_session: Session):
    def override_session():
        yield db_session

    def override_user():
        return User(name="T", email="t@t.ru", hashed_password="x",
                    role=UserRole.ADMIN, is_active=True)

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = override_user
    yield TestClient(app)
    app.dependency_overrides.clear()


def _make_bank_xlsx(rows: list[dict]) -> bytes:
    """Минимальный xlsx в формате банк-выписки."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.cell(1, 1, "Выписка по счёту"); ws.cell(1, 2, "40702")
    ws.cell(2, 1, "За период"); ws.cell(2, 2, "01.05.2026 - 18.05.2026")
    ws.cell(3, 1, "Владелец счёта"); ws.cell(3, 2, "ОНВИ Сервис")
    ws.cell(8, 1, "Дата"); ws.cell(8, 2, "Номер"); ws.cell(8, 4, "Кредит")
    ws.cell(8, 5, "Контрагент"); ws.cell(8, 6, "ИНН"); ws.cell(8, 11, "Назначение")
    for i, r in enumerate(rows, start=10):
        ws.cell(i, 1, r["date"])
        ws.cell(i, 2, r["doc_number"])
        ws.cell(i, 4, r["amount"])
        ws.cell(i, 5, r["counterparty"])
        ws.cell(i, 6, r["inn"])
        ws.cell(i, 11, r.get("description", ""))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _xlsx_file(content: bytes, name: str = "test.xlsx"):
    return ("file", (name, content,
                     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))


# Платёж БЕЗ периода в назначении
_NO_PERIOD_ROW = {
    "date": "18.05.2026", "doc_number": "542", "amount": 12387.38,
    "counterparty": 'ООО "Агростройкомплекс"', "inn": "5024039775",
    "description": "Доступ на месяц 2026г. к системе PASS24.online",
}
# Платёж С периодом в назначении
_WITH_PERIOD_ROW = {
    "date": "15.05.2026", "doc_number": "692", "amount": 12387.38,
    "counterparty": "ТСН ОРДЖОНИКИДЗЕ 1", "inn": "9725054546",
    "description": "ОПЛАТА ЗА ДОСТУП К СИСТЕМЕ PASS24.ONLINE STANDART МАЙ 2026 ГОДА",
}


class TestPreview:
    def test_preview_returns_payments_without_period(self, client):
        content = _make_bank_xlsx([_NO_PERIOD_ROW])
        resp = client.post(
            "/api/v1/import/preview?source_type=bank",
            files=[_xlsx_file(content)],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["total_payments"] == 1
        assert data["summary"]["without_period"] == 1
        assert len(data["payments"]) == 1
        p = data["payments"][0]
        assert p["index"] == 0
        assert p["detected_period"] is None
        assert p["inn"] == "5024039775"

    def test_preview_skips_payments_with_period(self, client):
        content = _make_bank_xlsx([_NO_PERIOD_ROW, _WITH_PERIOD_ROW])
        resp = client.post(
            "/api/v1/import/preview?source_type=bank",
            files=[_xlsx_file(content)],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["total_payments"] == 2
        assert data["summary"]["without_period"] == 1
        assert len(data["payments"]) == 1
        assert data["payments"][0]["index"] == 0

    def test_preview_returns_file_hash(self, client):
        content = _make_bank_xlsx([_NO_PERIOD_ROW])
        resp = client.post(
            "/api/v1/import/preview?source_type=bank",
            files=[_xlsx_file(content)],
        )
        data = resp.json()
        assert "file_hash" in data
        assert len(data["file_hash"]) == 64  # sha256 hex

    def test_preview_does_not_write_to_db(self, client, db_session: Session):
        content = _make_bank_xlsx([_NO_PERIOD_ROW])
        client.post(
            "/api/v1/import/preview?source_type=bank",
            files=[_xlsx_file(content)],
        )
        assert db_session.exec(select(ImportRun)).first() is None
        assert db_session.exec(select(Organization)).first() is None

    def test_preview_409_on_already_imported(self, client, db_session: Session):
        content = _make_bank_xlsx([_NO_PERIOD_ROW])
        file_hash = hashlib.sha256(content).hexdigest()
        run = ImportRun(filename="test.xlsx", file_hash=file_hash,
                        status=ImportStatus.COMPLETED,
                        completed_at=datetime.now(UTC))
        db_session.add(run)
        db_session.commit()

        resp = client.post(
            "/api/v1/import/preview?source_type=bank",
            files=[_xlsx_file(content)],
        )
        assert resp.status_code == 409


class TestCommit:
    def test_commit_writes_to_db(self, client, db_session: Session):
        content = _make_bank_xlsx([_NO_PERIOD_ROW])
        file_hash = hashlib.sha256(content).hexdigest()

        resp = client.post(
            "/api/v1/import/commit?source_type=bank",
            files=[_xlsx_file(content)],
            data={"file_hash": file_hash, "period_overrides_json": "{}"},
        )
        assert resp.status_code == 200
        assert db_session.exec(select(ImportRun)).first() is not None

    def test_commit_applies_period_override(self, client, db_session: Session):
        content = _make_bank_xlsx([_NO_PERIOD_ROW])
        file_hash = hashlib.sha256(content).hexdigest()
        overrides = json.dumps({"0": {"year": 2026, "month": 5}})

        resp = client.post(
            "/api/v1/import/commit?source_type=bank",
            files=[_xlsx_file(content)],
            data={"file_hash": file_hash, "period_overrides_json": overrides},
        )
        assert resp.status_code == 200

        docs = db_session.exec(select(Document)).all()
        assert len(docs) == 1
        assert docs[0].period_manual is True
        assert docs[0].period_year == 2026
        assert docs[0].period_month == 5

    def test_commit_400_on_hash_mismatch(self, client):
        content = _make_bank_xlsx([_NO_PERIOD_ROW])

        resp = client.post(
            "/api/v1/import/commit?source_type=bank",
            files=[_xlsx_file(content)],
            data={"file_hash": "wrong_hash_aaaaaa", "period_overrides_json": "{}"},
        )
        assert resp.status_code == 400
```

- [ ] **Step 5.2: Запустить — убедиться что падают**

```bash
cd backend && .venv/bin/pytest tests/test_api_import_preview.py -v
```

Ожидаем: `FAILED` — эндпоинты ещё не реализованы.

- [ ] **Step 5.3: Реализовать эндпоинты в imports.py**

Открыть `backend/app/api/v1/imports.py`.

Добавить в блок импортов:

```python
import json
from fastapi import Form
```

После существующего роутера `/upload` добавить два новых эндпоинта:

```python
@router.post("/preview")
def preview_import(
    file: UploadFile,
    source_type: Literal["bank", "payments"] = Query(default="bank"),
    session: Session = Depends(get_session),
):
    """Фаза 1: парсим файл, в БД не пишем, возвращаем платежи без периода."""
    if source_type not in ("bank", "payments"):
        raise HTTPException(status_code=400, detail="source_type must be bank or payments")
    if not file.filename or not file.filename.endswith((".xls", ".xlsx")):
        raise HTTPException(status_code=400, detail="Only .xls/.xlsx files accepted")

    content = file.file.read()
    file_hash = hashlib.sha256(content).hexdigest()

    existing = session.exec(
        select(ImportRun).where(ImportRun.file_hash == file_hash)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="File already imported")

    with tempfile.NamedTemporaryFile(suffix=Path(file.filename).suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        if source_type == "bank":
            result = parse_bank_statement(tmp_path)
        else:
            result = parse_payments_report(tmp_path)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Parse error: {e}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    payments_without_period = []
    total_amount = 0.0
    for idx, p in enumerate(result.payments):
        total_amount += float(p.amount)
        if p.payment_info and p.payment_info.periods:
            detected = {
                "year": p.payment_info.periods[0][0],
                "month": p.payment_info.periods[0][1],
            }
        else:
            detected = None
        if detected is None:
            payments_without_period.append({
                "index": idx,
                "date": str(p.date),
                "amount": float(p.amount),
                "counterparty": p.counterparty,
                "inn": p.inn,
                "description": p.description,
                "detected_period": None,
            })

    return {
        "file_hash": file_hash,
        "source_type": source_type,
        "summary": {
            "total_payments": len(result.payments),
            "total_amount": round(total_amount, 2),
            "without_period": len(payments_without_period),
        },
        "payments": payments_without_period,
    }


@router.post("/commit")
def commit_import(
    file: UploadFile,
    source_type: Literal["bank", "payments"] = Query(default="bank"),
    file_hash: str = Form(...),
    period_overrides_json: str = Form(default="{}"),
    session: Session = Depends(get_session),
):
    """Фаза 2: re-парсим файл, сверяем hash, применяем оверрайды, пишем в БД."""
    if source_type not in ("bank", "payments"):
        raise HTTPException(status_code=400, detail="source_type must be bank or payments")
    if not file.filename or not file.filename.endswith((".xls", ".xlsx")):
        raise HTTPException(status_code=400, detail="Only .xls/.xlsx files accepted")

    content = file.file.read()
    actual_hash = hashlib.sha256(content).hexdigest()
    if actual_hash != file_hash:
        raise HTTPException(status_code=400, detail="file_hash mismatch — файл изменился")

    existing = session.exec(
        select(ImportRun).where(ImportRun.file_hash == actual_hash)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="File already imported")

    overrides: dict[int, tuple[int, int]] = {}
    try:
        raw = json.loads(period_overrides_json or "{}")
        for k, v in raw.items():
            idx = int(k)
            year, month = int(v["year"]), int(v["month"])
            if not (1 <= month <= 12 and 2010 <= year <= 2035):
                raise HTTPException(status_code=422, detail=f"Invalid period at index {k}")
            overrides[idx] = (year, month)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid period_overrides_json: {exc}")

    with tempfile.NamedTemporaryFile(suffix=Path(file.filename).suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    svc = ImportService(session)
    try:
        if source_type == "bank":
            try:
                bank_result = parse_bank_statement(tmp_path)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=f"Parse error: {e}")
            bank_result.filename = file.filename
            import_run = svc.process_bank_import(
                bank_result, file_hash=actual_hash, period_overrides=overrides
            )
        else:
            try:
                pay_result = parse_payments_report(tmp_path)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=f"Parse error: {e}")
            pay_result.filename = file.filename
            import_run = svc.process_payments_report(
                pay_result, file_hash=actual_hash, period_overrides=overrides
            )
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return import_run
```

- [ ] **Step 5.4: Запустить API тесты**

```bash
cd backend && .venv/bin/pytest tests/test_api_import_preview.py -v
```

Ожидаем: все тесты `PASSED`.

- [ ] **Step 5.5: Полный suite**

```bash
cd backend && .venv/bin/pytest -q --ignore=tests/test_bank_parser.py
```

Ожидаем: 165+ passed, 0 failed.

- [ ] **Step 5.6: Commit**

```bash
git add backend/app/api/v1/imports.py backend/app/services/import_service.py \
  backend/tests/test_api_import_preview.py
git commit -m "feat(api): /import/preview и /import/commit для двухфазного импорта"
```

---

## Task 6: Frontend — двухфазный импорт в ImportView.vue

**Files:**
- Modify: `frontend/src/views/ImportView.vue`

- [ ] **Step 6.1: Заменить содержимое ImportView.vue**

Открыть `frontend/src/views/ImportView.vue` и полностью заменить содержимое:

```vue
<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import FileUpload from 'primevue/fileupload'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Tag from 'primevue/tag'
import Message from 'primevue/message'
import Select from 'primevue/select'
import DatePicker from 'primevue/datepicker'
import Button from 'primevue/button'
import api from '../api/client'

const SOURCE_TYPES = [
  {
    value: 'debt',
    label: 'Задолженность покупателей (1С)',
    hint: 'Полный отчёт из 1С: организации, договоры, реализации, оплаты, остатки.',
  },
  {
    value: 'bank',
    label: 'Банковская выписка',
    hint: 'Платежи как Document(type=PAYMENT). Новые ИНН → PROSPECT-карточки.',
  },
  {
    value: 'registry',
    label: 'Клиентская база (реестр)',
    hint: 'Проставляет «В реестре = Да», переносит договор/доп.документ/объекты.',
  },
  {
    value: 'payments',
    label: 'Оплата от покупателей (1С)',
    hint: 'Полная история платежей из 1С — источник для AR-леджера.',
  },
]

type Phase = 'idle' | 'review' | 'done'

const runs = ref<any[]>([])
const uploadResult = ref<any>(null)
const uploadError = ref('')
const loading = ref(false)
const sourceType = ref<'debt' | 'bank' | 'registry' | 'payments'>('debt')

const phase = ref<Phase>('idle')
const previewData = ref<any>(null)
const selectedFile = ref<File | null>(null)
// overrides[paymentIndex] = Date выбранная в DatePicker (mode=month)
const overrides = ref<Record<number, Date | null>>({})

const isPreviewSource = computed(
  () => sourceType.value === 'bank' || sourceType.value === 'payments'
)

async function loadRuns() {
  const res = await api.get('/import/runs')
  runs.value = res.data
}

onMounted(loadRuns)

async function onUpload(event: any) {
  uploadResult.value = null
  uploadError.value = ''
  loading.value = true
  const file: File = event.files[0]
  if (isPreviewSource.value) {
    await doPreview(file)
  } else {
    await doDirectUpload(file)
  }
  loading.value = false
}

async function doDirectUpload(file: File) {
  const formData = new FormData()
  formData.append('file', file)
  try {
    const res = await api.post(`/import/upload?source_type=${sourceType.value}`, formData)
    uploadResult.value = res.data
    phase.value = 'done'
    await loadRuns()
  } catch (e: any) {
    uploadError.value = e.response?.data?.detail || 'Ошибка загрузки'
  }
}

async function doPreview(file: File) {
  selectedFile.value = file
  overrides.value = {}
  const formData = new FormData()
  formData.append('file', file)
  try {
    const res = await api.post(`/import/preview?source_type=${sourceType.value}`, formData)
    previewData.value = res.data
    if (res.data.summary.without_period === 0) {
      await doCommit()
    } else {
      phase.value = 'review'
    }
  } catch (e: any) {
    uploadError.value = e.response?.data?.detail || 'Ошибка при анализе файла'
  }
}

async function doCommit() {
  if (!selectedFile.value || !previewData.value) return
  loading.value = true
  uploadError.value = ''

  const overridesObj: Record<string, { year: number; month: number }> = {}
  for (const [idxStr, dateVal] of Object.entries(overrides.value)) {
    if (dateVal) {
      overridesObj[idxStr] = {
        year: (dateVal as Date).getFullYear(),
        month: (dateVal as Date).getMonth() + 1,
      }
    }
  }

  const formData = new FormData()
  formData.append('file', selectedFile.value)
  formData.append('file_hash', previewData.value.file_hash)
  formData.append('period_overrides_json', JSON.stringify(overridesObj))

  try {
    const res = await api.post(`/import/commit?source_type=${sourceType.value}`, formData)
    uploadResult.value = res.data
    phase.value = 'done'
    await loadRuns()
  } catch (e: any) {
    uploadError.value = e.response?.data?.detail || 'Ошибка при импорте'
  } finally {
    loading.value = false
  }
}

function cancelReview() {
  phase.value = 'idle'
  previewData.value = null
  selectedFile.value = null
  overrides.value = {}
  uploadError.value = ''
}

function resetForm() {
  phase.value = 'idle'
  previewData.value = null
  selectedFile.value = null
  overrides.value = {}
  uploadResult.value = null
  uploadError.value = ''
}

function statusSeverity(status: string): 'success' | 'danger' | 'warn' | 'info' | undefined {
  switch (status) {
    case 'completed': return 'success'
    case 'failed': return 'danger'
    case 'processing': return 'warn'
    default: return 'info'
  }
}

function formatDate(dt: string) {
  if (!dt) return '—'
  return new Date(dt).toLocaleString('ru-RU')
}

function sourceFromRun(run: any): string {
  const ds = run?.delta_summary
  if (ds?.source === 'bank_statement') return 'Банк'
  if (ds?.source === 'registry') return 'Реестр'
  if (ds?.source === 'payments_report') return 'Оплаты'
  return '1С (задолженность)'
}

function sourceSeverity(label: string): 'info' | 'success' | 'warn' {
  if (label === 'Банк') return 'success'
  if (label === 'Реестр') return 'warn'
  return 'info'
}
</script>

<template>
  <div class="import-view">
    <h1>Импорт данных</h1>

    <!-- Форма загрузки — скрыта на шаге ревью -->
    <div v-if="phase !== 'review'" class="upload-controls">
      <div class="control">
        <label>Тип файла</label>
        <Select
          v-model="sourceType"
          :options="SOURCE_TYPES"
          option-label="label"
          option-value="value"
          style="width: 360px"
          @change="resetForm"
        />
        <div class="hint">
          {{ SOURCE_TYPES.find(s => s.value === sourceType)?.hint }}
        </div>
      </div>

      <div class="control">
        <label>Файл</label>
        <FileUpload
          mode="basic"
          accept=".xls,.xlsx"
          :maxFileSize="10000000"
          chooseLabel="Выбрать .xls / .xlsx"
          :auto="true"
          customUpload
          @uploader="onUpload"
          :disabled="loading"
        />
        <div v-if="loading" class="hint">Анализируем файл…</div>
      </div>
    </div>

    <Message v-if="uploadError" severity="error" :closable="true" @close="uploadError = ''">
      {{ uploadError }}
    </Message>

    <!-- Результат успешного импорта -->
    <div v-if="uploadResult && phase === 'done'" class="upload-result">
      <Message severity="success" :closable="false">
        Импорт завершён: {{ uploadResult.buyers_count }} организаций,
        {{ uploadResult.contracts_count }} контрактов,
        {{ uploadResult.documents_count }} документов.
        Новых: {{ uploadResult.new_buyers || 0 }}.
      </Message>
      <Button label="Загрузить ещё файл" severity="secondary" @click="resetForm" class="mt-2" />
    </div>

    <!-- Шаг ревью: платежи без периода -->
    <div v-if="phase === 'review' && previewData" class="review-block">
      <div class="review-header">
        <h2>Укажите период для {{ previewData.summary.without_period }} платежей</h2>
        <p class="review-hint">
          Комбобоксы можно оставить пустыми — такие платежи импортируются без периода, как раньше.
        </p>
      </div>

      <DataTable :value="previewData.payments" class="review-table" stripedRows>
        <Column field="date" header="Дата" style="width: 110px" />
        <Column field="counterparty" header="Контрагент">
          <template #body="{ data }">{{ (data.counterparty as string).slice(0, 45) }}</template>
        </Column>
        <Column field="amount" header="Сумма" style="width: 120px">
          <template #body="{ data }">
            {{ (data.amount as number).toLocaleString('ru-RU') }} ₽
          </template>
        </Column>
        <Column field="description" header="Назначение">
          <template #body="{ data }">
            <span class="description-cell">{{ data.description }}</span>
          </template>
        </Column>
        <Column header="Период" style="width: 165px">
          <template #body="{ data }">
            <DatePicker
              v-model="overrides[data.index]"
              view="month"
              dateFormat="mm/yy"
              placeholder="мм/гг"
              :showIcon="false"
              :minDate="new Date(2020, 0, 1)"
              :maxDate="new Date(2027, 11, 31)"
              style="width: 145px"
            />
          </template>
        </Column>
      </DataTable>

      <div class="review-actions">
        <Button
          label="Подтвердить импорт"
          @click="doCommit"
          :loading="loading"
        />
        <Button
          label="Отмена"
          severity="secondary"
          @click="cancelReview"
          :disabled="loading"
        />
      </div>
    </div>

    <h3>История импортов</h3>
    <DataTable :value="runs" stripedRows>
      <Column field="filename" header="Файл" />
      <Column header="Источник" style="width: 130px">
        <template #body="{ data }">
          <Tag :severity="sourceSeverity(sourceFromRun(data))">{{ sourceFromRun(data) }}</Tag>
        </template>
      </Column>
      <Column header="Период">
        <template #body="{ data }">
          {{ data.period_start || '—' }} — {{ data.period_end || '—' }}
        </template>
      </Column>
      <Column field="status" header="Статус" style="width: 120px">
        <template #body="{ data }">
          <Tag :severity="statusSeverity(data.status)">{{ data.status }}</Tag>
        </template>
      </Column>
      <Column field="buyers_count" header="Организации" style="width: 120px" />
      <Column field="contracts_count" header="Договоры" style="width: 110px" />
      <Column field="documents_count" header="Документы" style="width: 110px" />
      <Column field="new_buyers" header="Новых" style="width: 90px" />
      <Column header="Дата" style="width: 180px">
        <template #body="{ data }">{{ formatDate(data.started_at) }}</template>
      </Column>
    </DataTable>
  </div>
</template>

<style scoped>
.import-view { padding: 1.5rem; }
.import-view h1 { font-size: 1.5rem; color: #1e293b; margin: 0 0 1.5rem; }
.import-view h2 { font-size: 1.1rem; color: #1e293b; margin: 0 0 0.25rem; }
.import-view h3 { font-size: 1rem; color: #374151; margin: 1.5rem 0 0.75rem; }

.upload-controls {
  display: flex; gap: 1.5rem; align-items: flex-start;
  margin-bottom: 1rem; padding: 1rem;
  background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px;
  flex-wrap: wrap;
}
.control { display: flex; flex-direction: column; gap: 0.25rem; }
.control label {
  font-size: 0.75rem; color: #64748b;
  text-transform: uppercase; letter-spacing: 0.04em;
}
.hint { font-size: 0.8rem; color: #64748b; margin-top: 0.25rem; max-width: 360px; }
.upload-result { margin-bottom: 1rem; }

.review-block {
  margin-bottom: 1.5rem; border: 1px solid #e2e8f0;
  border-radius: 8px; padding: 1.25rem; background: #fffbeb;
}
.review-header { margin-bottom: 1rem; }
.review-hint { font-size: 0.85rem; color: #64748b; margin: 0; }
.review-table { margin-bottom: 1rem; }
.description-cell {
  font-size: 0.8rem; color: #475569;
  display: -webkit-box; -webkit-line-clamp: 2;
  -webkit-box-orient: vertical; overflow: hidden;
}
.review-actions { display: flex; gap: 0.75rem; }
.mt-2 { margin-top: 0.5rem; }
</style>
```

- [ ] **Step 6.2: Проверить TypeScript**

```bash
cd frontend && npm run type-check
```

Ожидаем: 0 errors. Если `DatePicker` не найден в типах, добавить в `vite.config.ts` или проверить версию PrimeVue (`^4.x` — DatePicker введён в 4.0 вместо Calendar).

- [ ] **Step 6.3: Проверить сборку**

```bash
cd frontend && npm run build
```

Ожидаем: сборка завершается без ошибок.

- [ ] **Step 6.4: Commit**

```bash
git add frontend/src/views/ImportView.vue
git commit -m "feat(ui): двухфазный импорт — шаг ревью с выбором периода для bank/payments"
```

---

## Task 7: Deploy на production

Сервер: `ceo.pass24pro.ru`, SSH-алиас `ceo24`, compose-директория `/root/pass24-ceo-dashbord/`.

- [ ] **Step 7.1: Сделать бэкап БД**

```bash
ssh ceo24 '/usr/local/bin/ceo24-backup.sh'
```

- [ ] **Step 7.2: Залить код**

```bash
git push origin main
ssh ceo24 'cd /root/pass24-ceo-dashbord && git pull'
```

- [ ] **Step 7.3: Применить миграцию**

```bash
ssh ceo24 'cd /root/pass24-ceo-dashbord && \
  docker compose exec backend alembic upgrade head'
```

Ожидаем последней строкой: `Running upgrade f811cf0c2c38 -> a2e7c3b1d0f5, add period_manual to documents`.

Проверить:

```bash
ssh ceo24 'cd /root/pass24-ceo-dashbord && docker compose exec backend alembic current'
```

Вывод должен содержать `a2e7c3b1d0f5 (head)`.

- [ ] **Step 7.4: Пересобрать и перезапустить**

```bash
ssh ceo24 'cd /root/pass24-ceo-dashbord && \
  docker compose build backend frontend && \
  docker compose up -d backend frontend'
```

- [ ] **Step 7.5: Проверить статус**

```bash
ssh ceo24 'cd /root/pass24-ceo-dashbord && docker compose ps'
```

Все три сервиса — `Up (healthy)`.

- [ ] **Step 7.6: Ручная проверка в браузере**

1. Открыть `https://ceo.pass24pro.ru` → войти.
2. Перейти в «Импорт».
3. Выбрать «Банковская выписка», загрузить `Выписка_40702810002630000347_01.05.2026–18.05.2026.xlsx`.
4. Должен появиться шаг ревью. Проверить: у НОРБИТ (93 786 ₽) период должен теперь определяться автоматически как `05/2026` (фикс парсера из Task 1) — значит в таблице его не будет. Если платежей без периода стало 6 вместо 7 — парсер работает.
5. Заполнить периоды для оставшихся → «Подтвердить импорт» → зелёное сообщение.
6. Повторная загрузка того же файла → ошибка 409 — корректное поведение.

---

## Spec Coverage Check

| Требование спека | Task |
|---|---|
| Двухфазный импорт preview → commit | Task 5 |
| preview не пишет в БД | Task 5 (test_preview_does_not_write_to_db) |
| commit сверяет file_hash | Task 5 (test_commit_400_on_hash_mismatch) |
| period_manual в PaymentInfo | Task 2 |
| period_manual колонка в Document | Task 2 |
| Миграция Alembic up/down | Task 2 |
| ImportService применяет оверрайды | Task 3 |
| AllocationService приоритет period_manual | Task 4 |
| Фикс MM.YYYY в period_extraction | Task 1 |
| Frontend шаг ревью с DatePicker | Task 6 |
| Без периода — прямой commit | Task 6 (without_period === 0) |
| Заполнение необязательное | Task 6 (пустые оверрайды не попадают) |
| debt/registry не затронуты | Task 5 (используют /import/upload) |
| process_payments_report получает overrides | Task 3 (Step 3.3 изменение 4) |
| Deploy с миграцией | Task 7 |
