import { test, expect, Page } from '@playwright/test'

// Helper to check for console errors
function setupConsoleErrorCheck(page: Page): string[] {
  const errors: string[] = []
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      errors.push(msg.text())
    }
  })
  page.on('pageerror', (error) => {
    errors.push(error.message)
  })
  return errors
}

// Helper to measure CLS
async function measureCLS(page: Page): Promise<number> {
  return await page.evaluate(() => {
    return new Promise<number>((resolve) => {
      let clsValue = 0
      const observer = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          const layoutShift = entry as unknown as { hadRecentInput: boolean; value: number }
          if (!layoutShift.hadRecentInput) {
            clsValue += layoutShift.value
          }
        }
      })
      observer.observe({ type: 'layout-shift', buffered: true })
      // Wait a bit and return accumulated CLS
      setTimeout(() => {
        observer.disconnect()
        resolve(clsValue)
      }, 1000)
    })
  })
}

test.describe('Home Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    // Wait for initial load
    await page.waitForLoadState('domcontentloaded')
  })

  test('displays the page title', async ({ page }) => {
    const errors = setupConsoleErrorCheck(page)
    await expect(page.locator('[data-testid="home-page"]')).toBeVisible()
    await expect(page.locator('h1')).toContainText('Daily Paper Report')
    expect(errors).toHaveLength(0)
  })

  test('displays the header with logo', async ({ page }) => {
    await expect(page.locator('[data-testid="logo-link"]')).toBeVisible()
    await expect(page.locator('[data-testid="logo-link"]')).toContainText('Daily Paper Report')
  })

  test('navigation links are visible and functional', async ({ page }) => {
    // Check navigation links exist
    await expect(page.locator('[data-testid="nav-today"]')).toBeVisible()
    await expect(page.locator('[data-testid="nav-archive"]')).toBeVisible()
    await expect(page.locator('[data-testid="nav-sources"]')).toBeVisible()
    await expect(page.locator('[data-testid="nav-status"]')).toBeVisible()

    // Navigate to Archive page
    await page.locator('[data-testid="nav-archive"]').click()
    await expect(page.locator('[data-testid="archive-page"]')).toBeVisible()

    // Navigate to Sources page
    await page.locator('[data-testid="nav-sources"]').click()
    await expect(page.locator('[data-testid="sources-page"]')).toBeVisible()

    // Navigate to Status page
    await page.locator('[data-testid="nav-status"]').click()
    await expect(page.locator('[data-testid="status-page"]')).toBeVisible()

    // Navigate back to Home
    await page.locator('[data-testid="nav-today"]').click()
    await expect(page.locator('[data-testid="home-page"]')).toBeVisible()
  })

  test('displays dashboard with stats and tabs', async ({ page }) => {
    const errors = setupConsoleErrorCheck(page)

    // Wait for content to load (either stats grid or loading state)
    await page.locator('.stats-grid, .content-skeleton').first().waitFor({ timeout: 10000 })

    // Check main tabs exist (category/source view)
    await expect(page.locator('.main-tabs')).toBeVisible()

    // Check tab buttons
    const categoryTab = page.locator('button:has-text("By Category")')
    const sourceTab = page.locator('button:has-text("By Source")')

    // At least one tab should be visible
    const hasCategoryTab = await categoryTab.isVisible().catch(() => false)
    const hasSourceTab = await sourceTab.isVisible().catch(() => false)
    expect(hasCategoryTab || hasSourceTab).toBeTruthy()

    expect(errors).toHaveLength(0)
  })

  test('search functionality works', async ({ page }) => {
    // Wait for search to be available
    await page.locator('.search-box').waitFor({ timeout: 10000 })

    const searchInput = page.locator('.search-input')
    await expect(searchInput).toBeVisible()

    // Type in search
    await searchInput.fill('test')

    // Search results indicator should appear
    await expect(page.locator('.search-results-indicator')).toBeVisible({ timeout: 5000 })
  })

  test('has no layout shifts (CLS check)', async ({ page }) => {
    const cls = await measureCLS(page)
    // CLS should be minimal (< 0.1 is good, < 0.25 is acceptable)
    expect(cls).toBeLessThan(0.25)
  })

  test('visual regression - home page', async ({ page }) => {
    // Wait for content to stabilize
    await page.waitForLoadState('domcontentloaded')
    await page.locator('.stats-grid, .content-skeleton').first().waitFor({ state: 'visible' })

    // Take screenshot for visual regression
    await expect(page).toHaveScreenshot('home-page.png', {
      maxDiffPixelRatio: 0.02,
      mask: [
        // Mask dynamic content like timestamps
        page.locator('.paper-card-time'),
        page.locator('.stat-number-time'),
      ],
    })
  })
})

test.describe('Sources Page', () => {
  test('displays source cards when data is available', async ({ page }) => {
    await page.goto('/sources')

    await expect(page.locator('[data-testid="sources-page"]')).toBeVisible()
    await expect(page.locator('h1')).toContainText('Sources')
  })

  test('visual regression - sources page', async ({ page }) => {
    await page.goto('/sources')
    await page.waitForLoadState('domcontentloaded')

    await expect(page).toHaveScreenshot('sources-page.png', {
      maxDiffPixelRatio: 0.02,
    })
  })
})

test.describe('Status Page', () => {
  test('displays system status information', async ({ page }) => {
    await page.goto('/status')

    await expect(page.locator('[data-testid="status-page"]')).toBeVisible()
    await expect(page.locator('h1')).toContainText('Status')
  })

  test('visual regression - status page', async ({ page }) => {
    await page.goto('/status')
    await page.waitForLoadState('domcontentloaded')

    await expect(page).toHaveScreenshot('status-page.png', {
      maxDiffPixelRatio: 0.02,
    })
  })
})

test.describe('Archive Page', () => {
  test('displays archive placeholder', async ({ page }) => {
    await page.goto('/archive')

    await expect(page.locator('[data-testid="archive-page"]')).toBeVisible()
    await expect(page.locator('h1')).toContainText('Archive')
  })

  test('visual regression - archive page', async ({ page }) => {
    await page.goto('/archive')
    await page.waitForLoadState('domcontentloaded')

    await expect(page).toHaveScreenshot('archive-page.png', {
      maxDiffPixelRatio: 0.02,
    })
  })
})
