import { test } from 'node:test'
import assert from 'node:assert/strict'
import { encodeForm, localPath, fetchPage } from '../api.js'

test('permissions retain repeated values and empty lists revoke all grants', () => {
  assert.deepEqual(encodeForm({ permissions: ['edit_project', 'view_finance'], email: 'a+b@example.com' }).getAll('permissions'), ['edit_project', 'view_finance'])
  assert.equal(encodeForm({ permissions: [] }).has('permissions'), false)
  assert.equal(encodeForm({ email: 'a+b@example.com' }).get('email'), 'a+b@example.com')
})

test('navigation refuses external and script URLs', () => {
  assert.equal(localPath('/login/?next=%2Fprojects%2F', 'http://localhost'), '/login/?next=%2Fprojects%2F')
  for (const path of ['https://attacker.test/', '//attacker.test/', 'javascript:alert(1)']) {
    assert.throws(() => localPath(path, 'http://localhost'))
  }
})

test('mutation sends session credentials and a current CSRF token', async () => {
  globalThis.window = { location: { origin: 'http://localhost' } }
  const originalFetch = globalThis.fetch
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/projects/request/')
    assert.equal(options.headers['X-CSRFToken'], 'current-token')
    assert.equal(options.credentials, 'same-origin')
    assert.equal(options.redirect, 'error')
    assert.equal(options.method, 'POST')
    assert.equal(options.body.get('title'), 'Тест')
    return new Response(JSON.stringify({ redirect: '/' }), { headers: { 'Content-Type': 'application/json' } })
  }
  try { assert.equal((await fetchPage('/projects/request/', { values: { title: 'Тест' }, csrfToken: 'current-token' })).payload.redirect, '/') }
  finally { globalThis.fetch = originalFetch; delete globalThis.window }
})

test('file uploads use multipart and retain file bytes and repeated fields', async () => {
  const file = new Blob(['evidence'], { type: 'text/plain' })
  const body = encodeForm({ file, kind: 'participants', indicators: ['1', '2'], confirmed: false })
  assert.ok(body instanceof FormData)
  assert.equal(await body.get('file').text(), 'evidence')
  assert.deepEqual(body.getAll('indicators'), ['1', '2'])
  assert.equal(body.get('kind'), 'participants')
  assert.equal(body.get('confirmed'), '')
})
