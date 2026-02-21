/** Step 3: AI Chat — introduce the AI profile builder. */

interface AIChatStepProps {
  onNext: () => void;
  onSkip: () => void;
}

export function AIChatStep({ onNext, onSkip }: AIChatStepProps) {
  return (
    <div className="ob-step">
      <div className="ob-step-icon">&#x1F4AC;</div>
      <h2 className="ob-step-heading">Meet Your AI Assistant</h2>
      <p className="ob-step-body">
        Don't want to fill out forms? Switch to <strong>Chat View</strong> on
        the profile page and tell the AI about yourself. It'll extract your
        details and build your profile conversationally.
      </p>
      <div className="ob-step-tip">
        <span className="ob-step-tip-label">Try saying:</span>
        <em>"I'm a real estate agent in Denver, CO with license #FA.100098765"</em>
      </div>
      <div className="ob-step-actions">
        <button className="ob-btn text" onClick={onSkip}>
          Skip for now
        </button>
        <button className="ob-btn primary" onClick={onNext}>
          Continue
        </button>
      </div>
    </div>
  );
}
