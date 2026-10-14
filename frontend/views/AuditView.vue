<script setup>
import { pageProps } from './props.js'
import { dateTime } from '../lib/format.js'
defineProps(pageProps)
</script>

<template>
  <section>
    <a class="back" href="/operations/">← Управление сервисом</a>
    <h1>Журнал действий</h1>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Время</th><th>Пользователь</th><th>Действие</th><th>Объект / данные</th></tr></thead>
        <tbody>
          <tr v-for="event in data.events" :key="event.id">
            <td>{{ dateTime(event.created_at) }}</td>
            <td>{{ event.actor || 'Удаленный пользователь' }}</td>
            <td>{{ event.action }}</td>
            <td>{{ event.target }}<p class="muted">{{ JSON.stringify(event.details) }}</p></td>
          </tr>
          <tr v-if="!data.events.length"><td colspan="4">Нет записей.</td></tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
