import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '../api/client'

interface CurrentUser {
  id: string
  name: string
  email: string
  role: 'admin' | 'manager' | 'viewer'
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const user = ref<CurrentUser | null>(
    localStorage.getItem('user') ? JSON.parse(localStorage.getItem('user')!) : null,
  )

  const isAuthenticated = computed(() => !!token.value)
  const isAdmin = computed(() => user.value?.role === 'admin')

  async function login(email: string, password: string) {
    const formData = new URLSearchParams()
    formData.append('username', email)
    formData.append('password', password)

    const response = await api.post('/auth/login', formData, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
    token.value = response.data.access_token
    localStorage.setItem('token', token.value)
    await fetchMe()
  }

  async function fetchMe() {
    const r = await api.get('/auth/me')
    user.value = r.data
    localStorage.setItem('user', JSON.stringify(r.data))
  }

  async function changePassword(currentPassword: string, newPassword: string) {
    await api.post('/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    })
  }

  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('user')
  }

  return { token, user, isAuthenticated, isAdmin, login, logout, fetchMe, changePassword }
})
