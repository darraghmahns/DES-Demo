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

  // If Clerk is not configured, redirect to dashboard (dev mode)
  if (!CLERK_ENABLED) {
    return <Navigate to="/dashboard" replace />;
  }

  // If already in demo mode, redirect to dashboard
  if (getDemoToken()) {
    return <Navigate to="/dashboard" replace />;
  }

  const handleTryDemo = async () => {
    setLoading(true);
    setError('');
    try {
      await startDemo();
      navigate('/dashboard');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start demo');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page-login">
      <div className="login-container">
        <h1>D.E.S.</h1>
        <p>Data Entry Sucks &mdash; Sign in to continue</p>
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
