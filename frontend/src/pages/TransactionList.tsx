/** Transaction list page — view, create, and manage deals + connected loops/envelopes. */

import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useTransactionList } from '../hooks/useTransaction';
import { useIntegrations } from '../hooks/useIntegrations';
import { fetchDotloopLoops, fetchDocuSignEnvelopes } from '../api';
import type { DotloopLoop, DocuSignEnvelope } from '../api';
import type { Transaction, TransactionStatus } from '../types/transaction';

const STATUS_LABELS: Record<TransactionStatus, string> = {
  draft: 'Draft',
  active: 'Active',
  under_contract: 'Under Contract',
  pending_close: 'Pending Close',
  closed: 'Closed',
  cancelled: 'Cancelled',
  expired: 'Expired',
};

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
  });
}

function formatPrice(amount?: number): string {
  if (!amount) return '--';
  return `$${amount.toLocaleString()}`;
}

function TransactionCard({ txn }: { txn: Transaction }) {
  const activeParticipants = txn.participants.filter(p => p.status !== 'removed');
  const addr = txn.property_address;
  const addrLine = addr
    ? `${addr.street_number} ${addr.street_name}, ${addr.city}, ${addr.state_or_province}`
    : null;

  return (
    <Link to={`/transactions/${txn._id}`} className="txn-card">
      <div className="txn-card-header">
        <h3 className="txn-card-name">{txn.name}</h3>
        <span className={`txn-status-badge status-${txn.status}`}>
          {STATUS_LABELS[txn.status]}
        </span>
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
    </Link>
  );
}

function LoopCard({ loop }: { loop: DotloopLoop }) {
  return (
    <Link to="/extraction" className="txn-card loop-card">
      <div className="txn-card-header">
        <h3 className="txn-card-name">{loop.name}</h3>
        <span className="txn-status-badge status-active">
          {loop.status || 'Active'}
        </span>
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
    </Link>
  );
}

function EnvelopeCard({ envelope }: { envelope: DocuSignEnvelope }) {
  return (
    <Link to="/extraction" className="txn-card loop-card">
      <div className="txn-card-header">
        <h3 className="txn-card-name">{envelope.emailSubject || 'Untitled'}</h3>
        <span className={`txn-status-badge status-${envelope.status === 'completed' ? 'closed' : 'active'}`}>
          {envelope.status}
        </span>
      </div>
      <div className="txn-card-details">
        <div className="txn-card-detail">
          <span className="detail-label">Source</span>
          <span className="detail-value source-docusign">DocuSign</span>
        </div>
        {envelope.createdDateTime && (
          <div className="txn-card-detail">
            <span className="detail-label">Created</span>
            <span className="detail-value">{formatDate(envelope.createdDateTime)}</span>
          </div>
        )}
        {envelope.completedDateTime && (
          <div className="txn-card-detail">
            <span className="detail-label">Completed</span>
            <span className="detail-value">{formatDate(envelope.completedDateTime)}</span>
          </div>
        )}
      </div>
    </Link>
  );
}

export function TransactionList() {
  const { transactions, loading, error, create } = useTransactionList();
  const { dotloopConnected, docusignConnected, loading: integrationsLoading } = useIntegrations();
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [creating, setCreating] = useState(false);

  // Dotloop loops & DocuSign envelopes
  const [loops, setLoops] = useState<DotloopLoop[]>([]);
  const [envelopes, setEnvelopes] = useState<DocuSignEnvelope[]>([]);
  const [loopsLoading, setLoopsLoading] = useState(false);

  // Fetch loops/envelopes when integration status is known
  useEffect(() => {
    if (integrationsLoading) return;
    if (!dotloopConnected && !docusignConnected) return;

    setLoopsLoading(true);
    const fetches: Promise<void>[] = [];

    if (dotloopConnected) {
      fetches.push(
        fetchDotloopLoops()
          .then(setLoops)
          .catch(() => setLoops([])),
      );
    }
    if (docusignConnected) {
      fetches.push(
        fetchDocuSignEnvelopes()
          .then(setEnvelopes)
          .catch(() => setEnvelopes([])),
      );
    }

    Promise.all(fetches).finally(() => setLoopsLoading(false));
  }, [dotloopConnected, docusignConnected, integrationsLoading]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    setCreating(true);
    try {
      await create({ name: newName.trim() });
      setNewName('');
      setShowCreate(false);
    } catch { /* handled by hook */ }
    setCreating(false);
  };

  const active = transactions.filter(t => !['closed', 'cancelled', 'expired'].includes(t.status));
  const closed = transactions.filter(t => ['closed', 'cancelled', 'expired'].includes(t.status));
  const hasConnectedLoops = loops.length > 0 || envelopes.length > 0;
  const neitherConnected = !dotloopConnected && !docusignConnected && !integrationsLoading;

  return (
    <div className="page-transactions">
      <div className="page-header-row">
        <div>
          <h1>Transactions</h1>
          <p className="page-subtitle">Manage your real estate deals</p>
        </div>
        <button className="btn-primary" onClick={() => setShowCreate(!showCreate)}>
          + New Transaction
        </button>
      </div>

      {showCreate && (
        <form className="txn-create-form" onSubmit={handleCreate}>
          <input
            type="text"
            placeholder="Transaction name (e.g., 123 Main St Purchase)"
            value={newName}
            onChange={e => setNewName(e.target.value)}
            autoFocus
          />
          <button type="submit" className="btn-primary" disabled={creating || !newName.trim()}>
            {creating ? 'Creating...' : 'Create'}
          </button>
          <button type="button" className="btn-secondary" onClick={() => setShowCreate(false)}>
            Cancel
          </button>
        </form>
      )}

      {error && <div className="error-banner">{error}</div>}

      {/* Connected Loops & Envelopes */}
      {(hasConnectedLoops || loopsLoading) && (
        <div className="txn-section">
          <h2 className="txn-section-title">
            Connected Loops &amp; Envelopes
            {loops.length + envelopes.length > 0 && (
              <span className="txn-section-count"> ({loops.length + envelopes.length})</span>
            )}
          </h2>
          {loopsLoading ? (
            <div className="loading-state">Loading from connected services...</div>
          ) : (
            <div className="txn-grid">
              {loops.map(loop => (
                <LoopCard key={`dl-${loop.id}`} loop={loop} />
              ))}
              {envelopes.map(env => (
                <EnvelopeCard key={`ds-${env.envelopeId}`} envelope={env} />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Prompt to connect if no integrations */}
      {neitherConnected && transactions.length === 0 && (
        <div className="txn-connect-banner">
          <span className="txn-connect-icon">&#x1F517;</span>
          <div>
            <p><strong>Connect Dotloop or DocuSign</strong> to see your loops and envelopes here.</p>
            <Link to="/profile" className="integration-profile-link">
              Set up integrations in Profile &rarr;
            </Link>
          </div>
        </div>
      )}

      {loading ? (
        <div className="loading-state">Loading transactions...</div>
      ) : transactions.length === 0 && !hasConnectedLoops ? (
        <div className="empty-state">
          <p>No transactions yet.</p>
          <p>Create your first transaction to start managing a deal.</p>
        </div>
      ) : (
        <>
          {active.length > 0 && (
            <div className="txn-section">
              <h2 className="txn-section-title">Active ({active.length})</h2>
              <div className="txn-grid">
                {active.map(txn => (
                  <TransactionCard key={txn._id} txn={txn} />
                ))}
              </div>
            </div>
          )}

          {closed.length > 0 && (
            <div className="txn-section">
              <h2 className="txn-section-title">Closed ({closed.length})</h2>
              <div className="txn-grid">
                {closed.map(txn => (
                  <TransactionCard key={txn._id} txn={txn} />
                ))}
              </div>
            </div>
          )}

          {/* Show connect prompt below transactions if not connected */}
          {neitherConnected && transactions.length > 0 && (
            <div className="txn-connect-banner" style={{ marginTop: 16 }}>
              <span className="txn-connect-icon">&#x1F517;</span>
              <div>
                <p>Connect <strong>Dotloop</strong> or <strong>DocuSign</strong> to see your loops and envelopes alongside your transactions.</p>
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
