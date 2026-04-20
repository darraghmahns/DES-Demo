/** N-way offer comparison table for Julie Gardner Properties. */

import { useState, useEffect, useRef, useCallback } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Group } from '@mantine/core';
import { fetchExtractions, fetchOffersComparison, deleteExtraction, updateOfferFields } from '../api';
import type { ExtractionSummary, OffersComparisonResult, OfferField, VerificationCitation } from '../api';
import { fetchOfferWorkspace, listTransactions, getOfferSummary, generateOfferSummary } from '../api/transactions';
import type { OfferSummaryResponse } from '../api/transactions';
import type { Transaction } from '../types/transaction';
import { ComparisonCellCitation } from '../components/offers/ComparisonCellCitation';

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

function formatValue(value: string | number | boolean | null, type: OfferField['type']): string {
  if (value === null || value === undefined) return '\u2014';
  if (type === 'currency' && typeof value === 'number') {
    return `$${value.toLocaleString()}`;
  }
  if (type === 'boolean') {
    return value ? 'Yes' : 'No';
  }
  return String(value);
}

function formatDate(iso: string | null): string {
  if (!iso) return '';
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
  });
}

// ---------------------------------------------------------------------------
// Highlight logic
// ---------------------------------------------------------------------------

function getPriceClass(
  value: number | null,
  allValues: Array<number | null>,
): string {
  const nums = allValues.filter((v): v is number => v !== null);
  if (nums.length < 2 || value === null) return '';
  const min = Math.min(...nums);
  const max = Math.max(...nums);
  if (value === max) return 'offer-cell-high';
  if (value === min) return 'offer-cell-low';
  return '';
}

function getDateClass(
  value: string | null,
  allValues: Array<string | null>,
): string {
  const dates = allValues.filter((v): v is string => v !== null);
  if (dates.length < 2 || value === null) return '';
  const sorted = [...dates].sort();
  if (value === sorted[0]) return 'offer-cell-earliest';
  if (value === sorted[sorted.length - 1]) return 'offer-cell-latest';
  return '';
}

// ---------------------------------------------------------------------------
// ComparisonTable — editable cells with auto-save
// ---------------------------------------------------------------------------

type FieldValue = string | number | boolean | null;
type LocalEdits = Map<string, Record<string, string>>;
type ComparisonExtractionOption = Pick<
  ExtractionSummary,
  | 'id'
  | 'document_id'
  | 'filename'
  | 'overall_confidence'
  | 'pages_processed'
  | 'created_at'
  | 'document_title'
  | 'document_type'
  | 'document_revision'
> & { buyer_name?: string | null };

function parseFieldValue(raw: string, type: OfferField['type']): FieldValue {
  if (raw === '') return null;
  if (type === 'currency') return isNaN(Number(raw)) ? raw : Number(raw);
  return raw;
}

interface EditableCellProps {
  value: FieldValue;
  field: OfferField;
  extractionId: string;
  allValues: FieldValue[];
  citations: VerificationCitation[];
  citationState: 'supported' | 'not_found' | 'not_captured';
  isStale: boolean;
  onSave: (extractionId: string, key: string, value: FieldValue) => void;
}

// Boolean fields that indicate a negative/risk when true (from seller's perspective)
const WARN_WHEN_TRUE = new Set(['opd_delivered']);

function EditableCell({
  value,
  field,
  extractionId,
  allValues,
  citations,
  citationState,
  isStale,
  onSave,
}: EditableCellProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');
  const [saved, setSaved] = useState(false);
  const [textFocused, setTextFocused] = useState(false);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  let cellClass = '';
  if (field.key === 'purchase_price') {
    cellClass = getPriceClass(
      typeof value === 'number' ? value : null,
      allValues.map(v => (typeof v === 'number' ? v : null)),
    );
  } else if (field.type === 'date') {
    cellClass = getDateClass(
      typeof value === 'string' ? value : null,
      allValues.map(v => (typeof v === 'string' ? v : null)),
    );
  } else if (field.type === 'boolean' && WARN_WHEN_TRUE.has(field.key) && value === true) {
    cellClass = 'offer-cell-warn';
  }

  const triggerSave = (rawDraft: string) => {
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      const parsed = parseFieldValue(rawDraft, field.type);
      onSave(extractionId, field.key, parsed);
      setSaved(true);
      setTimeout(() => setSaved(false), 1500);
    }, 400);
  };

  // Boolean: click to cycle null→true→false→null
  if (field.type === 'boolean') {
    const next = value === null ? true : value === true ? false : null;
    return (
      <ComparisonCellCitation
        fieldLabel={field.label}
        value={value}
        citations={citations}
        state={citationState}
        stale={isStale}
      >
        <td
          className={`comparison-cell comparison-cell-bool ${cellClass}`}
          onClick={() => { onSave(extractionId, field.key, next); setSaved(true); setTimeout(() => setSaved(false), 1500); }}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              onSave(extractionId, field.key, next);
              setSaved(true);
              setTimeout(() => setSaved(false), 1500);
            }
          }}
        >
          <span className="comparison-cell-value">{formatValue(value, field.type)}</span>
          {saved && <span className="comparison-cell-saved">Saved</span>}
        </td>
      </ComparisonCellCitation>
    );
  }

  // Text (notes, inclusions etc.): always-on textarea
  if (field.type === 'text') {
    return (
      <ComparisonCellCitation
        fieldLabel={field.label}
        value={value}
        citations={citations}
        state={citationState}
        stale={isStale}
        disabled={textFocused}
      >
        <td className={`comparison-cell comparison-cell-text ${cellClass}`}>
          <textarea
            className="comparison-cell-textarea"
            defaultValue={value != null ? String(value) : ''}
            onChange={e => triggerSave(e.target.value)}
            onFocus={() => setTextFocused(true)}
            onBlur={() => setTextFocused(false)}
            rows={3}
            placeholder="--"
          />
          {saved && <span className="comparison-cell-saved">Saved</span>}
        </td>
      </ComparisonCellCitation>
    );
  }

  // Currency: click-to-edit number input (single-line)
  if (editing && field.type === 'currency') {
    return (
      <td className={`comparison-cell comparison-cell-editing ${cellClass}`}>
        <input
          className="comparison-cell-input"
          autoFocus
          type="number"
          defaultValue={value != null ? String(value) : ''}
          onChange={e => { setDraft(e.target.value); triggerSave(e.target.value); }}
          onBlur={() => { triggerSave(draft || (value != null ? String(value) : '')); setEditing(false); }}
          onKeyDown={e => { if (e.key === 'Enter' || e.key === 'Escape') { (e.target as HTMLInputElement).blur(); } }}
        />
      </td>
    );
  }

  // String/date: click-to-edit wrapping textarea
  if (editing) {
    return (
      <td className={`comparison-cell comparison-cell-editing ${cellClass}`}>
        <textarea
          className="comparison-cell-input comparison-cell-input-wrap"
          autoFocus
          defaultValue={value != null ? String(value) : ''}
          onChange={e => { setDraft(e.target.value); triggerSave(e.target.value); }}
          onBlur={() => { triggerSave(draft || (value != null ? String(value) : '')); setEditing(false); }}
          onKeyDown={e => { if (e.key === 'Escape') { (e.target as HTMLTextAreaElement).blur(); } }}
          rows={2}
        />
      </td>
    );
  }

  return (
    <ComparisonCellCitation
      fieldLabel={field.label}
      value={value}
      citations={citations}
      state={citationState}
      stale={isStale}
    >
      <td
        className={`comparison-cell comparison-cell-clickable ${cellClass}`}
        onClick={() => { setDraft(value != null ? String(value) : ''); setEditing(true); }}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            setDraft(value != null ? String(value) : '');
            setEditing(true);
          }
        }}
      >
        <span className="comparison-cell-value">{formatValue(value, field.type)}</span>
        {saved && <span className="comparison-cell-saved">Saved</span>}
      </td>
    </ComparisonCellCitation>
  );
}

interface ComparisonTableProps {
  result: OffersComparisonResult;
  localEdits: LocalEdits;
  highlightedRow: number | null;
  onRowHover: (idx: number | null) => void;
  onRemoveOffer: (extractionId: string) => void;
  onFieldSave: (extractionId: string, key: string, value: FieldValue) => void;
}

function ComparisonTable({ result, localEdits, highlightedRow, onRowHover, onRemoveOffer, onFieldSave }: ComparisonTableProps) {
  const { offers, field_definitions } = result;
  const [hideEmpty, setHideEmpty] = useState(true);

  const visibleFields = hideEmpty
    ? field_definitions.filter(f => f.key === 'notes' || offers.some(o => {
        const local = localEdits.get(o.extraction_id)?.[f.key];
        return local !== undefined ? local !== '' : o.fields[f.key] != null;
      }))
    : field_definitions;

  let lastGroup = '';

  return (
    <div>
      <div className="comparison-table-toolbar">
        <button
          className="btn-link btn-sm"
          onClick={() => setHideEmpty(prev => !prev)}
        >
          {hideEmpty ? 'Show empty fields' : 'Hide empty fields'}
        </button>
        <span className="comparison-table-hint">Click any cell to edit - changes auto-save</span>
      </div>
      <div className="comparison-table-wrapper comparison-table-sticky">
        <table className="comparison-table">
          <thead>
            <tr>
              <th className="comparison-field-col comparison-sticky-col">Field</th>
              {offers.map((offer) => {
                const buyerName = localEdits.get(offer.extraction_id)?.['buyer_name'] ?? offer.fields['buyer_name'];
                const displayName = buyerName ? String(buyerName) : offer.filename;
                return (
                  <th key={offer.extraction_id} className="comparison-offer-col" title={offer.filename}>
                    <div className="comparison-offer-name">{displayName}</div>
                    <button
                      className="btn-link btn-sm comparison-remove-offer"
                      onClick={() => onRemoveOffer(offer.extraction_id)}
                      title="Remove from comparison"
                    >
                      &times; Remove
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {visibleFields.flatMap((field, rowIdx) => {
              const rows = [];

              if (field.group && field.group !== lastGroup) {
                lastGroup = field.group;
                rows.push(
                  <tr key={`grp-${field.group}`} className="comparison-group-row">
                    <td colSpan={offers.length + 1}>{field.group}</td>
                  </tr>
                );
              }

              rows.push(
                <tr
                  key={field.key}
                  className={highlightedRow === rowIdx ? 'comparison-row-highlight' : ''}
                  onMouseEnter={() => onRowHover(rowIdx)}
                  onMouseLeave={() => onRowHover(null)}
                >
                  <td className="comparison-field-label comparison-sticky-col">{field.label}</td>
                  {offers.map((offer) => {
                    const localVal = localEdits.get(offer.extraction_id)?.[field.key];
                    const rawValue: FieldValue = localVal !== undefined
                      ? parseFieldValue(localVal, field.type)
                      : (offer.fields[field.key] ?? null);
                    const hasLocalEdit = localVal !== undefined;
                    const citationMeta = offer.field_citation_meta?.[field.key] ?? { state: 'not_captured' as const, stale: false };
                    const allValues = offers.map(o => {
                      const lv = localEdits.get(o.extraction_id)?.[field.key];
                      return lv !== undefined ? parseFieldValue(lv, field.type) : (o.fields[field.key] ?? null);
                    });
                    return (
                      <EditableCell
                        key={offer.extraction_id}
                        value={rawValue}
                        field={field}
                        extractionId={offer.extraction_id}
                        allValues={allValues}
                        citations={offer.field_citations?.[field.key] ?? []}
                        citationState={citationMeta.state}
                        isStale={citationMeta.stale || hasLocalEdit}
                        onSave={onFieldSave}
                      />
                    );
                  })}
                </tr>
              );

              return rows;
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// OfferComparison page
// ---------------------------------------------------------------------------

export function OfferComparison() {
  const [searchParams] = useSearchParams();
  const preloadTxnId = searchParams.get('txn');
  const preloadIdsParam = searchParams.get('ids') ?? '';
  // IDs passed from the Offers tab — if present, filter and pre-select only those
  const preloadIds = preloadIdsParam
    ? new Set(preloadIdsParam.split(',').filter(Boolean))
    : null;

  const [extractions, setExtractions] = useState<ComparisonExtractionOption[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [result, setResult] = useState<OffersComparisonResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadingExtractions, setLoadingExtractions] = useState(true);
  const [highlightedRow, setHighlightedRow] = useState<number | null>(null);
  const [localEdits, setLocalEdits] = useState<LocalEdits>(new Map());
  // Map of plain doc_id -> transaction
  const [txnByDocId, setTxnByDocId] = useState<Map<string, Transaction>>(new Map());
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [filterTxnId, setFilterTxnId] = useState<string>('');
  const [deleting, setDeleting] = useState<Set<string>>(new Set());

  const [summary, setSummary] = useState<OfferSummaryResponse | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [comparedIds, setComparedIds] = useState<string[] | null>(null);
  const summaryPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopSummaryPoll = useCallback(() => {
    if (summaryPollRef.current) {
      clearInterval(summaryPollRef.current);
      summaryPollRef.current = null;
    }
  }, []);

  const pollSummary = useCallback(async (txnId: string, ids: string[]) => {
    try {
      const data = await getOfferSummary(txnId, ids);
      setSummary(data);
      if (data.status !== 'generating') {
        stopSummaryPoll();
      }
    } catch {
      setSummaryError('Could not load offer summary');
      stopSummaryPoll();
    }
  }, [stopSummaryPoll]);

  const startSummaryPoll = useCallback((txnId: string, ids: string[]) => {
    stopSummaryPoll();
    summaryPollRef.current = setInterval(() => {
      pollSummary(txnId, ids);
    }, 4000);
  }, [pollSummary, stopSummaryPoll]);

  useEffect(() => stopSummaryPoll, [stopSummaryPoll]);

  const handleRefreshSummary = useCallback(async () => {
    if (!preloadTxnId || !comparedIds || comparedIds.length < 2) return;
    setSummary({ status: 'generating', summary: null, generated_at: null });
    setSummaryError(null);
    try {
      await generateOfferSummary(preloadTxnId, comparedIds, true);
      startSummaryPoll(preloadTxnId, comparedIds);
    } catch {
      setSummary({ status: 'error', summary: null, generated_at: null });
    }
  }, [preloadTxnId, comparedIds, startSummaryPoll]);

  const handleFieldSave = useCallback(async (
    extractionId: string,
    key: string,
    value: string | number | boolean | null,
  ) => {
    setLocalEdits(prev => {
      const next = new Map(prev);
      const offerEdits = { ...(next.get(extractionId) ?? {}) };
      offerEdits[key] = value != null ? String(value) : '';
      next.set(extractionId, offerEdits);
      return next;
    });
    try {
      await updateOfferFields(extractionId, { [key]: value });
    } catch {
      // Non-critical — value is still reflected locally; user can retry
    }
  }, []);

  useEffect(() => {
    setLoadingExtractions(true);
    setError(null);
    const extractionRequest = preloadTxnId
      ? fetchOfferWorkspace(preloadTxnId).then((workspace) =>
          workspace.offers.map((offer) => ({
            id: offer.extraction_id,
            document_id: offer.document_id,
            filename: offer.summary.filename,
            overall_confidence: offer.summary.overall_confidence,
            pages_processed: offer.summary.pages_processed,
            created_at: offer.summary.created_at,
            document_title: offer.summary.document_title,
            document_type: offer.summary.document_type,
            document_revision: offer.summary.document_revision,
            buyer_name: offer.summary.buyer_name,
          })),
        )
      : fetchExtractions('real_estate').then((items) =>
          items.map((item) => ({
            id: item.id,
            document_id: item.document_id,
            filename: item.filename,
            overall_confidence: item.overall_confidence,
            pages_processed: item.pages_processed,
            created_at: item.created_at,
            document_title: item.document_title,
            document_type: item.document_type,
            document_revision: item.document_revision,
          })),
        );

    Promise.all([
      extractionRequest,
      listTransactions(),
    ]).then(([all, txns]) => {
      // Build doc_id -> transaction lookup
      const map = new Map<string, Transaction>();
      for (const txn of txns) {
        for (const docId of (txn.extraction_ids ?? [])) {
          map.set(docId, txn);
        }
      }
      setTxnByDocId(map);
      setTransactions(txns);

      // preloadIds are plain document ids for transaction-scoped compare;
      // global list_extractions returns composite "doc_id:idx" as `id` but plain doc_id as `document_id`
      const visible = preloadIds
        ? all.filter(e => preloadIds.has(e.id) || preloadIds.has(e.document_id))
        : all;
      setExtractions(visible);
      if (preloadIds) {
        setSelectedIds(new Set(visible.map(e => e.id)));
      } else {
        setSelectedIds(new Set());
      }
    })
      .catch(() => setError('Failed to load extractions'))
      .finally(() => setLoadingExtractions(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preloadIdsParam, preloadTxnId]);

  // Extractions visible in the selector after applying the transaction filter
  const visibleExtractions = filterTxnId
    ? extractions.filter(e => txnByDocId.get(e.document_id)?._id === filterTxnId)
    : extractions;

  // Transactions that have at least one extraction — for the filter dropdown
  const txnsWithExtractions = transactions.filter(t =>
    extractions.some(e => txnByDocId.get(e.document_id)?._id === t._id)
  );

  function toggleId(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    setResult(null);
    setComparedIds(null);
    setSummary(null);
    stopSummaryPoll();
  }

  function toggleAll() {
    const allVisibleSelected = visibleExtractions.every(e => selectedIds.has(e.id));
    if (allVisibleSelected) {
      setSelectedIds(prev => {
        const next = new Set(prev);
        visibleExtractions.forEach(e => next.delete(e.id));
        return next;
      });
    } else {
      setSelectedIds(prev => new Set([...prev, ...visibleExtractions.map(e => e.id)]));
    }
    setResult(null);
    setComparedIds(null);
    setSummary(null);
    stopSummaryPoll();
  }

  async function handleDelete(ext: ComparisonExtractionOption) {
    setDeleting(prev => new Set(prev).add(ext.id));
    try {
      // Pass the plain document_id (no composite suffix) to avoid URL encoding issues
      await deleteExtraction(ext.document_id);
      setExtractions(prev => prev.filter(e => e.id !== ext.id));
      setSelectedIds(prev => { const next = new Set(prev); next.delete(ext.id); return next; });
      setResult(null);
    } catch {
      setError('Failed to delete extraction');
    } finally {
      setDeleting(prev => { const next = new Set(prev); next.delete(ext.id); return next; });
    }
  }

  function handleRemoveOffer(extractionId: string) {
    // extraction_id from the result uses the composite "doc_id:idx" format
    toggleId(extractionId);
    setResult(null);
  }

  async function handleCompare() {
    if (selectedIds.size < 1) return;
    const ids = Array.from(selectedIds).sort();
    setLoading(true);
    setError(null);
    try {
      const data = await fetchOffersComparison(ids, preloadTxnId ?? undefined);
      setResult(data);
      setComparedIds(ids);

      if (preloadTxnId && ids.length >= 2) {
        setSummaryError(null);
        stopSummaryPoll();
        try {
          const existing = await getOfferSummary(preloadTxnId, ids);
          if (existing.status === 'ready' || existing.status === 'error') {
            setSummary(existing);
          } else if (existing.status === 'generating') {
            setSummary(existing);
            startSummaryPoll(preloadTxnId, ids);
          } else {
            setSummary({ status: 'generating', summary: null, generated_at: null });
            await generateOfferSummary(preloadTxnId, ids);
            startSummaryPoll(preloadTxnId, ids);
          }
        } catch {
          setSummaryError('Could not load offer summary');
        }
      } else {
        setSummary(null);
        stopSummaryPoll();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Comparison failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page-comparison">
      <Group justify="space-between" mb="lg">
        <div>
          <h1>Offer Comparison</h1>
          <p className="page-subtitle">Select 1 or more offers to compare side by side.</p>
        </div>
      </Group>

      {error && <div className="error-banner">{error}</div>}

      {/* Extraction selector */}
      <section className="comparison-selector">
        <div className="comparison-selector-header">
          <h2>Select Offers</h2>
          <div className="comparison-selector-controls">
            {txnsWithExtractions.length > 0 && (
              <select
                className="comparison-txn-filter"
                value={filterTxnId}
                onChange={e => { setFilterTxnId(e.target.value); setResult(null); }}
              >
                <option value="">All transactions</option>
                {txnsWithExtractions.map(t => (
                  <option key={t._id} value={t._id}>{t.name}</option>
                ))}
              </select>
            )}
            {visibleExtractions.length > 1 && (
              <button className="btn-link btn-sm" onClick={toggleAll}>
                {visibleExtractions.every(e => selectedIds.has(e.id)) ? 'Deselect All' : 'Select All'}
              </button>
            )}
          </div>
        </div>
        {loadingExtractions ? (
          <div className="loading-state">Loading extractions...</div>
        ) : extractions.length === 0 ? (
          <div className="comparison-empty-state">
            {preloadTxnId ? (
              <>
                <p>No offers linked to this transaction yet.</p>
                <p>Upload and extract an offer from the transaction Documents tab first.</p>
              </>
            ) : (
              <>
                <p>No real estate extractions found.</p>
                <p>Run an extraction on a purchase agreement first.</p>
                <Link to="/transactions" className="btn-primary" style={{ marginTop: 12 }}>
                  Go to Transactions
                </Link>
              </>
            )}
          </div>
        ) : visibleExtractions.length === 0 ? (
          <div className="comparison-empty-state">
            <p>No offers linked to this transaction yet.</p>
          </div>
        ) : (
          <div className="comparison-card-list">
            {visibleExtractions.map((ext) => {
              const linkedTxn = txnByDocId.get(ext.document_id);
              const displayTitle = (ext.buyer_name && ext.buyer_name.trim()) || ext.document_title || ext.filename;
              const displayType = ext.document_type ? ext.document_type.replace(/_/g, ' ') : null;
              return (
                <div
                  key={ext.id}
                  className={`comparison-card-row ${selectedIds.has(ext.id) ? 'selected' : ''}`}
                >
                  <label className="comparison-card-label">
                    <input
                      type="checkbox"
                      checked={selectedIds.has(ext.id)}
                      onChange={() => toggleId(ext.id)}
                    />
                    <div className="comparison-card-info">
                      <span className="comparison-card-filename">{displayTitle}</span>
                      <span className="comparison-card-meta">
                        {ext.pages_processed}p -{' '}
                        {displayType ? `${displayType} - ` : ''}
                        {ext.document_revision ? `${ext.document_revision} - ` : ''}
                        {ext.created_at && (
                          <> - {formatDate(ext.created_at)}</>
                        )}
                        {linkedTxn && (
                          <> - <span className="comparison-card-txn">{linkedTxn.name}</span></>
                        )}
                      </span>
                    </div>
                  </label>
                  <button
                    className="btn-link btn-sm btn-danger-text comparison-card-delete"
                    disabled={deleting.has(ext.id)}
                    onClick={() => handleDelete(ext)}
                    title="Permanently delete this extraction"
                  >
                    {deleting.has(ext.id) ? '...' : 'Delete'}
                  </button>
                </div>
              );
            })}
          </div>
        )}

        <button
          className="btn-primary"
          onClick={handleCompare}
          disabled={selectedIds.size < 1 || loading}
          style={{ marginTop: 16 }}
        >
          {loading
            ? 'Comparing...'
            : selectedIds.size === 1
              ? 'Compare Offer'
              : `Compare ${selectedIds.size > 0 ? `(${selectedIds.size})` : ''} Offers`}
        </button>
      </section>

      {/* AI Offer Summary — only shown after Compare is clicked for a transaction with ≥2 offers */}
      {preloadTxnId && comparedIds && comparedIds.length >= 2 && (summary || summaryError) && (
        <div className={`offer-summary-wrapper ${summary?.status === 'error' ? 'offer-summary-wrapper--error' : summary?.status === 'generating' ? 'rainbow-fast' : 'rainbow-slow'}`}>
          <section className="offer-summary-card">
            <div className="offer-summary-header">
              <h2 className="offer-summary-title">AI Offer Summary</h2>
              <button
                className={`offer-summary-refresh${summary?.status === 'generating' ? ' offer-summary-refresh--spinning' : ''}`}
                onClick={handleRefreshSummary}
                disabled={summary?.status === 'generating'}
                title="Regenerate summary"
                aria-label="Regenerate AI summary"
              >
                ↻
              </button>
            </div>

            {summaryError && (
              <p className="offer-summary-error">{summaryError}</p>
            )}

            {summary?.status === 'generating' && (
              <div className="offer-summary-loading">
                <p className="offer-summary-loading-label">
                  Analyzing offers&hellip; This takes about 15 seconds.
                </p>
                <div className="offer-summary-shimmer-bar" />
                <div className="offer-summary-shimmer-bar" style={{ width: '90%' }} />
                <div className="offer-summary-shimmer-bar" style={{ width: '95%' }} />
                <div className="offer-summary-shimmer-bar" style={{ width: '80%' }} />
                <div className="offer-summary-shimmer-bar" style={{ width: '70%' }} />
              </div>
            )}

            {summary?.status === 'ready' && summary.summary && (
              <div className="offer-summary-content" key={summary.generated_at ?? 'summary'}>
                <p className="offer-summary-text">{summary.summary}</p>
                {summary.generated_at && (
                  <p className="offer-summary-meta">
                    Generated {new Date(summary.generated_at).toLocaleString()}
                  </p>
                )}
              </div>
            )}

            {summary?.status === 'error' && (
              <p className="offer-summary-error">
                Summary generation failed. Click ↻ to retry.
              </p>
            )}
          </section>
        </div>
      )}

      {/* Comparison table */}
      {result && (
        <section className="comparison-result">
          <h2>Comparison ({result.offers.length} offers)</h2>
          <ComparisonTable
            result={result}
            localEdits={localEdits}
            highlightedRow={highlightedRow}
            onRowHover={setHighlightedRow}
            onRemoveOffer={handleRemoveOffer}
            onFieldSave={handleFieldSave}
          />
        </section>
      )}
    </div>
  );
}
