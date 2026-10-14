import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { fetchPage, localPath } from '../api.js'
import { getPage } from '../pages.js'

export function usePageNavigation(initial) {
  const state = ref(initial)
  const path = ref(window.location.pathname + window.location.search)
  const busy = ref(false)
  const error = ref('')
  const notices = ref(initial.messages || [])
  const content = ref(null)
  let controller
  const data = computed(() => state.value.data || {})
  const page = computed(() => state.value.page)

  async function load(target, values, push = true, depth = 0) {
    if (depth > 8) throw new Error('Не удалось открыть страницу. Обновите страницу.')
    const nextPath = localPath(target)
    controller?.abort()
    controller = new AbortController()
    const { payload, status } = await fetchPage(nextPath, { values, csrfToken: state.value.csrf_token, signal: controller.signal })
    if (payload.csrf_token) state.value.csrf_token = payload.csrf_token
    if (payload.messages?.length) notices.value.push(...payload.messages)
    if (payload.redirect) return load(payload.redirect, undefined, push, depth + 1)
    if (payload.error) throw new Error(payload.error)
    if (payload.page) {
      state.value = payload
      path.value = nextPath
      if (push && window.location.pathname + window.location.search !== nextPath) history.pushState({}, '', nextPath)
      document.title = `${data.value.title || getPage(page.value).title || 'Projectus'} · Projectus`
      await nextTick()
      content.value?.focus()
      if (values === undefined) window.scrollTo(0, 0)
    }
    if (status === 410) error.value = data.value.description
  }

  async function navigate(target, values, push = true) {
    if (busy.value) return
    busy.value = true
    error.value = ''
    notices.value = []
    try { await load(target, values, push) }
    catch (exc) { if (exc.name !== 'AbortError') error.value = exc.message || 'Ошибка соединения. Повторите запрос.' }
    finally { busy.value = false }
  }
  function submit(values) {
    return navigate(path.value, { ...values, ...(data.value.next ? { next: data.value.next } : {}) })
  }
  function intercept(event) {
    const anchor = event.target.closest('a')
    if (!anchor || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || anchor.target || anchor.hasAttribute('download')) return
    const url = new URL(anchor.href)
    if (url.origin !== window.location.origin || url.pathname.startsWith('/admin/') || url.pathname.startsWith('/static/')) return
    event.preventDefault()
    navigate(url.pathname + url.search)
  }
  function popstate() { navigate(window.location.pathname + window.location.search, undefined, false) }
  onMounted(() => window.addEventListener('popstate', popstate))
  onUnmounted(() => { window.removeEventListener('popstate', popstate); controller?.abort() })

  return { state, data, page, path, busy, error, notices, content, navigate, submit, intercept }
}
