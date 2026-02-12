# D.E.S. (Data Entry Sucks)

AI-powered document intelligence for real estate and government workflows. Extracts structured JSON from PDFs using GPT-4o Vision, validates against strict Pydantic schemas, verifies every field with source citations, runs jurisdiction-aware compliance checks, and syncs bidirectionally with Dotloop.

---

## Why This Exists

Data entry in real estate is brutal. Agents, title companies, and transaction coordinators spend hours manually keying property details, financials, and participant info from purchase agreements into platforms like Dotloop. Government agencies face the same pain processing FOIA requests. D.E.S. automates the entire pipeline: upload a PDF, get validated structured data back in seconds, with every extracted field cited back to its source location in the document.

---

## Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.12+, FastAPI, Pydantic v2, Beanie ODM |
| **AI/ML** | OpenAI GPT-4o Vision (neural OCR), Ollama + Docling (local alternative) |
| **Frontend** | React 18, TypeScript, Vite |
| **Database** | MongoDB (via Motor async driver + Beanie ODM) |
| **PDF Processing** | poppler (pdf2image), Pillow, ReportLab |
| **Integrations** | Dotloop v2 API (OAuth2, bidirectional sync, webhooks) |

---

## Modes

### Real Estate
Extracts from purchase agreements:
- **Property address** (street, city, state, ZIP, county, MLS#, parcel/tax ID)
- **Financials** (purchase price, earnest money, commission rate)
- **Contract dates** (agreement, closing, offer, expiration, inspection)
- **Participants** (buyers, sellers, agents, brokers with roles, emails, phones)

Output is Dotloop-compatible via `to_dotloop_api_format()`. Includes jurisdiction-aware compliance checking (JACE engine).

### Government
Extracts FOIA request fields:
- Requester info (name, email, phone, address, organization)
- Request details (description, category, agency, date ranges, fees)

Includes regex-based PII scanning (SSN, phone, email) with risk scoring (0-100).

---

## Project Structure

```
D.E.S./
|
|-- CORE PIPELINE
|   server.py                 FastAPI backend (SSE streaming, REST API, OAuth)
|   processor.py              CLI entry point (batch processing with Rich UI)
|   schemas.py                All Pydantic models (20+ models, 6 enums)
|   pdf_converter.py          PDF -> base64 images (poppler)
|
|-- EXTRACTION ENGINES
|   ocr_engine.py             Abstract base class + factory (get_engine())
|   openai_engine.py          GPT-4o Vision implementation
|   local_engine.py           Docling + Ollama implementation (offline capable)
|   extractor.py              GPT-4o extraction prompts and logic
|   verifier.py               Citation verification (2nd LLM pass)
|
|-- COMPLIANCE (JACE Engine)
|   compliance_engine.py      Jurisdiction-Aware Compliance Engine
|   scout.py                  AI Scout: GPT-4o research + verify pipeline
|   scout_models.py           MongoDB models for scout results
|   scout_cli.py              Rich terminal UI for scout research
|
|-- INTEGRATIONS (3-Layer Pattern)
|   dotloop_client.py         Low-level Dotloop v2 API wrapper
|   dotloop_connector.py      High-level orchestrator (sync, pull, webhooks)
|   dotloop_oauth.py          OAuth2 browser flow for token exchange
|
|-- DATA LAYER
|   db.py                     Beanie ODM models + MongoDB init
|   db_writer.py              Async persistence helpers
|
|-- SCANNING
|   pii_scanner.py            Regex PII detection (SSN, phone, email)
|
|-- FRONTEND
|   frontend/src/App.tsx      Main React component (SSE consumer, tabbed UI)
|   frontend/src/api.ts       TypeScript API client + types
|   frontend/src/App.css      Dark-theme styling (1200+ lines)
|
|-- UTILITIES
|   terminal_ui.py            Rich terminal UI components for CLI
|   generate_mocks.py         Test PDF generator (ReportLab)
|
|-- TESTS
|   tests/test_scout.py       680+ lines: unit, integration, API, model tests
|   tests/conftest.py         Fixtures (mock OpenAI, mock Beanie, sample data)
|   test_dotloop.py           Dotloop client tests
|
|-- DOCUMENTS
|   test_docs/                Sample PDFs (purchase agreement, FOIA, multi-doc)
|   dist/                     Extraction output JSON files
```

---

## Extraction Pipeline (7 Steps)

```
PDF Upload
    |
    v
1. LOAD DOCUMENT ---------- Validate PDF, get page count + file size
    |
    v
2. CONVERT TO IMAGES ------ Render pages at 200 DPI via poppler -> base64 PNG
    |
    v
3. NEURAL OCR EXTRACTION -- GPT-4o Vision extracts structured JSON (temp=0.0)
    |
    v
4. VALIDATE SCHEMA -------- Pydantic strict validation (with lenient fallback)
    |
    v
5. VERIFY CITATIONS ------- 2nd GPT-4o pass: cite page, line, surrounding text
    |                         for every extracted field (confidence 0.0-1.0)
    v
6a. COMPLIANCE CHECK ------ [real_estate] JACE engine: jurisdiction lookup +
    |                         seeded rules + AI Scout DB cascade
    |
6b. PII SCAN -------------- [gov] Regex detection: SSN (40pts), phone (15pts),
    |                         email (10pts) -> risk score 0-100
    v
7. OUTPUT ----------------- Write JSON to dist/, stream SSE events to frontend,
                              persist to MongoDB
```

All steps stream to the frontend in real-time via Server-Sent Events (SSE).

---

## Architecture Deep Dive

### Pluggable OCR Engines

The extraction engine is abstracted behind `OCREngine` (in `ocr_engine.py`):

```
ocr_engine.py (ABC)          get_engine() factory
    |                              |
    +-- openai_engine.py      GPT-4o Vision (cloud, default)
    |                         - Sends base64 images to OpenAI API
    |                         - response_format="json_object"
    |
    +-- local_engine.py       Docling + Ollama (self-hosted)
                              - Converts PDF -> Markdown via Docling
                              - Sends markdown to local LLM (qwen3:4b)
                              - prefers_file_path=True (native PDF parsing)
```

Set via `ENGINE` env var (`openai` or `local`).

### Two-Pass LLM Design

D.E.S. uses a deliberate two-pass approach for trustworthy extraction:

1. **Extract** (extractor.py) -- GPT-4o reads the document and produces structured JSON matching the target schema. Temperature 0.0 for determinism.
2. **Verify** (verifier.py) -- A separate GPT-4o call receives the document AND the extracted data, then must cite the exact page number, line/region, and surrounding text for every field. Each citation gets a confidence score (0.0-1.0).

This same pattern is used by AI Scout (research pass + verify pass).

### Compliance Engine (JACE)

**J**urisdiction-**A**ware **C**ompliance **E**ngine resolves property addresses to compliance requirements:

```
Address -> resolve_jurisdiction() -> "MT:Lewis And Clark:Helena"
                                          |
                              async_lookup_requirements()
                                     |          |
                                  MongoDB    SEED_RULES
                               (AI Scout)    (hardcoded)
                                     |          |
                                     v          v
                              Cascade: city -> county -> state
```

**Seed Rules** cover demo jurisdictions: Helena MT, Missoula MT (city vs county), LA City (9A Report), LA County.

**AI Scout** discovers new jurisdictions via GPT-4o:
1. Research pass: "What compliance requirements exist for real estate in {jurisdiction}?"
2. Verify pass: Cross-check each requirement, assign confidence, remove hallucinations (<0.5)
3. Save to MongoDB with `is_verified=False, is_active=False`
4. Human reviews via API -> flips to active -> picked up by compliance engine

### Integration Architecture (3-Layer Pattern)

```
dotloop_client.py         Layer 1: Raw HTTP API wrapper
    |                     - Auth headers, error handling, rate limits
    |                     - Auto token refresh on 401
    v
dotloop_connector.py      Layer 2: Business logic orchestrator
    |                     - sync_to_dotloop(), process_from_dotloop()
    |                     - OAuth token management, webhook handling
    v
server.py endpoints       Layer 3: FastAPI routes
                          - /api/dotloop/status, /oauth/connect, /sync/{id}
```

To add a new integration (e.g., DocuSign), replicate this pattern:
1. `docusign_client.py` -- raw API wrapper
2. `docusign_connector.py` -- orchestrator with `is_configured()`, `sync_to_docusign()`
3. Add routes to `server.py`
4. Add `to_docusign_format()` to schema models

### Data Model (MongoDB)

```
documents (collection)
  |-- filename, source, mode, page_count, file_size_bytes
  |-- extractions[] (embedded array)
        |-- engine, model_used, mode
        |-- extracted_data (raw JSON)
        |-- dotloop_api_payload
        |-- validation_success, validation_errors[]
        |-- overall_confidence
        |-- citations[] (VerificationCitation)
        |-- pii_report (PIIReport)
        |-- compliance_report (ComplianceReport)
        |-- duration_ms, timestamps

compliance_rules (collection) -- AI Scout results
  |-- state, county, city, jurisdiction_key, jurisdiction_type
  |-- requirements[] (ScoutRequirement with confidence scores)
  |-- is_verified, is_active, verified_by
  |-- source ("ai_scout"), model_used, timestamps
```

Extraction references use composite keys: `doc_id:index` (e.g., `507f1f77bcf86cd799439011:0`).

---

## Frontend

Single-page React app with a dark terminal-inspired theme:

- **Left panel**: Document picker + inline PDF preview
- **Right panel**: Pipeline progress steps + tabbed results
- **Tabs**: Extraction Data | Citations | Compliance | PII | Raw JSON
- **Dotloop section**: OAuth connect button, loop selector, sync status
- **SSE streaming**: Real-time step-by-step progress as extraction runs
- **Mobile responsive**: Stacked layout on tablet/phone

The frontend consumes the `/api/extract` SSE stream and renders each event type:
`step`, `step_complete`, `extraction`, `validation`, `citations`, `compliance`, `pii`, `complete`, `error`

---

## Setup

### Prerequisites

- Python 3.12+
- Node.js 18+
- MongoDB (local or Atlas)
- poppler (`brew install poppler` on macOS)

### Backend

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Environment

Create `.env`:

```bash
# Required
OPENAI_API_KEY=your-key-here
ENGINE=openai                    # "openai" or "local"

# MongoDB (defaults shown)
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=des

# Dotloop (optional)
DOTLOOP_CLIENT_ID=
DOTLOOP_CLIENT_SECRET=
DOTLOOP_API_TOKEN=
DOTLOOP_PROFILE_ID=

# Local engine (optional)
OLLAMA_MODEL=qwen3:4b
OLLAMA_HOST=http://localhost:11434
```

### Run

```bash
# Terminal 1 - Backend
source venv/bin/activate
python server.py                 # FastAPI on :8000

# Terminal 2 - Frontend
cd frontend && npm install && npm run dev    # Vite on :5173
```

### CLI

```bash
python processor.py --mode real_estate --input test_docs/sample_purchase_agreement.pdf
python processor.py --mode gov --input test_docs/sample_foia_request.pdf
```

### AI Scout CLI

```bash
python scout_cli.py --state MT --city Helena --county "Lewis And Clark"
python scout_cli.py --state CA --city "San Francisco" --county "San Francisco"
```

---

## API Endpoints

### Core
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/documents` | List available PDFs in test_docs/ |
| GET | `/api/documents/{name}` | Serve PDF for inline preview |
| POST | `/api/upload` | Upload a PDF (multipart) |
| POST | `/api/extract` | Run extraction pipeline (SSE stream) |

### Compliance
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/compliance/{ref}` | Get compliance report for extraction |
| GET | `/api/compliance-check` | Standalone compliance check by jurisdiction |

### AI Scout
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/scout/research` | Trigger GPT-4o research for jurisdiction |
| GET | `/api/scout/results` | List scout results (filter by state/verified) |
| GET | `/api/scout/results/{id}` | Get full scout result with requirements |
| PUT | `/api/scout/results/{id}/verify` | Mark result as verified + active |
| PUT | `/api/scout/results/{id}/reject` | Mark result as rejected |

### Dotloop
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/dotloop/status` | Check if Dotloop is configured |
| GET | `/api/dotloop/loops` | List recent Dotloop loops |
| POST | `/api/dotloop/sync/{extraction_id}` | Push extraction to Dotloop |
| POST | `/api/dotloop/process/{loop_id}` | Pull PDF from Dotloop + extract |
| GET | `/api/dotloop/oauth/connect` | Start OAuth2 browser flow |
| GET | `/api/dotloop/oauth/callback` | OAuth2 callback handler |
| POST | `/api/webhooks/dotloop` | Receive LOOP_UPDATED webhooks |

---

## Key Design Decisions

1. **Two-pass extraction** over single-pass: The verification pass catches hallucinations and provides audit trail. Every field has a cited source.

2. **Pluggable engines** over hardcoded OpenAI: The `OCREngine` ABC allows swapping between cloud (GPT-4o) and local (Docling + Ollama) without changing the pipeline.

3. **SSE streaming** over request-response: Multi-step extraction takes 30-60s. SSE lets the frontend show real-time progress instead of a spinner.

4. **MongoDB embedded documents** over normalized tables: Each document contains its extraction history as an embedded array. Simpler queries, atomic updates, no joins.

5. **Jurisdiction cascade** (city -> county -> state): Real estate compliance varies dramatically by locality. Helena MT requires a Water Rights Certificate; Missoula City requires "Connect on Sale" for sewer; unincorporated Missoula County does not.

6. **AI Scout with human-in-the-loop**: LLM-discovered compliance rules start as `is_active=false`. A human must verify and activate them before they affect production compliance checks.

7. **3-layer integration pattern**: Separating raw API client from business orchestrator from route handler keeps each layer testable and replaceable independently.

---

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run scout tests only
pytest tests/test_scout.py -v

# Run dotloop tests
pytest test_dotloop.py -v
```

Test suite covers:
- **Unit**: Jurisdiction resolution, rule lookup cascades, model parsing
- **Integration**: Mocked OpenAI + Beanie for full scout pipeline
- **API**: FastAPI test client against all scout endpoints
- **Model validation**: Pydantic constraint enforcement

---

## Branches

- `main` -- production baseline
- `demo` -- frozen snapshot (des.darraghmahns.com)
- `dev` -- development trunk
- `darragh` -- local OCR engine (Docling + Ollama)
- `varun` -- DocuSign integration
