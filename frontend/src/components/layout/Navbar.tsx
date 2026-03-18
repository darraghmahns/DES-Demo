import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Burger } from '@mantine/core';
import { SignedIn, SignedOut, SignIn, OrganizationSwitcher } from '@clerk/clerk-react';
import { useDemoAuth } from '../../hooks/useDemoAuth';
import { getProfile } from '../../api/profile';

const CLERK_ENABLED = !!import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

interface NavbarProps {
  onMenuToggle: () => void;
  drawerOpen: boolean;
}

export function Navbar({ onMenuToggle, drawerOpen }: NavbarProps) {
  const { isDemoMode, demoUser, exitDemo } = useDemoAuth();
  const [profileName, setProfileName] = useState<string | null>(null);

  useEffect(() => {
    if (!isDemoMode) return;
    const fetchName = () => {
      getProfile()
        .then(p => { if (p?.name) setProfileName(p.name); })
        .catch(() => {});
    };
    fetchName();
    window.addEventListener('profile-updated', fetchName);
    return () => window.removeEventListener('profile-updated', fetchName);
  }, [isDemoMode]);

  return (
    <nav className="navbar">
      <div className="navbar-left">
        <Burger
          opened={drawerOpen}
          onClick={onMenuToggle}
          size="sm"
          aria-label="Toggle navigation menu"
          hiddenFrom="sm"
        />
        <Link to="/" className="navbar-logo">
          <span className="navbar-logo-text">Comparari</span>
        </Link>
      </div>
      <div className="navbar-actions">
        {isDemoMode ? (
          <>
            <span className="navbar-demo-badge">Demo Mode</span>
            <span className="navbar-demo-user">{profileName || demoUser?.name || 'Demo User'}</span>
            <button className="demo-exit-btn" onClick={exitDemo}>
              Exit Demo
            </button>
          </>
        ) : CLERK_ENABLED ? (
          <>
            <SignedIn>
              <div className="navbar-org-switcher">
                <OrganizationSwitcher
                  appearance={{
                    elements: {
                      rootBox: { color: 'var(--mantine-color-text)' },
                      organizationSwitcherTrigger: { color: 'var(--mantine-color-text)' },
                    },
                  }}
                />
              </div>
            </SignedIn>
            <SignedOut>
              <SignIn
                routing="hash"
                appearance={{
                  elements: {
                    rootBox: { width: '100%' },
                    card: { background: 'var(--mantine-color-body)', border: '1px solid var(--mantine-color-default-border)' },
                  },
                }}
              />
            </SignedOut>
          </>
        ) : (
          <span className="navbar-dev-badge">Dev Mode</span>
        )}
      </div>
    </nav>
  );
}
