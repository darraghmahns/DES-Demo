/** Step 1: Welcome — intro text + "Let's Get Started" */

interface WelcomeStepProps {
  onNext: () => void;
}

export function WelcomeStep({ onNext }: WelcomeStepProps) {
  return (
    <div className="ob-step">
      <div className="ob-step-icon">&#x1F44B;</div>
      <h2 className="ob-step-title">Welcome to JGP</h2>
      <p className="ob-step-subtitle">Julie Gardner Properties</p>
      <p className="ob-step-body">
        JGP uses AI to extract structured data from real estate documents,
        manage transactions, and keep your deals organized. Let's walk you
        through the key features.
      </p>
      <div className="ob-step-actions">
        <button className="ob-btn primary" onClick={onNext}>
          Let's Get Started
        </button>
      </div>
    </div>
  );
}
