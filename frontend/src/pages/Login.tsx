import { SignIn } from '@clerk/clerk-react';
import { Navigate } from 'react-router-dom';

const CLERK_ENABLED = !!import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

export function Login() {
  // If Clerk is not configured, redirect to dashboard (dev mode)
  if (!CLERK_ENABLED) {
    return <Navigate to="/dashboard" replace />;
  }

  return (
    <div className="page-login">
      <div className="login-container">
        <h1>D.E.S.</h1>
        <p>Data Entry Sucks — Sign in to continue</p>
        <SignIn
          routing="hash"
          appearance={{
            elements: {
              rootBox: { width: '100%', maxWidth: 400 },
              card: { background: '#1a1a2e', border: '1px solid #333' },
            },
          }}
        />
      </div>
    </div>
  );
}
