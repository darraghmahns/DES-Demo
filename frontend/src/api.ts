// ---------------------------------------------------------------------------
// TypeScript interfaces mirroring schemas.py
// ---------------------------------------------------------------------------

export interface DocumentInfo {
  name: string;
  size_human: string;
  pages: number;
}

export interface VerificationCitation {
  field_name: string;
  extracted_value: string;
  page_number: number;
  line_or_region: string;
  surrounding_text: string;
  confidence: number;
}

export interface PIIFinding {
  pii_type: string;
  value_redacted: string;
  severity: string;
  confidence: number;
  location: string;
  recommendation: string;
}

export interface PIIReport {
  findings: PIIFinding[];
  pii_risk_score: number;
  risk_level: string;
}

export interface ComplianceRequirement {
  name: string;
  code: string | null;
  category: string;
  description: string;
  authority: string | null;
  fee: string | null;
  url: string | null;
  status: string;
  notes: string | null;
}

export interface ComplianceReport {
  jurisdiction_key: string;
  jurisdiction_display: string;
  jurisdiction_type: string;
  overall_status: string;
  requirements: ComplianceRequirement[];
  requirement_count: number;
  action_items: number;
  transaction_type: string | null;
  notes: string | null;
}

export interface ExtractionResult {
  mode: string;
  source_file: string;
  extraction_timestamp: string;
  model_used: string;
  pages_processed: number;
  dotloop_data: Record<string, unknown> | null;
  foia_data: Record<string, unknown> | null;
  dotloop_api_payload: Record<string, unknown> | null;
  docusign_api_payload: Record<string, unknown> | null;
  citations: VerificationCitation[];
  overall_confidence: number;
  pii_report: PIIReport | null;
  compliance_report: ComplianceReport | null;
  extraction_id?: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
}

// ---------------------------------------------------------------------------
// SSE event types (kept for App.tsx compatibility)
// ---------------------------------------------------------------------------

export interface StepEvent {
  step: number;
  total: number;
  title: string;
  status: string;
}

export interface StepCompleteEvent {
  step: number;
  title: string;
  status: string;
  data: Record<string, unknown>;
}

export interface ExtractionEvent {
  validated_data: Record<string, unknown>;
}

export interface ValidationEvent {
  success: boolean;
  errors: string[];
}

export interface CitationsEvent {
  citations: VerificationCitation[];
  overall_confidence: number;
}

export interface PIIEvent {
  findings: PIIFinding[];
  risk_score: number;
  risk_level: string;
}

export interface ComplianceEvent {
  jurisdiction_key: string;
  jurisdiction_display: string;
  jurisdiction_type: string;
  overall_status: string;
  requirements: ComplianceRequirement[];
  requirement_count: number;
  action_items: number;
  transaction_type: string | null;
  notes: string | null;
}

export interface PropertyEnrichmentEvent {
  match_quality: string;
  parcel_id: string | null;
  assessed_total: number | null;
  year_built: number | null;
  lot_size_acres: number | null;
  zoning: string | null;
  owner_name: string | null;
}

export type SSEEvent =
  | { type: 'step'; data: StepEvent }
  | { type: 'step_complete'; data: StepCompleteEvent }
  | { type: 'extraction'; data: ExtractionEvent }
  | { type: 'validation'; data: ValidationEvent }
  | { type: 'citations'; data: CitationsEvent }
  | { type: 'pii'; data: PIIEvent }
  | { type: 'compliance'; data: ComplianceEvent }
  | { type: 'property_enrichment'; data: PropertyEnrichmentEvent }
  | { type: 'complete'; data: ExtractionResult }
  | { type: 'error'; data: { message: string } };

// ---------------------------------------------------------------------------
// API Base URL
// ---------------------------------------------------------------------------

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

// ---------------------------------------------------------------------------
// Auth token provider — set by App.tsx via useAuth().getToken
// ---------------------------------------------------------------------------

let _getAuthToken: (() => Promise<string | null>) | null = null;

export function setAuthTokenProvider(getter: () => Promise<string | null>) {
  _getAuthToken = getter;
}

async function authHeaders(): Promise<HeadersInit> {
  if (!_getAuthToken) return {};
  const token = await _getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// ---------------------------------------------------------------------------
// Document operations
// ---------------------------------------------------------------------------

export async function fetchDocuments(mode?: string): Promise<DocumentInfo[]> {
  const url = mode
    ? `${API_BASE}/api/documents?mode=${encodeURIComponent(mode)}`
    : `${API_BASE}/api/documents`;
  const resp = await fetch(url, { headers: { ...await authHeaders() } });
  if (!resp.ok) throw new Error(`Failed to fetch documents: ${resp.status}`);
  return resp.json();
}

export function getDocumentUrl(name: string): string {
  return `${API_BASE}/api/documents/${encodeURIComponent(name)}?t=${Date.now()}`;
}

export async function uploadFile(file: File): Promise<DocumentInfo> {
  const form = new FormData();
  form.append('file', file);

  const resp = await fetch(`${API_BASE}/api/upload?mode=real_estate`, {
    method: 'POST',
    headers: { ...await authHeaders() },
    body: form,
  });

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: 'Upload failed' }));
    throw new Error(err.detail || 'Upload failed');
  }

  const data = await resp.json();
  return {
    name: data.filename,
    size_human: data.size_human,
    pages: data.pages,
  };
}

// ---------------------------------------------------------------------------
// Extraction via task-based SSE (survives browser close)
// ---------------------------------------------------------------------------

export interface StartExtractionResult {
  task_id: string;
  status: string;
}

export async function startExtraction(
  mode: string,
  filename: string,
): Promise<StartExtractionResult> {
  const resp = await fetch(`${API_BASE}/api/extract`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...await authHeaders() },
    body: JSON.stringify({ mode, filename }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: 'Extraction failed' }));
    throw new Error(err.detail || `HTTP ${resp.status}`);
  }
  return resp.json();
}

export function subscribeToTask(
  taskId: string,
  onEvent: (event: SSEEvent) => void,
): () => void {
  const controller = new AbortController();

  (async () => {
    try {
      const resp = await fetch(`${API_BASE}/api/extract/${taskId}/stream`, {
        signal: controller.signal,
        headers: { ...await authHeaders() },
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'Stream failed' }));
        onEvent({ type: 'error', data: { message: err.detail || `HTTP ${resp.status}` } });
        return;
      }

      const reader = resp.body?.getReader();
      if (!reader) {
        onEvent({ type: 'error', data: { message: 'No response stream' } });
        return;
      }

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Split on double-newline (SSE event boundary)
        const parts = buffer.split('\n\n');
        buffer = parts.pop() || '';

        for (const part of parts) {
          if (!part.trim()) continue;
          // Skip keepalive comments
          if (part.trim().startsWith(':')) continue;

          let eventType = '';
          let eventData = '';

          for (const line of part.split('\n')) {
            if (line.startsWith('event: ')) {
              eventType = line.slice(7).trim();
            } else if (line.startsWith('data: ')) {
              eventData = line.slice(6);
            }
          }

          if (eventType && eventData) {
            try {
              const parsed = JSON.parse(eventData);
              onEvent({ type: eventType, data: parsed } as SSEEvent);
            } catch {
              // Skip malformed events
            }
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') return;
      const message = err instanceof Error ? err.message : 'Unknown error';
      onEvent({ type: 'error', data: { message } });
    }
  })();

  return () => controller.abort();
}

export interface TaskInfo {
  task_id: string;
  mode: string;
  filename: string;
  status: string;
  event_count: number;
}

export async function fetchActiveTasks(): Promise<TaskInfo[]> {
  const resp = await fetch(`${API_BASE}/api/tasks`, { headers: { ...await authHeaders() } });
  if (!resp.ok) return [];
  const data = await resp.json();
  return (data.tasks || []).filter(
    (t: TaskInfo) => t.status === 'pending' || t.status === 'running',
  );
}

export async function fetchAllTasks(): Promise<TaskInfo[]> {
  const resp = await fetch(`${API_BASE}/api/tasks`, { headers: { ...await authHeaders() } });
  if (!resp.ok) return [];
  const data = await resp.json();
  return data.tasks || [];
}

// Legacy compatibility — runExtraction now uses task-based flow
export function runExtraction(
  mode: string,
  filename: string,
  onEvent: (event: SSEEvent) => void,
): () => void {
  let unsubscribe: (() => void) | null = null;

  (async () => {
    try {
      const { task_id } = await startExtraction(mode, filename);
      unsubscribe = subscribeToTask(task_id, onEvent);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      onEvent({ type: 'error', data: { message } });
    }
  })();

  return () => {
    if (unsubscribe) unsubscribe();
  };
}

// ---------------------------------------------------------------------------
// Dotloop integration
// ---------------------------------------------------------------------------

export async function checkDotloopStatus(): Promise<boolean> {
  try {
    const resp = await fetch(`${API_BASE}/api/dotloop/status`, { headers: { ...await authHeaders() } });
    if (!resp.ok) return false;
    const data = await resp.json();
    return data.configured === true;
  } catch {
    return false;
  }
}

export function getDotloopConnectUrl(): string {
  return `${API_BASE}/api/dotloop/oauth/connect`;
}

export interface DotloopLoop {
  id: number;
  name: string;
  transactionType?: string;
  status?: string;
  loopUrl?: string;
  updated?: string;
}

export async function fetchDotloopLoops(): Promise<DotloopLoop[]> {
  const resp = await fetch(`${API_BASE}/api/dotloop/loops`, { headers: { ...await authHeaders() } });
  if (!resp.ok) throw new Error(`Failed to fetch loops: ${resp.status}`);
  const data = await resp.json();
  return data.loops || [];
}

export interface DotloopSyncResult {
  loop_id: string;
  loop_url: string | null;
  action: string;
  document_uploaded: boolean;
  document_name: string | null;
  errors: string[];
}

export async function syncToDotloop(
  extractionId: string,
  loopId?: number,
  uploadDocument: boolean = true,
): Promise<DotloopSyncResult> {
  const resp = await fetch(`${API_BASE}/api/dotloop/sync/${extractionId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...await authHeaders() },
    body: JSON.stringify({
      loop_id: loopId ?? null,
      upload_document: uploadDocument,
    }),
  });

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: 'Sync failed' }));
    throw new Error(err.detail || `Sync failed (${resp.status})`);
  }

  return resp.json();
}

export async function disconnectDotloop(): Promise<{ status: string }> {
  const resp = await fetch(`${API_BASE}/api/dotloop/oauth/disconnect`, {
    method: 'DELETE',
    headers: { ...await authHeaders() },
  });
  if (!resp.ok) throw new Error('Failed to disconnect Dotloop');
  return resp.json();
}

export async function archiveAllDotloopLoops(): Promise<{ archived: number }> {
  const resp = await fetch(`${API_BASE}/api/dotloop/loops`, {
    method: 'DELETE',
    headers: { ...await authHeaders() },
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: 'Archive all failed' }));
    throw new Error(err.detail || `Archive all failed (${resp.status})`);
  }
  return resp.json();
}

// ---------------------------------------------------------------------------
// Loop Browser — Dotloop loop details & search
// ---------------------------------------------------------------------------

export interface LoopDocument {
  name: string;
  id?: number;
  folder?: string;
}

export interface LoopDetail {
  loop_id: number;
  name: string;
  transaction_type?: string;
  status?: string;
  loop_url?: string;
  updated?: string;
  property_address?: Record<string, string | null>;
  financials?: Record<string, unknown>;
  contract_dates?: Record<string, string | null>;
  participants?: Array<Record<string, string | null>>;
  documents?: LoopDocument[];
}

export async function fetchLoopDetail(loopId: number, profileId?: number): Promise<LoopDetail> {
  let url = `${API_BASE}/api/dotloop/loops/${loopId}`;
  if (profileId) url += `?profile_id=${profileId}`;
  const resp = await fetch(url, { headers: { ...await authHeaders() } });
  if (!resp.ok) throw new Error(`Failed to fetch loop detail: ${resp.status}`);
  return resp.json();
}

export async function searchDotloopLoops(query: string, profileId?: number): Promise<DotloopLoop[]> {
  let url = `${API_BASE}/api/dotloop/loops/search?q=${encodeURIComponent(query)}`;
  if (profileId) url += `&profile_id=${profileId}`;
  const resp = await fetch(url, { headers: { ...await authHeaders() } });
  if (!resp.ok) throw new Error(`Failed to search loops: ${resp.status}`);
  const data = await resp.json();
  return data.loops || [];
}

// ---------------------------------------------------------------------------
// Batch Extraction from Dotloop/DocuSign sources
// ---------------------------------------------------------------------------

export interface BatchSource {
  type: 'dotloop';
  id: string;
}

export interface BatchExtractResult {
  results: Array<Record<string, unknown>>;
  extraction_ids: string[];
  total: number;
  succeeded: number;
}

export async function extractBatch(sources: BatchSource[]): Promise<BatchExtractResult> {
  const resp = await fetch(`${API_BASE}/api/extract-batch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...await authHeaders() },
    body: JSON.stringify({ sources }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: 'Batch extraction failed' }));
    throw new Error(err.detail || `HTTP ${resp.status}`);
  }
  return resp.json();
}

// ---------------------------------------------------------------------------
// Extraction Listing (for comparison dropdowns)
// ---------------------------------------------------------------------------

export interface ExtractionSummary {
  id: string;
  document_id: string;
  filename: string;
  source: string;
  source_id: string | null;
  mode: string;
  engine: string;
  overall_confidence: number;
  pages_processed: number;
  created_at: string | null;
}

export async function fetchExtractions(mode?: string): Promise<ExtractionSummary[]> {
  let url = `${API_BASE}/api/extractions`;
  if (mode) url += `?mode=${encodeURIComponent(mode)}`;
  const resp = await fetch(url, { headers: { ...await authHeaders() } });
  if (!resp.ok) throw new Error(`Failed to fetch extractions: ${resp.status}`);
  const data = await resp.json();
  return data.extractions || [];
}

export async function deleteExtraction(extractionId: string): Promise<void> {
  const resp = await fetch(`${API_BASE}/api/extractions/${encodeURIComponent(extractionId)}`, {
    method: 'DELETE',
    headers: { ...await authHeaders() },
  });
  if (!resp.ok) throw new Error(`Failed to delete extraction: ${resp.status}`);
}

// ---------------------------------------------------------------------------
// Comparison Engine
// ---------------------------------------------------------------------------

export type FieldSignificance = 'critical' | 'major' | 'minor';
export type ChangeType = 'added' | 'removed' | 'modified';

export interface ComparisonFieldDelta {
  field_path: string;
  field_label: string;
  original_value: string | null;
  new_value: string | null;
  change_type: ChangeType;
  significance: FieldSignificance;
}

export interface ComparisonResult {
  comparison_id: string;
  from_extraction_id: string;
  to_extraction_id: string;
  from_source: string | null;
  to_source: string | null;
  deltas: ComparisonFieldDelta[];
  summary: string;
  critical_count: number;
  major_count: number;
  minor_count: number;
  total_changes: number;
  comparison_timestamp: string;
}

export async function compareExtractions(
  fromExtractionId: string,
  toExtractionId: string,
): Promise<ComparisonResult> {
  const resp = await fetch(
    `${API_BASE}/api/comparisons?from_extraction_id=${encodeURIComponent(fromExtractionId)}&to_extraction_id=${encodeURIComponent(toExtractionId)}`,
    { method: 'POST', headers: { ...await authHeaders() } },
  );
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: 'Comparison failed' }));
    throw new Error(err.detail || `HTTP ${resp.status}`);
  }
  return resp.json();
}

// ---------------------------------------------------------------------------
// Property Enrichment (Cadastral / Regrid)
// ---------------------------------------------------------------------------

export async function checkPropertyEnrichmentStatus(): Promise<boolean> {
  try {
    const resp = await fetch(`${API_BASE}/api/property/status`, { headers: { ...await authHeaders() } });
    if (!resp.ok) return false;
    const data = await resp.json();
    return data.configured === true;
  } catch {
    return false;
  }
}

export interface PropertyLookupResult {
  parcel_id: string | null;
  apn: string | null;
  owner_name: string | null;
  lot_size_sqft: number | null;
  lot_size_acres: number | null;
  year_built: number | null;
  assessed_total: number | null;
  assessed_land: number | null;
  assessed_improvement: number | null;
  zoning: string | null;
  land_use: string | null;
  latitude: number | null;
  longitude: number | null;
  source: string;
  lookup_timestamp: string | null;
  match_quality: string;
}

export async function lookupProperty(
  street: string,
  city: string,
  state: string,
  zip?: string,
): Promise<PropertyLookupResult> {
  const params = new URLSearchParams({ street, city, state });
  if (zip) params.set('zip', zip);
  const resp = await fetch(`${API_BASE}/api/property/lookup?${params}`, {
    headers: { ...await authHeaders() },
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: 'Property lookup failed' }));
    throw new Error(err.detail || `HTTP ${resp.status}`);
  }
  return resp.json();
}

// ---------------------------------------------------------------------------
// Onboarding
// ---------------------------------------------------------------------------

export type OnboardingStepId =
  | 'welcome'
  | 'profile'
  | 'documents'
  | 'extraction'
  | 'complete';

export interface OnboardingStepStatus {
  step_id: OnboardingStepId;
  status: 'pending' | 'completed' | 'skipped';
  completed_at: string | null;
}

export interface OnboardingStatus {
  version: number;
  completed: boolean;
  completed_at: string | null;
  current_step: number;
  steps: OnboardingStepStatus[];
  dotloop_connected: boolean;
  docusign_connected: boolean;
}

/** Default fail-open status — marks onboarding completed so it never blocks the app. */
const DEFAULT_ONBOARDING_STATUS: OnboardingStatus = {
  version: 2,
  completed: true,
  completed_at: null,
  current_step: 0,
  steps: [],
  dotloop_connected: false,
  docusign_connected: false,
};

export async function fetchOnboardingStatus(): Promise<OnboardingStatus> {
  try {
    const resp = await fetch(`${API_BASE}/api/onboarding/status`, {
      headers: { ...await authHeaders() },
    });
    if (!resp.ok) {
      // Fail open: treat as completed so onboarding doesn't block the app
      return DEFAULT_ONBOARDING_STATUS;
    }
    return resp.json();
  } catch {
    return DEFAULT_ONBOARDING_STATUS;
  }
}

export async function updateOnboardingStep(
  stepId: OnboardingStepId,
  status: 'completed' | 'skipped',
): Promise<OnboardingStatus> {
  const resp = await fetch(`${API_BASE}/api/onboarding/step`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...await authHeaders() },
    body: JSON.stringify({ step_id: stepId, status }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: 'Failed to update onboarding step' }));
    throw new Error(err.detail || `HTTP ${resp.status}`);
  }
  return resp.json();
}

export async function completeOnboarding(skippedSteps: string[]): Promise<void> {
  await fetch(`${API_BASE}/api/onboarding/complete`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...await authHeaders() },
    body: JSON.stringify({ skipped_steps: skippedSteps }),
  });
}

// ---------------------------------------------------------------------------
// Offer Comparison (N-way)
// ---------------------------------------------------------------------------

export interface OfferField {
  key: string;
  label: string;
  type: 'string' | 'currency' | 'date' | 'boolean' | 'text';
  group?: string;
}

export interface OfferData {
  extraction_id: string;
  filename: string;
  fields: Record<string, string | number | boolean | null>;
  /** All extracted values not covered by the field registry — nothing silently dropped. */
  raw_extras: Record<string, unknown>;
}

export interface OffersComparisonResult {
  offers: OfferData[];
  field_definitions: OfferField[];
}

export async function fetchOffersComparison(
  extractionIds: string[],
): Promise<OffersComparisonResult> {
  const ids = extractionIds.join(',');
  const resp = await fetch(
    `${API_BASE}/api/offers/compare?extraction_ids=${encodeURIComponent(ids)}`,
    { headers: { ...await authHeaders() } },
  );
  if (!resp.ok) throw new Error(`Failed to fetch comparison: ${resp.status}`);
  return resp.json();
}

export async function updateOfferFields(
  extractionId: string,
  updates: Record<string, string | number | boolean | null>,
): Promise<void> {
  const resp = await fetch(`${API_BASE}/api/offers/${encodeURIComponent(extractionId)}/fields`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...await authHeaders() },
    body: JSON.stringify({ updates }),
  });
  if (!resp.ok) throw new Error(`Failed to update offer fields: ${resp.status}`);
}

// ---------------------------------------------------------------------------
// HITL Dotloop Sync
// ---------------------------------------------------------------------------

export interface DotloopSyncPreview {
  loop_name: string;
  loop_action: 'create' | 'update';
  existing_loop: { id: number; name: string } | null;
  folder_name: string;
  participants: Array<Record<string, string>>;
  document_name: string | null;
  mode: string;
}

export async function previewDotloopSync(
  extractionId: string,
  mode: 'selling' | 'buying',
): Promise<DotloopSyncPreview> {
  const resp = await fetch(`${API_BASE}/api/dotloop/sync-preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...await authHeaders() },
    body: JSON.stringify({ extraction_id: extractionId, mode }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: 'Preview failed' }));
    throw new Error(err.detail || `Preview failed (${resp.status})`);
  }
  return resp.json();
}

export interface DotloopSyncResult {
  loop_id: string;
  loop_url: string | null;
  action: string;
  document_uploaded: boolean;
  document_name: string | null;
  errors: string[];
}

export async function executeDotloopSync(
  extractionId: string,
  mode: 'selling' | 'buying',
  loopId?: number,
  folderName?: string,
  uploadDocument: boolean = true,
): Promise<DotloopSyncResult> {
  const resp = await fetch(`${API_BASE}/api/dotloop/sync-execute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...await authHeaders() },
    body: JSON.stringify({
      extraction_id: extractionId,
      mode,
      loop_id: loopId ?? null,
      folder_name: folderName ?? null,
      upload_document: uploadDocument,
    }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: 'Sync failed' }));
    throw new Error(err.detail || `Sync failed (${resp.status})`);
  }
  return resp.json();
}
