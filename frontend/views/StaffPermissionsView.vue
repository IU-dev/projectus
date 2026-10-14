<script setup>
import PageForm from '../components/PageForm.vue'
import UserPicker from '../components/UserPicker.vue'
import { pageProps } from './props.js'
defineProps(pageProps)
defineEmits(['submit', 'navigate'])
</script>

<template>
  <section>
    <a class="back" href="/operations/">← Управление сервисом</a>
    <h1>Полномочия сотрудников</h1>
    <div class="detail-grid">
      <section class="panel">
        <h2>Назначить полномочия</h2>
        <UserPicker
          :selected="data.selected_user"
          :busy="busy"
          @select="$emit('navigate', `/operations/staff/?user_id=${$event}`)"
          @clear="$emit('navigate', '/operations/staff/')"
        />
        <p class="muted">Пустой список отзывает все полномочия.</p>
        <PageForm :schema="data.form" :busy="busy" :disabled="!data.selected_user" button="Сохранить полномочия" @submit="$emit('submit', $event)" />
      </section>
      <section class="panel">
        <h2>Сотрудники</h2>
        <div v-for="employee in data.staff" :key="employee.id" class="member-row">
          <div>
            <strong>{{ employee.email }}</strong>
            <ul class="rights">
              <li v-for="permission in employee.permissions" :key="permission.code">{{ permission.label }}</li>
            </ul>
            <a :href="`/operations/staff/?user_id=${employee.id}`">Изменить полномочия</a>
          </div>
        </div>
        <p v-if="!data.staff.length" class="muted">Нет назначений.</p>
      </section>
    </div>
  </section>
</template>
