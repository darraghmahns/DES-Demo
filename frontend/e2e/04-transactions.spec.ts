/** E2E Demo: Transactions — CRUD, participants, tabs, status, auto-fill. */

import { test, expect } from '@playwright/test';
import { screenshot, resetScreenshotCounter, waitForAPI, cleanupTransactions, pace } from './helpers';

test.describe('Transaction Management', () => {
  test.beforeAll(async () => {
    await waitForAPI();
    await cleanupTransactions();
  });

  test.beforeEach(() => {
    resetScreenshotCounter();
  });

  test('full transaction lifecycle — create, edit, invite, tabs, advance', async ({ page }) => {
    test.setTimeout(60_000);

    // ── Transaction List ──
    await page.goto('/transactions');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('.app-shell-content h1')).toHaveText('Transactions');
    await screenshot(page, 'transactions-list-initial');

    // ── Create Transaction ──
    await page.getByRole('button', { name: '+ New Transaction' }).click();
    await pace();
    await screenshot(page, 'transactions-create-form');

    // Fill transaction name
    await page.locator('input[placeholder*="Transaction name"]').fill('123 Maple Drive Purchase');
    await page.getByRole('button', { name: 'Create' }).click();
    await page.waitForLoadState('networkidle');
    await pace(1500);

    // Wait for the transaction card to appear (Link with .txn-card class)
    const txnCard = page.locator('.txn-card').first();
    await expect(txnCard).toBeVisible({ timeout: 10000 });
    await screenshot(page, 'transactions-created');

    // ── Click into Transaction Detail ──
    await txnCard.click();
    await page.waitForLoadState('networkidle');
    await pace();

    // Verify we're on the detail page
    await expect(page.locator('.app-shell-content h1')).toContainText('123 Maple Drive', { timeout: 10000 });
    await screenshot(page, 'transaction-detail-landing');

    // ── Overview Tab — Edit Deal Info ──
    // The Edit button is a btn-link next to "Deal Information"
    const editBtn = page.locator('.section-header .btn-link', { hasText: 'Edit' });
    if (await editBtn.isVisible()) {
      await editBtn.click();
      await pace();
      await screenshot(page, 'transaction-overview-edit-mode');

      // Fill deal information in the form-grid
      await page.locator('.form-field').filter({ hasText: 'Purchase Price' }).locator('input').fill('525000');
      await page.locator('.form-field').filter({ hasText: 'Earnest Money' }).locator('input').fill('15000');
      await page.locator('.form-field').filter({ hasText: 'MLS Number' }).locator('input').fill('MLS-2025-4567');

      await screenshot(page, 'transaction-overview-filled');

      // Save
      await page.locator('.form-actions .btn-primary').click();
      await page.waitForLoadState('networkidle');
      await pace(1000);
      await screenshot(page, 'transaction-overview-saved');
    }

    // ── Invite a Participant ──
    const inviteForm = page.locator('.invite-form');
    if (await inviteForm.isVisible()) {
      await inviteForm.locator('input[type="email"]').fill('buyer@example.com');
      await inviteForm.locator('input[placeholder*="Name"]').fill('John Buyer');
      await inviteForm.locator('select').selectOption('BUYER');
      await screenshot(page, 'transaction-invite-form-filled');

      await inviteForm.locator('button[type="submit"]').click();
      await pace(2000);
      await screenshot(page, 'transaction-invite-sent');
    }

    // ── Documents Tab ──
    const docsTab = page.locator('.txn-tab', { hasText: 'Documents' });
    await docsTab.click();
    await pace();
    await screenshot(page, 'transaction-documents-tab');

    // ── Participants Tab ──
    const participantsTab = page.locator('.txn-tab', { hasText: 'Participants' });
    await participantsTab.click();
    await pace();
    await screenshot(page, 'transaction-participants-tab');

    // ── Compliance Tab ──
    const complianceTab = page.locator('.txn-tab', { hasText: 'Compliance' });
    await complianceTab.click();
    await pace();
    await screenshot(page, 'transaction-compliance-tab');

    // ── Back to Overview ──
    const overviewTab = page.locator('.txn-tab', { hasText: 'Overview' });
    await overviewTab.click();
    await pace();

    // ── Advance Status ──
    const advanceBtn = page.getByRole('button', { name: /Advance to/ });
    if (await advanceBtn.isVisible()) {
      await advanceBtn.click();
      await page.waitForLoadState('networkidle');
      await pace(1000);
      await screenshot(page, 'transaction-status-advanced');
    }

    // ── Auto-Fill from Profiles ──
    const autoFillBtn = page.getByRole('button', { name: 'Auto-Fill from Profiles' });
    if (await autoFillBtn.isVisible()) {
      await autoFillBtn.click();
      await pace(1500);
      await screenshot(page, 'transaction-auto-fill-result');
    }

    // ── Navigate back to list ──
    const backLink = page.locator('.back-link');
    if (await backLink.isVisible()) {
      await backLink.click();
      await page.waitForLoadState('networkidle');
      await pace();
      await screenshot(page, 'transactions-list-with-active');
    }
  });
});
