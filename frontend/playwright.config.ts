import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 240_000,
  expect: {
    timeout: 30_000,
  },
  use: {
    baseURL: 'http://127.0.0.1:4173',
    headless: true,
    trace: 'retain-on-failure',
  },
  webServer: [
    {
      command: 'cd .. && uv run --project backend uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8010',
      url: 'http://127.0.0.1:8010/healthz',
      reuseExistingServer: true,
      timeout: 120_000,
    },
    {
      command: 'VITE_API_BASE_URL=http://127.0.0.1:8010 npx vite --host 127.0.0.1 --port 4173',
      url: 'http://127.0.0.1:4173',
      reuseExistingServer: true,
      timeout: 120_000,
    },
  ],
})
