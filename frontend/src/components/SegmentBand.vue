<script setup lang="ts">
interface Metric { label: string; value: string }
interface Segment { key: string; label: string; count?: number }

defineProps<{
  metrics: Metric[]
  segments: Segment[]
  modelValue: string
}>()
defineEmits<{ 'update:modelValue': [value: string] }>()
</script>

<template>
  <div class="segment-band">
    <div class="metrics">
      <div class="metric" v-for="m in metrics" :key="m.label">
        <span class="m-value">{{ m.value }}</span>
        <span class="m-label">{{ m.label }}</span>
      </div>
    </div>
    <div class="segments">
      <button
        v-for="s in segments"
        :key="s.key"
        class="seg-btn"
        :class="{ active: modelValue === s.key }"
        @click="$emit('update:modelValue', s.key)"
      >
        {{ s.label }}
        <span class="seg-count" v-if="s.count != null">{{ s.count }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.segment-band {
  background: #fff; border: 1px solid #e2e8f0; border-radius: 8px;
  padding: 1rem 1.25rem; display: flex; flex-direction: column; gap: 0.85rem;
}
.metrics { display: flex; flex-wrap: wrap; gap: 1.75rem; }
.metric { display: flex; flex-direction: column; }
.m-value { font-size: 1.25rem; font-weight: 700; color: #1e293b; }
.m-label { font-size: 0.72rem; color: #64748b; text-transform: uppercase;
  letter-spacing: 0.04em; }
.segments { display: flex; flex-wrap: wrap; gap: 0.5rem; }
.seg-btn {
  border: 1px solid #cbd5e1; background: #f8fafc; border-radius: 6px;
  padding: 0.35rem 0.8rem; font-size: 0.85rem; cursor: pointer;
  color: #475569; display: inline-flex; align-items: center; gap: 0.4rem;
}
.seg-btn:hover { background: #f1f5f9; }
.seg-btn.active { background: #6366f1; border-color: #6366f1; color: #fff; }
.seg-count {
  background: rgba(0,0,0,0.08); border-radius: 10px;
  padding: 0 0.4rem; font-size: 0.75rem; font-weight: 600;
}
.seg-btn.active .seg-count { background: rgba(255,255,255,0.25); }
</style>
