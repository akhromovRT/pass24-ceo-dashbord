import { createApp } from 'vue'
import { createPinia } from 'pinia'
import piniaPluginPersistedstate from 'pinia-plugin-persistedstate'
import PrimeVue from 'primevue/config'
import ToastService from 'primevue/toastservice'
import ConfirmationService from 'primevue/confirmationservice'
import Tooltip from 'primevue/tooltip'
import Aura from '@primevue/themes/aura'
import 'primeicons/primeicons.css'

import App from './App.vue'
import router from './router'
import './style.css'

// --- Авто-повтор загрузки чанков -------------------------------------------
// Канал VPS перемежающе обрывает HTTP-ответы. При обрыве динамически
// импортируемого чанка перезагружаем страницу: HTTP-кэш браузера сохраняет
// уже успешно загруженные чанки, докачиваются только оборванные — процесс
// сходится за 1-3 перезагрузки. Счётчик в sessionStorage защищает от цикла.
const RELOAD_KEY = 'ceo24ChunkReloads'

function reloadOnChunkError(): void {
  const n = Number(sessionStorage.getItem(RELOAD_KEY) || '0')
  if (n >= 8) return
  sessionStorage.setItem(RELOAD_KEY, String(n + 1))
  location.reload()
}

window.addEventListener('vite:preloadError', ((event: Event) => {
  event.preventDefault()
  reloadOnChunkError()
}) as EventListener)

window.addEventListener('unhandledrejection', (event: PromiseRejectionEvent) => {
  const reason = event.reason
  const msg = String((reason && reason.message) || reason || '')
  if (/dynamically imported module|module script failed|Failed to fetch/i.test(msg)) {
    event.preventDefault()
    reloadOnChunkError()
  }
})

const pinia = createPinia()
pinia.use(piniaPluginPersistedstate)

const app = createApp(App)
app.use(pinia)
app.use(router)
app.use(PrimeVue, {
  theme: {
    preset: Aura,
  },
})
app.use(ToastService)
app.use(ConfirmationService)
app.directive('tooltip', Tooltip)
app.mount('#app')

// приложение смонтировано и начальный маршрут загружен — сбрасываем счётчик
router.isReady().then(() => {
  setTimeout(() => sessionStorage.removeItem(RELOAD_KEY), 2000)
})
