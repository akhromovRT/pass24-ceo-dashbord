<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import Select from 'primevue/select'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
import {
  GridComponent, TooltipComponent, LegendComponent, MarkLineComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

import api from '../api/client'
import KpiTile from '../components/KpiTile.vue'
import AttentionPanel from '../components/AttentionPanel.vue'
import CashInflowChart from '../components/CashInflowChart.vue'

use([
  BarChart, LineChart,
  GridComponent, TooltipComponent, LegendComponent, MarkLineComponent,
  CanvasRenderer,
])

const router = useRouter()

function compositionLink(metric: string, period?: string | null) {
  return {
    path: '/reports',
    query: {
      preset: 'composition',
      metric,
      ...(period ? { period } : {}),
    },
  }
}

const summary = ref<any>(null)
const trend = ref<any[]>([])
const aging = ref<any[]>([])
const attention = ref<any[]>([])
const cashInflow = ref<any[]>([])
const selectedYear = ref<number | 'all'>('all')

onMounted(async () => {
  const [s, t, a, at, ci] = await Promise.all([
    api.get('/dashboard/summary'),
    api.get('/dashboard/collection-trend'),
    api.get('/dashboard/aging'),
    api.get('/dashboard/attention'),
    api.get('/dashboard/cash-inflow'),
  ])
  summary.value = s.data
  trend.value = t.data
  aging.value = a.data
  attention.value = at.data
  cashInflow.value = ci.data
  // по умолчанию — текущий год, чтобы график был читаемым
  const years = trend.value.map((r: any) => r.year)
  selectedYear.value = years.length ? Math.max(...years) : 'all'
})

// --- описания метрик (всплывают при наведении на плитку) --------------------
const HINTS: Record<string, string> = {
  mrrFact: 'Сколько абонплаты собрали за последний закрытый месяц. ' +
    'Норма для компании — 90%+. Ниже нормы — усилить взыскание, ' +
    'разобрать крупных неплательщиков в разделе «Должники».',
  mrrPlan: 'Сколько абонплаты должно приходить в месяц при 100% оплате ' +
    '(сумма АП активных клиентов). Снижение — отток клиентов или урезание тарифов.',
  sbor: 'Сколько собрано за текущий, ещё не закрытый месяц. Сравнивайте ' +
    '% сбора с долей прошедших дней: отставание = риск недосбора к концу месяца.',
  debt: 'Сумма к взысканию по данным 1С. Рост долга и высокая доля 90+ — ' +
    'сигнал активизировать взыскание. Клик по графику ниже открывает список.',
  active: 'Сколько клиентов в статусе «Активен» — это база регулярной выручки.',
  newPrev: 'Сколько клиентов впервые заплатили в прошлом (закрытом) месяце.',
  newCurr: 'Сколько клиентов впервые заплатили в текущем месяце (месяц ещё идёт).',
  newYear: 'Сколько клиентов впервые заплатили с начала текущего года — ' +
    'приток новой базы за год (число растёт до конца года).',
  stopped: 'Сколько клиентов перестали платить с начала года: последний платёж ' +
    'был в этом году, но более 60 дней назад. Рост — повод разобрать причины ухода.',
  churn: 'Доля оттока: ушедшие с начала года ÷ клиенты с платежами в прошлом году. ' +
    'Чем выше — тем больше теряем базу; разбирать причины и удерживать клиентов.',
}

const RU_MONTHS = [
  'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
  'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь',
]
function ruMonth(label: string | null | undefined): string {
  if (!label) return ''
  const [y, m] = label.split('-').map(Number)
  if (!y || !m) return label
  return `${RU_MONTHS[m - 1]} ${y}`
}

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
function shortRub(v: number) {
  return v >= 1000000 ? `${(v / 1000000).toFixed(1)}M`
       : v >= 1000 ? `${(v / 1000).toFixed(0)}K` : `${v}`
}

const currentMonthPct = computed(() => {
  if (!summary.value?.mrr_plan) return null
  return Math.round(summary.value.current_month_collected / summary.value.mrr_plan * 100)
})

// --- график собираемости: фильтр по годам -----------------------------------
const yearOptions = computed(() => {
  const ys = [...new Set(trend.value.map((r: any) => r.year))].sort(
    (a, b) => (b as number) - (a as number),
  )
  return [
    { label: 'Все годы', value: 'all' as const },
    ...ys.map(y => ({ label: String(y), value: y as number })),
  ]
})
const filteredTrend = computed(() =>
  selectedYear.value === 'all'
    ? trend.value
    : trend.value.filter((r: any) => r.year === selectedYear.value),
)

const hasTrend = computed(() => filteredTrend.value.length > 0)
const collectionChartOption = computed(() => ({
  tooltip: {
    trigger: 'axis',
    formatter: (params: any[]) => {
      const row = filteredTrend.value[params[0].dataIndex] || {}
      const tail = row.is_current_month ? '<br><i>месяц не закрыт</i>' : ''
      return `<b>${row.label}</b><br>Начислено: <b>${fmtRub(row.accrued)}</b><br>` +
             `Собрано: <b>${fmtRub(row.collected)}</b><br>` +
             `Собираемость: <b>${row.ratio ?? '—'}%</b>${tail}`
    },
  },
  legend: { data: ['Начислено', 'Собрано'], top: 0 },
  grid: { left: 64, right: 24, top: 36, bottom: 28 },
  xAxis: {
    type: 'category',
    data: filteredTrend.value.map(s => s.label),
    axisLabel: { fontSize: 11 },
  },
  yAxis: {
    type: 'value',
    axisLabel: { formatter: (v: number) => shortRub(v) },
  },
  series: [
    {
      name: 'Начислено',
      type: 'line',
      data: filteredTrend.value.map(s => s.accrued),
      lineStyle: { type: 'dashed', color: '#94a3b8', width: 2 },
      itemStyle: { color: '#94a3b8' },
      symbol: 'none',
    },
    {
      name: 'Собрано',
      type: 'bar',
      data: filteredTrend.value.map(s => ({
        value: s.collected,
        itemStyle: {
          color: s.is_current_month ? '#cbd5e1'
               : s.ratio == null ? '#94a3b8'
               : s.ratio >= 95 ? '#22c55e'
               : s.ratio >= 70 ? '#f59e0b'
               : '#ef4444',
        },
      })),
      barMaxWidth: 36,
    },
  ],
}))

const AGING_ORDER = ['90+', '61-90', '31-60', '0-30']
const AGING_COLORS: Record<string, string> = {
  '90+': '#7f1d1d', '61-90': '#ef4444', '31-60': '#f59e0b', '0-30': '#64748b',
}
const agingSorted = computed(() =>
  AGING_ORDER.map(b => aging.value.find(a => a.bucket === b))
    .filter((x): x is any => x != null)
)
const agingChartOption = computed(() => ({
  tooltip: {
    trigger: 'item',
    formatter: (p: any) => {
      const a = agingSorted.value[p.dataIndex] || {}
      return `<b>${p.name}</b> дней<br>Долг: <b>${fmtRub(a.amount)}</b><br>` +
             `Клиентов: <b>${a.count}</b><br><i>клик — список должников</i>`
    },
  },
  grid: { left: 64, right: 48, top: 12, bottom: 24 },
  xAxis: {
    type: 'value',
    axisLabel: { formatter: (v: number) => shortRub(v) },
  },
  yAxis: {
    type: 'category',
    data: agingSorted.value.map(a => a.bucket),
    axisLabel: { fontSize: 12, fontWeight: 600 },
  },
  series: [{
    type: 'bar',
    data: agingSorted.value.map(a => ({
      value: a.amount,
      itemStyle: { color: AGING_COLORS[a.bucket] || '#64748b' },
      label: { show: true, position: 'right', formatter: () => `${a.count}` },
    })),
    barMaxWidth: 30,
    cursor: 'pointer',
  }],
}))

function onAgingClick(event: any) {
  if (event.componentType !== 'series') return
  const bucket = agingSorted.value[event.dataIndex]?.bucket
  if (bucket) router.push(`/debtors?bucket=${encodeURIComponent(bucket)}`)
}
</script>

<template>
  <div class="dashboard">
    <div class="dash-header">
      <h1>Аналитика CEO</h1>
      <div class="period-label" v-if="summary?.fact_month">
        Факт за месяц: <b>{{ ruMonth(summary.fact_month) }}</b>
      </div>
    </div>

    <section class="kpi-section" v-if="summary">
      <div class="kpi-section-title">Финансы</div>
      <div class="kpi-grid kpi-grid-4">
        <KpiTile
          :label="`MRR факт · ${ruMonth(summary.fact_month)}`"
          :value="fmtRub(summary.mrr_fact)"
          :sub="summary.collection_rate_fact != null
            ? `собрано ${summary.collection_rate_fact}% от плана · норма 90%` : ''"
          :pct="summary.collection_rate_fact"
          :hint="HINTS.mrrFact"
          accent="primary"
          :to="compositionLink('mrr_fact', summary.fact_month)"
        />
        <KpiTile
          label="MRR план"
          :value="fmtRub(summary.mrr_plan)"
          sub="база подписки"
          :hint="HINTS.mrrPlan"
          accent="neutral"
          :to="compositionLink('mrr_plan')"
        />
        <KpiTile
          :label="`Сбор · ${ruMonth(summary.current_month_label)} (текущий)`"
          :value="fmtRub(summary.current_month_collected)"
          :sub="`${currentMonthPct ?? '—'}% плана · день ${summary.days_passed}/${summary.days_in_month}`"
          :pct="currentMonthPct"
          :hint="HINTS.sbor"
          :to="compositionLink('collected_current', summary.current_month_label)"
        />
        <KpiTile
          label="Долг активных"
          :value="fmtRub(summary.total_debt_active ?? summary.total_debt)"
          :sub="summary.total_debt_writeoff
            ? `к списанию: ${fmtRub(summary.total_debt_writeoff)} · 90+: ${fmtRub(summary.debt_90plus_amount)} (${summary.debt_90plus_share}%)`
            : `90+: ${fmtRub(summary.debt_90plus_amount)} (${summary.debt_90plus_share}%)`"
          :hint="HINTS.debt"
          accent="danger"
        />
      </div>
    </section>

    <section class="kpi-section" v-if="summary">
      <div class="kpi-section-title">Клиентская база</div>
      <div class="kpi-grid kpi-grid-6">
        <KpiTile
          label="Активные клиенты"
          :value="fmt(summary.active_clients)"
          sub="всего в статусе «Активен»"
          :hint="HINTS.active"
          accent="success"
          :to="compositionLink('active_clients')"
        />
        <KpiTile
          label="Новые за год"
          :value="fmt(summary.new_paid_curr_year)"
          :sub="`впервые заплатили в ${summary.current_month_label?.slice(0, 4)}`"
          :hint="HINTS.newYear"
          accent="success"
          :to="compositionLink('new_paid_curr_year', summary.current_month_label?.slice(0, 4))"
        />
        <KpiTile
          :label="`Новые · ${ruMonth(summary.fact_month)}`"
          :value="fmt(summary.new_paid_prev_month)"
          sub="впервые заплатили"
          :hint="HINTS.newPrev"
          accent="success"
          :to="compositionLink('new_paid_prev_month', summary.fact_month)"
        />
        <KpiTile
          :label="`Новые · ${ruMonth(summary.current_month_label)}`"
          :value="fmt(summary.new_paid_curr_month)"
          sub="впервые заплатили · месяц идёт"
          :hint="HINTS.newCurr"
          accent="success"
          :to="compositionLink('new_paid_curr_month', summary.current_month_label)"
        />
        <KpiTile
          label="Отток с начала года"
          :value="fmt(summary.stopped_since_year_start)"
          sub="перестали платить"
          :hint="HINTS.stopped"
          accent="danger"
          :to="compositionLink('stopped_since_year_start')"
        />
        <KpiTile
          label="Churn rate"
          :value="summary.churn_rate != null ? `${summary.churn_rate}%` : '—'"
          sub="доля ушедших за год"
          :hint="HINTS.churn"
          accent="warn"
        />
      </div>
    </section>

    <div class="charts-row">
      <div class="chart-card">
        <div class="chart-head">
          <div class="chart-title">Собираемость по месяцам (собрано за период ÷ начислено)</div>
          <Select
            v-model="selectedYear"
            :options="yearOptions"
            optionLabel="label"
            optionValue="value"
            class="year-select"
          />
        </div>
        <v-chart
          v-if="hasTrend"
          :option="collectionChartOption"
          style="height: 280px"
          autoresize
        />
        <div v-else class="empty-state">Нет данных о начислениях.</div>
        <div class="chart-legend">
          <span class="legend-dot" style="background: #22c55e" /> ≥95%
          <span class="legend-dot" style="background: #f59e0b" /> 70-95%
          <span class="legend-dot" style="background: #ef4444" /> &lt;70%
          собираемости · <span class="legend-dot" style="background: #cbd5e1" /> текущий месяц
        </div>
      </div>

      <div class="chart-card">
        <div class="chart-title">Структура долга ▶ клик для списка</div>
        <v-chart
          :option="agingChartOption"
          style="height: 280px"
          autoresize
          @click="onAgingClick"
        />
        <div class="chart-legend">
          Возраст — по календарным месяцам неоплаты. Каждый клиент в одной
          корзине; сумма корзин равна плитке «Долг».
        </div>
      </div>
    </div>

    <div class="chart-card">
      <div class="chart-title">Структура поступлений по месяцу прихода денег</div>
      <CashInflowChart v-if="cashInflow.length" :data="cashInflow" />
      <div v-else class="empty-state">Нет данных о поступлениях.</div>
    </div>

    <AttentionPanel :items="attention" />
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
.kpi-section {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.kpi-section-title {
  font-size: 0.8rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #94a3b8;
}
.kpi-grid {
  display: grid;
  gap: 0.75rem;
}
.kpi-grid-4 { grid-template-columns: repeat(4, 1fr); }
.kpi-grid-5 { grid-template-columns: repeat(5, 1fr); }
.kpi-grid-6 { grid-template-columns: repeat(6, 1fr); }
@media (max-width: 1200px) {
  .kpi-grid-4, .kpi-grid-5, .kpi-grid-6 { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 700px) {
  .kpi-grid-4, .kpi-grid-5, .kpi-grid-6 { grid-template-columns: repeat(2, 1fr); }
}
.charts-row {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: 0.75rem;
}
@media (max-width: 1100px) {
  .charts-row { grid-template-columns: 1fr; }
}
.chart-card {
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 1rem 1.25rem;
}
.chart-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  margin-bottom: 0.5rem;
}
.chart-title {
  font-size: 0.95rem;
  font-weight: 600;
  color: #1e293b;
  margin-bottom: 0.5rem;
}
.chart-head .chart-title {
  margin-bottom: 0;
}
.year-select {
  flex-shrink: 0;
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
.empty-state {
  padding: 2rem;
  text-align: center;
  color: #64748b;
}
</style>
