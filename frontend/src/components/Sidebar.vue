<script setup lang="ts">
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const navItems = [
  { label: 'Dashboard', icon: 'pi pi-chart-bar', route: '/' },
  { label: 'Биллинг', icon: 'pi pi-list', route: '/billing' },
  { label: 'Должники', icon: 'pi pi-exclamation-triangle', route: '/debtors' },
  { label: 'Импорт', icon: 'pi pi-upload', route: '/import' },
]

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
</style>
