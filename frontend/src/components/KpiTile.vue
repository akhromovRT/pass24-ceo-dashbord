<script setup lang="ts">
import { computed } from 'vue'
import type { RouteLocationRaw } from 'vue-router'

const props = defineProps<{
  label: string
  value: string
  sub?: string
  accent?: 'primary' | 'danger' | 'warn' | 'success' | 'neutral'
  pct?: number | null
  hint?: string
  to?: RouteLocationRaw
}>()

const pctClass = computed(() => {
  const p = props.pct
  if (p == null) return null
  if (p < 30) return 'pct-red'
  if (p < 50) return 'pct-orange'
  if (p < 80) return 'pct-yellow'
  return 'pct-green'
})

const tileClass = computed(() => [
  'kpi-tile',
  pctClass.value || props.accent || 'neutral',
  props.to ? 'kpi-tile--clickable' : '',
])

const tooltipValue = computed(() => {
  if (!props.hint) return undefined
  const suffix = props.to ? ' · кликните для состава' : ''
  return { value: props.hint + suffix, showDelay: 200 }
})
</script>

<template>
  <router-link
    v-if="to"
    :to="to"
    :class="tileClass"
    v-tooltip.bottom="tooltipValue"
  >
    <div class="kpi-label">
      {{ label }}
      <i v-if="hint" class="pi pi-info-circle kpi-info" />
    </div>
    <div class="kpi-value">{{ value }}</div>
    <div class="kpi-sub" v-if="sub">{{ sub }}</div>
  </router-link>
  <div
    v-else
    :class="tileClass"
    v-tooltip.bottom="tooltipValue"
  >
    <div class="kpi-label">
      {{ label }}
      <i v-if="hint" class="pi pi-info-circle kpi-info" />
    </div>
    <div class="kpi-value">{{ value }}</div>
    <div class="kpi-sub" v-if="sub">{{ sub }}</div>
  </div>
</template>

<style scoped>
.kpi-tile {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-left: 4px solid #cbd5e1;
  border-radius: 8px;
  padding: 1rem 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  min-height: 104px;
  text-decoration: none;
  color: inherit;
  transition: transform 120ms ease, box-shadow 120ms ease;
}
.kpi-tile.primary { border-left-color: #6366f1; }
.kpi-tile.danger  { border-left-color: #ef4444; }
.kpi-tile.warn    { border-left-color: #f59e0b; }
.kpi-tile.success { border-left-color: #22c55e; }

.kpi-tile.pct-red    { border-left-color: #ef4444; background: #fef2f2; }
.kpi-tile.pct-orange { border-left-color: #f97316; background: #fff7ed; }
.kpi-tile.pct-yellow { border-left-color: #eab308; background: #fefce8; }
.kpi-tile.pct-green  { border-left-color: #22c55e; background: #f0fdf4; }

.kpi-tile--clickable { cursor: pointer; }
.kpi-tile--clickable:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08);
}

.kpi-label {
  font-size: 0.72rem; color: #64748b;
  text-transform: uppercase; letter-spacing: 0.04em;
  display: flex; align-items: center; gap: 0.3rem;
}
.kpi-info { font-size: 0.8rem; color: #94a3b8; cursor: help; }
.kpi-value {
  font-size: 1.5rem; font-weight: 700; color: #1e293b;
  letter-spacing: -0.02em;
}
.kpi-sub { font-size: 0.78rem; color: #64748b; margin-top: auto; }
</style>
