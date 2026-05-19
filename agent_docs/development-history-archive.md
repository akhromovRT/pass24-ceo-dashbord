# Архив истории разработки

Записи, вытесненные из `development-history.md` по правилу «последние 10».
Читать при необходимости.

## Записи

### 2026-03-04 — Инициализация проекта

**Что сделано:**
- Изучена спецификация CEO24 v1.0 (12 разделов, модель данных, API, дорожная карта)
- Проанализированы 3 реальных файла-источника: задолженность покупателей (1593 строки, 243 покупателя), банковская выписка (35 строк за 1 день), аналитика поступлений (5 листов, 1780 детальных платежей)
- Выбран подход: классический монолит FastAPI + Vue 3 + PrimeVue + PostgreSQL
- Скоуп: MVP (6 недель) — парсер 1С, API, реестр клиентов, просрочки, базовый дашборд
- Заполнены проектные файлы: AGENTS.md, architecture.md, adr.md (5 решений), README.md
- Создан дизайн-документ: `docs/plans/2026-03-04-ceo24-mvp-design.md`

**Ключевые решения:** ADR-001..005 (монолит, SQLModel, иммутабельные снапшоты, три источника данных, расширенная модель organizations)

**Следующий шаг:** Создание implementation plan, scaffold проекта

### 2026-03-04 — Scaffold backend (Tasks 1-3)

**Что сделано:**
- Создан implementation plan: `docs/plans/2026-03-04-ceo24-mvp-implementation.md` (25 задач, 6 фаз)
- Task 1: Backend scaffold — pyproject.toml (hatchling), FastAPI app с CORS и /health, pydantic-settings конфиг, SQLModel database module
- Task 2: Docker Compose (postgres:16-alpine + backend) и Dockerfile. Docker не установлен на машине — файлы готовы к использованию
- Task 3: SQLModel модели — Organization (15+ полей, OrgType/OrgStatus enum), Contract (автоклассификация, ContractType enum), Document (DocType enum, denormalized org FK). 8 unit-тестов

**Окружение:**
- Python 3.12.12 через `uv` (venv в `backend/.venv`)
- Docker отсутствует на машине — для тестов используется SQLite in-memory
- Git-репозиторий инициализирован

**Ключевые решения:** ADR-006 (uv вместо pip для управления зависимостями)

**Следующий шаг:** Tasks 4-5 (остальные модели + Alembic миграции)

### 2026-03-05 — Phase 1 завершена (Tasks 4-5)

**Что сделано:**
- Task 4: Модели MonthlySnapshot (UniqueConstraint по 4 полям, иммутабельные снапшоты), ImportRun (JSON-поля errors/delta_summary через SQLAlchemy Column(JSON)), User (3 роли: admin/manager/viewer), Alert (9 типов алертов, 3 severity, 4 статуса). 11 новых тестов
- Task 5: Alembic инициализирован (1.18.4), env.py настроен на SQLModel.metadata + settings.DATABASE_URL. Миграция `2347cbabe6c7_initial_schema` сгенерирована через SQLite (Docker не установлен). Проверены upgrade/downgrade. 7 таблиц создаются корректно
- .gitignore дополнен правилом `*.db`

**Тесты:** 19/19 passed (8 старых + 11 новых)

**Файловая структура (новое):**
```
backend/app/models/
├── snapshot.py      # MonthlySnapshot
├── import_run.py    # ImportRun + ImportStatus
├── user.py          # User + UserRole
└── alert.py         # Alert + AlertType + AlertSeverity + AlertStatus
backend/alembic/
├── env.py           # Настроен на SQLModel.metadata
└── versions/
    └── 2347cbabe6c7_initial_schema.py
```

**Следующий шаг:** Phase 2 — Tasks 6-10 (парсеры 1С + импорт-сервис)

### 2026-03-06 — Phase 2 завершена (Tasks 6-10)

**Что сделано:**
- Task 6: Contract classifier — keyword-цепочка (подписка → оборудование → сервис → сумма ≥100K → other). 10 тестов
- Task 7: Hierarchy detection — detect_level() для 3-уровневой иерархии 1С. Расширен для edge-cases: "Допсоглашение", "ДОГОВОР МОНТАЖА", "Счет-оферта", номера без "Договор" префикса. 9 тестов
- Task 8: Full debt parser — parse_debt_report() парсит реальный файл 1С (1584 строки → 243 покупателя, 258 контрактов, 1036 документов). SHA-256 хеш, период, nested dataclasses. 5 интеграционных тестов
- Task 9: Bank statement parser — extract_payment_info() с regex для счёта, договора, периода (месяц+год), тарифа. parse_bank_statement() парсит XLSX выписку (26 платежей). 14 тестов
- Task 10: Import service — ImportService.process_import() сохраняет ParseResult в БД: find-or-create Organization по ИНН, classify + create Contract, create Document. Очистка имён (_ДИАДОК, _СБИС). Алерт для новых клиентов. Идемпотентность. 7 тестов на SQLite in-memory

**Тесты:** 64/64 passed

**Файловая структура (новое):**
```
backend/app/parser/
├── __init__.py
├── classifier.py       # classify_contract() → ClassificationResult
├── debt_report.py      # detect_level(), parse_debt_report() → ParseResult
└── bank_statement.py   # extract_payment_info(), parse_bank_statement()
backend/app/services/
├── __init__.py
└── import_service.py   # ImportService.process_import()
backend/tests/
├── conftest.py          # db_session fixture (SQLite in-memory)
├── test_classifier.py   # 10 тестов
├── test_debt_parser.py  # 14 тестов
├── test_bank_parser.py  # 14 тестов
└── test_import_service.py # 7 тестов
```

**Следующий шаг:** Phase 3 — Tasks 11-13 (JWT auth, Organizations API, Dashboard/Billing/Import/Alerts API)

### 2026-03-06 — Phase 3 завершена (Tasks 11-13)

**Что сделано:**
- Task 11: JWT auth — bcrypt (заменён passlib из-за несовместимости), jose JWT HS256, OAuth2PasswordBearer, get_current_user dependency. 3 теста
- Task 12: Organizations API — GET /organizations (pagination, search ilike по name/INN, filter by status/manager), GET /{inn}, /{inn}/snapshots, /{inn}/contracts. 7 API-тестов через TestClient
- Task 13: Dashboard API (summary: MRR/ARR/debt/clients/alerts, mrr-trend, aging buckets), Billing API (debtors sorted by debt), Import API (POST upload + duplicate check by hash, GET runs), Alerts API (list + PATCH status)
- conftest.py обновлён: StaticPool + check_same_thread=False для корректной работы SQLite с TestClient
- pyproject.toml: passlib[bcrypt] заменён на bcrypt>=4.2

**Тесты:** 74/74 passed

**API endpoints:**
```
POST /api/v1/auth/login
GET  /api/v1/organizations(?search,status,manager_id,page,page_size)
GET  /api/v1/organizations/{inn}
GET  /api/v1/organizations/{inn}/snapshots
GET  /api/v1/organizations/{inn}/contracts
GET  /api/v1/dashboard/summary
GET  /api/v1/dashboard/mrr-trend
GET  /api/v1/dashboard/aging
GET  /api/v1/billing/debtors(?min_debt)
POST /api/v1/import/upload
GET  /api/v1/import/runs
GET  /api/v1/alerts(?status)
PATCH /api/v1/alerts/{alert_id}
```

**Следующий шаг:** Phase 4 — Tasks 14-17 (Vue 3 SPA frontend)

### 2026-03-06 — Phase 4 завершена (Tasks 14-17)

**Что сделано:**
- Task 14: Vue 3 + Vite + TypeScript scaffold. PrimeVue 4 (Aura theme), Pinia + persistedstate, vue-echarts, axios, vue-router. Vite proxy /api → localhost:8000. Auth store (login/logout/token). Router с navigation guard
- Task 15: LoginView — PrimeVue InputText + Password + Button, error handling, redirect
- Task 16: BillingView — DataTable с pagination, search (debounced 300ms), columns: клиент, ИНН, АП/мес, долг (Tag color-coded), payment_score (ProgressBar), статус, объекты, город. Row click → client card
- Task 17: ClientCardView — 3 API-вызова через Promise.all, Tabs (PrimeVue 4 Tabs/TabList/Tab/TabPanels/TabPanel), 4 вкладки: инфо, договоры, история оплат, графики (vue-echarts bar + line)
- Placeholder views: DashboardView, DebtorsView, ImportView

**Тесты:** 74/74 backend passed. Frontend builds successfully

**Файловая структура:**
```
frontend/src/
├── main.ts              # PrimeVue + Pinia + Router setup
├── router.ts            # 6 routes + auth guard
├── style.css            # Base styles
├── api/client.ts        # Axios + Bearer token interceptor
├── stores/
│   ├── auth.ts          # login/logout/isAuthenticated
│   └── organizations.ts # fetch with search/pagination
└── views/
    ├── LoginView.vue
    ├── BillingView.vue
    ├── ClientCardView.vue
    ├── DashboardView.vue    (placeholder)
    ├── DebtorsView.vue      (placeholder)
    └── ImportView.vue       (placeholder)
```

**Следующий шаг:** Phase 5 — Tasks 18-19 (Payment Score + DebtorsView)
