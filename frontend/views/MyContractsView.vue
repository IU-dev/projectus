<script setup>
import { pageProps } from './props.js'
defineProps(pageProps)
</script>

<template>
  <section>
    <h1>Мои договоры</h1>
    <div class="panel">
      <p class="muted section-placeholder">У вас пока нет договоров.</p>
    </div>
  </section>
</template>
