import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('./views/LoginView.vue'),
  },
  {
    path: '/',
    name: 'dashboard',
    component: () => import('./views/DashboardView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/billing',
    name: 'billing',
    component: () => import('./views/BillingView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/clients/:inn',
    name: 'client-card',
    component: () => import('./views/ClientCardView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/debtors',
    name: 'debtors',
    component: () => import('./views/DebtorsView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/import',
    name: 'import',
    component: () => import('./views/ImportView.vue'),
    meta: { requiresAuth: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const token = localStorage.getItem('token')
  if (to.meta.requiresAuth && !token) {
    return { name: 'login' }
  }
})

export default router
