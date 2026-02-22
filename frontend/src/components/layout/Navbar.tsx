import { Link } from 'react-router-dom';
import { SignedIn, SignedOut, SignIn, UserButton, OrganizationSwitcher } from '@clerk/clerk-react';

const CLERK_ENABLED = !!import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

interface NavbarProps {
  onMenuToggle: () => void;
}

export function Navbar({ onMenuToggle }: NavbarProps) {
  return (
    <nav className="navbar">
      <div className="navbar-left">
        <button
          className="navbar-hamburger"
          onClick={onMenuToggle}
          aria-label="Toggle navigation menu"
        >
          <span className="hamburger-line" />
          <span className="hamburger-line" />
          <span className="hamburger-line" />
        </button>
        <Link to="/" className="navbar-logo">
          <span className="navbar-logo-text">D.E.S.</span>
          <span className="navbar-logo-sub">Data Entry Sucks</span>
        </Link>
      </div>
      <div className="navbar-actions">
        {CLERK_ENABLED ? (
          <>
            <SignedIn>
              <div className="navbar-org-switcher">
                <OrganizationSwitcher
                  appearance={{
                    elements: {
                      rootBox: { color: '#e0e0e0' },
                      organizationSwitcherTrigger: { color: '#e0e0e0' },
                    },
                  }}
                />
              </div>
              <UserButton
                appearance={{
                  elements: {
                    avatarBox: { width: 32, height: 32 },
                  },
                }}
              />
            </SignedIn>
            <SignedOut>
              <SignIn
                routing="hash"
                appearance={{
                  elements: {
                    rootBox: { width: '100%' },
                    card: { background: '#1a1a2e', border: '1px solid #333' },
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
