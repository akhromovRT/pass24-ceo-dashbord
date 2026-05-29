<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import Toast from 'primevue/toast'
import ConfirmDialog from 'primevue/confirmdialog'
import AppLayout from './components/AppLayout.vue'

const route = useRoute()
const showLayout = computed(() => route.name !== 'login')
</script>

<template>
  <Toast />
  <ConfirmDialog />
  <AppLayout v-if="showLayout">
    <router-view />
  </AppLayout>
  <router-view v-else />
</template>
