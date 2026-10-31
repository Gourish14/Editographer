import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { defineConfig, devices } from '@playwright/test';

/**
 * End-to-end run against the real backend and worker (specs/11-coding-standards.md section 5).
 * Ports differ from the app's own (8080, 8090, 4200) so a running copy is never touched.
 * Run through scripts\e2e.bat, which puts FFmpeg and uv on PATH.
 */
const ROOT = resolve(__dirname, '..');
const BACKEND_PORT = 18080;
const WORKER_PORT = 18090;
const UI_PORT = 4300;

function localEnv(): Record<string, string> {
  const values: Record<string, string> = {};
  for (const line of readFileSync(resolve(ROOT, 'config', 'local.env'), 'utf8').split(/\r?\n/)) {
    const match = /^\s*([A-Z_]+)=(.*)$/.exec(line);
    if (match) {
      values[match[1]] = match[2];
    }
  }
  return values;
}

const shared = {
  ...(process.env as Record<string, string>),
  ...localEnv(),
  BACKEND_PORT: String(BACKEND_PORT),
  WORKER_PORT: String(WORKER_PORT),
  MEDIA_DIR: 'media/e2e',
  DATA_DIR: 'data/e2e',
  LOGS_DIR: 'logs/e2e',
};

export default defineConfig({
  testDir: './e2e',
  timeout: 15 * 60_000,
  expect: { timeout: 30_000 },
  workers: 1,
  reporter: [['list']],
  outputDir: 'e2e-results',
  use: {
    baseURL: `http://127.0.0.1:${UI_PORT}`,
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: `cmd /c "cd /d worker && uv run uvicorn app.main:app --host 127.0.0.1 --port ${WORKER_PORT}"`,
      cwd: ROOT,
      env: shared,
      url: `http://127.0.0.1:${WORKER_PORT}/health`,
      timeout: 180_000,
    },
    {
      command: 'java -jar backend/target/editographer.jar',
      cwd: ROOT,
      env: shared,
      url: `http://127.0.0.1:${BACKEND_PORT}/api/system`,
      timeout: 180_000,
    },
    {
      command: `npx ng serve --port ${UI_PORT} --proxy-config e2e/proxy.e2e.json`,
      cwd: __dirname,
      url: `http://127.0.0.1:${UI_PORT}`,
      timeout: 240_000,
    },
  ],
});
