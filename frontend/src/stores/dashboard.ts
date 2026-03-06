import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '../api/client'

interface Summary {
  mrr: number
  arr: number
  total_debt: number
  active_clients: number
  open_alerts: number
}

interface MrrPoint {
  year: number
  month: number
  sold_ap: number
  paid_ap: number
}

interface AgingBucket {
  bucket: string
  amount: number
  count: number
}

export const useDashboardStore = defineStore('dashboard', () => {
  const summary = ref<Summary | null>(null)
  const mrrTrend = ref<MrrPoint[]>([])
  const aging = ref<AgingBucket[]>([])
  const loading = ref(false)

  async function fetchAll() {
    loading.value = true
    try {
      const [s, m, a] = await Promise.all([
        api.get('/dashboard/summary'),
        api.get('/dashboard/mrr-trend'),
        api.get('/dashboard/aging'),
      ])
      summary.value = s.data
      mrrTrend.value = m.data
      aging.value = a.data
    } finally {
      loading.value = false
    }
  }

  return { summary, mrrTrend, aging, loading, fetchAll }
})
