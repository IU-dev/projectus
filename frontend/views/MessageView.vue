<script setup>
import { pageProps } from './props.js'
defineProps(pageProps)
</script>

<template>
  <section class="form-card">
    <h1>{{ options.title }}</h1>
    <p v-if="options.message">{{ options.message }}</p>
    <a :href="options.href">{{ options.link }}</a>
  </section>
</template>
