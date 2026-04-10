import { Stack, Text, Tooltip } from '@mantine/core';
import { cloneElement, isValidElement, type ReactElement } from 'react';
import type { VerificationCitation } from '../../api';

type CitationState = 'supported' | 'not_found' | 'not_captured';
type CellValue = string | number | boolean | null;

function buildFallbackText(value: CellValue, state: CitationState): string {
  if (state === 'not_found') {
    if (value === null || value === undefined || value === '') return 'Not found in document';
    if (value === false) return 'Negative result could not be verified in document';
    return 'Value extracted, but source location was not verified';
  }
  if (value === null || value === undefined || value === '') return 'No citation captured for this empty result';
  if (value === false) return 'No citation captured for this negative result';
  return 'No citation captured for this value';
}

function stringifyValue(value: CellValue): string {
  if (value === null || value === undefined || value === '') return 'empty';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  return String(value);
}

function citationSummary(citation: VerificationCitation): string {
  return `Page ${citation.page_number}, ${citation.line_or_region}. ${citation.surrounding_text}`;
}

function isSyntheticNotFoundCitation(citation: VerificationCitation): boolean {
  return citation.page_number === 0
    && citation.line_or_region.trim().toLowerCase() === 'not found'
    && citation.surrounding_text.trim().toUpperCase() === 'NOT FOUND'
    && Number(citation.confidence ?? 0) <= 0;
}

export function ComparisonCellCitation({
  children,
  fieldLabel,
  value,
  citations,
  state,
  stale,
  disabled = false,
}: {
  children: ReactElement<{
    className?: string;
    tabIndex?: number;
    'aria-label'?: string;
  }>;
  fieldLabel: string;
  value: CellValue;
  citations: VerificationCitation[];
  state: CitationState;
  stale: boolean;
  disabled?: boolean;
}) {
  const fallbackText = buildFallbackText(value, state);
  const visibleCitations = citations.filter(citation => !isSyntheticNotFoundCitation(citation)).slice(0, 3);
  const ariaLabel = [
    fieldLabel,
    `Current value: ${stringifyValue(value)}.`,
    stale ? 'Edited value — citation reflects the original extraction.' : '',
    visibleCitations.length > 0
      ? visibleCitations.map(citationSummary).join(' ')
      : fallbackText,
  ]
    .filter(Boolean)
    .join(' ');

  const label = (
    <Stack gap={6} className="comparison-citation-tooltip">
      {stale && (
        <Text size="xs" fw={700} c="yellow.4">
          Edited value - citation reflects the original extraction
        </Text>
      )}
      {visibleCitations.length > 0 ? (
        visibleCitations.map((citation, idx) => (
          <div key={`${citation.field_name}-${citation.page_number}-${idx}`} className="comparison-citation-entry">
            <Text size="xs" fw={600}>
              Page {citation.page_number} · {citation.line_or_region}
            </Text>
            <Text size="xs">
              {citation.surrounding_text}
            </Text>
          </div>
        ))
      ) : (
        <Text size="xs">{fallbackText}</Text>
      )}
    </Stack>
  );

  const className = [children.props.className, 'comparison-citation-trigger'].filter(Boolean).join(' ');
  const content = isValidElement(children)
    ? cloneElement(children, {
        className,
        tabIndex: disabled ? -1 : 0,
        'aria-label': ariaLabel,
      })
    : children;

  if (disabled) return content;

  return (
    <Tooltip
      label={label}
      multiline
      openDelay={120}
      withinPortal
      position="top-start"
      classNames={{ tooltip: 'comparison-citation-tooltip-shell' }}
    >
      {content}
    </Tooltip>
  );
}
