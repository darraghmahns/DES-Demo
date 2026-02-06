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
  extraction_timestamp: "2026-02-06T16:58:18.506944+00:00",
  model_used: "docextract-vision-v1",
  pages_processed: 3,
  dotloop_data: {
    loop_name: "Clesson E. Hill, 7032 Jenaya Court, Missoula, MT 59803",
    transaction_type: "PURCHASE_OFFER",
    transaction_status: "PRE_OFFER",
    property_address: {
      street_number: "7032",
      street_name: "Jenaya Court",
      unit_number: null,
      city: "Missoula",
      state_or_province: "MT",
      postal_code: "59803",
      country: "US",
      county: "Missoula",
      mls_number: null,
      parcel_tax_id: null,
    },
    financials: {
      purchase_price: 740000.0,
      earnest_money_amount: 10000.0,
      earnest_money_held_by: "Insured Titles",
      sale_commission_rate: null,
      sale_commission_total: null,
    },
    contract_dates: {
      contract_agreement_date: "01/06/2026",
      closing_date: "01/29/2026",
      offer_date: "01/06/2026",
      offer_expiration_date: "01/07/2026",
      inspection_date: "01/19/2026",
    },
    participants: [
      { full_name: "Clesson E. Hill", role: "BUYER", email: null, phone: null, company_name: null },
      { full_name: "Paula G. Hill", role: "BUYER", email: null, phone: null, company_name: null },
      { full_name: "Laura Berryman", role: "SELLER", email: null, phone: null, company_name: null },
      { full_name: "Jefferson Berryman", role: "SELLER", email: null, phone: null, company_name: null },
      { full_name: "Julie Gardner", role: "LISTING_AGENT", email: "juliegardnerproperties@gmail.com", phone: "406-532-9200", company_name: "ERA Lambros Real Estate Missoula" },
      { full_name: "Maggie Springer", role: "BUYING_AGENT", email: "homesmissoula@gmail.com", phone: "406-240-9545", company_name: "Ink Realty Group" },
    ],
  },
  foia_data: null,
  dotloop_api_payload: {
    name: "Clesson E. Hill, 7032 Jenaya Court, Missoula, MT 59803",
    transactionType: "PURCHASE_OFFER",
    status: "PRE_OFFER",
    loopDetails: {
      "Property Address": {
        Country: "US", "Street Number": "7032", "Street Name": "Jenaya Court",
        "Unit Number": "", City: "Missoula", "State/Prov": "MT",
        "Zip/Postal Code": "59803", County: "Missoula", "MLS Number": "", "Parcel/Tax ID": "",
      },
      Financials: {
        "Purchase/Sale Price": "740000.0", "Earnest Money Amount": "10000.0",
        "Earnest Money Held By": "Insured Titles", "Sale Commission Rate": "", "Sale Commission Total": "",
      },
      "Contract Dates": {
        "Contract Agreement Date": "01/06/2026", "Closing Date": "01/29/2026",
        "Offer Date": "01/06/2026", "Offer Expiration Date": "01/07/2026", "Inspection Date": "01/19/2026",
      },
    },
    participants: [
      { fullName: "Clesson E. Hill", role: "BUYER", email: "", Phone: "", "Company Name": "" },
      { fullName: "Paula G. Hill", role: "BUYER", email: "", Phone: "", "Company Name": "" },
      { fullName: "Laura Berryman", role: "SELLER", email: "", Phone: "", "Company Name": "" },
      { fullName: "Jefferson Berryman", role: "SELLER", email: "", Phone: "", "Company Name": "" },
      { fullName: "Julie Gardner", role: "LISTING_AGENT", email: "juliegardnerproperties@gmail.com", Phone: "406-532-9200", "Company Name": "ERA Lambros Real Estate Missoula" },
      { fullName: "Maggie Springer", role: "BUYING_AGENT", email: "homesmissoula@gmail.com", Phone: "406-240-9545", "Company Name": "Ink Realty Group" },
    ],
  },
  citations: [
    { field_name: "loop_name", extracted_value: "Clesson E. Hill, 7032 Jenaya Court, Missoula, MT 59803", page_number: 3, line_or_region: "lines 1-10", surrounding_text: "Clesson E. Hill & Paula G. Hill...7032 Jenaya Court, Missoula, MT 59803", confidence: 0.95 },
    { field_name: "transaction_type", extracted_value: "PURCHASE_OFFER", page_number: 3, line_or_region: "top of page", surrounding_text: "BUY - SELL AGREEMENT (Residential)", confidence: 0.9 },
    { field_name: "transaction_status", extracted_value: "PRE_OFFER", page_number: 1, line_or_region: "top of page", surrounding_text: "COUNTER OFFER", confidence: 0.85 },
    { field_name: "property_address.street_number", extracted_value: "7032", page_number: 1, line_or_region: "line 6", surrounding_text: "7032 Jenaya Court, Missoula, MT 59803", confidence: 0.95 },
    { field_name: "property_address.street_name", extracted_value: "Jenaya Court", page_number: 1, line_or_region: "line 6", surrounding_text: "7032 Jenaya Court, Missoula, MT 59803", confidence: 0.95 },
    { field_name: "property_address.city", extracted_value: "Missoula", page_number: 1, line_or_region: "line 6", surrounding_text: "7032 Jenaya Court, Missoula, MT 59803", confidence: 0.95 },
    { field_name: "property_address.state_or_province", extracted_value: "MT", page_number: 1, line_or_region: "line 6", surrounding_text: "7032 Jenaya Court, Missoula, MT 59803", confidence: 0.95 },
    { field_name: "property_address.postal_code", extracted_value: "59803", page_number: 1, line_or_region: "line 6", surrounding_text: "7032 Jenaya Court, Missoula, MT 59803", confidence: 0.95 },
    { field_name: "property_address.country", extracted_value: "US", page_number: 3, line_or_region: "line 8", surrounding_text: "Missoula, County of Missoula, Montana", confidence: 0.9 },
    { field_name: "property_address.county", extracted_value: "Missoula", page_number: 3, line_or_region: "line 8", surrounding_text: "Missoula, County of Missoula, Montana", confidence: 0.95 },
    { field_name: "financials.earnest_money_held_by", extracted_value: "Insured Titles", page_number: 4, line_or_region: "line 68", surrounding_text: "earnest money shall be held in trust by Insured Titles", confidence: 0.95 },
    { field_name: "contract_dates.contract_agreement_date", extracted_value: "01/06/2026", page_number: 3, line_or_region: "line 1", surrounding_text: "Date: 1/6/2026", confidence: 0.95 },
    { field_name: "contract_dates.closing_date", extracted_value: "01/29/2026", page_number: 3, line_or_region: "line 41", surrounding_text: "closing shall be (date) 1/29/2026", confidence: 0.95 },
    { field_name: "contract_dates.offer_date", extracted_value: "01/06/2026", page_number: 1, line_or_region: "line 5", surrounding_text: "Agreement dated 01/06/2026", confidence: 0.95 },
    { field_name: "contract_dates.offer_expiration_date", extracted_value: "01/07/2026", page_number: 1, line_or_region: "line 1", surrounding_text: "Date: 01/07/2026", confidence: 0.95 },
    { field_name: "contract_dates.inspection_date", extracted_value: "01/19/2026", page_number: 6, line_or_region: "line 179", surrounding_text: "Inspection date 1/19/2026", confidence: 0.95 },
    { field_name: "participants[0].full_name", extracted_value: "Clesson E. Hill", page_number: 3, line_or_region: "line 2", surrounding_text: "Clesson E. Hill & Paula G. Hill", confidence: 0.95 },
    { field_name: "participants[0].role", extracted_value: "BUYER", page_number: 3, line_or_region: "line 2", surrounding_text: "hereafter the 'Buyer'", confidence: 0.95 },
    { field_name: "participants[1].full_name", extracted_value: "Paula G. Hill", page_number: 3, line_or_region: "line 2", surrounding_text: "Clesson E. Hill & Paula G. Hill", confidence: 0.95 },
    { field_name: "participants[1].role", extracted_value: "BUYER", page_number: 3, line_or_region: "line 2", surrounding_text: "hereafter the 'Buyer'", confidence: 0.95 },
    { field_name: "participants[2].full_name", extracted_value: "Laura Berryman", page_number: 1, line_or_region: "line 4", surrounding_text: "between Laura Berryman and Jefferson Berryman", confidence: 0.95 },
    { field_name: "participants[2].role", extracted_value: "SELLER", page_number: 1, line_or_region: "line 4", surrounding_text: "hereafter the 'Seller'", confidence: 0.95 },
    { field_name: "participants[3].full_name", extracted_value: "Jefferson Berryman", page_number: 1, line_or_region: "line 4", surrounding_text: "between Laura Berryman and Jefferson Berryman", confidence: 0.95 },
    { field_name: "participants[3].role", extracted_value: "SELLER", page_number: 1, line_or_region: "line 4", surrounding_text: "hereafter the 'Seller'", confidence: 0.95 },
    { field_name: "participants[4].full_name", extracted_value: "Julie Gardner", page_number: 12, line_or_region: "line 520", surrounding_text: "Julie Gardner of ERA Lambros Real Estate Missoula", confidence: 0.95 },
    { field_name: "participants[4].role", extracted_value: "LISTING_AGENT", page_number: 12, line_or_region: "line 531", surrounding_text: "is acting as Seller's Agent", confidence: 0.95 },
    { field_name: "participants[4].email", extracted_value: "juliegardnerproperties@gmail.com", page_number: 12, line_or_region: "line 528", surrounding_text: "juliegardnerproperties@gmail.com", confidence: 0.95 },
    { field_name: "participants[4].phone", extracted_value: "406-532-9200", page_number: 12, line_or_region: "line 526", surrounding_text: "406-532-9200", confidence: 0.95 },
    { field_name: "participants[4].company_name", extracted_value: "ERA Lambros Real Estate Missoula", page_number: 12, line_or_region: "line 521", surrounding_text: "ERA Lambros Real Estate Missoula", confidence: 0.95 },
    { field_name: "participants[5].full_name", extracted_value: "Maggie Springer", page_number: 12, line_or_region: "line 533", surrounding_text: "Maggie Springer of Ink Realty Group", confidence: 0.95 },
    { field_name: "participants[5].role", extracted_value: "BUYING_AGENT", page_number: 12, line_or_region: "line 544", surrounding_text: "is acting as Buyer's Agent", confidence: 0.95 },
    { field_name: "participants[5].email", extracted_value: "homesmissoula@gmail.com", page_number: 12, line_or_region: "line 542", surrounding_text: "homesmissoula@gmail.com", confidence: 0.95 },
    { field_name: "participants[5].phone", extracted_value: "406-240-9545", page_number: 12, line_or_region: "line 540", surrounding_text: "406-240-9545", confidence: 0.95 },
    { field_name: "participants[5].company_name", extracted_value: "Ink Realty Group", page_number: 12, line_or_region: "line 535", surrounding_text: "Ink Realty Group", confidence: 0.95 },
  ],
  overall_confidence: 0.9441176470588236,
  pii_report: null,
};

const GOV_RESULT: ExtractionResult = {
  mode: "gov",
  source_file: "sample_foia_request.pdf",
  extraction_timestamp: "2026-02-06T19:10:56.762827+00:00",
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
