<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Tag from 'primevue/tag'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import api from '../api/client'

use([BarChart, GridComponent, TooltipComponent, CanvasRenderer])

const router = useRouter()
const debtors = ref<any[]>([])
const aging = ref<any[]>([])
const loading = ref(true)

onMounted(async () => {
  try {
    const [debtorsRes, agingRes] = await Promise.all([
      api.get('/billing/debtors'),
      api.get('/dashboard/aging'),
    ])
    debtors.value = debtorsRes.data
    aging.value = agingRes.data
  } finally {
    loading.value = false
  }
})

import { computed } from 'vue'

const agingChartOption = computed(() => {
  const bucketOrder = ['0-30', '31-60', '61-90', '90+']
  const colors = ['#6b7280', '#eab308', '#f97316', '#ef4444']
  const amounts = bucketOrder.map(b => {
    const item = aging.value.find((a: any) => a.bucket === b)
    return item ? item.amount : 0
  })

  return {
    tooltip: {
      trigger: 'axis',
      formatter: (params: any) => {
        const p = params[0]
        return `${p.name}: ${new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }).format(p.value)}`
      },
    },
    xAxis: { type: 'value' },
    yAxis: {
      type: 'category',
      data: ['90+ дней', '61-90 дней', '31-60 дней', '0-30 дней'],
    },
    series: [{
      type: 'bar',
      data: [...amounts].reverse().map((v, i) => ({
        value: v,
        itemStyle: { color: colors[3 - i] },
      })),
    }],
  }
})

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

function onRowClick(event: any) {
  router.push(`/clients/${event.data.inn}`)
}
</script>

<template>
  <div class="debtors-view">
    <h1>Должники</h1>

    <div class="aging-chart-container">
      <h3>Aging buckets (просрочка по срокам)</h3>
      <v-chart :option="agingChartOption" style="height: 200px" autoresize />
    </div>

    <DataTable
      :value="debtors"
      :loading="loading"
      stripedRows
      rowHover
      @row-click="onRowClick"
      class="debtors-table"
    >
      <Column header="Клиент">
        <template #body="{ data }">
          {{ data.name_display || data.name_1c }}
        </template>
      </Column>
      <Column field="inn" header="ИНН" style="width: 130px" />
      <Column field="monthly_ap" header="АП/мес" style="width: 130px">
        <template #body="{ data }">{{ formatCurrency(data.monthly_ap) }}</template>
      </Column>
      <Column field="total_debt" header="Долг" sortable style="width: 150px">
        <template #body="{ data }">
          <Tag :severity="debtSeverity(data.total_debt)">
            {{ formatCurrency(data.total_debt) }}
          </Tag>
        </template>
      </Column>
      <Column field="payment_score" header="Оценка" style="width: 100px" />
      <Column field="status" header="Статус" style="width: 110px">
        <template #body="{ data }">
          <Tag :severity="data.status === 'active' ? 'success' : 'secondary'">
            {{ data.status }}
          </Tag>
        </template>
      </Column>
    </DataTable>
  </div>
</template>

<style scoped>
.debtors-view {
  padding: 1.5rem;
}

.debtors-view h1 {
  font-size: 1.5rem;
  color: #1e293b;
  margin: 0 0 1.5rem;
}

.aging-chart-container {
  background: white;
  border-radius: 8px;
  padding: 1.25rem;
  margin-bottom: 1.5rem;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}

.aging-chart-container h3 {
  margin: 0 0 0.75rem;
  font-size: 1rem;
  color: #374151;
}

.debtors-table {
  cursor: pointer;
}
</style>
