<script setup>
import { computed } from 'vue'
import { pageProps } from './props.js'
import { date, dateTime } from '../lib/format.js'
import PageForm from '../components/PageForm.vue'
const props = defineProps(pageProps)
defineEmits(['navigate'])
const event = computed(() => props.data.event)
const base = computed(() => `/projects/${props.data.project.id}/events/${event.value.id}/`)
const day = value => value ? date(value + 'T00:00:00') : 'Не указана'
const number = value => value === null ? '—' : new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 3 }).format(Number(value))
</script>

<template>
  <section>
    <a class="back" :href="`/projects/${data.project.id}/events/`">← Мероприятия</a>
    <div class="page-heading">
      <div><span class="tag">{{ event.status_label }}</span><h1>{{ event.title }}</h1></div>
      <div class="actions">
        <a v-if="data.can_plan && event.status !== 'confirmed'" class="button secondary" :href="base + 'plan/'">Изменить план</a>
        <a v-if="data.can_record && event.status !== 'confirmed'" class="button" :href="base + 'result/'">{{ event.status === 'planned' ? 'Внести факт проведения' : 'Изменить факт проведения' }}</a>
        <a v-if="data.can_confirm && event.status === 'conducted'" class="button" :href="base + 'confirm/'">Подтвердить проведение</a>
      </div>
    </div>
    <p v-if="event.status === 'confirmed'" class="notice">Подтверждено {{ dateTime(event.confirmed_at) }} · {{ event.confirmed_by }}. Мероприятие и вложения доступны только для просмотра.</p>
    <p v-else-if="event.status === 'conducted'" class="notice">Ожидает подтверждения. Фактические значения ещё не включены в достижение показателей проекта.</p>
    <div class="detail-grid">
      <section class="panel"><h2>План</h2><p>{{ day(event.start_date) }} — {{ day(event.end_date) }}</p><h3>Ожидаемый результат</h3><p class="description">{{ event.expected_result }}</p></section>
      <section class="panel"><h2>Факт</h2><template v-if="event.status !== 'planned'"><p>{{ day(event.actual_start_date) }} — {{ day(event.actual_end_date) }}</p><h3>Фактический результат</h3><p class="description">{{ event.actual_result }}</p><p>{{ event.actual_end_date <= event.end_date ? 'Завершено в плановый срок' : 'Завершено позже планового срока' }}</p></template><p v-else class="muted">Факт проведения ещё не внесён.</p></section>
    </div>
    <section class="panel"><h2>Задачи проекта</h2><ul v-if="event.tasks.length"><li v-for="task in event.tasks" :key="task">{{ task }}</li></ul><p v-else class="muted">Задачи не привязаны.</p></section>
    <section class="panel">
      <h2>Показатели: план и факт</h2>
      <p v-if="!event.indicators.length" class="muted">Показатели не привязаны.</p>
      <article v-for="indicator in event.indicators" :key="indicator.id" class="event-indicator">
        <h3>{{ indicator.title }}</h3>
        <template v-if="indicator.kind === 'quantitative'">
          <p>План: {{ number(indicator.planned_value) }} {{ indicator.unit }} · Факт: {{ number(indicator.actual_value) }} {{ indicator.unit }}</p>
          <strong v-if="indicator.met !== null">{{ indicator.met ? 'План выполнен' : 'План не выполнен' }}</strong>
          <span v-else class="muted">Фактическое значение пока не внесено.</span>
        </template>
        <p v-else class="muted">Качественный показатель · справочная связь</p>
      </article>
    </section>
    <section class="panel">
      <h2>Фотографии и файлы</h2>
      <p v-if="event.status === 'planned'" class="muted">Материалы можно прикрепить после внесения факта проведения.</p>
      <ul v-else-if="event.attachments.length" class="attachment-list">
        <li v-for="file in event.attachments" :key="file.id">
          <div><a :href="file.url" download>{{ file.name }}</a><p class="muted">{{ file.kind }} · {{ Math.max(1, Math.ceil(file.size / 1024)) }} КБ</p></div>
          <button v-if="data.can_record && event.status === 'conducted'" class="quiet danger" :disabled="busy" :aria-label="`Удалить файл ${file.name}`" @click="$emit('navigate', base + `attachments/${file.id}/remove/`, {})">Удалить</button>
        </li>
      </ul>
      <p v-else class="muted">Файлы пока не прикреплены.</p>
      <div v-if="data.form" class="attachment-form"><h3>Прикрепить файл</h3><PageForm :schema="data.form" :busy="busy" button="Прикрепить файл" @submit="$emit('navigate', base + 'attachments/', $event)" /></div>
    </section>
  </section>
</template>
<style scoped>
h1, h3, .description, li { overflow-wrap: anywhere; }
section > .panel + .panel { margin-top: 16px; }
.event-indicator { padding: 12px 0; border-bottom: 1px solid #dbe5df; }
.event-indicator:last-child { border-bottom: 0; }
.attachment-list { list-style: none; padding: 0; }
.attachment-list li { display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 8px 0; }
.attachment-list p { margin: 4px 0; }
.attachment-form { max-width: 520px; margin-top: 20px; }
</style>
