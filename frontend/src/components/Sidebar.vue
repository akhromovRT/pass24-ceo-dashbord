<script setup lang="ts">
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const navItems = computed(() => {
  const base = [
    { label: 'Dashboard', icon: 'pi pi-chart-bar', route: '/' },
    { label: 'Реестр клиентов', icon: 'pi pi-list', route: '/billing' },
    { label: 'Должники', icon: 'pi pi-exclamation-triangle', route: '/debtors' },
    { label: 'Отчёты', icon: 'pi pi-file-export', route: '/reports' },
    { label: 'Импорт', icon: 'pi pi-upload', route: '/import' },
  ]
  if (auth.isAdmin) {
    base.push({ label: 'Пользователи', icon: 'pi pi-users', route: '/users' })
  }
  return base
})

function navigate(path: string) {
  router.push(path)
}

function logout() {
  auth.logout()
  router.push('/login')
}

function isActive(path: string) {
  return route.path === path
}
</script>

<template>
  <aside class="sidebar">
    <div class="sidebar-brand" @click="navigate('/')">
      <span class="brand-text">CEO24</span>
    </div>

    <nav class="sidebar-nav">
      <a
        v-for="item in navItems"
        :key="item.route"
        class="nav-item"
        :class="{ active: isActive(item.route) }"
        @click="navigate(item.route)"
      >
        <i :class="item.icon" />
        <span>{{ item.label }}</span>
      </a>
    </nav>

    <div class="sidebar-footer">
      <div v-if="auth.user" class="user-block" @click="navigate('/profile')" :class="{ active: isActive('/profile') }">
        <i class="pi pi-user" />
        <div class="user-info">
          <div class="user-name">{{ auth.user.name }}</div>
          <div class="user-role">{{ auth.user.role }}</div>
        </div>
      </div>
      <a class="nav-item" @click="logout">
        <i class="pi pi-sign-out" />
        <span>Выход</span>
      </a>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 220px;
  background: #1e293b;
  color: white;
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  position: fixed;
  left: 0;
  top: 0;
}

.sidebar-brand {
  padding: 1.5rem 1.25rem;
  cursor: pointer;
}

.brand-text {
  font-size: 1.5rem;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: #818cf8;
}

.sidebar-nav {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 0 0.5rem;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  border-radius: 6px;
  cursor: pointer;
  color: #94a3b8;
  font-size: 0.875rem;
  transition: all 0.15s;
  text-decoration: none;
}

.nav-item:hover {
  background: #334155;
  color: white;
}

.nav-item.active {
  background: #6366f1;
  color: white;
}

.nav-item i {
  font-size: 1rem;
  width: 20px;
  text-align: center;
}

.sidebar-footer {
  padding: 0.5rem;
  border-top: 1px solid #334155;
}

.user-block {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  cursor: pointer;
  color: #cbd5e1;
  margin-bottom: 0.25rem;
}

.user-block:hover {
  background: #334155;
}

.user-block.active {
  background: #6366f1;
  color: white;
}

.user-info {
  display: flex;
  flex-direction: column;
  font-size: 0.8rem;
  overflow: hidden;
}

.user-name {
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.user-role {
  color: #94a3b8;
  font-size: 0.7rem;
}
</style>
