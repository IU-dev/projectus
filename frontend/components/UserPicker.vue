<script setup>
import { onUnmounted, ref, watch } from 'vue'
import { fetchPage } from '../api.js'

const props = defineProps({ selected: Object, busy: Boolean })
defineEmits(['select', 'clear'])
const query = ref('')
const results = ref([])
const loading = ref(false)
const searched = ref(false)
const hasMore = ref(false)
const error = ref('')
let timer
let controller
let sequence = 0

function cancel() {
  clearTimeout(timer)
  controller?.abort()
  sequence += 1
  loading.value = false
}

watch(query, value => {
  cancel()
  results.value = []
  searched.value = false
  hasMore.value = false
  error.value = ''
  const text = value.trim()
  if (text.replace(/\s/g, '').length < 3 || props.selected) return
  const requestId = sequence
  timer = setTimeout(async () => {
    controller = new AbortController()
    loading.value = true
    try {
      const { payload, status } = await fetchPage(`/operations/staff/search/?q=${encodeURIComponent(text)}`, { signal: controller.signal })
      if (requestId !== sequence) return
      if (status !== 200 || payload.redirect) {
        throw new Error(payload.error || 'Поиск недоступен. Обновите страницу и проверьте вход.')
      }
      results.value = payload.results
      hasMore.value = payload.has_more
      searched.value = true
    } catch (exc) {
      if (requestId === sequence && exc.name !== 'AbortError') error.value = exc.message
    } finally {
      if (requestId === sequence) loading.value = false
    }
  }, 300)
})

watch(() => props.selected, () => { cancel(); query.value = ''; results.value = [] })
onUnmounted(cancel)
</script>

<template>
  <div class="user-picker">
    <div v-if="selected" class="selected-user">
      <div><strong>{{ selected.name || selected.email }}</strong><p v-if="selected.name" class="muted">{{ selected.email }}</p></div>
      <button class="quiet" type="button" :disabled="busy" @click="$emit('clear')">Выбрать другого</button>
    </div>
    <template v-else>
      <label for="staff-user-search">Пользователь</label>
      <input
        id="staff-user-search"
        v-model="query"
        type="search"
        maxlength="100"
        autocomplete="off"
        placeholder="Имя или email"
        aria-describedby="staff-search-help"
        :disabled="busy"
      >
      <p id="staff-search-help" class="help">Введите минимум 3 символа имени, фамилии или email.</p>
      <p v-if="loading" role="status" class="muted">Поиск…</p>
      <p v-if="error" role="alert" class="error">{{ error }}</p>
      <ul v-if="results.length" class="user-results" aria-label="Найденные пользователи">
        <li v-for="user in results" :key="user.id">
          <button type="button" :disabled="busy" @click="$emit('select', user.id)">
            <strong>{{ user.name || user.email }}</strong>
            <span v-if="user.name" class="muted">{{ user.email }}</span>
          </button>
        </li>
      </ul>
      <p v-if="searched && !results.length" class="muted" role="status">Подходящих пользователей не найдено.</p>
      <p v-if="hasMore" class="help" role="status">Показаны первые 10 пользователей. Уточните запрос.</p>
    </template>
  </div>
</template>

<style scoped>
.user-picker { margin: 16px 0; }
label { display: block; font-size: 13px; font-weight: 600; margin-bottom: 4px; }
.selected-user { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; overflow-wrap: anywhere; }
.selected-user p { margin: 4px 0 0; font-size: 12px; }
.selected-user button { flex-shrink: 0; }
.user-results { list-style: none; margin: 8px 0; padding: 4px; border: 1px solid var(--line); border-radius: 10px; background: #fff; max-height: 300px; overflow-y: auto; }
.user-results button { width: 100%; display: flex; flex-direction: column; gap: 2px; text-align: left; border: 0; border-radius: 6px; padding: 8px; background: transparent; color: var(--ink); overflow-wrap: anywhere; }
.user-results button:hover, .user-results button:focus-visible { background: var(--mint); }
.user-results span { font-size: 12px; }
</style>
