/** DemoAuthProvider — manages demo session lifecycle via magic-link tokens. */

import { useState, useCallback, useEffect, type ReactNode } from 'react';
import {
  DemoAuthContext,
  getDemoToken,
  getDemoUser,
  setDemoStorage,
  clearDemoStorage,
} from '../hooks/useDemoAuth';
import { setAuthTokenProvider } from '../api';
import { setAuthTokenProvider as setClientAuthTokenProvider } from '../api/client';

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000';

function wireDemoToken(token: string) {
  const provider = () => Promise.resolve(token);
  setAuthTokenProvider(provider);
  setClientAuthTokenProvider(provider);
}

function clearAuthProviders() {
  setAuthTokenProvider(() => Promise.resolve(null));
  setClientAuthTokenProvider(() => Promise.resolve(null));
}

export function DemoAuthProvider({ children }: { children: ReactNode }) {
  const [isDemoMode, setIsDemoMode] = useState(() => !!getDemoToken());
  const [demoUser, setDemoUser] = useState(() => getDemoUser());

  // Wire the demo token into API clients on mount (if resuming a session)
  useEffect(() => {
    if (isDemoMode) {
      const token = getDemoToken();
      if (token) wireDemoToken(token);
    }
  }, [isDemoMode]);

  const startDemo = useCallback(async () => {
    const resp = await fetch(`${API_BASE}/api/auth/demo-login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: 'Demo login failed' }));
      throw new Error(err.detail || 'Demo login failed');
    }
    const data = await resp.json();
    const user = { email: data.email, name: data.name };

    setDemoStorage(data.demo_token, user);
    wireDemoToken(data.demo_token);
    setIsDemoMode(true);
    setDemoUser(user);
  }, []);

  const exitDemo = useCallback(() => {
    clearDemoStorage();
    clearAuthProviders();
    setIsDemoMode(false);
    setDemoUser(null);
    window.location.href = '/login';
  }, []);

  return (
    <DemoAuthContext.Provider value={{ isDemoMode, demoUser, startDemo, exitDemo }}>
      {children}
    </DemoAuthContext.Provider>
  );
}
