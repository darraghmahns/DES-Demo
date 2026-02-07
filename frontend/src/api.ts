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

export interface ExtractionResult {
  mode: string;
  source_file: string;
  extraction_timestamp: string;
  model_used: string;
  pages_processed: number;
  dotloop_data: Record<string, unknown> | null;
  foia_data: Record<string, unknown> | null;
  dotloop_api_payload: Record<string, unknown> | null;
  citations: VerificationCitation[];
  overall_confidence: number;
  pii_report: PIIReport | null;
  extraction_id?: string;
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

export type SSEEvent =
  | { type: 'step'; data: StepEvent }
  | { type: 'step_complete'; data: StepCompleteEvent }
  | { type: 'extraction'; data: ExtractionEvent }
  | { type: 'validation'; data: ValidationEvent }
  | { type: 'citations'; data: CitationsEvent }
  | { type: 'pii'; data: PIIEvent }
  | { type: 'complete'; data: ExtractionResult }
  | { type: 'error'; data: { message: string } };

// ---------------------------------------------------------------------------
// API Base URL
// ---------------------------------------------------------------------------

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

// ---------------------------------------------------------------------------
// Document operations
// ---------------------------------------------------------------------------

export async function fetchDocuments(_mode?: string): Promise<DocumentInfo[]> {
  const resp = await fetch(`${API_BASE}/api/documents`);
  if (!resp.ok) throw new Error(`Failed to fetch documents: ${resp.status}`);
  return resp.json();
}

export function getDocumentUrl(name: string): string {
  return `${API_BASE}/api/documents/${encodeURIComponent(name)}`;
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
// Extraction via real SSE
// ---------------------------------------------------------------------------

export function runExtraction(
  mode: string,
  filename: string,
  onEvent: (event: SSEEvent) => void,
): () => void {
  const controller = new AbortController();

  (async () => {
    try {
      const resp = await fetch(`${API_BASE}/api/extract`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode, filename }),
        signal: controller.signal,
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'Extraction failed' }));
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
        // Keep the last (possibly incomplete) chunk in the buffer
        buffer = parts.pop() || '';

        for (const part of parts) {
          if (!part.trim()) continue;

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
