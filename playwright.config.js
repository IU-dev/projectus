import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: 'frontend/e2e',
  workers: 1,
  timeout: 90000,
  use: { baseURL: process.env.PROJECTUS_TEST_URL, channel: process.env.PLAYWRIGHT_CHANNEL || undefined, headless: true, actionTimeout: 10000, screenshot: 'only-on-failure' },
  reporter: 'line',
})
