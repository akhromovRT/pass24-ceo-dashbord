<script setup lang="ts">
defineProps<{
  title: string
  value: string | number
  subtitle?: string
  icon?: string
  color?: string
}>()
</script>

<template>
  <div class="widget" :style="{ borderLeftColor: color || '#6366f1' }">
    <div class="widget-header">
      <i v-if="icon" :class="icon" class="widget-icon" :style="{ color: color || '#6366f1' }" />
      <span class="widget-title">{{ title }}</span>
    </div>
    <div class="widget-value">{{ value }}</div>
    <div v-if="subtitle" class="widget-subtitle">{{ subtitle }}</div>
  </div>
</template>

<style scoped>
.widget {
  background: white;
  border-radius: 8px;
  padding: 1.25rem;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
  border-left: 4px solid;
}

.widget-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}

.widget-icon {
  font-size: 1.25rem;
}

.widget-title {
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #64748b;
  font-weight: 600;
}

.widget-value {
  font-size: 1.75rem;
  font-weight: 700;
  color: #1e293b;
}

.widget-subtitle {
  font-size: 0.8rem;
  color: #94a3b8;
  margin-top: 0.25rem;
}
</style>
