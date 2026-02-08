# D.E.S. (Data Entry Sucks)

AI-powered document intelligence for real estate and government workflows. Extracts structured JSON from PDFs using GPT-4o Vision, validates against strict schemas, verifies every field with source citations, and syncs to third-party platforms.

## Stack

- **Backend**: Python, FastAPI, Pydantic v2, OpenAI GPT-4o Vision
- **Frontend**: React, Vite, TypeScript
- **Database**: PostgreSQL 15, SQLAlchemy 2.0, Alembic

## Modes

- **Real Estate** -- Extracts property address, financials, contract dates, and participants from purchase agreements. Output is Dotloop-compatible. DocuSign integration is next.
- **Government** -- Extracts FOIA request fields (requester info, agency, date ranges, etc.) and runs a PII scan with risk scoring.

## Project Structure

```
server.py             FastAPI backend (SSE extraction pipeline + sync endpoints)
processor.py          CLI entry point
schemas.py            Pydantic models (DotloopLoopDetails, FOIARequest, ExtractionResult, etc.)
extractor.py          GPT-4o Vision extraction calls
verifier.py           Citation verification pass
pdf_converter.py      PDF to images (poppler)
pii_scanner.py        Regex-based PII detection (gov mode)
terminal_ui.py        Rich terminal UI for CLI
frontend/             React/Vite/TypeScript frontend
test_docs/            Sample PDFs for testing
dist/                 Extraction output JSON files
```

## Setup

### Prerequisites

- Python 3.12+
- Node.js 18+
- PostgreSQL 15
- poppler (`brew install poppler` on macOS)

### Backend

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create `.env` with:

```
OPENAI_API_KEY=your-key-here
DATABASE_URL=postgresql://localhost/des
ENGINE=openai
```

Run:

```bash
python server.py   # FastAPI on :8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev         # Vite dev server on :5173
```

### CLI

```bash
python processor.py --mode real_estate --input test_docs/sample_purchase_agreement.pdf
python processor.py --mode gov --input test_docs/sample_foia_request.pdf
```

## Extraction Pipeline

1. **Load Document** -- validate PDF input
2. **Convert to Images** -- render pages via poppler
3. **Neural OCR Extraction** -- GPT-4o Vision extracts structured JSON
4. **Validate Schema** -- Pydantic validates against mode-specific schema
5. **Verify Citations** -- GPT-4o verifies each extracted value has a source location
6. **PII Scan** (gov mode only) -- regex-based detection of SSN, phone, email
7. **Output** -- write JSON to `dist/`, stream results via SSE

## Integration Architecture

Third-party integrations (Dotloop, DocuSign, etc.) follow a 3-layer pattern:

1. **`*_client.py`** -- Low-level API wrapper. HTTP calls, auth headers, error handling. No business logic.
2. **`*_connector.py`** -- High-level orchestrator. Takes extraction results, calls the client, manages OAuth tokens, exposes `is_configured()` and `sync_to_*()`.
3. **`server.py` endpoints** -- FastAPI routes for `/api/{service}/status`, `/api/{service}/oauth/*`, `/api/{service}/sync/{extraction_id}`.

### Adding a New Integration

Follow the Dotloop pattern:
- Create `{service}_client.py` with raw API methods
- Create `{service}_connector.py` with `is_configured()`, `set_oauth_tokens()`, `sync_to_{service}()`
- Add endpoints to `server.py`
- Add any new Pydantic models or `to_{service}_format()` methods to `schemas.py`
- Add env vars for credentials

## Branches

- `main` -- production baseline
- `demo` -- frozen snapshot for des.darraghmahns.com
- `dev` -- development trunk
- `darragh` -- local OCR engine feature (Docling + Ollama)
- `varun` -- DocuSign integration
