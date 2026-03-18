/** Transaction list page — view, create, and manage deals + connected loops. */

import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Button, Badge, Alert, TextInput, Select, Group, Card, SimpleGrid } from '@mantine/core';
import { useTransactionList } from '../hooks/useTransaction';
import { useIntegrations } from '../hooks/useIntegrations';
import { fetchDotloopLoops } from '../api';
import type { DotloopLoop } from '../api';
import { STATUS_LABELS, STATUS_COLORS, type Transaction } from '../types/transaction';

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
          <span className="source-dotloop">Dotloop</span> linked
        </div>
      )}
    </Card>
  );
}

function LoopCard({ loop }: { loop: DotloopLoop }) {
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
      <p className="txn-card-loop-hint">Link to a transaction from its Overview tab</p>
    </Card>
  );
}

export function TransactionList() {
  const { transactions, loading, error, create } = useTransactionList();
  const { dotloopConnected, loading: integrationsLoading } = useIntegrations();
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [agentRole, setAgentRole] = useState<'listing_agent' | 'buying_agent'>('listing_agent');
  const [creating, setCreating] = useState(false);

  const [loops, setLoops] = useState<DotloopLoop[]>([]);
  const [loopsLoading, setLoopsLoading] = useState(false);

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

  return (
    <div className="page-transactions">
      <Group justify="space-between" mb="lg">
        <div>
          <h1>Transactions</h1>
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
                  Set up integrations in Profile &rarr;
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
                    <LoopCard key={`dl-${loop.id}`} loop={loop} />
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
                  Set up integrations in Profile &rarr;
                </Link>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
