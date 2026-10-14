<script setup>
import { computed, ref, watch } from 'vue'
import { pageProps } from './props.js'
const props = defineProps(pageProps)
const emit = defineEmits(['submit'])
const values = ref({})
watch(() => props.data.form, schema => {
  values.value = Object.fromEntries(schema.fields.map(field => [field.name, field.value]))
}, { immediate: true })
const quantitative = computed(() => values.value.kind === 'quantitative')
const visibleFields = computed(() => props.data.form.fields.filter(field =>
  !(['target_value', 'unit'].includes(field.name) && !quantitative.value)
  && !(['result', 'achieved'].includes(field.name) && quantitative.value)))
function submit() {
  emit('submit', {
    ...values.value,
    target_value: quantitative.value ? values.value.target_value : '',
    unit: quantitative.value ? values.value.unit : '',
    result: quantitative.value ? '' : values.value.result,
    achieved: !quantitative.value && values.value.achieved ? 'on' : '',
  })
}
</script>

<template>
  <section class="form-card">
    <a class="back" :href="`/projects/${data.project.id}/indicators/`">← Показатели</a>
    <h1>{{ data.title }}</h1>
    <form @submit.prevent="submit">
      <fieldset :disabled="busy" class="form-fields">
        <div v-for="error in data.form.errors" :key="error" role="alert" class="error">{{ error }}</div>
        <div v-for="field in visibleFields" :key="field.name" class="field">
          <label :for="`indicator-${field.name}`">{{ field.label }}</label>
          <select v-if="field.name === 'kind'" :id="`indicator-${field.name}`" v-model="values[field.name]" required :disabled="field.disabled">
            <option v-for="choice in field.choices" :key="choice.value" :value="choice.value">{{ choice.label }}</option>
          </select>
          <input v-else-if="field.name === 'achieved'" :id="`indicator-${field.name}`" v-model="values[field.name]" type="checkbox">
          <textarea v-else-if="['title', 'result'].includes(field.name)" :id="`indicator-${field.name}`" v-model="values[field.name]" :required="field.required" :maxlength="field.max_length" rows="3" :aria-invalid="field.errors.length ? 'true' : undefined" :aria-describedby="`indicator-errors-${field.name}`" />
          <input v-else :id="`indicator-${field.name}`" v-model="values[field.name]" :type="field.name === 'target_value' ? 'number' : 'text'" :step="field.name === 'target_value' ? '0.001' : undefined" :min="field.name === 'target_value' ? '0.001' : undefined" :required="field.name === 'target_value'" :maxlength="field.max_length" :aria-invalid="field.errors.length ? 'true' : undefined" :aria-describedby="`indicator-errors-${field.name}`">
          <div :id="`indicator-errors-${field.name}`"><div v-for="error in field.errors" :key="error" role="alert" class="error">{{ error }}</div></div>
        </div>
        <button class="button" type="submit">{{ busy ? 'Сохраняем…' : 'Сохранить показатель' }}</button>
      </fieldset>
    </form>
  </section>
</template>
