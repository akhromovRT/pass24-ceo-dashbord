<script setup lang="ts">
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Tag from 'primevue/tag'

interface LedgerMonth {
  year: number
  month: number
  accrued: number
  allocated: number
  outstanding: number
  status: string
  source: string
}

defineProps<{ months: LedgerMonth[] }>()

function fmtRub(v: number | null) {
  if (v == null) return '—'
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency', currency: 'RUB', maximumFractionDigits: 0,
  }).format(v)
}

const STATUS: Record<string, { label: string; severity: string }> = {
  paid: { label: 'Оплачено', severity: 'success' },
  partial: { label: 'Частично', severity: 'warn' },
  unpaid: { label: 'Долг', severity: 'danger' },
}
</script>

<template>
  <DataTable :value="months" stripedRows paginator :rows="24" class="ledger-table">
    <template #empty>Начислений нет.</template>
    <Column header="Период" style="width: 110px">
      <template #body="{ data }">
        {{ String(data.month).padStart(2, '0') }}/{{ data.year }}
      </template>
    </Column>
    <Column field="accrued" header="Начислено">
      <template #body="{ data }">{{ fmtRub(data.accrued) }}</template>
    </Column>
    <Column field="allocated" header="Разнесено">
      <template #body="{ data }">{{ fmtRub(data.allocated) }}</template>
    </Column>
    <Column field="outstanding" header="Остаток">
      <template #body="{ data }">{{ fmtRub(data.outstanding) }}</template>
    </Column>
    <Column header="Статус" style="width: 130px">
      <template #body="{ data }">
        <Tag :severity="(STATUS[data.status] || {}).severity || 'secondary'">
          {{ (STATUS[data.status] || {}).label || data.status }}
        </Tag>
      </template>
    </Column>
  </DataTable>
</template>
