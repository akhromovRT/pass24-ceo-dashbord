# Дизайн: Drill-down с плиток Dashboard в раздел «Отчёты»

**Дата:** 2026-05-20
**Статус:** Approved — готов к плану

## Цель

Клик по любой из 8 KPI-плиток на Dashboard открывает раздел «Отчёты»
с преднастроенным фильтром, который раскрывает состав показателя:
какие компании и суммы попали в это число. Контрольная сумма drill-down
совпадает со значением плитки — это инвариант, гарантированный тестом.

## Сценарий пользователя

1. CEO открывает Dashboard, видит «MRR факт · апрель 2026: 3 720 480 ₽».
2. Хочет понять: какие 25 клиентов это дали и сколько каждый.
3. Кликает по плитке. Открывается `/reports?preset=composition&metric=mrr_fact&period=2026-04`.
4. В разделе «Отчёты» автоматически выбран пресет «Состав показателя»,
   подставлены показатель «MRR факт» и период «апрель 2026», запущен preview.
5. В шапке таблицы видна контрольная сумма «3 720 480 ₽ · 25 клиентов»,
   совпадающая с плиткой. Дальше CEO может донастроить фильтры
   (например, оставить только клиентов одного менеджера), сохранить
   шаблон, выгрузить .xlsx.

## Каталог метрик

8 KPI-плиток дашборда переводятся в drill-down. Ключ `metric` и параметр
`period` — единый контракт URL.

| Плитка | `metric` | Период | Источник | Контрольное значение |
|---|---|---|---|---|
| MRR факт · {prev_month} | `mrr_fact` | `YYYY-MM` (= `summary.fact_month`) | Σ `payment_allocations.allocated_amount` по `monthly_charges` с year/month = period; только неисключённые организации | сумма колонки «Собрано», ₽ |
| MRR план | `mrr_plan` | — | Σ `organizations.monthly_ap` со статусом `ACTIVE`, неисключённые | сумма колонки «АП/мес», ₽ |
| Сбор · {current_month} | `collected_current` | `YYYY-MM` (= `summary.current_month_label`) | то же, что `mrr_fact`, период — текущий месяц | сумма колонки «Собрано», ₽ |
| Активные клиенты | `active_clients` | — | count `organizations` со статусом `ACTIVE`, неисключённые | количество строк |
| Новые за год | `new_paid_curr_year` | `YYYY` (= `today.year`) | клиенты, у которых `MIN(documents.doc_date)` (тип `PAYMENT`) попал в указанный год | количество строк |
| Новые · {prev_month} | `new_paid_prev_month` | `YYYY-MM` (= `summary.fact_month`) | то же, но в указанный месяц | количество строк |
| Новые · {current_month} | `new_paid_curr_month` | `YYYY-MM` (= `summary.current_month_label`) | то же | количество строк |
| Отток с начала года | `stopped_since_year_start` | — (фиксированный диапазон: `01.01.{today.year}` ≤ last_payment ≤ `today − 60 дней`) | клиенты с последним платежом в этом году, но >60 дней назад | количество строк |

**Не входит в drill-down:**
- Плитка «Долг» — оставляем как есть. Drill-down уже работает через
  клик по графику «Структура долга» → `/debtors?bucket=...`.
- Плитка «Churn rate» — производная (отношение `stopped / paying_base`).
  Сам список — это drill-down метрики `stopped_since_year_start`,
  на которую и ссылается соседняя плитка «Отток».

## Контракт URL

```
/reports?preset=composition&metric=<key>&period=<YYYY или YYYY-MM>
```

Параметр `period` парсится по типу метрики:
- год для `new_paid_curr_year`,
- месяц `YYYY-MM` для `mrr_fact`, `collected_current`, `new_paid_prev_month`, `new_paid_curr_month`,
- игнорируется для `mrr_plan`, `active_clients`, `stopped_since_year_start`.

Если `metric` неизвестен → toast «Неизвестный показатель», откат к
дефолтному пресету `debtors`. Если `period` нельзя распарсить → берём
безопасный дефолт (None / прошлый месяц).

## Архитектура

### Backend

**Новый файл `backend/app/services/composition_service.py`** — отдельный
модуль рядом с `report_service.py`. Логика композиции
концептуально отделена от «отчётов по критериям»:

```
composition_service
├─ COMPOSITION_COLUMNS: list[tuple[str, str]]   # полный каталог
├─ _COLS_BY_METRIC: dict[str, list[str]]        # жёсткая матрица
├─ build_composition_report(session, criteria) -> list[dict]
└─ control_value_for(metric, rows) -> float | int
```

**Рефакторинг `dashboard.py`:** общие helpers выносятся в
`backend/app/services/dashboard_service.py`:

- `_excl()`
- `_plan_mrr_total(session)`
- `_collected_by_charge_month(session)`
- `_accrued_by_month(session)`
- `_first_pay_rows(session)` (новая обёртка над существующим запросом
  `first_pay_rows`)
- `_last_pay_rows(session)` (то же)

`dashboard.py` импортирует их и использует. `composition_service` — то же.
Это гарантирует, что цифры на дашборде и в drill-down считаются одним
кодом. Защита от регресса — `test_dashboard_service.py`.

**Расширение `ReportCriteria`** (`backend/app/services/report_service.py`):

```python
class ReportCriteria(BaseModel):
    model_config = ConfigDict(extra="ignore")
    # ... существующие поля ...
    metric: str | None = None      # только для composition
    period: str | None = None      # "YYYY" или "YYYY-MM", только для composition
```

Существующие пресеты `debtors`/`discipline` игнорируют новые поля.

**Расширение диспетчера** (`report_service._BUILDERS`):

```python
_BUILDERS = {
    "debtors": build_debtors_report,
    "discipline": build_discipline_report,
    "composition": build_composition_report,
}

REPORTS["composition"] = {
    "title": "Состав показателя",
    "columns": COMPOSITION_COLUMNS,
}
```

`columns_for("composition", criteria)` возвращает подмножество из
`_COLS_BY_METRIC[criteria.metric]`. Заголовки динамические: для
`contribution` подставляется месяц («Собрано за апрель 2026, ₽»).

**API:** ничего нового. Существующие эндпоинты `/reports/{type}/preview`
и `/reports/{type}/export` принимают `composition` через каталог
`REPORTS`. Ответ preview расширяется одним полем:

```json
{
  "columns": [...],
  "rows": [...],
  "total": 25,
  "control_value": 3720480.0   // ₽ для денежных, count для количественных
}
```

Для пресетов `debtors`/`discipline` `control_value` не возвращается
(остаётся ключ только в composition-ветке) — добавление поля не
ломает существующие клиенты, т.к. они его не читают.

### Frontend

**`frontend/src/components/KpiTile.vue`** — опциональный prop `to`:

```ts
import type { RouteLocationRaw } from 'vue-router'

const props = defineProps<{
  label: string
  value: string
  sub?: string
  accent?: 'primary' | 'danger' | 'warn' | 'success' | 'neutral'
  pct?: number | null
  hint?: string
  to?: RouteLocationRaw          // новое
}>()
```

Если `to` задан — корневой элемент рендерится как `<router-link>` с тем
же classList, добавляется класс `kpi-tile--clickable` (cursor: pointer,
лёгкий hover-эффект — `transform: translateY(-1px)` и углубление тени).
В подсказку (tooltip) добавляется фраза «Кликните, чтобы увидеть состав».

**`frontend/src/views/DashboardView.vue`** — хелпер
`compositionLink(metric: string, period?: string)` возвращает объект
для `to`:

```ts
function compositionLink(metric: string, period?: string) {
  return {
    path: '/reports',
    query: {
      preset: 'composition',
      metric,
      ...(period ? { period } : {}),
    },
  }
}
```

Привязка к плиткам — добавление `:to` в JSX каждой из 8 KpiTile.

**`frontend/src/views/ReportsView.vue`** — расширения:

1. `presetOptions` пополняется `{ label: 'Состав показателя', value: 'composition' }`.
2. `COLUMN_CATALOG.composition` — полный набор колонок (`name`, `inn`,
   `manager`, `monthly_ap`, `status`, `city`, `contribution`,
   `first_payment_date`, `last_payment_date`, `days_since_last`).
3. `criteria` пополняется полями `metric: string | null` и
   `period: string | null`.
4. Парсинг query на `onMounted`:
   - если `route.query.preset === 'composition'` —
     `preset.value = 'composition'`, `criteria.metric = query.metric`,
     `criteria.period = query.period`, `runPreview()`;
   - если `metric` не из каталога — toast «Неизвестный показатель»,
     откат к `debtors`.
5. Когда `preset === 'composition'`, в панели критериев:
   - **показываются:** Select «Показатель» (7 опций), DatePicker «Период»
     (`view="month"` для месячных метрик, `view="year"` для `new_paid_curr_year`),
     общие фильтры (менеджер, статус, тип договора, город, колонки,
     сортировка, исключённые);
   - **скрываются:** «Корзина просрочки», «Мин. сумма долга»
     (они только для `debtors`).
6. Шапка таблицы получает блок «Контроль показателя» — берёт
   `control_value` из ответа preview, форматирует через тот же `Intl`
   что и плитка (₽ или штуки), показывает рядом с «Строк: N».
7. При ручной смене пресета через SelectButton —
   `router.replace({ query: {} })` чтобы убрать «зомби-параметры» из URL.
8. `buildCriteria()` дописывает поля `metric` и `period`
   (только для composition; для других пресетов не вкладывает).

## Поток данных (для одной плитки)

```
DashboardView                        ReportsView                    Backend
─────────────                        ───────────                    ───────
KpiTile :to="compositionLink(        ←──── router.push ────→
  'mrr_fact', '2026-04')"            onMounted: парсит query
                                     preset=composition
                                     criteria.metric=mrr_fact
                                     criteria.period=2026-04
                                     runPreview() ───POST /reports/composition/preview───→
                                                                    build_composition_report
                                                                      match metric:
                                                                        case mrr_fact:
                                                                          orgs = active+excl
                                                                          allocs = по period
                                                                          rows = ...
                                                                      control_value = sum(contribution)
                                     ←─── {columns, rows, total, control_value} ──
                                     DataTable + шапка с контролем
```

## Обработка ошибок

- Неизвестный `metric` (URL или прямой ввод) → backend 400, frontend toast.
- Невалидный `period` → backend возвращает пустой результат, `control_value=0`.
- Будущий месяц/год → пустой результат, без ошибки.
- Расхождение с плиткой (например, `include_excluded=true`) — ожидаемо,
  на UI просто видно «Контроль: ₽X (плитка: ₽Y)».
- Пустая выборка → стандартное «Нет строк по заданным критериям»,
  `control_value=0`.

## Авторизация и безопасность

Эндпоинты идут через тот же `router = APIRouter(...,
dependencies=[Depends(get_current_user)])` в `reports.py` — ADR-011
закрывает все data-маршруты. Никаких новых guard'ов не нужно.

## Миграции

**Не требуются.** Все 7 метрик считаются из уже существующих таблиц
(`organizations`, `documents`, `monthly_charges`, `payment_allocations`).
Поля `metric` и `period` живут только в pydantic-схеме и в JSON-колонке
`report_templates.criteria` (она уже свободна).

## Производительность

Самая «тяжёлая» метрика — `mrr_fact` за конкретный месяц:
один JOIN `payment_allocations × monthly_charges × organizations` с
WHERE по `(year, month)`. На текущих объёмах (≈270 активных клиентов,
≈10 000 платежей) запрос укладывается в существующие индексы
(`monthly_charges.organization_id`, `payment_allocations.monthly_charge_id`).
Пагинация и lazy-loading не нужны.

## Тесты

**Backend (`backend/tests/`):**

- `test_composition_service.py` — unit-тесты builder'а, по тест-кейсу
  на каждую из 7 метрик: структура строк, фильтрация (excluded,
  manager_id), `control_value`, сортировка по умолчанию.
- `test_api_reports.py` (расширение):
  - POST `/reports/composition/preview` с валидным `metric` → 200,
    наличие `control_value`;
  - с невалидным `metric` → 400;
  - экспорт `.xlsx` → корректный openpyxl-файл;
  - сохранение/загрузка шаблона с `report_type=composition`.
- `test_composition_matches_dashboard.py` — **ключевой тест-инвариант.**
  Поднимает реалистичную фикстуру и для каждой из 7 применимых метрик:
  - GET `/dashboard/summary` → значение под нужным ключом;
  - POST `/reports/composition/preview` → `control_value`;
  - `assert abs(summary - control) < 0.01` (или равенство для count).
- `test_dashboard_service.py` — короткие проверки helpers после выноса
  в `services/dashboard_service.py` (защита от регресса).

**Frontend:**
- `vue-tsc` чисто, `vite build` успешен;
- ручная проверка в браузере (DoD): клик по каждой из 7 плиток,
  совпадение контрольной суммы, очистка query при ручной смене пресета,
  экспорт в Excel, сохранение шаблона.

**Ожидаемая дельта:** 173 → ~191 passed (+18 тестов).

## Что НЕ входит в скоуп

- Drill-down с плитки «Долг» (уже работает через aging-чарт).
- Drill-down с плитки «Churn rate» (производная от `stopped`).
- Серверная пагинация в composition (для ≤300 строк не нужна).
- Новые типы агрегатов в шапке кроме `control_value` (например, «средний
  чек», «медиана» — обсуждаемо отдельно, если попросят).

## Файлы (создание / правка)

**Создаются:**
- `backend/app/services/composition_service.py`
- `backend/app/services/dashboard_service.py` (рефакторинг helpers)
- `backend/tests/test_composition_service.py`
- `backend/tests/test_composition_matches_dashboard.py`
- `backend/tests/test_dashboard_service.py`

**Правятся:**
- `backend/app/api/v1/dashboard.py` (импорт helpers вместо локальных)
- `backend/app/api/v1/reports.py` (косвенно — через расширение каталога)
- `backend/app/services/report_service.py` (поля `metric`/`period`
  в `ReportCriteria`, регистрация `composition` в `REPORTS`/`_BUILDERS`)
- `backend/tests/test_api_reports.py` (новые кейсы)
- `frontend/src/components/KpiTile.vue` (prop `to`)
- `frontend/src/views/DashboardView.vue` (`compositionLink`, `:to` на плитках)
- `frontend/src/views/ReportsView.vue` (третий пресет, парсинг query,
  контрольная сумма)

## Связанные документы

- `agent_docs/adr.md` — ADR-011 (router-level auth dependency), ADR-013 (модуль «Отчёты»).
- `agent_docs/guides/dashboard-metrics.md` — памятка по плиткам (8 метрик).
- `docs/superpowers/specs/2026-05-18-subscription-ar-ledger-design.md` — основа AR-леджера.
- `docs/superpowers/specs/2026-05-15-ceo24-screens-redesign-design.md` — редизайн дашборда (откуда взялись текущие плитки).
