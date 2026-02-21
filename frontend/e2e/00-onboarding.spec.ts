/** E2E Demo: Onboarding guided tour — side panel with 6 steps. */

import { test, expect } from '@playwright/test';
import { screenshot, resetScreenshotCounter, waitForAPI, apiPost, pace } from './helpers';

test.describe('Onboarding Guided Tour', () => {
  test.beforeAll(async () => {
    await waitForAPI();
    // Reset onboarding so the wizard panel appears
    await apiPost('/api/test/reset-onboarding');
  });

  test.beforeEach(() => {
    resetScreenshotCounter();
  });

  test('wizard panel appears and completes full flow', async ({ page }) => {
    // Navigate to app — should show dashboard with onboarding panel
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    // ── Step 1: Welcome ──
    const panel = page.locator('.ob-panel');
    await expect(panel).toBeVisible();
    await expect(panel.locator('.ob-step-title')).toHaveText('Welcome to D.E.S.');
    await screenshot(page, 'onboarding-welcome');

    // Progress dots should be visible
    const dots = panel.locator('.ob-progress-dot');
    await expect(dots).toHaveCount(6);

    // Click "Let's Get Started"
    await panel.getByRole('button', { name: "Let's Get Started" }).click();
    await pace();

    // ── Step 2: Profile ──
    await expect(page).toHaveURL(/\/profile/);
    await expect(panel.locator('.ob-step-heading')).toHaveText('Set Up Your Profile');
    await screenshot(page, 'onboarding-profile');

    // Skip profile step
    await panel.getByRole('button', { name: 'Skip for now' }).click();
    await pace();

    // ── Step 3: AI Chat ──
    await expect(panel.locator('.ob-step-heading')).toHaveText('Meet Your AI Assistant');
    await screenshot(page, 'onboarding-ai-chat');

    // Skip AI chat step
    await panel.getByRole('button', { name: 'Skip for now' }).click();
    await pace();

    // ── Step 4: Documents ──
    await expect(page).toHaveURL(/\/profile\/documents/);
    await expect(panel.locator('.ob-step-heading')).toHaveText('Upload Your Documents');
    await screenshot(page, 'onboarding-documents');

    // Skip documents step
    await panel.getByRole('button', { name: 'Skip for now' }).click();
    await pace();

    // ── Step 5: Extraction ──
    await expect(page).toHaveURL(/\/extraction/);
    await expect(panel.locator('.ob-step-heading')).toHaveText('Try Document Intelligence');
    await screenshot(page, 'onboarding-extraction');

    // Skip extraction step
    await panel.getByRole('button', { name: 'Skip for now' }).click();
    await pace();

    // ── Step 6: Complete ──
    await expect(page).toHaveURL(/\/dashboard/);
    await expect(panel.locator('.ob-step-heading')).toHaveText("You're All Set!");
    await screenshot(page, 'onboarding-complete');

    // Should show summary items
    const summaryItems = panel.locator('.ob-summary-item');
    await expect(summaryItems).toHaveCount(4); // profile, ai_chat, documents, extraction

    // Should show next steps cards
    await expect(panel.locator('.ob-next-steps-card')).toHaveCount(2); // integrations + transactions

    // Click "Go to Dashboard" to finish
    await panel.getByRole('button', { name: 'Go to Dashboard' }).click();
    await pace();

    // Panel should be gone
    await expect(panel).not.toBeVisible();
    await screenshot(page, 'onboarding-done');
  });

  test('wizard does not reappear after completion', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    // Panel should not be visible (onboarding was completed in previous test)
    const panel = page.locator('.ob-panel');
    await expect(panel).not.toBeVisible();
    await screenshot(page, 'onboarding-not-shown');
  });

  test('panel can be dismissed and reopened', async ({ page }) => {
    // Reset onboarding again
    await apiPost('/api/test/reset-onboarding');

    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    const panel = page.locator('.ob-panel');
    await expect(panel).toBeVisible();

    // Dismiss the panel
    await panel.locator('.ob-panel-minimize').click();
    await pace();
    await expect(panel).not.toBeVisible();

    // Reopen button should appear
    const reopenBtn = page.locator('.ob-reopen-btn');
    await expect(reopenBtn).toBeVisible();
    await screenshot(page, 'onboarding-dismissed');

    // Click reopen
    await reopenBtn.click();
    await pace();
    await expect(panel).toBeVisible();
    await screenshot(page, 'onboarding-reopened');

    // Complete onboarding to clean up for subsequent tests
    await apiPost('/api/test/complete-onboarding');
  });

  // Clean up: complete onboarding so subsequent test specs don't see it
  test.afterAll(async () => {
    try {
      // Clear the e2e reset flag so subsequent specs get completed:true (default)
      await apiPost('/api/test/complete-onboarding');
    } catch {
      // ignore
    }
  });
});
