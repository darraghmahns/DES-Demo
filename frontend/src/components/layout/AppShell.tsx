import { useState, useEffect, useCallback } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { Navbar } from './Navbar';
import { Sidebar } from './Sidebar';
import { OnboardingOrchestrator } from '../onboarding/OnboardingOrchestrator';

export function AppShell() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const location = useLocation();

  // Close drawer on route change
  useEffect(() => {
    setDrawerOpen(false);
  }, [location.pathname]);

  // Scroll lock when drawer is open
  useEffect(() => {
    if (drawerOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => { document.body.style.overflow = ''; };
  }, [drawerOpen]);

  const toggleDrawer = useCallback(() => setDrawerOpen(prev => !prev), []);
  const closeDrawer = useCallback(() => setDrawerOpen(false), []);

  return (
    <OnboardingOrchestrator onMobileNavOpen={drawerOpen} onMobileNavClose={closeDrawer}>
      <div className="app-shell">
        <Navbar onMenuToggle={toggleDrawer} />
        <div className="app-shell-body">
          <Sidebar open={drawerOpen} onClose={closeDrawer} />
          <main className="app-shell-content">
            <Outlet />
          </main>
        </div>
      </div>
    </OnboardingOrchestrator>
  );
}
