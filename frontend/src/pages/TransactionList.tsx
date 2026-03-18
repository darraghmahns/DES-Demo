/** Transaction list page — view, create, and manage deals + connected loops. */

import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button, Badge, Alert, TextInput, Select, Group, Card, SimpleGrid, Modal, Stack } from '@mantine/core';
import { useTransactionList } from '../hooks/useTransaction';
import { useIntegrations } from '../hooks/useIntegrations';
import { fetchDotloopLoops } from '../api';
import type { DotloopLoop } from '../api';
import { IconImport, IconTransactions } from '../components/common/AppIcons';
import { STATUS_LABELS, STATUS_COLORS, type Transaction } from '../types/transaction';
import {
  createTransactionFromDotloop,
  previewTransactionFromDotloop,
  type DotloopTransactionPreview,
} from '../api/transactions';

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
  });
}

function formatPrice(amount?: number): string {
  if (!amount) return '--';
  return `$${amount.toLocaleString()}`;
}

function TransactionCard({ txn, highlight = false }: { txn: Transaction; highlight?: boolean }) {
  const activeParticipants = txn.participants.filter(p => p.status !== 'removed');
  const addr = txn.property_address;
  const addrLine = addr
    ? `${addr.street_number} ${addr.street_name}, ${addr.city}, ${addr.state_or_province}`
    : null;

  return (
    <Card
      shadow="sm"
      withBorder
      radius="md"
      component={Link}
      to={`/transactions/${txn._id}`}
      className={highlight ? 'txn-card-highlighted' : undefined}
      style={{ textDecoration: 'none', color: 'inherit' }}
    >
      <div className="txn-card-header">
        <h3 className="txn-card-name">{txn.name}</h3>
        <Badge color={STATUS_COLORS[txn.status]} variant="light">
          {STATUS_LABELS[txn.status]}
        </Badge>
      </div>

      {addrLine && <p className="txn-card-address">{addrLine}</p>}

      <div className="txn-card-details">
        <div className="txn-card-detail">
          <span className="detail-label">Price</span>
          <span className="detail-value">{formatPrice(txn.purchase_price)}</span>
        </div>
        <div className="txn-card-detail">
          <span className="detail-label">Participants</span>
          <span className="detail-value">{activeParticipants.length}</span>
        </div>
        <div className="txn-card-detail">
          <span className="detail-label">Created</span>
          <span className="detail-value">{formatDate(txn.created_at)}</span>
        </div>
      </div>

      {txn.closing_date && (
        <div className="txn-card-closing">
          Closing: {formatDate(txn.closing_date)}
        </div>
      )}

      {txn.dotloop_loop_id && (
        <div className="txn-card-loop-badge">
          <span className="source-dotloop">Dotloop</span> {txn.dotloop_sync_status || 'linked'}
        </div>
      )}
    </Card>
  );
}

function LoopCard({
  loop,
  onCreate,
  busy,
}: {
  loop: DotloopLoop;
  onCreate: () => void;
  busy: boolean;
}) {
  return (
    <Card shadow="sm" withBorder radius="md" className="loop-card">
      <div className="txn-card-header">
        <h3 className="txn-card-name">{loop.name}</h3>
        <Badge color="green" variant="light">
          {loop.status || 'Active'}
        </Badge>
      </div>
      <div className="txn-card-details">
        <div className="txn-card-detail">
          <span className="detail-label">Type</span>
          <span className="detail-value">{loop.transactionType || '--'}</span>
        </div>
        <div className="txn-card-detail">
          <span className="detail-label">Source</span>
          <span className="detail-value source-dotloop">Dotloop</span>
        </div>
        {loop.updated && (
          <div className="txn-card-detail">
            <span className="detail-label">Updated</span>
            <span className="detail-value">{formatDate(loop.updated)}</span>
          </div>
        )}
      </div>
      <Group justify="space-between" mt="md">
        <p className="txn-card-loop-hint">Create a local transaction from this loop.</p>
        <Button size="xs" color="campari" variant="light" onClick={onCreate} disabled={busy}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <IconImport size={14} />
            <span>{busy ? 'Loading...' : 'Create from Dotloop'}</span>
          </span>
        </Button>
      </Group>
    </Card>
  );
}

export function TransactionList() {
  const navigate = useNavigate();
  const { transactions, loading, error, create } = useTransactionList();
  const { dotloopConnected, loading: integrationsLoading } = useIntegrations();
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [agentRole, setAgentRole] = useState<'listing_agent' | 'buying_agent'>('listing_agent');
  const [creating, setCreating] = useState(false);

  const [loops, setLoops] = useState<DotloopLoop[]>([]);
  const [loopsLoading, setLoopsLoading] = useState(false);
  const [previewLoopId, setPreviewLoopId] = useState<number | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [preview, setPreview] = useState<DotloopTransactionPreview | null>(null);
  const [creatingFromLoop, setCreatingFromLoop] = useState(false);

  useEffect(() => {
    if (integrationsLoading) return;
    if (!dotloopConnected) return;

    setLoopsLoading(true);
    fetchDotloopLoops()
      .then(setLoops)
      .catch(() => setLoops([]))
      .finally(() => setLoopsLoading(false));
  }, [dotloopConnected, integrationsLoading]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    setCreating(true);
    try {
      await create({ name: newName.trim(), agent_role: agentRole });
      setNewName('');
      setShowCreate(false);
    } catch { /* handled by hook */ }
    setCreating(false);
  };

  const active = transactions.filter(t => !['closed', 'cancelled', 'expired'].includes(t.status));
  const closed = transactions.filter(t => ['closed', 'cancelled', 'expired'].includes(t.status));

  // Only show loops that aren't already linked to a transaction
  const linkedLoopIds = new Set(transactions.map(t => t.dotloop_loop_id).filter(Boolean));
  const unlinkedLoops = loops.filter(l => !linkedLoopIds.has(String(l.id)));
  const hasConnectedLoops = unlinkedLoops.length > 0;
  const dotloopNotConnected = !dotloopConnected && !integrationsLoading;

  const openDotloopPreview = async (loop: DotloopLoop) => {
    setPreviewLoopId(loop.id);
    setPreview(null);
    setPreviewError(null);
    setPreviewLoading(true);
    try {
      setPreview(await previewTransactionFromDotloop(loop.id));
    } catch (err) {
      setPreviewError(err instanceof Error ? err.message : 'Failed to preview Dotloop loop.');
    } finally {
      setPreviewLoading(false);
    }
  };

  const closePreview = () => {
    setPreviewLoopId(null);
    setPreview(null);
    setPreviewError(null);
    setCreatingFromLoop(false);
  };

  const handleCreateFromLoop = async () => {
    if (!previewLoopId) return;
    setCreatingFromLoop(true);
    setPreviewError(null);
    try {
      const txn = await createTransactionFromDotloop(previewLoopId, {
        agent_role: preview?.normalized_transaction.agent_role,
      });
      closePreview();
      navigate(`/transactions/${txn._id}`);
    } catch (err) {
      setPreviewError(err instanceof Error ? err.message : 'Failed to create transaction from Dotloop.');
    } finally {
      setCreatingFromLoop(false);
    }
  };

  return (
    <div className="page-transactions">
      <Group justify="space-between" mb="lg">
        <div>
          <h1 style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <IconTransactions size={22} />
            <span>Transactions</span>
          </h1>
          <p className="page-subtitle">Manage your real estate deals</p>
        </div>
        <Button variant="filled" color="cyan" onClick={() => setShowCreate(!showCreate)}>
          + New Transaction
        </Button>
      </Group>

      {showCreate && (
        <form onSubmit={handleCreate}>
          <Group gap="sm" align="flex-end" mb="md">
            <TextInput
              placeholder="Transaction name (e.g., 123 Main St Purchase)"
              value={newName}
              onChange={e => setNewName(e.target.value)}
              autoFocus
              size="sm"
              style={{ flex: 1 }}
            />
            <Select
              value={agentRole}
              onChange={(val) => { if (val) setAgentRole(val as 'listing_agent' | 'buying_agent'); }}
              data={[
                { value: 'listing_agent', label: 'Listing Agent (representing seller)' },
                { value: 'buying_agent', label: "Buyer's Agent (representing buyer)" },
              ]}
              size="sm"
            />
            <Button type="submit" variant="filled" color="cyan" disabled={creating || !newName.trim()}>
              {creating ? 'Creating...' : 'Create'}
            </Button>
            <Button type="button" variant="outline" color="cyan" onClick={() => setShowCreate(false)}>
              Cancel
            </Button>
          </Group>
        </form>
      )}

      {error && <Alert color="red" mb="sm">{error}</Alert>}

      {loading ? (
        <div className="loading-state">Loading transactions...</div>
      ) : transactions.length === 0 && !hasConnectedLoops ? (
        <div className="empty-state">
          <p>No transactions yet.</p>
          <p>Create your first transaction to start managing a deal.</p>
          {dotloopNotConnected && (
            <div className="txn-connect-banner" style={{ marginTop: 16 }}>
              <div>
                <p><strong>Connect Dotloop</strong> to see your loops here.</p>
                <Link to="/profile" className="integration-profile-link">
                  Set up integrations in Profile &gt;
                </Link>
              </div>
            </div>
          )}
        </div>
      ) : (
        <>
          {active.length > 0 && (
            <div className="txn-section">
              <h2 className="txn-section-title">Active ({active.length})</h2>
              <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }} spacing="md">
                {active.map(txn => (
                  <TransactionCard key={txn._id} txn={txn} highlight />
                ))}
              </SimpleGrid>
            </div>
          )}

          {closed.length > 0 && (
            <div className="txn-section">
              <h2 className="txn-section-title">Closed ({closed.length})</h2>
              <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }} spacing="md">
                {closed.map(txn => (
                  <TransactionCard key={txn._id} txn={txn} />
                ))}
              </SimpleGrid>
            </div>
          )}

          {/* Unlinked Dotloop Loops — only loops not yet tied to a transaction */}
          {(hasConnectedLoops || loopsLoading) && (
            <div className="txn-section">
              <h2 className="txn-section-title">
                Unlinked Loops
                {unlinkedLoops.length > 0 && (
                  <span className="txn-section-count"> ({unlinkedLoops.length})</span>
                )}
              </h2>
              {loopsLoading ? (
                <div className="loading-state">Loading from Dotloop...</div>
              ) : (
                <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }} spacing="md">
                  {unlinkedLoops.map(loop => (
                    <LoopCard
                      key={`dl-${loop.id}`}
                      loop={loop}
                      onCreate={() => void openDotloopPreview(loop)}
                      busy={previewLoopId === loop.id && previewLoading}
                    />
                  ))}
                </SimpleGrid>
              )}
            </div>
          )}

          {dotloopNotConnected && transactions.length > 0 && (
            <div className="txn-connect-banner" style={{ marginTop: 16 }}>
              <div>
                <p>Connect <strong>Dotloop</strong> to see your loops alongside your transactions.</p>
                <Link to="/profile" className="integration-profile-link">
                  Set up integrations in Profile &gt;
                </Link>
              </div>
            </div>
          )}
        </>
      )}

      <Modal
        opened={previewLoopId !== null}
        onClose={closePreview}
        title="Create Transaction from Dotloop"
        size="lg"
      >
        <Stack gap="sm">
          {previewError && <Alert color="red">{previewError}</Alert>}
          {previewLoading ? (
            <div className="loading-state">Loading Dotloop preview...</div>
          ) : preview ? (
            <>
              {preview.existing_transaction_id && (
                <Alert color="yellow">
                  This loop is already linked to transaction {preview.existing_transaction_id}.
                </Alert>
              )}
              <div className="dotloop-preview-grid">
                <div>
                  <strong>Name</strong>
                  <div>{preview.normalized_transaction.name}</div>
                </div>
                <div>
                  <strong>Type</strong>
                  <div>{preview.normalized_transaction.transaction_type}</div>
                </div>
                <div>
                  <strong>Price</strong>
                  <div>{preview.normalized_transaction.purchase_price ?? '--'}</div>
                </div>
                <div>
                  <strong>Closing</strong>
                  <div>{preview.normalized_transaction.closing_date ? formatDate(preview.normalized_transaction.closing_date) : '--'}</div>
                </div>
                <div>
                  <strong>Participants</strong>
                  <div>{preview.participant_suggestions.length}</div>
                </div>
                <div>
                  <strong>PDF Documents</strong>
                  <div>{preview.available_documents.pdf_count}</div>
                </div>
              </div>
              {preview.warnings.length > 0 && (
                <Alert color="yellow">
                  {preview.warnings.join(' ')}
                </Alert>
              )}
              <Group justify="flex-end">
                <Button variant="default" onClick={closePreview}>Cancel</Button>
                <Button
                  color="campari"
                  onClick={() => void handleCreateFromLoop()}
                  disabled={Boolean(preview.existing_transaction_id) || creatingFromLoop}
                >
                  {creatingFromLoop ? 'Creating...' : 'Create Transaction'}
                </Button>
              </Group>
            </>
          ) : null}
        </Stack>
      </Modal>
    </div>
  );
}
