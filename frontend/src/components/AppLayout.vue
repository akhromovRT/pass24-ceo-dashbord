<script setup lang="ts">
import Sidebar from './Sidebar.vue'
</script>

<template>
  <div class="app-layout">
    <Sidebar />
    <main class="main-content">
      <slot />
    </main>
  </div>
</template>

<style scoped>
.app-layout {
  display: flex;
  min-height: 100vh;
}

.main-content {
  flex: 1;
  /* min-width: 0 — без него flex-элемент расширяется под широкий контент
     (например таблицу) и страница получает горизонтальный скролл, из-за чего
     fixed-сайдбар наезжает на контент. С min-width:0 контент ограничен окном. */
  min-width: 0;
  margin-left: 220px;
  background: #f8f9fa;
  min-height: 100vh;
}
</style>
