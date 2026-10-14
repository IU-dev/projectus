<script setup>
import { pageProps } from './props.js'
defineProps(pageProps)
defineEmits(['submit'])
</script>

<template>
  <section class="form-card">
    <h1>{{ data.title }}</h1>
    <p>{{ data.description }}</p>
    <button v-if="data.button" class="button" :disabled="busy" @click="$emit('submit', {})">
      {{ data.button }}
    </button>
  </section>
</template>
