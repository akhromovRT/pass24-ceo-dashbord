<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Tag from 'primevue/tag'
import Select from 'primevue/select'
import { useToast } from 'primevue/usetoast'
import api from '../api/client'
import SegmentBand from '../components/SegmentBand.vue'

const router = useRouter()
const route = useRoute()
const toast = useToast()

const debtors = ref<any[]>([])
const loading = ref(true)
const bucket = ref<string>(
  typeof route.query.bucket === 'string' ? route.query.bucket : 'all'
)

const statusOptions = [
  { label: 'Активен', value: 'active' },
  { label: 'Приостановлен', value: 'suspended' },
  { label: 'Отток', value: 'churned' },
  { label: 'Потенциальный', value: 'prospect' },
]

onMounted(async () => {
  try {
    const res = await api.get('/billing/debtors')
    debtors.value = res.data
  } finally {
    loading.value = false
  }
})

const BUCKETS = ['0-30', '31-60', '61-90', '90+']

const filteredRows = computed(() =>
  bucket.value === 'all'
    ? debtors.value
    : debtors.value.filter(r => r.aging_bucket === bucket.value)
)

const metrics = computed(() => {
  const rows = debtors.value
  const totalDebt = rows.reduce((s, r) => s + (r.total_debt || 0), 0)
  const b90 = rows.filter(r => r.aging_bucket === '90+')
  const sum90 = b90.reduce((s, r) => s + (r.total_debt || 0), 0)
  const withMonths = rows.filter(r => r.months_overdue != null)
  const avgMonths = withMonths.length
    ? withMonths.reduce((s, r) => s + r.months_overdue, 0) / withMonths.length
    : 0
  return [
    { label: 'Общий долг', value: fmtRub(totalDebt) },
    { label: 'Должников', value: String(rows.length) },
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
</script>

<template>
  <div class="debtors-view">
    <h1>Реестр должников</h1>

    <SegmentBand :metrics="metrics" :segments="segments" v-model="bucket" />

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
      <Column field="payment_score" header="Оценка" style="width: 90px">
        <template #body="{ data }">{{ data.payment_score ?? '—' }}</template>
      </Column>
    </DataTable>
  </div>
</template>

<style scoped>
.debtors-view {
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}
.debtors-view h1 {
  font-size: 1.5rem;
  color: #1e293b;
  margin: 0;
}
.debtors-table {
  cursor: pointer;
}
</style>
