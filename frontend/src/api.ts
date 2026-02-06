// ---------------------------------------------------------------------------
// TypeScript interfaces mirroring schemas.py
// ---------------------------------------------------------------------------

export interface DocumentInfo {
  name: string;
  size_human: string;
  pages: number;
}

export interface VerificationCitation {
  field_name: string;
  extracted_value: string;
  page_number: number;
  line_or_region: string;
  surrounding_text: string;
  confidence: number;
}

export interface PIIFinding {
  pii_type: string;
  value_redacted: string;
  severity: string;
  confidence: number;
  location: string;
  recommendation: string;
}

export interface PIIReport {
  findings: PIIFinding[];
  pii_risk_score: number;
  risk_level: string;
}

export interface ExtractionResult {
  mode: string;
  source_file: string;
  extraction_timestamp: string;
  model_used: string;
  pages_processed: number;
  dotloop_data: Record<string, unknown> | null;
  foia_data: Record<string, unknown> | null;
  dotloop_api_payload: Record<string, unknown> | null;
  citations: VerificationCitation[];
  overall_confidence: number;
  pii_report: PIIReport | null;
}

// ---------------------------------------------------------------------------
// SSE event types (kept for App.tsx compatibility)
// ---------------------------------------------------------------------------

export interface StepEvent {
  step: number;
  total: number;
  title: string;
  status: string;
}

export interface StepCompleteEvent {
  step: number;
  title: string;
  status: string;
  data: Record<string, unknown>;
}

export interface ExtractionEvent {
  validated_data: Record<string, unknown>;
}

export interface ValidationEvent {
  success: boolean;
  errors: string[];
}

export interface CitationsEvent {
  citations: VerificationCitation[];
  overall_confidence: number;
}

export interface PIIEvent {
  findings: PIIFinding[];
  risk_score: number;
  risk_level: string;
}

export type SSEEvent =
  | { type: 'step'; data: StepEvent }
  | { type: 'step_complete'; data: StepCompleteEvent }
  | { type: 'extraction'; data: ExtractionEvent }
  | { type: 'validation'; data: ValidationEvent }
  | { type: 'citations'; data: CitationsEvent }
  | { type: 'pii'; data: PIIEvent }
  | { type: 'complete'; data: ExtractionResult }
  | { type: 'error'; data: { message: string } };

// ---------------------------------------------------------------------------
// Static demo data
// ---------------------------------------------------------------------------

const STATIC_DOCUMENTS: Record<string, DocumentInfo[]> = {
  real_estate: [
    { name: 'sample_purchase_agreement.pdf', size_human: '6.8 KB', pages: 3 },
  ],
  gov: [
    { name: 'sample_foia_request.pdf', size_human: '4.4 KB', pages: 2 },
  ],
};

const REAL_ESTATE_RESULT: ExtractionResult = {
  mode: "real_estate",
  source_file: "sample_purchase_agreement.pdf",
  extraction_timestamp: "2026-02-06T19:36:36.496058+00:00",
  model_used: "docextract-vision-v1",
  pages_processed: 3,
  dotloop_data: {
    loop_name: "Michael B. Curtis, 2100 Waterview Dr, Billings, Montana 59101",
    transaction_type: "PURCHASE_OFFER",
    transaction_status: "PRE_OFFER",
    property_address: {
      street_number: "2100",
      street_name: "Waterview Dr",
      unit_number: "B",
      city: "Billings",
      state_or_province: "Montana",
      postal_code: "59101",
      country: "US",
      county: "Yellowstone",
      mls_number: "MT-2024-88712",
      parcel_tax_id: "S06-2100-0045-00B",
    },
    financials: {
      purchase_price: 485000.0,
      earnest_money_amount: 10000.0,
      earnest_money_held_by: "First American Title",
      sale_commission_rate: "6%",
      sale_commission_total: null,
    },
    contract_dates: {
      contract_agreement_date: null,
      closing_date: "03/15/2025",
      offer_date: "01/28/2025",
      offer_expiration_date: "02/01/2025",
      inspection_date: "02/10/2025",
    },
    participants: [
      { full_name: "Michael B. Curtis", role: "BUYER", email: null, phone: null, company_name: null },
      { full_name: "Sarah A. Curtis", role: "BUYER", email: null, phone: null, company_name: null },
      { full_name: "Tiffany J. Selong", role: "SELLER", email: null, phone: null, company_name: null },
      { full_name: "Jason R. Selong", role: "SELLER", email: null, phone: null, company_name: null },
      { full_name: "Julie Henderson", role: "LISTING_AGENT", email: "julie.h@evmontana.com", phone: "(406) 555-0187", company_name: "Engel & Volkers" },
      { full_name: "Robert Chen", role: "BUYING_AGENT", email: "robert.chen@remax.com", phone: "(406) 555-0234", company_name: "RE/MAX Realty" },
    ],
  },
  foia_data: null,
  dotloop_api_payload: {
    name: "Michael B. Curtis, 2100 Waterview Dr, Billings, Montana 59101",
    transactionType: "PURCHASE_OFFER",
    status: "PRE_OFFER",
    loopDetails: {
      "Property Address": {
        Country: "US", "Street Number": "2100", "Street Name": "Waterview Dr",
        "Unit Number": "B", City: "Billings", "State/Prov": "Montana",
        "Zip/Postal Code": "59101", County: "Yellowstone", "MLS Number": "MT-2024-88712", "Parcel/Tax ID": "S06-2100-0045-00B",
      },
      Financials: {
        "Purchase/Sale Price": "485000.0", "Earnest Money Amount": "10000.0",
        "Earnest Money Held By": "First American Title", "Sale Commission Rate": "6%", "Sale Commission Total": "",
      },
      "Contract Dates": {
        "Contract Agreement Date": "", "Closing Date": "03/15/2025",
        "Offer Date": "01/28/2025", "Offer Expiration Date": "02/01/2025", "Inspection Date": "02/10/2025",
      },
    },
    participants: [
      { fullName: "Michael B. Curtis", role: "BUYER", email: "", Phone: "", "Company Name": "" },
      { fullName: "Sarah A. Curtis", role: "BUYER", email: "", Phone: "", "Company Name": "" },
      { fullName: "Tiffany J. Selong", role: "SELLER", email: "", Phone: "", "Company Name": "" },
      { fullName: "Jason R. Selong", role: "SELLER", email: "", Phone: "", "Company Name": "" },
      { fullName: "Julie Henderson", role: "LISTING_AGENT", email: "julie.h@evmontana.com", Phone: "(406) 555-0187", "Company Name": "Engel & Volkers" },
      { fullName: "Robert Chen", role: "BUYING_AGENT", email: "robert.chen@remax.com", Phone: "(406) 555-0234", "Company Name": "RE/MAX Realty" },
    ],
  },
  citations: [
    { field_name: "loop_name", extracted_value: "Michael B. Curtis, 2100 Waterview Dr, Billings, Montana 59101", page_number: 1, line_or_region: "Section 1, line 3 and Section 2, line 2", surrounding_text: "Michael B. Curtis & Sarah A. Curtis Purchaser 2100 Waterview Dr, Unit B", confidence: 0.9 },
    { field_name: "transaction_type", extracted_value: "PURCHASE_OFFER", page_number: 1, line_or_region: "Title", surrounding_text: "RESIDENTIAL PURCHASE AGREEMENT", confidence: 0.8 },
    { field_name: "transaction_status", extracted_value: "PRE_OFFER", page_number: 1, line_or_region: "NOT FOUND", surrounding_text: "NOT FOUND", confidence: 0.0 },
    { field_name: "property_address.street_number", extracted_value: "2100", page_number: 1, line_or_region: "Section 2, line 2", surrounding_text: "Street Address: 2100 Waterview Dr, Unit B", confidence: 0.95 },
    { field_name: "property_address.street_name", extracted_value: "Waterview Dr", page_number: 1, line_or_region: "Section 2, line 2", surrounding_text: "Street Address: 2100 Waterview Dr, Unit B", confidence: 0.95 },
    { field_name: "property_address.unit_number", extracted_value: "B", page_number: 1, line_or_region: "Section 2, line 2", surrounding_text: "Street Address: 2100 Waterview Dr, Unit B", confidence: 0.95 },
    { field_name: "property_address.city", extracted_value: "Billings", page_number: 1, line_or_region: "Section 2, line 3", surrounding_text: "City: Billings", confidence: 0.95 },
    { field_name: "property_address.state_or_province", extracted_value: "Montana", page_number: 1, line_or_region: "Section 2, line 4", surrounding_text: "State: Montana (MT)", confidence: 0.95 },
    { field_name: "property_address.postal_code", extracted_value: "59101", page_number: 1, line_or_region: "Section 2, line 5", surrounding_text: "ZIP Code: 59101", confidence: 0.95 },
    { field_name: "property_address.country", extracted_value: "US", page_number: 1, line_or_region: "NOT FOUND", surrounding_text: "NOT FOUND", confidence: 0.0 },
    { field_name: "property_address.county", extracted_value: "Yellowstone", page_number: 1, line_or_region: "Section 2, line 6", surrounding_text: "County: Yellowstone", confidence: 0.95 },
    { field_name: "property_address.mls_number", extracted_value: "MT-2024-88712", page_number: 1, line_or_region: "Section 2, line 7", surrounding_text: "MLS Number: MT-2024-88712", confidence: 0.95 },
    { field_name: "property_address.parcel_tax_id", extracted_value: "S06-2100-0045-00B", page_number: 1, line_or_region: "Section 2, line 8", surrounding_text: "Parcel/Tax ID: S06-2100-0045-00B", confidence: 0.95 },
    { field_name: "financials.earnest_money_held_by", extracted_value: "First American Title", page_number: 2, line_or_region: "Section 3, line 3", surrounding_text: "Earnest Money Held By: First American Title", confidence: 0.95 },
    { field_name: "financials.sale_commission_rate", extracted_value: "6%", page_number: 3, line_or_region: "Section 6, line 4", surrounding_text: "Sale Commission Rate: 6% of the purchase price", confidence: 0.95 },
    { field_name: "contract_dates.closing_date", extracted_value: "03/15/2025", page_number: 2, line_or_region: "Section 4, line 6", surrounding_text: "Closing Date: 03/15/2025", confidence: 0.95 },
    { field_name: "contract_dates.offer_date", extracted_value: "01/28/2025", page_number: 2, line_or_region: "Section 4, line 1", surrounding_text: "Offer Date: 01/28/2025", confidence: 0.95 },
    { field_name: "contract_dates.offer_expiration_date", extracted_value: "02/01/2025", page_number: 2, line_or_region: "Section 4, line 2", surrounding_text: "Offer Expiration: 02/01/2025 at 5:00 PM MST", confidence: 0.95 },
    { field_name: "contract_dates.inspection_date", extracted_value: "02/10/2025", page_number: 2, line_or_region: "Section 4, line 3", surrounding_text: "Inspection Deadline: 02/10/2025", confidence: 0.95 },
    { field_name: "participants[0].full_name", extracted_value: "Michael B. Curtis", page_number: 1, line_or_region: "Section 1, line 3", surrounding_text: "BUYER(S): Michael B. Curtis & Sarah A. Curtis", confidence: 0.95 },
    { field_name: "participants[0].role", extracted_value: "BUYER", page_number: 1, line_or_region: "Section 1, line 3", surrounding_text: "BUYER(S): Michael B. Curtis & Sarah A. Curtis Purchaser", confidence: 0.95 },
    { field_name: "participants[1].full_name", extracted_value: "Sarah A. Curtis", page_number: 1, line_or_region: "Section 1, line 3", surrounding_text: "BUYER(S): Michael B. Curtis & Sarah A. Curtis", confidence: 0.95 },
    { field_name: "participants[1].role", extracted_value: "BUYER", page_number: 1, line_or_region: "Section 1, line 3", surrounding_text: "BUYER(S): Michael B. Curtis & Sarah A. Curtis Purchaser", confidence: 0.95 },
    { field_name: "participants[2].full_name", extracted_value: "Tiffany J. Selong", page_number: 1, line_or_region: "Section 1, line 4", surrounding_text: "SELLER(S): Tiffany J. Selong & Jason R. Selong", confidence: 0.95 },
    { field_name: "participants[2].role", extracted_value: "SELLER", page_number: 1, line_or_region: "Section 1, line 4", surrounding_text: "SELLER(S): Tiffany J. Selong & Jason R. Selong Vendor", confidence: 0.95 },
    { field_name: "participants[3].full_name", extracted_value: "Jason R. Selong", page_number: 1, line_or_region: "Section 1, line 4", surrounding_text: "SELLER(S): Tiffany J. Selong & Jason R. Selong", confidence: 0.95 },
    { field_name: "participants[3].role", extracted_value: "SELLER", page_number: 1, line_or_region: "Section 1, line 4", surrounding_text: "SELLER(S): Tiffany J. Selong & Jason R. Selong Vendor", confidence: 0.95 },
    { field_name: "participants[4].full_name", extracted_value: "Julie Henderson", page_number: 3, line_or_region: "Section 6, line 1", surrounding_text: "Listing Agent: Julie Henderson", confidence: 0.95 },
    { field_name: "participants[4].role", extracted_value: "LISTING_AGENT", page_number: 3, line_or_region: "Section 6, line 1", surrounding_text: "Listing Agent: Julie Henderson", confidence: 0.95 },
    { field_name: "participants[4].email", extracted_value: "julie.h@evmontana.com", page_number: 3, line_or_region: "Section 6, line 1", surrounding_text: "julie.h@evmontana.com", confidence: 0.95 },
    { field_name: "participants[4].phone", extracted_value: "(406) 555-0187", page_number: 3, line_or_region: "Section 6, line 1", surrounding_text: "(406) 555-0187", confidence: 0.95 },
    { field_name: "participants[4].company_name", extracted_value: "Engel & Volkers", page_number: 3, line_or_region: "Section 6, line 1", surrounding_text: "Engel & Volkers", confidence: 0.95 },
    { field_name: "participants[5].full_name", extracted_value: "Robert Chen", page_number: 3, line_or_region: "Section 6, line 2", surrounding_text: "Buying Agent: Robert Chen", confidence: 0.95 },
    { field_name: "participants[5].role", extracted_value: "BUYING_AGENT", page_number: 3, line_or_region: "Section 6, line 2", surrounding_text: "Buying Agent: Robert Chen", confidence: 0.95 },
    { field_name: "participants[5].email", extracted_value: "robert.chen@remax.com", page_number: 3, line_or_region: "Section 6, line 2", surrounding_text: "robert.chen@remax.com", confidence: 0.95 },
    { field_name: "participants[5].phone", extracted_value: "(406) 555-0234", page_number: 3, line_or_region: "Section 6, line 2", surrounding_text: "(406) 555-0234", confidence: 0.95 },
    { field_name: "participants[5].company_name", extracted_value: "RE/MAX Realty", page_number: 3, line_or_region: "Section 6, line 2", surrounding_text: "RE/MAX Realty", confidence: 0.95 },
  ],
  overall_confidence: 0.8932432432432431,
  pii_report: null,
};

const GOV_RESULT: ExtractionResult = {
  mode: "gov",
  source_file: "sample_foia_request.pdf",
  extraction_timestamp: "2026-02-06T19:38:01.850102+00:00",
  model_used: "docextract-vision-v1",
  pages_processed: 2,
  dotloop_data: null,
  foia_data: {
    requester: {
      first_name: "Sarah",
      last_name: "Mitchell",
      email: "s.mitchell@springfield-news.org",
      phone: "(217) 555-0134",
      address_street: "742 Evergreen Terrace",
      address_city: "Springfield",
      address_state: "IL",
      address_zip: "62704",
      organization: "Springfield Daily Register",
    },
    request_description: "All contracts, purchase orders, invoices, and related correspondence pertaining to the procurement of border surveillance technology systems, including but not limited to: autonomous surveillance towers, ground-based radar systems, and integrated sensor platforms. This request covers all such records from the period of January 1, 2023 through December 31, 2024. This request includes, but is not limited to, records related to contract award notices, vendor selection criteria, cost-benefit analyses, performance evaluations, and any internal memoranda discussing the effectiveness or limitations of these systems. Reference case file: 078-05-1120.",
    request_category: "media",
    agency: "Department of Homeland Security",
    agency_component_name: "Office of Privacy",
    fee_amount_willing: 250.0,
    fee_waiver: true,
    expedited_processing: true,
    date_range_start: "01/01/2023",
    date_range_end: "12/31/2024",
  },
  dotloop_api_payload: null,
  citations: [
    { field_name: "first_name", extracted_value: "Sarah", page_number: 1, line_or_region: "line 1", surrounding_text: "Sarah Mitchell", confidence: 1.0 },
    { field_name: "last_name", extracted_value: "Mitchell", page_number: 1, line_or_region: "line 1", surrounding_text: "Sarah Mitchell", confidence: 1.0 },
    { field_name: "email", extracted_value: "s.mitchell@springfield-news.org", page_number: 1, line_or_region: "line 6", surrounding_text: "Email: s.mitchell@springfield-news.org", confidence: 1.0 },
    { field_name: "phone", extracted_value: "(217) 555-0134", page_number: 1, line_or_region: "line 5", surrounding_text: "Phone: (217) 555-0134", confidence: 1.0 },
    { field_name: "address_street", extracted_value: "742 Evergreen Terrace", page_number: 1, line_or_region: "line 3", surrounding_text: "742 Evergreen Terrace", confidence: 1.0 },
    { field_name: "address_city", extracted_value: "Springfield", page_number: 1, line_or_region: "line 4", surrounding_text: "Springfield, IL 62704", confidence: 1.0 },
    { field_name: "address_state", extracted_value: "IL", page_number: 1, line_or_region: "line 4", surrounding_text: "Springfield, IL 62704", confidence: 1.0 },
    { field_name: "address_zip", extracted_value: "62704", page_number: 1, line_or_region: "line 4", surrounding_text: "Springfield, IL 62704", confidence: 1.0 },
    { field_name: "organization", extracted_value: "Springfield Daily Register", page_number: 1, line_or_region: "line 2", surrounding_text: "Springfield Daily Register", confidence: 1.0 },
    { field_name: "request_description", extracted_value: "All contracts, purchase orders, invoices, and related correspondence pertaining to the procurement of border surveillance technology systems, including but not limited to: autonomous surveillance towers, ground-based radar systems, and integrated sensor platforms. This request covers all such records from the period of January 1, 2023 through December 31, 2024. This request includes, but is not limited to, records related to contract award notices, vendor selection criteria, cost-benefit analyses, performance evaluations, and any internal memoranda discussing the effectiveness or limitations of these systems. Reference case file: 078-05-1120.", page_number: 1, line_or_region: "lines 13-18", surrounding_text: "Requested Records: All contracts, purchase orders, invoices, and related correspondence", confidence: 1.0 },
    { field_name: "request_category", extracted_value: "media", page_number: 1, line_or_region: "line 20", surrounding_text: "I am a representative of the news media", confidence: 1.0 },
    { field_name: "agency", extracted_value: "Department of Homeland Security", page_number: 1, line_or_region: "line 10", surrounding_text: "Department of Homeland Security", confidence: 1.0 },
    { field_name: "agency_component_name", extracted_value: "Office of Privacy", page_number: 1, line_or_region: "line 11", surrounding_text: "Office of Privacy", confidence: 1.0 },
    { field_name: "date_range_start", extracted_value: "01/01/2023", page_number: 1, line_or_region: "line 16", surrounding_text: "from the period of January 1, 2023", confidence: 1.0 },
    { field_name: "date_range_end", extracted_value: "12/31/2024", page_number: 1, line_or_region: "line 16", surrounding_text: "through December 31, 2024.", confidence: 1.0 },
  ],
  overall_confidence: 1.0,
  pii_report: {
    findings: [
      { pii_type: "SSN", value_redacted: "***-**-1120", severity: "HIGH", confidence: 0.95, location: "Page 1, line 24", recommendation: "CRITICAL: SSN detected. Encrypt before transmission. Verify if SSN is required for this request." },
      { pii_type: "PHONE", value_redacted: "(***) ***-0134", severity: "MEDIUM", confidence: 0.95, location: "Page 1, line 5", recommendation: "Phone number detected. Required for FOIA contact. Ensure secure transmission channel." },
      { pii_type: "EMAIL", value_redacted: "s***@springfield-news.org", severity: "MEDIUM", confidence: 0.95, location: "Page 1, line 6", recommendation: "Email address detected. Required for FOIA correspondence. Standard handling applies." },
    ],
    pii_risk_score: 65,
    risk_level: "HIGH",
  },
};

// ---------------------------------------------------------------------------
// Static API functions
// ---------------------------------------------------------------------------

export async function fetchDocuments(mode?: string): Promise<DocumentInfo[]> {
  const key = mode === 'gov' ? 'gov' : 'real_estate';
  return Promise.resolve(STATIC_DOCUMENTS[key]);
}

export function getDocumentUrl(name: string): string {
  return `/docs/${encodeURIComponent(name)}`;
}

/**
 * Simulate the extraction pipeline with realistic delays.
 * Fires the same SSE-like events that App.tsx expects.
 * Returns an abort function to cancel.
 */
export function runExtraction(
  mode: string,
  _filename: string,
  onEvent: (event: SSEEvent) => void,
): () => void {
  let cancelled = false;
  const result = mode === 'gov' ? GOV_RESULT : REAL_ESTATE_RESULT;
  const isGov = mode === 'gov';
  const totalSteps = isGov ? 7 : 6;

  const extractedData = isGov ? result.foia_data! : result.dotloop_data!;

  // Build step sequence with delays
  interface QueuedEvent {
    delay: number;
    event: SSEEvent;
  }

  const events: QueuedEvent[] = [];
  let offset = 0;

  function addStep(step: number, title: string, duration: number, afterEvents?: SSEEvent[]) {
    events.push({ delay: offset, event: { type: 'step', data: { step, total: totalSteps, title, status: 'running' } } });
    offset += duration;
    events.push({ delay: offset, event: { type: 'step_complete', data: { step, title, status: 'complete', data: {} } } });
    if (afterEvents) {
      for (const e of afterEvents) {
        offset += 50;
        events.push({ delay: offset, event: e });
      }
    }
    offset += 100;
  }

  let stepNum = 1;

  // Step 1: Load Document
  addStep(stepNum++, 'Load Document', 300);

  // Step 2: Convert to Images
  addStep(stepNum++, 'Convert to Images', 500);

  // Step 3: Neural OCR Extraction
  addStep(stepNum++, 'Neural OCR Extraction', 2000, [
    { type: 'extraction', data: { validated_data: extractedData } },
  ]);

  // Step 4: Validate Schema
  addStep(stepNum++, 'Validate Schema', 400, [
    { type: 'validation', data: { success: true, errors: [] } },
  ]);

  // Step 5: Verify Citations
  addStep(stepNum++, 'Verify Citations', 1200, [
    { type: 'citations', data: { citations: result.citations, overall_confidence: result.overall_confidence } },
  ]);

  // Step 6 (gov only): PII Scan
  if (isGov) {
    addStep(stepNum++, 'PII Scan', 600, [
      { type: 'pii', data: { findings: result.pii_report!.findings, risk_score: result.pii_report!.pii_risk_score, risk_level: result.pii_report!.risk_level } },
    ]);
  }

  // Final step: Output
  addStep(stepNum, 'Output', 200, [
    { type: 'complete', data: result },
  ]);

  // Execute the event queue
  const timers: ReturnType<typeof setTimeout>[] = [];

  for (const { delay, event } of events) {
    timers.push(
      setTimeout(() => {
        if (!cancelled) onEvent(event);
      }, delay),
    );
  }

  return () => {
    cancelled = true;
    timers.forEach(clearTimeout);
  };
}
