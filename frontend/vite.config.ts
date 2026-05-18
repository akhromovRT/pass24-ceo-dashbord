import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Дробление вендорных бандлов. Канал VPS обрывает крупные HTTP-ответы —
// поэтому вендор режется на отдельные чанки. ВАЖНО: echarts и zrender
// взаимозависимы внутри — их нельзя резать по под-модулям (ломается порядок
// инициализации), каждый идёт ОДНИМ чанком. PrimeVue-компоненты независимы —
// их дробим по компонентам.
function manualChunks(id: string): string | undefined {
  if (!id.includes('node_modules/')) return
  const p = id.split('node_modules/')[1]
  // echarts и zrender взаимозависимы внутри — дробить нельзя (ломается
  // порядок инициализации классов), каждый идёт ОДНИМ чанком.
  if (p.startsWith('echarts/')) return 'echarts'
  if (p.startsWith('zrender/')) return 'zrender'
  if (
    p === 'vue' || p.startsWith('vue/') || p.startsWith('@vue/') ||
    p.startsWith('vue-router/') || p.startsWith('pinia/') ||
    p.startsWith('vue-echarts/') || p.startsWith('@vueuse/')
  ) {
    return 'vue'
  }
  if (
    p.startsWith('primevue/') || p.startsWith('@primevue/') ||
    p.startsWith('@primeuix/')
  ) {
    const parts = p.split('/')
    const seg = p.startsWith('@') ? parts[2] : parts[1]
    return 'pv-' + (seg || 'core').replace(/\.js$/, '')
  }
  return undefined
}

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: { manualChunks },
    },
  },
})
