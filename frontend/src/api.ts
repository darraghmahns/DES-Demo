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

export interface AggregateUsage {
  total_extractions: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  total_cost_usd: number;
  avg_cost_per_extraction: number;
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

export type SSEEvent =
  | { type: 'step'; data: StepEvent }
  | { type: 'step_complete'; data: StepCompleteEvent }
  | { type: 'extraction'; data: ExtractionEvent }
  | { type: 'validation'; data: ValidationEvent }
  | { type: 'citations'; data: CitationsEvent }
  | { type: 'pii'; data: PIIEvent }
  | { type: 'compliance'; data: ComplianceEvent }
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
// API Usage & Cost Tracking
// ---------------------------------------------------------------------------

export async function fetchAggregateUsage(): Promise<AggregateUsage> {
  const resp = await fetch(`${API_BASE}/api/usage`, { headers: { ...await authHeaders() } });
  if (!resp.ok) throw new Error(`Failed to fetch usage: ${resp.status}`);
  return resp.json();
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

// ---------------------------------------------------------------------------
// DocuSign integration
// ---------------------------------------------------------------------------

export async function checkDocuSignStatus(): Promise<boolean> {
  try {
    const resp = await fetch(`${API_BASE}/api/docusign/status`, { headers: { ...await authHeaders() } });
    if (!resp.ok) return false;
    const data = await resp.json();
    return data.configured === true;
  } catch {
    return false;
  }
}

export function getDocuSignConnectUrl(): string {
  return `${API_BASE}/api/docusign/oauth/connect`;
}

export interface DocuSignEnvelope {
  envelopeId: string;
  emailSubject: string;
  status: string;
  createdDateTime?: string;
  statusChangedDateTime?: string;
  sentDateTime?: string;
  completedDateTime?: string;
}

export async function fetchDocuSignEnvelopes(): Promise<DocuSignEnvelope[]> {
  const resp = await fetch(`${API_BASE}/api/docusign/envelopes`, { headers: { ...await authHeaders() } });
  if (!resp.ok) throw new Error(`Failed to fetch envelopes: ${resp.status}`);
  const data = await resp.json();
  return data.envelopes || [];
}

export async function voidDocuSignEnvelope(envelopeId: string): Promise<void> {
  const resp = await fetch(`${API_BASE}/api/docusign/envelopes/${envelopeId}`, {
    method: 'DELETE',
    headers: { ...await authHeaders() },
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: 'Delete failed' }));
    throw new Error(err.detail || `Delete failed (${resp.status})`);
  }
}

export async function deleteAllDocuSignEnvelopes(): Promise<{ removed: number }> {
  const resp = await fetch(`${API_BASE}/api/docusign/envelopes`, {
    method: 'DELETE',
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: 'Delete all failed' }));
    throw new Error(err.detail || `Delete all failed (${resp.status})`);
  }
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

export interface DocuSignSyncResult {
  envelope_id: string;
  action: string;
  errors: string[];
  envelope_url?: string;
}

export async function syncToDocuSign(
  extractionId: string,
  envelopeId?: string,
): Promise<DocuSignSyncResult> {
  const resp = await fetch(`${API_BASE}/api/docusign/sync/${extractionId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...await authHeaders() },
    body: JSON.stringify({ envelope_id: envelopeId ?? null }),
  });

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: 'Sync failed' }));
    throw new Error(err.detail || `Sync failed (${resp.status})`);
  }

  return resp.json();
}

// ---------------------------------------------------------------------------
// Extraction cache
// ---------------------------------------------------------------------------

export interface CachedExtractionResponse {
  cached: boolean;
  extraction?: Record<string, unknown>;
}

export async function computeFileHash(file: File): Promise<string> {
  const buffer = await file.arrayBuffer();
  const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');
}

export async function checkCachedExtraction(
  fileHash: string,
  mode: string = 'real_estate',
): Promise<CachedExtractionResponse> {
  const resp = await fetch(
    `${API_BASE}/api/extractions/cached?file_hash=${encodeURIComponent(fileHash)}&mode=${encodeURIComponent(mode)}`,
    { headers: { ...await authHeaders() } },
  );
  if (!resp.ok) return { cached: false };
  return resp.json();
}

export async function clearExtractionCache(mode?: string): Promise<{ deleted: number }> {
  const url = mode
    ? `${API_BASE}/api/extractions/cache?mode=${encodeURIComponent(mode)}`
    : `${API_BASE}/api/extractions/cache`;
  const resp = await fetch(url, { method: 'DELETE', headers: { ...await authHeaders() } });
  if (!resp.ok) throw new Error(`Failed to clear cache: ${resp.status}`);
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

export interface EnvelopeDetail {
  envelope_id: string;
  email_subject?: string;
  status: string;
  created?: string;
  sent?: string;
  completed?: string;
  recipients?: Array<Record<string, unknown>>;
  documents?: Array<Record<string, unknown>>;
  custom_fields?: Record<string, string>;
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

export async function fetchEnvelopeDetail(envelopeId: string): Promise<EnvelopeDetail> {
  const resp = await fetch(`${API_BASE}/api/docusign/envelopes/${envelopeId}`, { headers: { ...await authHeaders() } });
  if (!resp.ok) throw new Error(`Failed to fetch envelope detail: ${resp.status}`);
  return resp.json();
}

// ---------------------------------------------------------------------------
// Batch Extraction from Dotloop/DocuSign sources
// ---------------------------------------------------------------------------

export interface BatchSource {
  type: 'dotloop' | 'docusign';
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
