import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useEffect } from 'react';
import { useAuth } from '@clerk/clerk-react';
import { setAuthTokenProvider } from './api';

import { AppShell } from './components/layout/AppShell';
import { ProtectedRoute } from './components/layout/ProtectedRoute';

import { Dashboard } from './pages/Dashboard';
import { ExtractionPage } from './pages/Extraction';
import { Profile } from './pages/Profile';
import { ProfileDocuments } from './pages/ProfileDocuments';
import { TransactionList } from './pages/TransactionList';
import { TransactionDetail } from './pages/TransactionDetail';
import { InviteLanding } from './pages/InviteLanding';
import { Login } from './pages/Login';

const CLERK_ENABLED = !!import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

/** Wires Clerk auth token into the API client. */
function AuthTokenWiring() {
  const { getToken } = useAuth();
  useEffect(() => {
    setAuthTokenProvider(() => getToken());
  }, [getToken]);
  return null;
}

function App() {
  return (
    <BrowserRouter>
      {CLERK_ENABLED && <AuthTokenWiring />}
      <Routes>
        {/* Public routes */}
        <Route path="/login" element={<Login />} />
        <Route path="/invite/:token" element={<InviteLanding />} />

        {/* Protected routes inside AppShell layout */}
        <Route
          element={
            <ProtectedRoute>
              <AppShell />
            </ProtectedRoute>
          }
        >
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/extraction" element={<ExtractionPage />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/profile/documents" element={<ProfileDocuments />} />
          <Route path="/transactions" element={<TransactionList />} />
          <Route path="/transactions/:id" element={<TransactionDetail />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
