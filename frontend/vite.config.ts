import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Дробление вендорных бандлов на мелкие чанки. Канал VPS обрывает крупные
// HTTP-ответы (>~120 КБ) — поэтому echarts/zrender/vue режутся по под-путям,
// чтобы каждый чанк (в gzip) был заведомо ниже порога обрыва.
function manualChunks(id: string): string | undefined {
  if (!id.includes('node_modules/')) return
  const p = id.split('node_modules/')[1]
  if (p.startsWith('echarts/')) {
    const parts = p.split('/')
    return 'echarts-' + (parts[2] || parts[1] || 'core').replace(/\.js$/, '')
  }
  if (p.startsWith('zrender/')) {
    const parts = p.split('/')
    return 'zrender-' + (parts[2] || parts[1] || 'core').replace(/\.js$/, '')
  }
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
