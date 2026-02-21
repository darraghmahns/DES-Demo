/** Orchestrates the onboarding guided tour — navigates to pages and renders the side panel. */

import { useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useOnboarding, ONBOARDING_STEPS } from '../../hooks/useOnboarding';
import { OnboardingProvider } from '../../context/OnboardingContext';
import { OnboardingPanel } from './OnboardingPanel';

interface OnboardingOrchestratorProps {
  children: React.ReactNode;
}

export function OnboardingOrchestrator({ children }: OnboardingOrchestratorProps) {
  const navigate = useNavigate();
  const location = useLocation();

  const {
    isOnboarding,
    currentStep,
    currentStepIndex,
    steps,
    panelOpen,
    loading,
    dotloopConnected,
    docusignConnected,
    advanceStep,
    skipStep,
    dismissPanel,
    openPanel,
    markStepAction,
  } = useOnboarding();

  // Navigate to the correct page when step changes
  useEffect(() => {
    if (!isOnboarding || !panelOpen || loading) return;

    const targetRoute = ONBOARDING_STEPS[currentStepIndex]?.route;
    if (targetRoute && location.pathname !== targetRoute) {
      navigate(targetRoute);
    }
  }, [isOnboarding, panelOpen, currentStepIndex, loading, location.pathname, navigate]);

  // Handle final completion — navigate to dashboard and advance
  const handleFinish = async () => {
    await advanceStep(); // marks 'complete' step as completed
    navigate('/dashboard');
  };

  // Context value for consuming pages
  const contextValue = {
    isOnboarding,
    currentStep,
    markStepAction,
  };

  return (
    <OnboardingProvider value={contextValue}>
      <div
        className="ob-layout"
        style={{
          marginRight: isOnboarding && panelOpen ? 320 : 0,
          transition: 'margin-right 0.3s ease',
        }}
      >
        {children}
      </div>

      {isOnboarding && panelOpen && currentStep && (
        <OnboardingPanel
          currentStep={currentStep}
          currentIndex={currentStepIndex}
          steps={steps}
          dotloopConnected={dotloopConnected}
          docusignConnected={docusignConnected}
          onAdvance={advanceStep}
          onSkip={skipStep}
          onDismiss={dismissPanel}
          onFinish={handleFinish}
        />
      )}

      {/* Floating reopen button when panel is dismissed but onboarding is active */}
      {isOnboarding && !panelOpen && (
        <button
          className="ob-reopen-btn"
          onClick={openPanel}
          title="Resume setup guide"
          aria-label="Resume setup guide"
        >
          ?
        </button>
      )}
    </OnboardingProvider>
  );
}
