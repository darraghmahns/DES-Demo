/** Profile Documents page: upload, list, view extraction results. */

import { useEffect, useState } from 'react';
import { useDocumentUpload } from '../hooks/useDocumentUpload';
import { useOnboardingContext } from '../context/OnboardingContext';
import { FileUpload } from '../components/common/FileUpload';
import type { UserDocumentType } from '../types/user';

const DOC_TYPE_OPTIONS: { value: UserDocumentType; label: string }[] = [
  { value: 'pre_approval_letter', label: 'Pre-Approval Letter' },
  { value: 'bank_statement', label: 'Bank Statement' },
  { value: 'pay_stub', label: 'Pay Stub' },
  { value: 'w2', label: 'W-2' },
  { value: 'proof_of_funds', label: 'Proof of Funds' },
  { value: 'drivers_license', label: "Driver's License" },
  { value: 'proof_of_insurance', label: 'Proof of Insurance' },
  { value: 'tax_return', label: 'Tax Return' },
  { value: 'other', label: 'Other' },
];

const STATUS_LABELS: Record<string, string> = {
  pending: 'Pending',
  processing: 'Processing...',
  completed: 'Extracted',
  failed: 'Failed',
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDocType(dt: string): string {
  return DOC_TYPE_OPTIONS.find(o => o.value === dt)?.label || dt;
}

export function ProfileDocuments() {
  const {
    documents,
    loading,
    uploading,
    error,
    extractionProgress,
    refresh,
    upload,
    remove,
    reExtract,
  } = useDocumentUpload();

  const { markStepAction } = useOnboardingContext();
  const [selectedDocType, setSelectedDocType] = useState<UserDocumentType>('pre_approval_letter');
  const [expandedDoc, setExpandedDoc] = useState<string | null>(null);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleFileSelect = async (file: File) => {
    try {
      await upload(file, selectedDocType);
      markStepAction('document_uploaded');
    } catch {
      // Error is handled by the hook
    }
  };

  const handleDelete = async (docId: string) => {
    if (!confirm('Delete this document? This cannot be undone.')) return;
    try {
      await remove(docId);
    } catch {
      // Error is handled by the hook
    }
  };

  return (
    <div className="page-profile-documents">
      <h1>My Documents</h1>
      <p className="page-subtitle">Upload and manage your personal documents. AI will automatically extract structured data.</p>

      {error && <div className="error-banner">{error}</div>}

      {/* Upload Section */}
      <section className="upload-section">
        <div className="upload-controls">
          <label>
            <span>Document Type</span>
            <select
              value={selectedDocType}
              onChange={e => setSelectedDocType(e.target.value as UserDocumentType)}
              disabled={uploading}
            >
              {DOC_TYPE_OPTIONS.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </label>
        </div>

        <FileUpload
          onFileSelect={handleFileSelect}
          disabled={uploading}
          label={uploading ? 'Uploading...' : 'Drop a document here or click to browse'}
        />

        {extractionProgress && (
          <div className="extraction-progress">
            <div className="extraction-progress-bar">
              <div
                className="extraction-progress-fill"
                style={{ width: `${(extractionProgress.step / extractionProgress.total) * 100}%` }}
              />
            </div>
            <span className="extraction-progress-label">
              Step {extractionProgress.step}/{extractionProgress.total}: {extractionProgress.title}
            </span>
          </div>
        )}
      </section>

      {/* Document List */}
      <section className="documents-list">
        <h2>Uploaded Documents ({documents.length})</h2>

        {loading && <p>Loading documents...</p>}

        {!loading && documents.length === 0 && (
          <div className="placeholder-card">
            <p>No documents uploaded yet. Upload your first document above.</p>
          </div>
        )}

        {documents.map(doc => (
          <div key={doc._id} className="document-card">
            <div className="document-card-header" onClick={() => setExpandedDoc(expandedDoc === doc._id ? null : doc._id)}>
              <div className="document-card-info">
                <span className="document-filename">{doc.filename}</span>
                <span className="document-type-badge">{formatDocType(doc.doc_type)}</span>
                <span className={`document-status document-status-${doc.extraction_status}`}>
                  {STATUS_LABELS[doc.extraction_status] || doc.extraction_status}
                </span>
              </div>
              <div className="document-card-meta">
                <span>{formatBytes(doc.file_size_bytes)}</span>
                <span>{new Date(doc.uploaded_at).toLocaleDateString()}</span>
                {doc.overall_confidence !== null && (
                  <span className="confidence-badge">
                    {Math.round(doc.overall_confidence * 100)}% confidence
                  </span>
                )}
              </div>
            </div>

            {expandedDoc === doc._id && (
              <div className="document-card-expanded">
                {doc.extracted_data && (
                  <div className="extracted-data">
                    <h4>Extracted Data</h4>
                    <div className="extracted-fields">
                      {Object.entries(doc.extracted_data).map(([key, val]) => (
                        <div key={key} className="extracted-field">
                          <span className="field-key">{key.replace(/_/g, ' ')}</span>
                          <span className="field-value">
                            {val === null ? '—' : Array.isArray(val) ? val.join(', ') : String(val)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="document-actions">
                  {doc.extraction_status !== 'processing' && (
                    <button className="btn-secondary" onClick={() => reExtract(doc._id)}>
                      Re-Extract
                    </button>
                  )}
                  <button className="btn-danger" onClick={() => handleDelete(doc._id)}>
                    Delete
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
      </section>
    </div>
  );
}
