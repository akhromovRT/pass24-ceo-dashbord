<script setup lang="ts">
import { ref } from 'vue'
import { useAuthStore } from '../stores/auth'
import Password from 'primevue/password'
import Button from 'primevue/button'
import Message from 'primevue/message'

const auth = useAuthStore()
const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const loading = ref(false)
const successMsg = ref('')
const errorMsg = ref('')

async function submit() {
  successMsg.value = ''
  errorMsg.value = ''
  if (newPassword.value.length < 8) {
    errorMsg.value = 'Новый пароль должен быть не короче 8 символов'
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    errorMsg.value = 'Подтверждение пароля не совпадает'
    return
  }
  loading.value = true
  try {
    await auth.changePassword(currentPassword.value, newPassword.value)
    successMsg.value = 'Пароль обновлён'
    currentPassword.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
  } catch (e: any) {
    errorMsg.value = e.response?.data?.detail || 'Не удалось сменить пароль'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="profile-view">
    <h1>Профиль</h1>

    <section class="card">
      <h2>Информация</h2>
      <div class="info-row"><b>Имя:</b> {{ auth.user?.name || '—' }}</div>
      <div class="info-row"><b>Email:</b> {{ auth.user?.email || '—' }}</div>
      <div class="info-row"><b>Роль:</b> {{ auth.user?.role || '—' }}</div>
    </section>

    <section class="card">
      <h2>Сменить пароль</h2>
      <form class="form" @submit.prevent="submit">
        <div class="field">
          <label>Текущий пароль</label>
          <Password v-model="currentPassword" :feedback="false" toggleMask required />
        </div>
        <div class="field">
          <label>Новый пароль</label>
          <Password v-model="newPassword" toggleMask required />
        </div>
        <div class="field">
          <label>Подтверждение</label>
          <Password v-model="confirmPassword" :feedback="false" toggleMask required />
        </div>

        <Message v-if="errorMsg" severity="error" :closable="false">{{ errorMsg }}</Message>
        <Message v-if="successMsg" severity="success" :closable="false">{{ successMsg }}</Message>

        <Button type="submit" label="Сменить пароль" :loading="loading" />
      </form>
    </section>
  </div>
</template>

<style scoped>
.profile-view {
  padding: 1.5rem;
  max-width: 720px;
}
.card {
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 1.25rem 1.5rem;
  margin-bottom: 1rem;
}
h2 {
  margin-top: 0;
  font-size: 1.1rem;
}
.info-row {
  padding: 0.25rem 0;
}
.form {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  max-width: 420px;
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
:deep(.p-password) {
  width: 100%;
}
:deep(.p-password-input) {
  width: 100%;
}
</style>
