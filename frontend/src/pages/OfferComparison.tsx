/** N-way offer comparison table for Julie Gardner Properties. */

import { useState, useEffect } from 'react';
import { fetchExtractions, fetchOffersComparison } from '../api';
import type { ExtractionSummary, OffersComparisonResult, OfferField } from '../api';

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

function formatValue(value: string | number | boolean | null, type: OfferField['type']): string {
  if (value === null || value === undefined) return '—';
  if (type === 'currency' && typeof value === 'number') {
    return `$${value.toLocaleString()}`;
  }
  if (type === 'boolean') {
    return value ? 'Yes' : 'No';
  }
  return String(value);
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
// ComparisonTable
// ---------------------------------------------------------------------------

interface ComparisonTableProps {
  result: OffersComparisonResult;
}

function ComparisonTable({ result }: ComparisonTableProps) {
  const { offers, field_definitions } = result;

  return (
    <div className="comparison-table-wrapper">
      <table className="comparison-table">
        <thead>
          <tr>
            <th className="comparison-field-col">Field</th>
            {offers.map((offer) => (
              <th key={offer.extraction_id} className="comparison-offer-col">
                <div className="comparison-offer-name">
                  {String(offer.fields['buyer_name'] || offer.filename)}
                </div>
                <div className="comparison-offer-file">{offer.filename}</div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {field_definitions.map((field) => {
            const allValues = offers.map((o) => o.fields[field.key] ?? null);

            return (
              <tr key={field.key}>
                <td className="comparison-field-label">{field.label}</td>
                {offers.map((offer, idx) => {
                  const raw = offer.fields[field.key] ?? null;
                  let cellClass = '';
                  if (field.key === 'purchase_price') {
                    cellClass = getPriceClass(
                      typeof raw === 'number' ? raw : null,
                      allValues.map((v) => (typeof v === 'number' ? v : null)),
                    );
                  } else if (field.type === 'date') {
                    cellClass = getDateClass(
                      typeof raw === 'string' ? raw : null,
                      allValues.map((v) => (typeof v === 'string' ? v : null)),
                    );
                  }

                  return (
                    <td
                      key={`${field.key}-${idx}`}
                      className={`comparison-cell ${cellClass}`}
                    >
                      {formatValue(raw as string | number | boolean | null, field.type)}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// OfferComparison page
// ---------------------------------------------------------------------------

export function OfferComparison() {
  const [extractions, setExtractions] = useState<ExtractionSummary[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [result, setResult] = useState<OffersComparisonResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadingExtractions, setLoadingExtractions] = useState(true);

  useEffect(() => {
    fetchExtractions('real_estate')
      .then(setExtractions)
      .catch(() => setError('Failed to load extractions'))
      .finally(() => setLoadingExtractions(false));
  }, []);

  function toggleId(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    // Clear results when selection changes
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
      <div className="page-header-row">
        <div>
          <h1>Offer Comparison</h1>
          <p className="page-subtitle">Select 2 or more offers to compare side by side.</p>
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {/* Extraction selector */}
      <section className="comparison-selector">
        <h2>Select Offers</h2>
        {loadingExtractions ? (
          <div className="loading-state">Loading extractions...</div>
        ) : extractions.length === 0 ? (
          <div className="empty-state">
            <p>No real estate extractions found.</p>
            <p>Run an extraction on a purchase agreement first.</p>
          </div>
        ) : (
          <div className="comparison-checklist">
            {extractions.map((ext) => (
              <label key={ext.id} className="comparison-check-row">
                <input
                  type="checkbox"
                  checked={selectedIds.has(ext.id)}
                  onChange={() => toggleId(ext.id)}
                />
                <span className="comparison-check-label">
                  {ext.filename}
                  <span className="comparison-check-meta">
                    {ext.pages_processed}p &middot;{' '}
                    {Math.round(ext.overall_confidence * 100)}% confidence
                    {ext.created_at && (
                      <> &middot; {new Date(ext.created_at).toLocaleDateString()}</>
                    )}
                  </span>
                </span>
              </label>
            ))}
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
          <ComparisonTable result={result} />
        </section>
      )}
    </div>
  );
}
