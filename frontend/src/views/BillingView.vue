<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import InputText from 'primevue/inputtext'
import Tag from 'primevue/tag'
import ProgressBar from 'primevue/progressbar'
import SelectButton from 'primevue/selectbutton'
import MultiSelect from 'primevue/multiselect'
import { FilterMatchMode } from '@primevue/core/api'
import { useOrganizationsStore } from '../stores/organizations'
import api from '../api/client'

const store = useOrganizationsStore()
const router = useRouter()
const search = ref('')
const page = ref(1)
const pageSize = 25

// Mode toggle
const mode = ref<'clients' | 'contracts' | 'registry'>('clients')
const modeOptions = [
  { label: 'По клиентам', value: 'clients' },
  { label: 'По договорам', value: 'contracts' },
  { label: 'По реестру', value: 'registry' },
]

// Contracts mode state
const contracts = ref<any[]>([])
const contractsTotal = ref(0)
const contractsLoading = ref(false)
const contractSortBy = ref('org_name')
const contractSortDir = ref('asc')

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
  store.fetch({ search: search.value || undefined, page: page.value, page_size: pageSize })
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

function loadData() {
  if (mode.value === 'clients') loadClients()
  else if (mode.value === 'contracts') loadContracts()
  else loadRegistry()
}

onMounted(loadData)

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
  loadData()
})

function onPage(event: any) {
  page.value = Math.floor(event.first / pageSize) + 1
  loadData()
}

function onSort(event: any) {
  const fieldMap: Record<string, string> = {
    org_name: 'org_name',
    monthly_amount: 'monthly_amount',
    contract_date: 'contract_date',
  }
  contractSortBy.value = fieldMap[event.sortField] || 'org_name'
  contractSortDir.value = event.sortOrder === 1 ? 'asc' : 'desc'
  page.value = 1
  loadContracts()
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
</script>

<template>
  <div class="billing-view">
    <div class="billing-header">
      <h1>Реестр клиентов</h1>
      <div class="header-controls">
        <SelectButton v-model="mode" :options="modeOptions" optionLabel="label" optionValue="value" />
        <InputText
          v-model="search"
          :placeholder="mode === 'clients' ? 'Поиск по имени или ИНН...' :
                       mode === 'contracts' ? 'Поиск по контрагенту, ИНН, договору...' :
                       'Глобальный поиск по реестру...'"
          class="search-input"
        />
      </div>
    </div>

    <!-- Режим: По клиентам -->
    <DataTable
      v-if="mode === 'clients'"
      :value="store.items"
      :loading="store.loading"
      :lazy="true"
      :totalRecords="store.total"
      :rows="pageSize"
      :first="(page - 1) * pageSize"
      paginator
      stripedRows
      @page="onPage"
      @row-click="onRowClick"
      rowHover
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
      <Column field="payment_score" header="Оценка" style="width: 120px">
        <template #body="{ data }">
          <ProgressBar v-if="data.payment_score != null" :value="data.payment_score" :showValue="true" style="height: 20px" />
          <span v-else>—</span>
        </template>
      </Column>
      <Column field="status" header="Статус" style="width: 110px">
        <template #body="{ data }">
          <Tag :severity="data.status === 'active' ? 'success' : 'secondary'">{{ data.status }}</Tag>
        </template>
      </Column>
      <Column field="objects" header="Объекты" style="width: 90px" />
      <Column field="city_region" header="Город" style="width: 150px" />
    </DataTable>

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
      scrollHeight="calc(100vh - 220px)"
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
      scroll-height="calc(100vh - 240px)"
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
  margin-bottom: 1.5rem;
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

.client-table,
.contract-table,
.registry-table {
  cursor: pointer;
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
</style>
