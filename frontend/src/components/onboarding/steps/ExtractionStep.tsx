/** Step 4: Extraction - guidance for starting a transaction workflow. */

interface ExtractionStepProps {
  onNext: () => void;
  onSkip: () => void;
}

export function ExtractionStep({ onNext, onSkip }: ExtractionStepProps) {
  return (
    <div className="ob-step">
      <div className="ob-step-icon">04</div>
      <h2 className="ob-step-heading">Start Your First Transaction</h2>
      <p className="ob-step-body">
        Create a transaction from the Transactions page, then open it and use
        the Documents tab to upload a purchase agreement, listing contract, or
        disclosure. Comparari will extract the deal data inside the transaction
        workspace.
      </p>
      <ul className="ob-step-checklist">
        <li>Create a new transaction</li>
        <li>Open the transaction and go to Documents</li>
        <li>Upload a deal document and review the extracted data</li>
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
