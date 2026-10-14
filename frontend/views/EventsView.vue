<script setup>
import { computed } from 'vue'
import { pageProps } from './props.js'
import { date } from '../lib/format.js'
const props = defineProps(pageProps)
const base = computed(() => `/projects/${props.data.project.id}/events/`)
const day = value => date(value + 'T00:00:00')
</script>

<template>
  <section>
    <div class="page-heading">
      <div><h1>Мероприятия</h1><p class="muted">План, фактические результаты и материалы для отчёта.</p></div>
      <a v-if="data.can_plan" class="button" :href="base + 'new/'">+ Добавить мероприятие</a>
    </div>
    <div v-if="!data.project_events.length" class="panel"><h2>Мероприятий пока нет</h2><p class="muted">Добавьте события и шаги, которые помогут выполнить задачи проекта.</p></div>
    <div v-else class="table-wrap events-table-wrap" role="region" aria-label="Список мероприятий" tabindex="0">
      <table class="events-table">
        <thead><tr>
          <th scope="col">Номер</th><th scope="col">Наименование</th>
          <th scope="col">Дата начала</th><th scope="col">Дата окончания</th>
          <th scope="col">Ожидаемый результат</th><th scope="col">Статус</th><th scope="col">Действия</th>
        </tr></thead>
        <tbody>
          <tr v-for="(event, index) in data.project_events" :key="event.id">
            <td>{{ index + 1 }}</td>
            <th scope="row" class="event-name"><a :href="base + event.id + '/'">{{ event.title }}</a></th>
            <td class="event-date">{{ day(event.start_date) }}</td>
            <td class="event-date">{{ day(event.end_date) }}</td>
            <td class="event-expected">{{ event.expected_result }}</td>
            <td><span class="tag">{{ event.status_label }}</span></td>
            <td><div class="event-actions">
              <a class="button small secondary" :href="base + event.id + '/'">Открыть</a>
              <a v-if="data.can_plan && event.status !== 'confirmed'" class="button small secondary" :href="base + event.id + '/plan/'">Изменить план</a>
              <a v-if="data.can_record && event.status !== 'confirmed'" class="button small secondary" :href="base + event.id + '/result/'">{{ event.status === 'planned' ? 'Внести факт' : 'Изменить факт' }}</a>
              <a v-if="data.can_confirm && event.status === 'conducted'" class="button small" :href="base + event.id + '/confirm/'">Подтвердить</a>
            </div></td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
