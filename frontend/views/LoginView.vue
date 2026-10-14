<script setup>
import PageForm from '../components/PageForm.vue'
import { pageProps } from './props.js'
defineProps(pageProps)
defineEmits(['submit'])
</script>

<template>
  <section class="form-card auth-card">
    <h1>Вход в Projectus</h1>
    <PageForm :schema="data.form" :busy="busy" button="Войти" @submit="$emit('submit', $event)" />
    <div class="form-links">
      <a href="/password/reset/">Забыли пароль?</a>
      <a href="/email/resend/">Подтвердить email</a>
      <a href="/register/">Регистрация</a>
    </div>
  </section>
</template>
