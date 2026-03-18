/** Step 6: Complete — summary + next steps. */

import { Link } from 'react-router-dom';
import type { OnboardingStepStatus } from '../../../api';

interface CompleteStepProps {
  steps: OnboardingStepStatus[];
  dotloopConnected: boolean;
  onFinish: () => void;
}

export function CompleteStep({
  steps,
  dotloopConnected,
  onFinish,
}: CompleteStepProps) {
  // Build summary of actionable steps (skip welcome and complete)
  const actionableSteps = steps.filter(
    (s) => s.step_id !== 'welcome' && s.step_id !== 'complete',
  );

  const stepLabels: Record<string, string> = {
    profile: 'Profile Setup',
    documents: 'Document Upload',
    extraction: 'Document Intelligence',
  };

  return (
    <div className="ob-step">
      <div className="ob-step-icon">&#x1F389;</div>
      <h2 className="ob-step-heading">You're All Set!</h2>
      <p className="ob-step-body">
        Great work! Here's a summary of your setup:
      </p>

      <div className="ob-summary">
        {actionableSteps.map((s) => (
          <div key={s.step_id} className="ob-summary-item">
            <span className={`ob-summary-badge ${s.status}`}>
              {s.status === 'completed' ? '✓' : '—'}
            </span>
            <span>{stepLabels[s.step_id] ?? s.step_id}</span>
            {s.status === 'skipped' && (
              <span className="ob-summary-skipped">skipped</span>
            )}
          </div>
        ))}
      </div>

      <div className="ob-next-steps">
        <h3 className="ob-next-steps-heading">Next Steps</h3>
        {!dotloopConnected && (
          <Link to="/profile" className="ob-next-steps-card" onClick={onFinish}>
            <span className="ob-next-steps-icon">&#x1F517;</span>
            <span>Connect Dotloop</span>
          </Link>
        )}
        <Link to="/transactions" className="ob-next-steps-card" onClick={onFinish}>
          <span className="ob-next-steps-icon">&#x1F4BC;</span>
          <span>Create Your First Transaction</span>
        </Link>
      </div>

      <div className="ob-step-actions">
        <button className="ob-btn primary" onClick={onFinish}>
          Go to Transactions
        </button>
      </div>
    </div>
  );
}
