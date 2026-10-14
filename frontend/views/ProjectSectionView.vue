<script setup>
import { pageProps } from './props.js'
defineProps(pageProps)
</script>

<template>
  <section>
    <h1>{{ data.title }}</h1>
    <div class="panel">
      <p class="muted section-placeholder">Функционал раздела будет добавлен позже.</p>
    </div>
  </section>
</template>
