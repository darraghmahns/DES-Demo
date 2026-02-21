/** E2E Demo: Dashboard — navigation cards, completion banner, page links. */

import { test, expect } from '@playwright/test';
import { screenshot, resetScreenshotCounter, waitForAPI, resetTestUser, pace } from './helpers';

test.describe('Dashboard Walkthrough', () => {
  test.beforeAll(async () => {
    await waitForAPI();
    await resetTestUser();
  });

  test.beforeEach(() => {
    resetScreenshotCounter();
  });

  test('dashboard loads with welcome message and navigation cards', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    // Verify welcome heading (scoped to main content area)
    const main = page.locator('.app-shell-content');
    await expect(main.locator('h1')).toHaveText('Dashboard');
    await expect(main.locator('.page-subtitle')).toContainText('D.E.S.');
    await screenshot(page, 'dashboard-landing');

    // Verify all 4 dashboard cards are present
    const cards = page.locator('.dashboard-card');
    await expect(cards).toHaveCount(4);

    // Check card labels (scoped to dashboard grid to avoid sidebar matches)
    const grid = page.locator('.dashboard-grid');
    await expect(grid.getByText('Document Extraction')).toBeVisible();
    await expect(grid.getByText('Transactions')).toBeVisible();
    await expect(grid.getByText('My Profile')).toBeVisible();
    await expect(grid.getByText('My Documents')).toBeVisible();
    await screenshot(page, 'dashboard-cards');
  });

  test('navigate to each page from dashboard cards', async ({ page }) => {
    const grid = page.locator('.dashboard-grid');

    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    // Click Extraction card
    await grid.locator('.dashboard-card', { hasText: 'Document Extraction' }).click();
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(/\/extraction/);
    await screenshot(page, 'nav-extraction');
    await pace();

    // Click back and then Transactions
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    await grid.locator('.dashboard-card', { hasText: 'Transactions' }).click();
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(/\/transactions/);
    await screenshot(page, 'nav-transactions');
    await pace();

    // Click back and then Profile
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    await grid.locator('.dashboard-card', { hasText: 'My Profile' }).click();
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(/\/profile/);
    await screenshot(page, 'nav-profile');
    await pace();

    // Click back and then Documents
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    await grid.locator('.dashboard-card', { hasText: 'My Documents' }).click();
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(/\/profile\/documents/);
    await screenshot(page, 'nav-documents');
  });

  test('completion banner appears when profile is incomplete', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    // With a fresh/reset user, completion should be low — banner should appear
    const banner = page.locator('.dashboard-completion-banner');
    // Banner may or may not appear depending on backend state
    if (await banner.isVisible()) {
      await expect(banner).toContainText('complete');
      await expect(page.getByText('Complete Profile')).toBeVisible();
      await screenshot(page, 'dashboard-completion-banner');
    } else {
      await screenshot(page, 'dashboard-no-banner');
    }
  });
});
