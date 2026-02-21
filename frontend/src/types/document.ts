/** Document TypeScript types — mirrors backend db.py models. */

import type { UserDocumentType } from './user';

export interface UserDocument {
  _id: string;
  user_id: string;
  doc_type: UserDocumentType;
  filename: string;
  file_path: string;
  file_hash: string;
  file_size_bytes: number;
  extraction_status: 'pending' | 'processing' | 'completed' | 'failed';
  extracted_data?: Record<string, unknown>;
  extraction_id?: string;
  overall_confidence?: number;
  citations: Record<string, unknown>[];
  pii_report?: Record<string, unknown>;
  uploaded_at: string;
  description?: string;
}

export interface TransactionDocument {
  _id: string;
  transaction_id: string;
  doc_type: string;
  source: string;
  source_user_document_id?: string;
  filename: string;
  file_path: string;
  file_hash: string;
  document_record_id?: string;
  uploaded_by: string;
  uploaded_at: string;
}
