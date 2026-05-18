<script setup lang="ts">
import { onMounted, ref } from 'vue'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import DatePicker from 'primevue/datepicker'
import InputNumber from 'primevue/inputnumber'
import Button from 'primevue/button'
import { useToast } from 'primevue/usetoast'
import api from '../api/client'

const props = defineProps<{ inn: string }>()
const emit = defineEmits<{ changed: [] }>()
const toast = useToast()

const tariffs = ref<any[]>([])
const validFrom = ref<Date | null>(null)
const amount = ref<number | null>(null)
const saving = ref(false)

async function load() {
  const r = await api.get(`/organizations/${props.inn}/tariffs`)
  tariffs.value = r.data
}
onMounted(load)

async function add() {
  if (!validFrom.value || amount.value == null) return
  saving.value = true
  try {
    await api.post(`/organizations/${props.inn}/tariffs`, {
      valid_from: validFrom.value.toISOString().slice(0, 10),
      monthly_amount: amount.value,
    })
    validFrom.value = null
    amount.value = null
    await load()
    emit('changed')
    toast.add({ severity: 'success', summary: 'Тариф добавлен', life: 2500 })
  } catch {
    toast.add({ severity: 'error', summary: 'Не удалось добавить тариф', life: 4000 })
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
  <div class="tariff-history">
    <DataTable :value="tariffs" stripedRows>
      <template #empty>История тарифа пуста.</template>
      <Column field="valid_from" header="Действует с" />
      <Column field="monthly_amount" header="АП / мес">
        <template #body="{ data }">{{ fmtRub(data.monthly_amount) }}</template>
      </Column>
    </DataTable>
    <div class="add-row">
      <DatePicker v-model="validFrom" dateFormat="dd.mm.yy" showIcon
        placeholder="Действует с" />
      <InputNumber v-model="amount" :min="0" mode="currency" currency="RUB"
        locale="ru-RU" placeholder="АП / мес" />
      <Button label="Добавить тариф" icon="pi pi-plus" size="small"
        :loading="saving" :disabled="!validFrom || amount == null" @click="add" />
    </div>
  </div>
</template>

<style scoped>
.tariff-history {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.add-row {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  flex-wrap: wrap;
}
</style>
