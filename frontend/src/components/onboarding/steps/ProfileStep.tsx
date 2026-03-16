/** Step 2: Profile — guidance for filling profile on the real /profile page. */

interface ProfileStepProps {
  onNext: () => void;
  onSkip: () => void;
}

export function ProfileStep({ onNext, onSkip }: ProfileStepProps) {
  return (
    <div className="ob-step">
      <div className="ob-step-icon">&#x1F464;</div>
      <h2 className="ob-step-heading">Set Up Your Profile</h2>
      <p className="ob-step-body">
        Fill in your basic information and select your role. This helps JGP
        tailor your experience and auto-fill transaction documents.
      </p>
      <ul className="ob-step-checklist">
        <li>Enter your name and contact info</li>
        <li>Select at least one role (Agent, Buyer, Seller, Loan Officer)</li>
        <li>Fill role-specific details</li>
      </ul>
      <div className="ob-step-actions">
        <button className="ob-btn text" onClick={onSkip}>
          Skip for now
        </button>
        <button className="ob-btn primary" onClick={onNext}>
          Next
        </button>
      </div>
    </div>
  );
}
