export function localPath(value, origin = window.location.origin) {
  const url = new URL(value, origin)
  if (url.origin !== origin || !['http:', 'https:'].includes(url.protocol)) {
    throw new Error('Недопустимый адрес перехода.')
  }
  return url.pathname + url.search + url.hash
}

export function encodeForm(values) {
  const hasFile = Object.values(values).some(value => value instanceof Blob || (Array.isArray(value) && value.some(item => item instanceof Blob)))
  const body = hasFile ? new FormData() : new URLSearchParams()
  for (const [key, value] of Object.entries(values)) {
    if (Array.isArray(value)) value.forEach(item => body.append(key, item))
    else body.append(key, typeof value === 'boolean' ? (value ? 'on' : '') : value ?? '')
  }
  return body
}

export async function fetchPage(path, { values, csrfToken, signal } = {}) {
  const response = await fetch(localPath(path), {
    method: values === undefined ? 'GET' : 'POST',
    credentials: 'same-origin', redirect: 'error', signal,
    headers: { Accept: 'application/json', ...(values === undefined ? {} : { 'X-CSRFToken': csrfToken }) },
    body: values === undefined ? undefined : encodeForm(values),
  })
  if (!response.headers.get('content-type')?.includes('application/json')) {
    throw new Error('Сервер вернул неожиданный ответ. Обновите страницу.')
  }
  const payload = await response.json()
  return { payload, status: response.status }
}
