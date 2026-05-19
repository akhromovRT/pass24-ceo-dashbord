<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import FileUpload from 'primevue/fileupload'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Tag from 'primevue/tag'
import Message from 'primevue/message'
import Select from 'primevue/select'
import DatePicker from 'primevue/datepicker'
import Button from 'primevue/button'
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
    hint: 'Полная история платежей из 1С — источник для AR-леджера.',
  },
]

type Phase = 'idle' | 'review' | 'done'

const runs = ref<any[]>([])
const uploadResult = ref<any>(null)
const uploadError = ref('')
const loading = ref(false)
const committing = ref(false)
const sourceType = ref<'debt' | 'bank' | 'registry' | 'payments'>('debt')

const phase = ref<Phase>('idle')
const previewData = ref<any>(null)
const selectedFile = ref<File | null>(null)
// overrides[paymentIndex] = Date выбранная в DatePicker (mode=month)
const overrides = ref<Record<number, Date | null>>({})

const isPreviewSource = computed(
  () => sourceType.value === 'bank' || sourceType.value === 'payments'
)

async function loadRuns() {
  const res = await api.get('/import/runs')
  runs.value = res.data
}

onMounted(loadRuns)

async function onUpload(event: any) {
  uploadResult.value = null
  uploadError.value = ''
  loading.value = true
  const file: File = event.files[0]
  if (isPreviewSource.value) {
    await doPreview(file)
  } else {
    await doDirectUpload(file)
  }
  loading.value = false
}

async function doDirectUpload(file: File) {
  const formData = new FormData()
  formData.append('file', file)
  try {
    const res = await api.post(`/import/upload?source_type=${sourceType.value}`, formData)
    uploadResult.value = res.data
    phase.value = 'done'
    await loadRuns()
  } catch (e: any) {
    uploadError.value = e.response?.data?.detail || 'Ошибка загрузки'
  }
}

async function doPreview(file: File) {
  selectedFile.value = file
  overrides.value = {}
  const formData = new FormData()
  formData.append('file', file)
  try {
    const res = await api.post(`/import/preview?source_type=${sourceType.value}`, formData)
    previewData.value = res.data
    if (res.data.summary.without_period === 0) {
      await doCommit()
    } else {
      phase.value = 'review'
    }
  } catch (e: any) {
    uploadError.value = e.response?.data?.detail || 'Ошибка при анализе файла'
  }
}

async function doCommit() {
  if (!selectedFile.value || !previewData.value || committing.value) return
  committing.value = true
  loading.value = true
  uploadError.value = ''

  const overridesObj: Record<string, { year: number; month: number }> = {}
  for (const [idxStr, dateVal] of Object.entries(overrides.value)) {
    if (dateVal) {
      overridesObj[idxStr] = {
        year: (dateVal as Date).getFullYear(),
        month: (dateVal as Date).getMonth() + 1,
      }
    }
  }

  const formData = new FormData()
  formData.append('file', selectedFile.value)
  formData.append('file_hash', previewData.value.file_hash)
  formData.append('period_overrides_json', JSON.stringify(overridesObj))

  try {
    const res = await api.post(`/import/commit?source_type=${sourceType.value}`, formData)
    uploadResult.value = res.data
    phase.value = 'done'
    await loadRuns()
  } catch (e: any) {
    uploadError.value = e.response?.data?.detail || 'Ошибка при импорте'
  } finally {
    loading.value = false
    committing.value = false
  }
}

function cancelReview() {
  phase.value = 'idle'
  previewData.value = null
  selectedFile.value = null
  overrides.value = {}
  uploadError.value = ''
}

function resetForm() {
  phase.value = 'idle'
  previewData.value = null
  selectedFile.value = null
  overrides.value = {}
  uploadResult.value = null
  uploadError.value = ''
}

function statusSeverity(status: string): 'success' | 'danger' | 'warn' | 'info' | undefined {
  switch (status) {
    case 'completed': return 'success'
    case 'failed': return 'danger'
    case 'processing': return 'warn'
    default: return 'info'
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

    <!-- Форма загрузки — скрыта на шаге ревью -->
    <div v-if="phase !== 'review'" class="upload-controls">
      <div class="control">
        <label>Тип файла</label>
        <Select
          v-model="sourceType"
          :options="SOURCE_TYPES"
          option-label="label"
          option-value="value"
          style="width: 360px"
          @change="resetForm"
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
          :disabled="loading"
        />
        <div v-if="loading" class="hint">Анализируем файл…</div>
      </div>
    </div>

    <Message v-if="uploadError" severity="error" :closable="true" @close="uploadError = ''">
      {{ uploadError }}
    </Message>

    <!-- Результат успешного импорта -->
    <div v-if="uploadResult && phase === 'done'" class="upload-result">
      <Message severity="success" :closable="false">
        Импорт завершён: {{ uploadResult.buyers_count }} организаций,
        {{ uploadResult.contracts_count }} контрактов,
        {{ uploadResult.documents_count }} документов.
        Новых: {{ uploadResult.new_buyers || 0 }}.
      </Message>
      <Button label="Загрузить ещё файл" severity="secondary" @click="resetForm" class="mt-2" />
    </div>

    <!-- Шаг ревью: платежи без периода -->
    <div v-if="phase === 'review' && previewData" class="review-block">
      <div class="review-header">
        <h2>Укажите период для {{ previewData.summary.without_period }} платежей</h2>
        <p class="review-hint">
          Комбобоксы можно оставить пустыми — такие платежи импортируются без периода, как раньше.
        </p>
      </div>

      <DataTable :value="previewData.payments" class="review-table" stripedRows>
        <Column field="date" header="Дата" style="width: 110px" />
        <Column field="counterparty" header="Контрагент">
          <template #body="{ data }">{{ (data.counterparty as string).slice(0, 45) }}</template>
        </Column>
        <Column field="amount" header="Сумма" style="width: 120px">
          <template #body="{ data }">
            {{ (data.amount as number).toLocaleString('ru-RU') }} ₽
          </template>
        </Column>
        <Column field="description" header="Назначение">
          <template #body="{ data }">
            <span class="description-cell">{{ data.description }}</span>
          </template>
        </Column>
        <Column header="Период" style="width: 165px">
          <template #body="{ data }">
            <DatePicker
              v-model="overrides[data.index]"
              view="month"
              dateFormat="mm/yy"
              placeholder="мм/гг"
              :showIcon="false"
              :minDate="new Date(2010, 0, 1)"
              :maxDate="new Date(2035, 11, 31)"
              style="width: 145px"
            />
          </template>
        </Column>
      </DataTable>

      <div class="review-actions">
        <Button
          label="Подтвердить импорт"
          @click="doCommit"
          :loading="loading"
        />
        <Button
          label="Отмена"
          severity="secondary"
          @click="cancelReview"
          :disabled="loading"
        />
      </div>
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
.import-view { padding: 1.5rem; }
.import-view h1 { font-size: 1.5rem; color: #1e293b; margin: 0 0 1.5rem; }
.import-view h2 { font-size: 1.1rem; color: #1e293b; margin: 0 0 0.25rem; }
.import-view h3 { font-size: 1rem; color: #374151; margin: 1.5rem 0 0.75rem; }

.upload-controls {
  display: flex; gap: 1.5rem; align-items: flex-start;
  margin-bottom: 1rem; padding: 1rem;
  background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px;
  flex-wrap: wrap;
}
.control { display: flex; flex-direction: column; gap: 0.25rem; }
.control label {
  font-size: 0.75rem; color: #64748b;
  text-transform: uppercase; letter-spacing: 0.04em;
}
.hint { font-size: 0.8rem; color: #64748b; margin-top: 0.25rem; max-width: 360px; }
.upload-result { margin-bottom: 1rem; }

.review-block {
  margin-bottom: 1.5rem; border: 1px solid #e2e8f0;
  border-radius: 8px; padding: 1.25rem; background: #fffbeb;
}
.review-header { margin-bottom: 1rem; }
.review-hint { font-size: 0.85rem; color: #64748b; margin: 0; }
.review-table { margin-bottom: 1rem; }
.description-cell {
  font-size: 0.8rem; color: #475569;
  display: -webkit-box; -webkit-line-clamp: 2;
  -webkit-box-orient: vertical; overflow: hidden;
}
.review-actions { display: flex; gap: 0.75rem; }
.mt-2 { margin-top: 0.5rem; }
</style>
