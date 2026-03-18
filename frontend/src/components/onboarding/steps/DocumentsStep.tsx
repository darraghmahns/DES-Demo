/** Step 4: Documents — guidance for uploading personal supporting docs. */

interface DocumentsStepProps {
  onNext: () => void;
  onSkip: () => void;
}

export function DocumentsStep({ onNext, onSkip }: DocumentsStepProps) {
  return (
    <div className="ob-step">
      <div className="ob-step-icon">&#x1F4C1;</div>
      <h2 className="ob-step-heading">Upload Your Documents</h2>
      <p className="ob-step-body">
        Upload your supporting documents — pre-approval letters, bank
        statements, pay stubs, and more. Comparari will automatically extract
        and organize the data for your transactions.
      </p>
      <ul className="ob-step-checklist">
        <li>Select a document type from the dropdown</li>
        <li>Upload a PDF or image</li>
        <li>View auto-extracted data on each card</li>
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
