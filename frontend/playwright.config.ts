import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,        // Tests share dev user state — run sequentially
  workers: 1,
  timeout: 30_000,
  retries: 0,
  reporter: [['html', { open: 'never' }]],

  use: {
    baseURL: 'http://localhost:5174',
    screenshot: 'on',
    video: 'on',
    trace: 'on-first-retry',
    actionTimeout: 10_000,
  },

  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
    },
  ],

  /* Start a dedicated Vite dev server for E2E on port 5174 (no Clerk auth). */
  webServer: {
    command: 'npx vite --mode e2e --port 5174',
    port: 5174,
    reuseExistingServer: true,
    timeout: 15_000,
  },
});
