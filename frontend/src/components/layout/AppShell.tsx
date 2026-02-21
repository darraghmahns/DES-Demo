import { useState, useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import { Navbar } from './Navbar';
import { Sidebar } from './Sidebar';
import {
  fetchOnboardingStatus,
  completeOnboarding,
  checkDotloopStatus,
  checkDocuSignStatus,
} from '../../api';
import OnboardingWizard from '../OnboardingWizard';

export function AppShell() {
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [dotloopConnected, setDotloopConnected] = useState(false);
  const [docusignConnected, setDocusignConnected] = useState(false);

  useEffect(() => {
    // Check onboarding status on mount
    fetchOnboardingStatus().then((status) => {
      if (!status.completed) {
        setShowOnboarding(true);
      }
      setDotloopConnected(status.dotloop_connected);
      setDocusignConnected(status.docusign_connected);
    });

    // Also check integration status directly
    checkDotloopStatus().then(setDotloopConnected);
    checkDocuSignStatus().then(setDocusignConnected);

    // Handle OAuth redirect survival
    const params = new URLSearchParams(window.location.search);
    if (params.get('dotloop_connected') === 'true' || params.get('docusign_connected') === 'true') {
      fetchOnboardingStatus().then((status) => {
        if (!status.completed) {
          setShowOnboarding(true);
        }
      });
    }
  }, []);

  async function handleOnboardingComplete(skippedSteps: string[]) {
    await completeOnboarding(skippedSteps);
    setShowOnboarding(false);
    // Refresh integration status
    checkDotloopStatus().then(setDotloopConnected);
    checkDocuSignStatus().then(setDocusignConnected);
  }

  function handleOnboardingFileUploaded(_fileName: string) {
    // In the router-based architecture, individual pages manage their own state.
    // The uploaded file will appear when the user navigates to the extraction page.
  }

  return (
    <div className="app-shell">
      {showOnboarding && (
        <OnboardingWizard
          dotloopConnected={dotloopConnected}
          docusignConnected={docusignConnected}
          onComplete={handleOnboardingComplete}
          onFileUploaded={handleOnboardingFileUploaded}
        />
      )}
      <Navbar />
      <div className="app-shell-body">
        <Sidebar />
        <main className="app-shell-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
