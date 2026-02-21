/** Profile document API functions for D.E.S. */

import { apiFetch, apiSSE } from './client';
import type { UserDocumentType } from '../types/user';

export interface UserDocumentRecord {
  _id: string;
  user_id: string;
  doc_type: UserDocumentType;
  filename: string;
  file_path: string;
  file_hash: string;
  file_size_bytes: number;
  extraction_status: 'pending' | 'processing' | 'completed' | 'failed';
  extracted_data: Record<string, unknown> | null;
  extraction_id: string | null;
  overall_confidence: number | null;
  citations: Record<string, unknown>[];
  pii_report: Record<string, unknown> | null;
  uploaded_at: string;
  description: string | null;
}

export interface UploadDocumentResponse {
  document: UserDocumentRecord;
  duplicate: boolean;
  message?: string;
  extraction_id?: string;
}

export interface ExtractionSSEEvent {
  type: string;
  data: Record<string, unknown>;
}

export async function uploadDocument(
  file: File,
  docType: UserDocumentType,
  description?: string,
): Promise<UploadDocumentResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const params = new URLSearchParams({ doc_type: docType });
  if (description) params.append('description', description);

  return apiFetch<UploadDocumentResponse>(
    `/api/profile/documents?${params.toString()}`,
    { method: 'POST', body: formData },
  );
}

export async function listDocuments(
  docType?: UserDocumentType,
): Promise<UserDocumentRecord[]> {
  const params = docType ? `?doc_type=${docType}` : '';
  return apiFetch<UserDocumentRecord[]>(`/api/profile/documents${params}`);
}

export async function getDocument(docId: string): Promise<UserDocumentRecord> {
  return apiFetch<UserDocumentRecord>(`/api/profile/documents/${docId}`);
}

export async function deleteDocument(docId: string): Promise<{ deleted: boolean }> {
  return apiFetch<{ deleted: boolean }>(`/api/profile/documents/${docId}`, {
    method: 'DELETE',
  });
}

export async function triggerExtraction(
  docId: string,
): Promise<{ extraction_id: string; status: string }> {
  return apiFetch<{ extraction_id: string; status: string }>(
    `/api/profile/documents/${docId}/extract`,
    { method: 'POST' },
  );
}

export function subscribeToExtraction(
  docId: string,
  onEvent: (event: ExtractionSSEEvent) => void,
): () => void {
  return apiSSE(`/api/profile/documents/${docId}/stream`, onEvent as (e: { type: string; data: unknown }) => void);
}
