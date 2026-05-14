<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart, LineChart, HeatmapChart } from 'echarts/charts'
import {
  GridComponent, TooltipComponent, LegendComponent, VisualMapComponent,
  DataZoomComponent, MarkLineComponent, TitleComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import Dialog from 'primevue/dialog'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Tag from 'primevue/tag'

import api from '../api/client'

use([
  BarChart, LineChart, HeatmapChart,
  GridComponent, TooltipComponent, LegendComponent, VisualMapComponent,
  DataZoomComponent, MarkLineComponent, TitleComponent, CanvasRenderer,
])

const router = useRouter()
const summary = ref<any>(null)
const mrrSeries = ref<any[]>([])
const aging = ref<any[]>([])
const matrix = ref<any>({ months: [], orgs: [], cells: [] })

const drawerOpen = ref(false)
const drawerBucket = ref<string | null>(null)
const drawerRows = ref<any[]>([])
const drawerLoading = ref(false)

onMounted(async () => {
  const [s, m, a, mx] = await Promise.all([
    api.get('/dashboard/summary'),
    api.get('/dashboard/mrr-plan-vs-fact?months=12'),
    api.get('/dashboard/aging'),
    api.get('/dashboard/payment-matrix?months=12'),
  ])
  summary.value = s.data
  mrrSeries.value = m.data
  aging.value = a.data
  matrix.value = mx.data
})

function fmt(value: number | null, digits = 0) {
  if (value == null) return '—'
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: digits }).format(value)
}
function fmtRub(value: number | null) {
  if (value == null) return '—'
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency', currency: 'RUB', maximumFractionDigits: 0,
  }).format(value)
}

// ---- MRR plan vs fact chart ----
const mrrChartOption = computed(() => ({
  tooltip: {
    trigger: 'axis',
    formatter: (params: any[]) => {
      const head = `<b>${params[0].axisValue}</b>`
      const lines = params.map(p => `${p.marker} ${p.seriesName}: <b>${fmtRub(p.value)}</b>`)
      return [head, ...lines].join('<br>')
    },
  },
  legend: { data: ['План MRR', 'Факт MRR'], top: 0 },
  grid: { left: 70, right: 30, top: 36, bottom: 30 },
  xAxis: {
    type: 'category',
    data: mrrSeries.value.map(s => s.label),
    axisLabel: { fontSize: 11 },
  },
  yAxis: {
    type: 'value',
    axisLabel: {
      formatter: (v: number) => v >= 1000000 ? `${(v / 1000000).toFixed(1)}M` :
                                v >= 1000 ? `${(v / 1000).toFixed(0)}K` : `${v}`,
    },
  },
  series: [
    {
      name: 'План MRR',
      type: 'line',
      data: mrrSeries.value.map(s => s.plan),
      lineStyle: { type: 'dashed', color: '#94a3b8', width: 2 },
      itemStyle: { color: '#94a3b8' },
      symbol: 'none',
    },
    {
      name: 'Факт MRR',
      type: 'bar',
      data: mrrSeries.value.map((s) => ({
        value: s.fact,
        itemStyle: {
          color: s.ratio == null ? '#94a3b8'
               : s.ratio >= 95 ? '#22c55e'
               : s.ratio >= 70 ? '#f59e0b'
               : '#ef4444',
        },
      })),
      barMaxWidth: 32,
    },
  ],
}))

// ---- Aging chart (clickable bars) ----
const agingChartOption = computed(() => {
  const colors: Record<string, string> = {
    '0-30': '#64748b', '31-60': '#f59e0b',
    '61-90': '#ef4444', '90+': '#7f1d1d',
  }
  return {
    tooltip: {
      trigger: 'item',
      formatter: (p: any) => {
        const a = aging.value[p.dataIndex] || {}
        return `<b>${p.name}</b> дней<br>Сумма долга: <b>${fmtRub(a.amount)}</b><br>Клиентов: <b>${a.count}</b><br><i>Кликните, чтобы открыть список</i>`
      },
    },
    grid: { left: 80, right: 30, top: 16, bottom: 30 },
    xAxis: {
      type: 'value',
      axisLabel: {
        formatter: (v: number) => v >= 1000000 ? `${(v / 1000000).toFixed(1)}M` :
                                  v >= 1000 ? `${(v / 1000).toFixed(0)}K` : `${v}`,
      },
    },
    yAxis: {
      type: 'category',
      data: aging.value.map(a => a.bucket),
      axisLabel: { fontSize: 12, fontWeight: 600 },
    },
    series: [{
      type: 'bar',
      data: aging.value.map(a => ({
        value: a.amount,
        itemStyle: { color: colors[a.bucket] || '#64748b' },
        label: { show: true, position: 'right', formatter: () => `${a.count}` },
      })),
      barMaxWidth: 28,
      cursor: 'pointer',
    }],
  }
})

async function onAgingClick(event: any) {
  if (event.componentType !== 'series') return
  const bucket = aging.value[event.dataIndex]?.bucket
  if (!bucket) return
  drawerBucket.value = bucket
  drawerOpen.value = true
  drawerLoading.value = true
  try {
    const res = await api.get(`/dashboard/aging/${encodeURIComponent(bucket)}`)
    drawerRows.value = res.data
  } finally {
    drawerLoading.value = false
  }
}

function openClient(inn: string) {
  router.push(`/clients/${inn}`)
}

// ---- Payment matrix (heatmap) ----
const matrixHeight = computed(() => Math.max(360, Math.min(1200, matrix.value.orgs.length * 18)))
const matrixChartOption = computed(() => {
  if (!matrix.value.orgs.length) return {}
  const heatmapData = matrix.value.cells.map((c: any) => [
    c.col, c.row, c.ratio == null ? null : Math.min(150, c.ratio),
  ])
  return {
    tooltip: {
      formatter: (p: any) => {
        const c = matrix.value.cells.find((cc: any) => cc.row === p.value[1] && cc.col === p.value[0])
        const org = matrix.value.orgs[p.value[1]]
        const month = matrix.value.months[p.value[0]]
        if (!c || !org) return ''
        return `<b>${org.name}</b><br>${month}<br>План: <b>${fmtRub(c.plan)}</b><br>Факт: <b>${fmtRub(c.paid)}</b>` +
               (c.ratio != null ? `<br>Собираемость: <b>${c.ratio}%</b>` : '')
      },
    },
    grid: { left: 240, right: 30, top: 70, bottom: 30 },
    xAxis: {
      type: 'category', data: matrix.value.months,
      position: 'top',
      splitArea: { show: true },
      axisLabel: { fontSize: 11 },
    },
    yAxis: {
      type: 'category',
      data: matrix.value.orgs.map((o: any) => o.name.length > 32 ? o.name.substring(0, 30) + '…' : o.name),
      splitArea: { show: true },
      axisLabel: { fontSize: 10, width: 220, overflow: 'truncate' },
    },
    visualMap: {
      min: 0, max: 100,
      calculable: false,
      orient: 'horizontal', left: 'center', top: 30,
      itemWidth: 12, itemHeight: 200,
      inRange: { color: ['#fef2f2', '#fee2e2', '#fed7aa', '#fef3c7', '#d1fae5', '#86efac', '#22c55e'] },
      text: ['100%+', '0%'],
      textStyle: { fontSize: 10 },
    },
    series: [{
      type: 'heatmap',
      data: heatmapData,
      emphasis: { itemStyle: { borderColor: '#1e293b', borderWidth: 1 } },
      itemStyle: { borderColor: '#f1f5f9', borderWidth: 1 },
    }],
  }
})

function onMatrixClick(event: any) {
  if (event.componentType !== 'series') return
  const row = event.value?.[1]
  const org = matrix.value.orgs[row]
  if (org?.inn) router.push(`/clients/${org.inn}`)
}

function deltaSeverity(pct: number | null): 'success' | 'danger' | 'secondary' {
  if (pct == null) return 'secondary'
  if (pct >= 0) return 'success'
  return 'danger'
}
function deltaIcon(pct: number | null): string {
  if (pct == null || pct === 0) return ''
  return pct > 0 ? '▲' : '▼'
}
function collectabilityPct(): number | null {
  if (!summary.value?.mrr_plan) return null
  return Math.round(summary.value.mrr_fact / summary.value.mrr_plan * 100)
}
</script>

<template>
  <div class="dashboard">
    <div class="dash-header">
      <h1>Аналитика CEO</h1>
      <div class="period-label" v-if="summary?.fact_month">
        Факт за месяц: <b>{{ summary.fact_month }}</b>
      </div>
    </div>

    <!-- KPI tiles -->
    <div class="kpi-grid" v-if="summary">
      <div class="kpi-tile primary">
        <div class="kpi-label">MRR Факт</div>
        <div class="kpi-value">{{ fmtRub(summary.mrr_fact) }}</div>
        <div class="kpi-sub">
          <span v-if="summary.mom_mrr_delta_pct != null" :class="['delta', deltaSeverity(summary.mom_mrr_delta_pct)]">
            {{ deltaIcon(summary.mom_mrr_delta_pct) }} {{ Math.abs(summary.mom_mrr_delta_pct) }}% м/м
          </span>
        </div>
      </div>

      <div class="kpi-tile">
        <div class="kpi-label">MRR План</div>
        <div class="kpi-value plan">{{ fmtRub(summary.mrr_plan) }}</div>
        <div class="kpi-sub" v-if="collectabilityPct() != null">
          Собираемость: <b>{{ collectabilityPct() }}%</b>
        </div>
      </div>

      <div class="kpi-tile">
        <div class="kpi-label">ARR План</div>
        <div class="kpi-value">{{ fmtRub(summary.arr_plan) }}</div>
        <div class="kpi-sub">12 × MRR план</div>
      </div>

      <div class="kpi-tile danger">
        <div class="kpi-label">Общий долг</div>
        <div class="kpi-value">{{ fmtRub(summary.total_debt) }}</div>
        <div class="kpi-sub">Активных алертов: {{ summary.open_alerts }}</div>
      </div>

      <div class="kpi-tile">
        <div class="kpi-label">Активные клиенты</div>
        <div class="kpi-value">{{ fmt(summary.active_clients) }}</div>
        <div class="kpi-sub">
          <span class="delta success">+{{ summary.new_30d }}</span> за 30д,
          <span class="delta success">+{{ summary.new_90d }}</span> за 90д
        </div>
      </div>

      <div class="kpi-tile warn">
        <div class="kpi-label">Ушедшие (60д без оплаты)</div>
        <div class="kpi-value">{{ fmt(summary.churned_60d) }}</div>
        <div class="kpi-sub">Среди подписочных</div>
      </div>
    </div>

    <!-- Charts row -->
    <div class="charts-row">
      <div class="chart-card mrr-chart">
        <div class="chart-title">MRR: план vs факт (12 мес)</div>
        <v-chart :option="mrrChartOption" style="height: 280px" autoresize />
        <div class="chart-legend">
          <span class="legend-dot" style="background: #22c55e" /> ≥95%
          <span class="legend-dot" style="background: #f59e0b" /> 70-95%
          <span class="legend-dot" style="background: #ef4444" /> &lt;70%
          (% от плана)
        </div>
      </div>

      <div class="chart-card aging-chart">
        <div class="chart-title">Просрочка по корзинам ▶ клик для деталей</div>
        <v-chart
          :option="agingChartOption"
          style="height: 280px"
          autoresize
          @click="onAgingClick"
        />
      </div>
    </div>

    <!-- Payment matrix heatmap -->
    <div class="chart-card matrix-card">
      <div class="chart-title">
        Шахматка платежей: клиенты × месяцы ({{ matrix.orgs.length }} активных подписчиков)
        <span class="hint">▶ клик по строке → карточка клиента</span>
      </div>
      <v-chart
        v-if="matrix.orgs.length"
        :option="matrixChartOption"
        :style="{ height: matrixHeight + 'px' }"
        autoresize
        @click="onMatrixClick"
      />
      <div v-else class="empty-state">Нет активных подписчиков с monthly_amount.</div>
    </div>

    <!-- Drawer: aging detail -->
    <Dialog
      v-model:visible="drawerOpen"
      :header="`Должники в корзине: ${drawerBucket}`"
      modal
      :style="{ width: '900px', maxWidth: '95vw' }"
    >
      <DataTable :value="drawerRows" :loading="drawerLoading" stripedRows>
        <Column field="name" header="Клиент" sortable>
          <template #body="{ data }">
            <a class="drawer-link" @click.prevent="openClient(data.inn)">{{ data.name }}</a>
          </template>
        </Column>
        <Column field="inn" header="ИНН" style="width: 130px" />
        <Column field="monthly_ap" header="АП/мес" sortable style="width: 130px">
          <template #body="{ data }">{{ fmtRub(data.monthly_ap) }}</template>
        </Column>
        <Column field="total_debt" header="Долг" sortable style="width: 150px">
          <template #body="{ data }">
            <Tag severity="danger">{{ fmtRub(data.total_debt) }}</Tag>
          </template>
        </Column>
        <Column field="months_overdue" header="Месяцев просрочки" sortable style="width: 150px">
          <template #body="{ data }">{{ data.months_overdue }}</template>
        </Column>
        <Column field="status" header="Статус" style="width: 100px">
          <template #body="{ data }">
            <Tag :severity="data.status === 'active' ? 'success' : 'secondary'">{{ data.status }}</Tag>
          </template>
        </Column>
      </DataTable>
    </Dialog>
  </div>
</template>

<style scoped>
.dashboard {
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.dash-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}
.dash-header h1 {
  margin: 0;
  font-size: 1.5rem;
  color: #1e293b;
}
.period-label {
  color: #64748b;
  font-size: 0.875rem;
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 0.75rem;
}
@media (max-width: 1400px) {
  .kpi-grid { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 800px) {
  .kpi-grid { grid-template-columns: repeat(2, 1fr); }
}

.kpi-tile {
  background: white;
  border: 1px solid #e2e8f0;
  border-left: 4px solid #cbd5e1;
  border-radius: 8px;
  padding: 1rem 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  min-height: 100px;
}
.kpi-tile.primary { border-left-color: #6366f1; }
.kpi-tile.danger  { border-left-color: #ef4444; }
.kpi-tile.warn    { border-left-color: #f59e0b; }

.kpi-label {
  font-size: 0.75rem;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.kpi-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: #1e293b;
  letter-spacing: -0.02em;
}
.kpi-value.plan { color: #475569; font-weight: 500; }
.kpi-sub {
  font-size: 0.8rem;
  color: #64748b;
  margin-top: auto;
}
.delta {
  display: inline-block;
  font-weight: 600;
  font-size: 0.8rem;
}
.delta.success { color: #16a34a; }
.delta.danger  { color: #dc2626; }
.delta.secondary { color: #64748b; }

.charts-row {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: 0.75rem;
}
@media (max-width: 1200px) {
  .charts-row { grid-template-columns: 1fr; }
}

.chart-card {
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 1rem 1.25rem;
}
.chart-title {
  font-size: 0.95rem;
  font-weight: 600;
  color: #1e293b;
  margin-bottom: 0.5rem;
}
.chart-title .hint {
  font-weight: 400;
  font-size: 0.8rem;
  color: #94a3b8;
  margin-left: 0.5rem;
}
.chart-legend {
  font-size: 0.75rem;
  color: #64748b;
  margin-top: 0.25rem;
}
.legend-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 2px;
  margin: 0 3px 0 6px;
  vertical-align: middle;
}

.matrix-card {
  overflow: auto;
}

.empty-state {
  padding: 2rem;
  text-align: center;
  color: #64748b;
}

.drawer-link {
  color: #6366f1;
  cursor: pointer;
  text-decoration: none;
}
.drawer-link:hover { text-decoration: underline; }
</style>
