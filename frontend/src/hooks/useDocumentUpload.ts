/** Hook for profile document upload and extraction tracking. */

import { useState, useCallback } from 'react';
import type { UserDocumentType } from '../types/user';
import type { UserDocumentRecord, ExtractionSSEEvent } from '../api/documents';
import {
  uploadDocument,
  listDocuments,
  deleteDocument as apiDeleteDocument,
  triggerExtraction,
  subscribeToExtraction,
} from '../api/documents';

interface ExtractionProgress {
  step: number;
  total: number;
  title: string;
  status: string;
}

interface UseDocumentUploadReturn {
  documents: UserDocumentRecord[];
  loading: boolean;
  uploading: boolean;
  error: string | null;
  extractionProgress: ExtractionProgress | null;
  refresh: () => Promise<void>;
  upload: (file: File, docType: UserDocumentType, description?: string) => Promise<UserDocumentRecord>;
  remove: (docId: string) => Promise<void>;
  reExtract: (docId: string) => Promise<void>;
}

export function useDocumentUpload(): UseDocumentUploadReturn {
  const [documents, setDocuments] = useState<UserDocumentRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [extractionProgress, setExtractionProgress] = useState<ExtractionProgress | null>(null);

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const docs = await listDocuments();
      setDocuments(docs);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load documents');
    } finally {
      setLoading(false);
    }
  }, []);

  const upload = useCallback(async (
    file: File,
    docType: UserDocumentType,
    description?: string,
  ): Promise<UserDocumentRecord> => {
    try {
      setUploading(true);
      setError(null);
      setExtractionProgress(null);

      const result = await uploadDocument(file, docType, description);

      if (result.duplicate) {
        setError('This document has already been uploaded');
        return result.document;
      }

      // If extraction was auto-triggered, subscribe to progress
      if (result.extraction_id) {
        _subscribeToProgress(result.document._id);
      }

      await refresh();
      return result.document;
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Upload failed';
      setError(msg);
      throw e;
    } finally {
      setUploading(false);
    }
  }, [refresh]);

  const remove = useCallback(async (docId: string) => {
    try {
      setError(null);
      await apiDeleteDocument(docId);
      setDocuments(prev => prev.filter(d => d._id !== docId));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete document');
      throw e;
    }
  }, []);

  const reExtract = useCallback(async (docId: string) => {
    try {
      setError(null);
      setExtractionProgress(null);
      await triggerExtraction(docId);
      _subscribeToProgress(docId);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start extraction');
      throw e;
    }
  }, []);

  function _subscribeToProgress(docId: string) {
    const cancel = subscribeToExtraction(docId, (event: ExtractionSSEEvent) => {
      if (event.type === 'step') {
        setExtractionProgress(event.data as unknown as ExtractionProgress);
      } else if (event.type === 'complete') {
        setExtractionProgress(null);
        // Refresh to get updated extraction data
        refresh();
      } else if (event.type === 'error') {
        setExtractionProgress(null);
        setError((event.data as { message?: string }).message || 'Extraction failed');
        refresh();
      }
    });

    // Auto-cancel after 5 minutes
    setTimeout(cancel, 5 * 60 * 1000);
  }

  return {
    documents,
    loading,
    uploading,
    error,
    extractionProgress,
    refresh,
    upload,
    remove,
    reExtract,
  };
}
