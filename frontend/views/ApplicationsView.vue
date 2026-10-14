<script setup>
import { pageProps } from './props.js'
defineProps(pageProps)
</script>

<template>
  <section>
    <a class="back" href="/operations/">← Управление сервисом</a>
    <h1>Заявки на проекты</h1>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Проект</th><th>Пользователь</th><th>Статус</th><th>Решение</th></tr></thead>
        <tbody>
          <tr v-for="application in data.applications" :key="application.id">
            <td><strong>{{ application.title }}</strong><p class="muted">{{ application.description.slice(0, 250) }}</p></td>
            <td>{{ application.applicant }}</td>
            <td><span class="tag" :class="application.status">{{ application.status_label }}</span></td>
            <td>
              <a v-if="application.status === 'pending' && data.can_approve" :href="`/operations/applications/${application.id}/`">Рассмотреть →</a>
              <span v-else>{{ application.decision_note || '—' }}</span>
            </td>
          </tr>
          <tr v-if="!data.applications.length"><td colspan="4">Нет заявок.</td></tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
