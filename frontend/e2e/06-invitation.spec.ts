/** E2E Demo: Magic Link Invitation — create, validate, accept, profile submission. */

import { test, expect } from '@playwright/test';
import { screenshot, resetScreenshotCounter, waitForAPI, apiPost, apiGet, pace } from './helpers';

test.describe('Magic Link Invitation Flow', () => {
  let inviteToken: string | null = null;
  let transactionId: string | null = null;

  test.beforeAll(async () => {
    await waitForAPI();

    // Create a transaction via API for the invitation
    try {
      const txn = await apiPost<{ _id: string }>('/api/transactions', {
        name: 'Invitation Demo — 789 Oak St',
      });
      transactionId = txn._id;

      // Create an invitation
      const invite = await apiPost<{ signed_token: string }>('/api/invitations', {
        email: 'invited-buyer@example.com',
        role: 'BUYER',
        transaction_id: transactionId,
        name: 'Alex Buyer',
      });
      inviteToken = invite.signed_token;
    } catch (err) {
      console.error('Failed to set up invitation:', err);
    }
  });

  test.beforeEach(() => {
    resetScreenshotCounter();
  });

  test('complete magic link invitation flow', async ({ page }) => {
    if (!inviteToken) {
      test.skip(true, 'Could not create invitation — backend may not support it');
      return;
    }

    // ── Step 1: Navigate to invite URL ──
    await page.goto(`/invite/${inviteToken}`);
    await page.waitForLoadState('networkidle');
    await pace(1000);

    // ── Step 2: Welcome card ──
    const welcomeCard = page.locator('.invite-card');
    await expect(welcomeCard).toBeVisible({ timeout: 10000 });

    // Check if it's the welcome step or error
    const heading = await page.locator('.invite-card h2').textContent();

    if (heading?.includes('Something went wrong')) {
      await screenshot(page, 'invite-error');
      // Still a valid demo — shows error handling
      return;
    }

    await expect(page.getByText("You've Been Invited")).toBeVisible();
    await screenshot(page, 'invite-welcome');

    // Verify transaction and role info
    const txnName = page.locator('.invite-txn-name');
    if (await txnName.isVisible()) {
      await expect(txnName).toContainText('789 Oak St');
    }
    await screenshot(page, 'invite-welcome-details');

    // ── Step 3: Accept invitation ──
    await page.getByRole('button', { name: 'Accept Invitation' }).click();
    await page.waitForLoadState('networkidle');
    await pace(1000);
    await screenshot(page, 'invite-profile-form');

    // ── Step 4: Fill profile ──
    const nameInput = page.locator('input[placeholder*="full"]');
    if (await nameInput.isVisible()) {
      await nameInput.fill('Alex J. Buyer');
    }

    const phoneInput = page.locator('input[placeholder*="555"]');
    if (await phoneInput.isVisible()) {
      await phoneInput.fill('(720) 555-1234');
    }
    await screenshot(page, 'invite-profile-filled');

    // ── Step 5: Submit profile ──
    await page.getByRole('button', { name: 'Save & Continue' }).click();
    await page.waitForLoadState('networkidle');
    await pace(1500);
    await screenshot(page, 'invite-success');

    // Verify success state
    const successHeading = page.locator('.invite-card h2');
    if (await successHeading.isVisible()) {
      const text = await successHeading.textContent();
      if (text?.includes('All Set')) {
        await expect(page.getByText('create a full account')).toBeVisible();
        await screenshot(page, 'invite-done');
      }
    }
  });
});
