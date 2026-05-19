# Дизайн: ручной ввод периода при импорте платежей

- **Дата:** 2026-05-19
- **Статус:** утверждён, готов к планированию
- **Область:** импорт банковской выписки и реестра «Оплата от покупателей»

## Проблема

При импорте платежей (`source_type=bank` и `source_type=payments`) период, за
который пришёл платёж, извлекается автоматически из назначения платежа
(`app/parser/period_extraction.py`). Когда в назначении периода нет или он
записан в нераспознаваемом формате, платёж сохраняется без периода. Для
импорта `payments` это означает, что AR-леджер разносит такой платёж по FIFO
или авансом, а не на нужный месяц — собираемость по периодам искажается.

Примеры из выписки `01.05.2026–18.05.2026`: 7 из 40 платежей без периода, в том
числе «НОРБИТ» (93 786 ₽) с явным «ЗА 05.2026Г» в назначении — формат `MM.YYYYГ`
с точкой парсер не ловит.

Нужен интерфейс, в котором при импорте пользователь сам указывает период для
платежей, где он не определён автоматически.

## Область и принципы

- Касается импортов `bank` и `payments`. `debt` и `registry` не затрагиваются.
- Только новые импорты. Дозаполнение периода у ранее импортированных платежей
  (исторический бакет «не определён») — вне области, отдельная задача.
- Один платёж — один месяц. Мультимесячное покрытие (платёж за N месяцев)
  не вводится: пользователь указывает первый месяц, остаток разносится штатной
  авансовой логикой `AllocationService._spill_advance`.
- Заполнение периода необязательное: пользователь может подтвердить импорт,
  оставив часть комбобоксов пустыми — такие платежи импортируются без периода,
  как сегодня.

## Поток: двухфазный импорт

Сейчас импорт — один синхронный `POST /import/upload`: загрузка → парсинг →
запись в БД. Для `bank`/`payments` он становится двухфазным:

```
Фаза 1 — ПРЕВЬЮ:  загрузка файла → парсинг → в БД НЕ пишем →
                  возвращаем список платежей с пометкой «период не определён»
Фаза 2 — КОММИТ:  пользователь заполнил комбобоксы → запись в БД
```

Состояние между фазами на сервере **не хранится**: коммит повторно принимает
тот же файл. Файлы маленькие (выписки 10–20 КБ, лимит 10 МБ), поэтому
staging-таблица, TTL и фоновая очистка не нужны. Коммит сверяет `file_hash`
с тем, что вернуло превью — защита от подмены файла между шагами.

`debt` и `registry` продолжают идти через `/import/upload` без изменений.

## Backend

### Эндпоинты (`app/api/v1/imports.py`)

`POST /import/upload` остаётся без изменений (обратная совместимость,
рабочий путь для `debt`/`registry`). Добавляются два эндпоинта:

**`POST /import/preview?source_type=bank|payments`**
- Принимает файл. Парсит (`parse_bank_statement` / `parse_payments_report`).
- В БД ничего не пишет, `ImportRun` не создаёт, `file_hash` не регистрирует.
- Делает раннюю проверку «файл уже импортирован» → HTTP 409.
- Возвращает JSON:
  ```
  {
    "file_hash": "<sha256>",
    "source_type": "bank" | "payments",
    "summary": { "total_payments": int, "total_amount": number,
                 "without_period": int },
    "payments": [
      { "index": int, "date": "YYYY-MM-DD", "amount": number,
        "counterparty": str, "inn": str, "description": str,
        "detected_period": { "year": int, "month": int } | null }
    ]
  }
  ```
- `index` — порядковый номер платежа в файле (0..N-1), стабильный ключ для
  сопоставления оверрайдов при коммите.

**`POST /import/commit?source_type=bank|payments`**
- Принимает: файл (повторно), `file_hash` (сверка с превью), `period_overrides`
  — объект `{ "<index>": { "year": int, "month": int } }`.
- Re-парсит файл, сверяет `file_hash`; при расхождении — HTTP 400.
- Применяет оверрайды: для платежа с данным `index` проставляет период.
- Дальше — штатные `ImportService.process_bank_import` /
  `process_payments_report` (создание `ImportRun`, документов, пересчёт леджера).

### Модель данных

Новая колонка в `app/models/document.py`:

```python
period_manual: bool = Field(default=False)
```

Миграция Alembic (одна колонка, `server_default='false'`, downgrade — drop).

При применении оверрайда в commit-пути: `period_year` / `period_month` ←
из комбобокса, `period_manual = True`. Платежи, у которых период определил
парсер или которые остались без периода, — `period_manual = False`.

### Применение оверрайдов

В dataclass `PaymentInfo` (`app/parser/bank_statement.py`) добавляется поле
`period_manual: bool = False`.

Оверрайды применяются к `ParsedPayment.payment_info` в commit-эндпоинте до
передачи в `ImportService`. Для платежа с индексом `i` и оверрайдом
`{year, month}`: `payment_info.period_year = year`,
`payment_info.period_month = month`, `payment_info.periods = [(year, month)]`,
`payment_info.period_manual = True`.

`ImportService.process_bank_import` при создании `Document` пишет
`period_manual = p.payment_info.period_manual` — так запись узнаёт о ручном
вводе без отдельного канала данных.

### AllocationService

В `recompute_for_organization` (`app/services/allocation_service.py`) ветка
«явные периоды из назначения» строится на `extract_periods(raw_name)`.
Источник явного периода становится приоритетным от ручного ввода:

```python
ep = extract_periods(payment.raw_name or "", payment.doc_date or date.today())
if payment.period_manual and payment.period_year and payment.period_month:
    ep.periods = [(payment.period_year, payment.period_month)]
```

Остальная лестница (FIFO, аванс, нераспознанный остаток) не меняется.

**Почему отдельный флаг `period_manual`, а не просто `period_year/month`:**
`Document.period_year/period_month` уже заполняются парсером, иногда мусором
(например, «04/2024», ошибочно пойманное из номера договора `N10239-/04/2024`).
Без флага леджер не отличит надёжный ручной ввод от ложного срабатывания
regex. `period_manual = True` означает «период подтверждён человеком,
доверять безусловно».

**`bank`-импорт:** период сохраняется так же (`period_manual = True`), но на
леджер не влияет — контракт `BANK-IMPORT` сервис аллокаций не читает. Решение
осознанное: данные пишутся единообразно, и при возможном будущем подключении
`BANK-IMPORT` к леджеру период уже на месте.

## Frontend (`frontend/src/views/ImportView.vue`)

Для `source_type` ∈ {`bank`, `payments`} после выбора файла:

1. Вызов `POST /import/preview`.
2. Если `summary.without_period == 0` → сразу `POST /import/commit` без
   оверрайдов. Для пользователя поведение как сегодня.
3. Если `without_period > 0` → **шаг ревью**: таблица платежей без периода
   (`detected_period == null`) с колонками дата, контрагент, сумма, назначение
   и комбобоксом периода у каждой строки. Кнопки «Подтвердить импорт» и
   «Отмена».
4. Комбобокс — `PrimeVue DatePicker` с `view="month"`, `dateFormat="mm/yy"`,
   пустой по умолчанию. Диапазон лет — текущий ±1.
5. По «Подтвердить импорт» → `POST /import/commit` с заполненными оверрайдами
   (пустые комбобоксы в `period_overrides` не попадают).

`debt` / `registry` — путь без изменений (`/import/upload`, авто-загрузка).

Состояние во вью: `phase: 'idle' | 'review' | 'done'`, `previewData`,
выбранный файл (для повторной отправки в commit).

## Попутный фикс парсера периодов

`app/parser/period_extraction.py` не распознаёт формат `MM.YYYY` с точкой
(«ЗА 05.2026Г»). Добавляется regex по образцу `_SLASH_RE` с теми же
guard-условиями (negative lookbehind/lookahead), чтобы не цеплять даты внутри
`ДД.ММ.ГГГГ` и номеров договоров:

```python
_DOT_RE = re.compile(r"(?<![\d/\-.])(\d{1,2})\s*\.\s*(20\d{2})(?![\d/.])")
```

Обрабатывается в `extract_periods` рядом со slash-форматом. Чем больше период
ловит парсер, тем реже нужен ручной шаг.

## Обработка ошибок и крайние случаи

- Превью без коммита → в БД ничего не записано, `file_hash` не зарегистрирован,
  очистка не требуется (stateless).
- Файл уже импортирован → HTTP 409 на превью (рано) и на коммите.
- Файл при коммите не совпадает с превью (`file_hash`) → HTTP 400.
- Часть комбобоксов пуста → соответствующие платежи импортируются без периода
  (`period_manual = False`), ведут себя как сегодня.
- Оверрайд с `index`, которого нет среди распарсенных строк → игнорируется.
- Невалидный месяц/год в оверрайде → HTTP 422 (валидация Pydantic-схемы).

## Тестирование

Backend:
- `preview` возвращает корректный список платежей и `without_period`;
  не создаёт `ImportRun`.
- `preview` отдаёт 409 на повторный файл.
- `commit` применяет оверрайды: `Document.period_year/month/period_manual`
  проставлены; `commit` отдаёт 400 при несовпадении `file_hash`.
- `AllocationService` чтит `period_manual` — платёж с ручным периодом
  разносится на указанный месяц (basis `EXPLICIT_PERIOD`).
- Миграция Alembic up/down изолированно (временная SQLite).
- `period_extraction`: формат `MM.YYYYГ` распознаётся; `ДД.ММ.ГГГГ` и номера
  договоров по-прежнему не дают ложных периодов.
- Существующие тесты `/import/upload`, `test_bank_import_service.py`,
  `test_allocation_service.py`, `test_import_dedup.py` остаются зелёными.

Frontend: `vue-tsc` чисто, сборка успешна.

## Вне области

- Дозаполнение периода у уже импортированных платежей.
- Мультимесячное покрытие одним платежом (явный ввод диапазона).
- Подключение контракта `BANK-IMPORT` к AR-леджеру.

## Затрагиваемые файлы

- `backend/app/api/v1/imports.py` — эндпоинты `preview`, `commit`.
- `backend/app/services/import_service.py` — запись `period_manual` в
  `Document`.
- `backend/app/parser/bank_statement.py` — поле `period_manual` в `PaymentInfo`.
- `backend/app/models/document.py` — колонка `period_manual`.
- `backend/alembic/versions/` — новая миграция.
- `backend/app/services/allocation_service.py` — приоритет ручного периода.
- `backend/app/parser/period_extraction.py` — фикс `MM.YYYY`.
- `frontend/src/views/ImportView.vue` — двухфазный поток, шаг ревью.
- `backend/tests/` — новые и обновлённые тесты.
