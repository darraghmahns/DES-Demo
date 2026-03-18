/** Modal showing document requirements derived from a specific offer's extracted fields. */

import { useRef, useState } from 'react';
import { Modal, Stack, Group, Text, Badge, Button, Divider, ThemeIcon } from '@mantine/core';
import type { OfferData } from '../../api';
import type { TransactionDocRecord } from '../../api/transactions';
import { uploadOfferDocument } from '../../api/transactions';
import { ROLE_LABELS } from '../../types/transaction';
import { evaluateOfferRequirements } from '../../types/offerRequirements';

interface OfferRequirementsModalProps {
  opened: boolean;
  onClose: () => void;
  offer: OfferData | null;
  txnId: string;
  txnDocs: TransactionDocRecord[];
  onDocsRefresh: () => void;
}

function formatPrice(amount: number | string | null | undefined): string {
  const n = Number(amount);
  if (!amount || isNaN(n)) return '--';
  return `$${n.toLocaleString()}`;
}

export function OfferRequirementsModal({
  opened,
  onClose,
  offer,
  txnId,
  txnDocs,
  onDocsRefresh,
}: OfferRequirementsModalProps) {
  const [uploading, setUploading] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pendingDocType = useRef<string | null>(null);

  if (!offer) return null;

  const fields = offer.fields as Record<string, string | number | boolean | null>;
  const conf = typeof fields['overall_confidence'] === 'number'
    ? fields['overall_confidence'] as number
    : null;

  const requirements = evaluateOfferRequirements(fields, txnDocs, offer.extraction_id);

  const handleUploadClick = (docType: string) => {
    pendingDocType.current = docType;
    setUploadError(null);
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file || !pendingDocType.current) return;

    const docType = pendingDocType.current;
    setUploading(docType);
    setUploadError(null);
    try {
      await uploadOfferDocument(txnId, file, docType, offer.extraction_id);
      onDocsRefresh();
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(null);
    }
  };

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title="Offer Requirements"
      size="lg"
    >
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf"
        style={{ display: 'none' }}
        onChange={handleFileChange}
      />

      <Stack gap="md">
        {/* Summary */}
        <Group gap="xl" wrap="wrap">
          <div>
            <Text size="xs" c="dimmed">Buyer</Text>
            <Text size="sm" fw={500}>{String(fields['buyer_name'] ?? '--')}</Text>
          </div>
          <div>
            <Text size="xs" c="dimmed">Purchase Price</Text>
            <Text size="sm" fw={500}>{formatPrice(fields['purchase_price'] as string | number | null)}</Text>
          </div>
          <div>
            <Text size="xs" c="dimmed">Agent</Text>
            <Text size="sm" fw={500}>{String(fields['agent_name'] ?? '--')}</Text>
          </div>
          <div>
            <Text size="xs" c="dimmed">Closing Date</Text>
            <Text size="sm" fw={500}>{String(fields['closing_date'] ?? '--')}</Text>
          </div>
          {conf !== null && (
            <div>
              <Text size="xs" c="dimmed">Confidence</Text>
              <Badge
                variant="light"
                color={conf >= 0.85 ? 'green' : conf >= 0.65 ? 'yellow' : 'red'}
                size="sm"
              >
                {(conf * 100).toFixed(0)}%
              </Badge>
            </div>
          )}
        </Group>

        <Divider />

        {/* Requirements */}
        <div>
          <Text fw={600} mb={4}>Required Documents</Text>
          <Text size="xs" c="dimmed" mb="sm">
            Documents required based on the contingencies in this offer.
          </Text>

          {requirements.length === 0 ? (
            <Text size="sm" c="dimmed">No contingency-based requirements detected.</Text>
          ) : (
            <Stack gap="xs">
              {requirements.map(({ rule, satisfied }) => (
                <Group key={rule.doc_type} justify="space-between" align="flex-start" wrap="nowrap">
                  <Group align="flex-start" gap="sm" wrap="nowrap">
                    <ThemeIcon
                      color={satisfied ? 'green' : 'gray'}
                      variant="light"
                      size="sm"
                      style={{ flexShrink: 0, marginTop: 2 }}
                    >
                      {satisfied ? (
                        <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                          <path d="M2 5l2 2 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      ) : (
                        <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                          <circle cx="5" cy="5" r="3.5" stroke="currentColor" strokeWidth="1.5" />
                        </svg>
                      )}
                    </ThemeIcon>
                    <Stack gap={0}>
                      <Text size="sm" fw={500}>{rule.label}</Text>
                      <Text size="xs" c="dimmed">{rule.description}</Text>
                      <Text size="xs" c="dimmed">
                        From: {ROLE_LABELS[rule.role] ?? rule.role}
                      </Text>
                    </Stack>
                  </Group>
                  <Group gap="xs" style={{ flexShrink: 0 }}>
                    <Badge
                      variant="light"
                      color={satisfied ? 'green' : 'orange'}
                      size="sm"
                    >
                      {satisfied ? 'Received' : 'Pending'}
                    </Badge>
                    {!satisfied && (
                      <Button
                        size="xs"
                        variant="light"
                        color="cyan"
                        loading={uploading === rule.doc_type}
                        onClick={() => handleUploadClick(rule.doc_type)}
                      >
                        Upload
                      </Button>
                    )}
                  </Group>
                </Group>
              ))}
            </Stack>
          )}

          {uploadError && (
            <Text size="xs" c="red" mt="sm">{uploadError}</Text>
          )}
        </div>
      </Stack>
    </Modal>
  );
}
