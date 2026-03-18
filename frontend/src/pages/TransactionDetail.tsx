/** Transaction detail (lobby) page — tabbed view with participant sidebar. */

import { useState, useEffect, useRef } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { Button, Badge, Alert, TextInput, Select, NumberInput, SimpleGrid, Stack, Group, Tabs, Card } from '@mantine/core';
import { useTransactionDetail } from '../hooks/useTransaction';
import { CompletionIndicator } from '../components/common/CompletionIndicator';
import { STATUS_LABELS, STATUS_COLORS, ROLE_LABELS, type ParticipantRole, type TransactionStatus } from '../types/transaction';
import {
  listTransactionDocuments,
  linkDotloopLoop,
  type TransactionDocRecord,
} from '../api/transactions';
import { uploadFile, startExtraction, subscribeToTask, fetchDotloopLoops, searchDotloopLoops, fetchOffersComparison } from '../api';
import type { SSEEvent, DotloopLoop, OffersComparisonResult, OfferData, OfferField } from '../api';
import { useIntegrations } from '../hooks/useIntegrations';
import { OfferRequirementsModal } from '../components/offers/OfferRequirementsModal';
import { evaluateOfferRequirements } from '../types/offerRequirements';

const PARTICIPANT_STATUS_COLORS: Record<string, string> = {
  pending: 'yellow',
  accepted: 'green',
  removed: 'gray',
};

const STATUS_FLOW: TransactionStatus[] = [
  'draft', 'active', 'under_contract', 'pending_close', 'closed',
];

type TabKey = 'overview' | 'documents' | 'offers';

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

interface InlineUploadState {
  status: 'idle' | 'uploading' | 'extracting' | 'linking' | 'done' | 'error';
  filename?: string;
  progress?: string;
  error?: string;
}

export function TransactionDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const {
    transaction, completion, loading, error,
    update, removeParticipantById,
    sendInvitation, runAutoFill,
    extractions, unlinkExtraction, linkExtraction,
  } = useTransactionDetail(id);
  const [activeTab, setActiveTab] = useState<TabKey>('overview');
  const [offersData, setOffersData] = useState<OffersComparisonResult | null>(null);
  const [selectedOfferId, setSelectedOfferId] = useState<string | null>(null);
  const [docs, setDocs] = useState<TransactionDocRecord[]>([]);
  const [docsLoading, setDocsLoading] = useState(true);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteName, setInviteName] = useState('');
  const [inviteRole, setInviteRole] = useState<ParticipantRole>('BUYER');
  const [inviting, setInviting] = useState(false);
  const [inviteResult, setInviteResult] = useState<string | null>(null);
  const [autoFillMsg, setAutoFillMsg] = useState<string | null>(null);

  // Upload state lives here so it persists across tab switches
  const [uploadState, setUploadState] = useState<InlineUploadState>({ status: 'idle' });
  const unsubRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    return () => { unsubRef.current?.(); };
  }, []);

  useEffect(() => {
    if (extractions.length === 0) {
      setOffersData(null);
      setSelectedOfferId(null);
      return;
    }
    fetchOffersComparison(extractions.map(e => e.id))
      .then(result => {
        setOffersData(result);
        setSelectedOfferId(result.offers[0]?.extraction_id ?? null);
      })
      .catch(() => {
        setOffersData(null);
        setSelectedOfferId(null);
      });
  }, [extractions]);

  const refreshDocs = () => {
    if (!id) return;
    listTransactionDocuments(id).then(setDocs).catch(() => setDocs([]));
  };

  useEffect(() => {
    if (!id) return;
    listTransactionDocuments(id)
      .then(setDocs)
      .catch(() => setDocs([]))
      .finally(() => setDocsLoading(false));
  }, [id]);

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = '';

    setUploadState({ status: 'uploading', filename: file.name, progress: 'Uploading...' });

    let docInfo: { name: string };
    try {
      docInfo = await uploadFile(file);
    } catch (err) {
      setUploadState({ status: 'error', error: err instanceof Error ? err.message : 'Upload failed' });
      return;
    }

    setUploadState({ status: 'extracting', filename: file.name, progress: 'Extracting...' });

    let taskId: string;
    try {
      const result = await startExtraction('real_estate', docInfo.name);
      taskId = result.task_id;
    } catch (err) {
      setUploadState({ status: 'error', error: err instanceof Error ? err.message : 'Extraction failed' });
      return;
    }

    unsubRef.current = subscribeToTask(taskId, async (event: SSEEvent) => {
      if (event.type === 'step') {
        setUploadState(s => ({ ...s, progress: `${event.data.title}...` }));
      } else if (event.type === 'complete') {
        const extractionId = event.data.extraction_id;
        if (extractionId) {
          setUploadState({ status: 'linking', filename: file.name, progress: 'Linking to transaction...' });
          try {
            await linkExtraction(String(extractionId));
            setUploadState({ status: 'done', filename: file.name });
            setTimeout(() => setUploadState({ status: 'idle' }), 3000);
          } catch {
            setUploadState({ status: 'error', error: 'Failed to link extraction to transaction' });
          }
        } else {
          setUploadState({ status: 'done', filename: file.name });
          setTimeout(() => setUploadState({ status: 'idle' }), 3000);
        }
        unsubRef.current?.();
      } else if (event.type === 'error') {
        setUploadState({ status: 'error', error: event.data.message });
        unsubRef.current?.();
      }
    });
  };

  if (loading) return <div className="loading-state">Loading transaction...</div>;
  if (error) return <Alert color="red" mb="sm">{error}</Alert>;
  if (!transaction) return <Alert color="red" mb="sm">Transaction not found</Alert>;

  const activeParticipants = transaction.participants.filter(p => p.status !== 'removed');
  const addr = transaction.property_address;
  const isSeller = transaction.agent_side === 'seller';

  const visibleTabs: TabKey[] = isSeller
    ? ['overview', 'documents', 'offers']
    : ['overview', 'documents'];

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

  const TAB_LABELS: Record<TabKey, string> = {
    overview: 'Overview',
    documents: 'Documents',
    offers: 'Offers',
  };

  return (
    <div className="page-transaction-detail">
      <div className="txn-detail-header">
        <div>
          <Link to="/transactions" className="back-link">Back to Transactions</Link>
          <h1>{transaction.name}</h1>
          {addr && (
            <p className="txn-address">
              {addr.street_number} {addr.street_name}
              {addr.unit_number ? ` #${addr.unit_number}` : ''}, {addr.city}, {addr.state_or_province} {addr.postal_code}
            </p>
          )}
        </div>
        <div className="txn-header-actions">
          {transaction.agent_side && (
            <Badge color={transaction.agent_side === 'seller' ? 'blue' : 'teal'} variant="light">
              {transaction.agent_side === 'seller' ? 'Listing Side' : 'Buyer Side'}
            </Badge>
          )}
          <Badge color={STATUS_COLORS[transaction.status]} variant="light">
            {STATUS_LABELS[transaction.status]}
          </Badge>
          {nextStatus && (
            <Button size="sm" variant="filled" color="cyan" onClick={handleStatusAdvance}>
              Advance to {STATUS_LABELS[nextStatus]}
            </Button>
          )}
        </div>
      </div>

      {completion && (
        <div className="txn-completion-bar">
          <CompletionIndicator percentage={completion.overall} label="Transaction Readiness" size="md" />
        </div>
      )}

      {autoFillMsg && <Alert color="blue" mb="sm">{autoFillMsg}</Alert>}

      <div className="txn-lobby">
        {/* Main Content - Tabs */}
        <div className="txn-main">
          {/* Upload progress — persists across tab switches */}
          {uploadState.status !== 'idle' && (
            <Alert
              color={uploadState.status === 'error' ? 'red' : uploadState.status === 'done' ? 'green' : 'blue'}
              mb="sm"
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
                <span>
                  {uploadState.status === 'error' ? (
                    `Upload error: ${uploadState.error}`
                  ) : uploadState.status === 'done' ? (
                    `${uploadState.filename} extracted and linked.`
                  ) : (
                    `${uploadState.filename} - ${uploadState.progress}`
                  )}
                </span>
                {(uploadState.status === 'error' || uploadState.status === 'done') && (
                  <Button variant="subtle" size="sm" onClick={() => setUploadState({ status: 'idle' })}>
                    Dismiss
                  </Button>
                )}
              </div>
            </Alert>
          )}

          <Tabs value={activeTab} onChange={(val) => { if (val) setActiveTab(val as TabKey); }}>
            <Tabs.List mb="sm">
              {visibleTabs.map(tab => (
                <Tabs.Tab
                  key={tab}
                  value={tab}
                  rightSection={
                    tab === 'offers' && extractions.length > 0 ? <Badge size="xs">{extractions.length}</Badge> : undefined
                  }
                >
                  {TAB_LABELS[tab]}
                </Tabs.Tab>
              ))}
            </Tabs.List>

            <Tabs.Panel value="overview">
              <OverviewTab
                transaction={transaction}
                onUpdate={update}
                offersData={offersData}
                selectedOfferId={selectedOfferId}
                onSelectOffer={setSelectedOfferId}
              />
            </Tabs.Panel>
            <Tabs.Panel value="documents">
              <DocumentsTab
                txnId={id!}
                extractions={extractions}
                docs={docs}
                docsLoading={docsLoading}
                uploadBusy={uploadState.status !== 'idle'}
                onFileSelect={handleFileSelect}
              />
            </Tabs.Panel>
            <Tabs.Panel value="offers">
              {isSeller && (
                <OffersTab
                  txnId={id!}
                  extractions={extractions}
                  offersData={offersData}
                  txnDocs={docs}
                  onUnlink={unlinkExtraction}
                  onDocsRefresh={refreshDocs}
                  onNavigateToCompare={() =>
                    navigate(`/comparison?ids=${extractions.map(e => e.id).join(',')}`)
                  }
                />
              )}
            </Tabs.Panel>
          </Tabs>
        </div>

        {/* Participants Column */}
        <aside className="txn-sidebar">
          <div className="sidebar-section">
            <h3>Participants ({activeParticipants.length})</h3>
            {completion?.participants.map(p => (
              <Card key={p.user_id} padding="md" withBorder mb="xs">
                <Group justify="space-between" align="flex-start" mb={4}>
                  <h4 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>{p.name || p.email}</h4>
                  <Badge color={PARTICIPANT_STATUS_COLORS[p.status] ?? 'gray'} variant="light">{p.status}</Badge>
                </Group>
                <Stack gap={2} mb="xs" style={{ fontSize: 12, color: 'var(--mantine-color-dimmed)' }}>
                  <span>{(ROLE_LABELS as Record<string, string>)[p.role] || p.role}</span>
                  <span>{p.email}</span>
                </Stack>
                <CompletionIndicator percentage={p.profile_completion} label="Profile" size="sm" />
                {p.status !== 'removed' && (
                  <Button
                    variant="subtle"
                    size="sm"
                    color="red"
                    onClick={() => removeParticipantById(p.user_id)}
                  >
                    Remove
                  </Button>
                )}
              </Card>
            ))}
          </div>

          <div className="sidebar-section">
            <h3>Invite Participant</h3>
            <form onSubmit={handleInvite}>
              <Stack gap="sm">
                <TextInput
                  type="email"
                  placeholder="Email address"
                  value={inviteEmail}
                  onChange={e => setInviteEmail(e.target.value)}
                  required
                  size="sm"
                />
                <TextInput
                  placeholder="Name (optional)"
                  value={inviteName}
                  onChange={e => setInviteName(e.target.value)}
                  size="sm"
                />
                <Select
                  value={inviteRole}
                  onChange={(val) => { if (val) setInviteRole(val as ParticipantRole); }}
                  data={[
                    { value: 'BUYER', label: 'Buyer' },
                    { value: 'SELLER', label: 'Seller' },
                    { value: 'BUYING_AGENT', label: 'Buying Agent' },
                    { value: 'LISTING_AGENT', label: 'Listing Agent' },
                    { value: 'LOAN_OFFICER', label: 'Loan Officer' },
                    { value: 'ESCROW_TITLE_REP', label: 'Escrow/Title' },
                    { value: 'INSPECTOR', label: 'Inspector' },
                    { value: 'APPRAISER', label: 'Appraiser' },
                  ]}
                  size="sm"
                />
                <Button type="submit" size="sm" variant="filled" color="cyan" disabled={inviting}>
                  {inviting ? 'Sending...' : 'Send Invite'}
                </Button>
              </Stack>
            </form>
            {inviteResult && <p className="invite-result">{inviteResult}</p>}
          </div>

          <div className="sidebar-section">
            <Button variant="outline" color="cyan" onClick={handleAutoFill}>
              Auto-Fill from Profiles
            </Button>
          </div>
        </aside>
      </div>
    </div>
  );
}


/* ---- Tab Components ---- */

const DATE_FIELD_KEYS = [
  'offer_date',
  'closing_date',
  'contract_agreement_date',
  'offer_expiration_date',
  'inspection_date',
  'inspection_negotiation_deadline',
  'insurance_contingency_date',
  'loan_application_deadline',
  'seller_response_time',
  'possession_date',
];

function toICSDate(value: string): string | null {
  // Accept YYYY-MM-DD or MM/DD/YYYY
  let d: Date | null = null;
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    d = new Date(value + 'T00:00:00');
  } else if (/^\d{1,2}\/\d{1,2}\/\d{4}$/.test(value)) {
    const [m, day, y] = value.split('/');
    d = new Date(`${y}-${m.padStart(2, '0')}-${day.padStart(2, '0')}T00:00:00`);
  }
  if (!d || isNaN(d.getTime())) return null;
  return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`;
}

function exportDatesICS(offer: OfferData, dateFields: OfferField[], txnName: string) {
  const stamp = new Date().toISOString().replace(/[-:]/g, '').slice(0, 15) + 'Z';
  const events = dateFields
    .map(f => {
      const raw = String(offer.fields[f.key] ?? '').trim();
      const icsDate = raw ? toICSDate(raw) : null;
      if (!icsDate) return null;
      const uid = `${f.key}-${offer.extraction_id}@des`;
      return [
        'BEGIN:VEVENT',
        `UID:${uid}`,
        `DTSTAMP:${stamp}`,
        `DTSTART;VALUE=DATE:${icsDate}`,
        `DTEND;VALUE=DATE:${icsDate}`,
        `SUMMARY:${txnName} - ${f.label}`,
        'END:VEVENT',
      ].join('\r\n');
    })
    .filter(Boolean);

  const ics = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//DES//Deal Dates//EN',
    'CALSCALE:GREGORIAN',
    'METHOD:PUBLISH',
    ...events,
    'END:VCALENDAR',
  ].join('\r\n');

  const blob = new Blob([ics], { type: 'text/calendar' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `deal-dates-${txnName.replace(/\s+/g, '-')}.ics`;
  a.click();
  URL.revokeObjectURL(url);
}

function OverviewTab({
  transaction, onUpdate, offersData, selectedOfferId, onSelectOffer,
}: {
  transaction: NonNullable<ReturnType<typeof useTransactionDetail>['transaction']>;
  onUpdate: ReturnType<typeof useTransactionDetail>['update'];
  offersData: OffersComparisonResult | null;
  selectedOfferId: string | null;
  onSelectOffer: (id: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(transaction.name);
  const [price, setPrice] = useState(transaction.purchase_price?.toString() || '');
  const [earnest, setEarnest] = useState(transaction.earnest_money?.toString() || '');
  const [mls, setMls] = useState(transaction.mls_number || '');
  const [closingDate, setClosingDate] = useState(transaction.closing_date || '');
  const [txnType, setTxnType] = useState(transaction.transaction_type || '');
  const [streetNumber, setStreetNumber] = useState(transaction.property_address?.street_number || '');
  const [streetName, setStreetName] = useState(transaction.property_address?.street_name || '');
  const [unitNumber, setUnitNumber] = useState(transaction.property_address?.unit_number || '');
  const [city, setCity] = useState(transaction.property_address?.city || '');
  const [stateOrProvince, setStateOrProvince] = useState(transaction.property_address?.state_or_province || '');
  const [postalCode, setPostalCode] = useState(transaction.property_address?.postal_code || '');
  const [county, setCounty] = useState(transaction.property_address?.county || '');
  const [parcelTaxId, setParcelTaxId] = useState(transaction.property_address?.parcel_tax_id || '');
  const [saveError, setSaveError] = useState<string | null>(null);
  const { dotloopConnected } = useIntegrations();
  const [loops, setLoops] = useState<DotloopLoop[]>([]);
  const [selectedLoop, setSelectedLoop] = useState('');
  const [loopLinking, setLoopLinking] = useState(false);
  const [loopMsg, setLoopMsg] = useState<string | null>(null);
  const [loopSearching, setLoopSearching] = useState(false);
  const loopSearchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!dotloopConnected) return;
    fetchDotloopLoops()
      .then(setLoops)
      .catch(() => setLoops([]));
  }, [dotloopConnected]);

  useEffect(() => {
    if (editing) return;
    setName(transaction.name);
    setPrice(transaction.purchase_price?.toString() || '');
    setEarnest(transaction.earnest_money?.toString() || '');
    setMls(transaction.mls_number || '');
    setClosingDate(transaction.closing_date || '');
    setTxnType(transaction.transaction_type || '');
    setStreetNumber(transaction.property_address?.street_number || '');
    setStreetName(transaction.property_address?.street_name || '');
    setUnitNumber(transaction.property_address?.unit_number || '');
    setCity(transaction.property_address?.city || '');
    setStateOrProvince(transaction.property_address?.state_or_province || '');
    setPostalCode(transaction.property_address?.postal_code || '');
    setCounty(transaction.property_address?.county || '');
    setParcelTaxId(transaction.property_address?.parcel_tax_id || '');
    setSaveError(null);
  }, [transaction, editing]);

  const handleLoopSearch = (query: string) => {
    if (loopSearchTimer.current) clearTimeout(loopSearchTimer.current);
    if (!query.trim()) return;
    loopSearchTimer.current = setTimeout(async () => {
      setLoopSearching(true);
      try {
        const results = await searchDotloopLoops(query);
        setLoops(prev => {
          const merged = [...prev];
          for (const r of results) {
            if (!merged.some(l => l.id === r.id)) merged.push(r);
          }
          return merged;
        });
      } finally {
        setLoopSearching(false);
      }
    }, 350);
  };

  const handleSave = async () => {
    const hasAddressInput = [
      streetNumber,
      streetName,
      unitNumber,
      city,
      stateOrProvince,
      postalCode,
      county,
      parcelTaxId,
    ].some((value) => value.trim().length > 0);

    const propertyAddress = hasAddressInput
      ? {
        street_number: streetNumber.trim(),
        street_name: streetName.trim(),
        city: city.trim(),
        state_or_province: stateOrProvince.trim().toUpperCase(),
        postal_code: postalCode.trim(),
        ...(unitNumber.trim() ? { unit_number: unitNumber.trim() } : {}),
        ...(county.trim() ? { county: county.trim() } : {}),
        ...(parcelTaxId.trim() ? { parcel_tax_id: parcelTaxId.trim() } : {}),
      }
      : undefined;

    if (
      propertyAddress
      && (
        !propertyAddress.street_number
        || !propertyAddress.street_name
        || !propertyAddress.city
        || !propertyAddress.state_or_province
        || !propertyAddress.postal_code
      )
    ) {
      setSaveError('To save the property address, add street number, street name, city, state, and ZIP.');
      return;
    }

    setSaveError(null);

    try {
      await onUpdate({
        name: name || undefined,
        transaction_type: txnType || undefined,
        purchase_price: price ? parseFloat(price) : undefined,
        earnest_money: earnest ? parseFloat(earnest) : undefined,
        mls_number: mls || undefined,
        closing_date: closingDate || undefined,
        property_address: propertyAddress,
      });
      setEditing(false);
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : 'Failed to save transaction details.');
    }
  };

  const handleLinkLoop = async () => {
    if (!selectedLoop) return;
    setLoopLinking(true);
    try {
      await linkDotloopLoop(transaction._id, selectedLoop);
      setLoopMsg('Loop linked successfully');
      setTimeout(() => setLoopMsg(null), 3000);
    } catch {
      setLoopMsg('Failed to link loop');
    }
    setLoopLinking(false);
  };

  const selectedOffer: OfferData | null =
    offersData?.offers.find(o => o.extraction_id === selectedOfferId) ?? null;

  const dateFields: OfferField[] = offersData
    ? offersData.field_definitions.filter(f => DATE_FIELD_KEYS.includes(f.key))
    : [];

  function offerVal(key: string): string | number | boolean | null | undefined {
    return selectedOffer?.fields[key];
  }

  return (
    <div className="overview-tab">
      <div className="overview-section">
        {offersData && offersData.offers.length > 0 && (
          <div className="offer-selector">
            {offersData.offers.map(offer => {
              const conf = typeof offer.fields['overall_confidence'] === 'number'
                ? offer.fields['overall_confidence'] as number
                : null;
              const isActive = offer.extraction_id === selectedOfferId;
              const buyerName = typeof offer.fields['buyer_name'] === 'string' ? offer.fields['buyer_name'] : null;
              const pillLabel = buyerName
                ? buyerName.split(/[,\s]+/).filter(Boolean).map(part => part.split(/\s+/).pop() ?? part).join(' ').slice(0, 24)
                : offer.filename.replace(/\.[^.]+$/, '').slice(0, 22);
              return (
                <button
                  key={offer.extraction_id}
                  className={`offer-pill${isActive ? ' active' : ''}`}
                  onClick={() => onSelectOffer(offer.extraction_id)}
                  title={offer.filename}
                >
                  <span className="offer-pill-name">
                    {pillLabel}
                  </span>
                  {conf !== null && (
                    <Badge
                      variant="light"
                      color={conf >= 0.85 ? 'green' : conf >= 0.65 ? 'yellow' : 'red'}
                      size="xs"
                    >
                      {(conf * 100).toFixed(0)}%
                    </Badge>
                  )}
                </button>
              );
            })}
          </div>
        )}

        <div className="section-header">
          <h3>Deal Information</h3>
          <Button variant="subtle" onClick={() => setEditing(!editing)}>
            {editing ? 'Cancel' : 'Edit'}
          </Button>
        </div>

        {editing ? (
          <>
            <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm" mb="sm">
              <TextInput
                label="Transaction Name"
                value={name}
                onChange={e => setName(e.target.value)}
                size="sm"
              />
              <NumberInput
                label="Purchase Price"
                value={price ? Number(price) : ''}
                onChange={(val) => setPrice(val === '' ? '' : String(val))}
                placeholder="0"
                size="sm"
              />
              <NumberInput
                label="Earnest Money"
                value={earnest ? Number(earnest) : ''}
                onChange={(val) => setEarnest(val === '' ? '' : String(val))}
                placeholder="0"
                size="sm"
              />
              <TextInput
                label="MLS Number"
                value={mls}
                onChange={e => setMls(e.target.value)}
                placeholder="e.g. MLS-12345"
                size="sm"
              />
              <TextInput
                label="Transaction Type"
                value={txnType}
                onChange={e => setTxnType(e.target.value)}
                placeholder="e.g. Residential"
                size="sm"
              />
              <TextInput
                label="Closing Date"
                value={closingDate}
                onChange={e => setClosingDate(e.target.value)}
                placeholder="YYYY-MM-DD"
                size="sm"
              />
            </SimpleGrid>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Property Address</div>
            <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm" mb="xs">
              <TextInput
                label="Street Number"
                value={streetNumber}
                onChange={e => setStreetNumber(e.target.value)}
                placeholder="2760"
                size="sm"
              />
              <TextInput
                label="Street Name"
                value={streetName}
                onChange={e => setStreetName(e.target.value)}
                placeholder="Carla Jo Lane"
                size="sm"
              />
              <TextInput
                label="Unit Number"
                value={unitNumber}
                onChange={e => setUnitNumber(e.target.value)}
                placeholder="Optional"
                size="sm"
              />
              <TextInput
                label="City"
                value={city}
                onChange={e => setCity(e.target.value)}
                placeholder="Missoula"
                size="sm"
              />
              <TextInput
                label="State"
                value={stateOrProvince}
                onChange={e => setStateOrProvince(e.target.value)}
                placeholder="MT"
                size="sm"
              />
              <TextInput
                label="ZIP"
                value={postalCode}
                onChange={e => setPostalCode(e.target.value)}
                placeholder="59801"
                size="sm"
              />
              <TextInput
                label="County"
                value={county}
                onChange={e => setCounty(e.target.value)}
                placeholder="Optional"
                size="sm"
              />
              <TextInput
                label="Parcel / Tax ID"
                value={parcelTaxId}
                onChange={e => setParcelTaxId(e.target.value)}
                placeholder="Optional"
                size="sm"
              />
            </SimpleGrid>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 12 }}>
              Add a complete property address so the deal record stays consistent.
            </div>
            {saveError && (
              <Alert color="red" mb="sm">
                {saveError}
              </Alert>
            )}
            <Group mb="sm">
              <Button variant="filled" color="cyan" onClick={handleSave}>Save</Button>
            </Group>
          </>
        ) : (
          <div className="overview-grid">
            <div className="overview-item">
              <span className="overview-label">Name</span>
              <span className="overview-value">{transaction.name}</span>
            </div>
            <div className="overview-item">
              <span className="overview-label">Type</span>
              <span className="overview-value">{transaction.transaction_type}</span>
            </div>
            <div className="overview-item">
              <span className="overview-label">Side</span>
              <span className="overview-value">
                {transaction.agent_side === 'seller' ? 'Listing (Seller)' : transaction.agent_side === 'buyer' ? 'Buyer' : '--'}
              </span>
            </div>
            <div className="overview-item">
              <span className="overview-label">Purchase Price</span>
              <span className="overview-value">
                {selectedOffer
                  ? (offerVal('purchase_price') != null ? formatPrice(Number(offerVal('purchase_price'))) : '--')
                  : formatPrice(transaction.purchase_price)}
              </span>
            </div>
            <div className="overview-item">
              <span className="overview-label">Earnest Money</span>
              <span className="overview-value">
                {selectedOffer
                  ? (offerVal('earnest_money_amount') != null ? formatPrice(Number(offerVal('earnest_money_amount'))) : '--')
                  : formatPrice(transaction.earnest_money)}
              </span>
            </div>
            {selectedOffer && (
              <>
                <div className="overview-item">
                  <span className="overview-label">Financing Type</span>
                  <span className="overview-value">{String(offerVal('financing_type') ?? '--')}</span>
                </div>
                <div className="overview-item">
                  <span className="overview-label">Down Payment</span>
                  <span className="overview-value">
                    {offerVal('down_payment_amount') != null
                      ? formatPrice(Number(offerVal('down_payment_amount')))
                      : offerVal('down_payment_percentage') != null
                        ? String(offerVal('down_payment_percentage'))
                        : '--'}
                  </span>
                </div>
                <div className="overview-item">
                  <span className="overview-label">Buyer</span>
                  <span className="overview-value">{String(offerVal('buyer_name') ?? '--')}</span>
                </div>
                <div className="overview-item">
                  <span className="overview-label">Agent</span>
                  <span className="overview-value">{String(offerVal('agent_name') ?? '--')}</span>
                </div>
              </>
            )}
            <div className="overview-item">
              <span className="overview-label">MLS #</span>
              <span className="overview-value">{transaction.mls_number || '--'}</span>
            </div>
            <div className="overview-item">
              <span className="overview-label">Closing Date</span>
              <span className="overview-value">
                {selectedOffer
                  ? formatDate(String(offerVal('closing_date') ?? ''))
                  : formatDate(transaction.closing_date)}
              </span>
            </div>
            <div className="overview-item">
              <span className="overview-label">Created</span>
              <span className="overview-value">{formatDate(transaction.created_at)}</span>
            </div>
          </div>
        )}
      </div>

      {selectedOffer && dateFields.length > 0 && (
        <div className="overview-section">
          <div className="section-header">
            <h3>Deal Dates</h3>
            <Button
              variant="subtle"
              size="xs"
              onClick={() => exportDatesICS(selectedOffer, dateFields, transaction.name)}
            >
              Export to Calendar
            </Button>
          </div>
          <div className="deal-dates-list">
            {dateFields.map(field => (
              <div key={field.key} className="deal-date-row">
                <span className="date-label">{field.label}</span>
                <span className="date-value">
                  {selectedOffer.fields[field.key] != null
                    ? formatDate(String(selectedOffer.fields[field.key]))
                    : '--'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <RawExtrasPanel offer={selectedOffer} />

      <div className="overview-section">
        <h3>Property</h3>
        <div className="overview-grid">
          <div className="overview-item">
            <span className="overview-label">Address</span>
            <span className="overview-value">
              {[transaction.property_address?.street_number, transaction.property_address?.street_name]
                .filter(Boolean)
                .join(' ') || '--'}
            </span>
          </div>
          <div className="overview-item">
            <span className="overview-label">Unit</span>
            <span className="overview-value">{transaction.property_address?.unit_number || '--'}</span>
          </div>
          <div className="overview-item">
            <span className="overview-label">City</span>
            <span className="overview-value">{transaction.property_address?.city || '--'}</span>
          </div>
          <div className="overview-item">
            <span className="overview-label">State</span>
            <span className="overview-value">{transaction.property_address?.state_or_province || '--'}</span>
          </div>
          <div className="overview-item">
            <span className="overview-label">ZIP</span>
            <span className="overview-value">{transaction.property_address?.postal_code || '--'}</span>
          </div>
          <div className="overview-item">
            <span className="overview-label">County</span>
            <span className="overview-value">{transaction.property_address?.county || '--'}</span>
          </div>
          <div className="overview-item">
            <span className="overview-label">Parcel / Tax ID</span>
            <span className="overview-value">{transaction.property_address?.parcel_tax_id || '--'}</span>
          </div>
        </div>
      </div>

      <div className="overview-section">
        <h3>Dotloop Loop</h3>
        {transaction.dotloop_loop_id ? (
          <div className="dotloop-linked">
            <span className="dotloop-loop-id">Loop ID: {transaction.dotloop_loop_id}</span>
            {loops.find(l => String(l.id) === transaction.dotloop_loop_id) && (
              <span className="dotloop-loop-name">
                {loops.find(l => String(l.id) === transaction.dotloop_loop_id)?.name}
              </span>
            )}
          </div>
        ) : dotloopConnected ? (
          <Group gap="sm" align="flex-end">
            <Select
              value={selectedLoop || null}
              onChange={(val) => setSelectedLoop(val ?? '')}
              data={loops.map(l => ({ value: String(l.id), label: `${l.name}${l.status ? ` - ${l.status}` : ''}` }))}
              placeholder="Search loops..."
              size="sm"
              style={{ flex: 1 }}
              searchable
              onSearchChange={handleLoopSearch}
              rightSection={loopSearching ? <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>...</span> : undefined}
              nothingFoundMessage="No loops found"
            />
            <Button
              size="sm"
              variant="outline"
              color="cyan"
              onClick={handleLinkLoop}
              disabled={!selectedLoop || loopLinking}
            >
              {loopLinking ? 'Linking...' : 'Link Loop'}
            </Button>
          </Group>
        ) : (
          <p className="text-muted">
            <Link to="/profile">Connect Dotloop</Link> to link a loop to this transaction.
          </p>
        )}
        {loopMsg && <p className="invite-result">{loopMsg}</p>}
      </div>
    </div>
  );
}


function formatRawKey(key: string): string {
  return key
    .split('.')
    .map(part => part.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()))
    .join(' > ');
}

function RawExtrasPanel({ offer }: { offer: import('../api').OfferData | null }) {
  const [open, setOpen] = useState(false);
  if (!offer) return null;
  const entries = Object.entries(offer.raw_extras ?? {});
  if (entries.length === 0) return null;

  return (
    <div className="overview-section raw-extras-section">
      <button className="raw-extras-toggle" onClick={() => setOpen(o => !o)}>
        <span>{open ? 'v' : '>'} All extracted data</span>
        <span className="raw-extras-count">{entries.length} additional field{entries.length !== 1 ? 's' : ''}</span>
      </button>
      {open && (
        <div className="deal-dates-list raw-extras-list">
          {entries.map(([key, val]) => (
            <div key={key} className="deal-date-row">
              <span className="date-label">{formatRawKey(key)}</span>
              <span className="date-value raw-extras-value">
                {val === null || val === undefined ? '--' : String(val)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}


function DocumentsTab({
  txnId: _txnId,
  extractions,
  docs,
  docsLoading,
  uploadBusy,
  onFileSelect,
}: {
  txnId: string;
  extractions: ReturnType<typeof useTransactionDetail>['extractions'];
  docs: TransactionDocRecord[];
  docsLoading: boolean;
  uploadBusy: boolean;
  onFileSelect: (e: React.ChangeEvent<HTMLInputElement>) => void;
}) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  return (
    <div className="documents-tab">
      {/* Upload action bar */}
      <div className="doc-action-bar">
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf"
          style={{ display: 'none' }}
          onChange={onFileSelect}
        />
        <Button
          size="sm"
          variant="filled"
          color="cyan"
          disabled={uploadBusy}
          onClick={() => fileInputRef.current?.click()}
        >
          Upload & Extract Document
        </Button>
      </div>

      {/* Extracted documents linked to this transaction */}
      {extractions.length > 0 && (
        <div className="doc-requirements-section">
          <h3>Extracted Documents ({extractions.length})</h3>
          <div className="doc-requirements-list">
            {extractions.map(ext => (
              <div key={ext.id} className="doc-requirement satisfied">
                <span className="doc-req-icon">OK</span>
                <span className="doc-req-type">{ext.filename}</span>
                <span className="doc-req-role">{ext.mode}</span>
                <span className="doc-req-status status-ok">
                  {Math.round(ext.overall_confidence * 100)}% confidence
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Linked profile documents */}
      {docsLoading ? (
        <div className="loading-state">Loading documents...</div>
      ) : docs.length > 0 ? (
        <div className="doc-requirements-section">
          <h3>Linked Documents ({docs.length})</h3>
          <div className="doc-requirements-list">
            {docs.map(doc => (
              <div key={doc._id} className="doc-requirement satisfied">
                <span className="doc-req-icon">OK</span>
                <span className="doc-req-type">{doc.filename}</span>
                <span className="doc-req-role">{doc.doc_type.replace(/_/g, ' ')}</span>
                <span className="doc-req-status status-ok">{doc.source === 'user_profile' ? 'From Profile' : 'Uploaded'}</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}

    </div>
  );
}



interface ExtractionSummary {
  id: string;
  filename: string;
  mode: string;
  overall_confidence: number;
  pages_processed: number;
  created_at: string | null;
}

function OffersTab({
  txnId,
  extractions,
  offersData,
  txnDocs,
  onUnlink,
  onDocsRefresh,
  onNavigateToCompare,
}: {
  txnId: string;
  extractions: ExtractionSummary[];
  offersData: OffersComparisonResult | null;
  txnDocs: TransactionDocRecord[];
  onUnlink: (id: string) => Promise<void>;
  onDocsRefresh: () => void;
  onNavigateToCompare: () => void;
}) {
  const [unlinking, setUnlinking] = useState<string | null>(null);
  const [modalOfferId, setModalOfferId] = useState<string | null>(null);
  const modalOffer = offersData?.offers.find(o => o.extraction_id === modalOfferId) ?? null;

  const handleUnlink = async (id: string) => {
    setUnlinking(id);
    try {
      await onUnlink(id);
    } finally {
      setUnlinking(null);
    }
  };

  if (extractions.length === 0) {
    return (
      <div className="extractions-tab-empty">
        <p>No offers linked yet.</p>
        <p>Upload offer documents from the Documents tab to add them here.</p>
      </div>
    );
  }

  return (
    <div className="extractions-tab">
      <div className="extractions-tab-header">
        <span>{extractions.length} offer{extractions.length !== 1 ? 's' : ''} received</span>
        {extractions.length >= 2 && (
          <Button size="sm" variant="filled" color="cyan" onClick={onNavigateToCompare}>
            Compare All Offers
          </Button>
        )}
      </div>
      <div className="extractions-grid">
        {extractions.map(ext => {
          const offerFields = offersData?.offers.find(o => o.extraction_id === ext.id)?.fields ?? {};
          const reqs = evaluateOfferRequirements(offerFields, txnDocs, ext.id);
          const pendingCount = reqs.filter(r => !r.satisfied).length;
          return (
          <div
            key={ext.id}
            className="extraction-card"
            style={{ cursor: 'pointer' }}
            onClick={() => setModalOfferId(ext.id)}
          >
            <div className="extraction-card-header">
              <span className="extraction-card-filename">{ext.filename}</span>
              <Badge
                variant="light"
                color={ext.overall_confidence >= 0.85 ? 'green' : ext.overall_confidence >= 0.65 ? 'yellow' : 'red'}
              >
                {(ext.overall_confidence * 100).toFixed(0)}%
              </Badge>
            </div>
            <div className="extraction-card-meta">
              <span>{ext.pages_processed} page{ext.pages_processed !== 1 ? 's' : ''}</span>
              {ext.created_at && (
                <span>{formatDate(ext.created_at)}</span>
              )}
            </div>
            {reqs.length > 0 && (
              <div className="extraction-card-requirements">
                {pendingCount > 0 ? (
                  <Badge variant="light" color="orange" size="sm">
                    {pendingCount} doc{pendingCount !== 1 ? 's' : ''} pending
                  </Badge>
                ) : (
                  <Badge variant="light" color="green" size="sm">
                    All docs received
                  </Badge>
                )}
              </div>
            )}
            <Button
              variant="subtle"
              size="sm"
              color="red"
              disabled={unlinking === ext.id}
              onClick={(e) => { e.stopPropagation(); handleUnlink(ext.id); }}
            >
              {unlinking === ext.id ? 'Removing...' : 'Remove Offer'}
            </Button>
          </div>
          );
        })}
      </div>
      <OfferRequirementsModal
        opened={modalOfferId !== null}
        onClose={() => setModalOfferId(null)}
        offer={modalOffer}
        txnId={txnId}
        txnDocs={txnDocs}
        onDocsRefresh={onDocsRefresh}
      />
    </div>
  );
}
