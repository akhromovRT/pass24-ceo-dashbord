<script setup lang="ts">
import { onMounted, ref } from 'vue'
import FileUpload from 'primevue/fileupload'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Tag from 'primevue/tag'
import Message from 'primevue/message'
import Select from 'primevue/select'
import api from '../api/client'

const SOURCE_TYPES = [
  {
    value: 'debt',
    label: 'Задолженность покупателей (1С)',
    hint: 'Полный отчёт из 1С: организации, договоры, реализации, оплаты, остатки.',
  },
  {
    value: 'bank',
    label: 'Банковская выписка',
    hint: 'Платежи как Document(type=PAYMENT). Новые ИНН → PROSPECT-карточки.',
  },
  {
    value: 'registry',
    label: 'Клиентская база (реестр)',
    hint: 'Проставляет «В реестре = Да», переносит договор/доп.документ/объекты.',
  },
  {
    value: 'payments',
    label: 'Оплата от покупателей (1С)',
    hint: 'Полная история платежей из 1С — источник для AR-леджера. Платежи разносятся по месячным начислениям.',
  },
]

const runs = ref<any[]>([])
const uploadResult = ref<any>(null)
const uploadError = ref('')
const loading = ref(false)
const sourceType = ref<'debt' | 'bank' | 'registry' | 'payments'>('debt')

async function loadRuns() {
  const res = await api.get('/import/runs')
  runs.value = res.data
}

onMounted(loadRuns)

async function onUpload(event: any) {
  uploadResult.value = null
  uploadError.value = ''
  loading.value = true

  const file = event.files[0]
  const formData = new FormData()
  formData.append('file', file)

  try {
    const res = await api.post(`/import/upload?source_type=${sourceType.value}`, formData)
    uploadResult.value = res.data
    await loadRuns()
  } catch (e: any) {
    uploadError.value = e.response?.data?.detail || 'Ошибка загрузки'
  } finally {
    loading.value = false
  }
}

function statusSeverity(status: string): 'success' | 'danger' | 'warn' | 'info' | undefined {
  switch (status) {
    case 'completed': return 'success'
    case 'failed':    return 'danger'
    case 'processing':return 'warn'
    default:          return 'info'
  }
}

function formatDate(dt: string) {
  if (!dt) return '—'
  return new Date(dt).toLocaleString('ru-RU')
}

function sourceFromRun(run: any): string {
  const ds = run?.delta_summary
  if (ds?.source === 'bank_statement') return 'Банк'
  if (ds?.source === 'registry') return 'Реестр'
  if (ds?.source === 'payments_report') return 'Оплаты'
  return '1С (задолженность)'
}

function sourceSeverity(label: string): 'info' | 'success' | 'warn' {
  if (label === 'Банк') return 'success'
  if (label === 'Реестр') return 'warn'
  return 'info'
}
</script>

<template>
  <div class="import-view">
    <h1>Импорт данных</h1>

    <div class="upload-controls">
      <div class="control">
        <label>Тип файла</label>
        <Select
          v-model="sourceType"
          :options="SOURCE_TYPES"
          option-label="label"
          option-value="value"
          style="width: 360px"
        />
        <div class="hint">
          {{ SOURCE_TYPES.find(s => s.value === sourceType)?.hint }}
        </div>
      </div>

      <div class="control">
        <label>Файл</label>
        <FileUpload
          mode="basic"
          accept=".xls,.xlsx"
          :maxFileSize="10000000"
          chooseLabel="Выбрать .xls / .xlsx"
          :auto="true"
          customUpload
          @uploader="onUpload"
        />
      </div>
    </div>

    <Message v-if="uploadError" severity="error" :closable="true" @close="uploadError = ''">
      {{ uploadError }}
    </Message>

    <div v-if="uploadResult" class="upload-result">
      <Message severity="success" :closable="false">
        Импорт завершён: {{ uploadResult.buyers_count }} организаций,
        {{ uploadResult.contracts_count }} контрактов,
        {{ uploadResult.documents_count }} документов.
        Новых: {{ uploadResult.new_buyers || 0 }}.
      </Message>
    </div>

    <h3>История импортов</h3>
    <DataTable :value="runs" stripedRows>
      <Column field="filename" header="Файл" />
      <Column header="Источник" style="width: 130px">
        <template #body="{ data }">
          <Tag :severity="sourceSeverity(sourceFromRun(data))">{{ sourceFromRun(data) }}</Tag>
        </template>
      </Column>
      <Column header="Период">
        <template #body="{ data }">
          {{ data.period_start || '—' }} — {{ data.period_end || '—' }}
        </template>
      </Column>
      <Column field="status" header="Статус" style="width: 120px">
        <template #body="{ data }">
          <Tag :severity="statusSeverity(data.status)">{{ data.status }}</Tag>
        </template>
      </Column>
      <Column field="buyers_count" header="Организации" style="width: 120px" />
      <Column field="contracts_count" header="Договоры" style="width: 110px" />
      <Column field="documents_count" header="Документы" style="width: 110px" />
      <Column field="new_buyers" header="Новых" style="width: 90px" />
      <Column header="Дата" style="width: 180px">
        <template #body="{ data }">{{ formatDate(data.started_at) }}</template>
      </Column>
    </DataTable>
  </div>
</template>

<style scoped>
.import-view {
  padding: 1.5rem;
}

.import-view h1 {
  font-size: 1.5rem;
  color: #1e293b;
  margin: 0 0 1.5rem;
}

.import-view h3 {
  font-size: 1rem;
  color: #374151;
  margin: 1.5rem 0 0.75rem;
}

.upload-controls {
  display: flex;
  gap: 1.5rem;
  align-items: flex-start;
  margin-bottom: 1rem;
  padding: 1rem;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  flex-wrap: wrap;
}

.control {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.control label {
  font-size: 0.75rem;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.hint {
  font-size: 0.8rem;
  color: #64748b;
  margin-top: 0.25rem;
  max-width: 360px;
}

.upload-result {
  margin-bottom: 1rem;
}
</style>
