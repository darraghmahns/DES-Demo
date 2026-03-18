/** Transaction API functions for D.E.S. */

import { apiFetch } from './client';
import type {
  ParticipantRole,
  Transaction,
  TransactionInvitation,
  TransactionStatus,
} from '../types/transaction';

// ---------------------------------------------------------------------------
// Transaction CRUD
// ---------------------------------------------------------------------------

export interface CreateTransactionPayload {
  name: string;
  transaction_type?: string;
  property_address?: Record<string, string>;
  mls_number?: string;
  purchase_price?: number;
  earnest_money?: number;
  closing_date?: string;
  agent_role?: 'listing_agent' | 'buying_agent';
}

export async function createTransaction(data: CreateTransactionPayload): Promise<Transaction> {
  return apiFetch<Transaction>('/api/transactions', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function listTransactions(status?: TransactionStatus): Promise<Transaction[]> {
  const params = status ? `?status=${status}` : '';
  return apiFetch<Transaction[]>(`/api/transactions${params}`);
}

export async function getTransaction(id: string): Promise<Transaction> {
  return apiFetch<Transaction>(`/api/transactions/${id}`);
}

export async function updateTransaction(
  id: string,
  data: Partial<CreateTransactionPayload> & { status?: TransactionStatus },
): Promise<Transaction> {
  return apiFetch<Transaction>(`/api/transactions/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function deleteTransaction(id: string): Promise<{ deleted: boolean }> {
  return apiFetch<{ deleted: boolean }>(`/api/transactions/${id}`, { method: 'DELETE' });
}

// ---------------------------------------------------------------------------
// Participants
// ---------------------------------------------------------------------------

export interface AddParticipantPayload {
  email: string;
  role: ParticipantRole;
  name?: string;
}

export interface ParticipantResult {
  participant: {
    user_id: string;
    email: string;
    name: string;
    role: string;
    status: string;
  };
  transaction_id: string;
}

export async function addParticipant(
  txnId: string,
  data: AddParticipantPayload,
): Promise<ParticipantResult> {
  return apiFetch<ParticipantResult>(`/api/transactions/${txnId}/participants`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateParticipant(
  txnId: string,
  userId: string,
  data: { role?: ParticipantRole },
): Promise<{ updated: boolean }> {
  return apiFetch(`/api/transactions/${txnId}/participants/${userId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function removeParticipant(
  txnId: string,
  userId: string,
): Promise<{ removed: boolean }> {
  return apiFetch(`/api/transactions/${txnId}/participants/${userId}`, { method: 'DELETE' });
}

// ---------------------------------------------------------------------------
// Transaction Documents
// ---------------------------------------------------------------------------

export interface TransactionDocRecord {
  _id: string;
  transaction_id: string;
  doc_type: string;
  source: string;
  filename: string;
  uploaded_by: string;
  uploaded_at: string;
  offer_extraction_id?: string | null;
}

export async function listTransactionDocuments(txnId: string): Promise<TransactionDocRecord[]> {
  return apiFetch<TransactionDocRecord[]>(`/api/transactions/${txnId}/documents`);
}

export async function linkDocumentToTransaction(
  txnId: string,
  userDocId: string,
  docType: string,
  offerExtractionId?: string,
): Promise<TransactionDocRecord> {
  return apiFetch<TransactionDocRecord>(`/api/transactions/${txnId}/documents`, {
    method: 'POST',
    body: JSON.stringify({
      user_document_id: userDocId,
      doc_type: docType,
      offer_extraction_id: offerExtractionId ?? null,
    }),
  });
}

export async function uploadOfferDocument(
  txnId: string,
  file: File,
  docType: string,
  offerExtractionId: string,
): Promise<TransactionDocRecord> {
  const form = new FormData();
  form.append('file', file);
  form.append('doc_type', docType);
  form.append('offer_extraction_id', offerExtractionId);
  return apiFetch<TransactionDocRecord>(
    `/api/transactions/${txnId}/documents/upload-file`,
    { method: 'POST', body: form },
  );
}

// ---------------------------------------------------------------------------
// Auto-Fill & Completion
// ---------------------------------------------------------------------------

export interface AutoFillResult {
  filled_fields: string[];
  transaction: Transaction;
}

export async function autoFillTransaction(txnId: string): Promise<AutoFillResult> {
  return apiFetch<AutoFillResult>(`/api/transactions/${txnId}/auto-fill`, { method: 'POST' });
}

export interface TransactionCompletionResult {
  kind?: 'setup_progress';
  overall: number;
  blockers: string[];
  buckets: Array<{
    key: 'transaction_fields' | 'participant_acceptance' | 'participant_profiles' | 'required_documents';
    label: string;
    weight: number;
    score: number;
    status: 'complete' | 'partial' | 'missing';
    reasons: string[];
  }>;
  participants: Array<{
    user_id: string;
    role: string;
    status: string;
    name: string;
    email: string;
    profile_completion: number;
  }>;
  documents: {
    total_required: number;
    satisfied: number;
    completion: number;
    requirements: Array<{
      doc_type: string;
      role: string;
      required: boolean;
      satisfied: boolean;
    }>;
  };
}

export async function getTransactionCompletion(txnId: string): Promise<TransactionCompletionResult> {
  return apiFetch<TransactionCompletionResult>(`/api/transactions/${txnId}/completion`);
}

// ---------------------------------------------------------------------------
// Invitations
// ---------------------------------------------------------------------------

export interface CreateInvitationPayload {
  email: string;
  role: ParticipantRole;
  transaction_id: string;
  name?: string;
}

export interface InvitationResult {
  id: string;
  email: string;
  transaction_id: string;
  invitee_user_id?: string | null;
  role: ParticipantRole;
  status: TransactionInvitation['status'];
  expires_at?: string | null;
  sent_at?: string | null;
  opened_at?: string | null;
  accepted_at?: string | null;
  revoked_at?: string | null;
  provider?: string | null;
  provider_message_id?: string | null;
  last_error?: string | null;
  invite_url?: string | null;
}

export async function createInvitation(data: CreateInvitationPayload): Promise<InvitationResult> {
  return apiFetch<InvitationResult>('/api/invitations', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function listTransactionInvitations(txnId: string): Promise<TransactionInvitation[]> {
  const data = await apiFetch<{ invitations: TransactionInvitation[] }>(`/api/transactions/${txnId}/invitations`);
  return data.invitations;
}

export async function resendInvitation(invitationId: string): Promise<InvitationResult> {
  return apiFetch<InvitationResult>(`/api/invitations/${invitationId}/resend`, {
    method: 'POST',
  });
}

export async function revokeInvitation(invitationId: string): Promise<InvitationResult> {
  return apiFetch<InvitationResult>(`/api/invitations/${invitationId}/revoke`, {
    method: 'POST',
  });
}

export interface InvitationValidation {
  valid: boolean;
  email: string;
  name: string;
  has_clerk_account: boolean;
  user_id: string;
  invitation_status?: TransactionInvitation['status'];
  transaction?: {
    id: string;
    name: string;
    role: string;
  };
}

export interface DotloopTransactionPreview {
  normalized_transaction: {
    name: string;
    transaction_type: string;
    property_address?: Record<string, string> | null;
    purchase_price?: number | null;
    earnest_money?: number | null;
    closing_date?: string | null;
    dotloop_loop_id: string;
    agent_role?: 'listing_agent' | 'buying_agent';
    agent_side?: 'buyer' | 'seller';
  };
  participant_suggestions: Array<{
    name: string;
    email?: string | null;
    role: ParticipantRole;
    source_role: string;
    can_invite: boolean;
  }>;
  available_documents: {
    total: number;
    pdf_count: number;
    documents: Array<{
      id: number;
      name: string;
      folder_id: number;
      folder_name: string;
    }>;
  };
  warnings: string[];
  existing_transaction_id?: string | null;
}

export interface DotloopFolderDocument {
  folder_id: number;
  folder_name: string;
  document_id: number;
  name: string;
  is_pdf: boolean;
  already_imported: boolean;
}

export interface DotloopFolderGroup {
  folder_id: number;
  folder_name: string;
  documents: DotloopFolderDocument[];
}

export interface DotloopImportDocumentsResponse {
  results: Array<{
    name: string;
    document_id: number;
    failed: boolean;
    duplicate?: boolean;
    linked_existing?: boolean;
    local_document_id?: string;
    extraction_id?: string | null;
    filename?: string;
    error?: string;
  }>;
  imported: number;
  duplicates: number;
  failed: number;
}

export async function validateInvitation(token: string): Promise<InvitationValidation> {
  return apiFetch<InvitationValidation>(`/api/invitations/${token}/validate`);
}

export async function acceptInvitation(token: string): Promise<{ accepted: boolean; user_id: string; transaction_id: string }> {
  return apiFetch(`/api/invitations/${token}/accept`, { method: 'POST' });
}

// ---------------------------------------------------------------------------
// Dotloop Loop Linking
// ---------------------------------------------------------------------------

export async function linkDotloopLoop(txnId: string, loopId: string): Promise<Transaction> {
  return apiFetch<Transaction>(`/api/transactions/${txnId}/dotloop-loop`, {
    method: 'PATCH',
    body: JSON.stringify({ loop_id: loopId }),
  });
}

export async function previewTransactionFromDotloop(
  loopId: number,
  data?: { name_override?: string; agent_role?: 'listing_agent' | 'buying_agent' },
): Promise<DotloopTransactionPreview> {
  return apiFetch<DotloopTransactionPreview>(`/api/transactions/from-dotloop/${loopId}/preview`, {
    method: 'POST',
    body: JSON.stringify(data ?? {}),
  });
}

export async function createTransactionFromDotloop(
  loopId: number,
  data?: { name_override?: string; agent_role?: 'listing_agent' | 'buying_agent' },
): Promise<Transaction> {
  return apiFetch<Transaction>(`/api/transactions/from-dotloop/${loopId}`, {
    method: 'POST',
    body: JSON.stringify(data ?? {}),
  });
}

export async function listDotloopDocumentsForTransaction(txnId: string): Promise<{
  loop_id: string;
  folders: DotloopFolderGroup[];
}> {
  return apiFetch(`/api/transactions/${txnId}/dotloop/documents`);
}

export async function importDotloopDocuments(
  txnId: string,
  documents: Array<{ folder_id: number; document_id: number; name: string }>,
): Promise<DotloopImportDocumentsResponse> {
  return apiFetch<DotloopImportDocumentsResponse>(`/api/transactions/${txnId}/dotloop/import-documents`, {
    method: 'POST',
    body: JSON.stringify({ documents }),
  });
}

// ---------------------------------------------------------------------------
// Extraction Linking
// ---------------------------------------------------------------------------

export async function linkExtractionToTransaction(
  txnId: string,
  extractionId: string,
): Promise<Transaction> {
  return apiFetch<Transaction>(`/api/transactions/${txnId}/extractions/${extractionId}`, {
    method: 'POST',
  });
}

export async function unlinkExtractionFromTransaction(
  txnId: string,
  extractionId: string,
): Promise<Transaction> {
  return apiFetch<Transaction>(`/api/transactions/${txnId}/extractions/${extractionId}`, {
    method: 'DELETE',
  });
}

export async function fetchTransactionExtractions(
  txnId: string,
): Promise<Array<{ id: string; filename: string; mode: string; overall_confidence: number; pages_processed: number; created_at: string | null }>> {
  const data = await apiFetch<{ extractions: Array<{ id: string; filename: string; mode: string; overall_confidence: number; pages_processed: number; created_at: string | null }> }>(`/api/transactions/${txnId}/extractions`);
  return data.extractions;
}

export async function submitProfileViaMagicLink(
  token: string,
  data: { name?: string; phone?: string; address?: Record<string, string> },
): Promise<{ updated: boolean; user_id: string; name: string }> {
  return apiFetch(`/api/invitations/${token}/profile`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}
