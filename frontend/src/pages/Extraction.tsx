import { useEffect, useState, useRef } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useOnboardingContext } from '../context/OnboardingContext';
import { useIntegrations } from '../hooks/useIntegrations';
import { useTransactionList } from '../hooks/useTransaction';
import { linkExtractionToTransaction } from '../api/transactions';
import {
  fetchDocuments,
  getDocumentUrl,
  startExtraction,
  subscribeToTask,
  fetchActiveTasks,
  fetchAllTasks,
  uploadFile,
  previewDotloopSync,
  executeDotloopSync,
  checkPropertyEnrichmentStatus,
} from '../api';

import type {
  DocumentInfo,
  ExtractionResult,
  SSEEvent,
  DotloopSyncResult,
  DotloopSyncPreview,
  PropertyEnrichmentEvent,
} from '../api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Mode = 'real_estate';

// Key date fields for ICS export
const DATE_FIELDS = [
  { key: 'closing_date', label: 'Closing Date' },
  { key: 'offer_date', label: 'Offer Date' },
  { key: 'offer_expiration_date', label: 'Offer Expiration Date' },
  { key: 'contract_agreement_date', label: 'Contract Agreement Date' },
  { key: 'inspection_date', label: 'Inspection Contingency Deadline' },
  { key: 'inspection_negotiation_deadline', label: 'Inspection Negotiation Deadline' },
  { key: 'insurance_contingency_date', label: 'Insurance Contingency Date' },
  { key: 'loan_application_deadline', label: 'Loan Application Deadline' },
  { key: 'seller_response_time', label: 'Seller Response Time' },
] as const;
type StepStatus = 'pending' | 'running' | 'complete' | 'error';

interface PipelineStep {
  num: number;
  title: string;
  status: StepStatus;
}

function getSteps(propertyEnrichmentEnabled = false): PipelineStep[] {
  const base: PipelineStep[] = [
    { num: 1, title: 'Load Document', status: 'pending' },
    { num: 2, title: 'Convert to Images', status: 'pending' },
    { num: 3, title: 'Neural OCR Extraction', status: 'pending' },
    { num: 4, title: 'Validate Schema', status: 'pending' },
    { num: 5, title: 'Verify Citations', status: 'pending' },
  ];
  if (propertyEnrichmentEnabled) {
    base.push({ num: base.length + 1, title: 'Property Enrichment', status: 'pending' });
  }
  base.push({ num: base.length + 1, title: 'Compliance Check', status: 'pending' });
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


// Job key for parallel extraction tracking
function jk(filename: string): string {
  return `real_estate:${filename}`;
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
// Extraction Page
// ---------------------------------------------------------------------------

export function ExtractionPage() {
  const { markStepAction } = useOnboardingContext();
  const [searchParams] = useSearchParams();
  const mode: Mode = 'real_estate';

  // Core
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [selectedDoc, setSelectedDoc] = useState<string | null>(null);
  const [loadingDocs, setLoadingDocs] = useState(true);

  // Upload
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Pipeline (for currently viewed doc)
  const [steps, setSteps] = useState<PipelineStep[]>(getSteps());
  const [isRunning, setIsRunning] = useState(false);

  // Results (for currently viewed doc)
  const [extractedData, setExtractedData] = useState<Record<string, unknown> | null>(null);
  const [validationSuccess, setValidationSuccess] = useState<boolean | null>(null);
  const [, setValidationErrors] = useState<string[]>([]);
  const [finalResult, setFinalResult] = useState<ExtractionResult | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [extractionId, setExtractionId] = useState<string | null>(null);

  // Parallel extraction tracking
  const [taskStatuses, setTaskStatuses] = useState<Record<string, string>>({});
  const [selectedDocs, setSelectedDocs] = useState<Set<string>>(new Set());
  const taskMapRef = useRef<Record<string, string>>({}); // jk → task_id
  const taskStatusesRef = useRef<Record<string, string>>({});
  taskStatusesRef.current = taskStatuses;
  const currentAbortRef = useRef<(() => void) | null>(null);

  // Integrations (shared hook — connection management lives on Profile page)
  const { dotloopConnected: dotloopConfigured } = useIntegrations();

  // HITL Dotloop sync
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<DotloopSyncResult | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [syncMode, setSyncMode] = useState<'selling' | 'buying'>('buying');
  const [syncPreview, setSyncPreview] = useState<DotloopSyncPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewFolderName, setPreviewFolderName] = useState('');

  // Key Dates .ics export
  const [selectedDates, setSelectedDates] = useState<Set<string>>(new Set());

  // Property Enrichment (Cadastral)
  const [propertyEnrichmentConfigured, setPropertyEnrichmentConfigured] = useState(false);
  const [propertyEnrichment, setPropertyEnrichment] = useState<PropertyEnrichmentEvent | null>(null);

  // Transaction linking
  const { transactions } = useTransactionList();
  const [selectedTransactionId, setSelectedTransactionId] = useState<string | null>(
    searchParams.get('txn'),
  );
  const [linkingStatus, setLinkingStatus] = useState<string | null>(null);

  // ---------------------------------------------------------------------------
  // Core helpers
  // ---------------------------------------------------------------------------

  function resetResults() {
    setExtractedData(null);
    setValidationSuccess(null);
    setValidationErrors([]);

    setPropertyEnrichment(null);
    setFinalResult(null);
    setErrorMessage(null);
    setExtractionId(null);
    setSyncResult(null);
    setSyncError(null);
    setSyncPreview(null);
    setPreviewError(null);
    setSelectedDates(new Set());
    setLinkingStatus(null);
  }

  // ---------------------------------------------------------------------------
  // SSE subscription — subscribe to a task for the currently viewed doc
  // ---------------------------------------------------------------------------

  function subscribeToDoc(taskId: string, docName: string) {
    // Unsubscribe from previous
    if (currentAbortRef.current) {
      currentAbortRef.current();
      currentAbortRef.current = null;
    }

    const key = jk(docName);

    const handler = (event: SSEEvent) => {
      switch (event.type) {
        case 'step':
          setSteps((prev) =>
            prev.map((s) =>
              s.num === event.data.step ? { ...s, status: 'running' as StepStatus } : s,
            ),
          );
          break;
        case 'step_complete':
          setSteps((prev) =>
            prev.map((s) =>
              s.num === event.data.step ? { ...s, status: 'complete' as StepStatus } : s,
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
          break;
        case 'property_enrichment':
          setPropertyEnrichment(event.data as PropertyEnrichmentEvent);
          break;
        case 'complete':
          setFinalResult(event.data);
          if (event.data.extraction_id) {
            setExtractionId(event.data.extraction_id);
            // Auto-link to selected transaction
            if (selectedTransactionId && event.data.extraction_id) {
              handleAutoLink(event.data.extraction_id);
            }
          }
          setIsRunning(false);
          setTaskStatuses((prev) => ({ ...prev, [key]: 'complete' }));
          break;
        case 'error':
          setErrorMessage(event.data.message);
          setIsRunning(false);
          setSteps((prev) =>
            prev.map((s) =>
              s.status === 'running' ? { ...s, status: 'error' as StepStatus } : s,
            ),
          );
          setTaskStatuses((prev) => ({ ...prev, [key]: 'error' }));
          break;
      }
    };

    const unsub = subscribeToTask(taskId, handler);
    currentAbortRef.current = unsub;
  }

  // ---------------------------------------------------------------------------
  // Auto-link extraction to transaction
  // ---------------------------------------------------------------------------

  async function handleAutoLink(extId: string) {
    if (!selectedTransactionId) return;
    try {
      await linkExtractionToTransaction(selectedTransactionId, extId);
      const txn = transactions.find(t => t._id === selectedTransactionId);
      setLinkingStatus(`Linked to ${txn?.name || 'transaction'}`);
    } catch {
      setLinkingStatus('Failed to link to transaction');
    }
  }

  // ---------------------------------------------------------------------------
  // Extraction actions
  // ---------------------------------------------------------------------------

  async function startDocExtraction(docName: string) {
    const key = jk(docName);
    if (taskStatusesRef.current[key] === 'running') return;

    try {
      const { task_id } = await startExtraction(mode, docName);
      taskMapRef.current[key] = task_id;
      setTaskStatuses((prev) => ({ ...prev, [key]: 'running' }));

      // If this is the currently selected doc, subscribe to SSE
      if (docName === selectedDoc) {
        resetResults();
        setSteps(getSteps(propertyEnrichmentConfigured));
        setIsRunning(true);
        subscribeToDoc(task_id, docName);
      }
    } catch (err) {
      setTaskStatuses((prev) => ({ ...prev, [key]: 'error' }));
      if (docName === selectedDoc) {
        setErrorMessage(err instanceof Error ? err.message : 'Failed to start extraction');
      }
    }
  }

  function handleRun() {
    if (!selectedDoc || isRunning) return;
    startDocExtraction(selectedDoc);
  }

  function handleBatchExtract(docNames: string[]) {
    for (const doc of docNames) {
      startDocExtraction(doc);
    }
  }

  function handleExtractAll() {
    handleBatchExtract(documents.map((d) => d.name));
  }

  // ---------------------------------------------------------------------------
  // Document selection — subscribe to task SSE or check cache
  // ---------------------------------------------------------------------------

  function handleDocSelect(docName: string) {
    if (docName === selectedDoc) return;

    // Unsubscribe from current SSE
    if (currentAbortRef.current) {
      currentAbortRef.current();
      currentAbortRef.current = null;
    }

    setSelectedDoc(docName);
    setIsRunning(false);

    // Check if this doc has a task
    const key = jk(docName);
    const taskId = taskMapRef.current[key];

    if (taskId && taskStatusesRef.current[key]) {
      // Has a task — subscribe to SSE to replay all events
      resetResults();
      setSteps(getSteps(propertyEnrichmentConfigured));
      if (taskStatusesRef.current[key] === 'running') setIsRunning(true);
      subscribeToDoc(taskId, docName);
    } else {
      resetResults();
      setSteps(getSteps(propertyEnrichmentConfigured));
    }
  }

  // ---------------------------------------------------------------------------
  // Upload
  // ---------------------------------------------------------------------------

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    try {
      const result = await uploadFile(file);
      const docs = await fetchDocuments(mode);
      setDocuments(docs);
      setSelectedDoc(result.name);
      resetResults();
      setSteps(getSteps(propertyEnrichmentConfigured));
      markStepAction('file_uploaded');
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }

  // ---------------------------------------------------------------------------
  // HITL Dotloop sync handlers
  // ---------------------------------------------------------------------------

  async function handlePreviewSync() {
    if (!extractionId) return;
    setPreviewLoading(true);
    setPreviewError(null);
    setSyncPreview(null);
    try {
      const preview = await previewDotloopSync(extractionId, syncMode);
      setSyncPreview(preview);
      setPreviewFolderName(preview.folder_name);
    } catch (err) {
      setPreviewError(err instanceof Error ? err.message : 'Preview failed');
    } finally {
      setPreviewLoading(false);
    }
  }

  async function handleExecuteSync() {
    if (!extractionId || !syncPreview) return;
    setIsSyncing(true);
    setSyncError(null);
    try {
      const result = await executeDotloopSync(
        extractionId,
        syncMode,
        syncPreview.existing_loop?.id,
        previewFolderName || syncPreview.folder_name,
        true,
      );
      setSyncResult(result);
      setSyncPreview(null);
    } catch (err) {
      setSyncError(err instanceof Error ? err.message : 'Sync failed');
      setSyncPreview(null);
    } finally {
      setIsSyncing(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Key Dates ICS export
  // ---------------------------------------------------------------------------

  function handleExportICS() {
    if (!finalResult || selectedDates.size === 0) return;
    const dotloopData = finalResult.dotloop_data as Record<string, unknown> | null;
    const dates = dotloopData?.['contract_dates'] as Record<string, string | null> | undefined;
    if (!dates) return;

    const lines: string[] = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//JGP//OfferDates//EN'];

    for (const key of Array.from(selectedDates)) {
      const raw = dates[key];
      if (!raw) continue;
      const parts = raw.split('/');
      if (parts.length !== 3) continue;
      const [mm, dd, yyyy] = parts;
      if (!mm || !dd || !yyyy) continue;
      const dtval = `${yyyy}${mm.padStart(2, '0')}${dd.padStart(2, '0')}`;
      const label = DATE_FIELDS.find((f) => f.key === key)?.label ?? key;
      const uid = `${key}-${extractionId}@jgp`;

      lines.push(
        'BEGIN:VEVENT',
        `UID:${uid}`,
        `DTSTART;VALUE=DATE:${dtval}`,
        `DTEND;VALUE=DATE:${dtval}`,
        `SUMMARY:${label}`,
        'END:VEVENT',
      );
    }

    lines.push('END:VCALENDAR');
    const blob = new Blob([lines.join('\r\n')], { type: 'text/calendar' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'transaction-dates.ics';
    a.click();
    URL.revokeObjectURL(url);
  }

  // ---------------------------------------------------------------------------
  // Effects
  // ---------------------------------------------------------------------------

  // Mount: check property enrichment, reconnect to running tasks
  useEffect(() => {
    checkPropertyEnrichmentStatus().then(setPropertyEnrichmentConfigured);

    // Reconnect to any active extraction tasks
    fetchActiveTasks().then((tasks) => {
      for (const task of tasks) {
        if (task.mode !== mode) continue;
        const key = jk(task.filename);
        taskMapRef.current[key] = task.task_id;
        setTaskStatuses((prev) => ({ ...prev, [key]: 'running' }));

        if (!selectedDoc) {
          setSelectedDoc(task.filename);
          setIsRunning(true);
          setSteps(getSteps(propertyEnrichmentConfigured));
          subscribeToDoc(task.task_id, task.filename);
        }
      }
    }).catch(() => {});
  }, []);

  // Load documents on mount
  useEffect(() => {
    setLoadingDocs(true);
    resetResults();
    setSteps(getSteps(propertyEnrichmentConfigured));
    setSelectedDocs(new Set());

    fetchDocuments(mode).then((docs) => {
      setDocuments(docs);
      const docToSelect = docs.length > 0 ? docs[0].name : null;
      setSelectedDoc(docToSelect);

      if (docToSelect) {
        const key = jk(docToSelect);
        const taskId = taskMapRef.current[key];

        if (taskId) {
          if (taskStatusesRef.current[key] === 'running') setIsRunning(true);
          subscribeToDoc(taskId, docToSelect);
        }
      }
    }).catch(() => {
      setDocuments([]);
      setSelectedDoc(null);
    }).finally(() => setLoadingDocs(false));
  }, []);

  // Poll task statuses for background status indicators
  useEffect(() => {
    const interval = setInterval(async () => {
      const current = taskStatusesRef.current;
      const hasRunning = Object.values(current).some((s) => s === 'running');
      if (!hasRunning) return;

      try {
        const tasks = await fetchAllTasks();
        setTaskStatuses((prev) => {
          const next = { ...prev };
          let changed = false;
          for (const task of tasks) {
            const key = jk(task.filename);
            if (key in next && next[key] === 'running') {
              const newStatus = task.status === 'complete' ? 'complete'
                : task.status === 'error' ? 'error'
                : 'running';
              if (next[key] !== newStatus) {
                next[key] = newStatus;
                changed = true;
              }
            }
          }
          return changed ? next : prev;
        });
      } catch {
        // ignore polling errors
      }
    }, 3000);

    return () => clearInterval(interval);
  }, []);

  // Derived state
  const totalBackgroundRunning = Object.entries(taskStatuses).filter(
    ([key, status]) => status === 'running' && key !== jk(selectedDoc || ''),
  ).length;

  // --- Render ---

  return (<div className="app">
      {/* Header */}
      <header className="header">
        <span className="header-title">Document Extraction</span>
        <span className="header-subtitle">Upload and extract data from purchase agreements</span>
      </header>

      <div className="main">
        {/* Left Panel */}
        <div className="left-panel">
          {/* Transaction Selector */}
          <div className="panel-section">
            <div className="panel-section-title">Link to Transaction</div>
            <select
              className="txn-selector"
              value={selectedTransactionId || ''}
              onChange={(e) => setSelectedTransactionId(e.target.value || null)}
            >
              <option value="">None (extract only)</option>
              {transactions
                .filter(t => !['closed', 'cancelled', 'expired'].includes(t.status))
                .map(t => (
                  <option key={t._id} value={t._id}>{t.name}</option>
                ))
              }
            </select>
            {selectedTransactionId && (
              <div className="txn-selector-indicator">
                Extractions will be linked to this transaction
              </div>
            )}
            {linkingStatus && (
              <div className={`txn-link-status ${linkingStatus.startsWith('Failed') ? 'error' : 'success'}`}>
                {linkingStatus}
              </div>
            )}
          </div>

          {/* Upload Section */}
          <div className="panel-section">
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf"
              onChange={handleUpload}
              style={{ display: 'none' }}
            />
            <button
              className={`upload-btn ${isUploading ? 'uploading' : ''}`}
              disabled={isUploading}
              onClick={() => fileInputRef.current?.click()}
            >
              {isUploading ? (
                <><span className="spinner" /> Uploading...</>
              ) : (
                <><span className="upload-icon">+</span> Upload PDF</>
              )}
            </button>
          </div>

          <div className="panel-section">
            <div className="panel-section-header">
              <div className="panel-section-title">Documents</div>
              {documents.length > 1 && (
                <label className="select-all-label">
                  <input
                    type="checkbox"
                    checked={selectedDocs.size === documents.length && documents.length > 0}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setSelectedDocs(new Set(documents.map((d) => d.name)));
                      } else {
                        setSelectedDocs(new Set());
                      }
                    }}
                  />
                  <span>All</span>
                </label>
              )}
            </div>
            <div className="doc-list">
              {loadingDocs ? (
                <div style={{ textAlign: 'center', padding: 20 }}>
                  <span className="spinner" />
                </div>
              ) : documents.length === 0 ? (
                <div className="empty-doc-list">
                  Upload a PDF to get started
                </div>
              ) : (
                documents.map((doc) => {
                  const key = jk(doc.name);
                  const status = taskStatuses[key];
                  return (
                    <div
                      key={doc.name}
                      className={`doc-item ${selectedDoc === doc.name ? 'selected' : ''}`}
                    >
                      <input
                        type="checkbox"
                        className="doc-checkbox"
                        checked={selectedDocs.has(doc.name)}
                        onClick={(e) => e.stopPropagation()}
                        onChange={() => {
                          setSelectedDocs((prev) => {
                            const next = new Set(prev);
                            if (next.has(doc.name)) next.delete(doc.name);
                            else next.add(doc.name);
                            return next;
                          });
                        }}
                      />
                      <div
                        className="doc-item-content"
                        onClick={() => handleDocSelect(doc.name)}
                      >
                        <span className="doc-icon">PDF</span>
                        <div className="doc-info">
                          <div className="doc-name">{doc.name}</div>
                          <div className="doc-meta">
                            {doc.size_human} - {doc.pages} page{doc.pages !== 1 ? 's' : ''}
                          </div>
                        </div>
                      </div>
                      {status && (
                        <span className={`doc-status-badge ${status}`}>
                          {status === 'running' ? (
                            <span className="spinner" style={{ width: 12, height: 12, borderWidth: 1.5 }} />
                          ) : status === 'complete' ? '\u2713' : '\u2717'}
                        </span>
                      )}
                    </div>
                  );
                })
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
                <><span className="spinner" /> Processing...</>
              ) : (
                <>&#9654; Run Extraction</>
              )}
            </button>
            {documents.length > 1 && (
              <div className="batch-buttons">
                {selectedDocs.size > 0 && (
                  <button
                    className="batch-btn"
                    onClick={() => handleBatchExtract([...selectedDocs])}
                    disabled={[...selectedDocs].every(
                      (d) => taskStatusesRef.current[jk(d)] === 'running',
                    )}
                  >
                    Extract Selected ({selectedDocs.size})
                  </button>
                )}
                <button
                  className="batch-btn"
                  onClick={handleExtractAll}
                  disabled={documents.every(
                    (d) => taskStatusesRef.current[jk(d.name)] === 'running',
                  )}
                >
                  Extract All ({documents.length})
                </button>
              </div>
            )}
          </div>

          <div className="pdf-preview">
            {selectedDoc ? (
              <>
                <embed
                  src={getDocumentUrl(selectedDoc)}
                  type="application/pdf"
                  key={selectedDoc}
                />
                <a
                  href={getDocumentUrl(selectedDoc)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="pdf-mobile-link"
                >
                  Open PDF in new tab
                </a>
              </>
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

          {/* Background Jobs Indicator */}
          {totalBackgroundRunning > 0 && (
            <div className="cached-banner">
              <span className="spinner" />
              <span className="cached-text">
                {totalBackgroundRunning} extraction{totalBackgroundRunning !== 1 ? 's' : ''} running in background
              </span>
            </div>
          )}

          {/* Property Enrichment */}
          {propertyEnrichment && propertyEnrichment.match_quality !== 'none' && (
            <div className="property-enrichment-section">
              <div className="property-enrichment-title">
                Property Enrichment (Regrid)
              </div>
              <div className="property-enrichment-grid">
                {propertyEnrichment.parcel_id && (
                  <div className="property-enrichment-field">
                    <span className="property-enrichment-label">Parcel ID</span>
                    <span className="property-enrichment-value">{propertyEnrichment.parcel_id}</span>
                  </div>
                )}
                {propertyEnrichment.assessed_total != null && (
                  <div className="property-enrichment-field">
                    <span className="property-enrichment-label">Assessed Value</span>
                    <span className="property-enrichment-value">${propertyEnrichment.assessed_total.toLocaleString()}</span>
                  </div>
                )}
                {propertyEnrichment.year_built != null && (
                  <div className="property-enrichment-field">
                    <span className="property-enrichment-label">Year Built</span>
                    <span className="property-enrichment-value">{propertyEnrichment.year_built}</span>
                  </div>
                )}
                {propertyEnrichment.lot_size_acres != null && (
                  <div className="property-enrichment-field">
                    <span className="property-enrichment-label">Lot Size</span>
                    <span className="property-enrichment-value">{propertyEnrichment.lot_size_acres.toFixed(2)} acres</span>
                  </div>
                )}
                {propertyEnrichment.zoning && (
                  <div className="property-enrichment-field">
                    <span className="property-enrichment-label">Zoning</span>
                    <span className="property-enrichment-value">{propertyEnrichment.zoning}</span>
                  </div>
                )}
                {propertyEnrichment.owner_name && (
                  <div className="property-enrichment-field">
                    <span className="property-enrichment-label">Owner on Record</span>
                    <span className="property-enrichment-value">{propertyEnrichment.owner_name}</span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Key Dates panel — ICS export */}
          {finalResult && (() => {
            const dotloopData = finalResult.dotloop_data as Record<string, unknown> | null;
            const dates = dotloopData?.['contract_dates'] as Record<string, string | null> | undefined;
            const availableDates = dates
              ? DATE_FIELDS.filter((f) => dates[f.key])
              : [];
            if (availableDates.length === 0) return null;
            return (
              <div className="key-dates-section">
                <h3 className="key-dates-heading">Key Dates</h3>
                <div className="key-dates-list">
                  {availableDates.map((f) => (
                    <label key={f.key} className="key-dates-row">
                      <input
                        type="checkbox"
                        checked={selectedDates.has(f.key)}
                        onChange={() => setSelectedDates((prev) => {
                          const next = new Set(prev);
                          if (next.has(f.key)) next.delete(f.key);
                          else next.add(f.key);
                          return next;
                        })}
                      />
                      <span className="key-dates-label">{f.label}</span>
                      <span className="key-dates-value">{dates![f.key]}</span>
                    </label>
                  ))}
                </div>
                <button
                  className="btn-secondary"
                  disabled={selectedDates.size === 0}
                  onClick={handleExportICS}
                  style={{ marginTop: 12 }}
                >
                  Export to Calendar (.ics)
                </button>
              </div>
            );
          })()}

          {/* Dotloop Section — link to Profile when not connected */}
          {!dotloopConfigured && (
            <div className="dotloop-section">
              <Link to="/profile" className="integration-profile-link">
                Dotloop not connected - Set up in Profile
              </Link>
            </div>
          )}

          {/* HITL Dotloop Sync */}
          {dotloopConfigured && finalResult && extractionId && (
            <div className="dotloop-section">
              {!syncResult && !syncError && !syncPreview && (
                <>
                  <div className="dotloop-mode-selector">
                    <span className="dotloop-label">Sync Mode</span>
                    <label className="dotloop-radio">
                      <input
                        type="radio"
                        value="buying"
                        checked={syncMode === 'buying'}
                        onChange={() => setSyncMode('buying')}
                      />
                      Buying (loop per buyer)
                    </label>
                    <label className="dotloop-radio">
                      <input
                        type="radio"
                        value="selling"
                        checked={syncMode === 'selling'}
                        onChange={() => setSyncMode('selling')}
                      />
                      Selling (loop per property, folder per buyer)
                    </label>
                  </div>
                  <button
                    className="dotloop-sync-btn"
                    disabled={previewLoading}
                    onClick={handlePreviewSync}
                  >
                    {previewLoading
                      ? <><span className="spinner" /> Loading preview...</>
                      : <>Preview Sync</>
                    }
                  </button>
                  {previewError && (
                    <div className="dotloop-error" style={{ marginTop: 8 }}>
                      Preview failed: {previewError}
                    </div>
                  )}
                </>
              )}

              {/* Confirmation modal */}
              {syncPreview && !syncResult && (
                <div className="hitl-modal">
                  <h3 className="hitl-modal-title">Confirm Dotloop Sync</h3>
                  <div className="hitl-modal-row">
                    <span className="hitl-modal-label">Loop</span>
                    <span className="hitl-modal-value">
                      {syncPreview.loop_action === 'create' ? '[Will create] ' : '[Will update] '}
                      {syncPreview.loop_name}
                    </span>
                  </div>
                  <div className="hitl-modal-row">
                    <span className="hitl-modal-label">Folder</span>
                    <input
                      className="hitl-modal-input"
                      value={previewFolderName}
                      onChange={(e) => setPreviewFolderName(e.target.value)}
                    />
                  </div>
                  {syncPreview.participants.length > 0 && (
                    <div className="hitl-modal-row">
                      <span className="hitl-modal-label">Participants</span>
                      <span className="hitl-modal-value">
                        {syncPreview.participants
                          .slice(0, 3)
                          .map((p) => `${p.fullName} (${p.role})`)
                          .join(', ')}
                        {syncPreview.participants.length > 3 && ` +${syncPreview.participants.length - 3} more`}
                      </span>
                    </div>
                  )}
                  {syncPreview.document_name && (
                    <div className="hitl-modal-row">
                      <span className="hitl-modal-label">Document</span>
                      <span className="hitl-modal-value">{syncPreview.document_name}</span>
                    </div>
                  )}
                  <div className="hitl-modal-actions">
                    <button
                      className="btn-secondary"
                      onClick={() => setSyncPreview(null)}
                    >
                      Cancel
                    </button>
                    <button
                      className="btn-primary"
                      disabled={isSyncing}
                      onClick={handleExecuteSync}
                    >
                      {isSyncing ? <><span className="spinner" /> Syncing...</> : 'Confirm Sync'}
                    </button>
                  </div>
                </div>
              )}

              {syncResult && (
                <div className="dotloop-success">
                  <span className="dotloop-check">OK</span>
                  {syncResult.action} loop in Dotloop
                  {syncResult.document_uploaded && syncResult.document_name && (
                    <span className="dotloop-doc-uploaded"> - Uploaded {syncResult.document_name}</span>
                  )}
                  {syncResult.loop_url && (
                    <a href={syncResult.loop_url} target="_blank" rel="noopener noreferrer" className="dotloop-link">
                      Open in Dotloop
                    </a>
                  )}
                  {syncResult.errors.length > 0 && (
                    <div className="dotloop-warnings">
                      {syncResult.errors.map((e, i) => (
                        <div key={i} className="dotloop-warning">{e}</div>
                      ))}
                    </div>
                  )}
                </div>
              )}
              {syncError && (
                <div className="dotloop-error">
                  Sync failed: {syncError}
                  <button className="dotloop-retry" onClick={() => { setSyncError(null); setSyncResult(null); }}>
                    Try Again
                  </button>
                </div>
              )}
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

          {/* Results Content — extraction table only */}
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

            {extractedData && (
              <>
                {validationSuccess !== null && (
                  <div className={`extraction-validation-badge ${validationSuccess ? 'valid' : 'invalid'}`}>
                    {validationSuccess ? '\u2713 Validated' : '! Validation issues'}
                  </div>
                )}
                {finalResult && (
                  <div className="extraction-confidence-row">
                    <span className="extraction-pages">
                      {finalResult.pages_processed} page{finalResult.pages_processed !== 1 ? 's' : ''}
                    </span>
                  </div>
                )}
                <ExtractionTable data={extractedData} />
              </>
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


export default ExtractionPage;
