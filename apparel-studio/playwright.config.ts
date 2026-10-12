import { defineConfig } from '@playwright/test';
import fs from 'node:fs';

// Use a preinstalled Chromium when present (CI/cloud images); otherwise Playwright's own.
const chrome = process.env.CHROME_PATH || (fs.existsSync('/opt/pw-browsers/chromium') ? '/opt/pw-browsers/chromium' : undefined);

export default defineConfig({
  testDir: 'e2e',
  timeout: 90_000,
  expect: { timeout: 15_000 },
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:5174',
    viewport: { width: 1440, height: 900 },
    launchOptions: chrome ? { executablePath: chrome } : {},
    trace: 'retain-on-failure',
  },
  webServer: [
    {
      command: 'rm -rf .e2e-data && DATA_DIR=.e2e-data PORT=4100 node --import tsx src/server/index.ts',
      url: 'http://localhost:4100/api/health',
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: 'API_URL=http://localhost:4100 npx vite --port 5174 --strictPort',
      url: 'http://localhost:5174',
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
