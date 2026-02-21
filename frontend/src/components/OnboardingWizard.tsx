import { useState, useRef, useEffect } from 'react';
import { getDotloopConnectUrl, getDocuSignConnectUrl, uploadFile } from '../api';
import './OnboardingWizard.css';

const STEP_KEY = 'des_onboarding_step';

interface OnboardingWizardProps {
  dotloopConnected: boolean;
  docusignConnected: boolean;
  onComplete: (skippedSteps: string[]) => void;
  onFileUploaded: (fileName: string) => void;
}

type WizardStep = 'welcome' | 'integrations' | 'extraction' | 'done';
const STEPS: WizardStep[] = ['welcome', 'integrations', 'extraction', 'done'];

export default function OnboardingWizard({
  dotloopConnected,
  docusignConnected,
  onComplete,
  onFileUploaded,
}: OnboardingWizardProps) {
  const savedStep = localStorage.getItem(STEP_KEY);
  const initialIdx = savedStep ? Math.min(Number(savedStep), STEPS.length - 1) : 0;
  const [stepIdx, setStepIdx] = useState(initialIdx);
  const [skippedSteps, setSkippedSteps] = useState<string[]>([]);
  const [uploadState, setUploadState] = useState<'idle' | 'uploading' | 'done' | 'error'>('idle');
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadedFileName, setUploadedFileName] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const step = STEPS[stepIdx];

  useEffect(() => {
    localStorage.setItem(STEP_KEY, String(stepIdx));
  }, [stepIdx]);

  function goNext() {
    setStepIdx((prev) => Math.min(prev + 1, STEPS.length - 1));
  }

  function skipStep(stepName: string) {
    setSkippedSteps((prev) => [...prev, stepName]);
    goNext();
  }

  function handleFinish() {
    localStorage.removeItem(STEP_KEY);
    onComplete(skippedSteps);
  }

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadState('uploading');
    setUploadError(null);
    try {
      const result = await uploadFile(file);
      setUploadState('done');
      setUploadedFileName(result.name);
      onFileUploaded(result.name);
    } catch (err) {
      setUploadState('error');
      setUploadError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      if (fileRef.current) fileRef.current.value = '';
    }
  }

  const integrationConnected = dotloopConnected || docusignConnected;

  return (
    <div className="onboarding-overlay">
      <div className="onboarding-modal">
        {/* Progress indicator */}
        <div className="onboarding-progress">
          {STEPS.map((s, i) => (
            <div
              key={s}
              className={`onboarding-dot ${i === stepIdx ? 'active' : ''} ${i < stepIdx ? 'completed' : ''}`}
            />
          ))}
        </div>

        {/* Step 1: Welcome */}
        {step === 'welcome' && (
          <div className="onboarding-step">
            <h1 className="onboarding-title">Welcome to D.E.S.</h1>
            <p className="onboarding-subtitle">Document Extract System</p>
            <p className="onboarding-body">
              Upload real estate documents and extract structured data in seconds.
              Sync directly to Dotloop or DocuSign.
            </p>
            <button className="onboarding-btn primary" onClick={goNext}>
              Get Started
            </button>
          </div>
        )}

        {/* Step 2: Connect an Integration */}
        {step === 'integrations' && (
          <div className="onboarding-step">
            <h2 className="onboarding-heading">Connect Your Platform</h2>
            <p className="onboarding-body">
              Link your transaction management platform to push extracted data directly.
            </p>
            <div className="onboarding-cards">
              <div className={`onboarding-card ${dotloopConnected ? 'connected' : ''}`}>
                <span className="onboarding-card-icon">&#x1F517;</span>
                <span className="onboarding-card-label">Dotloop</span>
                {dotloopConnected ? (
                  <span className="onboarding-card-status">&#x2713; Connected</span>
                ) : (
                  <a href={getDotloopConnectUrl()} className="onboarding-btn secondary">
                    Connect
                  </a>
                )}
              </div>
              <div className={`onboarding-card ${docusignConnected ? 'connected' : ''}`}>
                <span className="onboarding-card-icon">&#x1F4DD;</span>
                <span className="onboarding-card-label">DocuSign</span>
                {docusignConnected ? (
                  <span className="onboarding-card-status">&#x2713; Connected</span>
                ) : (
                  <a href={getDocuSignConnectUrl()} className="onboarding-btn secondary">
                    Connect
                  </a>
                )}
              </div>
            </div>
            <div className="onboarding-actions">
              <button className="onboarding-btn text" onClick={() => skipStep('integration')}>
                Skip for now
              </button>
              <button
                className="onboarding-btn primary"
                onClick={goNext}
                disabled={!integrationConnected}
                title={integrationConnected ? '' : 'Connect at least one platform or skip'}
              >
                Next
              </button>
            </div>
          </div>
        )}

        {/* Step 3: First Extraction */}
        {step === 'extraction' && (
          <div className="onboarding-step">
            <h2 className="onboarding-heading">Upload Your First Document</h2>
            <p className="onboarding-body">
              Try it out with a purchase agreement, listing contract, or any real estate PDF.
            </p>

            {uploadState === 'idle' && (
              <label className="onboarding-upload-area">
                <input
                  type="file"
                  accept=".pdf"
                  ref={fileRef}
                  onChange={handleUpload}
                  hidden
                />
                <span className="onboarding-upload-icon">&#x1F4C4;</span>
                <span className="onboarding-upload-text">Click to upload a PDF</span>
              </label>
            )}

            {uploadState === 'uploading' && (
              <div className="onboarding-upload-progress">
                <span className="spinner" /> Uploading...
              </div>
            )}

            {uploadState === 'done' && (
              <div className="onboarding-upload-success">
                <span>&#x2713;</span> Uploaded {uploadedFileName}
              </div>
            )}

            {uploadState === 'error' && (
              <div className="onboarding-upload-error">
                {uploadError}
                <button className="onboarding-btn text" onClick={() => setUploadState('idle')}>
                  Try again
                </button>
              </div>
            )}

            <div className="onboarding-actions">
              <button className="onboarding-btn text" onClick={() => skipStep('extraction')}>
                Skip for now
              </button>
              <button
                className="onboarding-btn primary"
                onClick={goNext}
                disabled={uploadState !== 'done'}
              >
                {uploadState === 'done' ? 'Finish Setup' : 'Next'}
              </button>
            </div>
          </div>
        )}

        {/* Step 4: Done */}
        {step === 'done' && (
          <div className="onboarding-step">
            <h2 className="onboarding-heading">You're All Set!</h2>
            <div className="onboarding-summary">
              <div className="onboarding-summary-item">
                {integrationConnected ? '\u2713' : '\u2014'}{' '}
                {integrationConnected
                  ? `Connected to ${dotloopConnected ? 'Dotloop' : ''}${dotloopConnected && docusignConnected ? ' & ' : ''}${docusignConnected ? 'DocuSign' : ''}`
                  : 'Integration skipped'}
              </div>
              <div className="onboarding-summary-item">
                {uploadedFileName ? '\u2713' : '\u2014'}{' '}
                {uploadedFileName ? `Uploaded ${uploadedFileName}` : 'First extraction skipped'}
              </div>
            </div>
            <button className="onboarding-btn primary" onClick={handleFinish}>
              Go to Dashboard
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
