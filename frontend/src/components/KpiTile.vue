<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  label: string
  value: string
  sub?: string
  accent?: 'primary' | 'danger' | 'warn' | 'success' | 'neutral'
  pct?: number | null
  hint?: string
}>()

// Шкала окраса по проценту: <30 красный, 30–50 оранжевый, 50–80 жёлтый, 80–100 зелёный
const pctClass = computed(() => {
  const p = props.pct
  if (p == null) return null
  if (p < 30) return 'pct-red'
  if (p < 50) return 'pct-orange'
  if (p < 80) return 'pct-yellow'
  return 'pct-green'
})
</script>

<template>
  <div
    class="kpi-tile"
    :class="pctClass || accent || 'neutral'"
    v-tooltip.bottom="hint ? { value: hint, showDelay: 200 } : undefined"
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
}
.kpi-tile.primary { border-left-color: #6366f1; }
.kpi-tile.danger  { border-left-color: #ef4444; }
.kpi-tile.warn    { border-left-color: #f59e0b; }
.kpi-tile.success { border-left-color: #22c55e; }

/* Окрас по проценту (R3) — заливка + левая граница */
.kpi-tile.pct-red    { border-left-color: #ef4444; background: #fef2f2; }
.kpi-tile.pct-orange { border-left-color: #f97316; background: #fff7ed; }
.kpi-tile.pct-yellow { border-left-color: #eab308; background: #fefce8; }
.kpi-tile.pct-green  { border-left-color: #22c55e; background: #f0fdf4; }

.kpi-label {
  font-size: 0.72rem; color: #64748b;
  text-transform: uppercase; letter-spacing: 0.04em;
  display: flex; align-items: center; gap: 0.3rem;
}
.kpi-info {
  font-size: 0.8rem; color: #94a3b8; cursor: help;
}
.kpi-value {
  font-size: 1.5rem; font-weight: 700; color: #1e293b;
  letter-spacing: -0.02em;
}
.kpi-sub { font-size: 0.78rem; color: #64748b; margin-top: auto; }
</style>
