import { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Checkbox, Group, Modal, Stack, Text } from '@mantine/core';
import {
  importDotloopDocuments,
  listDotloopDocumentsForTransaction,
  type DotloopFolderDocument,
  type DotloopImportDocumentsResponse,
} from '../../api/transactions';

interface DotloopImportModalProps {
  transactionId: string;
  opened: boolean;
  onClose: () => void;
  onImported: () => void;
}

export function DotloopImportModal({ transactionId, opened, onClose, onImported }: DotloopImportModalProps) {
  const [documents, setDocuments] = useState<DotloopFolderDocument[]>([]);
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DotloopImportDocumentsResponse | null>(null);

  useEffect(() => {
    if (!opened) return;
    setLoading(true);
    setError(null);
    setResult(null);
    setSelectedKeys([]);
    listDotloopDocumentsForTransaction(transactionId)
      .then((data) => setDocuments(data.folders.flatMap((folder) => folder.documents)))
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load Dotloop documents.'))
      .finally(() => setLoading(false));
  }, [opened, transactionId]);

  const selectableDocuments = useMemo(
    () => documents.filter((document) => document.is_pdf),
    [documents],
  );

  const selectedDocuments = useMemo(
    () => selectableDocuments.filter((document) => selectedKeys.includes(`${document.folder_id}:${document.document_id}`)),
    [selectableDocuments, selectedKeys],
  );

  const toggleDocument = (document: DotloopFolderDocument) => {
    const key = `${document.folder_id}:${document.document_id}`;
    setSelectedKeys((current) => (
      current.includes(key)
        ? current.filter((item) => item !== key)
        : [...current, key].slice(0, 5)
    ));
  };

  const handleImport = async () => {
    if (selectedDocuments.length === 0) return;
    setSubmitting(true);
    setError(null);
    try {
      const response = await importDotloopDocuments(
        transactionId,
        selectedDocuments.map((document) => ({
          folder_id: document.folder_id,
          document_id: document.document_id,
          name: document.name,
        })),
      );
      setResult(response);
      onImported();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to import Dotloop documents.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal opened={opened} onClose={onClose} title="Import Dotloop Documents" size="lg">
      <Stack gap="sm">
        <Text size="sm" c="dimmed">Select up to 5 PDF documents to import into this transaction.</Text>

        {error && <Alert color="red">{error}</Alert>}

        {loading ? (
          <Text size="sm">Loading Dotloop documents...</Text>
        ) : (
          <Stack gap="xs" className="dotloop-import-list">
            {documents.length === 0 && <Text size="sm">No documents available from Dotloop.</Text>}
            {documents.map((document) => {
              const key = `${document.folder_id}:${document.document_id}`;
              const disabled = !document.is_pdf || (!selectedKeys.includes(key) && selectedKeys.length >= 5);
              return (
                <Checkbox
                  key={key}
                  checked={selectedKeys.includes(key)}
                  disabled={disabled}
                  onChange={() => toggleDocument(document)}
                  label={
                    <div className="dotloop-import-item">
                      <span>{document.name}</span>
                      <span className="dotloop-import-meta">
                        {document.folder_name} · {document.is_pdf ? 'PDF' : 'Unsupported'}
                        {document.already_imported ? ' · Already imported' : ''}
                      </span>
                    </div>
                  }
                />
              );
            })}
          </Stack>
        )}

        {result && (
          <Alert color={result.failed > 0 ? 'yellow' : 'green'}>
            Imported {result.imported}, duplicates {result.duplicates}, failed {result.failed}.
          </Alert>
        )}

        <Group justify="space-between" mt="sm">
          <Text size="xs" c="dimmed">{selectedDocuments.length}/5 selected</Text>
          <Group>
            <Button variant="default" onClick={onClose}>Close</Button>
            <Button color="campari" onClick={() => void handleImport()} disabled={selectedDocuments.length === 0 || submitting}>
              {submitting ? 'Importing...' : 'Import Documents'}
            </Button>
          </Group>
        </Group>
      </Stack>
    </Modal>
  );
}
