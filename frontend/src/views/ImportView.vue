<script setup lang="ts">
import { onMounted, ref } from 'vue'
import FileUpload from 'primevue/fileupload'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Tag from 'primevue/tag'
import Message from 'primevue/message'
import api from '../api/client'

const runs = ref<any[]>([])
const uploadResult = ref<any>(null)
const uploadError = ref('')
const loading = ref(false)

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
    const res = await api.post('/import/upload', formData)
    uploadResult.value = res.data
    await loadRuns()
  } catch (e: any) {
    uploadError.value = e.response?.data?.detail || 'Ошибка загрузки'
  } finally {
    loading.value = false
  }
}

function statusSeverity(status: string): "success" | "danger" | "warn" | "info" | undefined {
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
</script>

<template>
  <div class="import-view">
    <h1>Импорт данных</h1>

    <div class="upload-section">
      <FileUpload
        mode="basic"
        accept=".xls,.xlsx"
        :maxFileSize="10000000"
        chooseLabel="Выбрать файл XLS/XLSX"
        :auto="true"
        customUpload
        @uploader="onUpload"
      />
    </div>

    <Message v-if="uploadError" severity="error" :closable="true" @close="uploadError = ''">
      {{ uploadError }}
    </Message>

    <div v-if="uploadResult" class="upload-result">
      <Message severity="success" :closable="false">
        Импорт завершён: {{ uploadResult.buyers_count }} покупателей,
        {{ uploadResult.contracts_count }} контрактов,
        {{ uploadResult.documents_count }} документов.
        Новых: {{ uploadResult.new_buyers || 0 }}.
      </Message>
    </div>

    <h3>История импортов</h3>
    <DataTable :value="runs" stripedRows>
      <Column field="filename" header="Файл" />
      <Column header="Период">
        <template #body="{ data }">
          {{ data.period_start }} — {{ data.period_end }}
        </template>
      </Column>
      <Column field="status" header="Статус" style="width: 120px">
        <template #body="{ data }">
          <Tag :severity="statusSeverity(data.status)">{{ data.status }}</Tag>
        </template>
      </Column>
      <Column field="buyers_count" header="Покупатели" style="width: 120px" />
      <Column field="contracts_count" header="Договоры" style="width: 110px" />
      <Column field="documents_count" header="Документы" style="width: 110px" />
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

.upload-section {
  margin-bottom: 1rem;
}

.upload-result {
  margin-bottom: 1rem;
}
</style>
