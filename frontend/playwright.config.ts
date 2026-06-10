import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',

  // Snapshot settings for visual regression
  snapshotDir: './e2e/__screenshots__',
  snapshotPathTemplate: '{snapshotDir}/{testFilePath}/{arg}{ext}',

  // Update snapshots when running with --update-snapshots
  updateSnapshots: 'missing',

  use: {
    baseURL: 'http://localhost:4173',
    trace: 'on-first-retry',

    // Consistent viewport for screenshots
    viewport: { width: 1280, height: 720 },

    // Disable animations for deterministic screenshots
    launchOptions: {
      args: ['--disable-animations'],
    },

    // Screenshot settings
    screenshot: 'only-on-failure',
  },

  expect: {
    // Visual comparison settings
    toHaveScreenshot: {
      maxDiffPixelRatio: 0.02,
      threshold: 0.2,
    },
  },

  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        // Reduce motion for consistent tests
        contextOptions: {
          reducedMotion: 'reduce',
        },
      },
    },
  ],

  webServer: {
    command: 'pnpm run preview',
    url: 'http://localhost:4173',
    reuseExistingServer: !process.env.CI,
    timeout: 120000,
  },
})
