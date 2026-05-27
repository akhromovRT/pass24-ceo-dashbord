# Архитектура CEO24

## Обзор

CEO24 — веб-приложение с монолитной архитектурой для управленческой аналитики ООО «ОНВИ СЕРВИС». Получает данные из 1С через файловый импорт, обогащает управленческими метриками и представляет через Vue SPA.

## Контекст

- 274 клиента, 5 пользователей — микросервисы избыточны
- 1С — единственный источник финансовых данных (master-система)
- CEO24 добавляет: привязку менеджеров, классификацию контрактов, KPI, алерты, план/факт
- Данные не перезаписываются — иммутабельные снапшоты для аудируемости

## Ключевые компоненты

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│ 1С файлы │────>│  Парсер  │────>│PostgreSQL│
│(XLS/XLSX)│     │ (Python) │     │   16     │
│+ Выписка │     └──────────┘     └────┬─────┘
└──────────┘                           │
                                  ┌────▼─────┐
                                  │ FastAPI  │
                                  │ (REST)   │
                                  └────┬─────┘
                             ┌─────────┼─────────┐
                        ┌────▼───┐┌────▼───┐┌────▼───┐
                        │Биллинг ││Просроч-││Дашборд │
                        │  АП    ││  ки    ││  CEO   │
                        └────────┘└────────┘└────────┘
                             Vue 3 + PrimeVue + ECharts
```

### Backend (`backend/`)
- **FastAPI** — async REST API, автогенерация Swagger
- **SQLModel** — ORM + Pydantic-схемы в одной модели, миграции через Alembic
- **Парсер 1С** — `openpyxl` + `xlrd` (через `load_workbook_any()`): разбор 3-уровневой иерархии (Покупатель→Договор→Документ), поддержка .xls и .xlsx
- **Парсер выписки** — матчинг платежей по ИНН, извлечение периода из назначения
- **Seed-скрипт** — `scripts/seed_data.py`: импорт аналитики поступлений (метаданные объектов, план/факт)
- **JWT-авторизация** — роли: admin, manager, viewer

### Frontend (`frontend/`)
- **Vue 3** + TypeScript + Composition API
- **PrimeVue** — DataTable с фильтрами/сортировкой, Dialog, Calendar
- **vue-echarts** — графики MRR, aging, план/факт
- **Pinia** — state management

### Инфраструктура
- **PostgreSQL 16** — JSONB, оконные функции, CTE
- **Docker + docker-compose** — PostgreSQL + backend + frontend (nginx собран в образ; bind-mount для pgdata и TLS-сертификатов)
- **nginx** — reverse proxy `/api` → backend:8000, статика Vue, TLS-терминация (Let's Encrypt)
- **Сервер:** Timeweb VPS 85.239.51.34, домен `ceo.pass24pro.ru`, порты 22/80/443

## Потоки данных

1. Бухгалтер формирует отчёт «Задолженность покупателей» в 1С → XLS/XLSX
2. Загрузка через UI (`/api/v1/import/upload`) или cron из `/import/inbox/`
3. Парсер: валидация → разбор иерархии (Покупатель→Договор→Документ, включая Корректировки/Допсоглашения/физлица без ИНН/служебные `<…>` — см. ADR-019) → нормализация имён → автоклассификация контрактов
4. Дельта-детекция: сравнение с предыдущим snapshot (новые клиенты, рост долгов, закрытие)
5. Загрузка: INSERT/UPDATE в `organizations`, `contracts`, `documents`
6. **DebtSnapshot**: одновременно с основным импортом пишется полный срез файла 1С (`debt_snapshots` + `debt_snapshot_rows`) — все 8 числовых колонок включая авансы и предоплаты, иерархия через `parent_row_id` (см. ADR-019). Используется для UI «1С-вид» и сверки.
7. Агрегация: пересчёт `monthly_snapshots` за период
8. Метрики: payment_score, DSO, collectability
9. Алерты: проверка пороговых значений
10. API → Vue SPA → дашборд, таблицы, графики

Банковская выписка обрабатывается аналогично (шаги 1-3), но матчит платежи по ИНН с существующими организациями.

## Технологии и зависимости

| Компонент | Технология | Обоснование |
|-----------|-----------|-------------|
| Backend | Python 3.12 + FastAPI | Async, Pydantic, автодокументация |
| ORM | SQLModel + Alembic | Одна модель = ORM + схема API |
| БД | PostgreSQL 16 | JSONB, оконные функции, CTE |
| Frontend | Vue 3 + TypeScript | Composition API, реактивность |
| UI | PrimeVue | 90+ компонентов, DataTable |
| Графики | vue-echarts (ECharts) | 40+ типов, drill-down |
| State | Pinia | Типизированный, DevTools |
| Парсер | openpyxl + xlrd | XLS (OLE2) + XLSX (OpenXML) |
| Контейнеры | Docker + docker-compose | Единый деплой |
| Web-сервер | nginx | Reverse proxy, HTTPS, статика |

## Файловая структура (актуальная)

```
backend/
├── pyproject.toml          # hatchling build, deps, ruff, pytest
├── Dockerfile              # python:3.12-slim + alembic + scripts
├── alembic.ini
├── alembic/                # Миграции БД
├── scripts/
│   └── seed_data.py        # Импорт аналитики поступлений
├── app/
│   ├── main.py             # FastAPI app, CORS, /health, все роутеры
│   ├── core/
│   │   ├── config.py       # Settings (pydantic-settings, .env)
│   │   └── database.py     # SQLModel engine, get_session DI
│   ├── models/
│   │   ├── organization.py # Organization + OrgType + OrgStatus
│   │   ├── contract.py     # Contract + ContractType + ContractStatus
│   │   ├── document.py     # Document + DocType
│   │   ├── snapshot.py     # MonthlySnapshot
│   │   ├── import_run.py   # ImportRun + ImportStatus
│   │   ├── user.py         # User + UserRole
│   │   ├── alert.py        # Alert + AlertType + AlertSeverity
│   │   └── debt_snapshot.py # DebtSnapshot + DebtSnapshotRow + DebtSnapshotLevel
│   ├── api/v1/
│   │   ├── auth.py         # POST /auth/login
│   │   ├── organizations.py # GET /organizations, /{inn}, /snapshots, /contracts
│   │   ├── contracts.py    # GET /contracts (join + search + sort)
│   │   ├── dashboard.py    # GET /dashboard/summary, /mrr-trend, /aging
│   │   ├── billing.py      # GET /billing/debtors
│   │   ├── imports.py      # POST /import/upload, GET /import/runs
│   │   ├── debt_snapshots.py # GET /debt-snapshots, /latest, /{id} (UI «1С-вид»)
│   │   └── alerts.py       # GET /alerts, PATCH /{id}
│   ├── parser/
│   │   ├── utils.py        # load_workbook_any() — .xls/.xlsx support
│   │   ├── classifier.py   # classify_contract()
│   │   ├── debt_report.py  # parse_debt_report()
│   │   └── bank_statement.py # parse_bank_statement()
│   └── services/
│       └── import_service.py # ImportService.process_import() + _build_debt_snapshot()
├── scripts/
│   └── backfill_debt_snapshot.py # Backfill DebtSnapshot для существующих ImportRun
└── tests/                  # 245 passed, 9 skipped
frontend/
├── nginx.conf              # Reverse proxy config (baked into image)
├── Dockerfile              # Multi-stage: node build → nginx
├── src/
│   ├── main.ts
│   ├── router.ts
│   ├── api/client.ts       # Axios + Bearer token
│   ├── stores/
│   │   ├── auth.ts
│   │   └── organizations.ts
│   ├── components/
│   │   └── Sidebar.vue     # Навигация: Dashboard, Реестр клиентов, Должники, Импорт
│   └── views/
│       ├── LoginView.vue
│       ├── BillingView.vue      # Режимы: По клиентам / Шахматка / По договорам / По реестру
│       ├── ClientCardView.vue
│       ├── DashboardView.vue
│       ├── DebtorsView.vue      # Режимы: Реестр должников / 1С-вид (TreeTable)
│       ├── ReportsView.vue
│       └── ImportView.vue
docker-compose.yml          # db + backend + frontend (без volumes)
```

## Настройка окружения

- Python 3.12 через `uv`: `cd backend && uv venv --python 3.12 .venv && source .venv/bin/activate && uv pip install -e ".[dev]"`
- БД для разработки: `docker compose up -d db` (PostgreSQL 16)
- Тесты: `cd backend && python -m pytest -v` (SQLite in-memory для unit-тестов)

## Нефункциональные требования и ограничения

- Импорт < 5 сек для 4600 строк
- Иммутабельные снапшоты (данные не перезаписываются)
- Дедупликация файлов по SHA-256
- 4 роли: admin, manager (свои данные), viewer, бухгалтер (импорт)
- Один сервер: 2 vCPU, 4GB RAM, 50GB SSD

## Roadmap

- **MVP (6 нед.):** Парсер 1С + модель данных → API + JWT → Реестр клиентов → Просрочки → Базовый дашборд
- **v1.0 (3 мес.):** Полный биллинг + алерты + автоимпорт + email-дайджест
- **v2.0 (6 мес.):** Воронка продаж + KPI менеджеров + прогнозирование + интеграция Битрикс24

## Модель данных (MVP)

### Основные таблицы
- `organizations` — контрагенты (ИНН, имя, менеджер, статус, payment_score, объекты, адрес, ссылка на облако)
- `contracts` — договоры (номер, тип: subscription/equipment/service/other, сумма АП, автоклассификация)
- `documents` — документы/проводки (реализации, поступления, предоплаты)
- `monthly_snapshots` — ежемесячные агрегаты (sold, paid, debt, collectability, plan, fact)
- `tariff_periods` — история тарифа клиента (AR-леджер)
- `monthly_charges` — месячные начисления абонплаты (AR-леджер): 1С-Реализация или синтетика из тарифа
- `payment_allocations` — разнесение платежа на одно/несколько начислений (явный период / FIFO / аванс / ручная правка)
- `import_runs` — журнал импорта (файл, хеш, статистика, ошибки)
- `users` — пользователи (имя, email, роль)
- `alerts` — алерты (тип, severity, статус)
- `deals` — сделки/воронка (v2.0, но таблица создаётся в MVP)
- `debt_snapshots` — полный срез файла «Задолженность покупателей» 1С на момент импорта (1-к-1 с `import_runs`): период, агрегированные итоги по 8 числовым полям, счётчики
- `debt_snapshot_rows` — строки иерархии снимка (Покупатель/Договор/Документ через `parent_row_id`): все 8 числовых колонок файла + опциональные FK на `organizations`/`contracts`/`documents` для сверки и навигации. Сохраняет физлиц без ИНН (`organization_id=NULL`), которые в основной модели не помещаются из-за UNIQUE inn. См. ADR-019.
