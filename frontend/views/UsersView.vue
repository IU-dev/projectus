<script setup>
import { pageProps } from './props.js'
import { permissionLabels } from '../lib/format.js'
defineProps(pageProps)
</script>

<template>
  <section>
    <a class="back" href="/operations/">← Управление сервисом</a>
    <h1>Пользователи</h1>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Email</th><th>Имя</th><th>Подтвержден</th><th>Полномочия</th></tr></thead>
        <tbody>
          <tr v-for="account in data.users" :key="account.id">
            <td>{{ account.email }}</td>
            <td>{{ account.name || '—' }}</td>
            <td>{{ account.email_verified ? 'Да' : 'Нет' }}</td>
            <td>{{ account.is_superuser ? 'Главный аккаунт' : permissionLabels(account.permissions) || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
