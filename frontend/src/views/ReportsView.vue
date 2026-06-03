<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import SelectButton from 'primevue/selectbutton'
import Select from 'primevue/select'
import MultiSelect from 'primevue/multiselect'
import DatePicker from 'primevue/datepicker'
import InputText from 'primevue/inputtext'
import InputNumber from 'primevue/inputnumber'
import Checkbox from 'primevue/checkbox'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import { useToast } from 'primevue/usetoast'
import { useRoute, useRouter } from 'vue-router'
import api from '../api/client'

const toast = useToast()
const route = useRoute()
const router = useRouter()

// --- пресеты и каталоги колонок ---------------------------------------------

const presetOptions = [
  { label: 'Реестр должников', value: 'debtors' },
  { label: 'Дисциплина платежей', value: 'discipline' },
  { label: 'Состав показателя', value: 'composition' },
  { label: 'Платежи', value: 'payments' },
]

type MetricKey =
  | 'mrr_fact'
  | 'collected_current'
  | 'mrr_plan'
  | 'active_clients'
  | 'new_paid_curr_year'
  | 'new_paid_prev_month'
  | 'new_paid_curr_month'
  | 'stopped_since_year_start'
  | 'active_overdue'

type MetricOption = { value: MetricKey; label: string; period: 'month' | 'year' | 'none' }

const METRIC_OPTIONS: MetricOption[] = [
  { value: 'mrr_fact',                 label: 'MRR факт (за месяц)',          period: 'month' },
  { value: 'collected_current',        label: 'Сбор за месяц',                period: 'month' },
  { value: 'mrr_plan',                 label: 'MRR план',                     period: 'none' },
  { value: 'active_clients',           label: 'Активные клиенты',             period: 'none' },
  { value: 'new_paid_curr_year',       label: 'Новые за год',                 period: 'year' },
  { value: 'new_paid_prev_month',      label: 'Новые за прошлый месяц',       period: 'month' },
  { value: 'new_paid_curr_month',      label: 'Новые за текущий месяц',       period: 'month' },
  { value: 'stopped_since_year_start', label: 'Отток с начала года',          period: 'none' },
  { value: 'active_overdue',           label: 'Активные с просрочкой',         period: 'none' },
]

function metricPeriodKind(m: string | null): 'month' | 'year' | 'none' {
  return METRIC_OPTIONS.find(x => x.value === m)?.period ?? 'none'
}

const MONEY_METRICS = new Set(['mrr_fact', 'collected_current', 'mrr_plan'])

const COLUMN_CATALOG: Record<string, { key: string; label: string }[]> = {
  debtors: [
    { key: 'name', label: 'Клиент' },
    { key: 'inn', label: 'ИНН' },
    { key: 'manager', label: 'Менеджер' },
    { key: 'monthly_ap', label: 'АП/мес' },
    { key: 'total_debt', label: 'Долг' },
    { key: 'months_overdue', label: 'Месяцев просрочки' },
    { key: 'aging_bucket', label: 'Корзина' },
    { key: 'last_payment_date', label: 'Последний платёж' },
    { key: 'collectability', label: 'Собираемость, %' },
    { key: 'payment_score', label: 'Payment score' },
    { key: 'priority', label: 'Приоритет взыскания' },
    { key: 'city', label: 'Город' },
    { key: 'status', label: 'Статус' },
  ],
  discipline: [
    { key: 'name', label: 'Клиент' },
    { key: 'inn', label: 'ИНН' },
    { key: 'manager', label: 'Менеджер' },
    { key: 'monthly_ap', label: 'АП/мес' },
    { key: 'collectability', label: 'Собираемость, %' },
    { key: 'on_time', label: 'On-time, %' },
    { key: 'tendency', label: 'Тенденция' },
    { key: 'trend', label: 'Тренд' },
    { key: 'unpaid_streak', label: 'Неоплачено подряд, мес' },
    { key: 'payment_score', label: 'Payment score' },
    { key: 'total_debt', label: 'Долг' },
    { key: 'status', label: 'Статус' },
  ],
  composition: [
    { key: 'name', label: 'Клиент' },
    { key: 'inn', label: 'ИНН' },
    { key: 'manager', label: 'Менеджер' },
    { key: 'monthly_ap', label: 'АП/мес' },
    { key: 'status', label: 'Статус' },
    { key: 'city', label: 'Город' },
    { key: 'contribution', label: 'Вклад в показатель, ₽' },
    { key: 'first_payment_date', label: 'Дата первого платежа' },
    { key: 'last_payment_date', label: 'Дата последнего платежа' },
    { key: 'days_since_last', label: 'Дней с последнего платежа' },
  ],
  payments: [
    { key: 'doc_date', label: 'Дата платежа' },
    { key: 'org_name', label: 'Контрагент' },
    { key: 'inn', label: 'ИНН' },
    { key: 'amount', label: 'Сумма, ₽' },
    { key: 'raw_name', label: 'Назначение' },
    { key: 'allocated_periods', label: 'Зачтено за' },
    { key: 'manager', label: 'Менеджер' },
  ],
}

const statusOptions = [
  { label: 'Активен', value: 'active' },
  { label: 'Приостановлен', value: 'suspended' },
  { label: 'Отток', value: 'churned' },
  { label: 'Транзит', value: 'transit' },
  { label: 'Потенциальный', value: 'prospect' },
  { label: 'Поставщик', value: 'supplier' },
]
const bucketOptions = ['0-30', '31-60', '61-90', '90+']
const contractTypeOptions = [
  { label: 'Подписка', value: 'subscription' },
  { label: 'Оборудование', value: 'equipment' },
  { label: 'Услуги', value: 'service' },
  { label: 'Прочее', value: 'other' },
]
const sortDirOptions = [
  { label: '↓ убыв.', value: 'desc' },
  { label: '↑ возр.', value: 'asc' },
]

const CURRENCY_KEYS = new Set(['monthly_ap', 'total_debt', 'priority', 'contribution', 'amount'])
const PERCENT_KEYS = new Set(['collectability', 'on_time'])

// Минимальная ширина колонки — чтобы таблица имела предсказуемую ширину и
// скроллилась по горизонтали внутри своего контейнера, не растягивая страницу.
const COLUMN_WIDTH: Record<string, string> = {
  name: '15rem',
  inn: '8rem',
  manager: '10rem',
  monthly_ap: '8rem',
  total_debt: '9rem',
  months_overdue: '9rem',
  aging_bucket: '7rem',
  last_payment_date: '9rem',
  collectability: '9rem',
  on_time: '8rem',
  tendency: '8rem',
  trend: '6rem',
  unpaid_streak: '11rem',
  payment_score: '8rem',
  priority: '11rem',
  city: '11rem',
  status: '8rem',
  contribution: '12rem',
  first_payment_date: '11rem',
  days_since_last: '11rem',
}

function colMinWidth(key: string): string {
  return COLUMN_WIDTH[key] || '8rem'
}

// --- состояние --------------------------------------------------------------

const preset = ref<'debtors' | 'discipline' | 'composition' | 'payments'>('debtors')

const criteria = reactive({
  period_from: null as Date | null,
  period_to: null as Date | null,
  statuses: [] as string[],
  manager_id: null as string | null,
  aging_buckets: [] as string[],
  contract_types: [] as string[],
  city: '',
  min_debt: 0,
  columns: [] as string[],
  sort_by: null as string | null,
  sort_dir: 'desc',
  include_excluded: false,
  metric: null as MetricKey | null,
  period: null as string | null,
  // P3.0.4 (Софья 2026-05-28): точный диапазон дат и фильтр по контрагентам.
  // Применяются в пресете payments; для остальных пресетов backend их
  // игнорирует через ConfigDict(extra="ignore").
  date_from: null as Date | null,
  date_to: null as Date | null,
  organization_ids: [] as string[],
})

const controlValue = ref<number | null>(null)

const periodDate = computed<Date | null>({
  get() {
    if (!criteria.period) return null
    const kind = metricPeriodKind(criteria.metric)
    if (kind === 'year') return new Date(Number(criteria.period), 0, 1)
    const [y, m] = criteria.period.split('-').map(Number)
    if (!y || !m) return null
    return new Date(y, m - 1, 1)
  },
  set(d) {
    if (!d) {
      criteria.period = null
      return
    }
    const kind = metricPeriodKind(criteria.metric)
    criteria.period = kind === 'year'
      ? String(d.getFullYear())
      : `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
  },
})

const managers = ref<{ id: string; name: string }[]>([])
const templates = ref<any[]>([])
const selectedTemplate = ref<any>(null)

// Список организаций для фильтра «Контрагенты» в пресете payments (P3.0.4).
// Загружаем лениво — только при первом переключении на payments.
const organizationOptions = ref<{ value: string; label: string }[]>([])
const organizationsLoading = ref(false)
async function loadOrganizationsForFilter() {
  if (organizationOptions.value.length || organizationsLoading.value) return
  organizationsLoading.value = true
  try {
    // Берём страницу большего размера; в проде ~300 организаций — влезает.
    const res = await api.get('/organizations', { params: { page_size: 1000 } })
    const items = Array.isArray(res.data) ? res.data : res.data.items ?? []
    organizationOptions.value = items.map((o: any) => ({
      value: String(o.id),
      label: `${o.name_display || o.name_1c} (${o.inn})`,
    }))
  } finally {
    organizationsLoading.value = false
  }
}

const rows = ref<any[]>([])
const columns = ref<{ key: string; header: string }[]>([])
const total = ref(0)
const loading = ref(false)
const exporting = ref(false)

const saveDialog = ref(false)
const templateName = ref('')

const columnChoices = computed(() => COLUMN_CATALOG[preset.value])
const templatesForPreset = computed(() =>
  templates.value.filter(t => t.report_type === preset.value),
)

// --- загрузка справочников --------------------------------------------------

async function loadManagers() {
  try {
    managers.value = (await api.get('/users/options')).data
  } catch {
    /* список менеджеров не критичен */
  }
}

async function loadTemplates() {
  try {
    templates.value = (await api.get('/reports/templates')).data
  } catch {
    /* шаблоны не критичны */
  }
}

// --- сборка критериев -------------------------------------------------------

function monthStr(d: Date | null): string | null {
  if (!d) return null
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

function parseMonth(value: string | null): Date | null {
  if (!value) return null
  const [y, m] = value.split('-').map(Number)
  if (!y || !m) return null
  return new Date(y, m - 1, 1)
}

function buildCriteria() {
  const c: any = {
    period_from: monthStr(criteria.period_from),
    period_to: monthStr(criteria.period_to),
    statuses: criteria.statuses,
    manager_id: criteria.manager_id || null,
    aging_buckets: preset.value === 'debtors' ? criteria.aging_buckets : [],
    contract_types: criteria.contract_types,
    city: criteria.city || null,
    min_debt: criteria.min_debt || 0,
    columns: criteria.columns,
    sort_by: criteria.sort_by || null,
    sort_dir: criteria.sort_dir,
    include_excluded: criteria.include_excluded,
  }
  if (preset.value === 'composition') {
    c.metric = criteria.metric
    c.period = criteria.period
  }
  if (preset.value === 'payments') {
    c.date_from = isoDate(criteria.date_from)
    c.date_to = isoDate(criteria.date_to)
    c.organization_ids = criteria.organization_ids
  }
  return c
}

function isoDate(d: Date | null): string | null {
  if (!d) return null
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

// --- генерация и экспорт ----------------------------------------------------

async function runPreview() {
  loading.value = true
  controlValue.value = null
  try {
    const res = await api.post(`/reports/${preset.value}/preview`, buildCriteria())
    columns.value = res.data.columns
    rows.value = res.data.rows
    total.value = res.data.total
    if (preset.value === 'composition' && typeof res.data.control_value === 'number') {
      controlValue.value = res.data.control_value
    }
  } catch (e: any) {
    const detail = e?.response?.data?.detail ?? 'Не удалось построить отчёт'
    toast.add({ severity: 'error', summary: detail, life: 4000 })
  } finally {
    loading.value = false
  }
}

async function exportXlsx() {
  exporting.value = true
  try {
    const res = await api.post(`/reports/${preset.value}/export`, buildCriteria(), {
      responseType: 'blob',
    })
    const url = URL.createObjectURL(res.data)
    const link = document.createElement('a')
    link.href = url
    link.download = `${preset.value}-${new Date().toISOString().slice(0, 10)}.xlsx`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
    toast.add({ severity: 'success', summary: 'Файл выгружен', life: 2500 })
  } catch {
    toast.add({ severity: 'error', summary: 'Не удалось выгрузить файл', life: 4000 })
  } finally {
    exporting.value = false
  }
}

// --- шаблоны критериев ------------------------------------------------------

function applyTemplate(tpl: any) {
  if (!tpl) return
  preset.value = tpl.report_type
  const c = tpl.criteria || {}
  criteria.period_from = parseMonth(c.period_from)
  criteria.period_to = parseMonth(c.period_to)
  criteria.statuses = c.statuses || []
  criteria.manager_id = c.manager_id || null
  criteria.aging_buckets = c.aging_buckets || []
  criteria.contract_types = c.contract_types || []
  criteria.city = c.city || ''
  criteria.min_debt = c.min_debt || 0
  criteria.columns = c.columns || []
  criteria.sort_by = c.sort_by || null
  criteria.sort_dir = c.sort_dir || 'desc'
  criteria.include_excluded = !!c.include_excluded
  criteria.metric = c.metric || null
  criteria.period = c.period || null
  runPreview()
}

async function saveTemplate() {
  if (!templateName.value.trim()) return
  try {
    await api.post('/reports/templates', {
      name: templateName.value.trim(),
      report_type: preset.value,
      criteria: buildCriteria(),
    })
    saveDialog.value = false
    templateName.value = ''
    await loadTemplates()
    toast.add({ severity: 'success', summary: 'Шаблон сохранён', life: 2500 })
  } catch {
    toast.add({ severity: 'error', summary: 'Не удалось сохранить шаблон', life: 4000 })
  }
}

async function deleteTemplate() {
  if (!selectedTemplate.value) return
  try {
    await api.delete(`/reports/templates/${selectedTemplate.value.id}`)
    selectedTemplate.value = null
    await loadTemplates()
    toast.add({ severity: 'success', summary: 'Шаблон удалён', life: 2500 })
  } catch {
    toast.add({ severity: 'error', summary: 'Не удалось удалить шаблон', life: 4000 })
  }
}

// --- форматирование ячеек ---------------------------------------------------

function formatControlValue(v: number): string {
  if (criteria.metric && MONEY_METRICS.has(criteria.metric)) {
    return new Intl.NumberFormat('ru-RU', {
      style: 'currency', currency: 'RUB', maximumFractionDigits: 0,
    }).format(v)
  }
  return `${v} клиентов`
}

function formatCell(key: string, value: any): string {
  if (value === null || value === undefined || value === '') return '—'
  if (CURRENCY_KEYS.has(key)) {
    return new Intl.NumberFormat('ru-RU', {
      style: 'currency', currency: 'RUB', maximumFractionDigits: 0,
    }).format(value)
  }
  if (PERCENT_KEYS.has(key)) return `${value} %`
  if (key === 'last_payment_date' || key === 'first_payment_date') {
    return new Date(value).toLocaleDateString('ru-RU')
  }
  return String(value)
}

// --- реакции ----------------------------------------------------------------

watch(preset, () => {
  selectedTemplate.value = null
  criteria.columns = []
  criteria.sort_by = null
  criteria.aging_buckets = []
  if (preset.value !== 'composition') {
    criteria.metric = null
    criteria.period = null
  }
  if (preset.value === 'payments') {
    loadOrganizationsForFilter()
  }
  if (route.query.preset && route.query.preset !== preset.value) {
    router.replace({ query: {} })
  }
  runPreview()
})

function applyQueryComposition() {
  const q = route.query
  if (q.preset !== 'composition' || typeof q.metric !== 'string') return false
  const known = METRIC_OPTIONS.some(m => m.value === q.metric)
  if (!known) {
    toast.add({ severity: 'warn', summary: 'Неизвестный показатель', life: 3500 })
    return false
  }
  preset.value = 'composition'
  criteria.metric = q.metric as MetricKey
  criteria.period = typeof q.period === 'string' ? q.period : null
  return true
}

onMounted(() => {
  loadManagers()
  loadTemplates()
  // applyQueryComposition() переключает preset → triggers watch(preset) → runPreview()
  // вручную вызываем только если query-параметров не было
  const fromQuery = applyQueryComposition()
  if (!fromQuery) {
    runPreview()
  }
})
</script>

<template>
  <div class="reports-view">
    <div class="reports-header">
      <h1>Отчёты</h1>
      <SelectButton
        v-model="preset"
        :options="presetOptions"
        optionLabel="label"
        optionValue="value"
        :allowEmpty="false"
      />
    </div>

    <p class="preset-hint">
      {{ preset === 'debtors'
        ? 'Кого взыскивать: должники с приоритетом взыскания (долг × возраст × шанс возврата).'
        : preset === 'discipline'
        ? 'Кто соскальзывает в долг: собираемость, дисциплина и тренд по активным подписчикам.'
        : preset === 'payments'
        ? 'Реестр платежей с датой, контрагентом и зачётом по периодам. Выбирайте точный диапазон дат и нужных контрагентов — сверять с выгрузкой Ирины из 1С.'
        : 'Состав KPI-плитки дашборда: какие клиенты и суммы попали в показатель. Контрольная сумма в шапке должна совпадать с плиткой.' }}
    </p>

    <!-- Панель критериев -->
    <div class="criteria-card">
      <div class="criteria-grid">
        <label v-if="preset === 'composition'" class="field">
          <span>Показатель</span>
          <Select v-model="criteria.metric" :options="METRIC_OPTIONS"
                  optionLabel="label" optionValue="value"
                  placeholder="выберите" />
        </label>
        <label v-if="preset === 'composition' && metricPeriodKind(criteria.metric) !== 'none'"
               class="field">
          <span>Период</span>
          <DatePicker
            v-model="periodDate"
            :view="metricPeriodKind(criteria.metric) === 'year' ? 'year' : 'month'"
            :dateFormat="metricPeriodKind(criteria.metric) === 'year' ? 'yy' : 'mm/yy'"
            showButtonBar />
        </label>

        <!-- Платежи: точный диапазон дат + фильтр по контрагентам (P3.0.4) -->
        <label v-if="preset === 'payments'" class="field">
          <span>Дата платежа с</span>
          <DatePicker v-model="criteria.date_from" dateFormat="dd.mm.yy"
                      placeholder="любая" showButtonBar showIcon />
        </label>
        <label v-if="preset === 'payments'" class="field">
          <span>Дата платежа по</span>
          <DatePicker v-model="criteria.date_to" dateFormat="dd.mm.yy"
                      placeholder="любая" showButtonBar showIcon />
        </label>
        <label v-if="preset === 'payments'" class="field" style="grid-column: span 2">
          <span>Контрагенты</span>
          <MultiSelect v-model="criteria.organization_ids" :options="organizationOptions"
                       optionLabel="label" optionValue="value"
                       :loading="organizationsLoading"
                       placeholder="любой" filter
                       :maxSelectedLabels="3" />
        </label>
        <label class="field">
          <span>Период с</span>
          <DatePicker v-model="criteria.period_from" view="month" dateFormat="mm/yy"
                      placeholder="любой" showButtonBar />
        </label>
        <label class="field">
          <span>Период по</span>
          <DatePicker v-model="criteria.period_to" view="month" dateFormat="mm/yy"
                      placeholder="тек. месяц" showButtonBar />
        </label>
        <label class="field">
          <span>Статус клиента</span>
          <MultiSelect v-model="criteria.statuses" :options="statusOptions"
                       optionLabel="label" optionValue="value"
                       placeholder="любой" :maxSelectedLabels="2" />
        </label>
        <label class="field">
          <span>Менеджер</span>
          <Select v-model="criteria.manager_id" :options="managers"
                  optionLabel="name" optionValue="id"
                  placeholder="любой" showClear filter />
        </label>
        <label v-if="preset === 'debtors'" class="field">
          <span>Корзина просрочки</span>
          <MultiSelect v-model="criteria.aging_buckets" :options="bucketOptions"
                       placeholder="любая" :maxSelectedLabels="3" />
        </label>
        <label class="field">
          <span>Тип договора</span>
          <MultiSelect v-model="criteria.contract_types" :options="contractTypeOptions"
                       optionLabel="label" optionValue="value"
                       placeholder="любой" :maxSelectedLabels="2" />
        </label>
        <label class="field">
          <span>Город / регион</span>
          <InputText v-model="criteria.city" placeholder="любой" />
        </label>
        <label v-if="preset === 'debtors'" class="field">
          <span>Мин. сумма долга, ₽</span>
          <InputNumber v-model="criteria.min_debt" :min="0" :step="1000"
                       showButtons mode="decimal" />
        </label>
        <label class="field">
          <span>Колонки</span>
          <MultiSelect v-model="criteria.columns" :options="columnChoices"
                       optionLabel="label" optionValue="key"
                       placeholder="все" :maxSelectedLabels="3" />
        </label>
        <label class="field">
          <span>Сортировать по</span>
          <Select v-model="criteria.sort_by" :options="columnChoices"
                  optionLabel="label" optionValue="key"
                  placeholder="по умолчанию" showClear />
        </label>
        <label class="field">
          <span>Направление</span>
          <SelectButton v-model="criteria.sort_dir" :options="sortDirOptions"
                        optionLabel="label" optionValue="value" :allowEmpty="false" />
        </label>
        <label class="field field-check">
          <Checkbox v-model="criteria.include_excluded" :binary="true" inputId="excl" />
          <span>Учитывать исключённых из аналитики</span>
        </label>
      </div>

      <div class="criteria-actions">
        <div class="template-block">
          <Select v-model="selectedTemplate" :options="templatesForPreset"
                  optionLabel="name" placeholder="Сохранённый набор"
                  showClear class="template-select"
                  @update:modelValue="applyTemplate" />
          <Button label="Удалить" icon="pi pi-trash" severity="secondary" outlined
                  :disabled="!selectedTemplate" @click="deleteTemplate" />
          <Button label="Сохранить набор" icon="pi pi-bookmark" severity="secondary"
                  outlined @click="saveDialog = true" />
        </div>
        <div class="run-block">
          <Button label="Сформировать" icon="pi pi-refresh"
                  :loading="loading" @click="runPreview" />
          <Button label="Экспорт в Excel" icon="pi pi-file-excel" severity="success"
                  :loading="exporting" :disabled="!rows.length" @click="exportXlsx" />
        </div>
      </div>
    </div>

    <!-- Превью -->
    <DataTable
      :value="rows"
      :loading="loading"
      paginator
      :rows="25"
      :rowsPerPageOptions="[25, 50, 100]"
      stripedRows
      rowHover
      scrollable
      scrollHeight="flex"
      class="report-table"
    >
      <template #empty>Нет строк по заданным критериям.</template>
      <template #header>
        <div class="table-header-bar">
          <span class="row-count">Строк: {{ total }}</span>
          <span v-if="preset === 'composition' && controlValue !== null" class="control-value">
            Контроль:
            <b>{{ formatControlValue(controlValue) }}</b>
          </span>
        </div>
      </template>
      <Column
        v-for="col in columns"
        :key="col.key"
        :field="col.key"
        :header="col.header"
        sortable
        :style="{ minWidth: colMinWidth(col.key) }"
      >
        <template #body="{ data }">{{ formatCell(col.key, data[col.key]) }}</template>
      </Column>
    </DataTable>

    <!-- Диалог сохранения шаблона -->
    <Dialog v-model:visible="saveDialog" header="Сохранить набор критериев"
            modal :style="{ width: '24rem' }">
      <label class="dialog-field">
        <span>Название набора</span>
        <InputText v-model="templateName" autofocus
                   placeholder="напр. Крупные должники 90+"
                   @keyup.enter="saveTemplate" />
      </label>
      <template #footer>
        <Button label="Отмена" severity="secondary" text @click="saveDialog = false" />
        <Button label="Сохранить" icon="pi pi-check"
                :disabled="!templateName.trim()" @click="saveTemplate" />
      </template>
    </Dialog>
  </div>
</template>

<style scoped>
.reports-view {
  box-sizing: border-box;
  /* высота окна + overflow:hidden — отчёт всегда умещается на одной странице,
     страница не прокручивается ни по вертикали, ни по горизонтали */
  height: 100vh;
  overflow: hidden;
  min-width: 0;
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.reports-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}

.reports-header h1 {
  margin: 0;
  font-size: 1.5rem;
  color: #1e293b;
}

.preset-hint {
  margin: -0.25rem 0 0;
  color: #64748b;
  font-size: 0.85rem;
}

.criteria-card {
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  /* на низком окне панель критериев скроллится внутри себя,
     а не выталкивает страницу */
  min-height: 0;
  overflow-y: auto;
}

.criteria-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 1rem;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  font-size: 0.8rem;
  color: #475569;
}

.field span {
  font-weight: 600;
}

.field :deep(.p-component) {
  width: 100%;
}

.field-check {
  flex-direction: row;
  align-items: center;
  gap: 0.5rem;
  align-self: end;
}

.field-check span {
  font-weight: 500;
}

.criteria-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
  border-top: 1px solid #f1f5f9;
  padding-top: 1rem;
}

.template-block,
.run-block {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.template-select {
  min-width: 220px;
}

.report-table {
  /* таблица сохраняет рабочую высоту; при нехватке места сжимается панель
     критериев, а не таблица */
  flex: 1;
  min-height: 240px;
  min-width: 0;
  background: white;
  border-radius: 8px;
}

.row-count {
  font-size: 0.85rem;
  font-weight: 600;
  color: #475569;
}

.table-header-bar {
  display: flex; align-items: center; gap: 1rem; flex-wrap: wrap;
}
.control-value {
  margin-left: auto;
  font-size: 0.85rem; color: #475569;
}
.control-value b { color: #0f172a; font-weight: 700; }

.dialog-field {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  font-size: 0.85rem;
  color: #475569;
}

.dialog-field span {
  font-weight: 600;
}

.dialog-field :deep(.p-component) {
  width: 100%;
}
</style>
