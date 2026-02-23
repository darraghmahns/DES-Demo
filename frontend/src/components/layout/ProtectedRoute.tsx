import { Navigate } from 'react-router-dom';
import { SignedIn, SignedOut } from '@clerk/clerk-react';
import { getDemoToken } from '../../hooks/useDemoAuth';

const CLERK_ENABLED = !!import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

interface ProtectedRouteProps {
  children: React.ReactNode;
}

export function ProtectedRoute({ children }: ProtectedRouteProps) {
  // If Clerk is not configured, allow all access (dev mode)
  if (!CLERK_ENABLED) {
    return <>{children}</>;
  }

  // If in demo mode, allow access (authenticated via magic link token)
  if (getDemoToken()) {
    return <>{children}</>;
  }

  return (
    <>
      <SignedIn>{children}</SignedIn>
      <SignedOut>
        <Navigate to="/login" replace />
      </SignedOut>
    </>
  );
}
