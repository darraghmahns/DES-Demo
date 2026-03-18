/** Step 5: Extraction — guidance for trying AI document intelligence. */

interface ExtractionStepProps {
  onNext: () => void;
  onSkip: () => void;
}

export function ExtractionStep({ onNext, onSkip }: ExtractionStepProps) {
  return (
    <div className="ob-step">
      <div className="ob-step-icon">&#x1F9E0;</div>
      <h2 className="ob-step-heading">Try Document Intelligence</h2>
      <p className="ob-step-body">
        Upload a real estate document — a purchase agreement, listing contract,
        or disclosure — and watch Comparari extract structured data with
        AI-powered intelligence.
      </p>
      <ul className="ob-step-checklist">
        <li>Upload a PDF in the left panel</li>
        <li>Click "Extract" to start AI analysis</li>
        <li>Review extracted fields, citations, and compliance</li>
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
