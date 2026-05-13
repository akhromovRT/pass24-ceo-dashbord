<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import api from '../api/client'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import InputText from 'primevue/inputtext'
import Button from 'primevue/button'
import Select from 'primevue/select'
import Dialog from 'primevue/dialog'
import Tag from 'primevue/tag'
import Message from 'primevue/message'

interface User {
  id: string
  name: string
  email: string
  role: string
  is_active: boolean
  created_at: string
}

const users = ref<User[]>([])
const loading = ref(false)
const errorMsg = ref('')

const createOpen = ref(false)
const newName = ref('')
const newEmail = ref('')
const newRole = ref('viewer')
const roleOptions = [
  { label: 'Администратор', value: 'admin' },
  { label: 'Менеджер', value: 'manager' },
  { label: 'Просмотр', value: 'viewer' },
]
const createResult = ref<{ email: string; password: string } | null>(null)
const createResultOpen = computed({
  get: () => createResult.value !== null,
  set: (v: boolean) => {
    if (!v) createResult.value = null
  },
})

const resetResult = ref<{ email: string; password: string } | null>(null)
const resetResultOpen = computed({
  get: () => resetResult.value !== null,
  set: (v: boolean) => {
    if (!v) resetResult.value = null
  },
})

async function load() {
  loading.value = true
  errorMsg.value = ''
  try {
    const r = await api.get('/users')
    users.value = r.data
  } catch (e: any) {
    errorMsg.value = e.response?.data?.detail || 'Не удалось загрузить пользователей'
  } finally {
    loading.value = false
  }
}

async function submitCreate() {
  errorMsg.value = ''
  try {
    const r = await api.post('/users', {
      name: newName.value,
      email: newEmail.value,
      role: newRole.value,
    })
    createResult.value = { email: r.data.email, password: r.data.generated_password }
    newName.value = ''
    newEmail.value = ''
    newRole.value = 'viewer'
    createOpen.value = false
    await load()
  } catch (e: any) {
    errorMsg.value = e.response?.data?.detail || 'Ошибка создания'
  }
}

async function reset(u: User) {
  if (!confirm(`Сбросить пароль для ${u.email}? Будет сгенерирован новый, покажу его один раз.`)) return
  try {
    const r = await api.post(`/users/${u.id}/reset-password`)
    resetResult.value = { email: r.data.email, password: r.data.new_password }
  } catch (e: any) {
    errorMsg.value = e.response?.data?.detail || 'Ошибка сброса'
  }
}

function roleSeverity(role: string) {
  if (role === 'admin') return 'danger'
  if (role === 'manager') return 'warn'
  return 'info'
}

onMounted(load)
</script>

<template>
  <div class="users-view">
    <div class="header">
      <h1>Пользователи</h1>
      <Button label="Создать" icon="pi pi-plus" @click="createOpen = true" />
    </div>

    <Message v-if="errorMsg" severity="error" :closable="true" @close="errorMsg = ''">{{ errorMsg }}</Message>

    <DataTable :value="users" :loading="loading" striped-rows>
      <Column field="email" header="Email" />
      <Column field="name" header="Имя" />
      <Column header="Роль">
        <template #body="{ data }">
          <Tag :value="data.role" :severity="roleSeverity(data.role)" />
        </template>
      </Column>
      <Column header="Статус">
        <template #body="{ data }">
          <Tag :value="data.is_active ? 'активен' : 'выключен'" :severity="data.is_active ? 'success' : 'secondary'" />
        </template>
      </Column>
      <Column field="created_at" header="Создан">
        <template #body="{ data }">
          {{ data.created_at ? new Date(data.created_at).toLocaleDateString('ru-RU') : '' }}
        </template>
      </Column>
      <Column header="">
        <template #body="{ data }">
          <Button label="Сбросить пароль" size="small" outlined @click="reset(data)" />
        </template>
      </Column>
    </DataTable>

    <Dialog v-model:visible="createOpen" header="Создать пользователя" modal :style="{ width: '420px' }">
      <div class="form">
        <div class="field">
          <label>Имя</label>
          <InputText v-model="newName" />
        </div>
        <div class="field">
          <label>Email</label>
          <InputText v-model="newEmail" />
        </div>
        <div class="field">
          <label>Роль</label>
          <Select v-model="newRole" :options="roleOptions" option-label="label" option-value="value" />
        </div>
        <Button label="Создать" @click="submitCreate" />
      </div>
    </Dialog>

    <Dialog v-model:visible="createResultOpen" header="Пользователь создан" modal :style="{ width: '460px' }" :closable="true">
      <div class="result-block" v-if="createResult">
        <p>Email: <b>{{ createResult.email }}</b></p>
        <p>Сгенерированный пароль (покажу один раз — сохраните):</p>
        <pre class="pw">{{ createResult.password }}</pre>
        <p class="hint">Пользователь сможет сменить пароль в разделе Профиль.</p>
      </div>
    </Dialog>

    <Dialog v-model:visible="resetResultOpen" header="Пароль сброшен" modal :style="{ width: '460px' }" :closable="true">
      <div class="result-block" v-if="resetResult">
        <p>Email: <b>{{ resetResult.email }}</b></p>
        <p>Новый пароль:</p>
        <pre class="pw">{{ resetResult.password }}</pre>
      </div>
    </Dialog>
  </div>
</template>

<style scoped>
.users-view {
  padding: 1.5rem;
}
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}
.form {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.field label {
  font-size: 0.875rem;
  color: #475569;
}
.result-block .pw {
  background: #f1f5f9;
  padding: 0.75rem;
  border-radius: 6px;
  font-family: 'SF Mono', 'Monaco', monospace;
  font-size: 1rem;
  user-select: all;
}
.hint {
  color: #64748b;
  font-size: 0.875rem;
}
</style>
