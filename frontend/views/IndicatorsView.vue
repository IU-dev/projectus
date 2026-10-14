<script setup>
import { computed } from 'vue'
import { pageProps } from './props.js'
const props = defineProps(pageProps)
const basePath = computed(() => `/projects/${props.data.project.id}/indicators/`)
const number = value => new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 3 }).format(Number(value))
</script>

<template>
  <section>
    <div class="page-heading">
      <h1>Показатели</h1>
      <a v-if="data.can_edit" class="button" :href="basePath + 'new/'">+ Добавить показатель</a>
    </div>
    <div v-if="!data.indicators.length" class="panel">
      <h2>Показателей пока нет</h2>
    </div>
    <div v-else class="indicator-list">
      <article v-for="indicator in data.indicators" :key="indicator.id" class="panel indicator-card">
        <div class="page-heading">
          <span class="tag">{{ indicator.kind_label }}</span>
          <a v-if="data.can_edit" :href="basePath + `${indicator.id}/edit/`" :aria-label="`Редактировать показатель: ${indicator.title}`">Редактировать</a>
        </div>
        <h2>{{ indicator.title }}</h2>
        <template v-if="indicator.kind === 'quantitative'">
          <p class="indicator-value">{{ number(indicator.current_value) }} / {{ number(indicator.target_value) }} <span class="muted">{{ indicator.unit }}</span></p>
          <progress :value="Math.min(Number(indicator.progress_percent), 100)" max="100" :aria-label="`Достижение: ${indicator.title}`" />
          <p>{{ number(indicator.progress_percent) }}% · {{ Number(indicator.current_value) >= Number(indicator.target_value) ? 'Цель достигнута' : 'В процессе' }}</p>
        </template>
        <template v-else>
          <p><strong>{{ indicator.achieved ? 'Достигнут' : 'В процессе' }}</strong></p>
          <h3>Текущий результат</h3>
          <p class="description">{{ indicator.result || 'Результат пока не описан.' }}</p>
        </template>
      </article>
    </div>
  </section>
</template>

<style scoped>
.indicator-card h2, .indicator-card .description { overflow-wrap: anywhere; }
.indicator-card .page-heading { margin-bottom: 12px; }
.indicator-value { font-size: 1.4rem; font-weight: 600; }
progress { width: 100%; height: 12px; accent-color: var(--primary, #246653); }
</style>
