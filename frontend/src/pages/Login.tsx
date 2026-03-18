import { SignIn } from '@clerk/clerk-react';
import { Navigate, useNavigate } from 'react-router-dom';
import { useState } from 'react';
import { useDemoAuth, getDemoToken } from '../hooks/useDemoAuth';

const CLERK_ENABLED = !!import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

export function Login() {
  const navigate = useNavigate();
  const { startDemo } = useDemoAuth();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // If Clerk is not configured, redirect to transactions (dev mode)
  if (!CLERK_ENABLED) {
    return <Navigate to="/transactions" replace />;
  }

  // If already in demo mode, redirect to transactions
  if (getDemoToken()) {
    return <Navigate to="/transactions" replace />;
  }

  const handleTryDemo = async () => {
    setLoading(true);
    setError('');
    try {
      await startDemo();
      navigate('/transactions');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start demo');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page-login">
      <div className="login-container">
        <h1>Comparari</h1>
        <p>Sign in to continue</p>
        <SignIn
          routing="hash"
          appearance={{
            elements: {
              rootBox: { width: '100%', maxWidth: 400 },
              card: {
                background: 'var(--mantine-color-body)',
                border: '1px solid var(--mantine-color-default-border)',
                borderRadius: '12px',
                boxShadow: '0 4px 24px rgba(0,0,0,0.4)',
              },
              headerTitle: { color: 'var(--mantine-color-text)' },
              headerSubtitle: { color: 'var(--mantine-color-dimmed)' },
              socialButtonsBlockButton: {
                border: '1px solid var(--mantine-color-default-border)',
                background: 'var(--mantine-color-default)',
                color: 'var(--mantine-color-text)',
              },
              socialButtonsBlockButtonText: { color: 'var(--mantine-color-text)' },
              dividerLine: { background: 'var(--mantine-color-default-border)' },
              dividerText: { color: 'var(--mantine-color-dimmed)' },
              formFieldLabel: { color: 'var(--mantine-color-text)' },
              formFieldInput: {
                background: 'var(--mantine-color-default)',
                border: '1px solid var(--mantine-color-default-border)',
                color: 'var(--mantine-color-text)',
              },
              formButtonPrimary: {
                background: 'var(--mantine-primary-color-filled)',
                color: 'var(--mantine-primary-color-filled-hover)',
              },
              footerActionText: { color: 'var(--mantine-color-dimmed)' },
              footerActionLink: { color: 'var(--mantine-primary-color-filled)' },
            },
          }}
        />
        <div className="login-divider">
          <span>or</span>
        </div>
        <button
          className="demo-login-btn"
          onClick={handleTryDemo}
          disabled={loading}
        >
          {loading ? 'Starting Demo...' : 'Try Demo'}
        </button>
        {error && <p className="demo-login-error">{error}</p>}
        <p className="demo-login-hint">
          Explore the app with sample data &mdash; no account needed
        </p>
      </div>
    </div>
  );
}
