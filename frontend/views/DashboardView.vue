<script setup>
import { pageProps } from './props.js'
import { date } from '../lib/format.js'
defineProps(pageProps)
</script>

<template>
  <section>
    <div class="page-heading">
      <h1>Мои проекты</h1>
      <a class="button" href="/projects/request/">+ Новый проект</a>
    </div>
    <div class="project-grid">
      <a
        v-for="project in data.projects"
        :key="project.id"
        :href="`/projects/${project.id}/`"
        class="project-card"
      >
        <span class="tag">{{ project.owner.id === user.id ? 'Владелец' : 'Участник' }}</span>
        <h2>{{ project.title }}</h2>
        <p v-if="project.description" class="muted">{{ project.description.slice(0, 140) }}</p>
      </a>
      <div v-if="!data.projects.length" class="empty">
        <h2>Пока нет проектов</h2>
        <a href="/projects/request/">Подать заявку</a>
      </div>
    </div>
    <div class="section-heading"><h2>Заявки</h2></div>
    <div v-if="data.applications.length" class="table-wrap">
      <table>
        <thead><tr><th>Проект</th><th>Дата</th><th>Статус</th><th>Комментарий</th></tr></thead>
        <tbody>
          <tr v-for="application in data.applications" :key="application.id">
            <td>{{ application.title }}</td>
            <td>{{ date(application.created_at) }}</td>
            <td><span class="tag" :class="application.status">{{ application.status_label }}</span></td>
            <td>{{ application.decision_note || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-else class="muted">Нет заявок.</p>
  </section>
</template>
