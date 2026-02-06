import { useEffect, useState, useCallback, useRef } from 'react';
import {
  fetchDocuments,
  getDocumentUrl,
  runExtraction,
} from './api';
import type {
  DocumentInfo,
  VerificationCitation,
  PIIFinding,
  ExtractionResult,
  SSEEvent,
} from './api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Mode = 'real_estate' | 'gov';
type StepStatus = 'pending' | 'running' | 'complete' | 'error';
type TabId = 'extraction' | 'citations' | 'pii' | 'json';

interface PipelineStep {
  num: number;
  title: string;
  status: StepStatus;
}

function getSteps(mode: Mode): PipelineStep[] {
  const base: PipelineStep[] = [
    { num: 1, title: 'Load Document', status: 'pending' },
    { num: 2, title: 'Convert to Images', status: 'pending' },
    { num: 3, title: 'Neural OCR Extraction', status: 'pending' },
    { num: 4, title: 'Validate Schema', status: 'pending' },
    { num: 5, title: 'Verify Citations', status: 'pending' },
  ];
  if (mode === 'gov') {
    base.push({ num: 6, title: 'PII Scan', status: 'pending' });
  }
  base.push({ num: base.length + 1, title: 'Output', status: 'pending' });
  return base;
}

function stepIcon(status: StepStatus): string {
  switch (status) {
    case 'pending': return '\u25CB';
    case 'running': return '\u23F3';
    case 'complete': return '\u2713';
    case 'error': return '\u2717';
  }
}

function confLevel(c: number): string {
  if (c >= 0.85) return 'high';
  if (c >= 0.65) return 'medium';
  return 'low';
}

// Flatten nested object for extraction table
function flattenObject(
  obj: Record<string, unknown>,
  prefix = '',
): Array<{ key: string; value: unknown }> {
  const result: Array<{ key: string; value: unknown }> = [];
  for (const [k, v] of Object.entries(obj)) {
    const fullKey = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      result.push(...flattenObject(v as Record<string, unknown>, fullKey));
    } else if (Array.isArray(v)) {
      v.forEach((item, i) => {
        if (item && typeof item === 'object') {
          result.push(
            ...flattenObject(item as Record<string, unknown>, `${fullKey}[${i}]`),
          );
        } else {
          result.push({ key: `${fullKey}[${i}]`, value: item });
        }
      });
    } else {
      result.push({ key: fullKey, value: v });
    }
  }
  return result;
}

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------

function App() {
  // Core
  const [mode, setMode] = useState<Mode>('real_estate');
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [selectedDoc, setSelectedDoc] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [loadingDocs, setLoadingDocs] = useState(true);

  // Pipeline
  const [steps, setSteps] = useState<PipelineStep[]>(getSteps('real_estate'));

  // Results
  const [extractedData, setExtractedData] = useState<Record<string, unknown> | null>(null);
  const [validationSuccess, setValidationSuccess] = useState<boolean | null>(null);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [citations, setCitations] = useState<VerificationCitation[] | null>(null);
  const [overallConfidence, setOverallConfidence] = useState<number | null>(null);
  const [piiFindings, setPiiFindings] = useState<PIIFinding[] | null>(null);
  const [piiRiskScore, setPiiRiskScore] = useState<number | null>(null);
  const [piiRiskLevel, setPiiRiskLevel] = useState<string | null>(null);
  const [finalResult, setFinalResult] = useState<ExtractionResult | null>(null);
  const [activeTab, setActiveTab] = useState<TabId>('extraction');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const abortRef = useRef<(() => void) | null>(null);

  // Load documents
  useEffect(() => {
    fetchDocuments()
      .then(setDocuments)
      .catch(() => setDocuments([]))
      .finally(() => setLoadingDocs(false));
  }, []);

  // Reset steps when mode changes
  useEffect(() => {
    setSteps(getSteps(mode));
    resetResults();
  }, [mode]);

  function resetResults() {
    setExtractedData(null);
    setValidationSuccess(null);
    setValidationErrors([]);
    setCitations(null);
    setOverallConfidence(null);
    setPiiFindings(null);
    setPiiRiskScore(null);
    setPiiRiskLevel(null);
    setFinalResult(null);
    setErrorMessage(null);
    setActiveTab('extraction');
  }

  const handleEvent = useCallback(
    (event: SSEEvent) => {
      switch (event.type) {
        case 'step':
          setSteps((prev) =>
            prev.map((s) =>
              s.num === event.data.step
                ? { ...s, status: 'running' as StepStatus }
                : s,
            ),
          );
          break;

        case 'step_complete':
          setSteps((prev) =>
            prev.map((s) =>
              s.num === event.data.step
                ? { ...s, status: 'complete' as StepStatus }
                : s,
            ),
          );
          break;

        case 'extraction':
          setExtractedData(event.data.validated_data);
          break;

        case 'validation':
          setValidationSuccess(event.data.success);
          setValidationErrors(event.data.errors);
          break;

        case 'citations':
          setCitations(event.data.citations);
          setOverallConfidence(event.data.overall_confidence);
          break;

        case 'pii':
          setPiiFindings(event.data.findings);
          setPiiRiskScore(event.data.risk_score);
          setPiiRiskLevel(event.data.risk_level);
          break;

        case 'complete':
          setFinalResult(event.data);
          setIsRunning(false);
          break;

        case 'error':
          setErrorMessage(event.data.message);
          setIsRunning(false);
          setSteps((prev) =>
            prev.map((s) =>
              s.status === 'running'
                ? { ...s, status: 'error' as StepStatus }
                : s,
            ),
          );
          break;
      }
    },
    [],
  );

  function handleRun() {
    if (!selectedDoc || isRunning) return;

    resetResults();
    setSteps(getSteps(mode));
    setIsRunning(true);

    const abort = runExtraction(mode, selectedDoc, handleEvent);
    abortRef.current = abort;
  }

  function handleModeChange(newMode: Mode) {
    if (isRunning) return;
    setMode(newMode);
    setSelectedDoc(null);
  }

  // --- Render ---

  return (
    <div className="app">
      {/* Header */}
      <header className="header">
        <div className="header-left">
          <span className="header-title">D.E.S.</span>
          <div className="mode-toggle">
            <button
              className={`mode-btn ${mode === 'real_estate' ? 'active' : ''}`}
              onClick={() => handleModeChange('real_estate')}
            >
              Real Estate
            </button>
            <button
              className={`mode-btn ${mode === 'gov' ? 'active' : ''}`}
              onClick={() => handleModeChange('gov')}
            >
              Government
            </button>
          </div>
        </div>
        <span className="header-subtitle">Neural OCR + Pydantic Validation</span>
      </header>

      <div className="main">
        {/* Left Panel */}
        <div className="left-panel">
          <div className="panel-section">
            <div className="panel-section-title">Documents</div>
            <div className="doc-list">
              {loadingDocs ? (
                <div style={{ textAlign: 'center', padding: 20 }}>
                  <span className="spinner" />
                </div>
              ) : (
                documents.map((doc) => (
                  <div
                    key={doc.name}
                    className={`doc-item ${selectedDoc === doc.name ? 'selected' : ''}`}
                    onClick={() => {
                      if (!isRunning) {
                        setSelectedDoc(doc.name);
                        resetResults();
                        setSteps(getSteps(mode));
                      }
                    }}
                  >
                    <span className="doc-icon">PDF</span>
                    <div className="doc-info">
                      <div className="doc-name">{doc.name}</div>
                      <div className="doc-meta">
                        {doc.size_human} &middot; {doc.pages} page{doc.pages !== 1 ? 's' : ''}
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="panel-section">
            <button
              className={`run-btn ${isRunning ? 'running' : selectedDoc ? 'ready' : ''}`}
              disabled={!selectedDoc || isRunning}
              onClick={handleRun}
            >
              {isRunning ? (
                <>
                  <span className="spinner" /> Processing...
                </>
              ) : (
                <>&#9654; Run Extraction</>
              )}
            </button>
          </div>

          <div className="pdf-preview">
            {selectedDoc ? (
              <embed
                src={getDocumentUrl(selectedDoc)}
                type="application/pdf"
                key={selectedDoc}
              />
            ) : (
              <div className="pdf-placeholder">Select a document to preview</div>
            )}
          </div>
        </div>

        {/* Right Panel */}
        <div className="right-panel">
          {/* Pipeline Steps */}
          <div className="pipeline">
            <div className="pipeline-title">Pipeline</div>
            <div className="steps">
              {steps.map((s) => (
                <div key={s.num} className={`step ${s.status}`}>
                  <span className="step-icon">{stepIcon(s.status)}</span>
                  {s.title}
                </div>
              ))}
            </div>
          </div>

          {/* Confidence Bar */}
          {overallConfidence !== null && (
            <div className="confidence-section">
              <span className="confidence-label">Confidence</span>
              <div className="confidence-bar">
                <div
                  className={`confidence-fill ${confLevel(overallConfidence)}`}
                  style={{ width: `${overallConfidence * 100}%` }}
                />
              </div>
              <span className={`confidence-value ${confLevel(overallConfidence)}`}>
                {(overallConfidence * 100).toFixed(0)}%
              </span>
            </div>
          )}

          {/* Error Banner */}
          {errorMessage && (
            <div style={{
              padding: '12px 20px',
              background: 'var(--red-dim)',
              borderBottom: '1px solid var(--red)',
              color: 'var(--red)',
              fontFamily: 'var(--font-mono)',
              fontSize: 13,
            }}>
              Error: {errorMessage}
            </div>
          )}

          {/* Tabs */}
          {(extractedData || finalResult) && (
            <div className="tabs">
              <button
                className={`tab ${activeTab === 'extraction' ? 'active' : ''}`}
                onClick={() => setActiveTab('extraction')}
              >
                Extraction
                {validationSuccess !== null && (
                  <span className={`tab-badge ${validationSuccess ? 'green' : 'red'}`}>
                    {validationSuccess ? '\u2713' : '!'}
                  </span>
                )}
              </button>
              {citations && (
                <button
                  className={`tab ${activeTab === 'citations' ? 'active' : ''}`}
                  onClick={() => setActiveTab('citations')}
                >
                  Citations
                  <span className="tab-badge green">{citations.length}</span>
                </button>
              )}
              {piiFindings && mode === 'gov' && (
                <button
                  className={`tab ${activeTab === 'pii' ? 'active' : ''}`}
                  onClick={() => setActiveTab('pii')}
                >
                  PII
                  {piiFindings.length > 0 && (
                    <span className="tab-badge red">{piiFindings.length}</span>
                  )}
                </button>
              )}
              {finalResult && (
                <button
                  className={`tab ${activeTab === 'json' ? 'active' : ''}`}
                  onClick={() => setActiveTab('json')}
                >
                  JSON
                </button>
              )}
            </div>
          )}

          {/* Results Content */}
          <div className="results">
            {!extractedData && !isRunning && (
              <div className="empty-state">
                <div className="empty-state-icon">&mdash;</div>
                <div className="empty-state-text">
                  Select a document and click Run to start extraction
                </div>
              </div>
            )}

            {!extractedData && isRunning && (
              <div className="empty-state">
                <span className="spinner" />
                <div className="empty-state-text">Processing document...</div>
              </div>
            )}

            {/* Extraction Tab */}
            {activeTab === 'extraction' && extractedData && (
              <ExtractionTable data={extractedData} />
            )}

            {/* Citations Tab */}
            {activeTab === 'citations' && citations && (
              <CitationsTable citations={citations} />
            )}

            {/* PII Tab */}
            {activeTab === 'pii' && piiFindings && (
              <PIIPanel
                findings={piiFindings}
                riskScore={piiRiskScore ?? 0}
                riskLevel={piiRiskLevel ?? 'LOW'}
              />
            )}

            {/* JSON Tab */}
            {activeTab === 'json' && finalResult && (
              <JSONOutput data={finalResult} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ExtractionTable({ data }: { data: Record<string, unknown> }) {
  const rows = flattenObject(data);

  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>Field</th>
          <th>Value</th>
          <th style={{ width: 32 }}></th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const present =
            row.value !== null &&
            row.value !== undefined &&
            row.value !== '';
          return (
            <tr key={row.key}>
              <td>
                <span className="field-name">{row.key}</span>
              </td>
              <td>
                <span className={`field-value ${present ? '' : 'missing'}`}>
                  {present ? String(row.value) : '\u2014'}
                </span>
              </td>
              <td>
                <span className={`status-icon ${present ? 'present' : 'absent'}`}>
                  {present ? '\u2713' : '\u25CB'}
                </span>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function CitationsTable({ citations }: { citations: VerificationCitation[] }) {
  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>Field</th>
          <th>Value</th>
          <th>Page</th>
          <th>Location</th>
          <th>Context</th>
          <th>Conf.</th>
        </tr>
      </thead>
      <tbody>
        {citations.map((c, i) => (
          <tr key={i}>
            <td>
              <span className="field-name">{c.field_name}</span>
            </td>
            <td>
              <span className="field-value">
                {c.extracted_value.length > 25
                  ? c.extracted_value.slice(0, 22) + '...'
                  : c.extracted_value}
              </span>
            </td>
            <td style={{ textAlign: 'center' }}>{c.page_number}</td>
            <td style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
              {c.line_or_region}
            </td>
            <td
              style={{
                fontSize: 11,
                color: 'var(--text-muted)',
                fontFamily: 'var(--font-mono)',
                maxWidth: 200,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {c.surrounding_text}
            </td>
            <td>
              <span className={`conf-badge ${confLevel(c.confidence)}`}>
                {(c.confidence * 100).toFixed(0)}%
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function PIIPanel({
  findings,
  riskScore,
  riskLevel,
}: {
  findings: PIIFinding[];
  riskScore: number;
  riskLevel: string;
}) {
  return (
    <div>
      <div className={`pii-risk-banner ${riskLevel}`}>
        <span>PII Risk Score: {riskScore}/100</span>
        <span className={`severity-badge ${riskLevel}`}>{riskLevel}</span>
      </div>

      {findings.length === 0 ? (
        <div style={{ color: 'var(--green)', padding: 20, textAlign: 'center' }}>
          No PII detected.
        </div>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Type</th>
              <th>Redacted</th>
              <th>Location</th>
              <th>Severity</th>
              <th>Recommendation</th>
            </tr>
          </thead>
          <tbody>
            {findings.map((f, i) => (
              <tr key={i}>
                <td style={{ fontWeight: 600 }}>{f.pii_type}</td>
                <td>
                  <span className="field-value">{f.value_redacted}</span>
                </td>
                <td style={{ fontSize: 12 }}>{f.location}</td>
                <td>
                  <span className={`severity-badge ${f.severity}`}>
                    {f.severity}
                  </span>
                </td>
                <td style={{ fontSize: 12, color: 'var(--text-secondary)', maxWidth: 300 }}>
                  {f.recommendation}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function JSONOutput({ data }: { data: ExtractionResult }) {
  const [copied, setCopied] = useState(false);
  const json = JSON.stringify(data, null, 2);

  function handleCopy() {
    navigator.clipboard.writeText(json).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <div className="json-output">
      <button className="copy-btn" onClick={handleCopy}>
        {copied ? 'Copied!' : 'Copy'}
      </button>
      <pre>{json}</pre>
    </div>
  );
}

export default App;
