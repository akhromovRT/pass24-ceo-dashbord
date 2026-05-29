<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import InputText from 'primevue/inputtext'
import Tag from 'primevue/tag'
import ProgressBar from 'primevue/progressbar'
import SelectButton from 'primevue/selectbutton'
import Select from 'primevue/select'
import MultiSelect from 'primevue/multiselect'
import DatePicker from 'primevue/datepicker'
import { useToast } from 'primevue/usetoast'
import { FilterMatchMode } from '@primevue/core/api'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { HeatmapChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, VisualMapComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useOrganizationsStore } from '../stores/organizations'
import SegmentBand from '../components/SegmentBand.vue'
import api from '../api/client'

use([HeatmapChart, GridComponent, TooltipComponent, VisualMapComponent, CanvasRenderer])

const store = useOrganizationsStore()
const router = useRouter()
const toast = useToast()
const search = ref('')
const page = ref(1)
const pageSize = 25

const statusOptions = [
  { label: 'Активен', value: 'active' },
  { label: 'Приостановлен', value: 'suspended' },
  { label: 'Отток', value: 'churned' },
  { label: 'Транзит', value: 'transit' },
  { label: 'Потенциальный', value: 'prospect' },
  { label: 'Поставщик', value: 'supplier' },
]

function statusSeverity(status: string): 'success' | 'secondary' | 'warn' | 'danger' | 'info' {
  if (status === 'active') return 'success'
  if (status === 'suspended') return 'warn'
  if (status === 'churned') return 'danger'
  if (status === 'prospect') return 'info'
  return 'secondary'
}

async function changeClientStatus(item: any, newStatus: string) {
  const prev = item.status
  if (newStatus === prev) return
  item.status = newStatus
  try {
    const updated = await store.updateOrganization(item.inn, { status: newStatus })
    if (updated) Object.assign(item, updated)
    const msg = (newStatus === 'churned' || newStatus === 'transit') && updated?.churn_month
      ? `Месяц отключения: ${fmtChurnMonth(updated.churn_month)}`
      : undefined
    toast.add({
      severity: 'success', summary: 'Статус обновлён',
      detail: msg, life: 3000,
    })
  } catch (e: any) {
    item.status = prev
    const detail = e?.response?.data?.detail || 'Изменения не сохранены'
    toast.add({
      severity: 'error', summary: 'Не удалось сменить статус',
      detail, life: 6000,
    })
  }
}

function toMonthIsoString(d: Date | null): string | null {
  if (!d) return null
  // Бэкенд нормализует до 1-го числа месяца, но отправляем уже нормализованную
  // дату в UTC-формате, чтобы избежать timezone-сдвига на бэке.
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`
}

async function changeChurnMonth(item: any, newDate: Date | null) {
  const prevIso = item.churn_month
  const newIso = toMonthIsoString(newDate)
  if (newIso === prevIso) return
  item.churn_month = newIso
  try {
    const updated = await store.updateOrganization(item.inn, { churn_month: newIso })
    if (updated) Object.assign(item, updated)
    toast.add({
      severity: 'success', summary: 'Месяц отключения обновлён',
      detail: newIso ? fmtChurnMonth(newIso) : 'очищен',
      life: 2500,
    })
  } catch (e: any) {
    item.churn_month = prevIso
    const detail = e?.response?.data?.detail || 'Изменения не сохранены'
    toast.add({
      severity: 'error', summary: 'Не удалось обновить месяц',
      detail, life: 5000,
    })
  }
}

function parseChurnMonth(val: string | null): Date | null {
  if (!val) return null
  // Сервер отдаёт ISO date (YYYY-MM-DD), парсим без timezone-сдвига.
  const [y, m] = val.split('-').map(Number)
  if (!y || !m) return null
  return new Date(y, m - 1, 1)
}

const mode = ref<'clients' | 'contracts' | 'registry' | 'matrix'>('clients')
const modeOptions = [
  { label: 'По клиентам', value: 'clients' },
  { label: 'Шахматка', value: 'matrix' },
  { label: 'По договорам', value: 'contracts' },
  { label: 'По реестру', value: 'registry' },
]

// Segments
const segmentsData = ref<any>(null)
const activeSegment = ref('all')

// Contracts mode state
const contracts = ref<any[]>([])
const contractsTotal = ref(0)
const contractsLoading = ref(false)
const contractSortBy = ref('org_name')
const contractSortDir = ref<'asc' | 'desc'>('asc')

// Clients mode sort state — поля и направление, которые шлются в /organizations.
const clientSortBy = ref<string | null>(null)
const clientSortDir = ref<'asc' | 'desc'>('asc')

// Registry mode state
const registryItems = ref<any[]>([])
const registryLoading = ref(false)
const registryFilters = ref<any>({
  global: { value: null, matchMode: FilterMatchMode.CONTAINS },
  company: { value: null, matchMode: FilterMatchMode.CONTAINS },
  object_name: { value: null, matchMode: FilterMatchMode.CONTAINS },
  inn: { value: null, matchMode: FilterMatchMode.CONTAINS },
  contract_1c: { value: null, matchMode: FilterMatchMode.CONTAINS },
  active_doc: { value: null, matchMode: FilterMatchMode.CONTAINS },
  cloud_url: { value: null, matchMode: FilterMatchMode.CONTAINS },
  object_number: { value: null, matchMode: FilterMatchMode.CONTAINS },
  objects_count: { value: null, matchMode: FilterMatchMode.EQUALS },
  object_type: { value: null, matchMode: FilterMatchMode.IN },
  address: { value: null, matchMode: FilterMatchMode.CONTAINS },
  city_region: { value: null, matchMode: FilterMatchMode.IN },
  doc_exchange: { value: null, matchMode: FilterMatchMode.IN },
})

// Matrix mode state
const matrix = ref<any>({ months: [], orgs: [], cells: [], year: 0 })
const matrixLoading = ref(false)
const matrixSearch = ref('')
const matrixSortMode = ref<'amount_desc' | 'name_asc'>('amount_desc')
const matrixSortOptions = [
  { label: 'По АП ↓', value: 'amount_desc' },
  { label: 'А → Я', value: 'name_asc' },
]

const objectTypeOptions = computed(() =>
  [...new Set(registryItems.value.map(r => r.object_type).filter(Boolean))].sort()
)
const cityOptions = computed(() =>
  [...new Set(registryItems.value.map(r => r.city_region).filter(Boolean))].sort()
)
const docExchangeOptions = computed(() =>
  [...new Set(registryItems.value.map(r => r.doc_exchange).filter(Boolean))].sort()
)

function loadClients() {
  store.fetch({
    search: search.value || undefined,
    sort_by: clientSortBy.value || undefined,
    sort_dir: clientSortDir.value,
    page: page.value,
    page_size: pageSize,
  })
}

async function loadContracts() {
  contractsLoading.value = true
  try {
    const res = await api.get('/contracts', {
      params: {
        search: search.value || undefined,
        sort_by: contractSortBy.value,
        sort_dir: contractSortDir.value,
        page: page.value,
        page_size: pageSize,
      },
    })
    contracts.value = res.data.items
    contractsTotal.value = res.data.total
  } finally {
    contractsLoading.value = false
  }
}

async function loadRegistry() {
  registryLoading.value = true
  try {
    const res = await api.get('/registry')
    registryItems.value = res.data.items
  } finally {
    registryLoading.value = false
  }
}

async function loadMatrix() {
  matrixLoading.value = true
  try {
    const res = await api.get('/dashboard/payment-matrix')
    matrix.value = res.data
  } finally {
    matrixLoading.value = false
  }
}

function loadData() {
  if (mode.value === 'clients') loadClients()
  else if (mode.value === 'contracts') loadContracts()
  else if (mode.value === 'matrix') loadMatrix()
  else loadRegistry()
}

onMounted(async () => {
  loadData()
  try {
    const res = await api.get('/billing/segments')
    segmentsData.value = res.data
  } catch {
    /* шапка сегментов не критична */
  }
})

let searchTimeout: ReturnType<typeof setTimeout>
watch(search, () => {
  clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => {
    if (mode.value === 'registry') {
      registryFilters.value.global.value = search.value || null
    } else {
      page.value = 1
      loadData()
    }
  }, 300)
})

watch(mode, () => {
  page.value = 1
  search.value = ''
  registryFilters.value.global.value = null
  clientSortBy.value = null
  clientSortDir.value = 'asc'
  matrixSearch.value = ''
  loadData()
})

// Сегмент «Должники» ведёт на отдельный реестр должников
watch(activeSegment, (v) => {
  if (v === 'debtors') {
    router.push('/debtors')
    activeSegment.value = 'all'
  }
})

const segmentMetrics = computed(() => {
  const s = segmentsData.value
  if (!s) return []
  return [
    { label: 'Клиентов', value: String(s.total) },
    { label: 'Объектов', value: s.objects_total != null ? String(s.objects_total) : '—' },
    { label: 'MRR план', value: formatCurrency(s.mrr_plan) },
    { label: 'Платят', value: String(s.paying) },
    { label: 'Частично', value: String(s.partial) },
    { label: 'Не платят', value: String(s.not_paying) },
  ]
})
const segmentButtons = computed(() => {
  const s = segmentsData.value
  return [
    { key: 'all', label: 'Реестр' },
    { key: 'debtors', label: `Должники${s ? ' · ' + s.debtors : ''} →` },
  ]
})

function onPage(event: any) {
  page.value = Math.floor(event.first / pageSize) + 1
  loadData()
}

function onSort(event: any) {
  const dir: 'asc' | 'desc' = event.sortOrder === -1 ? 'desc' : 'asc'
  if (mode.value === 'contracts') {
    const fieldMap: Record<string, string> = {
      org_name: 'org_name',
      monthly_amount: 'monthly_amount',
      contract_date: 'contract_date',
    }
    contractSortBy.value = fieldMap[event.sortField] || 'org_name'
    contractSortDir.value = dir
    page.value = 1
    loadContracts()
  } else if (mode.value === 'clients') {
    clientSortBy.value = event.sortField || null
    clientSortDir.value = dir
    page.value = 1
    loadClients()
  }
}

function onRowClick(event: any) {
  if (mode.value === 'clients') router.push(`/clients/${event.data.inn}`)
  else if (mode.value === 'contracts') router.push(`/clients/${event.data.org_inn}`)
  else router.push(`/clients/${event.data.inn}`)
}

function formatCurrency(value: number | null) {
  if (value == null) return '—'
  return new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }).format(value)
}

function formatDate(val: string | null) {
  if (!val) return '—'
  return new Date(val).toLocaleDateString('ru-RU')
}

function ensureProtocol(url: string | null | undefined): string {
  if (!url) return ''
  const trimmed = url.trim()
  if (/^https?:\/\//i.test(trimmed)) return trimmed
  return 'https://' + trimmed
}

const RU_MONTHS_SHORT = [
  'янв', 'фев', 'мар', 'апр', 'май', 'июн',
  'июл', 'авг', 'сен', 'окт', 'ноя', 'дек',
]
function fmtChurnMonth(val: string | null): string {
  if (!val) return '—'
  const d = new Date(val)
  return `${RU_MONTHS_SHORT[d.getMonth()]} ${d.getFullYear()}`
}

function debtSeverity(value: number | null): 'danger' | 'warn' | 'secondary' | undefined {
  if (!value || value <= 0) return 'secondary'
  if (value > 100000) return 'danger'
  if (value > 30000) return 'warn'
  return undefined
}

function contractStatusSeverity(status: string): 'success' | 'secondary' | 'danger' {
  if (status === 'active') return 'success'
  if (status === 'terminated') return 'danger'
  return 'secondary'
}

function docExchangeSeverity(v: string | null): 'success' | 'warn' | 'info' | 'secondary' {
  if (!v) return 'secondary'
  if (v === 'ЭДО') return 'success'
  if (v.toLowerCase().includes('бумаг')) return 'warn'
  return 'info'
}

const contractStatusLabel: Record<string, string> = {
  active: 'Активен',
  completed: 'Завершён',
  terminated: 'Расторгнут',
}

// --- Шахматка платежей ---
// Карта статусов для пометки в ячейке churn-месяца.
const STATUS_LABEL_SHORT: Record<string, string> = {
  churned: 'Отток',
  transit: 'Транзит',
}

// Отфильтрованный + отсортированный список клиентов матрицы.
// Меняем порядок строк → пересчитываем индексы (row) у cells/orgs.
const matrixFiltered = computed(() => {
  const orgs = matrix.value.orgs as any[]
  if (!orgs.length) return { orgs: [], cells: [] }

  const q = matrixSearch.value.trim().toLowerCase()
  let filtered = q
    ? orgs.filter(o => (o.name || '').toLowerCase().includes(q) || (o.inn || '').includes(q))
    : [...orgs]

  if (matrixSortMode.value === 'name_asc') {
    filtered.sort((a, b) => (a.name || '').localeCompare(b.name || '', 'ru'))
  }
  // amount_desc — backend уже отдаёт в таком порядке (monthly_ap desc nulls last)

  const oldIdx = new Map<string, number>()
  orgs.forEach((o, i) => oldIdx.set(o.id, i))
  const newIdx = new Map<string, number>()
  filtered.forEach((o, i) => newIdx.set(o.id, i))

  const cells = (matrix.value.cells as any[])
    .filter(c => {
      const org = orgs[c.row]
      return org && newIdx.has(org.id)
    })
    .map(c => {
      const org = orgs[c.row]
      return { ...c, row: newIdx.get(org.id)! }
    })

  return { orgs: filtered, cells }
})

// 22px на ряд — комфортно для шрифта 11px, без перекрытия меток.
// Без верхнего ограничения — пусть страница скроллится, лишь бы все клиенты были видны.
const matrixHeight = computed(() => Math.max(360, matrixFiltered.value.orgs.length * 22 + 90))
const matrixChartOption = computed(() => {
  const { orgs, cells } = matrixFiltered.value
  if (!orgs.length) return {}
  // Базовый слой heatmap — без churn-ячеек (их рендерим отдельным слоем).
  const churnSet = new Set<string>()
  orgs.forEach((o: any, i: number) => {
    if (o.churn_col != null) churnSet.add(`${i}:${o.churn_col}`)
  })
  const heatmapData = cells
    .filter((c: any) => !churnSet.has(`${c.row}:${c.col}`))
    .map((c: any) => [c.col, c.row, c.ratio == null ? null : Math.min(150, c.ratio)])
  // Отдельный слой — churn-ячейки с тёмно-красным фоном и пометкой статуса.
  const churnData = orgs
    .map((o: any, rowIdx: number) => ({ o, rowIdx }))
    .filter(({ o }) => o.churn_col != null)
    .map(({ o, rowIdx }) => ({
      value: [o.churn_col, rowIdx, 0],
      itemStyle: { color: '#b91c1c', borderColor: '#7f1d1d' },
      label: {
        show: true,
        formatter: STATUS_LABEL_SHORT[o.status] || 'Отток',
        color: '#fff',
        fontSize: 9,
        fontWeight: 'bold',
      },
    }))
  return {
    tooltip: {
      formatter: (p: any) => {
        const c = cells.find((cc: any) => cc.row === p.value[1] && cc.col === p.value[0])
        const org = orgs[p.value[1]]
        const month = matrix.value.months[p.value[0]]
        if (!c || !org) return ''
        const churnSuffix = (org.churn_col === p.value[0])
          ? `<br><span style="color:#b91c1c"><b>${STATUS_LABEL_SHORT[org.status] || 'Отток'}</b> с этого месяца</span>`
          : ''
        return `<b>${org.name}</b><br>${month}<br>План: <b>${formatCurrency(c.plan)}</b><br>Факт: <b>${formatCurrency(c.paid)}</b>` +
               (c.ratio != null ? `<br>Собираемость: <b>${c.ratio}%</b>` : '') + churnSuffix
      },
    },
    grid: { left: 240, right: 30, top: 30, bottom: 30 },
    xAxis: {
      type: 'category', data: matrix.value.months,
      position: 'top', splitArea: { show: true },
      axisLabel: { fontSize: 11 },
    },
    yAxis: {
      type: 'category',
      // inverse=true чтобы orgs[0] был наверху: amount_desc → крупнейший АП сверху,
      // А→Я → буква А сверху, ниже Б, В, …, Я в самом низу.
      inverse: true,
      data: orgs.map((o: any) => o.name.length > 32 ? o.name.substring(0, 30) + '…' : o.name),
      splitArea: { show: true },
      axisLabel: {
        fontSize: 11,
        width: 230,
        overflow: 'truncate',
        // interval=0 принудительно рисует каждую метку, без авто-пропуска через одну.
        interval: 0,
      },
    },
    visualMap: {
      // Слайдер легенды скрыт — пользователь просил убрать ползунок с процентами.
      // Цветовое отображение собираемости остаётся.
      show: false,
      min: 0, max: 100, calculable: false,
      inRange: { color: ['#fef2f2', '#fee2e2', '#fed7aa', '#fef3c7', '#d1fae5', '#86efac', '#22c55e'] },
      seriesIndex: 0,
    },
    series: [
      {
        type: 'heatmap',
        data: heatmapData,
        emphasis: { itemStyle: { borderColor: '#1e293b', borderWidth: 1 } },
        itemStyle: { borderColor: '#f1f5f9', borderWidth: 1 },
      },
      {
        type: 'heatmap',
        data: churnData,
        emphasis: { itemStyle: { borderColor: '#1e293b', borderWidth: 1 } },
        itemStyle: { borderColor: '#7f1d1d', borderWidth: 1 },
        // Этот слой статичный — visualMap его не трогает (seriesIndex: 0 выше).
      },
    ],
  }
})

function onMatrixClick(event: any) {
  if (event.componentType !== 'series') return
  const row = event.value?.[1]
  const org = matrixFiltered.value.orgs[row]
  if (org?.inn) router.push(`/clients/${org.inn}`)
}
</script>

<template>
  <div class="billing-view">
    <div class="billing-header">
      <h1>Реестр клиентов</h1>
      <div class="header-controls">
        <SelectButton v-model="mode" :options="modeOptions" optionLabel="label" optionValue="value" />
        <InputText
          v-if="mode !== 'matrix'"
          v-model="search"
          :placeholder="mode === 'clients' ? 'Поиск по имени или ИНН...' :
                       mode === 'contracts' ? 'Поиск по контрагенту, ИНН, договору...' :
                       'Глобальный поиск по реестру...'"
          class="search-input"
        />
        <InputText
          v-else
          v-model="matrixSearch"
          placeholder="Поиск клиента в шахматке..."
          class="search-input"
        />
      </div>
    </div>

    <SegmentBand
      v-if="segmentsData"
      :metrics="segmentMetrics"
      :segments="segmentButtons"
      v-model="activeSegment"
      class="segment-band-spacing"
    />

    <!-- Режим: По клиентам -->
    <DataTable
      v-if="mode === 'clients'"
      :value="store.items"
      :loading="store.loading"
      :lazy="true"
      :totalRecords="store.total"
      :rows="pageSize"
      :first="(page - 1) * pageSize"
      :sortField="clientSortBy || undefined"
      :sortOrder="clientSortDir === 'desc' ? -1 : 1"
      paginator
      stripedRows
      @page="onPage"
      @sort="onSort"
      @row-click="onRowClick"
      rowHover
      removableSort
      class="client-table"
    >
      <Column field="name_display" header="Клиент" sortable>
        <template #body="{ data }">{{ data.name_display || data.name_1c }}</template>
      </Column>
      <Column field="inn" header="ИНН" style="width: 130px" />
      <Column field="monthly_ap" header="АП/мес" sortable style="width: 130px">
        <template #body="{ data }">{{ formatCurrency(data.monthly_ap) }}</template>
      </Column>
      <Column field="total_debt" header="Долг" sortable style="width: 150px">
        <template #body="{ data }">
          <Tag :severity="debtSeverity(data.total_debt)">{{ formatCurrency(data.total_debt) }}</Tag>
        </template>
      </Column>
      <Column field="payment_score" header="Оценка" sortable style="width: 120px">
        <template #body="{ data }">
          <ProgressBar v-if="data.payment_score != null" :value="data.payment_score" :showValue="true" style="height: 20px" />
          <span v-else>—</span>
        </template>
      </Column>
      <Column field="status" header="Статус" sortable style="width: 170px">
        <template #body="{ data }">
          <div class="status-cell" @click.stop>
            <Tag
              :severity="statusSeverity(data.status)"
              class="status-dot"
              :title="data.status"
            />
            <Select
              :modelValue="data.status"
              :options="statusOptions"
              optionLabel="label"
              optionValue="value"
              @update:modelValue="(v: string) => changeClientStatus(data, v)"
              class="status-inline-select"
              size="small"
              :pt="{ root: { 'aria-label': 'Статус клиента' } }"
            />
          </div>
        </template>
      </Column>
      <Column field="churn_month" header="Отключён" sortable style="width: 150px">
        <template #body="{ data }">
          <div
            v-if="data.status === 'churned' || data.status === 'transit'"
            class="churn-edit-cell" @click.stop
          >
            <DatePicker
              :modelValue="parseChurnMonth(data.churn_month)"
              @update:modelValue="(v) => changeChurnMonth(data, (v as Date | null) ?? null)"
              view="month"
              dateFormat="mm/yy"
              :placeholder="'мес/год'"
              showIcon
              size="small"
              class="churn-inline-picker"
              :pt="{ pcInputText: { root: { 'aria-label': 'Месяц отключения' } } }"
            />
          </div>
          <span v-else class="muted">—</span>
        </template>
      </Column>
      <Column field="objects" header="Объекты" style="width: 90px" />
      <Column field="city_region" header="Город" style="width: 150px" />
    </DataTable>

    <!-- Режим: Шахматка -->
    <div v-else-if="mode === 'matrix'" class="matrix-card">
      <div class="matrix-title">
        <span>
          Шахматка платежей · {{ matrix.year || '—' }} · клиентов: {{ matrixFiltered.orgs.length }}<span v-if="matrixFiltered.orgs.length !== matrix.orgs.length"> / {{ matrix.orgs.length }}</span>
        </span>
        <span class="matrix-controls">
          <SelectButton
            v-model="matrixSortMode"
            :options="matrixSortOptions"
            optionLabel="label"
            optionValue="value"
            :allow-empty="false"
            size="small"
          />
        </span>
        <span class="hint">▶ клик по строке — карточка клиента · красная ячейка — месяц перехода в Отток/Транзит</span>
      </div>
      <v-chart
        v-if="matrixFiltered.orgs.length"
        :option="matrixChartOption"
        :style="{ height: matrixHeight + 'px' }"
        autoresize
        @click="onMatrixClick"
      />
      <div v-else-if="matrixLoading" class="empty-state">Загрузка…</div>
      <div v-else-if="matrixSearch" class="empty-state">По запросу «{{ matrixSearch }}» клиенты не найдены.</div>
      <div v-else class="empty-state">Нет клиентов для отображения.</div>
    </div>

    <!-- Режим: По договорам -->
    <DataTable
      v-else-if="mode === 'contracts'"
      :value="contracts"
      :loading="contractsLoading"
      :lazy="true"
      :totalRecords="contractsTotal"
      :rows="pageSize"
      :first="(page - 1) * pageSize"
      paginator
      stripedRows
      @page="onPage"
      @sort="onSort"
      @row-click="onRowClick"
      rowHover
      class="contract-table"
      scrollable
      scrollHeight="calc(100vh - 280px)"
    >
      <Column field="org_name" header="Контрагент" sortable style="min-width: 200px" />
      <Column field="org_inn" header="ИНН" style="width: 130px" />
      <Column field="raw_name" header="Договор" style="min-width: 180px">
        <template #body="{ data }">{{ data.raw_name || data.contract_number || '—' }}</template>
      </Column>
      <Column field="contract_date" header="Дата" sortable style="width: 110px">
        <template #body="{ data }">{{ formatDate(data.contract_date) }}</template>
      </Column>
      <Column field="monthly_amount" header="АП/мес" sortable style="width: 130px">
        <template #body="{ data }">{{ formatCurrency(data.monthly_amount) }}</template>
      </Column>
      <Column field="org_object_type" header="Тип объекта" style="width: 130px" />
      <Column field="status" header="Статус" style="width: 120px">
        <template #body="{ data }">
          <Tag :severity="contractStatusSeverity(data.status)">{{ contractStatusLabel[data.status] || data.status }}</Tag>
        </template>
      </Column>
      <Column field="org_cloud_url" header="Облако" style="width: 90px">
        <template #body="{ data }">
          <a v-if="data.org_cloud_url" :href="ensureProtocol(data.org_cloud_url)" target="_blank" @click.stop style="color: #6366f1">↗</a>
          <span v-else>—</span>
        </template>
      </Column>
      <Column field="org_system_number" header="№ сист." style="width: 90px" />
      <Column field="org_equipment" header="Оборудование" style="min-width: 150px" />
      <Column field="org_address" header="Адрес" style="min-width: 200px" />
    </DataTable>

    <!-- Режим: По реестру -->
    <DataTable
      v-else
      :value="registryItems"
      :loading="registryLoading"
      v-model:filters="registryFilters"
      filter-display="menu"
      :global-filter-fields="['company','inn','object_name','contract_1c','active_doc','cloud_url','object_number','object_type','address','city_region','doc_exchange']"
      stripedRows
      paginator
      :rows="25"
      :rows-per-page-options="[25, 50, 100, 250]"
      @row-click="onRowClick"
      rowHover
      class="registry-table"
      scrollable
      scroll-height="calc(100vh - 300px)"
      removableSort
    >
      <template #empty>Нет данных в реестре.</template>

      <Column field="company" header="Компания" sortable style="min-width: 220px" :show-filter-match-modes="false">
        <template #filter="{ filterModel, filterCallback }">
          <InputText v-model="filterModel.value" @input="filterCallback()" placeholder="Поиск..." />
        </template>
      </Column>

      <Column field="object_name" header="Объект (реестр)" sortable style="min-width: 180px" :show-filter-match-modes="false">
        <template #filter="{ filterModel, filterCallback }">
          <InputText v-model="filterModel.value" @input="filterCallback()" placeholder="Поиск..." />
        </template>
        <template #body="{ data }">{{ data.object_name || '—' }}</template>
      </Column>

      <Column field="inn" header="ИНН" sortable style="width: 130px" :show-filter-match-modes="false">
        <template #filter="{ filterModel, filterCallback }">
          <InputText v-model="filterModel.value" @input="filterCallback()" placeholder="ИНН..." />
        </template>
      </Column>

      <Column field="contract_1c" header="Договор 1С" sortable style="min-width: 220px" :show-filter-match-modes="false">
        <template #filter="{ filterModel, filterCallback }">
          <InputText v-model="filterModel.value" @input="filterCallback()" placeholder="Поиск..." />
        </template>
        <template #body="{ data }">
          <span class="truncate" :title="data.contract_1c">{{ data.contract_1c || '—' }}</span>
        </template>
      </Column>

      <Column field="active_doc" header="Активный документ" sortable style="min-width: 220px" :show-filter-match-modes="false">
        <template #filter="{ filterModel, filterCallback }">
          <InputText v-model="filterModel.value" @input="filterCallback()" placeholder="Поиск..." />
        </template>
        <template #body="{ data }">
          <span class="truncate" :title="data.active_doc">{{ data.active_doc || '—' }}</span>
        </template>
      </Column>

      <Column field="cloud_url" header="Ссылка на облако" sortable style="width: 130px" :show-filter-match-modes="false">
        <template #filter="{ filterModel, filterCallback }">
          <InputText v-model="filterModel.value" @input="filterCallback()" placeholder="Поиск..." />
        </template>
        <template #body="{ data }">
          <a v-if="data.cloud_url" :href="ensureProtocol(data.cloud_url)" target="_blank" @click.stop class="cloud-link">
            ↗ ссылка
          </a>
          <span v-else>—</span>
        </template>
      </Column>

      <Column field="object_number" header="№ объекта" sortable style="width: 110px" :show-filter-match-modes="false">
        <template #filter="{ filterModel, filterCallback }">
          <InputText v-model="filterModel.value" @input="filterCallback()" placeholder="№..." />
        </template>
        <template #body="{ data }">{{ data.object_number || '—' }}</template>
      </Column>

      <Column field="objects_count" header="Кол-во объектов" sortable style="width: 110px" data-type="numeric">
        <template #filter="{ filterModel, filterCallback }">
          <InputText v-model="filterModel.value" type="number" @input="filterCallback()" placeholder="N" />
        </template>
        <template #body="{ data }">{{ data.objects_count ?? '—' }}</template>
      </Column>

      <Column field="object_type" header="Тип объекта" sortable style="min-width: 150px" :show-filter-match-modes="false">
        <template #filter="{ filterModel, filterCallback }">
          <MultiSelect
            v-model="filterModel.value"
            :options="objectTypeOptions"
            @change="filterCallback()"
            placeholder="Любой"
            :max-selected-labels="2"
            style="min-width: 200px"
          />
        </template>
        <template #body="{ data }">
          <Tag v-if="data.object_type" :value="data.object_type" severity="info" />
          <span v-else>—</span>
        </template>
      </Column>

      <Column field="address" header="Адрес" sortable style="min-width: 220px" :show-filter-match-modes="false">
        <template #filter="{ filterModel, filterCallback }">
          <InputText v-model="filterModel.value" @input="filterCallback()" placeholder="Поиск..." />
        </template>
        <template #body="{ data }">
          <span class="truncate" :title="data.address">{{ data.address || '—' }}</span>
        </template>
      </Column>

      <Column field="city_region" header="Город/область" sortable style="width: 170px" :show-filter-match-modes="false">
        <template #filter="{ filterModel, filterCallback }">
          <MultiSelect
            v-model="filterModel.value"
            :options="cityOptions"
            @change="filterCallback()"
            placeholder="Любой"
            :max-selected-labels="2"
            style="min-width: 200px"
            filter
          />
        </template>
      </Column>

      <Column field="doc_exchange" header="Обмен документами" sortable style="width: 160px" :show-filter-match-modes="false">
        <template #filter="{ filterModel, filterCallback }">
          <MultiSelect
            v-model="filterModel.value"
            :options="docExchangeOptions"
            @change="filterCallback()"
            placeholder="Любой"
            style="min-width: 200px"
          />
        </template>
        <template #body="{ data }">
          <Tag v-if="data.doc_exchange" :value="data.doc_exchange" :severity="docExchangeSeverity(data.doc_exchange)" />
          <span v-else>—</span>
        </template>
      </Column>
    </DataTable>
  </div>
</template>

<style scoped>
.billing-view {
  padding: 1.5rem;
}

.billing-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
  gap: 1rem;
}

.billing-header h1 {
  margin: 0;
  font-size: 1.5rem;
  color: #1e293b;
  flex-shrink: 0;
}

.header-controls {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}

.search-input {
  width: 320px;
}

.segment-band-spacing {
  margin-bottom: 1rem;
}

.client-table,
.contract-table,
.registry-table {
  cursor: pointer;
}

.matrix-card {
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 1rem 1.25rem;
  overflow: auto;
}
.matrix-title {
  font-size: 0.95rem;
  font-weight: 600;
  color: #1e293b;
  margin-bottom: 0.75rem;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
}
.matrix-title .hint {
  font-weight: 400;
  font-size: 0.8rem;
  color: #94a3b8;
}
.matrix-controls {
  display: inline-flex;
  align-items: center;
}
.empty-state {
  padding: 2rem;
  text-align: center;
  color: #64748b;
}

.truncate {
  display: inline-block;
  max-width: 220px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: middle;
}

.cloud-link {
  color: #6366f1;
  text-decoration: none;
}
.cloud-link:hover {
  text-decoration: underline;
}
.churn-cell { color: #b45309; font-size: 0.85rem; }
.muted { color: #cbd5e1; }

.status-cell {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  cursor: default;
}
.status-cell .status-dot {
  flex-shrink: 0;
  width: 8px;
  height: 8px;
  min-width: 8px;
  padding: 0;
  border-radius: 50%;
}
.status-cell :deep(.p-select) {
  width: 100%;
  min-width: 0;
}
.status-cell :deep(.p-select-label) {
  padding: 0.25rem 0.4rem;
  font-size: 0.85rem;
}
.status-cell :deep(.p-select-dropdown) {
  width: 1.8rem;
}

.churn-edit-cell {
  cursor: default;
}
.churn-edit-cell :deep(.p-datepicker) {
  width: 100%;
  min-width: 0;
}
.churn-edit-cell :deep(.p-datepicker-input) {
  padding: 0.25rem 0.4rem;
  font-size: 0.85rem;
  width: 100%;
  min-width: 0;
}
.churn-edit-cell :deep(.p-datepicker-dropdown) {
  width: 1.8rem;
}
</style>
