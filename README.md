# D.E.S. (Data Entry Sucks)

AI-powered document intelligence for real estate and government workflows. Extracts structured JSON from PDFs, validates against strict Pydantic schemas, verifies every field with source citations, enriches with public parcel data, runs jurisdiction-aware compliance checks, and syncs with Dotloop and DocuSign.

---

## Why This Exists

Data entry in real estate is brutal. Agents, title companies, and transaction coordinators spend hours manually keying property details, financials, and participant info from purchase agreements into platforms like Dotloop. Government agencies face the same pain processing FOIA requests. D.E.S. automates the entire pipeline: upload a PDF, get validated structured data back in seconds, with every extracted field cited back to its source location in the document.

---

## Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.12+, FastAPI, Pydantic v2, Beanie ODM |
| **AI/ML** | OpenAI GPT-4o Vision (neural OCR), Ollama + Docling (local alternative) |
| **Frontend** | React 18, TypeScript, Vite, Clerk (auth) |
| **Database** | MongoDB (Motor async driver + Beanie ODM) |
| **PDF Processing** | poppler (pdf2image), Pillow, ReportLab |
| **Integrations** | Dotloop (OAuth2), DocuSign (JWT + OAuth2), Regrid (parcel data), Clerk (auth) |

---

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 18+
- MongoDB (local or [Atlas](https://www.mongodb.com/atlas))
- poppler (`brew install poppler` on macOS)
- An OpenAI API key

### 1. Clone and set up the backend

```bash
cd backend
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

Create a `.env` file in the project root:

```bash
# ── Required ──────────────────────────────────────────
OPENAI_API_KEY=sk-...
ENGINE=openai                          # "openai" or "local"

# ── MongoDB ───────────────────────────────────────────
MONGODB_URI=mongodb://localhost:27017   # or Atlas connection string
MONGODB_DB=des

# ── CORS (comma-separated origins) ───────────────────
CORS_ORIGINS=http://localhost:5173

# ── Clerk Auth (optional — disabled if unset) ────────
CLERK_SECRET_KEY=
CLERK_JWKS_URL=

# ── Dotloop (optional) ───────────────────────────────
DOTLOOP_CLIENT_ID=
DOTLOOP_CLIENT_SECRET=
DOTLOOP_API_TOKEN=
DOTLOOP_REFRESH_TOKEN=
DOTLOOP_PROFILE_ID=

# ── DocuSign (optional) ──────────────────────────────
DOCUSIGN_CLIENT_ID=
DOCUSIGN_CLIENT_SECRET=
DOCUSIGN_ACCOUNT_ID=
DOCUSIGN_USER_ID=
DOCUSIGN_AUTH_SERVER=account-d.docusign.com
DOCUSIGN_BASE_URL=https://demo.docusign.net/restapi

# ── Regrid / Property Enrichment (optional) ──────────
REGRID_API_KEY=

# ── Local Engine (optional) ──────────────────────────
OLLAMA_MODEL=qwen3:4b
OLLAMA_HOST=http://localhost:11434
```

### 3. Set up the frontend

```bash
cd frontend
npm install
```

Create `frontend/.env`:

```bash
VITE_CLERK_PUBLISHABLE_KEY=pk_test_...
VITE_API_BASE=http://localhost:8000     # points to backend
```

### 4. Run

```bash
# Terminal 1 — Backend (from backend/)
source venv/bin/activate
python server.py                        # FastAPI on http://localhost:8000

# Terminal 2 — Frontend (from frontend/)
npm run dev                             # Vite on http://localhost:5173
```

Open http://localhost:5173, upload a PDF, and watch the extraction pipeline run in real time.

### CLI Mode

```bash
cd backend
python processor.py --mode real_estate --input test_docs/sample_purchase_agreement.pdf
python processor.py --mode gov --input test_docs/sample_foia_request.pdf
```

---

## Modes

### Real Estate
Extracts from purchase agreements:
- **Property address** (street, city, state, ZIP, county, MLS#, parcel/tax ID)
- **Financials** (purchase price, earnest money, commission rate)
- **Contract dates** (agreement, closing, offer, expiration, inspection)
- **Participants** (buyers, sellers, agents, brokers with roles, emails, phones)

Output is Dotloop-compatible via `to_dotloop_api_format()`. Includes jurisdiction-aware compliance checking (JACE engine) and property enrichment via Regrid parcel data.

### Government
Extracts FOIA request fields:
- Requester info (name, email, phone, address, organization)
- Request details (description, category, agency, date ranges, fees)

Includes regex-based PII scanning (SSN, phone, email, driver's license) with risk scoring.

---

## Project Structure

```
DES-Demo/
├── .github/workflows/ci.yml        GitHub Actions (pytest + frontend build)
├── .env                             Shared environment config
├── README.md
│
├── backend/                         FastAPI backend (port 8000)
│   ├── server.py                    Entry point — SSE streaming, REST API, OAuth
│   ├── schemas.py                   Pydantic models (20+ models, 6 enums)
│   ├── pdf_converter.py             PDF -> base64 PNG images (poppler)
│   ├── task_manager.py              Background task tracking (survives disconnects)
│   │
│   ├── ocr_engine.py                Abstract OCREngine base class + factory
│   ├── openai_engine.py             GPT-4o Vision engine (cloud, default)
│   ├── local_engine.py              Docling + Ollama engine (self-hosted)
│   ├── extractor.py                 Extraction prompts + GPT-4o logic
│   ├── verifier.py                  Citation verification (2nd LLM pass)
│   │
│   ├── compliance_engine.py         JACE — Jurisdiction-Aware Compliance Engine
│   ├── scout.py                     AI Scout: GPT-4o jurisdiction research
│   ├── scout_models.py              Scout MongoDB models
│   ├── scout_cli.py                 Scout CLI with Rich UI
│   │
│   ├── cadastral_client.py          Regrid API client (parcel lookups)
│   ├── property_prefill.py          Property enrichment orchestrator
│   ├── comparison_engine.py         Multi-offer field-by-field comparison
│   ├── pii_scanner.py               Regex PII detection + risk scoring
│   │
│   ├── dotloop_client.py            Dotloop v2 API wrapper
│   ├── dotloop_connector.py         Dotloop sync orchestrator
│   ├── dotloop_oauth.py             Dotloop OAuth2 flow
│   ├── docusign_client.py           DocuSign API wrapper (JWT auth)
│   ├── docusign_connector.py        DocuSign sync orchestrator
│   ├── docusign_oauth.py            DocuSign OAuth2 + JWT flow
│   │
│   ├── auth.py                      Clerk JWT verification
│   ├── db.py                        Beanie ODM models + MongoDB init
│   ├── db_writer.py                 Async persistence helpers
│   │
│   ├── processor.py                 CLI entry point
│   ├── terminal_ui.py               Rich terminal UI components
│   ├── generate_mocks.py            Test PDF generator (ReportLab)
│   │
│   ├── test_docs/                   7 sample PDFs (real estate + FOIA)
│   ├── tests/                       pytest suite (scout, cache, dotloop)
│   ├── dist/                        Extraction output JSON
│   │
│   ├── Dockerfile                   Python 3.12-slim + poppler
│   ├── render.yaml                  Render.com deployment config
│   ├── requirements.txt             Dev dependencies (includes docling, ollama)
│   └── requirements-prod.txt        Production dependencies
│
└── frontend/                        React + Vite app (port 5173)
    ├── src/
    │   ├── App.tsx                   Main component (SSE consumer, tabbed UI)
    │   ├── api.ts                    TypeScript API client + event types
    │   ├── App.css                   Dark terminal-inspired theme
    │   └── main.tsx                  React DOM mount
    ├── .env                          Clerk publishable key + API base URL
    ├── package.json                  React 18, Clerk, Vite 6
    └── vite.config.ts               Vite configuration
```

---

## Extraction Pipeline (8 Steps)

```
PDF Upload
    |
    v
1. LOAD DOCUMENT ----------- Validate PDF, get page count + file size
    |
    v
2. CONVERT TO IMAGES ------- Render pages at 200 DPI via poppler -> base64 PNG
    |
    v
3. NEURAL OCR EXTRACTION --- GPT-4o Vision extracts structured JSON (temp=0.0)
    |
    v
4. VALIDATE SCHEMA --------- Pydantic strict validation (with lenient fallback)
    |
    v
5. VERIFY CITATIONS -------- 2nd GPT-4o pass: cite page, line, surrounding text
    |                          for every extracted field (confidence 0.0-1.0)
    v
6. PROPERTY ENRICHMENT ----- [real_estate] Regrid API: parcel data, assessed
    |                          value, year built, zoning, lot size, owner
    v
7a. COMPLIANCE CHECK ------- [real_estate] JACE engine: jurisdiction lookup +
    |                          seeded rules + AI Scout DB cascade
    |
7b. PII SCAN --------------- [gov] Regex detection: SSN, phone, email,
    |                          driver's license -> risk score 0-100
    v
8. OUTPUT ------------------ Stream SSE events to frontend, persist to MongoDB
```

All steps stream to the frontend in real-time via Server-Sent Events (SSE).

---

## Architecture

### Pluggable OCR Engines

```
ocr_engine.py (ABC)           get_engine() factory
    |                               |
    +-- openai_engine.py       GPT-4o Vision (cloud, default)
    |                          - Sends base64 images to OpenAI API
    |                          - response_format="json_object"
    |
    +-- local_engine.py        Docling + Ollama (self-hosted)
                               - Converts PDF -> Markdown via Docling
                               - Sends markdown to local LLM (qwen3:4b)
                               - Native PDF parsing (tables, layout, reading order)
```

Set via `ENGINE` env var (`openai` or `local`).

### Two-Pass LLM Design

1. **Extract** (extractor.py) — GPT-4o reads the document and produces structured JSON matching the target schema. Temperature 0.0 for determinism.
2. **Verify** (verifier.py) — A separate GPT-4o call receives the document AND the extracted data, then must cite the exact page number, line/region, and surrounding text for every field. Each citation gets a confidence score (0.0-1.0).

### Integration Architecture (3-Layer Pattern)

Each external integration follows the same structure:

```
*_client.py            Layer 1: Raw HTTP API wrapper
    |                  - Auth headers, error handling, rate limits
    v
*_connector.py         Layer 2: Business logic orchestrator
    |                  - sync_to_*(), OAuth token management
    v
server.py endpoints    Layer 3: FastAPI routes
                       - /api/*/status, /oauth/connect, /sync/{id}
```

Currently implemented for **Dotloop** and **DocuSign**.

### Property Enrichment (Regrid)

After extraction, the property address is looked up against the Regrid parcel database:

```
Extracted address -> cadastral_client.py -> Regrid API v2
                                               |
                                    Returns: parcel ID, assessed value,
                                    year built, lot size, zoning, owner
```

State names are auto-normalized (e.g., "Texas" -> "TX") before the API call.

### Compliance Engine (JACE)

**J**urisdiction-**A**ware **C**ompliance **E**ngine resolves property addresses to compliance requirements via a cascade: city -> county -> state. Combines hardcoded seed rules with AI Scout-discovered rules (GPT-4o research + verification, human-in-the-loop activation).

### Authentication

Clerk JWT-based auth with JWKS validation. Disabled gracefully if `CLERK_SECRET_KEY` is not set, allowing local development without auth.

---

## API Endpoints

### Core
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/documents` | List available PDFs |
| GET | `/api/documents/{name}` | Serve PDF for preview |
| POST | `/api/upload` | Upload a PDF |
| POST | `/api/extract` | Run extraction pipeline (SSE stream) |
| GET | `/api/usage` | Token usage statistics |

### Property Enrichment
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/property/lookup` | Manual parcel lookup by address or APN |

### Compliance
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/compliance/{ref}` | Compliance report for extraction |
| GET | `/api/compliance-check` | Standalone check by jurisdiction |

### AI Scout
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/scout/research` | GPT-4o jurisdiction research |
| GET | `/api/scout/results` | List scout results |
| PUT | `/api/scout/results/{id}/verify` | Verify + activate result |
| PUT | `/api/scout/results/{id}/reject` | Reject result |

### Dotloop
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/dotloop/status` | Connection status |
| GET | `/api/dotloop/loops` | List recent loops |
| POST | `/api/dotloop/sync/{id}` | Push extraction to Dotloop |
| GET | `/api/dotloop/oauth/connect` | Start OAuth2 flow |
| GET | `/api/dotloop/oauth/callback` | OAuth2 callback |

### DocuSign
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/docusign/status` | Connection status |
| POST | `/api/docusign/sync/{id}` | Push extraction to DocuSign |
| GET | `/api/docusign/oauth/connect` | Start OAuth2 flow |
| GET | `/api/docusign/oauth/callback` | OAuth2 callback |

---

## Testing

```bash
cd backend

# Run all tests
pytest tests/ -v

# Scout tests
pytest tests/test_scout.py -v

# Dotloop tests
pytest test_dotloop.py -v
```

---

## Deployment

### Backend (Render.com)

The backend deploys as a Docker container via `backend/render.yaml`. Environment variables are configured in the Render dashboard.

### Frontend (Netlify)

The frontend builds as a static site. Live demo: [des.darraghmahns.com](https://des.darraghmahns.com)

```bash
cd frontend
npm run build    # outputs to frontend/dist/
```

---

## Branches

- `main` — production baseline
- `demo` — frozen snapshot for des.darraghmahns.com
- `dev` — development trunk
- `darragh` — active feature branch (off dev)
- `varun` — DocuSign integration
