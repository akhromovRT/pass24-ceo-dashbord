<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import InputText from 'primevue/inputtext'
import Tag from 'primevue/tag'
import ProgressBar from 'primevue/progressbar'
import { useOrganizationsStore } from '../stores/organizations'

const store = useOrganizationsStore()
const router = useRouter()
const search = ref('')
const page = ref(1)
const pageSize = 25

function loadData() {
  store.fetch({ search: search.value || undefined, page: page.value, page_size: pageSize })
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

function onPage(event: any) {
  page.value = Math.floor(event.first / pageSize) + 1
  loadData()
}

function onRowClick(event: any) {
  router.push(`/clients/${event.data.inn}`)
}

function formatCurrency(value: number | null) {
  if (value == null) return '—'
  return new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }).format(value)
}

function debtSeverity(value: number | null): "danger" | "warn" | "secondary" | undefined {
  if (!value || value <= 0) return 'secondary'
  if (value > 100000) return 'danger'
  if (value > 30000) return 'warn'
  return undefined
}
</script>

<template>
  <div class="billing-view">
    <div class="billing-header">
      <h1>Реестр клиентов</h1>
      <InputText v-model="search" placeholder="Поиск по имени или ИНН..." class="search-input" />
    </div>

    <DataTable
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
        <template #body="{ data }">
          {{ data.name_display || data.name_1c }}
        </template>
      </Column>
      <Column field="inn" header="ИНН" style="width: 130px" />
      <Column field="monthly_ap" header="АП/мес" sortable style="width: 130px">
        <template #body="{ data }">
          {{ formatCurrency(data.monthly_ap) }}
        </template>
      </Column>
      <Column field="total_debt" header="Долг" sortable style="width: 150px">
        <template #body="{ data }">
          <Tag :severity="debtSeverity(data.total_debt)">
            {{ formatCurrency(data.total_debt) }}
          </Tag>
        </template>
      </Column>
      <Column field="payment_score" header="Оценка" style="width: 120px">
        <template #body="{ data }">
          <ProgressBar
            v-if="data.payment_score != null"
            :value="data.payment_score"
            :showValue="true"
            style="height: 20px"
          />
          <span v-else>—</span>
        </template>
      </Column>
      <Column field="status" header="Статус" style="width: 110px">
        <template #body="{ data }">
          <Tag :severity="data.status === 'active' ? 'success' : 'secondary'">
            {{ data.status }}
          </Tag>
        </template>
      </Column>
      <Column field="objects" header="Объекты" style="width: 90px" />
      <Column field="city_region" header="Город" style="width: 150px" />
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
}

.billing-header h1 {
  margin: 0;
  font-size: 1.5rem;
  color: #1e293b;
}

.search-input {
  width: 320px;
}

.client-table {
  cursor: pointer;
}
</style>
