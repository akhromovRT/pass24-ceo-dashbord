<script setup lang="ts">
import { onMounted, computed } from 'vue'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Tag from 'primevue/tag'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart, BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import DashboardWidget from '../components/DashboardWidget.vue'
import { useDashboardStore } from '../stores/dashboard'
import api from '../api/client'
import { ref } from 'vue'

use([LineChart, BarChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const store = useDashboardStore()
const problemClients = ref<any[]>([])

onMounted(async () => {
  await store.fetchAll()
  try {
    const res = await api.get('/billing/debtors', { params: { min_debt: 100000 } })
    problemClients.value = res.data.slice(0, 10)
  } catch { /* ignore */ }
})

function formatCurrency(value: number) {
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency', currency: 'RUB', maximumFractionDigits: 0,
  }).format(value)
}

const mrrChartOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  legend: { data: ['Продано (АП)', 'Оплачено (АП)'] },
  xAxis: {
    type: 'category',
    data: store.mrrTrend.map(p => `${p.month}/${p.year}`),
  },
  yAxis: { type: 'value' },
  series: [
    { name: 'Продано (АП)', type: 'line', data: store.mrrTrend.map(p => p.sold_ap), color: '#6366f1', smooth: true },
    { name: 'Оплачено (АП)', type: 'line', data: store.mrrTrend.map(p => p.paid_ap), color: '#22c55e', smooth: true },
  ],
}))

const agingChartOption = computed(() => {
  const bucketOrder = ['0-30', '31-60', '61-90', '90+']
  const colors = ['#6b7280', '#eab308', '#f97316', '#ef4444']
  const amounts = bucketOrder.map(b => {
    const item = store.aging.find(a => a.bucket === b)
    return item ? item.amount : 0
  })

  return {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'value' },
    yAxis: {
      type: 'category',
      data: ['90+', '61-90', '31-60', '0-30'],
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
</script>

<template>
  <div class="dashboard" v-if="store.summary">
    <h1>CEO Dashboard</h1>

    <div class="widgets-row">
      <DashboardWidget
        title="MRR"
        :value="formatCurrency(store.summary.mrr)"
        :subtitle="`ARR: ${formatCurrency(store.summary.arr)}`"
        icon="pi pi-chart-line"
        color="#6366f1"
      />
      <DashboardWidget
        title="Общий долг"
        :value="formatCurrency(store.summary.total_debt)"
        icon="pi pi-exclamation-triangle"
        color="#ef4444"
      />
      <DashboardWidget
        title="Активные клиенты"
        :value="store.summary.active_clients"
        icon="pi pi-users"
        color="#22c55e"
      />
      <DashboardWidget
        title="Открытые алерты"
        :value="store.summary.open_alerts"
        icon="pi pi-bell"
        color="#f59e0b"
      />
    </div>

    <div class="charts-row">
      <div class="chart-card">
        <h3>MRR Trend (12 мес)</h3>
        <v-chart :option="mrrChartOption" style="height: 300px" autoresize />
      </div>
      <div class="chart-card">
        <h3>Aging (просрочка)</h3>
        <v-chart :option="agingChartOption" style="height: 300px" autoresize />
      </div>
    </div>

    <div class="problem-section" v-if="problemClients.length">
      <h3>Проблемные клиенты (долг > 100K)</h3>
      <DataTable :value="problemClients" stripedRows>
        <Column header="Клиент">
          <template #body="{ data }">{{ data.name_display || data.name_1c }}</template>
        </Column>
        <Column field="inn" header="ИНН" style="width: 130px" />
        <Column field="total_debt" header="Долг" style="width: 150px">
          <template #body="{ data }">
            <Tag severity="danger">{{ formatCurrency(data.total_debt) }}</Tag>
          </template>
        </Column>
        <Column field="payment_score" header="Оценка" style="width: 100px" />
        <Column field="status" header="Статус" style="width: 110px" />
      </DataTable>
    </div>
  </div>
  <div v-else class="loading">Загрузка...</div>
</template>

<style scoped>
.dashboard {
  padding: 1.5rem;
}

.dashboard h1 {
  font-size: 1.5rem;
  color: #1e293b;
  margin: 0 0 1.5rem;
}

.widgets-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.charts-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.chart-card {
  background: white;
  border-radius: 8px;
  padding: 1.25rem;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}

.chart-card h3 {
  margin: 0 0 0.75rem;
  font-size: 1rem;
  color: #374151;
}

.problem-section h3 {
  font-size: 1rem;
  color: #374151;
  margin: 0 0 0.75rem;
}

.loading {
  padding: 3rem;
  text-align: center;
  color: #64748b;
}
</style>
