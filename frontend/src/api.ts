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
}

// ---------------------------------------------------------------------------
// SSE event types
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
// API functions
// ---------------------------------------------------------------------------

const API_BASE = '/api';

export async function fetchDocuments(): Promise<DocumentInfo[]> {
  const response = await fetch(`${API_BASE}/documents`);
  if (!response.ok) throw new Error('Failed to fetch documents');
  return response.json();
}

export function getDocumentUrl(name: string): string {
  return `${API_BASE}/documents/${encodeURIComponent(name)}`;
}

/**
 * Run extraction via SSE stream. Calls onEvent for each server-sent event.
 * Returns an abort function to cancel the stream.
 */
export function runExtraction(
  mode: string,
  filename: string,
  onEvent: (event: SSEEvent) => void,
): () => void {
  const controller = new AbortController();

  fetch(`${API_BASE}/extract`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode, filename }),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        onEvent({ type: 'error', data: { message: `HTTP ${response.status}` } });
        return;
      }

      const reader = response.body?.getReader();
      if (!reader) return;

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        let currentEventType = '';
        let currentData = '';

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEventType = line.slice(7).trim();
          } else if (line.startsWith('data: ')) {
            currentData = line.slice(6);
          } else if (line === '' && currentEventType && currentData) {
            try {
              const parsed = JSON.parse(currentData);
              onEvent({ type: currentEventType, data: parsed } as SSEEvent);
            } catch {
              // Skip malformed events
            }
            currentEventType = '';
            currentData = '';
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        onEvent({ type: 'error', data: { message: err.message } });
      }
    });

  return () => controller.abort();
}
