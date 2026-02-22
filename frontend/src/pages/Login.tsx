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
              card: {
                background: '#ffffff',
                border: '1px solid #e0e0e0',
                borderRadius: '12px',
                boxShadow: '0 4px 24px rgba(0,0,0,0.4)',
              },
              headerTitle: { color: '#1a1a2e' },
              headerSubtitle: { color: '#555' },
              socialButtonsBlockButton: {
                border: '1px solid #d0d0d0',
                background: '#f8f9fa',
                color: '#333',
              },
              socialButtonsBlockButtonText: { color: '#333' },
              dividerLine: { background: '#d0d0d0' },
              dividerText: { color: '#888' },
              formFieldLabel: { color: '#555' },
              formFieldInput: {
                background: '#fff',
                border: '1px solid #d0d0d0',
                color: '#1a1a2e',
              },
              formButtonPrimary: {
                background: '#58a6ff',
                color: '#fff',
              },
              footerActionText: { color: '#555' },
              footerActionLink: { color: '#58a6ff' },
            },
          }}
        />
      </div>
    </div>
  );
}
