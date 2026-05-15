<script setup lang="ts">
import { useRouter } from 'vue-router'

interface AttentionItem {
  type: string; label: string; route: string
  count: number; amount: number; weight: number
}
defineProps<{ items: AttentionItem[] }>()
const router = useRouter()

function fmtRub(v: number) {
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency', currency: 'RUB', maximumFractionDigits: 0,
  }).format(v)
}
function dotClass(weight: number) {
  return weight >= 3 ? 'crit' : weight === 2 ? 'warn' : 'info'
}
</script>

<template>
  <div class="attention">
    <div class="att-title">Требуют внимания</div>
    <div v-if="!items.length" class="att-empty">Открытых алертов нет.</div>
    <button
      v-for="it in items.slice(0, 5)"
      :key="it.type"
      class="att-row"
      @click="router.push(it.route)"
    >
      <span class="dot" :class="dotClass(it.weight)" />
      <span class="att-label">{{ it.label }}</span>
      <span class="att-count">{{ it.count }}</span>
      <span class="att-amount" v-if="it.amount > 0">{{ fmtRub(it.amount) }}</span>
      <span class="att-arrow">&rarr;</span>
    </button>
  </div>
</template>

<style scoped>
.attention {
  background: #fff; border: 1px solid #e2e8f0; border-radius: 8px;
  padding: 1rem 1.25rem;
}
.att-title { font-size: 0.95rem; font-weight: 600; color: #1e293b;
  margin-bottom: 0.6rem; }
.att-empty { color: #64748b; font-size: 0.85rem; padding: 0.5rem 0; }
.att-row {
  width: 100%; display: flex; align-items: center; gap: 0.75rem;
  padding: 0.55rem 0.4rem; border: none; background: none;
  border-bottom: 1px solid #f1f5f9; cursor: pointer; font-size: 0.9rem;
  text-align: left;
}
.att-row:hover { background: #f8fafc; }
.att-row:last-child { border-bottom: none; }
.dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
.dot.crit { background: #ef4444; }
.dot.warn { background: #f59e0b; }
.dot.info { background: #64748b; }
.att-label { color: #1e293b; }
.att-count {
  background: #f1f5f9; border-radius: 10px; padding: 0 0.5rem;
  font-size: 0.8rem; font-weight: 600; color: #475569;
}
.att-amount { color: #64748b; font-size: 0.85rem; }
.att-arrow { margin-left: auto; color: #94a3b8; }
</style>
