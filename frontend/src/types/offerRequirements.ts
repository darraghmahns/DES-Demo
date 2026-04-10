/** Offer requirements evaluation — rules, types, and evaluator. */

import type { ParticipantRole } from './transaction';
import type { TransactionDocRecord } from '../api/transactions';

type FieldValue = string | number | boolean | null;

export interface OfferRequirementRule {
  doc_type: string;
  label: string;
  description: string;
  role: ParticipantRole;
  required: boolean;
  upload_mode: 'attachment_only' | 'extract_and_merge';
  triggered_when: (fields: Record<string, FieldValue>) => boolean;
}

export interface EvaluatedRequirement {
  rule: OfferRequirementRule;
  satisfied: boolean;
}

export const OFFER_REQUIREMENT_RULES: OfferRequirementRule[] = [
  {
    doc_type: 'pre_approval_letter',
    label: 'Pre-Approval Letter',
    description: 'Lender letter confirming buyer is approved for financing.',
    role: 'BUYING_AGENT',
    required: true,
    upload_mode: 'attachment_only',
    triggered_when: () => true,
  },
  {
    doc_type: 'escalation_addendum',
    label: 'Escalation Addendum',
    description: 'Addendum detailing escalation clause terms and cap.',
    role: 'BUYING_AGENT',
    required: true,
    upload_mode: 'extract_and_merge',
    triggered_when: (fields) => fields['escalation_clause'] === true,
  },
  {
    doc_type: 'inspection_addendum',
    label: 'Inspection Addendum',
    description: 'Addendum specifying inspection contingency terms and deadlines.',
    role: 'BUYING_AGENT',
    required: true,
    upload_mode: 'extract_and_merge',
    triggered_when: (fields) => fields['inspection_contingency'] === true,
  },
  {
    doc_type: 'hoa_documents',
    label: 'HOA Documents',
    description: 'HOA rules, financials, or approval documentation required for the contingency.',
    role: 'BUYING_AGENT',
    required: true,
    upload_mode: 'attachment_only',
    triggered_when: (fields) => fields['hoa_approval_contingency'] === true,
  },
  {
    doc_type: 'sale_contingency_addendum',
    label: 'Sale Contingency Addendum',
    description: 'Addendum confirming sale of buyer\'s current home as a condition of this offer.',
    role: 'BUYER',
    required: true,
    upload_mode: 'extract_and_merge',
    triggered_when: (fields) => fields['sale_of_home_contingency'] === true,
  },
  {
    doc_type: 'appraisal_contingency_addendum',
    label: 'Appraisal Contingency Addendum',
    description: 'Addendum documenting terms if property appraises below purchase price.',
    role: 'BUYING_AGENT',
    required: true,
    upload_mode: 'extract_and_merge',
    triggered_when: (fields) => fields['appraisal_contingency'] === true,
  },
];

export function evaluateOfferRequirements(
  fields: Record<string, FieldValue>,
  txnDocs: TransactionDocRecord[],
  offerExtractionId: string,
): EvaluatedRequirement[] {
  return OFFER_REQUIREMENT_RULES
    .filter(rule => rule.triggered_when(fields))
    .map(rule => ({
      rule,
      // A doc satisfies the requirement if it matches the doc_type AND is either
      // scoped to this offer or unscoped (uploaded before offer-scoping existed).
      satisfied: txnDocs.some(
        d => d.doc_type === rule.doc_type &&
          (d.offer_extraction_id === offerExtractionId || !d.offer_extraction_id),
      ),
    }));
}
