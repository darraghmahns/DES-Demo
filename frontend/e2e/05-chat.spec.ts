/** E2E Demo: AI Chat Profile Builder — conversational profile completion.
 *
 * This test requires OPENAI_API_KEY to be set in the backend environment.
 * It will gracefully skip if the chat endpoint returns an error.
 */

import { test, expect } from '@playwright/test';
import { screenshot, resetScreenshotCounter, waitForAPI, pace, API_BASE } from './helpers';

test.describe('AI Chat Profile Builder', () => {
  let chatAvailable = true;

  test.beforeAll(async () => {
    await waitForAPI();

    // Probe the chat endpoint to see if OpenAI is configured
    try {
      const res = await fetch(`${API_BASE}/api/profile/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: 'hello' }),
      });
      if (!res.ok) {
        chatAvailable = false;
      }
    } catch {
      chatAvailable = false;
    }
  });

  test.beforeEach(() => {
    resetScreenshotCounter();
  });

  test('chat interface walkthrough', async ({ page }) => {
    if (!chatAvailable) {
      test.skip(true, 'Chat API not available (OPENAI_API_KEY may not be set)');
      return;
    }

    // ── Navigate to Profile and toggle to Chat ──
    await page.goto('/profile');
    await page.waitForLoadState('networkidle');

    const chatToggle = page.getByRole('button', { name: 'AI Chat' });
    await expect(chatToggle).toBeVisible();
    await chatToggle.click();
    await pace();

    // ── Welcome State ──
    await expect(page.locator('.chat-welcome')).toBeVisible();
    await screenshot(page, 'chat-welcome');

    // ── Click a suggestion button ──
    const suggestion = page.locator('.suggestion-btn').first();
    if (await suggestion.isVisible()) {
      const suggestionText = await suggestion.textContent();
      await suggestion.click();

      // Wait for AI response (generous timeout for OpenAI)
      await page.waitForSelector('.chat-message.assistant', { timeout: 30000 });
      await pace(1000);
      await screenshot(page, 'chat-first-response');
    }

    // ── Send a typed message ──
    const chatInput = page.locator('.chat-input input, .chat-input textarea');
    if (await chatInput.isVisible()) {
      await chatInput.fill('My license number is AG-99999 and I work at Summit Realty');
      await screenshot(page, 'chat-typed-message');

      const sendBtn = page.getByRole('button', { name: 'Send' });
      await sendBtn.click();

      // Wait for response
      await page.waitForSelector('.chat-message.assistant:nth-child(4)', { timeout: 30000 }).catch(() => {});
      await pace(1000);
      await screenshot(page, 'chat-second-response');

      // Check for extracted field chips
      const fieldChips = page.locator('.extracted-field-chip, .field-chip');
      if (await fieldChips.first().isVisible().catch(() => false)) {
        await screenshot(page, 'chat-extracted-fields');
      }
    }

    // ── Send another message with buyer info ──
    const chatInputAgain = page.locator('.chat-input input, .chat-input textarea');
    if (await chatInputAgain.isVisible()) {
      await chatInputAgain.fill("I'm also a buyer with a $500k pre-approval from First National");
      const sendBtn = page.getByRole('button', { name: 'Send' });
      await sendBtn.click();

      await page.waitForSelector('.chat-message.assistant:nth-child(6)', { timeout: 30000 }).catch(() => {});
      await pace(1000);
      await screenshot(page, 'chat-buyer-response');
    }

    // ── New Chat ──
    const newChatBtn = page.getByRole('button', { name: 'New Chat' });
    if (await newChatBtn.isVisible()) {
      await newChatBtn.click();
      await pace();
      // Welcome screen should reappear
      await screenshot(page, 'chat-reset');
    }

    // ── Switch back to Form View ──
    await page.getByRole('button', { name: 'Form View' }).click();
    await pace();
    await screenshot(page, 'chat-back-to-form');
  });
});
