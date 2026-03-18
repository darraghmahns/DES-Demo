/** N-way offer comparison table for Julie Gardner Properties. */

import { useState, useEffect, useRef, useCallback } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Group } from '@mantine/core';
import { fetchExtractions, fetchOffersComparison, deleteExtraction, updateOfferFields } from '../api';
import type { ExtractionSummary, OffersComparisonResult, OfferField } from '../api';
import { listTransactions } from '../api/transactions';
import type { Transaction } from '../types/transaction';

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
  onSave: (extractionId: string, key: string, value: FieldValue) => void;
}

// Boolean fields that indicate a negative/risk when true (from seller's perspective)
const WARN_WHEN_TRUE = new Set(['opd_delivered']);

function EditableCell({ value, field, extractionId, allValues, onSave }: EditableCellProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');
  const [saved, setSaved] = useState(false);
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
      <td
        className={`comparison-cell comparison-cell-bool ${cellClass}`}
        onClick={() => { onSave(extractionId, field.key, next); setSaved(true); setTimeout(() => setSaved(false), 1500); }}
        title="Click to toggle"
      >
        <span className="comparison-cell-value">{formatValue(value, field.type)}</span>
        {saved && <span className="comparison-cell-saved">Saved</span>}
      </td>
    );
  }

  // Text (notes, inclusions etc.): always-on textarea
  if (field.type === 'text') {
    return (
      <td className={`comparison-cell comparison-cell-text ${cellClass}`}>
        <textarea
          className="comparison-cell-textarea"
          defaultValue={value != null ? String(value) : ''}
          onChange={e => triggerSave(e.target.value)}
          rows={3}
          placeholder="--"
        />
        {saved && <span className="comparison-cell-saved">Saved</span>}
      </td>
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
    <td
      className={`comparison-cell comparison-cell-clickable ${cellClass}`}
      onClick={() => { setDraft(value != null ? String(value) : ''); setEditing(true); }}
      title="Click to edit"
    >
      <span className="comparison-cell-value">{formatValue(value, field.type)}</span>
      {saved && <span className="comparison-cell-saved">Saved</span>}
    </td>
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
  // IDs passed from the Offers tab — if present, filter and pre-select only those
  const preloadIds = searchParams.get('ids')
    ? new Set(searchParams.get('ids')!.split(',').filter(Boolean))
    : null;

  const [extractions, setExtractions] = useState<ExtractionSummary[]>([]);
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
    Promise.all([
      fetchExtractions('real_estate'),
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

      // preloadIds are plain ObjectIds (from fetchTransactionExtractions);
      // list_extractions returns composite "doc_id:idx" as `id` but plain doc_id as `document_id`
      const visible = preloadIds
        ? all.filter(e => preloadIds.has(e.document_id))
        : all;
      setExtractions(visible);
      if (preloadIds) {
        setSelectedIds(new Set(visible.map(e => e.id)));
      }
    })
      .catch(() => setError('Failed to load extractions'))
      .finally(() => setLoadingExtractions(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
  }

  async function handleDelete(ext: ExtractionSummary) {
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
    if (selectedIds.size < 2) return;
    setLoading(true);
    setError(null);
    try {
      const data = await fetchOffersComparison(Array.from(selectedIds));
      setResult(data);
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
          <p className="page-subtitle">Select 2 or more offers to compare side by side.</p>
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
            <p>No real estate extractions found.</p>
            <p>Run an extraction on a purchase agreement first.</p>
            <Link to="/transactions" className="btn-primary" style={{ marginTop: 12 }}>
              Go to Transactions
            </Link>
          </div>
        ) : visibleExtractions.length === 0 ? (
          <div className="comparison-empty-state">
            <p>No offers linked to this transaction yet.</p>
          </div>
        ) : (
          <div className="comparison-card-list">
            {visibleExtractions.map((ext) => {
              const linkedTxn = txnByDocId.get(ext.document_id);
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
                      <span className="comparison-card-filename">{ext.filename}</span>
                      <span className="comparison-card-meta">
                        {ext.pages_processed}p -{' '}
                        <span className={`conf-badge-inline ${ext.overall_confidence >= 0.85 ? 'high' : ext.overall_confidence >= 0.65 ? 'medium' : 'low'}`}>
                          {Math.round(ext.overall_confidence * 100)}%
                        </span>
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
          disabled={selectedIds.size < 2 || loading}
          style={{ marginTop: 16 }}
        >
          {loading ? 'Comparing...' : `Compare ${selectedIds.size > 0 ? `(${selectedIds.size})` : ''} Offers`}
        </button>
      </section>

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
