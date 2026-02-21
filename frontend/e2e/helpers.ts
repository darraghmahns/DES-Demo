/** Shared E2E test helpers. */

import { type Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

export const API_BASE = 'http://localhost:8000';
export const APP_BASE = 'http://localhost:5173';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SCREENSHOT_DIR = path.join(__dirname, 'screenshots');
let screenshotCounter = 0;

/** Reset the global screenshot counter (call at the start of each spec). */
export function resetScreenshotCounter() {
  screenshotCounter = 0;
}

/** Take a named screenshot, saved to e2e/screenshots/ with auto-incrementing prefix. */
export async function screenshot(page: Page, name: string) {
  if (!fs.existsSync(SCREENSHOT_DIR)) {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  }
  screenshotCounter++;
  const filename = `${String(screenshotCounter).padStart(2, '0')}-${name}.png`;
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, filename), fullPage: true });
}

/** Direct API GET helper (bypasses frontend, used for setup/teardown). */
export async function apiGet<T = unknown>(endpoint: string): Promise<T> {
  const res = await fetch(`${API_BASE}${endpoint}`);
  if (!res.ok) throw new Error(`API GET ${endpoint}: ${res.status}`);
  return res.json() as Promise<T>;
}

/** Direct API POST helper. */
export async function apiPost<T = unknown>(endpoint: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API POST ${endpoint}: ${res.status} — ${text}`);
  }
  return res.json() as Promise<T>;
}

/** Direct API PUT helper. */
export async function apiPut<T = unknown>(endpoint: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`API PUT ${endpoint}: ${res.status}`);
  return res.json() as Promise<T>;
}

/** Direct API DELETE helper. */
export async function apiDelete(endpoint: string): Promise<void> {
  const res = await fetch(`${API_BASE}${endpoint}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`API DELETE ${endpoint}: ${res.status}`);
}

/** Check that the backend API is reachable. */
export async function waitForAPI(retries = 10, delayMs = 1000): Promise<void> {
  for (let i = 0; i < retries; i++) {
    try {
      const res = await fetch(`${API_BASE}/api/profile`);
      if (res.ok || res.status === 401) return; // server is up
    } catch {
      // not ready yet
    }
    await new Promise(r => setTimeout(r, delayMs));
  }
  throw new Error('Backend API not reachable after retries');
}

/** Reset the dev user's profile to a clean state for testing. */
export async function resetTestUser(): Promise<void> {
  try {
    // Reset shared fields to blank
    await apiPut('/api/profile', { name: '', phone: null, address: null });

    // Remove all roles
    const profile = await apiGet<{ user_types: string[] }>('/api/profile');
    for (const role of profile.user_types) {
      try {
        await apiDelete(`/api/profile/roles/${role}`);
      } catch {
        // ignore — role might already be removed
      }
    }
  } catch {
    // Backend might not be running yet — that's ok for setup
  }
}

/** Clean up test transactions. */
export async function cleanupTransactions(): Promise<void> {
  try {
    const txns = await apiGet<Array<{ _id: string; status: string }>>('/api/transactions');
    for (const txn of txns) {
      if (txn.status === 'draft') {
        try {
          await apiDelete(`/api/transactions/${txn._id}`);
        } catch {
          // ignore
        }
      }
    }
  } catch {
    // ignore
  }
}

/** Clean up all uploaded documents for the dev user. */
export async function cleanupDocuments(): Promise<void> {
  try {
    const docs = await apiGet<Array<{ _id: string }>>('/api/profile/documents');
    for (const doc of docs) {
      try {
        await apiDelete(`/api/profile/documents/${doc._id}`);
      } catch {
        // ignore
      }
    }
  } catch {
    // ignore
  }
}

/** Short delay for visual pacing in headed mode. */
export async function pace(ms = 500): Promise<void> {
  await new Promise(r => setTimeout(r, ms));
}
