<script setup>
import { computed } from 'vue'
import AppHeader from './layouts/AppHeader.vue'
import ProjectSidebar from './layouts/ProjectSidebar.vue'
import Pagination from './components/Pagination.vue'
import { usePageNavigation } from './composables/usePageNavigation.js'
import { getPage } from './pages.js'

const props = defineProps({ initial: Object })
const {
  state, data, page, path, busy, error, notices, content,
  navigate, submit, intercept,
} = usePageNavigation(props.initial)
const currentPage = computed(() => getPage(page.value))
</script>

<template>
  <div class="app-shell" @click="intercept">
    <AppHeader
      :user="state.user"
      :show-operations="state.show_operations"
      :busy="busy"
      :path="path"
      @logout="navigate('/logout/', {})"
    />
    <main ref="content" tabindex="-1" :aria-busy="busy" :class="{ 'project-workspace': data.project }">
      <ProjectSidebar v-if="data.project" :project="data.project" :page="page" />
      <div class="page-content">
        <div v-if="busy" class="loading" role="status">Загрузка…</div>
        <div
          v-for="(notice, index) in notices"
          :key="index"
          class="notice"
          :class="notice.level"
          role="status"
        >{{ notice.text }}</div>
        <div v-if="error" class="notice error" role="alert">{{ error }}</div>
        <component
          :is="currentPage.component"
          :key="page"
          :data="data"
          :user="state.user"
          :busy="busy"
          :options="currentPage"
          @submit="submit"
          @navigate="navigate"
        />
        <Pagination :pagination="data.pagination" :path="path" />
      </div>
    </main>
  </div>
</template>
