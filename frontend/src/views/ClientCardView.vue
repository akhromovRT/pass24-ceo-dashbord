<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import Tabs from 'primevue/tabs'
import TabList from 'primevue/tablist'
import Tab from 'primevue/tab'
import TabPanels from 'primevue/tabpanels'
import TabPanel from 'primevue/tabpanel'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Tag from 'primevue/tag'
import InputText from 'primevue/inputtext'
import InputNumber from 'primevue/inputnumber'
import Textarea from 'primevue/textarea'
import Select from 'primevue/select'
import Checkbox from 'primevue/checkbox'
import DatePicker from 'primevue/datepicker'
import Button from 'primevue/button'
import { useToast } from 'primevue/usetoast'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useOrganizationsStore } from '../stores/organizations'
import api from '../api/client'
import LedgerTable from '../components/LedgerTable.vue'
import AllocationEditor from '../components/AllocationEditor.vue'
import TariffHistory from '../components/TariffHistory.vue'

use([BarChart, LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const route = useRoute()
const inn = route.params.inn as string
const store = useOrganizationsStore()
const toast = useToast()

const org = ref<any>(null)
const snapshots = ref<any[]>([])
const contracts = ref<any[]>([])
const objects = ref<any[]>([])
const documents = ref<any[]>([])
const managers = ref<any[]>([])
const ledger = ref<{ months: any[]; payments: any[] }>({ months: [], payments: [] })
const editorVisible = ref(false)
const editingPayment = ref<any>(null)
const loading = ref(true)

const editMode = ref(false)
const saving = ref(false)
const form = ref<Record<string, any>>({})

const EDITABLE_KEYS = [
  'name_display', 'org_type', 'manager_id', 'client_since',
  'objects', 'object_type', 'system_number', 'equipment',
  'address', 'city_region', 'cloud_url', 'has_folder', 'doc_exchange',
  'monthly_ap', 'notes', 'in_registry', 'excluded_from_analytics',
  'excluded_reason', 'churn_month',
]

const RU_MONTHS = [
  'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
  'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь',
]
function formatChurnMonth(val: string | null): string {
  if (!val) return '—'
  const d = new Date(val)
  return `${RU_MONTHS[d.getMonth()]} ${d.getFullYear()}`
}

const statusOptions = [
  { label: 'Активен', value: 'active' },
  { label: 'Приостановлен', value: 'suspended' },
  { label: 'Отток', value: 'churned' },
  { label: 'Транзит', value: 'transit' },
  { label: 'Потенциальный', value: 'prospect' },
  { label: 'Поставщик', value: 'supplier' },
]
const orgTypeOptions = [
  { label: 'ТСН', value: 'TSN' },
  { label: 'ООО', value: 'OOO' },
  { label: 'АО', value: 'AO' },
  { label: 'ИП', value: 'IP' },
  { label: 'КП', value: 'KP' },
  { label: 'ЖК', value: 'ZHK' },
  { label: 'СНТ', value: 'SNT' },
  { label: 'НП', value: 'NP' },
  { label: 'Физлицо', value: 'FL' },
  { label: 'Прочее', value: 'Prochee' },
]
const triBool = [
  { label: 'Да', value: true },
  { label: 'Нет', value: false },
]
const docTypeLabel: Record<string, string> = {
  sale: 'Реализация', payment: 'Платёж',
  prepay_in: 'Аванс получен', prepay_used: 'Аванс зачтён',
}
const docTypeSeverity: Record<string, string> = {
  sale: 'info', payment: 'success', prepay_in: 'warn', prepay_used: 'secondary',
}

onMounted(async () => {
  try {
    const [o, s, c, ob, d, m, l] = await Promise.all([
      api.get(`/organizations/${inn}`),
      api.get(`/organizations/${inn}/snapshots`),
      api.get(`/organizations/${inn}/contracts`),
      api.get(`/organizations/${inn}/objects`),
      api.get(`/organizations/${inn}/documents`),
      api.get('/users/options'),
      api.get(`/organizations/${inn}/ledger`),
    ])
    org.value = o.data
    snapshots.value = s.data
    contracts.value = c.data
    objects.value = ob.data
    documents.value = d.data
    managers.value = m.data
    ledger.value = l.data
  } finally {
    loading.value = false
  }
})

function formatCurrency(value: number | null) {
  if (value == null) return '—'
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency', currency: 'RUB', maximumFractionDigits: 0,
  }).format(value)
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
function managerName(id: string | null) {
  if (!id) return '—'
  return managers.value.find(m => m.id === id)?.name || '—'
}

async function reloadLedger() {
  const r = await api.get(`/organizations/${inn}/ledger`)
  ledger.value = r.data
}
function openEditor(payment: any) {
  editingPayment.value = payment
  editorVisible.value = true
}

function enterEdit() {
  const f: Record<string, any> = {}
  for (const k of EDITABLE_KEYS) {
    if ((k === 'client_since' || k === 'churn_month') && org.value[k]) {
      f[k] = new Date(org.value[k])
    } else {
      f[k] = org.value[k]
    }
  }
  form.value = f
  editMode.value = true
}
function cancelEdit() {
  editMode.value = false
  form.value = {}
}
async function save() {
  saving.value = true
  const patch: Record<string, any> = {}
  for (const k of EDITABLE_KEYS) {
    let v = form.value[k]
    if ((k === 'client_since' || k === 'churn_month') && v instanceof Date) {
      v = v.toISOString().slice(0, 10)
    }
    patch[k] = v
  }
  try {
    const updated = await store.updateOrganization(inn, patch)
    org.value = updated
    editMode.value = false
    toast.add({ severity: 'success', summary: 'Сохранено', life: 2500 })
  } catch {
    toast.add({
      severity: 'error', summary: 'Не удалось сохранить',
      detail: 'Изменения остались в форме', life: 4000,
    })
  } finally {
    saving.value = false
  }
}
async function changeStatus(newStatus: string) {
  const prev = org.value.status
  if (newStatus === prev) return
  org.value.status = newStatus
  try {
    const updated = await store.updateOrganization(inn, { status: newStatus })
    if (updated) org.value = updated
    await reloadLedger()
    const msg = newStatus === 'churned' && updated?.churn_month
      ? `Месяц отключения: ${formatChurnMonth(updated.churn_month)}`
      : undefined
    toast.add({
      severity: 'success', summary: 'Статус обновлён',
      detail: msg, life: 3500,
    })
  } catch (e: any) {
    org.value.status = prev
    const detail = e?.response?.data?.detail
      || 'Изменения не сохранены'
    toast.add({
      severity: 'error', summary: 'Не удалось сменить статус',
      detail, life: 6000,
    })
  }
}

const barChartOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  legend: { data: ['Продано', 'Оплачено'] },
  xAxis: { type: 'category', data: snapshots.value.map(s => `${s.month}/${s.year}`) },
  yAxis: { type: 'value' },
  series: [
    { name: 'Продано', type: 'bar', data: snapshots.value.map(s => s.sold || 0), color: '#6366f1' },
    { name: 'Оплачено', type: 'bar', data: snapshots.value.map(s => s.paid || 0), color: '#22c55e' },
  ],
}))
const lineChartOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  xAxis: { type: 'category', data: snapshots.value.map(s => `${s.month}/${s.year}`) },
  yAxis: { type: 'value' },
  series: [
    { name: 'Долг', type: 'line', data: snapshots.value.map(s => s.debt_end || 0),
      color: '#ef4444', areaStyle: { opacity: 0.1 } },
  ],
}))
</script>

<template>
  <div class="client-card" v-if="!loading && org">
    <div class="card-header">
      <div class="header-main">
        <h1>{{ org.name_display || org.name_1c }}</h1>
        <div class="card-meta">
          <span>ИНН: {{ org.inn }}</span>
          <Tag v-if="org.org_type" :value="org.org_type" severity="info" />
          <Tag v-if="org.in_registry" severity="success" icon="pi pi-check">В реестре</Tag>
        </div>
      </div>
      <div class="header-actions">
        <div class="status-control">
          <span class="sc-label">Статус</span>
          <Select
            :modelValue="org.status"
            :options="statusOptions"
            optionLabel="label"
            optionValue="value"
            @update:modelValue="changeStatus"
          />
          <span v-if="org.status === 'churned'" class="churn-month-display"
            :title="'Месяц последнего начисления абонплаты. После него клиент не накапливает долг.'">
            Отключён: <b>{{ formatChurnMonth(org.churn_month) }}</b>
          </span>
        </div>
        <div class="header-stats">
          <div class="stat">
            <span class="stat-label">АП/мес</span>
            <span class="stat-value">{{ formatCurrency(org.monthly_ap) }}</span>
          </div>
          <div class="stat">
            <span class="stat-label">Долг</span>
            <span class="stat-value debt">{{ formatCurrency(org.total_debt) }}</span>
          </div>
          <div class="stat">
            <span class="stat-label">Оценка</span>
            <span class="stat-value">{{ org.payment_score ?? '—' }}</span>
          </div>
        </div>
        <Button v-if="!editMode" label="Редактировать" icon="pi pi-pencil"
          size="small" @click="enterEdit" />
      </div>
    </div>

    <Tabs value="info">
      <TabList>
        <Tab value="info">Карточка</Tab>
        <Tab value="payments">История платежей</Tab>
        <Tab value="ledger">Расчёты</Tab>
        <Tab value="monthly">Помесячно</Tab>
        <Tab value="contracts">Договоры</Tab>
        <Tab value="objects">Объекты</Tab>
      </TabList>
      <TabPanels>
        <TabPanel value="info">
          <div class="sections">
            <section class="fld-section">
              <h3>Реквизиты</h3>
              <div class="fld-grid">
                <div class="fld">
                  <label>Отображаемое название</label>
                  <InputText v-if="editMode" v-model="form.name_display" />
                  <span v-else>{{ org.name_display || '—' }}</span>
                </div>
                <div class="fld">
                  <label>Название в 1С</label>
                  <span class="ro">{{ org.name_1c }}</span>
                </div>
                <div class="fld">
                  <label>ИНН</label>
                  <span class="ro">{{ org.inn }}</span>
                </div>
                <div class="fld">
                  <label>Тип организации</label>
                  <Select v-if="editMode" v-model="form.org_type" :options="orgTypeOptions"
                    optionLabel="label" optionValue="value" showClear placeholder="—" />
                  <span v-else>{{ org.org_type || '—' }}</span>
                </div>
                <div class="fld">
                  <label>Менеджер</label>
                  <Select v-if="editMode" v-model="form.manager_id" :options="managers"
                    optionLabel="name" optionValue="id" showClear placeholder="—" />
                  <span v-else>{{ managerName(org.manager_id) }}</span>
                </div>
                <div class="fld">
                  <label>Клиент с</label>
                  <DatePicker v-if="editMode" v-model="form.client_since" dateFormat="dd.mm.yy" showIcon />
                  <span v-else>{{ formatDate(org.client_since) }}</span>
                </div>
                <div class="fld" v-if="org.status === 'churned'">
                  <label>Месяц отключения
                    <i class="pi pi-info-circle"
                       title="Последний месяц начисления АП. После него клиент не накапливает долг." />
                  </label>
                  <DatePicker v-if="editMode" v-model="form.churn_month"
                    view="month" dateFormat="mm/yy" showIcon />
                  <span v-else>{{ formatChurnMonth(org.churn_month) }}</span>
                </div>
              </div>
            </section>

            <section class="fld-section">
              <h3>Объект и система</h3>
              <div class="fld-grid">
                <div class="fld">
                  <label>Объектов (число)</label>
                  <InputNumber v-if="editMode" v-model="form.objects" :min="0" />
                  <span v-else>{{ org.objects ?? '—' }}</span>
                </div>
                <div class="fld">
                  <label>Тип объекта</label>
                  <InputText v-if="editMode" v-model="form.object_type" />
                  <span v-else>{{ org.object_type || '—' }}</span>
                </div>
                <div class="fld">
                  <label>Номер системы</label>
                  <InputText v-if="editMode" v-model="form.system_number" />
                  <span v-else>{{ org.system_number || '—' }}</span>
                </div>
                <div class="fld">
                  <label>Оборудование</label>
                  <InputText v-if="editMode" v-model="form.equipment" />
                  <span v-else>{{ org.equipment || '—' }}</span>
                </div>
                <div class="fld">
                  <label>Адрес</label>
                  <InputText v-if="editMode" v-model="form.address" />
                  <span v-else>{{ org.address || '—' }}</span>
                </div>
                <div class="fld">
                  <label>Город / регион</label>
                  <InputText v-if="editMode" v-model="form.city_region" />
                  <span v-else>{{ org.city_region || '—' }}</span>
                </div>
                <div class="fld">
                  <label>Ссылка на облако</label>
                  <InputText v-if="editMode" v-model="form.cloud_url" />
                  <a v-else-if="org.cloud_url" :href="ensureProtocol(org.cloud_url)" target="_blank">
                    {{ org.cloud_url }}
                  </a>
                  <span v-else>—</span>
                </div>
                <div class="fld">
                  <label>Папка заведена</label>
                  <Select v-if="editMode" v-model="form.has_folder" :options="triBool"
                    optionLabel="label" optionValue="value" showClear placeholder="—" />
                  <span v-else>{{ org.has_folder == null ? '—' : org.has_folder ? 'Да' : 'Нет' }}</span>
                </div>
                <div class="fld">
                  <label>Обмен документами</label>
                  <InputText v-if="editMode" v-model="form.doc_exchange" />
                  <span v-else>{{ org.doc_exchange || '—' }}</span>
                </div>
              </div>
            </section>

            <section class="fld-section">
              <h3>Финансы</h3>
              <div class="fld-grid">
                <div class="fld">
                  <label>АП / месяц</label>
                  <InputNumber v-if="editMode" v-model="form.monthly_ap" :min="0"
                    mode="currency" currency="RUB" locale="ru-RU" />
                  <span v-else>{{ formatCurrency(org.monthly_ap) }}</span>
                </div>
                <div class="fld">
                  <label>Долг (из 1С)</label>
                  <span class="ro">{{ formatCurrency(org.total_debt) }}</span>
                </div>
                <div class="fld">
                  <label>Оценка платежей</label>
                  <span class="ro">{{ org.payment_score ?? '—' }}</span>
                </div>
              </div>
            </section>

            <section class="fld-section">
              <h3>Заметки</h3>
              <Textarea v-if="editMode" v-model="form.notes" rows="3" autoResize style="width: 100%" />
              <div v-else class="notes-text">{{ org.notes || '—' }}</div>
            </section>

            <section class="fld-section">
              <h3>Аналитика</h3>
              <div class="fld-grid">
                <div class="fld checkbox-fld">
                  <Checkbox v-if="editMode" v-model="form.in_registry" :binary="true" inputId="reg" />
                  <label for="reg">В реестре{{ editMode ? '' : ': ' + (org.in_registry ? 'да' : 'нет') }}</label>
                </div>
                <div class="fld checkbox-fld">
                  <Checkbox v-if="editMode" v-model="form.excluded_from_analytics" :binary="true" inputId="excl" />
                  <label for="excl">Исключён из аналитики{{ editMode ? '' : ': ' + (org.excluded_from_analytics ? 'да' : 'нет') }}</label>
                </div>
                <div class="fld">
                  <label>Причина исключения</label>
                  <InputText v-if="editMode" v-model="form.excluded_reason" />
                  <span v-else>{{ org.excluded_reason || '—' }}</span>
                </div>
              </div>
            </section>
          </div>
        </TabPanel>

        <TabPanel value="payments">
          <DataTable :value="documents" stripedRows paginator :rows="25"
            sortField="doc_date" :sortOrder="-1">
            <template #empty>Документов нет.</template>
            <Column field="doc_date" header="Дата" sortable style="width: 120px">
              <template #body="{ data }">{{ formatDate(data.doc_date) }}</template>
            </Column>
            <Column field="doc_type" header="Тип" style="width: 150px">
              <template #body="{ data }">
                <Tag :severity="docTypeSeverity[data.doc_type] || 'secondary'">
                  {{ docTypeLabel[data.doc_type] || data.doc_type }}
                </Tag>
              </template>
            </Column>
            <Column field="doc_number" header="Номер" style="width: 130px">
              <template #body="{ data }">{{ data.doc_number || '—' }}</template>
            </Column>
            <Column field="amount" header="Сумма" sortable style="width: 140px">
              <template #body="{ data }">{{ formatCurrency(data.amount) }}</template>
            </Column>
            <Column header="Период" style="width: 110px">
              <template #body="{ data }">
                {{ data.period_month ? `${data.period_month}/${data.period_year}` : '—' }}
              </template>
            </Column>
            <Column field="raw_name" header="Назначение">
              <template #body="{ data }">
                <span class="truncate" :title="data.raw_name">{{ data.raw_name || '—' }}</span>
              </template>
            </Column>
          </DataTable>
        </TabPanel>

        <TabPanel value="ledger">
          <div class="sections">
            <section class="fld-section">
              <h3>Начисления по месяцам</h3>
              <LedgerTable :months="ledger.months" />
            </section>
            <section class="fld-section">
              <h3>Платежи и разнесение</h3>
              <DataTable :value="ledger.payments" stripedRows paginator :rows="15">
                <template #empty>Платежей нет.</template>
                <Column header="Дата" style="width: 110px">
                  <template #body="{ data }">{{ formatDate(data.doc_date) }}</template>
                </Column>
                <Column field="amount" header="Сумма" style="width: 130px">
                  <template #body="{ data }">{{ formatCurrency(data.amount) }}</template>
                </Column>
                <Column header="Разнесено на">
                  <template #body="{ data }">
                    <span v-if="data.allocations.length" class="alloc-tags">
                      <Tag v-for="(a, i) in data.allocations" :key="i"
                        :severity="a.year ? 'info' : 'secondary'">
                        {{ a.year ? `${a.month}/${a.year}` : 'не опр.' }}:
                        {{ formatCurrency(a.amount) }}{{ a.is_manual ? ' ✎' : '' }}
                      </Tag>
                    </span>
                    <span v-else>—</span>
                  </template>
                </Column>
                <Column header="" style="width: 100px">
                  <template #body="{ data }">
                    <Button label="Правка" text size="small" icon="pi pi-pencil"
                      @click="openEditor(data)" />
                  </template>
                </Column>
              </DataTable>
            </section>
            <section class="fld-section">
              <h3>История тарифа</h3>
              <TariffHistory :inn="inn" @changed="reloadLedger" />
            </section>
          </div>
        </TabPanel>

        <TabPanel value="monthly">
          <div class="charts-grid">
            <div class="chart-box">
              <h3>Продано vs Оплачено</h3>
              <v-chart :option="barChartOption" style="height: 280px" autoresize />
            </div>
            <div class="chart-box">
              <h3>Динамика долга</h3>
              <v-chart :option="lineChartOption" style="height: 280px" autoresize />
            </div>
          </div>
          <DataTable :value="snapshots" stripedRows class="monthly-table">
            <template #empty>Помесячных данных нет.</template>
            <Column header="Период">
              <template #body="{ data }">{{ data.month }}/{{ data.year }}</template>
            </Column>
            <Column field="plan_amount" header="План">
              <template #body="{ data }">{{ formatCurrency(data.plan_amount) }}</template>
            </Column>
            <Column field="sold" header="Продано">
              <template #body="{ data }">{{ formatCurrency(data.sold) }}</template>
            </Column>
            <Column field="paid" header="Оплачено">
              <template #body="{ data }">{{ formatCurrency(data.paid) }}</template>
            </Column>
            <Column field="debt_end" header="Долг">
              <template #body="{ data }">{{ formatCurrency(data.debt_end) }}</template>
            </Column>
            <Column field="collectability" header="Собираемость">
              <template #body="{ data }">{{ data.collectability != null ? data.collectability + '%' : '—' }}</template>
            </Column>
          </DataTable>
        </TabPanel>

        <TabPanel value="contracts">
          <DataTable :value="contracts" stripedRows>
            <template #empty>Договоров нет.</template>
            <Column field="contract_number" header="Номер" />
            <Column field="contract_type" header="Тип">
              <template #body="{ data }"><Tag>{{ data.contract_type }}</Tag></template>
            </Column>
            <Column field="monthly_amount" header="Сумма/мес">
              <template #body="{ data }">{{ formatCurrency(data.monthly_amount) }}</template>
            </Column>
            <Column field="status" header="Статус">
              <template #body="{ data }">
                <Tag :severity="data.status === 'active' ? 'success' : 'secondary'">{{ data.status }}</Tag>
              </template>
            </Column>
          </DataTable>
        </TabPanel>

        <TabPanel value="objects">
          <DataTable v-if="objects.length" :value="objects" stripedRows>
            <Column field="name" header="Название" />
            <Column header="Ссылка на облако">
              <template #body="{ data }">
                <a v-if="data.cloud_url" :href="ensureProtocol(data.cloud_url)" target="_blank">ссылка</a>
                <span v-else>—</span>
              </template>
            </Column>
            <Column field="object_number" header="№ в облаке" />
            <Column field="object_type" header="Тип" />
            <Column field="address" header="Адрес" />
            <Column field="city_region" header="Город/область" />
          </DataTable>
          <div v-else class="empty-state">Объекты не указаны.</div>
        </TabPanel>
      </TabPanels>
    </Tabs>

    <AllocationEditor v-model:visible="editorVisible" :payment="editingPayment"
      @saved="reloadLedger" />

    <div v-if="editMode" class="save-bar">
      <span class="save-hint">Режим редактирования</span>
      <Button label="Отмена" severity="secondary" outlined size="small" @click="cancelEdit" />
      <Button label="Сохранить" icon="pi pi-check" size="small" :loading="saving" @click="save" />
    </div>
  </div>
  <div v-else-if="loading" class="loading">Загрузка...</div>
</template>

<style scoped>
.client-card {
  padding: 1.5rem;
  padding-bottom: 5rem;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 1.25rem;
  gap: 1.5rem;
  flex-wrap: wrap;
}
.header-main h1 {
  margin: 0 0 0.5rem;
  font-size: 1.6rem;
  color: #1e293b;
}
.card-meta {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  color: #64748b;
  flex-wrap: wrap;
}
.header-actions {
  display: flex;
  align-items: flex-start;
  gap: 1.5rem;
  flex-wrap: wrap;
}
.status-control {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.sc-label {
  font-size: 0.72rem;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.churn-month-display {
  margin-top: 0.25rem;
  font-size: 0.78rem;
  color: #b45309;
  cursor: help;
}
.churn-month-display b { color: #92400e; }
.header-stats {
  display: flex;
  gap: 1.5rem;
}
.stat { text-align: right; }
.stat-label {
  display: block;
  font-size: 0.72rem;
  color: #64748b;
  text-transform: uppercase;
}
.stat-value {
  font-size: 1.35rem;
  font-weight: 700;
  color: #1e293b;
}
.stat-value.debt { color: #ef4444; }

.sections {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  padding-top: 0.5rem;
}
.fld-section {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 1rem 1.25rem;
}
.fld-section h3 {
  margin: 0 0 0.85rem;
  font-size: 0.95rem;
  color: #1e293b;
}
.fld-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0.85rem 1.25rem;
}
@media (max-width: 900px) {
  .fld-grid { grid-template-columns: 1fr; }
}
.fld {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.fld label {
  font-size: 0.72rem;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.fld > span, .fld > a {
  font-size: 0.95rem;
  color: #1e293b;
}
.fld .ro { color: #94a3b8; }
.checkbox-fld {
  flex-direction: row;
  align-items: center;
  gap: 0.5rem;
}
.checkbox-fld label { text-transform: none; font-size: 0.9rem; color: #1e293b; }
.notes-text {
  font-size: 0.95rem;
  color: #1e293b;
  white-space: pre-wrap;
}
.charts-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
  margin-bottom: 1.25rem;
}
@media (max-width: 900px) {
  .charts-grid { grid-template-columns: 1fr; }
}
.chart-box h3 {
  margin: 0 0 0.5rem;
  font-size: 0.95rem;
  color: #374151;
}
.monthly-table { margin-top: 0.5rem; }
.alloc-tags {
  display: flex;
  gap: 0.25rem;
  flex-wrap: wrap;
}
.truncate {
  display: inline-block;
  max-width: 320px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: middle;
}
.empty-state {
  padding: 1.5rem;
  text-align: center;
  color: #64748b;
  background: #f8fafc;
  border-radius: 6px;
  border: 1px dashed #e2e8f0;
}
.loading {
  padding: 3rem;
  text-align: center;
  color: #64748b;
}
.save-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  background: #fff;
  border-top: 1px solid #e2e8f0;
  padding: 0.85rem 1.5rem;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.75rem;
  box-shadow: 0 -2px 8px rgba(0, 0, 0, 0.06);
  z-index: 50;
}
.save-hint {
  margin-right: auto;
  color: #64748b;
  font-size: 0.85rem;
}
</style>
