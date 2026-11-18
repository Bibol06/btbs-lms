import { defineConfig } from '@playwright/test'

// QA/e2e suite. Needs the isolated QA environment (tools/qa/start_qa.ps1): frontend 5174 → backend 8100 → lms_qa.
// Locally it runs on the installed Microsoft Edge; CI sets E2E_CHANNEL='' and installs Playwright's chromium.
const channel = process.env.E2E_CHANNEL ?? 'msedge'

export default defineConfig({
  testDir: './e2e',
  // The full sweep is long; it runs only when asked for explicitly (npm run e2e:sweep).
  testIgnore: process.argv.some(arg => arg.includes('sweep')) ? [] : ['**/sweep.spec.ts'],
  timeout: 120_000,
  expect: { timeout: 10_000 },
  fullyParallel: true,
  // One worker by default: several Edge instances next to PostgreSQL, two dev servers and
  // the IDE exhausted 12 GB of RAM and crashed PostgreSQL (QA-001). Raise E2E_WORKERS on bigger machines.
  workers: Number(process.env.E2E_WORKERS || 1),
  reporter: [['list']],
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://127.0.0.1:5174',
    ...(channel ? { channel } : {}),
    trace: 'off',
    screenshot: 'off',
    video: 'off',
    locale: 'ru-RU',
  },
})
