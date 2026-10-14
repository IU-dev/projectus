<script setup>
import { pageProps } from './props.js'
defineProps(pageProps)
</script>

<template>
  <section>
    <h1>Управление сервисом</h1>
    <div class="project-grid operations-grid">
      <a v-if="data.can_requests" class="project-card" href="/operations/applications/">Заявки на проекты <span>↗</span></a>
      <a v-if="data.can_users" class="project-card" href="/operations/users/">Пользователи <span>↗</span></a>
      <a v-if="data.can_audit" class="project-card" href="/operations/audit/">Журнал действий <span>↗</span></a>
      <a v-if="user.is_superuser" class="project-card" href="/operations/staff/">Полномочия сотрудников <span>↗</span></a>
    </div>
  </section>
</template>
