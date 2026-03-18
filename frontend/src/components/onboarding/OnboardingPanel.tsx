/** Docked side panel that displays onboarding step content. */

import type { OnboardingStepId, OnboardingStepStatus } from '../../api';
import { OnboardingProgress } from './OnboardingProgress';
import { WelcomeStep } from './steps/WelcomeStep';
import { ProfileStep } from './steps/ProfileStep';
import { DocumentsStep } from './steps/DocumentsStep';
import { ExtractionStep } from './steps/ExtractionStep';
import { CompleteStep } from './steps/CompleteStep';
import './OnboardingPanel.css';

interface OnboardingPanelProps {
  currentStep: OnboardingStepId;
  currentIndex: number;
  steps: OnboardingStepStatus[];
  dotloopConnected: boolean;
  onAdvance: () => void;
  onSkip: () => void;
  onDismiss: () => void;
  onFinish: () => void;
}

export function OnboardingPanel({
  currentStep,
  currentIndex,
  steps,
  dotloopConnected,
  onAdvance,
  onSkip,
  onDismiss,
  onFinish,
}: OnboardingPanelProps) {
  return (
    <aside className="ob-panel" role="complementary" aria-label="Setup guide">
      <div className="ob-panel-header">
        <span className="ob-panel-title">Setup Guide</span>
        <button
          className="ob-panel-minimize"
          onClick={onDismiss}
          title="Minimize"
          aria-label="Minimize setup guide"
        >
          X
        </button>
      </div>

      {steps.length > 0 && (
        <OnboardingProgress steps={steps} currentIndex={currentIndex} />
      )}

      <div className="ob-panel-content">
        {currentStep === 'welcome' && (
          <WelcomeStep onNext={onAdvance} />
        )}
        {currentStep === 'profile' && (
          <ProfileStep onNext={onAdvance} onSkip={onSkip} />
        )}
        {currentStep === 'documents' && (
          <DocumentsStep onNext={onAdvance} onSkip={onSkip} />
        )}
        {currentStep === 'extraction' && (
          <ExtractionStep onNext={onAdvance} onSkip={onSkip} />
        )}
        {currentStep === 'complete' && (
          <CompleteStep
            steps={steps}
            dotloopConnected={dotloopConnected}
            onFinish={onFinish}
          />
        )}
      </div>
    </aside>
  );
}
