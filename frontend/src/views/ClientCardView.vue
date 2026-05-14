<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import Tabs from 'primevue/tabs'
import TabList from 'primevue/tablist'
import Tab from 'primevue/tab'
import TabPanels from 'primevue/tabpanels'
import TabPanel from 'primevue/tabpanel'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Tag from 'primevue/tag'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import api from '../api/client'

use([BarChart, LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const route = useRoute()
const inn = route.params.inn as string

const org = ref<any>(null)
const snapshots = ref<any[]>([])
const contracts = ref<any[]>([])
const objects = ref<any[]>([])
const loading = ref(true)

onMounted(async () => {
  try {
    const [orgRes, snapRes, contractRes, objRes] = await Promise.all([
      api.get(`/organizations/${inn}`),
      api.get(`/organizations/${inn}/snapshots`),
      api.get(`/organizations/${inn}/contracts`),
      api.get(`/organizations/${inn}/objects`),
    ])
    org.value = orgRes.data
    snapshots.value = snapRes.data
    contracts.value = contractRes.data
    objects.value = objRes.data
  } finally {
    loading.value = false
  }
})

function formatCurrency(value: number | null) {
  if (value == null) return '—'
  return new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }).format(value)
}

function ensureProtocol(url: string | null | undefined): string {
  if (!url) return ''
  const trimmed = url.trim()
  if (/^https?:\/\//i.test(trimmed)) return trimmed
  return 'https://' + trimmed
}

const barChartOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  legend: { data: ['Продано', 'Оплачено'] },
  xAxis: {
    type: 'category',
    data: snapshots.value.map(s => `${s.month}/${s.year}`),
  },
  yAxis: { type: 'value' },
  series: [
    { name: 'Продано', type: 'bar', data: snapshots.value.map(s => s.sold || 0), color: '#6366f1' },
    { name: 'Оплачено', type: 'bar', data: snapshots.value.map(s => s.paid || 0), color: '#22c55e' },
  ],
}))

const lineChartOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  xAxis: {
    type: 'category',
    data: snapshots.value.map(s => `${s.month}/${s.year}`),
  },
  yAxis: { type: 'value' },
  series: [
    { name: 'Долг', type: 'line', data: snapshots.value.map(s => s.debt_end || 0), color: '#ef4444', areaStyle: { opacity: 0.1 } },
  ],
}))
</script>

<template>
  <div class="client-card" v-if="!loading && org">
    <div class="card-header">
      <div>
        <h1>{{ org.name_display || org.name_1c }}</h1>
        <div class="card-meta">
          <span>ИНН: {{ org.inn }}</span>
          <Tag v-if="org.org_type" :value="org.org_type" severity="info" />
          <Tag :severity="org.status === 'active' ? 'success' : 'secondary'">
            {{ org.status }}
          </Tag>
          <Tag v-if="org.in_registry" severity="success" icon="pi pi-check">
            В реестре
          </Tag>
        </div>
        <div class="card-details" v-if="org.address">{{ org.address }}</div>
      </div>
      <div class="card-stats">
        <div class="stat">
          <span class="stat-label">АП/мес</span>
          <span class="stat-value">{{ formatCurrency(org.monthly_ap) }}</span>
        </div>
        <div class="stat">
          <span class="stat-label">Долг</span>
          <span class="stat-value debt">{{ formatCurrency(org.total_debt) }}</span>
        </div>
      </div>
    </div>

    <Tabs value="info">
      <TabList>
        <Tab value="info">Информация</Tab>
        <Tab value="registry">
          Реестр
          <Tag v-if="org.in_registry" severity="success" :pt="{ root: { style: 'margin-left: 6px; padding: 1px 6px; font-size: 0.7rem;' } }">Да</Tag>
        </Tab>
        <Tab value="contracts">Договоры</Tab>
        <Tab value="payments">История оплат</Tab>
        <Tab value="charts">Графики</Tab>
      </TabList>
      <TabPanels>
        <TabPanel value="info">
          <div class="info-grid">
            <div><strong>Объекты (число):</strong> {{ org.objects ?? org.objects_count_declared ?? '—' }}</div>
            <div><strong>Тип:</strong> {{ org.object_type ?? '—' }}</div>
            <div><strong>Оборудование:</strong> {{ org.equipment ?? '—' }}</div>
            <div><strong>Номер системы:</strong> {{ org.system_number ?? '—' }}</div>
            <div v-if="org.cloud_url"><strong>Облако:</strong> <a :href="ensureProtocol(org.cloud_url)" target="_blank">{{ org.cloud_url }}</a></div>
            <div><strong>Город:</strong> {{ org.city_region ?? '—' }}</div>
          </div>
        </TabPanel>

        <TabPanel value="registry">
          <div class="registry-tab">
            <div class="reg-status">
              <strong>Статус в реестре:</strong>
              <Tag v-if="org.in_registry" severity="success">Да</Tag>
              <Tag v-else severity="secondary">Нет</Tag>
            </div>

            <div class="reg-fields">
              <div class="field-block">
                <div class="field-label">Договор 1С</div>
                <div class="field-value">{{ org.contract_1c_raw || '—' }}</div>
              </div>

              <div class="field-block">
                <div class="field-label">Активный документ</div>
                <div class="field-value">{{ org.active_doc_raw || '—' }}</div>
              </div>

              <div class="field-block">
                <div class="field-label">Количество объектов (по реестру)</div>
                <div class="field-value">{{ org.objects_count_declared ?? '—' }}</div>
              </div>
            </div>

            <h3>Объекты ({{ objects.length }})</h3>
            <DataTable v-if="objects.length" :value="objects" stripedRows responsiveLayout="scroll">
              <Column field="name" header="Название" />
              <Column header="Ссылка на облако">
                <template #body="{ data }">
                  <a v-if="data.cloud_url" :href="ensureProtocol(data.cloud_url)" target="_blank">{{ data.cloud_url }}</a>
                  <span v-else>—</span>
                </template>
              </Column>
              <Column field="object_number" header="№ в облаке" />
              <Column field="object_type" header="Тип" />
              <Column field="address" header="Адрес" />
              <Column field="city_region" header="Город/область" />
            </DataTable>
            <div v-else class="empty-state">
              Объекты в реестре не указаны для этой организации.
            </div>
          </div>
        </TabPanel>

        <TabPanel value="contracts">
          <DataTable :value="contracts" stripedRows>
            <Column field="contract_number" header="Номер" />
            <Column field="contract_type" header="Тип">
              <template #body="{ data }">
                <Tag>{{ data.contract_type }}</Tag>
              </template>
            </Column>
            <Column field="monthly_amount" header="Сумма/мес">
              <template #body="{ data }">{{ formatCurrency(data.monthly_amount) }}</template>
            </Column>
            <Column field="status" header="Статус">
              <template #body="{ data }">
                <Tag :severity="data.status === 'active' ? 'success' : 'secondary'">{{ data.status }}</Tag>
              </template>
            </Column>
            <Column field="classification_source" header="Классификация" />
          </DataTable>
        </TabPanel>

        <TabPanel value="payments">
          <DataTable :value="snapshots" stripedRows>
            <Column header="Период">
              <template #body="{ data }">{{ data.month }}/{{ data.year }}</template>
            </Column>
            <Column field="plan_amount" header="План">
              <template #body="{ data }">{{ formatCurrency(data.plan_amount) }}</template>
            </Column>
            <Column field="sold" header="Продано">
              <template #body="{ data }">{{ formatCurrency(data.sold) }}</template>
            </Column>
            <Column field="paid" header="Оплачено">
              <template #body="{ data }">{{ formatCurrency(data.paid) }}</template>
            </Column>
            <Column field="debt_end" header="Долг">
              <template #body="{ data }">{{ formatCurrency(data.debt_end) }}</template>
            </Column>
            <Column field="collectability" header="Собираемость">
              <template #body="{ data }">{{ data.collectability != null ? data.collectability + '%' : '—' }}</template>
            </Column>
          </DataTable>
        </TabPanel>

        <TabPanel value="charts">
          <div class="charts-grid">
            <div class="chart-box">
              <h3>Продано vs Оплачено</h3>
              <v-chart :option="barChartOption" style="height: 300px" autoresize />
            </div>
            <div class="chart-box">
              <h3>Динамика долга</h3>
              <v-chart :option="lineChartOption" style="height: 300px" autoresize />
            </div>
          </div>
        </TabPanel>
      </TabPanels>
    </Tabs>
  </div>
  <div v-else-if="loading" class="loading">Загрузка...</div>
</template>

<style scoped>
.client-card {
  padding: 1.5rem;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 1.5rem;
}

.card-header h1 {
  margin: 0 0 0.5rem;
  font-size: 1.75rem;
  color: #1e293b;
}

.card-meta {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  color: #64748b;
  flex-wrap: wrap;
}

.card-details {
  margin-top: 0.5rem;
  color: #64748b;
  font-size: 0.875rem;
}

.card-stats {
  display: flex;
  gap: 2rem;
}

.stat {
  text-align: right;
}

.stat-label {
  display: block;
  font-size: 0.75rem;
  color: #64748b;
  text-transform: uppercase;
}

.stat-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: #1e293b;
}

.stat-value.debt {
  color: #ef4444;
}

.info-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}

.registry-tab {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.reg-status {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  font-size: 0.95rem;
}

.reg-fields {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0.75rem;
  padding: 1rem;
  background: #f8fafc;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
}

.field-block .field-label {
  font-size: 0.75rem;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 0.25rem;
}

.field-block .field-value {
  font-size: 0.95rem;
  color: #1e293b;
  white-space: pre-wrap;
}

.empty-state {
  padding: 1.5rem;
  text-align: center;
  color: #64748b;
  background: #f8fafc;
  border-radius: 6px;
  border: 1px dashed #e2e8f0;
}

.charts-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
}

.chart-box h3 {
  margin: 0 0 0.75rem;
  font-size: 1rem;
  color: #374151;
}

.loading {
  padding: 3rem;
  text-align: center;
  color: #64748b;
}

.registry-tab h3 {
  margin: 0.5rem 0;
  font-size: 1rem;
  color: #374151;
}
</style>
