<script setup>
const props = defineProps({ pagination: Object, path: String })
function pageLink(number) {
  const url = new URL(props.path, window.location.origin)
  url.searchParams.set('page', number)
  return url.pathname + url.search
}
</script>
<template>
  <nav v-if="pagination && pagination.pages > 1" class="pagination" aria-label="Страницы списка">
    <a v-if="pagination.page > 1" :href="pageLink(pagination.page - 1)">← Назад</a>
    <span>Страница {{ pagination.page }} из {{ pagination.pages }}</span>
    <a v-if="pagination.page < pagination.pages" :href="pageLink(pagination.page + 1)">Далее →</a>
  </nav>
</template>
