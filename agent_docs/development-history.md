# История разработки

Правило: хранить только последние 10 записей. При добавлении новой переносить старые в
`agent_docs/development-history-archive.md`. Архив читать при необходимости.

---

Краткий журнал итераций проекта.

## Записи

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
  `last_pay_rows`, `excl`, `to_float`, `months_back`). Dashboard и
  drill-down считают из одной точки.
- **Backend:** новый пресет `composition` в `/reports` с параметрами
  `metric` и `period`. Builder `composition_service.py` реализует 8
  метрик: `mrr_fact`, `collected_current`, `mrr_plan`, `active_clients`,
  `new_paid_curr_year/prev_month/curr_month`, `stopped_since_year_start`.
  Ответ `/preview` для composition содержит `control_value` — ₽ для
  денежных метрик, count для количественных. Явный guard для
  `metric=None` (HTTP 400 с понятным сообщением).
- **Frontend:** `KpiTile` получил опциональный prop `to: RouteLocationRaw`
  (становится router-link с hover-эффектом). DashboardView навешивает
  `:to="compositionLink(metric, period)"` на 8 плиток. Плитки «Долг»
  (drill-down через aging-чарт) и «Churn rate» (производная) — без `:to`.
  ReportsView парсит `?preset=composition&metric=...&period=...` на mount,
  показывает в шапке таблицы контрольную сумму, скрывает дебитор-специфичные
  фильтры для composition, при ручной смене пресета очищает query из URL.
- **Инвариант:** `test_composition_matches_dashboard.py` — 8 тестов,
  для каждой метрики проверяет, что `dashboard.summary[metric] ==
  composition.control_value`. Контракт регрессии: пока тесты зелёные,
  drill-down не разъезжается с плитками. Прошёл с первого запуска без
  правок логики.

**Тесты:** backend 173 → **209 passed**, 9 skipped (+36 тестов: 3 регресс
на dashboard_service, 10 unit на composition по метрикам, 8 invariant,
5 API + scaffolding-кейсы). Frontend: `vue-tsc` чисто, `vite build`
успешен. ruff чисто.

**Миграции:** не требуются — все метрики из существующих таблиц.

**Не сделано / отложено:**
- Браузерная проверка на dev-сервере по чек-листу из плана (8 плиток,
  очистка query, экспорт, шаблоны).
- Деплой на production — после браузерной проверки.

**Следующий шаг:** браузерный smoke-тест drill-down, деплой.

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

### 2026-05-19 — Доработки Dashboard по памятке руководителя

**Контекст:** на основе памятки `agent_docs/guides/dashboard-metrics.md` руководитель
вписал требования к доработкам раздела Dashboard (R1–R11).

**Backend (`dashboard.py`):**
- «Структура долга» переработана: каждый клиент с долгом по 1С попадает ровно в одну
  корзину по календарному возрасту самого раннего неоплаченного начисления леджера;
  сумма корзин = `total_debt` (сходится с плиткой ДОЛГ). Хелпер `_debt_aging` —
  единый источник для `/aging`, `/aging/{bucket}` и доли 90+ в `/summary`.
- `/summary` — новые метрики клиентской базы: `new_paid_prev_month`,
  `new_paid_curr_month`, `stopped_since_year_start`, `churn_rate`.

**Frontend:**
- Плитки MRR факт и Сбор — месяц в названии; окрас по шкале процента
  (<30 красный / 30-50 оранжевый / 50-80 жёлтый / 80-100 зелёный) — компонент `KpiTile`.
- Блок «Клиентская база» — отдельные карточки (активные, новые за прошлый/текущий
  месяц, отток с начала года, churn rate); KPI сгруппированы «Финансы» / «Клиентская база».
- График «Собираемость по месяцам» — фильтр по годам (`Select`).
- На каждой плитке всплывающая подсказка (директива PrimeVue `Tooltip`): что
  показывает метрика и как реагировать на отклонения.

**Документация:** памятка `dashboard-metrics.md` переписана под новые изменения (R10),
добавлена в `agent_docs/index.md`.

**Тесты:** backend 162 → **164 passed**, 9 skipped (тесты aging обновлены под новую
логику + тест метрик клиентской базы). Frontend: `vue-tsc` чисто, build успешен.
ruff чисто.

**Деплой:** выполнен на production 2026-05-19 (`ceo.pass24pro.ru`). Проверка в
браузере: корзины «Структуры долга» суммируются в 5,6 млн ₽ = плитка ДОЛГ (было
~37 млн); счётчики корзин не пересекаются; новые плитки и подсказки отображаются.

**Aging выровнен (продолжение 2026-05-19):** логика возраста долга вынесена в общий
сервис `app/services/aging.py` (`debt_aging`, `aging_index`, `age_bucket`,
`ledger_outstanding`). Дашборд, экран «Должники» (`/billing/debtors`) и модуль
«Отчёты» (`report_service`) теперь считают возраст долга одинаково — по календарным
месяцам неоплаты. Дублировавшиеся `_aging_bucket` удалены. backend 165 passed.

**Следующий шаг:** наблюдение.

### 2026-05-19 — Плитка «Новые за год» в блоке «Клиентская база»

**Контекст:** запрос руководителя — видеть, сколько клиентов впервые заплатили в
текущем году (приток новой базы за год), отдельной плиткой после «Активных клиентов».

**Backend (`dashboard.py`):** `/summary` отдаёт новую метрику `new_paid_curr_year` —
число клиентов, чей первый платёж (`MIN(Document.doc_date)`, `doc_type=PAYMENT`)
пришёлся на текущий год. Считается из уже собранного `first_pay_rows`, без новых
запросов к БД.

**Frontend (`DashboardView.vue`):** в блоке «Клиентская база» после «Активных
клиентов» добавлена плитка «Новые за год» (значение `new_paid_curr_year`, подпись
с годом из `current_month_label`, подсказка `HINTS.newYear`). Сетка блока
`kpi-grid-5` → `kpi-grid-6`; добавлен класс `.kpi-grid-6` и брейкпоинты (6→3→2).

**Документация:** памятка `dashboard-metrics.md` — блок «Клиентская база» теперь
6 плиток, добавлено описание «Новые за год».

**Тесты:** `test_summary_client_base_metrics` проверяет ключ `new_paid_curr_year`;
`test_api_dashboard.py` — 8 passed. ruff чисто, frontend build (`vue-tsc`) успешен.

**Следующий шаг:** деплой на production, проверка в браузере.

### 2026-05-19 — Ручной ввод периода при импорте платежей (двухфазный импорт)

**Контекст:** часть банковских платежей и платежей из реестра 1С приходит без
распознаваемого периода в назначении — раньше такие платежи импортировались без
периода и разносились эвристикой. Нужен шаг ручного указания месяца при импорте.

**Backend:**
- Парсер периодов (`period_extraction.py`): распознаётся формат `MM.YYYY` с точкой
  («ЗА 05.2026Г») — `_DOT_RE` с lookbehind/lookahead против ложных матчей внутри дат.
- Поле `period_manual` добавлено в `PaymentInfo` (dataclass) и `Document` (модель +
  Alembic-миграция `a2e7c3b1d0f5`, `ADD COLUMN` с `server_default false NOT NULL`).
- `ImportService.process_bank_import` принимает `period_overrides: dict[int,
  tuple[int,int]]` (ключ — позиционный индекс платежа в файле), проставляет
  `period_manual=True` и период; `process_payments_report` пробрасывает оверрайды.
- `AllocationService`: `Document.period_manual=True` приоритетнее regex из `raw_name`
  — платёж разносится на указанный месяц (basis `EXPLICIT_PERIOD`). При нарушении
  инварианта (флаг без года/месяца) — `logger.warning`, без падения пересчёта.
- API: `POST /import/preview` (фаза 1 — парсит файл, в БД не пишет, отдаёт
  `file_hash` + платежи без периода) и `POST /import/commit` (фаза 2 — сверяет
  `file_hash`, применяет оверрайды, пишет в БД). `/import/upload` для debt/registry
  не затронут.

**Frontend (`ImportView.vue`):** двухфазный поток для bank/payments — после загрузки
шаг ревью с таблицей платежей без периода и помесячным `DatePicker`. Если все периоды
распознаны — commit сразу. Заполнение необязательное. debt/registry — прежний upload.

**Тесты:** backend **173 passed**, 5 skipped (было 155 — +18 новых: парсер, import
service, allocation, API preview/commit). Frontend `vue-tsc` чисто, build успешен.

**Известный нюанс:** оверрайды сопоставляются с платежами по позиционному индексу —
корректно, т.к. preview и commit парсят один и тот же файл (сверка по `file_hash`),
порядок платежей детерминирован.

**Деплой:** выполнен на production (`ceo.pass24pro.ru`) 2026-05-19. Миграция
`a2e7c3b1d0f5` применена (`documents.period_manual`), все сервисы `Up (healthy)`,
эндпоинты `/import/preview` и `/import/commit` отвечают. Нюанс порядка: backend-образ
собирается без bind-mount исходников (`build: ./backend`), поэтому миграцию нельзя
применять `docker compose exec` на ещё не пересобранном контейнере. Корректный
порядок — `build` → `docker compose run --rm backend alembic upgrade head`
(одноразовый контейнер нового образа) → `up -d`; так нет окна «новый код на старой
схеме».

**Следующий шаг:** ручная проверка двухфазного импорта в браузере.
