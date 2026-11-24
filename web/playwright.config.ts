import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  outputDir: '../artifacts/playwright-results',
  reporter: 'list',
  use: {
    launchOptions: { args: ['--unsafely-treat-insecure-origin-as-secure=http://100.66.205.39:8000'] }, baseURL: process.env.E2E_BASE_URL ?? 'http://100.66.205.39:8000', trace: 'retain-on-failure' },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1440, height: 900 } } },
    { name: 'phone', use: { viewport: { width: 390, height: 844 }, hasTouch: true } },
  ],
})
