import { Link } from 'react-router-dom';
import { SignedIn, SignedOut, SignIn, UserButton, OrganizationSwitcher } from '@clerk/clerk-react';

const CLERK_ENABLED = !!import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

export function Navbar() {
  return (
    <nav className="navbar">
      <div className="navbar-brand">
        <Link to="/" className="navbar-logo">
          <span className="navbar-logo-text">D.E.S.</span>
          <span className="navbar-logo-sub">Data Entry Sucks</span>
        </Link>
      </div>
      <div className="navbar-actions">
        {CLERK_ENABLED ? (
          <>
            <SignedIn>
              <OrganizationSwitcher
                appearance={{
                  elements: {
                    rootBox: { color: '#e0e0e0' },
                    organizationSwitcherTrigger: { color: '#e0e0e0' },
                  },
                }}
              />
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
