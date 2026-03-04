# CEO24 MVP — Дизайн-документ

**Дата:** 2026-03-04
**Версия:** 1.0
**Статус:** Утверждён

## Цель

Заменить ручной анализ Excel-выгрузок из 1С автоматизированной системой. MVP за 6 недель: парсер 1С → API → реестр клиентов → просрочки → базовый дашборд.

## Архитектура

Монолит: FastAPI (Python 3.12) + PostgreSQL 16 + Vue 3 SPA (PrimeVue + vue-echarts). Docker-compose для деплоя.

```
ceo24/
├── backend/
│   ├── app/
│   │   ├── api/v1/          # REST endpoints
│   │   ├── models/          # SQLModel (ORM + Pydantic)
│   │   ├── services/        # Бизнес-логика, метрики
│   │   ├── parser/          # Парсеры 1С файлов
│   │   │   ├── debt_report.py    # Задолженность покупателей
│   │   │   ├── bank_statement.py # Банковская выписка
│   │   │   └── analytics.py      # Аналитика поступлений (миграция)
│   │   └── core/            # Config, security, database
│   ├── alembic/
│   └── tests/
├── frontend/
│   └── src/
│       ├── views/           # Dashboard, Billing, ClientCard, Debtors
│       ├── components/      # Переиспользуемые компоненты
│       ├── stores/          # Pinia stores
│       └── api/             # HTTP-клиент (axios/fetch)
├── docker-compose.yml
├── nginx/nginx.conf
└── import/inbox/            # Директория для файлов 1С
```

## Источники данных

### 1. Задолженность покупателей (основной)
- Формат: XLS/XLSX из 1С:Бухгалтерия
- Структура: 3-уровневая иерархия в одном столбце (колонка A)
  - **Покупатель:** ИНН в колонке B (10-12 цифр)
  - **Договор:** колонка A начинается с «Договор» или «Основной договор»
  - **Документ:** колонка A начинается с «Реализация» или «Поступление»
- Колонки: A=имя, B=ИНН, C=долг начало, D=аванс начало, E=продано, F=оплачено, G=предоплата поступила, H=предоплата зачтена, I=долг конец, J=аванс конец, K=комментарий
- Шапка: строки 1-8, данные с строки 9, последняя строка «Итого» — пропускается
- Реальный объём: ~1593 строки, 243 покупателя, 213 договоров, 1058 документов

### 2. Банковская выписка (дополнительный)
- Формат: XLSX — «Выписка по счёту»
- Структура: плоский список (шапка строки 1-9, данные с строки 10)
- Колонки: A=дата, B=номер документа, D=кредит (сумма), E=контрагент, F=ИНН, K=назначение платежа, M=тип документа
- Из назначения платежа парсим: номер счёта, период оплаты, тариф (PROF/STANDART), номер договора

### 3. Аналитика поступлений (для первичной миграции)
- 5 листов Excel — текущий ручной инструмент
- **«План vs Факт»** (185 строк): ИНН, контрагент, договор, дата, АП/мес, объект(ы), тип, статус, ссылка на облако, № в системе, оборудование, адрес, город, помесячные план/факт
- **«Должники»** (103 строки): ИНН, контрагент, задолженность, месяцы неоплаты, последний платёж
- **«Детализация платежей»** (1780 строк): дата, ИНН, контрагент, сумма, договор, назначение
- **«Денежный поток»** (11 строк): агрегаты план/факт подписок + прочие
- **«Прочие поступления»** (56 строк): неподписочная выручка по клиентам

## Модель данных

### organizations
| Поле | Тип | Описание |
|------|-----|----------|
| id | UUID PK | |
| inn | VARCHAR(12) UNIQUE NOT NULL | ИНН из 1С |
| name_1c | TEXT NOT NULL | Имя из 1С (с _ДИАДОК и т.д.) |
| name_display | TEXT | Очищенное имя |
| org_type | ENUM | ТСН, ООО, АО, ИП, КП, ЖК, СНТ, НП, ФЛ, Прочее |
| manager_id | UUID FK → users | Ответственный менеджер |
| client_since | DATE | Дата первой реализации |
| status | ENUM DEFAULT active | active, churned, suspended, prospect |
| objects | TEXT | Объект(ы) клиента (из аналитики) |
| object_type | TEXT | Тип объекта (ЖК, Производство и т.д.) |
| cloud_url | TEXT | Ссылка на PASS24 |
| system_number | TEXT | Номер в системе PASS24 |
| equipment | TEXT | Оборудование |
| address | TEXT | Адрес |
| city_region | TEXT | Город/область |
| has_folder | BOOLEAN DEFAULT false | Есть ли папка в Битрикс24 |
| payment_score | SMALLINT 0-100 | Индекс платёжной дисциплины |
| monthly_ap | DECIMAL(12,2) | Текущая АП |
| total_debt | DECIMAL(12,2) | Текущий долг |
| notes | TEXT | Заметки менеджера |

### contracts
| Поле | Тип | Описание |
|------|-----|----------|
| id | UUID PK | |
| organization_id | UUID FK | |
| contract_number | TEXT NOT NULL | Номер из 1С |
| contract_date | DATE | Дата заключения |
| contract_type | ENUM NOT NULL | subscription, equipment, service, other |
| classification_source | ENUM | auto, manual |
| classification_rule | TEXT | Правило автоклассификации |
| monthly_amount | DECIMAL(12,2) | АП для подписок |
| total_amount | DECIMAL(12,2) | Общая сумма для оборудования |
| status | ENUM DEFAULT active | active, completed, terminated |
| raw_name | TEXT | Полное название из 1С |

### documents
| Поле | Тип | Описание |
|------|-----|----------|
| id | UUID PK | |
| contract_id | UUID FK | |
| organization_id | UUID FK | Денормализация |
| doc_type | ENUM NOT NULL | sale, payment, prepay_in, prepay_used |
| doc_number | TEXT | Номер из 1С |
| doc_date | DATE NOT NULL | |
| amount | DECIMAL(12,2) NOT NULL | |
| period_year | SMALLINT | |
| period_month | SMALLINT | |
| import_run_id | UUID FK | |

### monthly_snapshots
| Поле | Тип | Описание |
|------|-----|----------|
| id | UUID PK | |
| organization_id | UUID FK | |
| year | SMALLINT NOT NULL | |
| month | SMALLINT 1-12 | |
| debt_start | DECIMAL(12,2) | |
| advance_start | DECIMAL(12,2) | |
| sold | DECIMAL(12,2) | |
| paid | DECIMAL(12,2) | |
| sold_ap | DECIMAL(12,2) | По контрактам АП |
| paid_ap | DECIMAL(12,2) | |
| sold_equip | DECIMAL(12,2) | |
| paid_equip | DECIMAL(12,2) | |
| debt_end | DECIMAL(12,2) | |
| advance_end | DECIMAL(12,2) | |
| plan_amount | DECIMAL(12,2) | План (из аналитики) |
| collectability | DECIMAL(5,2) | paid/sold × 100% |
| is_active | BOOLEAN | |
| import_run_id | UUID FK | |
| UNIQUE | (organization_id, year, month, import_run_id) | |

### import_runs, users, alerts, deals
Как в спецификации (раздел 4).

## Классификация контрактов

| Тип | Ключевые слова | Доля |
|-----|---------------|------|
| subscription | /П, услуг, оказан, абонент, обслуживан | ~70% |
| equipment | монтаж, поставк, оборудов, установк, СКУД, ГРЗ, ≥100K | ~20% |
| service | ремонт, техобслуж, сервис | ~5% |
| other | остальное | ~5% |

## API endpoints (MVP)

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | /api/v1/organizations | Список клиентов (пагинация, фильтры) |
| GET | /api/v1/organizations/{inn} | Карточка клиента |
| GET | /api/v1/organizations/{inn}/snapshots | Помесячная история |
| GET | /api/v1/organizations/{inn}/contracts | Договоры клиента |
| GET | /api/v1/dashboard/summary | Виджеты дашборда |
| GET | /api/v1/dashboard/mrr-trend | MRR за 12 месяцев |
| GET | /api/v1/dashboard/aging | Aging buckets |
| GET | /api/v1/billing/debtors | Список должников |
| GET | /api/v1/alerts | Открытые алерты |
| POST | /api/v1/import/upload | Загрузить файл 1С |
| GET | /api/v1/import/runs | Журнал импортов |

## UI-экраны (MVP)

1. **Дашборд CEO** — 4 виджета (выручка, долг, клиенты, собираемость) + 2 графика (MRR, aging) + таблица проблемных клиентов
2. **Реестр подписок** — PrimeVue DataTable: фильтры по менеджеру, статусу, диапазону АП, Payment Score. Поиск по названию/ИНН
3. **Карточка клиента** — реквизиты, объекты, договоры, история оплат (таблица + графики sold vs paid)
4. **Просрочки и должники** — aging buckets (0-30, 31-60, 61-90, 90+), цветовая кодировка
5. **Импорт** — загрузка файла, лог импорта, статистика

## Метрики (MVP)

| Метрика | Формула |
|---------|---------|
| MRR | SUM(monthly_ap) WHERE status=active |
| Collectability | SUM(paid_ap) / SUM(sold_ap) × 100% |
| Payment Score | on_time×40 + collectability×30 + tenure×20 + debt_ratio×10 |
| ARPU | MRR / active_clients |

## Дорожная карта

| Неделя | Задача |
|--------|--------|
| 1-2 | Парсер 1С + модель данных + первичная миграция из аналитики |
| 3 | API + JWT-авторизация |
| 4 | Реестр клиентов + карточка клиента (UI) |
| 5 | Просрочки + должники + Payment Score |
| 6 | Базовый дашборд (виджеты + графики) |
