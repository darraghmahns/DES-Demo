import { useEffect, useState, useRef } from 'react';
import {
  fetchDocuments,
  getDocumentUrl,
  startExtraction,
  subscribeToTask,
  fetchActiveTasks,
  fetchAllTasks,
  uploadFile,
  checkDotloopStatus,
  syncToDotloop,
  getDotloopConnectUrl,
  fetchDotloopLoops,
  checkDocuSignStatus,
  syncToDocuSign,
  voidDocuSignEnvelope,
  getDocuSignConnectUrl,
  fetchDocuSignEnvelopes,
  fetchAggregateUsage,
  computeFileHash,
  checkCachedExtraction,
  clearExtractionCache,
  searchDotloopLoops,
  fetchLoopDetail,
  fetchEnvelopeDetail,
  extractBatch,
  compareExtractions,
  fetchExtractions,
  setAuthTokenProvider,
  checkPropertyEnrichmentStatus,
} from './api';

// Clerk auth — only active when VITE_CLERK_PUBLISHABLE_KEY is set
import { useAuth, SignedIn, SignedOut, SignIn, UserButton, OrganizationSwitcher } from '@clerk/clerk-react';

const CLERK_ENABLED = !!import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;
import type {
  DocumentInfo,
  VerificationCitation,
  PIIFinding,
  PIIReport,
  ComplianceReport,
  ComplianceRequirement,
  ExtractionResult,
  SSEEvent,
  DotloopSyncResult,
  DotloopLoop,
  DocuSignSyncResult,
  DocuSignEnvelope,
  AggregateUsage,
  LoopDetail,
  EnvelopeDetail,
  ComparisonResult,
  FieldSignificance,
  BatchSource,
  ExtractionSummary,
  PropertyEnrichmentEvent,
} from './api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Mode = 'real_estate' | 'gov';
type ViewId = 'extraction' | 'loops' | 'compare';
type StepStatus = 'pending' | 'running' | 'complete' | 'error';
type TabId = 'extraction' | 'citations' | 'compliance' | 'pii' | 'json';

interface PipelineStep {
  num: number;
  title: string;
  status: StepStatus;
}

function getSteps(mode: Mode, propertyEnrichmentEnabled = false): PipelineStep[] {
  const base: PipelineStep[] = [
    { num: 1, title: 'Load Document', status: 'pending' },
    { num: 2, title: 'Convert to Images', status: 'pending' },
    { num: 3, title: 'Neural OCR Extraction', status: 'pending' },
    { num: 4, title: 'Validate Schema', status: 'pending' },
    { num: 5, title: 'Verify Citations', status: 'pending' },
  ];
  if (mode === 'real_estate' && propertyEnrichmentEnabled) {
    base.push({ num: base.length + 1, title: 'Property Enrichment', status: 'pending' });
  }
  if (mode === 'real_estate') {
    base.push({ num: base.length + 1, title: 'Compliance Check', status: 'pending' });
  }
  if (mode === 'gov') {
    base.push({ num: base.length + 1, title: 'PII Scan', status: 'pending' });
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

// Job key for parallel extraction tracking
function jk(mode: Mode, filename: string): string {
  return `${mode}:${filename}`;
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

function AuthTokenWiring() {
  const { getToken } = useAuth();
  useEffect(() => {
    setAuthTokenProvider(() => getToken());
  }, [getToken]);
  return null;
}

function App() {
  // Core
  const [mode, setMode] = useState<Mode>('real_estate');
  const [activeView, setActiveView] = useState<ViewId>('extraction');
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [selectedDoc, setSelectedDoc] = useState<string | null>(null);
  const [loadingDocs, setLoadingDocs] = useState(true);

  // Upload
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Pipeline (for currently viewed doc)
  const [steps, setSteps] = useState<PipelineStep[]>(getSteps('real_estate'));
  const [isRunning, setIsRunning] = useState(false);

  // Results (for currently viewed doc)
  const [extractedData, setExtractedData] = useState<Record<string, unknown> | null>(null);
  const [validationSuccess, setValidationSuccess] = useState<boolean | null>(null);
  const [, setValidationErrors] = useState<string[]>([]);
  const [citations, setCitations] = useState<VerificationCitation[] | null>(null);
  const [overallConfidence, setOverallConfidence] = useState<number | null>(null);
  const [piiFindings, setPiiFindings] = useState<PIIFinding[] | null>(null);
  const [piiRiskScore, setPiiRiskScore] = useState<number | null>(null);
  const [piiRiskLevel, setPiiRiskLevel] = useState<string | null>(null);
  const [complianceReport, setComplianceReport] = useState<ComplianceReport | null>(null);
  const [finalResult, setFinalResult] = useState<ExtractionResult | null>(null);
  const [activeTab, setActiveTab] = useState<TabId>('extraction');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [extractionId, setExtractionId] = useState<string | null>(null);

  // Parallel extraction tracking
  const [taskStatuses, setTaskStatuses] = useState<Record<string, string>>({});
  const [selectedDocs, setSelectedDocs] = useState<Set<string>>(new Set());
  const taskMapRef = useRef<Record<string, string>>({}); // jk → task_id
  const taskStatusesRef = useRef<Record<string, string>>({});
  taskStatusesRef.current = taskStatuses;
  const currentAbortRef = useRef<(() => void) | null>(null);
  const modeDocRef = useRef<Partial<Record<Mode, string | null>>>({});

  // Dotloop
  const [dotloopConfigured, setDotloopConfigured] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<DotloopSyncResult | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [dotloopLoops, setDotloopLoops] = useState<DotloopLoop[]>([]);
  const [selectedLoopId, setSelectedLoopId] = useState<number | null>(null);
  const [loadingLoops, setLoadingLoops] = useState(false);

  // Property Enrichment (Cadastral)
  const [propertyEnrichmentConfigured, setPropertyEnrichmentConfigured] = useState(false);
  const [propertyEnrichment, setPropertyEnrichment] = useState<PropertyEnrichmentEvent | null>(null);

  // DocuSign
  const [docusignConfigured, setDocusignConfigured] = useState(false);
  const [isDocusignSyncing, setIsDocusignSyncing] = useState(false);
  const [docusignSyncResult, setDocusignSyncResult] = useState<DocuSignSyncResult | null>(null);
  const [docusignSyncError, setDocusignSyncError] = useState<string | null>(null);
  const [docusignEnvelopes, setDocusignEnvelopes] = useState<DocuSignEnvelope[]>([]);
  const [selectedEnvelopeId, setSelectedEnvelopeId] = useState<string | null>(null);
  const [loadingEnvelopes, setLoadingEnvelopes] = useState(false);

  // API Usage
  const [aggregateUsage, setAggregateUsage] = useState<AggregateUsage | null>(null);

  // Cache
  const [isCached, setIsCached] = useState(false);
  const [checkingCache, setCheckingCache] = useState(false);

  // Comparison
  const [compareFromId, setCompareFromId] = useState('');
  const [compareToId, setCompareToId] = useState('');

  // ---------------------------------------------------------------------------
  // Core helpers
  // ---------------------------------------------------------------------------

  function resetResults() {
    setExtractedData(null);
    setValidationSuccess(null);
    setValidationErrors([]);
    setCitations(null);
    setOverallConfidence(null);
    setPiiFindings(null);
    setPiiRiskScore(null);
    setPiiRiskLevel(null);
    setComplianceReport(null);
    setPropertyEnrichment(null);
    setFinalResult(null);
    setErrorMessage(null);
    setActiveTab('extraction');
    setExtractionId(null);
    setSyncResult(null);
    setSyncError(null);
    setDotloopLoops([]);
    setSelectedLoopId(null);
    setDocusignSyncResult(null);
    setDocusignSyncError(null);
    setSelectedEnvelopeId(null);
    setIsCached(false);
  }

  // ---------------------------------------------------------------------------
  // SSE subscription — subscribe to a task for the currently viewed doc
  // ---------------------------------------------------------------------------

  function subscribeToDoc(taskId: string, docMode: Mode, docName: string) {
    // Unsubscribe from previous
    if (currentAbortRef.current) {
      currentAbortRef.current();
      currentAbortRef.current = null;
    }

    const key = jk(docMode, docName);

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
          setCitations(event.data.citations);
          setOverallConfidence(event.data.overall_confidence);
          break;
        case 'pii':
          setPiiFindings(event.data.findings);
          setPiiRiskScore(event.data.risk_score);
          setPiiRiskLevel(event.data.risk_level);
          break;
        case 'compliance':
          setComplianceReport(event.data as unknown as ComplianceReport);
          break;
        case 'property_enrichment':
          setPropertyEnrichment(event.data as PropertyEnrichmentEvent);
          break;
        case 'complete':
          setFinalResult(event.data);
          if (event.data.extraction_id) setExtractionId(event.data.extraction_id);
          setIsRunning(false);
          setTaskStatuses((prev) => ({ ...prev, [key]: 'complete' }));
          fetchAggregateUsage().then(setAggregateUsage).catch(() => {});
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
  // Extraction actions
  // ---------------------------------------------------------------------------

  async function startDocExtraction(docName: string) {
    const key = jk(mode, docName);
    if (taskStatusesRef.current[key] === 'running') return;

    try {
      const { task_id } = await startExtraction(mode, docName);
      taskMapRef.current[key] = task_id;
      setTaskStatuses((prev) => ({ ...prev, [key]: 'running' }));

      // If this is the currently selected doc, subscribe to SSE
      if (docName === selectedDoc) {
        resetResults();
        setIsCached(false);
        setSteps(getSteps(mode, propertyEnrichmentConfigured));
        setIsRunning(true);
        subscribeToDoc(task_id, mode, docName);
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
    const key = jk(mode, docName);
    const taskId = taskMapRef.current[key];

    if (taskId && taskStatusesRef.current[key]) {
      // Has a task — subscribe to SSE to replay all events
      resetResults();
      setSteps(getSteps(mode, propertyEnrichmentConfigured));
      setIsCached(false);
      if (taskStatusesRef.current[key] === 'running') setIsRunning(true);
      subscribeToDoc(taskId, mode, docName);
    } else {
      // No task — check cache
      resetResults();
      setSteps(getSteps(mode, propertyEnrichmentConfigured));
      checkDocCache(docName);
    }
  }

  // ---------------------------------------------------------------------------
  // Mode switching
  // ---------------------------------------------------------------------------

  function handleModeChange(newMode: Mode) {
    if (newMode === mode) return;

    // Remember selected doc for current mode
    modeDocRef.current[mode] = selectedDoc;

    // Unsubscribe from current SSE
    if (currentAbortRef.current) {
      currentAbortRef.current();
      currentAbortRef.current = null;
    }

    // Reset
    resetResults();
    setIsRunning(false);
    setSelectedDoc(null);
    setSelectedDocs(new Set());
    setMode(newMode);
  }

  // ---------------------------------------------------------------------------
  // Cache check
  // ---------------------------------------------------------------------------

  async function checkDocCache(docName: string) {
    setCheckingCache(true);
    try {
      const resp = await fetch(getDocumentUrl(docName));
      if (!resp.ok) return;
      const blob = await resp.blob();
      const file = new File([blob], docName);
      const hash = await computeFileHash(file);
      const cached = await checkCachedExtraction(hash, mode);
      if (cached.cached && cached.extraction) {
        const ext = cached.extraction;
        setIsCached(true);
        setExtractionId(ext.id as string);
        setExtractedData(ext.extracted_data as Record<string, unknown> | null);
        setOverallConfidence(ext.overall_confidence as number ?? null);
        if (ext.citations) setCitations(ext.citations as VerificationCitation[]);
        if (ext.pii_report) {
          const pii = ext.pii_report as PIIReport;
          setPiiFindings(pii.findings);
          setPiiRiskScore(pii.pii_risk_score);
          setPiiRiskLevel(pii.risk_level);
        }
        if (ext.compliance_report) {
          setComplianceReport(ext.compliance_report as unknown as ComplianceReport);
        }
        setValidationSuccess(ext.validation_success as boolean ?? null);
        setFinalResult({
          mode: ext.mode as string,
          source_file: docName,
          extraction_timestamp: ext.extraction_timestamp as string,
          model_used: ext.model_used as string,
          pages_processed: ext.pages_processed as number,
          dotloop_data: ext.mode === 'real_estate' ? ext.extracted_data as Record<string, unknown> : null,
          foia_data: ext.mode === 'gov' ? ext.extracted_data as Record<string, unknown> : null,
          dotloop_api_payload: ext.dotloop_api_payload as Record<string, unknown> | null,
          docusign_api_payload: ext.docusign_api_payload as Record<string, unknown> | null,
          citations: (ext.citations ?? []) as VerificationCitation[],
          overall_confidence: ext.overall_confidence as number,
          pii_report: ext.pii_report as PIIReport | null ?? null,
          compliance_report: ext.compliance_report as unknown as ComplianceReport | null ?? null,
          extraction_id: ext.id as string,
          prompt_tokens: ext.prompt_tokens as number ?? 0,
          completion_tokens: ext.completion_tokens as number ?? 0,
          total_tokens: ext.total_tokens as number ?? 0,
          cost_usd: ext.cost_usd as number ?? 0,
        });
        setSteps(prev => prev.map(s => ({ ...s, status: 'complete' as StepStatus })));
      }
    } catch {
      // Cache check is best-effort
    } finally {
      setCheckingCache(false);
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
      setSteps(getSteps(mode, propertyEnrichmentConfigured));
      checkDocCache(result.name);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }

  // ---------------------------------------------------------------------------
  // Dotloop sync
  // ---------------------------------------------------------------------------

  async function handleDotloopSync() {
    if (!extractionId || isSyncing) return;
    setIsSyncing(true);
    setSyncError(null);
    setSyncResult(null);
    try {
      const result = await syncToDotloop(extractionId, selectedLoopId ?? undefined);
      setSyncResult(result);
    } catch (err) {
      setSyncError(err instanceof Error ? err.message : 'Sync failed');
    } finally {
      setIsSyncing(false);
    }
  }

  // ---------------------------------------------------------------------------
  // DocuSign sync
  // ---------------------------------------------------------------------------

  async function handleDocuSignSync() {
    if (!extractionId || isDocusignSyncing) return;
    setIsDocusignSyncing(true);
    setDocusignSyncError(null);
    setDocusignSyncResult(null);
    try {
      const result = await syncToDocuSign(extractionId, selectedEnvelopeId ?? undefined);
      setDocusignSyncResult(result);
    } catch (err) {
      setDocusignSyncError(err instanceof Error ? err.message : 'Sync failed');
    } finally {
      setIsDocusignSyncing(false);
    }
  }

  async function handleVoidEnvelope(envelopeId: string) {
    try {
      await voidDocuSignEnvelope(envelopeId);
      setDocusignEnvelopes((prev) => prev.filter((e) => e.envelopeId !== envelopeId));
      if (selectedEnvelopeId === envelopeId) setSelectedEnvelopeId(null);
    } catch (err) {
      setDocusignSyncError(err instanceof Error ? err.message : 'Delete failed');
    }
  }

  function loadDocuSignEnvelopes() {
    setLoadingEnvelopes(true);
    fetchDocuSignEnvelopes()
      .then(setDocusignEnvelopes)
      .catch(() => setDocusignEnvelopes([]))
      .finally(() => setLoadingEnvelopes(false));
  }

  // ---------------------------------------------------------------------------
  // Cache clear
  // ---------------------------------------------------------------------------

  async function handleClearCache() {
    try {
      await clearExtractionCache(mode);
      if (isCached) {
        setIsCached(false);
        resetResults();
        setSteps(getSteps(mode, propertyEnrichmentConfigured));
      }
    } catch {
      setErrorMessage('Failed to clear cache');
    }
  }

  // ---------------------------------------------------------------------------
  // Effects
  // ---------------------------------------------------------------------------

  // Mount: check integrations, load usage, reconnect to running tasks
  useEffect(() => {
    checkDotloopStatus().then(setDotloopConfigured);
    checkDocuSignStatus().then(setDocusignConfigured);
    checkPropertyEnrichmentStatus().then(setPropertyEnrichmentConfigured);
    fetchAggregateUsage().then(setAggregateUsage).catch(() => {});

    // Reconnect to any active extraction tasks
    fetchActiveTasks().then((tasks) => {
      for (const task of tasks) {
        const taskMode = task.mode as Mode;
        const key = jk(taskMode, task.filename);
        taskMapRef.current[key] = task.task_id;
        setTaskStatuses((prev) => ({ ...prev, [key]: 'running' }));

        // If matches current mode, subscribe to the first one
        if (taskMode === mode) {
          setSelectedDoc(task.filename);
          setIsRunning(true);
          setSteps(getSteps(taskMode, propertyEnrichmentConfigured));
          subscribeToDoc(task.task_id, taskMode, task.filename);
        }
      }
    }).catch(() => {});

    // Handle OAuth redirects
    const params = new URLSearchParams(window.location.search);
    if (params.get('dotloop_connected') === 'true') {
      checkDotloopStatus().then(setDotloopConfigured);
      window.history.replaceState({}, '', window.location.pathname);
    }
    if (params.get('dotloop_error')) {
      setSyncError(`Dotloop connection failed: ${params.get('dotloop_error')}`);
      window.history.replaceState({}, '', window.location.pathname);
    }
    if (params.get('docusign_connected') === 'true') {
      checkDocuSignStatus().then(setDocusignConfigured);
      window.history.replaceState({}, '', window.location.pathname);
    }
    if (params.get('docusign_error')) {
      setDocusignSyncError(`DocuSign connection failed: ${params.get('docusign_error')}`);
      window.history.replaceState({}, '', window.location.pathname);
    }
  }, []);

  // Load documents when mode changes
  useEffect(() => {
    setLoadingDocs(true);
    resetResults();
    setSteps(getSteps(mode, propertyEnrichmentConfigured));
    setSelectedDocs(new Set());

    fetchDocuments(mode).then((docs) => {
      setDocuments(docs);

      // Restore previously selected doc for this mode, or pick first
      const prevDoc = modeDocRef.current[mode];
      const docToSelect = prevDoc && docs.some((d) => d.name === prevDoc)
        ? prevDoc
        : docs.length > 0 ? docs[0].name : null;

      setSelectedDoc(docToSelect);

      if (docToSelect) {
        const key = jk(mode, docToSelect);
        const taskId = taskMapRef.current[key];

        if (taskId) {
          // Resubscribe — SSE replays all events
          setIsCached(false);
          if (taskStatusesRef.current[key] === 'running') setIsRunning(true);
          subscribeToDoc(taskId, mode, docToSelect);
        } else {
          checkDocCache(docToSelect);
        }
      }
    }).catch(() => {
      setDocuments([]);
      setSelectedDoc(null);
    }).finally(() => setLoadingDocs(false));
  }, [mode]);

  // Load Dotloop loops when extraction completes
  useEffect(() => {
    if (dotloopConfigured && mode === 'real_estate' && finalResult && extractionId) {
      setLoadingLoops(true);
      fetchDotloopLoops()
        .then(setDotloopLoops)
        .catch(() => setDotloopLoops([]))
        .finally(() => setLoadingLoops(false));
    }
  }, [dotloopConfigured, mode, finalResult, extractionId]);

  // Load DocuSign envelopes
  useEffect(() => {
    if (docusignConfigured && mode === 'real_estate') {
      loadDocuSignEnvelopes();
    }
  }, [docusignConfigured, mode]);

  // Refresh envelopes after sync
  useEffect(() => {
    if (docusignSyncResult && docusignConfigured) {
      loadDocuSignEnvelopes();
    }
  }, [docusignSyncResult]);

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
            const key = jk(task.mode as Mode, task.filename);
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
  const backgroundRunningCount = Object.entries(taskStatuses).filter(
    ([key, status]) => status === 'running' && !key.startsWith(mode + ':'),
  ).length;
  const currentModeRunningCount = Object.entries(taskStatuses).filter(
    ([key, status]) => status === 'running' && key.startsWith(mode + ':') &&
      key !== jk(mode, selectedDoc || ''),
  ).length;
  const totalBackgroundRunning = backgroundRunningCount + currentModeRunningCount;

  // --- Render ---

  // Auth gate: when Clerk is enabled, show sign-in for unauthenticated users
  if (CLERK_ENABLED) {
    return (
      <>
        <AuthTokenWiring />
        <SignedOut>
          <div className="auth-gate">
            <div className="auth-gate-inner">
              <span className="auth-gate-title">D.E.S.</span>
              <span className="auth-gate-subtitle">Document Extract System</span>
              <SignIn />
            </div>
          </div>
        </SignedOut>
        <SignedIn>
          {renderMainApp()}
        </SignedIn>
      </>
    );
  }

  return renderMainApp();

  /* eslint-disable-next-line no-unreachable */
  function renderMainApp() { return (<div className="app">
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
          {mode === 'real_estate' && (
            <div className="view-toggle">
              <button
                className={`view-btn ${activeView === 'extraction' ? 'active' : ''}`}
                onClick={() => setActiveView('extraction')}
              >
                Extract
              </button>
              <button
                className={`view-btn ${activeView === 'loops' ? 'active' : ''}`}
                onClick={() => setActiveView('loops')}
              >
                Loops
              </button>
              <button
                className={`view-btn ${activeView === 'compare' ? 'active' : ''}`}
                onClick={() => setActiveView('compare')}
              >
                Compare
              </button>
            </div>
          )}
        </div>
        <div className="header-right">
          <span className="header-subtitle">Neural OCR + Pydantic Validation</span>
          {CLERK_ENABLED && (
            <div className="header-auth">
              <OrganizationSwitcher />
              <UserButton />
            </div>
          )}
        </div>
      </header>

      {/* Loops Browser View */}
      {activeView === 'loops' && mode === 'real_estate' && (
        <LoopBrowser
          dotloopConfigured={dotloopConfigured}
          docusignConfigured={docusignConfigured}
          onCompare={(fromId, toId) => {
            setCompareFromId(fromId);
            setCompareToId(toId);
            setActiveView('compare');
          }}
        />
      )}

      {/* Comparison View */}
      {activeView === 'compare' && mode === 'real_estate' && (
        <ComparisonView
          initialFromId={compareFromId}
          initialToId={compareToId}
        />
      )}

      {/* Extraction View (original) */}
      {(activeView === 'extraction' || mode === 'gov') && <div className="main">
        {/* Left Panel */}
        <div className="left-panel">
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
                  const key = jk(mode, doc.name);
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
                            {doc.size_human} &middot; {doc.pages} page{doc.pages !== 1 ? 's' : ''}
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
                      (d) => taskStatusesRef.current[jk(mode, d)] === 'running',
                    )}
                  >
                    Extract Selected ({selectedDocs.size})
                  </button>
                )}
                <button
                  className="batch-btn"
                  onClick={handleExtractAll}
                  disabled={documents.every(
                    (d) => taskStatusesRef.current[jk(mode, d.name)] === 'running',
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

          {/* Cached Badge */}
          {isCached && (
            <div className="cached-banner">
              <span className="cached-badge">CACHED</span>
              <span className="cached-text">Loaded from previous extraction</span>
              <button
                className="cached-reextract"
                disabled={isRunning}
                onClick={() => {
                  setIsCached(false);
                  resetResults();
                  setSteps(getSteps(mode, propertyEnrichmentConfigured));
                  handleRun();
                }}
              >
                Re-extract
              </button>
              <button
                className="cached-reextract"
                onClick={handleClearCache}
              >
                Clear Cache
              </button>
            </div>
          )}

          {/* Checking cache spinner */}
          {checkingCache && !isCached && !isRunning && !finalResult && (
            <div className="cached-banner">
              <span className="spinner" /> Checking cache...
            </div>
          )}

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

          {/* API Usage — per-extraction cost */}
          {finalResult && finalResult.total_tokens > 0 && (
            <div className="usage-section">
              <div className="usage-row">
                <span className="usage-label">Tokens</span>
                <span className="usage-value">
                  {finalResult.prompt_tokens.toLocaleString()} in / {finalResult.completion_tokens.toLocaleString()} out
                </span>
              </div>
              <div className="usage-row">
                <span className="usage-label">Cost</span>
                <span className="usage-value usage-cost">${finalResult.cost_usd.toFixed(4)}</span>
              </div>
            </div>
          )}

          {/* Aggregate Usage Banner */}
          {aggregateUsage && aggregateUsage.total_extractions > 0 && (
            <div className="usage-aggregate">
              <div className="usage-aggregate-title">Running Totals</div>
              <div className="usage-aggregate-grid">
                <div className="usage-stat">
                  <span className="usage-stat-value">{aggregateUsage.total_extractions}</span>
                  <span className="usage-stat-label">Extractions</span>
                </div>
                <div className="usage-stat">
                  <span className="usage-stat-value">{(aggregateUsage.total_tokens / 1000).toFixed(1)}k</span>
                  <span className="usage-stat-label">Tokens</span>
                </div>
                <div className="usage-stat">
                  <span className="usage-stat-value">${aggregateUsage.total_cost_usd.toFixed(4)}</span>
                  <span className="usage-stat-label">Total Spend</span>
                </div>
                <div className="usage-stat">
                  <span className="usage-stat-value">${aggregateUsage.avg_cost_per_extraction.toFixed(4)}</span>
                  <span className="usage-stat-label">Avg/Extract</span>
                </div>
              </div>
            </div>
          )}

          {/* Property Enrichment — show after extraction in real_estate mode */}
          {propertyEnrichment && propertyEnrichment.match_quality !== 'none' && mode === 'real_estate' && (
            <div className="property-enrichment-section">
              <div className="property-enrichment-title">
                <span style={{ marginRight: 6 }}>&#x1F4CD;</span>
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

          {/* Dotloop Section — connect button always visible in real_estate mode */}
          {mode === 'real_estate' && !dotloopConfigured && (
            <div className="dotloop-section">
              <a href={getDotloopConnectUrl()} className="dotloop-connect-btn">
                <span className="dotloop-icon">&#x1F517;</span> Connect to Dotloop
              </a>
            </div>
          )}

          {/* Dotloop Sync — only after extraction completes */}
          {mode === 'real_estate' && dotloopConfigured && finalResult && extractionId && (
            <div className="dotloop-section">
              {!syncResult && !syncError && (
                <div className="dotloop-loop-selector">
                  <label className="dotloop-label">Target Loop</label>
                  {loadingLoops ? (
                    <div style={{ padding: 8, textAlign: 'center' }}>
                      <span className="spinner" />
                    </div>
                  ) : (
                    <select
                      className="dotloop-select"
                      value={selectedLoopId ?? ''}
                      onChange={(e) =>
                        setSelectedLoopId(e.target.value ? Number(e.target.value) : null)
                      }
                    >
                      <option value="">+ Create New Loop</option>
                      {dotloopLoops.map((loop) => (
                        <option key={loop.id} value={loop.id}>
                          {loop.name} ({loop.status || 'unknown'})
                        </option>
                      ))}
                    </select>
                  )}
                </div>
              )}
              {!syncResult && !syncError && (
                <button
                  className={`dotloop-sync-btn ${isSyncing ? 'syncing' : ''}`}
                  disabled={isSyncing || loadingLoops}
                  onClick={handleDotloopSync}
                >
                  {isSyncing ? (
                    <><span className="spinner" /> Syncing to Dotloop...</>
                  ) : (
                    <><span className="dotloop-icon">&#x21C4;</span> Sync to Dotloop</>
                  )}
                </button>
              )}
              {syncResult && (
                <div className="dotloop-success">
                  <span className="dotloop-check">&#x2713;</span>
                  {syncResult.action} loop in Dotloop
                  {syncResult.document_uploaded && syncResult.document_name && (
                    <span className="dotloop-doc-uploaded"> &middot; Uploaded {syncResult.document_name}</span>
                  )}
                  {syncResult.loop_url && (
                    <a href={syncResult.loop_url} target="_blank" rel="noopener noreferrer" className="dotloop-link">
                      Open in Dotloop &#x2192;
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
                  <button className="dotloop-retry" onClick={handleDotloopSync}>Retry</button>
                </div>
              )}
            </div>
          )}

          {/* DocuSign Section — connect button when not configured */}
          {mode === 'real_estate' && !docusignConfigured && (
            <div className="dotloop-section">
              <a href={getDocuSignConnectUrl()} className="dotloop-connect-btn">
                <span className="dotloop-icon">&#x1F4DD;</span> Connect to DocuSign
              </a>
            </div>
          )}

          {/* DocuSign — always visible when configured in real_estate mode */}
          {mode === 'real_estate' && docusignConfigured && (
            <div className="dotloop-section">
              <div className="dotloop-loop-selector">
                <label className="dotloop-label">
                  DocuSign Envelopes
                  {!loadingEnvelopes && docusignEnvelopes.length > 0 && (
                    <span style={{ fontWeight: 400, color: 'var(--text-muted)', marginLeft: 6 }}>
                      ({docusignEnvelopes.length})
                    </span>
                  )}
                </label>
                {loadingEnvelopes ? (
                  <div style={{ padding: 8, textAlign: 'center' }}>
                    <span className="spinner" />
                  </div>
                ) : docusignEnvelopes.length === 0 ? (
                  <div style={{ padding: '8px 0', color: 'var(--text-muted)', fontSize: 12 }}>
                    No envelopes found
                  </div>
                ) : (
                  <div className="docusign-envelope-list">
                    {docusignEnvelopes.map((env) => (
                      <div
                        key={env.envelopeId}
                        className={`docusign-envelope-item ${selectedEnvelopeId === env.envelopeId ? 'selected' : ''}`}
                        onClick={() => setSelectedEnvelopeId(
                          selectedEnvelopeId === env.envelopeId ? null : env.envelopeId
                        )}
                      >
                        <div className="docusign-envelope-info">
                          <div className="docusign-envelope-subject">
                            {env.emailSubject || 'Untitled'}
                          </div>
                          <div className="docusign-envelope-meta">
                            <span className={`docusign-status-badge ${env.status}`}>
                              {env.status}
                            </span>
                            {env.createdDateTime && (
                              <span className="docusign-envelope-date">
                                {new Date(env.createdDateTime).toLocaleDateString()}
                              </span>
                            )}
                          </div>
                        </div>
                        <button
                          className="docusign-delete-btn"
                          title={env.status === 'created' ? 'Delete draft' : 'Void envelope'}
                          onClick={(e) => {
                            e.stopPropagation();
                            if (confirm(`${env.status === 'created' ? 'Delete' : 'Void'} this envelope?`)) {
                              handleVoidEnvelope(env.envelopeId);
                            }
                          }}
                        >
                          &#x2715;
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {finalResult && extractionId && !docusignSyncResult && !docusignSyncError && (
                <button
                  className={`dotloop-sync-btn ${isDocusignSyncing ? 'syncing' : ''}`}
                  disabled={isDocusignSyncing || loadingEnvelopes}
                  onClick={handleDocuSignSync}
                >
                  {isDocusignSyncing ? (
                    <><span className="spinner" /> Syncing to DocuSign...</>
                  ) : selectedEnvelopeId ? (
                    <><span className="dotloop-icon">&#x21C4;</span> Update Selected Envelope</>
                  ) : (
                    <><span className="dotloop-icon">&#x21C4;</span> Create New Envelope</>
                  )}
                </button>
              )}

              {docusignSyncResult && (
                <div className="dotloop-success">
                  <span className="dotloop-check">&#x2713;</span>
                  {docusignSyncResult.action} envelope in DocuSign
                  {docusignSyncResult.envelope_url && (
                    <a href={docusignSyncResult.envelope_url} target="_blank" rel="noopener noreferrer" className="dotloop-link">
                      Open in DocuSign &#x2192;
                    </a>
                  )}
                  <div className="docusign-envelope-id">
                    Envelope: {docusignSyncResult.envelope_id}
                  </div>
                  {docusignSyncResult.errors.length > 0 && (
                    <div className="dotloop-warnings">
                      {docusignSyncResult.errors.map((e, i) => (
                        <div key={i} className="dotloop-warning">{e}</div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {docusignSyncError && (
                <div className="dotloop-error">
                  {docusignSyncError}
                  <button className="dotloop-retry" onClick={() => setDocusignSyncError(null)}>Dismiss</button>
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
              {complianceReport && mode === 'real_estate' && (
                <button
                  className={`tab ${activeTab === 'compliance' ? 'active' : ''}`}
                  onClick={() => setActiveTab('compliance')}
                >
                  Compliance
                  <span className={`tab-badge ${
                    complianceReport.overall_status === 'PASS' ? 'green' :
                    complianceReport.overall_status === 'ACTION_NEEDED' ? 'yellow' : 'red'
                  }`}>
                    {complianceReport.action_items}
                  </span>
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

            {activeTab === 'extraction' && extractedData && (
              <ExtractionTable data={extractedData} />
            )}
            {activeTab === 'citations' && citations && (
              <CitationsTable citations={citations} />
            )}
            {activeTab === 'compliance' && complianceReport && (
              <CompliancePanel report={complianceReport} />
            )}
            {activeTab === 'pii' && piiFindings && (
              <PIIPanel
                findings={piiFindings}
                riskScore={piiRiskScore ?? 0}
                riskLevel={piiRiskLevel ?? 'LOW'}
              />
            )}
            {activeTab === 'json' && finalResult && (
              <JSONOutput data={finalResult} />
            )}
          </div>
        </div>
      </div>}
    </div>
  ); }
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

function categoryIcon(cat: string): string {
  switch (cat) {
    case 'FORM': return '\uD83D\uDCDD';
    case 'INSPECTION': return '\uD83D\uDD0D';
    case 'DISCLOSURE': return '\uD83D\uDCCB';
    case 'CERTIFICATE': return '\u2705';
    case 'FEE': return '\uD83D\uDCB0';
    default: return '\u25CF';
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case 'REQUIRED': return 'Required';
    case 'LIKELY_REQUIRED': return 'Likely Required';
    case 'NOT_REQUIRED': return 'Not Required';
    default: return 'Unknown';
  }
}

function statusClass(status: string): string {
  switch (status) {
    case 'REQUIRED': return 'required';
    case 'LIKELY_REQUIRED': return 'likely';
    case 'NOT_REQUIRED': return 'not-required';
    default: return 'unknown';
  }
}

function CompliancePanel({ report }: { report: ComplianceReport }) {
  return (
    <div className="compliance-panel">
      <div className={`compliance-banner ${report.overall_status}`}>
        <div className="compliance-banner-main">
          <span className="compliance-banner-icon">
            {report.overall_status === 'PASS' ? '\u2705' :
             report.overall_status === 'ACTION_NEEDED' ? '\u26A0\uFE0F' : '\u2753'}
          </span>
          <div>
            <div className="compliance-jurisdiction">{report.jurisdiction_display}</div>
            <div className="compliance-status-text">
              {report.overall_status === 'PASS' && 'All requirements identified — no action items.'}
              {report.overall_status === 'ACTION_NEEDED' && `${report.action_items} action item${report.action_items !== 1 ? 's' : ''} identified`}
              {report.overall_status === 'UNKNOWN_JURISDICTION' && 'Jurisdiction not in compliance database.'}
            </div>
          </div>
        </div>
        {report.notes && (
          <div className="compliance-banner-notes">{report.notes}</div>
        )}
      </div>

      {report.requirements.length > 0 && (
        <div className="compliance-list">
          {report.requirements.map((req: ComplianceRequirement, i: number) => (
            <div key={i} className={`compliance-item ${statusClass(req.status)}`}>
              <div className="compliance-item-header">
                <span className="compliance-category-icon">{categoryIcon(req.category)}</span>
                <div className="compliance-item-title">
                  <span className="compliance-item-name">{req.name}</span>
                  {req.code && <span className="compliance-code">{req.code}</span>}
                </div>
                <span className={`compliance-status-badge ${statusClass(req.status)}`}>
                  {statusLabel(req.status)}
                </span>
              </div>
              <div className="compliance-item-body">
                <p className="compliance-description">{req.description}</p>
                <div className="compliance-meta">
                  {req.authority && (
                    <span className="compliance-meta-item">
                      <span className="compliance-meta-label">Authority:</span> {req.authority}
                    </span>
                  )}
                  {req.fee && (
                    <span className="compliance-meta-item">
                      <span className="compliance-meta-label">Fee:</span> {req.fee}
                    </span>
                  )}
                  {req.url && (
                    <a href={req.url} target="_blank" rel="noopener noreferrer" className="compliance-meta-link">
                      Reference &#x2192;
                    </a>
                  )}
                </div>
                {req.notes && (
                  <p className="compliance-notes">{req.notes}</p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {report.requirements.length === 0 && report.overall_status !== 'UNKNOWN_JURISDICTION' && (
        <div style={{ color: 'var(--green)', padding: 20, textAlign: 'center' }}>
          No specific requirements found for this jurisdiction.
        </div>
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

// ---------------------------------------------------------------------------
// Loop Browser — unified Dotloop + DocuSign browser
// ---------------------------------------------------------------------------

interface LoopBrowserProps {
  dotloopConfigured: boolean;
  docusignConfigured: boolean;
  onCompare: (fromId: string, toId: string) => void;
}

interface UnifiedLoopItem {
  id: string;
  source: 'dotloop' | 'docusign';
  name: string;
  propertyAddress?: string;
  transactionType?: string;
  status?: string;
  updated?: string;
  documentCount?: number;
}

function LoopBrowser({ dotloopConfigured, docusignConfigured, onCompare }: LoopBrowserProps) {
  const [items, setItems] = useState<UnifiedLoopItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [selectedItems, setSelectedItems] = useState<Set<string>>(new Set());
  const [expandedItem, setExpandedItem] = useState<string | null>(null);
  const [loopDetail, setLoopDetail] = useState<LoopDetail | null>(null);
  const [envelopeDetail, setEnvelopeDetail] = useState<EnvelopeDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [extractionIds, setExtractionIds] = useState<Record<string, string>>({});
  const [extractError, setExtractError] = useState<string | null>(null);

  // Load initial items
  useEffect(() => {
    loadItems();
  }, [dotloopConfigured, docusignConfigured]);

  async function loadItems() {
    setLoading(true);
    const unified: UnifiedLoopItem[] = [];

    try {
      if (dotloopConfigured) {
        const loops = await fetchDotloopLoops();
        for (const loop of loops) {
          unified.push({
            id: `dl-${loop.id}`,
            source: 'dotloop',
            name: loop.name,
            transactionType: loop.transactionType,
            status: loop.status,
            updated: loop.updated,
          });
        }
      }
    } catch { /* ignore */ }

    try {
      if (docusignConfigured) {
        const envelopes = await fetchDocuSignEnvelopes();
        for (const env of envelopes) {
          unified.push({
            id: `ds-${env.envelopeId}`,
            source: 'docusign',
            name: env.emailSubject || 'Untitled',
            status: env.status,
            updated: env.createdDateTime,
          });
        }
      }
    } catch { /* ignore */ }

    setItems(unified);
    setLoading(false);
  }

  async function handleSearch() {
    if (!searchQuery.trim()) {
      loadItems();
      return;
    }
    setSearching(true);
    const unified: UnifiedLoopItem[] = [];
    const q = searchQuery.trim().toLowerCase();

    try {
      if (dotloopConfigured) {
        const loops = await searchDotloopLoops(searchQuery);
        for (const loop of loops) {
          unified.push({
            id: `dl-${loop.id}`,
            source: 'dotloop',
            name: loop.name,
            transactionType: loop.transactionType,
            status: loop.status,
            updated: loop.updated,
          });
        }
      }
    } catch { /* ignore */ }

    // Client-side filter DocuSign
    try {
      if (docusignConfigured) {
        const envelopes = await fetchDocuSignEnvelopes();
        for (const env of envelopes) {
          const subject = (env.emailSubject || '').toLowerCase();
          if (subject.includes(q)) {
            unified.push({
              id: `ds-${env.envelopeId}`,
              source: 'docusign',
              name: env.emailSubject || 'Untitled',
              status: env.status,
              updated: env.createdDateTime,
            });
          }
        }
      }
    } catch { /* ignore */ }

    setItems(unified);
    setSearching(false);
  }

  async function handleExpand(item: UnifiedLoopItem) {
    if (expandedItem === item.id) {
      setExpandedItem(null);
      setLoopDetail(null);
      setEnvelopeDetail(null);
      return;
    }
    setExpandedItem(item.id);
    setLoadingDetail(true);
    setLoopDetail(null);
    setEnvelopeDetail(null);

    try {
      if (item.source === 'dotloop') {
        const rawId = parseInt(item.id.replace('dl-', ''));
        const detail = await fetchLoopDetail(rawId);
        setLoopDetail(detail);
      } else {
        const rawId = item.id.replace('ds-', '');
        const detail = await fetchEnvelopeDetail(rawId);
        setEnvelopeDetail(detail);
      }
    } catch {
      // ignore
    } finally {
      setLoadingDetail(false);
    }
  }

  function toggleSelect(id: string) {
    setSelectedItems(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleExtractSelected() {
    if (selectedItems.size === 0) return;
    setExtracting(true);
    setExtractError(null);

    const sources: BatchSource[] = [];
    for (const id of selectedItems) {
      if (id.startsWith('dl-')) {
        sources.push({ type: 'dotloop', id: id.replace('dl-', '') });
      } else if (id.startsWith('ds-')) {
        sources.push({ type: 'docusign', id: id.replace('ds-', '') });
      }
    }

    try {
      const result = await extractBatch(sources);
      const newIds: Record<string, string> = { ...extractionIds };
      for (const r of result.results) {
        const src = r.source as Record<string, string>;
        const key = src.type === 'dotloop' ? `dl-${src.id}` : `ds-${src.id}`;
        if (r.extraction_id) {
          newIds[key] = r.extraction_id as string;
        }
      }
      setExtractionIds(newIds);
    } catch (err) {
      setExtractError(err instanceof Error ? err.message : 'Extraction failed');
    } finally {
      setExtracting(false);
    }
  }

  function handleCompare() {
    const selected = [...selectedItems];
    if (selected.length !== 2) return;
    const fromId = extractionIds[selected[0]];
    const toId = extractionIds[selected[1]];
    if (!fromId || !toId) return;
    onCompare(fromId, toId);
  }

  const canCompare = selectedItems.size === 2 &&
    [...selectedItems].every(id => extractionIds[id]);

  return (
    <div className="loops-browser">
      <div className="loops-toolbar">
        <div className="loops-search">
          <input
            type="text"
            className="loops-search-input"
            placeholder="Search by property address or name..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          />
          <button
            className="loops-search-btn"
            onClick={handleSearch}
            disabled={searching}
          >
            {searching ? <span className="spinner" /> : 'Search'}
          </button>
        </div>
        <div className="loops-actions">
          {selectedItems.size > 0 && (
            <button
              className="loops-extract-btn"
              onClick={handleExtractSelected}
              disabled={extracting}
            >
              {extracting ? (
                <><span className="spinner" /> Extracting...</>
              ) : (
                <>Extract Selected ({selectedItems.size})</>
              )}
            </button>
          )}
          {canCompare && (
            <button className="loops-compare-btn" onClick={handleCompare}>
              Compare Selected
            </button>
          )}
        </div>
      </div>

      {extractError && (
        <div className="loops-error">{extractError}</div>
      )}

      {!dotloopConfigured && !docusignConfigured && (
        <div className="loops-empty">
          <div className="loops-empty-icon">&#x1F517;</div>
          <div>Connect Dotloop or DocuSign to browse your loops and envelopes</div>
          <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
            <a href={getDotloopConnectUrl()} className="dotloop-connect-btn" style={{ flex: 1 }}>
              Connect Dotloop
            </a>
            <a href={getDocuSignConnectUrl()} className="dotloop-connect-btn" style={{ flex: 1 }}>
              Connect DocuSign
            </a>
          </div>
        </div>
      )}

      {loading ? (
        <div className="loops-loading"><span className="spinner" /> Loading...</div>
      ) : items.length === 0 ? (
        <div className="loops-empty">
          <div className="loops-empty-icon">&mdash;</div>
          <div>{searchQuery ? 'No results found' : 'No loops or envelopes found'}</div>
        </div>
      ) : (
        <div className="loops-list">
          {items.map(item => (
            <div key={item.id} className={`loops-item ${selectedItems.has(item.id) ? 'selected' : ''}`}>
              <div className="loops-item-row">
                <input
                  type="checkbox"
                  className="doc-checkbox"
                  checked={selectedItems.has(item.id)}
                  onChange={() => toggleSelect(item.id)}
                  onClick={e => e.stopPropagation()}
                />
                <div
                  className="loops-item-content"
                  onClick={() => handleExpand(item)}
                >
                  <span className={`loops-source-badge ${item.source}`}>
                    {item.source === 'dotloop' ? 'DL' : 'DS'}
                  </span>
                  <div className="loops-item-info">
                    <div className="loops-item-name">{item.name}</div>
                    <div className="loops-item-meta">
                      {item.transactionType && <span>{item.transactionType}</span>}
                      {item.status && (
                        <span className={`loops-status-badge ${item.status?.toLowerCase()}`}>
                          {item.status}
                        </span>
                      )}
                      {item.updated && (
                        <span className="loops-item-date">
                          {new Date(item.updated).toLocaleDateString()}
                        </span>
                      )}
                    </div>
                  </div>
                  {extractionIds[item.id] && (
                    <span className="doc-status-badge complete" title="Extracted">&#x2713;</span>
                  )}
                  <span className="loops-expand-icon">
                    {expandedItem === item.id ? '\u25B2' : '\u25BC'}
                  </span>
                </div>
              </div>

              {/* Expanded detail */}
              {expandedItem === item.id && (
                <div className="loops-detail">
                  {loadingDetail ? (
                    <div style={{ padding: 12, textAlign: 'center' }}><span className="spinner" /></div>
                  ) : loopDetail ? (
                    <LoopDetailPanel detail={loopDetail} />
                  ) : envelopeDetail ? (
                    <EnvelopeDetailPanel detail={envelopeDetail} />
                  ) : (
                    <div style={{ padding: 12, color: 'var(--text-muted)' }}>Failed to load details</div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function LoopDetailPanel({ detail }: { detail: LoopDetail }) {
  const addr = detail.property_address;
  const addressStr = addr
    ? [addr.street_number, addr.street_name, addr.city, addr.state_or_province, addr.postal_code]
        .filter(Boolean).join(', ')
    : null;

  return (
    <div className="loop-detail-panel">
      {addressStr && (
        <div className="loop-detail-field">
          <span className="loop-detail-label">Property</span>
          <span className="loop-detail-value">{addressStr}</span>
        </div>
      )}
      {detail.transaction_type && (
        <div className="loop-detail-field">
          <span className="loop-detail-label">Type</span>
          <span className="loop-detail-value">{detail.transaction_type}</span>
        </div>
      )}
      {detail.financials && Object.keys(detail.financials).length > 0 && (
        <div className="loop-detail-section">
          <div className="loop-detail-section-title">Financials</div>
          {Object.entries(detail.financials).map(([k, v]) => v != null && (
            <div key={k} className="loop-detail-field">
              <span className="loop-detail-label">{k.replace(/_/g, ' ')}</span>
              <span className="loop-detail-value">{String(v)}</span>
            </div>
          ))}
        </div>
      )}
      {detail.participants && detail.participants.length > 0 && (
        <div className="loop-detail-section">
          <div className="loop-detail-section-title">Participants</div>
          {detail.participants.map((p, i) => (
            <div key={i} className="loop-detail-field">
              <span className="loop-detail-label">{p.role || 'Unknown'}</span>
              <span className="loop-detail-value">{p.name || p.email || '—'}</span>
            </div>
          ))}
        </div>
      )}
      {detail.documents && detail.documents.length > 0 && (
        <div className="loop-detail-section">
          <div className="loop-detail-section-title">Documents ({detail.documents.length})</div>
          {detail.documents.map((doc, i) => (
            <div key={i} className="loop-detail-doc">
              <span className="doc-icon" style={{ fontSize: 14 }}>PDF</span>
              <span>{doc.name}</span>
              {doc.folder && <span className="loop-detail-folder">{doc.folder}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function EnvelopeDetailPanel({ detail }: { detail: EnvelopeDetail }) {
  return (
    <div className="loop-detail-panel">
      <div className="loop-detail-field">
        <span className="loop-detail-label">Status</span>
        <span className={`docusign-status-badge ${detail.status}`}>{detail.status}</span>
      </div>
      {detail.created && (
        <div className="loop-detail-field">
          <span className="loop-detail-label">Created</span>
          <span className="loop-detail-value">{new Date(detail.created).toLocaleString()}</span>
        </div>
      )}
      {detail.recipients && detail.recipients.length > 0 && (
        <div className="loop-detail-section">
          <div className="loop-detail-section-title">Recipients</div>
          {detail.recipients.map((r, i) => (
            <div key={i} className="loop-detail-field">
              <span className="loop-detail-label">{String(r.role || r.recipientType || 'Signer')}</span>
              <span className="loop-detail-value">{String(r.name || r.email || '—')}</span>
            </div>
          ))}
        </div>
      )}
      {detail.documents && detail.documents.length > 0 && (
        <div className="loop-detail-section">
          <div className="loop-detail-section-title">Documents ({detail.documents.length})</div>
          {detail.documents.map((doc, i) => (
            <div key={i} className="loop-detail-doc">
              <span className="doc-icon" style={{ fontSize: 14 }}>PDF</span>
              <span>{String(doc.name || 'Untitled')}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Comparison View — side-by-side delta table
// ---------------------------------------------------------------------------

interface ComparisonViewProps {
  initialFromId: string;
  initialToId: string;
}

function formatExtractionLabel(ext: ExtractionSummary): string {
  const badge = ext.source === 'dotloop' ? 'DL: ' : ext.source === 'docusign' ? 'DS: ' : '';
  const conf = Math.round(ext.overall_confidence * 100);
  return `${badge}${ext.filename} (${ext.pages_processed}p, ${conf}%)`;
}

function ComparisonView({ initialFromId, initialToId }: ComparisonViewProps) {
  const [fromId, setFromId] = useState(initialFromId);
  const [toId, setToId] = useState(initialToId);
  const [extractions, setExtractions] = useState<ExtractionSummary[]>([]);
  const [comparison, setComparison] = useState<ComparisonResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filterSig, setFilterSig] = useState<FieldSignificance | 'all'>('all');

  // Load available extractions for dropdowns
  useEffect(() => {
    fetchExtractions('real_estate')
      .then(setExtractions)
      .catch(() => {}); // silent fail — dropdowns just stay empty
  }, []);

  useEffect(() => {
    setFromId(initialFromId);
    setToId(initialToId);
  }, [initialFromId, initialToId]);

  // Auto-compare if both IDs are provided
  useEffect(() => {
    if (fromId && toId) {
      runComparison();
    }
  }, []);

  async function runComparison() {
    if (!fromId || !toId) {
      setError('Please select both documents');
      return;
    }
    setLoading(true);
    setError(null);
    setComparison(null);

    try {
      const result = await compareExtractions(fromId, toId);
      setComparison(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Comparison failed');
    } finally {
      setLoading(false);
    }
  }

  const filteredDeltas = comparison?.deltas.filter(d =>
    filterSig === 'all' || d.significance === filterSig
  ) || [];

  return (
    <div className="comparison-view">
      {/* Document selector bar */}
      <div className="comparison-inputs">
        <div className="comparison-input-group">
          <label className="comparison-input-label">Base Document (From)</label>
          <select
            className="comparison-select"
            value={fromId}
            onChange={(e) => setFromId(e.target.value)}
          >
            <option value="">Select a document...</option>
            {extractions.map(ext => (
              <option key={ext.id} value={ext.id} disabled={ext.id === toId}>
                {formatExtractionLabel(ext)}
              </option>
            ))}
          </select>
        </div>
        <div className="comparison-arrow">&#x2192;</div>
        <div className="comparison-input-group">
          <label className="comparison-input-label">Compare To</label>
          <select
            className="comparison-select"
            value={toId}
            onChange={(e) => setToId(e.target.value)}
          >
            <option value="">Select a document...</option>
            {extractions.map(ext => (
              <option key={ext.id} value={ext.id} disabled={ext.id === fromId}>
                {formatExtractionLabel(ext)}
              </option>
            ))}
          </select>
        </div>
        <button
          className="comparison-run-btn"
          onClick={runComparison}
          disabled={loading || !fromId || !toId}
        >
          {loading ? <span className="spinner" /> : 'Compare'}
        </button>
      </div>

      {error && <div className="comparison-error">{error}</div>}

      {comparison && (
        <>
          {/* Summary banner */}
          <div className={`comparison-summary ${comparison.critical_count > 0 ? 'has-critical' : comparison.major_count > 0 ? 'has-major' : 'all-minor'}`}>
            <div className="comparison-summary-text">{comparison.summary}</div>
            <div className="comparison-summary-counts">
              <div className="comparison-summary-sources">
                {comparison.from_source && <span className="comparison-source-label">From: {comparison.from_source}</span>}
                {comparison.to_source && <span className="comparison-source-label">To: {comparison.to_source}</span>}
              </div>
              <span className="comparison-count critical">{comparison.critical_count} Critical</span>
              <span className="comparison-count major">{comparison.major_count} Major</span>
              <span className="comparison-count minor">{comparison.minor_count} Minor</span>
              <span className="comparison-count total">{comparison.total_changes} Total</span>
            </div>
          </div>

          {/* Filter tabs */}
          <div className="comparison-filters">
            <button
              className={`comparison-filter-btn ${filterSig === 'all' ? 'active' : ''}`}
              onClick={() => setFilterSig('all')}
            >
              All ({comparison.total_changes})
            </button>
            <button
              className={`comparison-filter-btn critical ${filterSig === 'critical' ? 'active' : ''}`}
              onClick={() => setFilterSig('critical')}
            >
              Critical ({comparison.critical_count})
            </button>
            <button
              className={`comparison-filter-btn major ${filterSig === 'major' ? 'active' : ''}`}
              onClick={() => setFilterSig('major')}
            >
              Major ({comparison.major_count})
            </button>
            <button
              className={`comparison-filter-btn minor ${filterSig === 'minor' ? 'active' : ''}`}
              onClick={() => setFilterSig('minor')}
            >
              Minor ({comparison.minor_count})
            </button>
          </div>

          {/* Delta table */}
          <div className="comparison-table-container">
            <table className="data-table comparison-table">
              <thead>
                <tr>
                  <th style={{ width: 80 }}>Severity</th>
                  <th>Field</th>
                  <th>Original</th>
                  <th style={{ width: 30 }}></th>
                  <th>New Value</th>
                  <th style={{ width: 80 }}>Change</th>
                </tr>
              </thead>
              <tbody>
                {filteredDeltas.map((delta, i) => (
                  <tr key={i} className={`comparison-row ${delta.significance}`}>
                    <td>
                      <span className={`comparison-sig-badge ${delta.significance}`}>
                        {delta.significance}
                      </span>
                    </td>
                    <td>
                      <span className="field-name">{delta.field_label}</span>
                      <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                        {delta.field_path}
                      </div>
                    </td>
                    <td>
                      <span className={`comparison-value ${delta.change_type === 'removed' ? 'removed' : delta.change_type === 'modified' ? 'from' : ''}`}>
                        {delta.original_value ?? '\u2014'}
                      </span>
                    </td>
                    <td className="comparison-arrow-cell">
                      {delta.change_type === 'added' ? '+' :
                       delta.change_type === 'removed' ? '\u2212' : '\u2192'}
                    </td>
                    <td>
                      <span className={`comparison-value ${delta.change_type === 'added' ? 'added' : delta.change_type === 'modified' ? 'to' : ''}`}>
                        {delta.new_value ?? '\u2014'}
                      </span>
                    </td>
                    <td>
                      <span className={`comparison-change-badge ${delta.change_type}`}>
                        {delta.change_type}
                      </span>
                    </td>
                  </tr>
                ))}
                {filteredDeltas.length === 0 && (
                  <tr>
                    <td colSpan={6} style={{ textAlign: 'center', padding: 24, color: 'var(--text-muted)' }}>
                      {comparison.total_changes === 0
                        ? 'No differences found between these documents'
                        : 'No changes match this filter'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      {!comparison && !loading && !error && (
        <div className="comparison-empty">
          <div className="loops-empty-icon">&#x2194;</div>
          <div>Select two documents to compare</div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
            {extractions.length > 0
              ? 'Choose documents from the dropdowns above, or use the Loops tab to extract new ones'
              : 'Use the Loops tab or Extract tab to process documents first'}
          </div>
        </div>
      )}
    </div>
  );
}


export default App;
