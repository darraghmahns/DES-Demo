/** E2E Demo: Profile — personal info, role selection, role-specific forms, completion. */

import { test, expect } from '@playwright/test';
import { screenshot, resetScreenshotCounter, waitForAPI, resetTestUser, pace } from './helpers';

test.describe('Profile Management', () => {
  test.beforeAll(async () => {
    await waitForAPI();
    await resetTestUser();
  });

  test.beforeEach(() => {
    resetScreenshotCounter();
  });

  test('complete profile walkthrough — personal info, roles, and forms', async ({ page }) => {
    // ── Navigate to Profile ──
    await page.goto('/profile');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('.app-shell-content h1')).toHaveText('My Profile');
    await screenshot(page, 'profile-initial');

    // ── Verify field editability ──
    // Email field should be present and disabled (read-only — managed by Clerk)
    const emailInput = page.locator('input[type="email"]');
    await expect(emailInput).toBeVisible();
    await expect(emailInput).toBeDisabled();

    // Name field should be present and editable (MongoDB owns name)
    const nameInput = page.locator('input[placeholder="Your full name"]');
    await expect(nameInput).toBeVisible();
    await expect(nameInput).toBeEnabled();

    // ── Fill Personal Information ──
    await nameInput.fill('Jane Marie Doe');
    await page.locator('input[placeholder="(555) 555-5555"]').fill('(303) 555-7890');
    await page.locator('input[placeholder="123 Main St"]').fill('456 Elm Avenue');
    await page.locator('input[placeholder="City"]').fill('Denver');
    await page.locator('input[placeholder="ST"]').fill('CO');
    await page.locator('input[placeholder="12345"]').fill('80202');
    await screenshot(page, 'profile-personal-filled');
    await pace();

    // Save personal info
    await page.getByRole('button', { name: 'Save Personal Info' }).click();
    await page.waitForLoadState('networkidle');
    await pace(1000);
    await screenshot(page, 'profile-personal-saved');

    // Verify name persisted after save (reload page and check value)
    await page.reload();
    await page.waitForLoadState('networkidle');
    await expect(page.locator('input[placeholder="Your full name"]')).toHaveValue('Jane Marie Doe');
    // Email should still be disabled after reload
    await expect(page.locator('input[type="email"]')).toBeDisabled();

    // ── Add Agent Role ──
    const agentChip = page.locator('.role-chip', { hasText: 'Agent' });
    await agentChip.click();
    await page.waitForLoadState('networkidle');
    await pace(1000);

    // Verify Agent form appeared
    await expect(page.getByRole('heading', { name: 'Agent Details' })).toBeVisible();
    await screenshot(page, 'profile-agent-form-visible');

    // Fill Agent details
    await page.locator('input[placeholder="e.g., RE-12345678"]').fill('RE-20250001');
    await page.locator('input[placeholder="e.g., CA"]').fill('CO');
    await page.locator('input[placeholder="e.g., Keller Williams"]').fill('Summit Realty Group');
    await page.locator('input[placeholder="MLS member ID"]').fill('MLS-88442');
    await page.locator('input[placeholder="NAR member ID"]').fill('NAR-112233');
    await screenshot(page, 'profile-agent-filled');

    // Save Agent details
    await page.getByRole('button', { name: 'Save Agent Details' }).click();
    await page.waitForLoadState('networkidle');
    await pace(1000);
    await screenshot(page, 'profile-agent-saved');

    // ── Add Buyer Role ──
    const buyerChip = page.locator('.role-chip', { hasText: 'Buyer' });
    await buyerChip.click();
    await page.waitForLoadState('networkidle');
    await pace(1000);

    // Verify Buyer form appeared
    await expect(page.getByRole('heading', { name: 'Buyer Details' })).toBeVisible();
    await screenshot(page, 'profile-buyer-form-visible');

    // Fill Buyer details
    await page.locator('select').filter({ hasText: 'None' }).selectOption('pre_approved');
    await page.locator('input[placeholder="$0.00"]').first().fill('485000');
    await page.locator('input[placeholder="Lender name"]').fill('First National Bank');
    // Budget min/max
    const budgetInputs = page.locator('input[placeholder="$0.00"]');
    await budgetInputs.nth(1).fill('400000');
    await budgetInputs.nth(2).fill('550000');
    // First-time buyer
    await page.locator('select').filter({ hasText: '-- Select --' }).selectOption('yes');
    // Employment
    await page.locator('input[placeholder*="employed"]').fill('employed');
    await page.locator('input[placeholder="Current employer"]').fill('Meridian Tech Solutions');
    // Annual income — last $0.00 input
    const incomeInput = budgetInputs.last();
    await incomeInput.fill('125000');
    await screenshot(page, 'profile-buyer-filled');

    // Save Buyer details
    await page.getByRole('button', { name: 'Save Buyer Details' }).click();
    await page.waitForLoadState('networkidle');
    await pace(1000);
    await screenshot(page, 'profile-buyer-saved');

    // ── Verify Completion Indicator ──
    const completionLabel = page.locator('.completion-label, .completion-text, [class*="completion"]');
    if (await completionLabel.first().isVisible()) {
      await screenshot(page, 'profile-completion-high');
    }

    // ── Toggle to AI Chat and back ──
    const chatToggle = page.getByRole('button', { name: 'AI Chat' });
    if (await chatToggle.isVisible()) {
      await chatToggle.click();
      await pace();
      await screenshot(page, 'profile-chat-view');

      // Toggle back
      await page.getByRole('button', { name: 'Form View' }).click();
      await pace();
      await screenshot(page, 'profile-form-view-back');
    }

    // Final full-page screenshot of completed profile
    await screenshot(page, 'profile-complete-final');
  });
});
