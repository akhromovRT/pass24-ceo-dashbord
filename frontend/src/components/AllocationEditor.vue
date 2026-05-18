<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import Dialog from 'primevue/dialog'
import InputNumber from 'primevue/inputnumber'
import Button from 'primevue/button'
import { useToast } from 'primevue/usetoast'
import api from '../api/client'

interface Alloc { year: number | null; month: number | null; amount: number }
interface Payment { id: string; amount: number; allocations: Alloc[] }

const props = defineProps<{ payment: Payment | null; visible: boolean }>()
const emit = defineEmits<{ 'update:visible': [boolean]; saved: [] }>()
const toast = useToast()

const rows = ref<{ year: number; month: number; amount: number }[]>([])
const saving = ref(false)

watch(() => props.visible, (v) => {
  if (v && props.payment) {
    rows.value = props.payment.allocations
      .filter(a => a.year != null && a.month != null)
      .map(a => ({ year: a.year as number, month: a.month as number, amount: a.amount }))
    if (rows.value.length === 0) {
      const d = new Date()
      rows.value = [{
        year: d.getFullYear(), month: d.getMonth() + 1,
        amount: props.payment.amount,
      }]
    }
  }
})

const allocated = computed(() => rows.value.reduce((s, r) => s + (r.amount || 0), 0))
const diff = computed(() => (props.payment?.amount || 0) - allocated.value)

function addRow() {
  const d = new Date()
  rows.value.push({ year: d.getFullYear(), month: d.getMonth() + 1, amount: 0 })
}
function removeRow(i: number) {
  rows.value.splice(i, 1)
}

async function save() {
  if (!props.payment) return
  saving.value = true
  try {
    await api.put(`/payments/${props.payment.id}/allocations`, {
      allocations: rows.value.map(r => ({
        year: r.year, month: r.month, amount: r.amount,
      })),
    })
    emit('saved')
    emit('update:visible', false)
    toast.add({ severity: 'success', summary: 'Разнесение сохранено', life: 2500 })
  } catch {
    toast.add({ severity: 'error', summary: 'Не удалось сохранить', life: 4000 })
  } finally {
    saving.value = false
  }
}

function fmtRub(v: number) {
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency', currency: 'RUB', maximumFractionDigits: 0,
  }).format(v)
}
</script>

<template>
  <Dialog :visible="visible" @update:visible="emit('update:visible', $event)"
    modal header="Разнесение платежа" :style="{ width: '480px' }">
    <div v-if="payment" class="alloc-editor">
      <div class="pay-sum">Сумма платежа: <b>{{ fmtRub(payment.amount) }}</b></div>
      <div v-for="(r, i) in rows" :key="i" class="alloc-row">
        <InputNumber v-model="r.month" :min="1" :max="12" placeholder="Мес"
          :inputStyle="{ width: '64px' }" />
        <InputNumber v-model="r.year" :min="2017" :max="2030" :useGrouping="false"
          placeholder="Год" :inputStyle="{ width: '80px' }" />
        <InputNumber v-model="r.amount" :min="0" mode="currency" currency="RUB"
          locale="ru-RU" />
        <Button icon="pi pi-times" text severity="danger" @click="removeRow(i)" />
      </div>
      <Button label="Добавить строку" icon="pi pi-plus" text size="small" @click="addRow" />
      <div class="alloc-diff" :class="{ bad: Math.abs(diff) > 0.01 }">
        Разнесено: {{ fmtRub(allocated) }} · расхождение: {{ fmtRub(diff) }}
      </div>
    </div>
    <template #footer>
      <Button label="Отмена" text @click="emit('update:visible', false)" />
      <Button label="Сохранить" icon="pi pi-check" :loading="saving"
        :disabled="Math.abs(diff) > 0.01" @click="save" />
    </template>
  </Dialog>
</template>

<style scoped>
.alloc-editor {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}
.pay-sum { color: #475569; font-size: 0.9rem; }
.alloc-row {
  display: flex;
  gap: 0.4rem;
  align-items: center;
}
.alloc-diff { font-size: 0.85rem; color: #64748b; }
.alloc-diff.bad { color: #ef4444; font-weight: 600; }
</style>
