/** Transaction detail (lobby) page — tabbed view with participant sidebar. */

import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useTransactionDetail } from '../hooks/useTransaction';
import { CompletionIndicator } from '../components/common/CompletionIndicator';
import type { ParticipantRole, TransactionStatus } from '../types/transaction';

const STATUS_LABELS: Record<TransactionStatus, string> = {
  draft: 'Draft',
  active: 'Active',
  under_contract: 'Under Contract',
  pending_close: 'Pending Close',
  closed: 'Closed',
  cancelled: 'Cancelled',
  expired: 'Expired',
};

const STATUS_FLOW: TransactionStatus[] = [
  'draft', 'active', 'under_contract', 'pending_close', 'closed',
];

const ROLE_LABELS: Record<string, string> = {
  BUYER: 'Buyer',
  SELLER: 'Seller',
  LISTING_AGENT: 'Listing Agent',
  BUYING_AGENT: 'Buying Agent',
  LISTING_BROKER: 'Listing Broker',
  BUYING_BROKER: 'Buying Broker',
  ESCROW_TITLE_REP: 'Escrow/Title',
  LOAN_OFFICER: 'Loan Officer',
  APPRAISER: 'Appraiser',
  INSPECTOR: 'Inspector',
  TRANSACTION_COORDINATOR: 'TC',
  OTHER: 'Other',
};

type TabKey = 'overview' | 'documents' | 'participants' | 'compliance';

function formatPrice(amount?: number): string {
  if (!amount) return '--';
  return `$${amount.toLocaleString()}`;
}

function formatDate(iso?: string): string {
  if (!iso) return '--';
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
  });
}

export function TransactionDetail() {
  const { id } = useParams<{ id: string }>();
  const {
    transaction, completion, loading, error,
    update, removeParticipantById,
    sendInvitation, runAutoFill,
  } = useTransactionDetail(id);
  const [activeTab, setActiveTab] = useState<TabKey>('overview');
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteName, setInviteName] = useState('');
  const [inviteRole, setInviteRole] = useState<ParticipantRole>('BUYER');
  const [inviting, setInviting] = useState(false);
  const [inviteResult, setInviteResult] = useState<string | null>(null);
  const [autoFillMsg, setAutoFillMsg] = useState<string | null>(null);

  if (loading) return <div className="loading-state">Loading transaction...</div>;
  if (error) return <div className="error-banner">{error}</div>;
  if (!transaction) return <div className="error-banner">Transaction not found</div>;

  const activeParticipants = transaction.participants.filter(p => p.status !== 'removed');
  const addr = transaction.property_address;

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteEmail.trim()) return;
    setInviting(true);
    setInviteResult(null);
    try {
      await sendInvitation(inviteEmail.trim(), inviteRole, inviteName.trim() || undefined);
      setInviteResult(`Invitation sent to ${inviteEmail}`);
      setInviteEmail('');
      setInviteName('');
    } catch (err) {
      setInviteResult(err instanceof Error ? err.message : 'Failed to send invitation');
    }
    setInviting(false);
  };

  const handleAutoFill = async () => {
    const fields = await runAutoFill();
    if (fields.length > 0) {
      setAutoFillMsg(`Auto-filled: ${fields.join(', ')}`);
    } else {
      setAutoFillMsg('No new fields to auto-fill.');
    }
    setTimeout(() => setAutoFillMsg(null), 5000);
  };

  const handleStatusAdvance = async () => {
    const currentIdx = STATUS_FLOW.indexOf(transaction.status);
    if (currentIdx >= 0 && currentIdx < STATUS_FLOW.length - 1) {
      await update({ status: STATUS_FLOW[currentIdx + 1] });
    }
  };

  const nextStatus = STATUS_FLOW[STATUS_FLOW.indexOf(transaction.status) + 1];

  return (
    <div className="page-transaction-detail">
      <div className="txn-detail-header">
        <div>
          <Link to="/transactions" className="back-link">&larr; All Transactions</Link>
          <h1>{transaction.name}</h1>
          {addr && (
            <p className="txn-address">
              {addr.street_number} {addr.street_name}
              {addr.unit_number ? ` #${addr.unit_number}` : ''}, {addr.city}, {addr.state_or_province} {addr.postal_code}
            </p>
          )}
        </div>
        <div className="txn-header-actions">
          <span className={`txn-status-badge status-${transaction.status}`}>
            {STATUS_LABELS[transaction.status]}
          </span>
          {nextStatus && (
            <button className="btn-primary btn-sm" onClick={handleStatusAdvance}>
              Advance to {STATUS_LABELS[nextStatus]}
            </button>
          )}
        </div>
      </div>

      {completion && (
        <div className="txn-completion-bar">
          <CompletionIndicator percentage={completion.overall} label="Transaction Readiness" size="md" />
        </div>
      )}

      {autoFillMsg && <div className="info-banner">{autoFillMsg}</div>}

      <div className="txn-lobby">
        {/* Sidebar */}
        <aside className="txn-sidebar">
          <div className="sidebar-section">
            <h3>Participants ({activeParticipants.length})</h3>
            {activeParticipants.map(p => {
              const pInfo = completion?.participants.find(cp => cp.user_id === p.user_id);
              return (
                <div key={p.user_id} className="participant-card">
                  <div className="participant-info">
                    <span className="participant-name">{pInfo?.name || 'Unknown'}</span>
                    <span className="participant-role">{ROLE_LABELS[p.role] || p.role}</span>
                  </div>
                  <div className="participant-meta">
                    <span className={`participant-status ps-${p.status}`}>{p.status}</span>
                    {pInfo && (
                      <CompletionIndicator percentage={pInfo.profile_completion} size="sm" />
                    )}
                  </div>
                  {p.status !== 'removed' && (
                    <button
                      className="btn-link btn-sm btn-danger-text"
                      onClick={() => removeParticipantById(p.user_id)}
                    >
                      Remove
                    </button>
                  )}
                </div>
              );
            })}
          </div>

          <div className="sidebar-section">
            <h3>Invite Participant</h3>
            <form className="invite-form" onSubmit={handleInvite}>
              <input
                type="email"
                placeholder="Email address"
                value={inviteEmail}
                onChange={e => setInviteEmail(e.target.value)}
                required
              />
              <input
                type="text"
                placeholder="Name (optional)"
                value={inviteName}
                onChange={e => setInviteName(e.target.value)}
              />
              <select value={inviteRole} onChange={e => setInviteRole(e.target.value as ParticipantRole)}>
                <option value="BUYER">Buyer</option>
                <option value="SELLER">Seller</option>
                <option value="BUYING_AGENT">Buying Agent</option>
                <option value="LISTING_AGENT">Listing Agent</option>
                <option value="LOAN_OFFICER">Loan Officer</option>
                <option value="ESCROW_TITLE_REP">Escrow/Title</option>
                <option value="INSPECTOR">Inspector</option>
                <option value="APPRAISER">Appraiser</option>
              </select>
              <button type="submit" className="btn-primary btn-sm" disabled={inviting}>
                {inviting ? 'Sending...' : 'Send Invite'}
              </button>
            </form>
            {inviteResult && <p className="invite-result">{inviteResult}</p>}
          </div>

          <div className="sidebar-section">
            <button className="btn-secondary" onClick={handleAutoFill}>
              Auto-Fill from Profiles
            </button>
          </div>
        </aside>

        {/* Main Content - Tabs */}
        <div className="txn-main">
          <div className="txn-tabs">
            {(['overview', 'documents', 'participants', 'compliance'] as TabKey[]).map(tab => (
              <button
                key={tab}
                className={`txn-tab ${activeTab === tab ? 'active' : ''}`}
                onClick={() => setActiveTab(tab)}
              >
                {tab.charAt(0).toUpperCase() + tab.slice(1)}
              </button>
            ))}
          </div>

          <div className="txn-tab-content">
            {activeTab === 'overview' && (
              <OverviewTab
                transaction={transaction}
                onUpdate={update}
              />
            )}
            {activeTab === 'documents' && (
              <DocumentsTab completion={completion} />
            )}
            {activeTab === 'participants' && (
              <ParticipantsTab completion={completion} />
            )}
            {activeTab === 'compliance' && (
              <div className="tab-placeholder">
                <p>Compliance integration coming soon.</p>
                <p>This tab will show jurisdiction requirements from JACE.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}


/* ---- Tab Components ---- */

function OverviewTab({
  transaction, onUpdate,
}: {
  transaction: NonNullable<ReturnType<typeof useTransactionDetail>['transaction']>;
  onUpdate: ReturnType<typeof useTransactionDetail>['update'];
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(transaction.name);
  const [price, setPrice] = useState(transaction.purchase_price?.toString() || '');
  const [earnest, setEarnest] = useState(transaction.earnest_money?.toString() || '');
  const [mls, setMls] = useState(transaction.mls_number || '');

  const handleSave = async () => {
    await onUpdate({
      name: name || undefined,
      purchase_price: price ? parseFloat(price) : undefined,
      earnest_money: earnest ? parseFloat(earnest) : undefined,
      mls_number: mls || undefined,
    });
    setEditing(false);
  };

  return (
    <div className="overview-tab">
      <div className="overview-section">
        <div className="section-header">
          <h3>Deal Information</h3>
          <button className="btn-link" onClick={() => setEditing(!editing)}>
            {editing ? 'Cancel' : 'Edit'}
          </button>
        </div>

        {editing ? (
          <div className="form-grid">
            <div className="form-field">
              <label>Transaction Name</label>
              <input value={name} onChange={e => setName(e.target.value)} />
            </div>
            <div className="form-field">
              <label>Purchase Price</label>
              <input type="number" value={price} onChange={e => setPrice(e.target.value)} placeholder="0" />
            </div>
            <div className="form-field">
              <label>Earnest Money</label>
              <input type="number" value={earnest} onChange={e => setEarnest(e.target.value)} placeholder="0" />
            </div>
            <div className="form-field">
              <label>MLS Number</label>
              <input value={mls} onChange={e => setMls(e.target.value)} placeholder="e.g. MLS-12345" />
            </div>
            <div className="form-actions">
              <button className="btn-primary" onClick={handleSave}>Save</button>
            </div>
          </div>
        ) : (
          <div className="overview-grid">
            <div className="overview-item">
              <span className="overview-label">Type</span>
              <span className="overview-value">{transaction.transaction_type}</span>
            </div>
            <div className="overview-item">
              <span className="overview-label">Purchase Price</span>
              <span className="overview-value">{formatPrice(transaction.purchase_price)}</span>
            </div>
            <div className="overview-item">
              <span className="overview-label">Earnest Money</span>
              <span className="overview-value">{formatPrice(transaction.earnest_money)}</span>
            </div>
            <div className="overview-item">
              <span className="overview-label">MLS #</span>
              <span className="overview-value">{transaction.mls_number || '--'}</span>
            </div>
            <div className="overview-item">
              <span className="overview-label">Closing Date</span>
              <span className="overview-value">{formatDate(transaction.closing_date)}</span>
            </div>
            <div className="overview-item">
              <span className="overview-label">Created</span>
              <span className="overview-value">{formatDate(transaction.created_at)}</span>
            </div>
          </div>
        )}
      </div>

      {transaction.property_address && (
        <div className="overview-section">
          <h3>Property</h3>
          <div className="overview-grid">
            <div className="overview-item">
              <span className="overview-label">Address</span>
              <span className="overview-value">
                {transaction.property_address.street_number} {transaction.property_address.street_name}
              </span>
            </div>
            <div className="overview-item">
              <span className="overview-label">City</span>
              <span className="overview-value">{transaction.property_address.city}</span>
            </div>
            <div className="overview-item">
              <span className="overview-label">State</span>
              <span className="overview-value">{transaction.property_address.state_or_province}</span>
            </div>
            <div className="overview-item">
              <span className="overview-label">ZIP</span>
              <span className="overview-value">{transaction.property_address.postal_code}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


function DocumentsTab({ completion }: { completion: ReturnType<typeof useTransactionDetail>['completion'] }) {
  if (!completion) return <div className="loading-state">Loading...</div>;

  const { requirements } = completion.documents;
  const required = requirements.filter(r => r.required);
  const optional = requirements.filter(r => !r.required);

  return (
    <div className="documents-tab">
      <div className="doc-completion-summary">
        <CompletionIndicator
          percentage={completion.documents.completion}
          label="Documents"
          size="md"
        />
        <span className="doc-summary-text">
          {completion.documents.satisfied} of {completion.documents.total_required} required documents submitted
        </span>
      </div>

      <div className="doc-requirements-section">
        <h3>Required Documents</h3>
        <div className="doc-requirements-list">
          {required.map((r, i) => (
            <div key={i} className={`doc-requirement ${r.satisfied ? 'satisfied' : 'pending'}`}>
              <span className="doc-req-icon">{r.satisfied ? '\u2713' : '\u25CB'}</span>
              <span className="doc-req-type">{r.doc_type.replace(/_/g, ' ')}</span>
              <span className="doc-req-role">{ROLE_LABELS[r.role] || r.role}</span>
              <span className={`doc-req-status ${r.satisfied ? 'status-ok' : 'status-pending'}`}>
                {r.satisfied ? 'Submitted' : 'Pending'}
              </span>
            </div>
          ))}
        </div>
      </div>

      {optional.length > 0 && (
        <div className="doc-requirements-section">
          <h3>Optional Documents</h3>
          <div className="doc-requirements-list">
            {optional.map((r, i) => (
              <div key={i} className={`doc-requirement ${r.satisfied ? 'satisfied' : 'optional'}`}>
                <span className="doc-req-icon">{r.satisfied ? '\u2713' : '\u2014'}</span>
                <span className="doc-req-type">{r.doc_type.replace(/_/g, ' ')}</span>
                <span className="doc-req-role">{ROLE_LABELS[r.role] || r.role}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}


function ParticipantsTab({ completion }: { completion: ReturnType<typeof useTransactionDetail>['completion'] }) {
  if (!completion) return <div className="loading-state">Loading...</div>;

  return (
    <div className="participants-tab">
      <div className="participants-grid">
        {completion.participants.map(p => (
          <div key={p.user_id} className="participant-detail-card">
            <div className="participant-detail-header">
              <h4>{p.name || p.email}</h4>
              <span className={`txn-status-badge status-${p.status}`}>{p.status}</span>
            </div>
            <div className="participant-detail-meta">
              <span>{ROLE_LABELS[p.role] || p.role}</span>
              <span>{p.email}</span>
            </div>
            <CompletionIndicator
              percentage={p.profile_completion}
              label="Profile"
              size="sm"
            />
          </div>
        ))}
      </div>
    </div>
  );
}
