/** Horizontal step progress indicator for the onboarding panel. */

import type { OnboardingStepStatus } from '../../api';

interface OnboardingProgressProps {
  steps: OnboardingStepStatus[];
  currentIndex: number;
}

export function OnboardingProgress({ steps, currentIndex }: OnboardingProgressProps) {
  return (
    <div className="ob-progress">
      {steps.map((step, i) => {
        let cls = 'ob-progress-dot';
        if (i === currentIndex) cls += ' active';
        if (step.status === 'completed') cls += ' completed';
        if (step.status === 'skipped') cls += ' skipped';
        return <span key={step.step_id} className={cls} title={step.step_id} />;
      })}
    </div>
  );
}
