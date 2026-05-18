# История разработки

Правило: хранить только последние 10 записей. При добавлении новой переносить старые в
`agent_docs/development-history-archive.md`. Архив читать при необходимости.

---

Краткий журнал итераций проекта.

## Записи

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

### 2026-03-06 — MVP complete (Tasks 18-25)

**Что сделано:**
- Tasks 18-25: DashboardView (4 KPI-карточки, MRR-тренд ECharts, aging bar chart), DebtorsView (DataTable с фильтром min_debt), ImportView (drag-and-drop загрузка XLS/XLSX, история импортов), Payment Score расчёт, Sidebar + Layout, Alerts panel
- Frontend Nginx для production-сборки
- seed_data.py скрипт для загрузки аналитики поступлений (метаданные объектов, план/факт, адреса)

**Тесты:** 74/74 backend passed. Frontend builds successfully

### 2026-05-13 — User management feature + akhromov admin + backlog

**Что сделано:**
- **Backend API:**
  - `POST /api/v1/auth/change-password` — любой пользователь меняет свой пароль (требует current_password + new_password ≥ 8 символов)
  - `GET /api/v1/auth/me` — возвращает информацию о текущем пользователе
  - `GET/POST /api/v1/users` + `POST /api/v1/users/{id}/reset-password` — admin-only (role guard через `require_admin`)
  - `require_admin` dependency в `auth.py` (HTTP 403 если `role != admin`)
- **CLI `backend/scripts/manage_users.py`:** list / create / reset-password / set-role / (de)activate. Запуск через `docker exec -it $(docker ps -qf name=backend) python scripts/manage_users.py ...`. Для emergency-операций без UI.
- **Frontend:**
  - `views/ProfileView.vue` — информация о пользователе + смена пароля
  - `views/UsersView.vue` — admin-only: таблица пользователей, кнопки «Создать», «Сбросить пароль», диалог с одноразовым показом сгенерированного пароля
  - `components/Sidebar.vue` — блок с именем/ролью текущего пользователя (клик → /profile), ссылка «Пользователи» для admin
  - `stores/auth.ts` — `user`, `isAdmin`, `fetchMe`, `changePassword`
  - `router.ts` — `/profile`, `/users` (с `requiresAdmin` meta)
- **Тесты:** 11 новых в `test_users_api.py` (admin-only enforcement, password validation, generated/explicit password paths, duplicate detection, change-password flow). Total: 81 passed, 9 skipped.
- **Применение:**
  - admin@onvi-service.ru пароль сброшен (новый в `~/.config/ceo24/credentials`)
  - akhromov@pass24online.ru создан с ролью admin (пароль там же)
- **Документация:** `agent_docs/backlog.md` — собран бэклог рекомендаций (P3 фичи, инфра, качество, безопасность, идеи). `agent_docs/index.md` обновлён ссылкой на backlog и информацией о пользователях.

**Известный нюанс:** EmailStr (pydantic) требует `email-validator` пакета (не установлен), заменено на regex-валидацию через `field_validator`. Если позже нужна полная RFC-валидация — добавить `pydantic[email]` в зависимости.

**Что в backlog (приоритеты для P3):**
- P3.1 сверка платежей с банком — первый кандидат
- P3.2 прогноз MRR
- P3.3 реальные роли manager/viewer
- P3.4 алерты по расписанию (cron)
- + инфра/безопасность/качество: frontend healthcheck, UptimeRobot, S3-backup, rate-limit на /auth/login, audit log

**Следующий шаг:** UptimeRobot (5 мин, на стороне пользователя через web-UI), затем P3.1 (сверка платежей).

### 2026-05-13 — Инцидент: восстановление + security hotfix + reliability + persistent БД (P0/P1/P2)

**Что сделано:**
- **Инцидент:** обнаружено, что http://85.239.51.34 не открывается (порт 80 closed). Диагностика: контейнеры в статусе `Exited (255)` 4 недели назад, не удалены. Причина — отсутствие `restart: unless-stopped` в compose и (вероятно) перезапуск Docker daemon на стороне Timeweb.
- **P0 Recovery:**
  - SSH-ключ: `~/.ssh/ceo24_ed25519`, alias `ceo24` в `~/.ssh/config`. Запись добавлена.
  - Дамп БД до любых изменений: `~/Backups/ceo24/ceo24-pre-recovery-2026-05-13-1656.dump` (385 KB)
  - Стек поднят через `docker compose up -d`. Данные на месте: 273 orgs, 557 contracts, 3814 docs, 3428 snapshots, MRR 4 483 322 ₽ (совпало с эталоном).
- **P0.6 Security hotfix:** все 6 data-роутеров (dashboard, billing, organizations, contracts, alerts, imports) использовали `Depends(get_session)` без `get_current_user` — финансовые данные ОНВИ СЕРВИС публично утекали через `/api/v1/dashboard/summary` и т.д. Добавлен router-level `dependencies=[Depends(get_current_user)]`. Тесты обновлены (override в conftest-стиле). 70 passed, 9 skipped (file-based parsers без артефактов). ADR-011 зафиксирован.
- **P1 Reliability:**
  - `restart: unless-stopped` для всех 3 сервисов
  - healthchecks: backend `/health`, frontend `wget /`, db `pg_isready`
  - лог-ротация `json-file 10MB × 3`
  - swap 2 GB (swappiness=10) — система была без swap при 2 GB RAM
  - auto-recovery test: `docker kill backend` → через ~12 сек снова Up
- **P2 Persistent storage:**
  - Bind mount `/srv/ceo24/pgdata:/var/lib/postgresql/data` (uid 70, chmod 700)
  - Дамп → восстановление в новый bind mount → 273 orgs (совпало)
  - Persistence test: `docker compose rm -fs db && up -d db` → 273 orgs остались. ADR-007 помечен superseded by ADR-010.
- **P2.3 Автобэкап:** `/usr/local/bin/ceo24-backup.sh` (pg_dump -Fc | gzip, retention 14 дней), cron `/etc/cron.d/ceo24-backup` 03:00 UTC. Первый бэкап: 377 KB gz.
- **P2.4 Pull на ноут:** launchd-агент `com.akhromov.ceo24-backup-pull` 05:00 локального → `~/Backups/ceo24/`. Первый pull выполнен.
- **Runbook:** `agent_docs/guides/runbook.md` — операционные процедуры (диагностика, восстановление из дампа, деплой, сброс пароля).
- **Документация:** исправлен `agent_docs/index.md` (admin login — это email `admin@onvi-service.ru`, не `admin`). Локальные креды в `~/.config/ceo24/credentials` (chmod 600).

**ADR:** ADR-010 (persistent pg через bind mount), ADR-011 (router-level auth dependency), ADR-007 superseded.

**Метрики (после восстановления):** MRR 4 483 322 ₽, ARR 53 799 866 ₽, 273 активных клиента, 6 172 462 ₽ долг (совпало с эталоном 2026-03-07 — никаких потерь).

**Не сделано / отложено:**
- Сброс admin-пароля (генерация выполнена локально, новый хеш в `~/.config/ceo24/credentials`, но UPDATE в production users заблокирован auto-policy — требует явного одобрения)
- UptimeRobot (P1.3) — интерактивная настройка через web-UI, оставлено пользователю
- DR-drill в изолированную БД (P2.5) — частично закрыто фактом успешного restore при миграции на bind mount
- P3 (фичи) — план зафиксирован, начнётся после стабилизации

**Следующий шаг:** Сброс admin-пароля (или установка пользовательского). После этого — UptimeRobot, затем переход к P3.1 (сверка платежей с банк-выпиской через UI).

### 2026-03-07 — Деплой + Contracts Registry + Fixes

**Что сделано:**
- **Деплой на Timeweb VPS** (85.239.51.34): Docker Compose (PostgreSQL + FastAPI + Vue/Nginx), настройка firewall (порты 22, 80, 443), Alembic миграции, seed admin user
- **Docker fixes:** убраны volumes из docker-compose.yml (managed platform restriction), nginx.conf скопирован в frontend build context вместо bind mount, backend Dockerfile дополнен COPY для alembic/, alembic.ini, scripts/
- **XLS support:** создан `backend/app/parser/utils.py` — `load_workbook_any()` конвертирует .xls (xlrd) → openpyxl Workbook. Обновлены debt_report.py и bank_statement.py
- **Импорт данных:** загружен отчёт «Задолженность покупателей» (268 orgs, 376 contracts, 3814 docs) + аналитика поступлений через seed_data.py (176 orgs обновлено, 182 contracts, 3428 snapshots)
- **Contracts API:** новый endpoint `GET /api/v1/contracts` — join Contract+Organization, search, sort (org_name/monthly_amount/contract_date), pagination
- **BillingView v2:** режим-переключатель SelectButton ("По клиентам" / "По договорам"), таблица договоров с 11 колонками (Контрагент, ИНН, Договор, Дата, АП/мес, Тип объекта, Статус, Облако, № сист., Оборудование, Адрес)
- **Sidebar:** label "Биллинг" → "Реестр клиентов"
- **Очистка БД:** удалены 3 пустых import_runs (0 buyers/contracts/docs)

**Dashboard метрики:** MRR 4,483,322₽, ARR 53,799,866₽, 273 активных клиента, 6,172,462₽ общий долг

**Файловая структура (новое):**
```
backend/app/parser/utils.py        # load_workbook_any() — .xls/.xlsx support
backend/app/api/v1/contracts.py    # GET /contracts — join + search + sort + pagination
frontend/nginx.conf                # Скопирован в build context (не bind mount)
```

**API endpoints (добавлено):**
```
GET /api/v1/contracts(?search,sort_by,sort_dir,page,page_size)
```

**Ключевые решения:** ADR-007 (без volumes в Docker), ADR-008 (xlrd конвертация), ADR-009 (режим-переключатель в реестре)

**Следующий шаг:** Импорт банковской выписки через UI, расширение парсера аналитики

### 2026-05-16 — Редизайн рабочих экранов (Dashboard, Реестр, Должники, карточка)

**Контекст:** графики дашборда показывали 7 пустых месяцев (платежи импортированы только с 01/2026), KPI «-23% м/м» вводил в заблуждение (откат от мартовской аномалии 127%), «287 алертов» — голый счётчик. Реестр — плоская таблица без аналитики, карточка клиента — только просмотр.

**Спецификация/планы:** `docs/superpowers/specs/2026-05-15-ceo24-screens-redesign-design.md`, `docs/superpowers/plans/2026-05-15-ceo24-screens-redesign.md`.

**Backend (8 эндпоинтов, без миграций — все поля уже были в моделях):**
- `PATCH /organizations/{inn}` — редактирование (схема `OrganizationUpdate`, read-only inn/name_1c/total_debt/payment_score/*_raw)
- `GET /organizations/{inn}/documents` — история документов
- `GET /users/options` — список менеджеров для не-админов (router-level admin-guard перенесён на конкретные эндпоинты)
- `GET /dashboard/collection-trend` — тренд сбора только по месяцам с данными
- `GET /dashboard/attention` — агрегация открытых алертов по типу
- `dashboard/summary` расширен: current_month_collected, days_passed/in_month, debt_90plus_amount/share, collection_rate_fact
- `GET /billing/segments` — сегментация (платят/частично/не платят/должники)
- `GET /billing/debtors` обогащён months_overdue + aging_bucket

**Frontend:**
- Новые компоненты: `KpiTile`, `SegmentBand`, `AttentionPanel`
- `DashboardView` переписан: 5 KPI вокруг сбора денег, честный график сбора, aging с кликом на /debtors, панель «Требуют внимания»; шахматка убрана
- `DebtorsView` переписан: реестр должников с aging-фильтром и инлайн-сменой статуса
- `BillingView`: шапка сегментов + режим «Шахматка» (heatmap перенесён с дашборда)
- `ClientCardView` переписан: редактируемый инструмент (все поля правятся, статус меняется), вкладки История платежей / Помесячно / Договоры / Объекты
- Подключён `ToastService` для уведомлений

**Тесты:** backend 121 passed, 9 skipped (было 106 — добавлено 15: test_api_dashboard.py, test_api_billing.py, PATCH/documents/options). Frontend: vue-tsc чисто, build успешен.

**Не сделано / отложено:**
- Деплой на production — требует подтверждения пользователя (shared-система, 5 пользователей)
- Аномалия марта 2026 (собираемость 127%) — внесена в backlog как задача проверки данных
- Сегменты paying/partial/not_paying на Реестре — пока только числа в шапке (нет серверного фильтра по собираемости в списке организаций)

**Следующий шаг:** деплой и ручная проверка на production; затем P3.1 (сверка платежей с банком — план готов).

### 2026-05-18 — Учёт абонентской платы (AR-леджер)

**Контекст:** аномалия марта 2026 (собираемость 127%) при расследовании оказалась не ошибкой данных, а дефектом определения метрики: `collection-trend` суммировал валовой приток платежей по дате прихода и сравнивал с планом одного месяца. Платежи приходят неравномерно (за прошлые / текущий / будущие периоды).

**Спецификация/план:** `docs/superpowers/specs/2026-05-18-subscription-ar-ledger-design.md`, `docs/superpowers/plans/2026-05-18-subscription-ar-ledger.md`. Фича поглотила backlog-пункт P3.1.

**Что сделано:**
- **3 новые таблицы** (миграция `8f49f48e53dc`): `tariff_periods` (история тарифа), `monthly_charges` (месячные начисления), `payment_allocations` (разнесение платежа на начисления).
- **Парсер периодов** `app/parser/period_extraction.py` — slash-формат с валидацией, названия месяцев, диапазоны, «на N месяцев», классификация `payment_kind`. Чинит мусор вида `month=63`.
- **`ChargeService`** — лента начислений: реальная 1С-Реализация (subscription-`SALE`) где есть, синтетика из тарифа — для пропусков.
- **`AllocationService`** — детерминированное разнесение платежей: лестница приоритетов (явный период → FIFO → аванс в будущие месяцы, горизонт 24 мес), сохранение ручных аллокаций; пересчёт = чистая функция от данных.
- **Источник платежей** — реестр «Оплата от покупателей» из 1С (2017-2026, 10157 платежей): парсер `payments_report.py`, импорт через `source_type=payments` на синтетический контракт `1C-PAYMENTS`.
- **Backfill** `scripts/build_ledger.py` — идемпотентное построение леджера по существующим данным.
- **Метрики дашборда на леджере:** `collection-trend` (собираемость периода), новый `cash-inflow` (структура поступлений), `aging`/`payment-matrix`/`mrr-plan-vs-fact`/`summary` переведены на леджер.
- **API карточки клиента:** `GET /organizations/{inn}/ledger`, история тарифа (`GET/POST /{inn}/tariffs`), ручная правка разнесения (`PUT /payments/{id}/allocations`).
- **Фронтенд:** компоненты `CashInflowChart`, `LedgerTable`, `AllocationEditor`, `TariffHistory`; дашборд переведён на честную собираемость + структуру поступлений; в карточке клиента — вкладка «Расчёты».

**Тесты:** backend 152 passed, 9 skipped (было 121; +31 теста). Frontend: `vue-tsc` чисто, build успешен. ruff чисто по новым файлам.

**Проверка на копии production-БД** (бэкап 2026-05-16 + полная история платежей): собираемость 2025-2026 — 77-90%, март 2026 — **83%** (было 127%). Аномалия закрыта.

**ADR:** ADR-012 (модель AR-леджера).

**Деплой:** выполнен на production 2026-05-18 — дамп `ceo24-2026-05-18-1435.dump.gz`, миграция
`8f49f48e53dc`, импорт реестра оплат (10021 платёж), `build_ledger` (182 тарифа, 442 клиента).
Проверка: сайт HTTP 200, собираемость марта 2026 на production — 83%.

**Не сделано / отложено:**
- ~27% платежей при backfill попали в бакет «не определён» — в основном исторические неподписочные плательщики без начислений; приемлемо.
- Справочник контрагентов 1С не использован (ИНН в реестре оплат заполнен на 99%) — в backlog для возможного обогащения имён.

**Следующий шаг:** наблюдение за production-дашбордом.
