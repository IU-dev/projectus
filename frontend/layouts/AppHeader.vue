<script setup>
defineProps({ user: Object, showOperations: Boolean, busy: Boolean, path: String })
defineEmits(['logout'])
</script>

<template>
  <header class="topbar">
    <a class="brand" href="/" aria-label="Projectus — главная">
      <span class="brand-icon" aria-hidden="true">P</span>projectus
    </a>
    <nav aria-label="Основная навигация">
      <template v-if="user">
        <a href="/" :aria-current="path === '/' ? 'page' : undefined">Мои проекты</a>
        <a href="/contracts/" :aria-current="path.startsWith('/contracts/') ? 'page' : undefined">Мои договоры</a>
        <a
          v-if="showOperations"
          href="/operations/"
          :aria-current="path.startsWith('/operations/') ? 'page' : undefined"
        >Управление сервисом</a>
        <a class="account" href="/password/change/">{{ user.email }}</a>
        <button class="quiet" :disabled="busy" @click="$emit('logout')">Выйти</button>
      </template>
      <template v-else>
        <a href="/login/" :aria-current="path === '/login/' ? 'page' : undefined">Войти</a>
        <a class="button secondary small" href="/register/">Регистрация</a>
      </template>
    </nav>
  </header>
</template>
