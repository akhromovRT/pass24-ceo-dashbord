<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import TreeTable from 'primevue/treetable'
import Tag from 'primevue/tag'
import Select from 'primevue/select'
import SelectButton from 'primevue/selectbutton'
import InputText from 'primevue/inputtext'
import Textarea from 'primevue/textarea'
import Button from 'primevue/button'
import { useToast } from 'primevue/usetoast'
import { useConfirm } from 'primevue/useconfirm'
import api from '../api/client'
import SegmentBand from '../components/SegmentBand.vue'

const router = useRouter()
const route = useRoute()
const toast = useToast()
const confirm = useConfirm()

const mode = ref<'registry' | 'source'>(
  route.query.mode === 'source' ? 'source' : 'registry'
)
const modeOptions = [
  { label: 'Реестр должников', value: 'registry' },
  { label: '1С-вид', value: 'source' },
]
watch(mode, v => {
  router.replace({ query: { ...route.query, mode: v } })
  if (v === 'source' && !sourceData.value) loadSource()
})

// --- Реестр должников (старая логика) ---
const debtors = ref<any[]>([])
const loading = ref(true)
const bucket = ref<string>(
  typeof route.query.bucket === 'string' ? route.query.bucket : 'all'
)

const statusOptions = [
  { label: 'Активен', value: 'active' },
  { label: 'Приостановлен', value: 'suspended' },
  { label: 'Отток', value: 'churned' },
  { label: 'Транзит', value: 'transit' },
  { label: 'Потенциальный', value: 'prospect' },
  { label: 'Поставщик', value: 'supplier' },
]

onMounted(async () => {
  try {
    const res = await api.get('/billing/debtors')
    debtors.value = res.data
  } finally {
    loading.value = false
  }
  if (mode.value === 'source') loadSource()
})

const BUCKETS = ['0-30', '31-60', '61-90', '90+']

// P3.0.7 (Софья 2026-05-29): поиск в Реестре должников по name/inn.
const registrySearch = ref('')

const filteredRows = computed(() => {
  let rows = debtors.value
  if (bucket.value !== 'all') {
    rows = rows.filter(r => r.aging_bucket === bucket.value)
  }
  const q = registrySearch.value.trim().toLowerCase()
  if (q) {
    rows = rows.filter(r =>
      (r.name || '').toLowerCase().includes(q) ||
      (r.inn || '').includes(q),
    )
  }
  return rows
})

// Разделение долга по статусам клиента (P3.0.3, вариант Б):
// «к взысканию» — ACTIVE+SUSPENDED, «к списанию» — CHURNED+TRANSIT.
const ACTIVE_DEBT_STATUSES = ['active', 'suspended']
const WRITEOFF_DEBT_STATUSES = ['churned', 'transit']

// P3.0.9 (Софья 2026-05-29): шапка считает по filteredRows, чтобы цифры
// «метчились с фильтром» (если выбрана корзина 0–30, метрика «Долг активных»
// показывает долг только видимых строк, а не всех должников).
const metrics = computed(() => {
  const rows = filteredRows.value
  const debtActive = rows
    .filter(r => ACTIVE_DEBT_STATUSES.includes(r.status))
    .reduce((s, r) => s + (r.total_debt || 0), 0)
  const debtWriteoff = rows
    .filter(r => WRITEOFF_DEBT_STATUSES.includes(r.status))
    .reduce((s, r) => s + (r.total_debt || 0), 0)
  const b90 = rows.filter(r => r.aging_bucket === '90+'
                                && ACTIVE_DEBT_STATUSES.includes(r.status))
  const sum90 = b90.reduce((s, r) => s + (r.total_debt || 0), 0)
  const withMonths = rows.filter(r => r.months_overdue != null
                                       && ACTIVE_DEBT_STATUSES.includes(r.status))
  const avgMonths = withMonths.length
    ? withMonths.reduce((s, r) => s + r.months_overdue, 0) / withMonths.length
    : 0
  const activeCount = rows.filter(r => ACTIVE_DEBT_STATUSES.includes(r.status)).length
  return [
    { label: 'Долг активных', value: fmtRub(debtActive) },
    { label: 'К списанию', value: fmtRub(debtWriteoff) },
    { label: 'Должников активных', value: String(activeCount) },
    { label: 'Просрочка 90+', value: `${b90.length} · ${fmtRub(sum90)}` },
    { label: 'Средняя просрочка', value: `${avgMonths.toFixed(1)} мес` },
  ]
})

const segments = computed(() => [
  { key: 'all', label: 'Все', count: debtors.value.length },
  ...BUCKETS.map(b => ({
    key: b,
    label: b,
    count: debtors.value.filter(r => r.aging_bucket === b).length,
  })),
])

function fmtRub(value: number | null) {
  if (value == null) return '—'
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency', currency: 'RUB', maximumFractionDigits: 0,
  }).format(value)
}

const RU_MONTHS = [
  'янв', 'фев', 'мар', 'апр', 'май', 'июн',
  'июл', 'авг', 'сен', 'окт', 'ноя', 'дек',
]
function fmtChurnMonth(val: string | null): string {
  if (!val) return '—'
  const d = new Date(val)
  return `${RU_MONTHS[d.getMonth()]} ${d.getFullYear()}`
}

const BUCKET_SEVERITY: Record<string, string> = {
  '0-30': 'secondary', '31-60': 'warn', '61-90': 'danger', '90+': 'danger',
}

async function onStatusChange(row: any, newStatus: string) {
  const prev = row.status
  if (newStatus === prev) return
  row.status = newStatus
  try {
    await api.patch(`/organizations/${row.inn}`, { status: newStatus })
    toast.add({
      severity: 'success', summary: 'Статус обновлён',
      detail: row.name, life: 2500,
    })
  } catch {
    row.status = prev
    toast.add({
      severity: 'error', summary: 'Не удалось сохранить статус',
      detail: row.name, life: 4000,
    })
  }
}

function openClient(inn: string) {
  router.push(`/clients/${inn}`)
}

// P3.0.8b (Софья 2026-05-29): «Списать долг» — невозвратный долг.
// Атомарно обнуляет total_debt, ставит CHURNED + churn_month=today.
function confirmWriteOff(row: any) {
  const sum = fmtRub(row.total_debt)
  confirm.require({
    header: 'Списать долг как невозвратный?',
    message: `Долг ${sum} клиента «${row.name}» (ИНН ${row.inn}) будет обнулён, клиент переведён в «Отток» с месяцем отключения = сегодня. Действие необратимо — но останется в audit log.`,
    icon: 'pi pi-exclamation-triangle',
    acceptLabel: 'Списать',
    rejectLabel: 'Отмена',
    acceptClass: 'p-button-danger',
    accept: () => writeOffDebt(row),
  })
}

async function writeOffDebt(row: any) {
  try {
    const res = await api.post(`/organizations/${row.inn}/write-off`)
    // Локально обновляем строку — чтобы UI среагировал без полной перезагрузки
    row.total_debt = res.data.new_total_debt
    row.status = res.data.status
    row.churn_month = res.data.churn_month
    toast.add({
      severity: 'success',
      summary: 'Долг списан',
      detail: `${row.name}: ${fmtRub(res.data.previous_total_debt)} → 0 ₽`,
      life: 4000,
    })
  } catch (e: any) {
    toast.add({
      severity: 'error',
      summary: 'Не удалось списать долг',
      detail: e?.response?.data?.detail || 'Ошибка сервера',
      life: 5000,
    })
  }
}

// --- 1С-вид ---
const snapshots = ref<any[]>([])
const sourceLoading = ref(false)
const selectedSnapshotId = ref<string | null>(null)
const sourceData = ref<any | null>(null)
const sourceSearch = ref('')
const showOnlyDiffs = ref(false)

// Пресеты фильтра «по статусам клиента» (P3.0.2 от 2026-05-28).
// Каждый пресет = csv для API ?org_statuses=...; пустая строка = «без фильтра».
const statusPresets = [
  { label: 'Все', value: '' },
  { label: 'Активные', value: 'active' },
  { label: '+ Приостановл.', value: 'active,suspended' },
  { label: 'Наши (вкл. Отток)', value: 'active,suspended,churned' },
]
const orgStatusesPreset = ref<string>('active')  // по умолчанию — только активные

// Пресеты фильтра «по статусу проработки» (P3.0.6 от 2026-05-29).
// Каждый пресет = csv для API ?workflow_statuses=...; пустая строка = все.
const workflowPresets = [
  { label: 'Все', value: '' },
  { label: 'Не разобранные', value: 'not_started,in_progress' },
  { label: 'Только Не начато', value: 'not_started' },
  { label: 'Только В работе', value: 'in_progress' },
  { label: 'Только Проработано', value: 'done' },
]
const workflowPreset = ref<string>('')  // по умолчанию — все

const workflowStatusOptions = [
  { label: 'Не начато', value: 'not_started' },
  { label: 'В работе', value: 'in_progress' },
  { label: 'Проработано', value: 'done' },
]

async function loadSnapshots() {
  const res = await api.get('/debt-snapshots')
  snapshots.value = res.data
}

async function loadSource(snapshotId: string | null = null) {
  sourceLoading.value = true
  try {
    await loadSnapshots()
    const url = snapshotId
      ? `/debt-snapshots/${snapshotId}`
      : '/debt-snapshots/latest'
    const res = await api.get(url, {
      params: {
        org_statuses: orgStatusesPreset.value || undefined,
        workflow_statuses: workflowPreset.value || undefined,
      },
    })
    sourceData.value = res.data
    selectedSnapshotId.value = res.data.snapshot.id
  } catch (e: any) {
    if (e?.response?.status === 404) {
      sourceData.value = {
        snapshot: null, rows: [], actual_org_totals: {},
        workflow_by_org: {}, diffs: [],
      }
    } else {
      toast.add({
        severity: 'error', summary: 'Не удалось загрузить 1С-вид',
        detail: e?.response?.data?.detail || 'Ошибка сервера', life: 5000,
      })
    }
  } finally {
    sourceLoading.value = false
  }
}

watch(selectedSnapshotId, (v, prev) => {
  if (v && v !== prev && v !== sourceData.value?.snapshot?.id) loadSource(v)
})

// При смене пресета статусов или workflow-фильтра перезагружаем с бэка —
// фильтрация серверная (каскад по дереву и подсчёт «расхождений»
// считаются от уже отфильтрованного множества).
watch([orgStatusesPreset, workflowPreset], () => {
  if (mode.value === 'source') loadSource(selectedSnapshotId.value)
})

// Локальная мапа workflow для inline-редактирования (без перезагрузки всего вида).
const workflowDraft = ref<Record<string, { status: string; comment: string }>>({})

function getWorkflow(orgId: string | null): { status: string; comment: string } {
  if (!orgId) return { status: 'not_started', comment: '' }
  if (workflowDraft.value[orgId]) return workflowDraft.value[orgId]
  const fromServer = sourceData.value?.workflow_by_org?.[orgId]
  return {
    status: fromServer?.status || 'not_started',
    comment: fromServer?.comment || '',
  }
}

const savingWorkflowOrg = ref<string | null>(null)

async function saveWorkflow(
  orgId: string,
  changes: { status?: string; comment?: string },
) {
  const current = getWorkflow(orgId)
  const next = { ...current, ...changes }
  // Локально обновляем мгновенно — UX отзывчивее.
  workflowDraft.value[orgId] = next
  savingWorkflowOrg.value = orgId
  try {
    const res = await api.put(`/debtor-workflow/${orgId}`, changes)
    // Синхронизируем sourceData.workflow_by_org с сервером.
    if (sourceData.value) {
      sourceData.value.workflow_by_org = sourceData.value.workflow_by_org || {}
      sourceData.value.workflow_by_org[orgId] = res.data
    }
    toast.add({
      severity: 'success', summary: 'Сохранено',
      detail: changes.status ? 'Статус обновлён' : 'Комментарий обновлён',
      life: 1500,
    })
  } catch (e: any) {
    delete workflowDraft.value[orgId]
    toast.add({
      severity: 'error', summary: 'Не удалось сохранить',
      detail: e?.response?.data?.detail || 'Ошибка сервера', life: 4000,
    })
  } finally {
    savingWorkflowOrg.value = null
  }
}

// Маппинг snapshot rows → дерево PrimeVue TreeTable.
// Помечаем строки, по которым найдено расхождение с БД.
const diffSet = computed(() => {
  const s = new Set<string>()
  if (!sourceData.value) return s
  for (const d of sourceData.value.diffs) s.add(d.row_id)
  return s
})

function rowMatchesSearch(row: any, q: string): boolean {
  if (!q) return true
  const blob = (row.raw_name + ' ' + (row.raw_inn || '') + ' ' +
                (row.doc_number || '') + ' ' + (row.contract_number || ''))
    .toLowerCase()
  return blob.includes(q)
}

const treeNodes = computed(() => {
  if (!sourceData.value) return []
  const rows = sourceData.value.rows as any[]
  const q = sourceSearch.value.trim().toLowerCase()

  // Шаг 1: строим map id → node.
  const nodeById = new Map<string, any>()
  for (const r of rows) {
    nodeById.set(r.id, {
      key: r.id,
      data: {
        ...r,
        has_diff: diffSet.value.has(r.id),
      },
      children: [],
    })
  }
  // Шаг 2: вешаем детей на родителей.
  const roots: any[] = []
  for (const r of rows) {
    const node = nodeById.get(r.id)!
    if (r.parent_row_id && nodeById.has(r.parent_row_id)) {
      nodeById.get(r.parent_row_id)!.children.push(node)
    } else {
      roots.push(node)
    }
  }

  // Шаг 3: фильтрация по поиску и «только расхождения».
  // Узел сохраняется если он сам или любой потомок проходит фильтр.
  const onlyDiffs = showOnlyDiffs.value
  function keep(node: any): boolean {
    const selfMatch =
      (!q || rowMatchesSearch(node.data, q)) &&
      (!onlyDiffs || node.data.has_diff)
    const filteredChildren: any[] = []
    for (const c of node.children) {
      if (keep(c)) filteredChildren.push(c)
    }
    node.children = filteredChildren
    // Если внутри есть совпавшие дети — сохраняем узел независимо от selfMatch
    // (типичное поведение TreeTable-поиска).
    return selfMatch || filteredChildren.length > 0
  }

  const result: any[] = []
  for (const r of roots) {
    if (keep(r)) result.push(r)
  }
  return result
})

const expandedKeys = ref<Record<string, boolean>>({})

// При активном поиске/фильтре расхождений — авто-раскрытие подходящих узлов.
watch([sourceSearch, showOnlyDiffs, sourceData], () => {
  expandedKeys.value = {}
  if (!sourceSearch.value && !showOnlyDiffs.value) return
  function markExpanded(node: any) {
    if (node.children?.length) {
      expandedKeys.value[node.key] = true
      node.children.forEach(markExpanded)
    }
  }
  treeNodes.value.forEach(markExpanded)
})

function sourceSeverity(level: string): string {
  if (level === 'buyer') return 'info'
  if (level === 'contract') return 'secondary'
  return 'success'  // document
}

function sourceLevelLabel(level: string): string {
  if (level === 'buyer') return 'Покупатель'
  if (level === 'contract') return 'Договор'
  return 'Документ'
}

function fmtDate(s: string | null): string {
  if (!s) return '—'
  const d = new Date(s)
  return d.toLocaleDateString('ru-RU')
}

const sourceMetrics = computed(() => {
  const s = sourceData.value?.snapshot
  if (!s) return []
  return [
    { label: 'Долг (файл)', value: fmtRub(s.total_debt_end) },
    { label: 'Аванс (файл)', value: fmtRub(s.total_advance_end) },
    { label: 'Покупателей', value: String(s.buyers_count) },
    { label: 'Расхождений', value: String(sourceData.value.diffs.length) },
  ]
})

const sourceSnapshotLabel = (s: any) =>
  s.period_start && s.period_end
    ? `${fmtDate(s.period_start)} – ${fmtDate(s.period_end)} (${fmtDate(s.created_at)})`
    : `${s.filename} (${fmtDate(s.created_at)})`
</script>

<template>
  <div class="debtors-view">
    <div class="debtors-header">
      <h1>Должники</h1>
      <SelectButton v-model="mode" :options="modeOptions" optionLabel="label"
        optionValue="value" :allow-empty="false" />
    </div>

    <!-- Режим: Реестр должников -->
    <template v-if="mode === 'registry'">
      <SegmentBand :metrics="metrics" :segments="segments" v-model="bucket" />

      <div class="registry-toolbar">
        <InputText
          v-model="registrySearch"
          placeholder="Поиск по имени или ИНН..."
          class="registry-search"
        />
        <span v-if="registrySearch" class="registry-search-hint">
          найдено: {{ filteredRows.length }} из {{ debtors.length }}
        </span>
      </div>

      <DataTable
        :value="filteredRows"
        :loading="loading"
        sortField="total_debt"
        :sortOrder="-1"
        paginator
        :rows="25"
        stripedRows
        rowHover
        class="debtors-table"
        @row-click="(e: any) => openClient(e.data.inn)"
      >
        <Column field="name" header="Клиент" sortable />
        <Column field="inn" header="ИНН" style="width: 130px" />
        <Column field="monthly_ap" header="АП/мес" sortable style="width: 120px">
          <template #body="{ data }">{{ fmtRub(data.monthly_ap) }}</template>
        </Column>
        <Column field="total_debt" header="Долг" sortable style="width: 140px">
          <template #body="{ data }">
            <Tag severity="danger">{{ fmtRub(data.total_debt) }}</Tag>
          </template>
        </Column>
        <Column field="months_overdue" header="Просрочка, мес" sortable style="width: 130px">
          <template #body="{ data }">{{ data.months_overdue ?? '—' }}</template>
        </Column>
        <Column field="aging_bucket" header="Корзина" style="width: 110px">
          <template #body="{ data }">
            <Tag :severity="BUCKET_SEVERITY[data.aging_bucket] || 'secondary'">
              {{ data.aging_bucket }}
            </Tag>
          </template>
        </Column>
        <Column header="Статус" style="width: 170px">
          <template #body="{ data }">
            <Select
              :modelValue="data.status"
              :options="statusOptions"
              optionLabel="label"
              optionValue="value"
              size="small"
              @click.stop
              @update:modelValue="(v: string) => onStatusChange(data, v)"
            />
          </template>
        </Column>
        <Column header="Месяц отключения" style="width: 130px">
          <template #body="{ data }">
            <span v-if="data.status === 'churned'" class="churn-cell"
              title="Последний месяц начисления АП">
              {{ fmtChurnMonth(data.churn_month) }}
            </span>
            <span v-else class="muted">—</span>
          </template>
        </Column>
        <Column field="payment_score" header="Оценка" style="width: 90px">
          <template #body="{ data }">{{ data.payment_score ?? '—' }}</template>
        </Column>
        <Column header="Действия" style="width: 130px">
          <template #body="{ data }">
            <Button
              v-if="data.total_debt > 0"
              icon="pi pi-times-circle"
              label="Списать"
              severity="danger"
              size="small"
              text
              @click.stop="confirmWriteOff(data)"
              :title="`Списать долг ${fmtRub(data.total_debt)} как невозвратный`"
            />
          </template>
        </Column>
      </DataTable>
    </template>

    <!-- Режим: 1С-вид -->
    <template v-else>
      <div class="source-toolbar">
        <div class="source-snapshot-picker">
          <label>Импорт:</label>
          <Select
            v-model="selectedSnapshotId"
            :options="snapshots"
            optionLabel="filename"
            optionValue="id"
            placeholder="Выберите снимок…"
            size="small"
          >
            <template #option="{ option }">
              <div class="snap-opt">
                <div class="snap-opt-name">{{ option.filename }}</div>
                <div class="snap-opt-meta">{{ sourceSnapshotLabel(option) }}</div>
              </div>
            </template>
            <template #value="{ value, placeholder }">
              <span v-if="!value">{{ placeholder }}</span>
              <span v-else>
                {{ snapshots.find((s: any) => s.id === value)?.filename || value }}
              </span>
            </template>
          </Select>
        </div>
        <InputText
          v-model="sourceSearch"
          placeholder="Поиск по имени, ИНН, № документа…"
          class="source-search"
        />
        <label class="source-toggle" :class="{ active: showOnlyDiffs }">
          <input type="checkbox" v-model="showOnlyDiffs" />
          Только расхождения
        </label>
        <div class="source-status-filter"
             title="Какие статусы клиента показывать. По умолчанию — только активные.">
          <span class="source-status-label">Клиенты:</span>
          <SelectButton
            v-model="orgStatusesPreset"
            :options="statusPresets"
            optionLabel="label"
            optionValue="value"
            :allow-empty="false"
            size="small"
          />
        </div>
        <div class="source-status-filter"
             title="Фильтр по статусу проработки клиента. «Не разобранные» скрывает Проработанных.">
          <span class="source-status-label">Проработка:</span>
          <Select
            v-model="workflowPreset"
            :options="workflowPresets"
            optionLabel="label"
            optionValue="value"
            size="small"
            class="source-workflow-select"
          />
        </div>
      </div>

      <SegmentBand
        v-if="sourceData?.snapshot"
        :metrics="sourceMetrics"
        :segments="[]"
        v-model:modelValue="bucket"
      />

      <div v-if="sourceLoading" class="empty-state">Загрузка…</div>
      <div v-else-if="!sourceData?.snapshot" class="empty-state">
        Нет ни одного импорта файла «Задолженность». Загрузите файл через раздел «Импорт».
      </div>
      <TreeTable
        v-else
        :value="treeNodes"
        v-model:expandedKeys="expandedKeys"
        class="source-tree"
        :pt="{ root: { 'aria-label': '1С-вид задолженности' } }"
      >
        <Column field="raw_name" header="Покупатель / Договор / Документ" expander style="min-width: 340px">
          <template #body="{ node }">
            <div class="src-name-cell">
              <Tag :severity="sourceSeverity(node.data.level)" class="src-level-tag">
                {{ sourceLevelLabel(node.data.level) }}
              </Tag>
              <span :class="{ 'src-diff': node.data.has_diff }">{{ node.data.raw_name }}</span>
              <Tag v-if="node.data.has_diff" severity="warn" class="src-diff-tag"
                   :title="'Расхождение с БД'">
                ≠ БД
              </Tag>
            </div>
          </template>
        </Column>
        <Column field="raw_inn" header="ИНН" style="width: 130px">
          <template #body="{ node }">
            <span v-if="node.data.level === 'buyer'">{{ node.data.raw_inn || '—' }}</span>
            <span v-else-if="node.data.level === 'document'">
              {{ node.data.doc_number ? '№' + node.data.doc_number : '' }}
              {{ node.data.doc_date ? fmtDate(node.data.doc_date) : '' }}
            </span>
            <span v-else>—</span>
          </template>
        </Column>
        <Column field="debt_start" header="Долг (нач)" style="width: 130px">
          <template #body="{ node }">{{ fmtRub(node.data.debt_start) }}</template>
        </Column>
        <Column field="advance_start" header="Аванс (нач)" style="width: 130px">
          <template #body="{ node }">{{ fmtRub(node.data.advance_start) }}</template>
        </Column>
        <Column field="sold" header="Продано" style="width: 130px">
          <template #body="{ node }">{{ fmtRub(node.data.sold) }}</template>
        </Column>
        <Column field="paid" header="Оплачено" style="width: 130px">
          <template #body="{ node }">{{ fmtRub(node.data.paid) }}</template>
        </Column>
        <Column field="prepay_in" header="Поступило" style="width: 130px">
          <template #body="{ node }">{{ fmtRub(node.data.prepay_in) }}</template>
        </Column>
        <Column field="prepay_used" header="Зачтено" style="width: 130px">
          <template #body="{ node }">{{ fmtRub(node.data.prepay_used) }}</template>
        </Column>
        <Column field="debt_end" header="Долг (кон)" style="width: 130px">
          <template #body="{ node }">
            <span :class="{ 'src-debt-end': true, 'src-diff': node.data.has_diff }">
              {{ fmtRub(node.data.debt_end) }}
            </span>
          </template>
        </Column>
        <Column field="advance_end" header="Аванс (кон)" style="width: 130px">
          <template #body="{ node }">{{ fmtRub(node.data.advance_end) }}</template>
        </Column>
        <Column header="Проработано" style="width: 170px">
          <template #body="{ node }">
            <Select
              v-if="node.data.level === 'buyer' && node.data.organization_id"
              :modelValue="getWorkflow(node.data.organization_id).status"
              :options="workflowStatusOptions"
              optionLabel="label"
              optionValue="value"
              size="small"
              :loading="savingWorkflowOrg === node.data.organization_id"
              :class="['wf-status', `wf-${getWorkflow(node.data.organization_id).status}`]"
              @update:modelValue="(v: string) => saveWorkflow(node.data.organization_id, { status: v })"
              @click.stop
            />
            <span v-else class="muted">—</span>
          </template>
        </Column>
        <Column header="Комментарий" style="min-width: 220px">
          <template #body="{ node }">
            <Textarea
              v-if="node.data.level === 'buyer' && node.data.organization_id"
              :modelValue="getWorkflow(node.data.organization_id).comment"
              @update:modelValue="(v: string) => { workflowDraft[node.data.organization_id] = { ...getWorkflow(node.data.organization_id), comment: v } }"
              @blur="(e: any) => {
                const v = e.target.value
                const current = sourceData?.workflow_by_org?.[node.data.organization_id]?.comment || ''
                if (v !== current) saveWorkflow(node.data.organization_id, { comment: v })
              }"
              rows="1"
              autoResize
              class="wf-comment"
              placeholder="Заметка по проработке…"
              @click.stop
            />
            <span v-else class="muted">—</span>
          </template>
        </Column>
      </TreeTable>
    </template>
  </div>
</template>

<style scoped>
.debtors-view {
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}
.debtors-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}
.debtors-view h1 {
  font-size: 1.5rem;
  color: #1e293b;
  margin: 0;
}
.debtors-table {
  cursor: pointer;
}
.churn-cell { color: #b45309; font-size: 0.85rem; }
.muted { color: #cbd5e1; }
.registry-toolbar {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin: 0.25rem 0 0.5rem;
}
.registry-search {
  width: 320px;
}
.registry-search-hint {
  color: #64748b;
  font-size: 0.85rem;
}

/* --- 1С-вид --- */
.source-toolbar {
  display: flex;
  gap: 1rem;
  align-items: center;
  flex-wrap: wrap;
  padding: 0.5rem 0;
}
.source-snapshot-picker {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.source-snapshot-picker label {
  color: #475569;
  font-size: 0.9rem;
}
.source-snapshot-picker :deep(.p-select) {
  min-width: 360px;
}
.source-search {
  width: 320px;
}
.source-toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  color: #475569;
  font-size: 0.9rem;
  cursor: pointer;
  padding: 0.35rem 0.75rem;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  background: white;
  user-select: none;
}
.source-toggle.active {
  border-color: #b91c1c;
  background: #fef2f2;
  color: #b91c1c;
}
.source-status-filter {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
}
.source-status-label {
  color: #475569;
  font-size: 0.9rem;
}
.source-workflow-select {
  min-width: 180px;
}
.snap-opt {
  display: flex;
  flex-direction: column;
}
.snap-opt-name {
  font-size: 0.9rem;
}
.snap-opt-meta {
  font-size: 0.75rem;
  color: #94a3b8;
}
.source-tree {
  font-size: 0.85rem;
}
.src-name-cell {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}
.src-level-tag {
  font-size: 0.7rem;
  font-weight: 600;
}
.src-diff {
  color: #b91c1c;
  font-weight: 600;
}
.src-diff-tag {
  font-size: 0.7rem;
}
.src-debt-end {
  font-variant-numeric: tabular-nums;
}
.empty-state {
  padding: 2rem;
  text-align: center;
  color: #64748b;
}
.wf-status :deep(.p-select-label) {
  font-size: 0.8rem;
}
.wf-not_started :deep(.p-select-label) { color: #64748b; }
.wf-in_progress :deep(.p-select-label) { color: #b45309; font-weight: 600; }
.wf-done :deep(.p-select-label) { color: #15803d; font-weight: 600; }
.wf-comment {
  width: 100%;
  font-size: 0.8rem;
  min-height: 28px;
  resize: vertical;
}
</style>
