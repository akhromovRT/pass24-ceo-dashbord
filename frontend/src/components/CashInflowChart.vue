<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

use([BarChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

interface InflowRow {
  label: string
  current: number
  advance: number
  arrears: number
  undetermined: number
  non_subscription: number
}

const props = defineProps<{ data: InflowRow[] }>()

function shortRub(v: number) {
  return v >= 1000000 ? `${(v / 1000000).toFixed(1)}M`
       : v >= 1000 ? `${(v / 1000).toFixed(0)}K` : `${v}`
}

const SEGMENTS = [
  { key: 'current', name: 'Текущий период', color: '#22c55e' },
  { key: 'arrears', name: 'Погашение долга', color: '#f59e0b' },
  { key: 'advance', name: 'Аванс', color: '#3b82f6' },
  { key: 'non_subscription', name: 'Непериодические', color: '#a855f7' },
  { key: 'undetermined', name: 'Не определён', color: '#94a3b8' },
] as const

const option = computed(() => ({
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  legend: { top: 0, type: 'scroll' },
  grid: { left: 64, right: 24, top: 32, bottom: 28 },
  xAxis: {
    type: 'category',
    data: props.data.map(r => r.label),
    axisLabel: { fontSize: 11 },
  },
  yAxis: {
    type: 'value',
    axisLabel: { formatter: (v: number) => shortRub(v) },
  },
  series: SEGMENTS.map(s => ({
    name: s.name,
    type: 'bar',
    stack: 'inflow',
    data: props.data.map(r => (r as unknown as Record<string, number>)[s.key]),
    itemStyle: { color: s.color },
    barMaxWidth: 36,
  })),
}))
</script>

<template>
  <v-chart :option="option" style="height: 280px" autoresize />
</template>
