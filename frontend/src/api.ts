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
// Document operations
// ---------------------------------------------------------------------------

export async function fetchDocuments(mode?: string): Promise<DocumentInfo[]> {
  const url = mode
    ? `${API_BASE}/api/documents?mode=${encodeURIComponent(mode)}`
    : `${API_BASE}/api/documents`;
  const resp = await fetch(url);
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
    headers: { 'Content-Type': 'application/json' },
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
  const resp = await fetch(`${API_BASE}/api/tasks`);
  if (!resp.ok) return [];
  const data = await resp.json();
  return (data.tasks || []).filter(
    (t: TaskInfo) => t.status === 'pending' || t.status === 'running',
  );
}

export async function fetchAllTasks(): Promise<TaskInfo[]> {
  const resp = await fetch(`${API_BASE}/api/tasks`);
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
  const resp = await fetch(`${API_BASE}/api/usage`);
  if (!resp.ok) throw new Error(`Failed to fetch usage: ${resp.status}`);
  return resp.json();
}

// ---------------------------------------------------------------------------
// Dotloop integration
// ---------------------------------------------------------------------------

export async function checkDotloopStatus(): Promise<boolean> {
  try {
    const resp = await fetch(`${API_BASE}/api/dotloop/status`);
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
  const resp = await fetch(`${API_BASE}/api/dotloop/loops`);
  if (!resp.ok) throw new Error(`Failed to fetch loops: ${resp.status}`);
  const data = await resp.json();
  return data.loops || [];
}

export interface DotloopSyncResult {
  loop_id: string;
  loop_url: string | null;
  action: string;
  errors: string[];
}

export async function syncToDotloop(
  extractionId: string,
  loopId?: number,
): Promise<DotloopSyncResult> {
  const resp = await fetch(`${API_BASE}/api/dotloop/sync/${extractionId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ loop_id: loopId ?? null }),
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
    const resp = await fetch(`${API_BASE}/api/docusign/status`);
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
  const resp = await fetch(`${API_BASE}/api/docusign/envelopes`);
  if (!resp.ok) throw new Error(`Failed to fetch envelopes: ${resp.status}`);
  const data = await resp.json();
  return data.envelopes || [];
}

export async function voidDocuSignEnvelope(envelopeId: string): Promise<void> {
  const resp = await fetch(`${API_BASE}/api/docusign/envelopes/${envelopeId}`, {
    method: 'DELETE',
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
    headers: { 'Content-Type': 'application/json' },
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
  );
  if (!resp.ok) return { cached: false };
  return resp.json();
}

export async function clearExtractionCache(mode?: string): Promise<{ deleted: number }> {
  const url = mode
    ? `${API_BASE}/api/extractions/cache?mode=${encodeURIComponent(mode)}`
    : `${API_BASE}/api/extractions/cache`;
  const resp = await fetch(url, { method: 'DELETE' });
  if (!resp.ok) throw new Error(`Failed to clear cache: ${resp.status}`);
  return resp.json();
}
