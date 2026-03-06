import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '../api/client'

interface Organization {
  id: string
  inn: string
  name_1c: string
  name_display: string | null
  org_type: string | null
  status: string
  monthly_ap: number | null
  total_debt: number | null
  payment_score: number | null
  objects: number | null
  city_region: string | null
}

export const useOrganizationsStore = defineStore('organizations', () => {
  const items = ref<Organization[]>([])
  const total = ref(0)
  const loading = ref(false)

  async function fetch(params: {
    search?: string
    status?: string
    manager_id?: string
    page?: number
    page_size?: number
  } = {}) {
    loading.value = true
    try {
      const response = await api.get('/organizations', { params })
      items.value = response.data.items
      total.value = response.data.total
    } finally {
      loading.value = false
    }
  }

  return { items, total, loading, fetch }
})
