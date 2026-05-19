# История разработки

Правило: хранить только последние 10 записей. При добавлении новой переносить старые в
`agent_docs/development-history-archive.md`. Архив читать при необходимости.

---

Краткий журнал итераций проекта.

## Записи

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

### 2026-05-19 — Модуль «Отчёты» (экспорт по долгу и собираемости)

**Контекст:** были дашборд (агрегаты) и реестр (таблица), но не было инструмента, где
руководитель сам собирает выборку по критериям и выгружает её. Цель — управленческий
инструмент снижения задолженности и роста собираемости абонплаты.

**План:** `~/.claude/plans/sharded-chasing-stream.md` (plan-mode). ADR-013.

**Что сделано:**
- **Модель + миграция** `f811cf0c2c38`: таблица `report_templates` (`criteria` —
  JSON-колонка) для сохраняемых наборов критериев; шаблоны общие для всех пользователей.
- **`report_service.py`** — сборка двух пресетов поверх AR-леджера (без таблиц-агрегатов,
  всё считается на лету): `debtors` (реестр должников + вычисляемый «приоритет
  взыскания») и `discipline` (дисциплина платежей: собираемость, on-time, тенденция
  аванс/в-срок/просрочка, тренд ↑→↓, подряд неоплаченных месяцев). Общая фильтрация
  (период, статус, менеджер, корзина, тип договора, город, мин. долг, исключённые),
  выбор колонок, сортировка. Экспорт `.xlsx` через openpyxl.
- **Роутер** `/api/v1/reports`: `POST /{type}/preview` (JSON), `POST /{type}/export`
  (.xlsx), `GET/POST/DELETE /reports/templates`. Router-level auth-guard (ADR-011).
- **Фронтенд** `ReportsView.vue` (+ маршрут `/reports`, пункт сайдбара «Отчёты»):
  переключатель пресетов, панель критериев, сохранение/загрузка/удаление шаблонов,
  preview-таблица с динамическими колонками, кнопка «Экспорт в Excel» (blob-скачивание).

**Тесты:** backend 152 → **162 passed**, 9 skipped (+10: `test_api_reports.py` —
пресеты, фильтры, сортировка, валидность .xlsx через openpyxl, CRUD шаблонов).
Миграция изолированно проверена на временной SQLite (upgrade/downgrade чисто).
Frontend: `vue-tsc` чисто, build успешен (чанк `ReportsView` 14.7 КБ / 5.4 gzip).
ruff чисто по новым файлам.

**Деплой:** выполнен на production 2026-05-19 — бэкап БД, миграция `f811cf0c2c38`,
пересборка образов backend+frontend. Проверка: сайт HTTP 200, `alembic current` =
`f811cf0c2c38`, таблица `report_templates` создана, `/api/v1/reports/*` под auth-guard.

**Правка вёрстки (после деплоя):** широкая таблица отчёта вызывала горизонтальный
скролл всей страницы, из-за чего fixed-сайдбар наезжал на контент. Исправлено:
`min-width: 0` на `.main-content` (flex-элемент больше не расширяется под контент),
колонки таблицы получили `min-width`, таблица скроллится внутри себя
(`scrollHeight="flex"`), `.reports-view` ограничен высотой окна.

**Не сделано / отложено:**
- Третий пресет «Структура доходов» не делался в v1 (частично есть на дашборде).
- Ручная браузерная проверка модуля на production.

**Следующий шаг:** браузерная проверка модуля; решение по сетевому дефекту VPS.

### 2026-05-19 — HTTPS (Let's Encrypt) + домен ceo.pass24pro.ru

**Контекст:** подключён домен `ceo.pass24pro.ru` (A-запись → 85.239.51.34). Сервис работал
по голому HTTP — JWT-логины и финансовые данные шли по открытому каналу.

**Что сделано:**
- **Доки:** IP заменён на домен в `index.md`, `architecture.md`, `runbook.md` (в
  диагностических `ping`-командах IP оставлен). В `runbook.md` — новый раздел «HTTPS /
  TLS-сертификат» (проверка срока, ручное/авто-продление, первичный выпуск, troubleshooting).
- **nginx.conf:** HTTP→HTTPS редирект (301), ACME-webroot `/.well-known/acme-challenge/`,
  HTTPS-сервер (TLS 1.2/1.3, HTTP/2, HSTS), отдельная локация `/healthz` без редиректа.
- **docker-compose.yml:** frontend — порт 443 и два ro-bind-mount сертификатов
  (`/srv/ceo24/certbot/{conf,www}`). Healthcheck переведён с `localhost` на `127.0.0.1`:
  `localhost` резолвился в IPv6 `::1`, nginx слушает только IPv4 — контейнер висел
  `unhealthy` (предсуществующий баг, исправлен попутно).
- **Сертификат:** Let's Encrypt для `ceo.pass24pro.ru` выпущен (certbot standalone,
  действует до 2026-08-17).
- **Автопродление:** `/usr/local/bin/ceo24-cert-renew.sh` + cron `/etc/cron.d/ceo24-cert-renew`
  (еженедельно, пн 04:00; `certonly --webroot --keep-until-expiring` + `nginx -s reload`).
  Пробный запуск — exit 0, сертификат продления пока не требует.

**Деплой:** выполнен на production 2026-05-19. Простой ~1–2 мин на выпуск сертификата
(остановка frontend для certbot standalone). Проверка: `https://ceo.pass24pro.ru` — HTTP/2 200;
HTTP → 301 на HTTPS; API через HTTPS — 401 (ожидаемо без токена); сертификат Let's Encrypt
валиден; контейнер `frontend` — `healthy`.

**ADR:** ADR-014 (HTTPS через Let's Encrypt, TLS-терминация в nginx-контейнере).

**Следующий шаг:** наблюдение; проконтролировать срабатывание cron-продления.
