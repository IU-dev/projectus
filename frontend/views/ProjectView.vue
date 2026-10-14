<script setup>
import { computed } from 'vue'
import { pageProps } from './props.js'
import { date } from '../lib/format.js'
const props = defineProps(pageProps)
const projectPath = computed(() => `/projects/${props.data.project.id}/`)
</script>

<template>
  <section>
    <div class="page-heading">
      <div>
        <h1>{{ data.project.title }}</h1>
        <p class="muted">{{ data.project.owner.email }} · {{ date(data.project.created_at) }}</p>
      </div>
      <div class="actions">
        <a v-if="data.can_edit" class="button secondary" :href="projectPath + 'edit/'">Редактировать</a>
        <a v-if="data.owner" class="button" :href="projectPath + 'members/'">Команда и доступ</a>
      </div>
    </div>
    <div class="detail-grid">
      <section class="panel">
        <h2>Краткое описание проекта</h2>
        <div class="description">{{ data.project.description || 'Нет описания.' }}</div>
      </section>
      <section class="panel">
        <h2>Сроки реализации проекта</h2>
        <p>Начальная дата: {{ data.project.start_date ? date(data.project.start_date + 'T00:00:00') : 'Не указана' }}</p>
        <p>Конечная дата: {{ data.project.end_date ? date(data.project.end_date + 'T00:00:00') : 'Не указана' }}</p>
      </section>
      <section class="panel">
        <h2>Цели проекта</h2>
        <ol v-if="data.project.goals.length"><li v-for="(goal, index) in data.project.goals" :key="index">{{ goal }}</li></ol>
        <p v-else class="muted">Цели пока не добавлены.</p>
      </section>
      <section class="panel">
        <h2>Задачи проекта</h2>
        <ol v-if="data.project.tasks.length"><li v-for="(task, index) in data.project.tasks" :key="index">{{ task }}</li></ol>
        <p v-else class="muted">Задачи пока не добавлены.</p>
      </section>
    </div>
  </section>
</template>
