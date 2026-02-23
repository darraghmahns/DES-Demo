/** Demo authentication hook — manages @deslabs.local demo sessions. */

import { createContext, useContext } from 'react';

const DEMO_TOKEN_KEY = 'des_demo_token';
const DEMO_USER_KEY = 'des_demo_user';

export interface DemoUser {
  email: string;
  name: string;
}

export interface DemoAuthContextValue {
  isDemoMode: boolean;
  demoUser: DemoUser | null;
  startDemo: () => Promise<void>;
  exitDemo: () => void;
}

export const DemoAuthContext = createContext<DemoAuthContextValue>({
  isDemoMode: false,
  demoUser: null,
  startDemo: async () => {},
  exitDemo: () => {},
});

export function useDemoAuth() {
  return useContext(DemoAuthContext);
}

// localStorage helpers (synchronous — safe for route guards)

export function getDemoToken(): string | null {
  try {
    return localStorage.getItem(DEMO_TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setDemoStorage(token: string, user: DemoUser): void {
  localStorage.setItem(DEMO_TOKEN_KEY, token);
  localStorage.setItem(DEMO_USER_KEY, JSON.stringify(user));
}

export function clearDemoStorage(): void {
  localStorage.removeItem(DEMO_TOKEN_KEY);
  localStorage.removeItem(DEMO_USER_KEY);
}

export function getDemoUser(): DemoUser | null {
  try {
    const raw = localStorage.getItem(DEMO_USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}
