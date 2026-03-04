# CEO24 MVP Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a management analytics system that replaces manual Excel analysis of 1C data with an automated web dashboard for billing, debtors, and CEO overview.

**Architecture:** Python FastAPI monolith with PostgreSQL, Vue 3 SPA frontend. Data flows: 1C XLS/XLSX files -> Python parsers -> PostgreSQL -> REST API -> Vue 3 + PrimeVue UI. Immutable snapshots for auditability.

**Tech Stack:** Python 3.12, FastAPI, SQLModel, Alembic, PostgreSQL 16, openpyxl, xlrd | Vue 3, TypeScript, PrimeVue, vue-echarts, Pinia | Docker, nginx

**Reference docs:**
- Design: `docs/plans/2026-03-04-ceo24-mvp-design.md`
- Architecture: `agent_docs/architecture.md`
- ADRs: `agent_docs/adr.md`
- Spec (full): `~/Downloads/_Spreadsheets/CEO24_Спецификация_системы.docx`

**Sample data:**
- Debt report: `~/Downloads/_Spreadsheets/Задолженность покупателей за Январь 2026 г. - Февраль 2026 г. ООО  ОНВИ СЕРВИС v.2 на 02.03.2026 г..xls.xlsx`
- Bank statement: `~/Downloads/Выписка_40702810002630000347_03.03.2026.xlsx`
- Analytics: `~/Library/Mobile Documents/com~apple~CloudDocs/ClaudeCode/Аналитика поступлений/Аналитика_поступлений_2025_2026.xlsx`

---

## Phase 1: Project Scaffold and Database (Week 1, Days 1-2)

### Task 1: Initialize backend project

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/app/core/__init__.py`
- Create: `backend/app/core/config.py`
- Create: `backend/app/core/database.py`

**Step 1: Create backend directory and pyproject.toml**

Dependencies: fastapi, uvicorn[standard], sqlmodel, alembic, psycopg[binary], python-jose[cryptography], passlib[bcrypt], python-multipart, openpyxl, xlrd, pydantic-settings. Dev deps: pytest, pytest-asyncio, httpx, ruff.

**Step 2: Create config module**

Settings via pydantic-settings: DATABASE_URL, SECRET_KEY, ACCESS_TOKEN_EXPIRE_MINUTES (480), IMPORT_INBOX_DIR, env_file=".env".

**Step 3: Create database module**

SQLModel engine from settings.DATABASE_URL, get_session generator for dependency injection, create_db_and_tables function.

**Step 4: Create FastAPI app**

FastAPI app with CORS middleware (allow localhost:5173), /health endpoint returning status ok.

**Step 5: Create .env.example**

Template with DATABASE_URL, SECRET_KEY, IMPORT_INBOX_DIR.

**Step 6: Verify it starts**

Run: `cd backend && pip install -e ".[dev]" && uvicorn app.main:app --reload`
Expected: Server starts, /health returns ok

**Step 7: Commit**

`feat: initialize backend project with FastAPI scaffold`

---

### Task 2: Docker Compose setup

**Files:**
- Create: `docker-compose.yml`
- Create: `backend/Dockerfile`

**Step 1: Create docker-compose.yml**

Services: db (postgres:16-alpine, user ceo24, port 5432), backend (build ./backend, port 8000, depends_on db), volume pgdata.

**Step 2: Create backend Dockerfile**

FROM python:3.12-slim, WORKDIR /app, install deps from pyproject.toml, CMD uvicorn.

**Step 3: Start database**

Run: `docker-compose up -d db`
Expected: PostgreSQL running

**Step 4: Commit**

`feat: add Docker Compose with PostgreSQL`

---

### Task 3: SQLModel models - organizations, contracts, documents

**Files:**
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/models/organization.py`
- Create: `backend/app/models/contract.py`
- Create: `backend/app/models/document.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/test_models.py`

**Step 1: Write failing test for Organization model**

Test: create Organization with inn, name_1c, name_display, org_type (TSN), status (ACTIVE), monthly_ap. Assert all fields. Test default status is ACTIVE.

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_models.py -v`
Expected: FAIL

**Step 3: Implement Organization model**

SQLModel table "organizations". Fields: id (UUID PK), inn (VARCHAR(12) UNIQUE), name_1c, name_display, org_type (Enum: TSN/OOO/AO/IP/KP/ZHK/SNT/NP/FL/Prochee), manager_id (FK users), client_since, status (Enum: active/churned/suspended/prospect, default active), objects, object_type, cloud_url, system_number, equipment, address, city_region, has_folder, payment_score (0-100), monthly_ap (Decimal 12,2), total_debt (Decimal 12,2), notes, created_at, updated_at.

**Step 4: Run test - should pass**

**Step 5: Write test and implement Contract model**

SQLModel table "contracts". Fields: id (UUID), organization_id (FK), contract_number, contract_date, contract_type (Enum: subscription/equipment/service/other), classification_source (auto/manual), classification_rule, monthly_amount, total_amount, status (active/completed/terminated), raw_name, created_at.

**Step 6: Implement Document model**

SQLModel table "documents". Fields: id, contract_id (FK), organization_id (FK, denormalized), doc_type (Enum: sale/payment/prepay_in/prepay_used), doc_number, doc_date, amount, period_year, period_month, import_run_id (FK), raw_name, created_at.

**Step 7: Run all tests, commit**

`feat: add SQLModel models for organizations, contracts, documents`

---

### Task 4: SQLModel models - snapshots, import_runs, users, alerts

**Files:**
- Create: `backend/app/models/snapshot.py`
- Create: `backend/app/models/import_run.py`
- Create: `backend/app/models/user.py`
- Create: `backend/app/models/alert.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/tests/test_models.py`

**Step 1: Write test for MonthlySnapshot**

Test creation with organization_id, year, month, debt_start, sold, paid, debt_end, collectability, is_active.

**Step 2: Implement MonthlySnapshot**

Table "monthly_snapshots" with UniqueConstraint(organization_id, year, month, import_run_id). Fields: id, organization_id (FK), year, month (1-12), debt_start, advance_start, sold, paid, sold_ap, paid_ap, sold_equip, paid_equip, debt_end, advance_end, plan_amount, collectability, dso, is_active, import_run_id (FK).

**Step 3: Implement ImportRun**

Table "import_runs". Fields: id, filename, file_hash (SHA-256, VARCHAR(64)), period_start, period_end, status (pending/processing/completed/failed), total_rows, buyers_count, contracts_count, documents_count, new_buyers, errors (JSON), delta_summary (JSON), started_at, completed_at.

**Step 4: Implement User**

Table "users". Fields: id, name, email (unique), hashed_password, role (admin/manager/viewer), telegram_id, is_active, created_at.

**Step 5: Implement Alert**

Table "alerts". Fields: id, organization_id (FK, nullable), alert_type (Enum: non_payment/churn_risk/large_debt/unassigned_client/phantom_deal/project_overdue/anomaly/collectability_drop/new_client), severity (critical/warning/info), title, description, metric_value, threshold, status (open/acknowledged/resolved/dismissed), resolved_by (FK users), resolved_at, created_at.

**Step 6: Update __init__.py, run tests, commit**

`feat: add all SQLModel models (snapshots, imports, users, alerts)`

---

### Task 5: Alembic migrations

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Auto-generated: `backend/alembic/versions/`

**Step 1: Initialize Alembic**

Run: `cd backend && alembic init alembic`

**Step 2: Configure alembic env.py**

Set target_metadata = SQLModel.metadata, import all models, use settings.DATABASE_URL.

**Step 3: Generate first migration**

Run: `cd backend && alembic revision --autogenerate -m "initial schema"`

**Step 4: Apply migration**

Run: `cd backend && alembic upgrade head`
Expected: All tables created

**Step 5: Verify tables**

Run: `docker-compose exec db psql -U ceo24 -c "\dt"`
Expected: 7 tables listed

**Step 6: Commit**

`feat: add Alembic migrations with initial schema`

---

## Phase 2: 1C Parsers (Week 1 Day 3 - Week 2)

### Task 6: Contract classifier

**Files:**
- Create: `backend/app/parser/__init__.py`
- Create: `backend/app/parser/classifier.py`
- Create: `backend/tests/test_classifier.py`

**Step 1: Write failing tests**

7 tests: subscription by /P suffix, subscription by "uslug" keyword, equipment by "montazh", equipment by "SKUD", service by "remont", other for unknown, equipment by large amount (>=100K).

**Step 2: Implement classifier**

ClassificationResult dataclass (type, rule, source). Three keyword lists: SUBSCRIPTION_KEYWORDS (5 items: /P, uslug, okazan, abonent, obsluzhivan), EQUIPMENT_KEYWORDS (6 items: montazh, postavk, oborudov, ustanovk, SKUD, GRZ), SERVICE_KEYWORDS (3 items: remont, tekhobsluzh, servis). Function classify_contract(name, single_amount) - check subscription first, then equipment, service, amount>=100K for equipment, default other.

**Step 3: Run tests, commit**

`feat: add contract classifier with keyword rules`

---

### Task 7: Debt report parser - hierarchy detection

**Files:**
- Create: `backend/app/parser/debt_report.py`
- Create: `backend/tests/test_debt_parser.py`

**Step 1: Write tests for hierarchy detection**

8 tests: buyer by 10-digit INN, buyer by 12-digit INN, contract starting with "Dogovor", contract starting with "Osnovnoy dogovor", document starting with "Realizatsiya", document starting with "Postupleniye", total row "Itogo", unknown for empty.

**Step 2: Implement detect_level function**

Enum HierarchyLevel (buyer/contract/document/total/unknown). Logic: "Itogo" -> total, column B has 10-12 digit number -> buyer, starts with "Dogovor"/"Osnovnoy dogovor" -> contract, starts with "Realizatsiya"/"Postupleniye" -> document, else unknown.

**Step 3: Run tests, commit**

`feat: add hierarchy level detection for 1C debt report`

---

### Task 8: Debt report parser - full file parsing

**Files:**
- Modify: `backend/app/parser/debt_report.py`
- Modify: `backend/tests/test_debt_parser.py`

**Step 1: Write integration test with real file**

Test parse_debt_report with sample file. Assert: total_rows > 1500, buyers_count >= 240, contracts_count >= 200, documents_count >= 1000. Check first buyer: inn="9717053891", name contains "7 NEBO", has contracts with documents. Test period detection: January-February 2026.

**Step 2: Implement full parser**

Dataclasses: ParsedDocument (raw_name, doc_type, doc_number, doc_date, amount, all column values), ParsedContract (raw_name, contract_number, contract_date, documents list, aggregated columns), ParsedBuyer (name, inn, contracts list, aggregated columns), ParseResult (filename, file_hash, period_start/end, counts, buyers list, errors).

Helper functions: _parse_period (regex for "za Yanvar 2026 g. - Fevral 2026 g."), _to_decimal, _parse_doc_number_date (regex for "No X ot DD.MM.YYYY"), _detect_doc_type, _parse_contract_number_date.

Main parse_debt_report function: read file with openpyxl, compute SHA-256 hash, parse period from row 2, iterate rows from 9, detect hierarchy level, build nested structure (buyers -> contracts -> documents), stop at "Itogo" row.

Column mapping: A=name, B=INN, C=debt_start, D=advance_start, E=sold, F=paid, G=prepay_in, H=prepay_used, I=debt_end, J=advance_end.

**Step 3: Run tests, commit**

`feat: implement full 1C debt report parser`

---

### Task 9: Bank statement parser

**Files:**
- Create: `backend/app/parser/bank_statement.py`
- Create: `backend/tests/test_bank_parser.py`

**Step 1: Write tests**

Test extract_payment_info: extract invoice number from "schet No 238", extract contract number from "DOGOVOR No ...", extract period month/year from "za mart 2026". Integration test with real file: parse_bank_statement returns 20+ payments, all have INN and amount > 0.

**Step 2: Implement parser**

PaymentInfo dataclass (invoice_number, contract_number, period_month, period_year, tariff). ParsedPayment dataclass (date, doc_number, amount, counterparty, inn, description, doc_type, payment_info). BankStatementResult dataclass.

extract_payment_info function: regex for invoice number, contract number, period (month name + year), short period (MM/YYYY), tariff (PROF/STANDART).

parse_bank_statement function: read XLSX, parse header (rows 1-5: account, period, owner), iterate from row 10, extract credit column D, counterparty, INN column F, description column K.

**Step 3: Run tests, commit**

`feat: add bank statement parser`

---

### Task 10: Import service - save parsed data to DB

**Files:**
- Create: `backend/app/services/__init__.py`
- Create: `backend/app/services/import_service.py`
- Create: `backend/tests/test_import_service.py`
- Create: `backend/tests/conftest.py`

**Step 1: Create test fixtures**

conftest.py: db_session fixture using SQLite in-memory (SQLModel.metadata.create_all, Session yield).

**Step 2: Write test**

Create mock ParseResult with 1 buyer, 1 contract, 1 document. Call ImportService.process_import. Assert import_run.buyers_count == 1, status == completed.

**Step 3: Implement ImportService**

process_import method: create ImportRun (processing), iterate buyers -> _process_buyer, update counts, set completed. _process_buyer: find or create Organization by INN, create Alert for new unassigned clients, process contracts. _process_contract: classify contract, find or create Contract, create Documents. _clean_name: remove _DIADOK, _SBIS, etc.

**Step 4: Run tests, commit**

`feat: add import service to save parsed data to DB`

---

## Phase 3: REST API (Week 3)

### Task 11: Auth - JWT + user management

**Files:**
- Create: `backend/app/core/security.py`
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/v1/__init__.py`
- Create: `backend/app/api/v1/auth.py`
- Create: `backend/tests/test_auth.py`

**Step 1: Implement security utilities**

Functions: verify_password (bcrypt), get_password_hash, create_access_token (jose JWT with HS256, expiry from settings).

**Step 2: Implement auth endpoint**

POST /auth/login - OAuth2PasswordRequestForm, verify credentials, return access_token. get_current_user dependency - decode JWT, lookup user by email.

**Step 3: Write tests**

Test password hash/verify, test token creation returns string > 50 chars.

**Step 4: Run tests, commit**

`feat: add JWT auth with login endpoint`

---

### Task 12: Organizations API

**Files:**
- Create: `backend/app/api/v1/organizations.py`
- Create: `backend/tests/test_api_organizations.py`

**Step 1: Implement organizations router**

GET /organizations - list with pagination (page, page_size), search (name/INN ilike), filter by status and manager_id. Returns {items, total, page, page_size}.
GET /organizations/{inn} - single org by INN, 404 if not found.
GET /organizations/{inn}/snapshots - monthly history sorted by year/month.
GET /organizations/{inn}/contracts - contracts list.

**Step 2: Register router in main.py**

**Step 3: Write tests, commit**

`feat: add organizations API with search, filters, pagination`

---

### Task 13: Dashboard, billing, import, alerts API

**Files:**
- Create: `backend/app/api/v1/dashboard.py`
- Create: `backend/app/api/v1/billing.py`
- Create: `backend/app/api/v1/imports.py`
- Create: `backend/app/api/v1/alerts.py`

**Step 1: Dashboard API**

GET /dashboard/summary - aggregate MRR (sum monthly_ap where active), ARR (MRR*12), total_debt, active_clients count, open_alerts count.
GET /dashboard/mrr-trend - group monthly_snapshots by year/month, sum sold_ap and paid_ap.
GET /dashboard/aging - aggregate organizations with debt > 0 into buckets.

**Step 2: Billing API**

GET /billing/debtors - organizations with total_debt > min_debt, sorted by debt desc.

**Step 3: Import API**

POST /import/upload - accept XLS/XLSX file, save to inbox, parse with debt_report parser, check duplicate by file_hash (409 if exists), run ImportService, return import_run.
GET /import/runs - list import runs sorted by started_at desc.

**Step 4: Alerts API**

GET /alerts - list alerts filtered by status, sorted by created_at desc.
PATCH /alerts/{alert_id} - update alert status.

**Step 5: Register all routers in main.py, verify Swagger at /docs**

**Step 6: Commit**

`feat: add all MVP API endpoints (dashboard, billing, import, alerts)`

---

## Phase 4: Frontend - Vue 3 SPA (Week 4)

### Task 14: Initialize Vue 3 project

**Step 1: Scaffold**

Run: npm create vite@latest frontend -- --template vue-ts
Install: primevue, @primevue/themes, primeicons, pinia, @pinia/plugin-persistedstate, vue-echarts, echarts, axios, vue-router.

**Step 2: Configure main.ts**

Create Pinia with persistedstate plugin, PrimeVue with Aura theme, vue-router.

**Step 3: Create API client**

Axios instance with baseURL /api/v1, request interceptor adding Bearer token from localStorage.

**Step 4: Create auth store**

Pinia store: token state, isAuthenticated getter, login action (POST /auth/login with form data), logout action.

**Step 5: Create router**

Routes: /login, / (Dashboard), /billing, /clients/:inn, /debtors, /import. Navigation guard: redirect to /login if no token.

**Step 6: Verify dev server, commit**

`feat: initialize Vue 3 + PrimeVue + Pinia frontend`

---

### Task 15: Login page

**Files:**
- Create: `frontend/src/views/LoginView.vue`

Login form with PrimeVue InputText + Password + Button. Error handling. Redirect to / on success.

**Commit:** `feat: add login page`

---

### Task 16: Billing - client registry (main table)

**Files:**
- Create: `frontend/src/views/BillingView.vue`
- Create: `frontend/src/stores/organizations.ts`

**Step 1: Organizations store**

Pinia store: items array, total count, loading flag. fetch action with params (search, status, manager_id, page).

**Step 2: BillingView with PrimeVue DataTable**

Columns: name_display (Klient), inn, monthly_ap (AP/mes with currency format), total_debt (with Tag color: danger > 100K, warn > 30K), payment_score (ProgressBar 0-100), status, objects, city_region. Search input. Row click navigates to /clients/{inn}. Paginator, striped rows, sortable columns.

**Commit:** `feat: add billing registry with PrimeVue DataTable`

---

### Task 17: Client card view

**Files:**
- Create: `frontend/src/views/ClientCardView.vue`

**Step 1: Create client card**

Fetch data from 3 endpoints: /organizations/{inn}, /organizations/{inn}/snapshots, /organizations/{inn}/contracts.

Header: name_display, INN, org_type, status badge, cloud_url link, address.

PrimeVue TabView with tabs:
- Info: organization details, metadata from analytics (objects, equipment, system_number)
- Contracts: DataTable of contracts (number, type, amount, status, classification)
- Payment History: DataTable of monthly snapshots (year/month, plan, sold, paid, debt, collectability)
- Charts: vue-echarts bar chart (sold vs paid by month), line chart (debt_end trend)

**Commit:** `feat: add client card view with charts and payment history`

---

## Phase 5: Debtors and Payment Score (Week 5)

### Task 18: Payment Score calculation

**Files:**
- Create: `backend/app/services/metrics.py`
- Create: `backend/tests/test_metrics.py`

**Step 1: Write tests**

Test perfect payer (all 100% -> score >= 90). Test bad payer (20% on_time, 40% collect, 3 months, 80% debt -> score <= 30). Test range always 0-100.

**Step 2: Implement**

Formula: on_time_pct * 0.4 + collectability * 0.3 + tenure_score * 0.2 + debt_score * 0.1. Tenure normalized to 0-100 (cap at 48 months). Debt score inverted (0% debt = 100). Clamp result to 0-100.

**Step 3: Run tests, commit**

`feat: add Payment Score calculation`

---

### Task 19: Debtors view

**Files:**
- Create: `frontend/src/views/DebtorsView.vue`

Aging buckets visualization: vue-echarts horizontal bar chart (4 buckets: 0-30, 31-60, 61-90, 90+ days, colored gray/yellow/orange/red).

DataTable of debtors sorted by debt desc. Columns: name, INN, monthly_ap, total_debt (color-coded Tag), payment_score, status. Row click -> client card.

**Commit:** `feat: add debtors view with aging buckets`

---

## Phase 6: Dashboard and Final (Week 6)

### Task 20: Dashboard view

**Files:**
- Create: `frontend/src/views/DashboardView.vue`
- Create: `frontend/src/components/DashboardWidget.vue`
- Create: `frontend/src/stores/dashboard.ts`

**Step 1: Dashboard store**

Pinia store: summary, mrrTrend, aging states. fetchAll action: Promise.all 3 API calls.

**Step 2: DashboardWidget component**

Props: title, value, subtitle, icon, color. Displays large number with trend indicator.

**Step 3: DashboardView**

Top row: 4 widgets (MRR with sparkline, Total Debt, Active Clients, Open Alerts).
Middle: MRR Trend line chart (12 months sold_ap vs paid_ap) + Aging horizontal bar chart.
Bottom: "Problemnye klienty" table - organizations with total_debt > 100K or payment_score < 30.

**Commit:** `feat: add CEO dashboard with widgets and charts`

---

### Task 21: Import page

**Files:**
- Create: `frontend/src/views/ImportView.vue`

PrimeVue FileUpload (drag and drop, accept .xls,.xlsx). On upload: POST /import/upload. Show result summary (buyers_count, contracts_count, documents_count, new_buyers, errors).

Import history: DataTable of import_runs (filename, period, status badge, counts, started_at).

**Commit:** `feat: add import page with file upload and history`

---

### Task 22: App layout and navigation

**Files:**
- Modify: `frontend/src/App.vue`
- Create: `frontend/src/components/AppLayout.vue`
- Create: `frontend/src/components/Sidebar.vue`

Sidebar navigation: logo "CEO24", links (Dashboard, Billing, Debtors, Import) with PrimeIcons. User name + logout button at bottom. Main content area with router-view.

**Commit:** `feat: add app layout with sidebar navigation`

---

### Task 23: nginx + Docker for full stack

**Files:**
- Create: `frontend/Dockerfile`
- Create: `nginx/nginx.conf`
- Modify: `docker-compose.yml`

Frontend Dockerfile: multi-stage (node:20-alpine build, nginx:alpine serve). nginx config: /api/ proxied to backend:8000, / serves Vue SPA with try_files for SPA routing. Update docker-compose with frontend and nginx services.

**Commit:** `feat: add Docker setup for full stack deployment`

---

### Task 24: Seed data from analytics spreadsheet

**Files:**
- Create: `backend/app/parser/analytics_migration.py`
- Create: `backend/scripts/seed_data.py`

Migration script reads "Analitika postupleniy" XLSX "Plan vs Fact" sheet: populates organizations with objects, object_type, cloud_url, system_number, equipment, address, city_region, monthly_ap. Creates contracts from contract column. Creates monthly_snapshots from plan/fact columns (2025 actuals + 2026 plan).

Seed script: creates admin user (admin@onvi-service.ru), runs analytics migration.

**Commit:** `feat: add seed data script and analytics migration`

---

### Task 25: Final integration test

**Step 1: Start full stack**

docker-compose up -d db, alembic upgrade head, seed data, start backend + frontend.

**Step 2: Smoke test checklist**

- [ ] Login as admin
- [ ] Dashboard shows widgets
- [ ] Upload debt report via Import
- [ ] Organizations appear in Billing
- [ ] Click organization -> client card
- [ ] Debtors page shows data
- [ ] Dashboard updates

**Step 3: Run all backend tests**

Run: `cd backend && python -m pytest -v`
Expected: All passed

**Step 4: Commit**

`feat: CEO24 MVP complete`

---

## Summary

| Phase | Tasks | Duration |
|-------|-------|----------|
| 1. Scaffold and DB | Tasks 1-5 | Week 1, Days 1-2 |
| 2. Parsers | Tasks 6-10 | Week 1 Day 3 - Week 2 |
| 3. REST API | Tasks 11-13 | Week 3 |
| 4. Frontend UI | Tasks 14-17 | Week 4 |
| 5. Debtors and Score | Tasks 18-19 | Week 5 |
| 6. Dashboard and Final | Tasks 20-25 | Week 6 |

**Total: 25 tasks, 6 weeks**
