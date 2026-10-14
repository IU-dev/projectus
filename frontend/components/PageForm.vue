<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  schema: Object,
  button: { type: String, default: 'Сохранить' },
  busy: Boolean,
  disabled: Boolean,
})
const emit = defineEmits(['submit'])
const values = ref({})
const revision = ref(0)
const visible = field => !field.show_when || values.value[field.show_when.field]?.includes(field.show_when.value)

watch(() => props.schema, schema => {
  revision.value++
  values.value = Object.fromEntries(schema.fields.map(field => [
    field.name,
    Array.isArray(field.value) ? [...field.value] : field.value,
  ]))
}, { immediate: true })

const autocomplete = name => ({
  username: 'username', email: 'email',
  first_name: 'given-name', last_name: 'family-name',
  password: 'current-password', old_password: 'current-password',
  password1: 'new-password', password2: 'new-password',
  new_password1: 'new-password', new_password2: 'new-password',
})[name] || 'off'
</script>

<template>
  <form @submit.prevent="emit('submit', values)">
    <fieldset :disabled="busy || disabled" class="form-fields">
      <div v-for="error in schema.errors" :key="error" role="alert" class="error">{{ error }}</div>
      <template v-for="field in schema.fields" :key="field.name">
      <div v-if="visible(field)" :class="{ field: field.kind !== 'hidden' }">
        <input v-if="field.kind === 'hidden'" type="hidden" :name="field.name" :value="values[field.name]">
        <fieldset v-else-if="field.kind === 'text-list'" class="project-list-fields">
          <legend>{{ field.label }}</legend>
          <div v-for="(_, index) in values[field.name]" :key="index" class="project-list-row">
            <label :for="`field-${field.name}-${index}`">{{ field.name === 'goals' ? 'Цель' : 'Задача' }} {{ index + 1 }}</label>
            <div class="project-list-controls">
              <input :id="`field-${field.name}-${index}`" v-model="values[field.name][index]" type="text" :name="field.name">
              <button type="button" class="button secondary" :disabled="values[field.name].length === 1" :aria-label="`${field.name === 'goals' ? 'Удалить цель' : 'Удалить задачу'} ${index + 1}`" @click="values[field.name].splice(index, 1)">−</button>
            </div>
          </div>
          <button type="button" class="button secondary" :aria-label="field.name === 'goals' ? 'Добавить цель' : 'Добавить задачу'" @click="values[field.name].push('')">+</button>
        </fieldset>
        <fieldset v-else-if="field.kind === 'checkboxes'" class="permission-fields">
          <legend>{{ field.label }}</legend>
          <label v-for="choice in field.choices" :key="choice.value" class="check-choice">
            <input v-model="values[field.name]" type="checkbox" :value="choice.value" :name="field.name">
            {{ choice.label }}
          </label>
        </fieldset>
        <template v-else>
          <label :for="`field-${field.name}`">{{ field.label }}</label>
          <textarea
            v-if="field.kind === 'textarea'"
            :id="`field-${field.name}`"
            v-model="values[field.name]"
            :required="field.required"
            :maxlength="field.max_length"
            :aria-describedby="`help-${field.name}`"
          />
          <select
            v-else-if="field.kind === 'select'"
            :id="`field-${field.name}`"
            v-model="values[field.name]"
            :required="field.required"
          >
            <option v-for="choice in field.choices" :key="choice.value" :value="choice.value">
              {{ choice.label }}
            </option>
          </select>
          <input
            v-else-if="field.kind === 'file'"
            :key="revision"
            :id="`field-${field.name}`"
            type="file"
            :required="field.required"
            @change="values[field.name] = $event.target.files[0] || ''"
          >
          <input
            v-else
            :id="`field-${field.name}`"
            v-model="values[field.name]"
            :name="field.name"
            :type="field.kind"
            :required="field.required"
            :maxlength="field.max_length"
            :min="field.min"
            :step="field.step"
            :autocomplete="autocomplete(field.name)"
            :aria-invalid="field.errors.length ? 'true' : undefined"
            :aria-describedby="`help-${field.name}`"
          >
        </template>
        <div :id="`help-${field.name}`" class="help">{{ field.help }}</div>
        <div v-for="error in field.errors" :key="error" role="alert" class="error">{{ error }}</div>
      </div>
      </template>
      <button class="button" type="submit">{{ busy ? 'Сохраняем…' : button }}</button>
    </fieldset>
  </form>
</template>
