import { Outlet } from 'react-router-dom';
import { Navbar } from './Navbar';
import { Sidebar } from './Sidebar';
import { OnboardingOrchestrator } from '../onboarding/OnboardingOrchestrator';

export function AppShell() {
  return (
    <OnboardingOrchestrator>
      <div className="app-shell">
        <Navbar />
        <div className="app-shell-body">
          <Sidebar />
          <main className="app-shell-content">
            <Outlet />
          </main>
        </div>
      </div>
    </OnboardingOrchestrator>
  );
}
