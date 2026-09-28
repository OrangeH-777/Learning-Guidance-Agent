import { defineConfig } from '@playwright/test'
import { resolve } from 'node:path'

const root = resolve(import.meta.dirname, '..')
const python = resolve(root, process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python')

export default defineConfig({
  testDir: './e2e',
  outputDir: '../tests/results/browser',
  workers: 1,
  retries: 0,
  timeout: 30000,
  reporter: [['list'], ['json', { outputFile: '../tests/results/browser-report.json' }]],
  use: { baseURL: 'http://127.0.0.1:5174', screenshot: 'only-on-failure', trace: 'retain-on-failure' },
  projects: [{ name: 'chrome', use: { channel: 'chrome' } }, { name: 'edge', use: { channel: 'msedge' } }],
  webServer: [
    { command: `"${python}" -m scripts.serve_test_backend`, cwd: root, url: 'http://127.0.0.1:8001/health/ready', reuseExistingServer: false, timeout: 30000 },
    { command: 'npm run dev -- --port 5174', url: 'http://127.0.0.1:5174', env: { API_PROXY_TARGET: 'http://127.0.0.1:8001' }, reuseExistingServer: false },
  ],
})
