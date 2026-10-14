<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({ project: { type: Object, required: true }, page: String })
const expanded = ref(false)
const projectPath = computed(() => `/projects/${props.project.id}/`)
const sections = [
  { label: 'Информация', path: '', pages: ['project', 'project_edit'] },
  { label: 'Показатели', path: 'indicators/', pages: ['project_indicators', 'indicator_create', 'indicator_edit'] },
  { label: 'Мероприятия', path: 'events/', pages: ['project_events', 'event_create', 'event_plan', 'event_result', 'event_detail', 'event_confirm'] },
  { label: 'Бюджет', path: 'budget/', pages: ['project_budget', 'budget_revision', 'budget_clone', 'budget_template', 'budget_section_create', 'budget_section_edit', 'budget_line_create', 'budget_line_edit', 'budget_publish', 'budget_submit', 'budget_approve', 'budget_reject', 'budget_settings', 'receipt_create', 'payment_create', 'payment_edit', 'payment_detail', 'payment_submit', 'payment_approve', 'payment_reject', 'payment_execute', 'budget_section_remove', 'budget_line_remove'] },
  { label: 'Договоры', path: 'contracts/', pages: ['project_contracts'] },
]
watch(() => [props.page, props.project.id], () => { expanded.value = false })
</script>

<template>
  <aside class="project-sidebar" aria-label="Выбранный проект">
    <div class="sidebar-heading">
      <strong class="sidebar-title">{{ project.title }}</strong>
      <button
        class="quiet sidebar-toggle"
        :aria-expanded="expanded"
        aria-controls="project-navigation"
        @click="expanded = !expanded"
      >Разделы проекта</button>
    </div>
    <nav
      id="project-navigation"
      class="project-navigation"
      :class="{ expanded }"
      aria-label="Разделы проекта"
    >
      <a
        v-for="section in sections"
        :key="section.path"
        :href="projectPath + section.path"
        :aria-current="section.pages.includes(page) ? 'page' : undefined"
      >{{ section.label }}</a>
      <a class="project-exit" href="/">← Выйти из проекта</a>
    </nav>
  </aside>
</template>
