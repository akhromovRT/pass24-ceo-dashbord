<script setup lang="ts">
defineProps<{
  label: string
  value: string
  sub?: string
  accent?: 'primary' | 'danger' | 'warn' | 'success' | 'neutral'
}>()
</script>

<template>
  <div class="kpi-tile" :class="accent || 'neutral'">
    <div class="kpi-label">{{ label }}</div>
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
.kpi-label {
  font-size: 0.72rem; color: #64748b;
  text-transform: uppercase; letter-spacing: 0.04em;
}
.kpi-value {
  font-size: 1.5rem; font-weight: 700; color: #1e293b;
  letter-spacing: -0.02em;
}
.kpi-sub { font-size: 0.78rem; color: #64748b; margin-top: auto; }
</style>
