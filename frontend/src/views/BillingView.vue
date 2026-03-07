<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import InputText from 'primevue/inputtext'
import Tag from 'primevue/tag'
import ProgressBar from 'primevue/progressbar'
import SelectButton from 'primevue/selectbutton'
import { useOrganizationsStore } from '../stores/organizations'
import api from '../api/client'

const store = useOrganizationsStore()
const router = useRouter()
const search = ref('')
const page = ref(1)
const pageSize = 25

// Mode toggle
const mode = ref<'clients' | 'contracts'>('clients')
const modeOptions = [
  { label: 'По клиентам', value: 'clients' },
  { label: 'По договорам', value: 'contracts' },
]

// Contracts mode state
const contracts = ref<any[]>([])
const contractsTotal = ref(0)
const contractsLoading = ref(false)
const contractSortBy = ref('org_name')
const contractSortDir = ref('asc')

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

function loadData() {
  if (mode.value === 'clients') loadClients()
  else loadContracts()
}

onMounted(loadData)

let searchTimeout: ReturnType<typeof setTimeout>
watch(search, () => {
  clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => {
    page.value = 1
    loadData()
  }, 300)
})

watch(mode, () => {
  page.value = 1
  search.value = ''
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
  if (mode.value === 'clients') {
    router.push(`/clients/${event.data.inn}`)
  } else {
    router.push(`/clients/${event.data.org_inn}`)
  }
}

function formatCurrency(value: number | null) {
  if (value == null) return '—'
  return new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }).format(value)
}

function formatDate(val: string | null) {
  if (!val) return '—'
  return new Date(val).toLocaleDateString('ru-RU')
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
        <InputText v-model="search" :placeholder="mode === 'clients' ? 'Поиск по имени или ИНН...' : 'Поиск по контрагенту, ИНН, договору...'" class="search-input" />
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
      v-else
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
      <Column field="org_name" header="Контрагент" sortable style="min-width: 200px">
        <template #body="{ data }">{{ data.org_name }}</template>
      </Column>
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
      <Column field="org_object_type" header="Тип объекта" style="width: 130px">
        <template #body="{ data }">{{ data.org_object_type || '—' }}</template>
      </Column>
      <Column field="status" header="Статус" style="width: 120px">
        <template #body="{ data }">
          <Tag :severity="contractStatusSeverity(data.status)">{{ contractStatusLabel[data.status] || data.status }}</Tag>
        </template>
      </Column>
      <Column field="org_cloud_url" header="Облако" style="width: 90px">
        <template #body="{ data }">
          <a v-if="data.org_cloud_url" :href="data.org_cloud_url" target="_blank" @click.stop style="color: #6366f1">↗</a>
          <span v-else>—</span>
        </template>
      </Column>
      <Column field="org_system_number" header="№ сист." style="width: 90px">
        <template #body="{ data }">{{ data.org_system_number || '—' }}</template>
      </Column>
      <Column field="org_equipment" header="Оборудование" style="min-width: 150px">
        <template #body="{ data }">{{ data.org_equipment || '—' }}</template>
      </Column>
      <Column field="org_address" header="Адрес" style="min-width: 200px">
        <template #body="{ data }">{{ data.org_address || '—' }}</template>
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
}

.search-input {
  width: 320px;
}

.client-table,
.contract-table {
  cursor: pointer;
}
</style>
