<script setup>
import PageForm from '../components/PageForm.vue'
import { pageProps } from './props.js'
defineProps(pageProps)
defineEmits(['submit'])
</script>

<template>
  <section class="form-card">
    <a v-if="data.back_url" :href="data.back_url">← Вернуться</a>
    <h1>{{ data.title || options.title }}</h1>
    <p v-if="options.showSubtitle && data.subtitle" class="muted">{{ data.subtitle }}</p>
    <PageForm
      v-if="data.form"
      :schema="data.form"
      :busy="busy"
      :button="data.button || options.button || 'Сохранить'"
      @submit="$emit('submit', $event)"
    />
    <template v-if="data.validlink === false">
      <p>Ссылка недействительна или срок ее действия истек.</p>
      <a href="/password/reset/">Запросить новую ссылку</a>
    </template>
  </section>
</template>
