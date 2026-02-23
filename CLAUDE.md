# DES-Demo — Claude Code Project Context

## What This Is
D.E.S. (Data Entry Sucks) — a real estate transaction management platform.
- **Frontend**: React + Vite + TypeScript (port 5173)
- **Backend**: FastAPI + Beanie/MongoDB (port 8000)
- **Auth**: Clerk (production), bypassed in dev mode (`AUTH_ENABLED=false`)
- **OCR/Extraction**: OpenAI GPT-4o Vision
- **Integrations**: Dotloop, DocuSign (OAuth2)
- **Deployment**: Render (Docker backend + static frontend)

## Key URLs
- Frontend (prod): https://des-demo-frontend.onrender.com
- Backend API (prod): https://des-demo-api.onrender.com
- GitHub: https://github.com/darraghmahns/DES-Demo

## Branch Strategy
- `main` — main development branch
- `prod` — production deployment branch (Render auto-deploys from this)
- `VarunPhases` — feature branch for phased development
- `darragh` — Darragh's feature branch

## Architectural Decisions Log

### Phase 4.5: E2E Testing (Playwright)
- **Decision**: Use Playwright with sequential tests, 1 worker, Chromium only
- **Auth bypass for E2E**: Empty `VITE_CLERK_PUBLISHABLE_KEY` bypasses ProtectedRoute; `AUTH_ENABLED=false` returns dev user on backend
- **Test data**: Each test creates its own data; `cleanupDocuments()` / `cleanupTransactions()` in `beforeAll` prevent interference from seed data
- **Chat test**: Skips gracefully if no `OPENAI_API_KEY`

### Phase 5: Demo Seed Data
- **Decision**: New `seed_demo.py` script (separate from `seed_test_user.py` test harness)
- **No external API deps**: All extraction results are pre-computed JSON fixtures (no OpenAI calls)
- **Demo data identification**: `@deslabs.local` email domain + `description: "Demo — sample data"` on UserDocuments
- **Scope**: 1 primary user (agent+buyer), 3 secondary users, 7 profile docs, 4 transactions (Draft/Active/Under Contract/Closed), 3 extraction records
- **Extractions look real**: Realistic timestamps, token counts, duration_ms, confidence scores — indistinguishable from real pipeline output
- **Integrations**: NOT mocked — DocuSign/Dotloop show "Ready to Connect" (copy improvement from "Not Connected"). Real connections need real accounts.
- **DRY**: Extraction fixtures are inlined per-script (seed_demo.py vs seed_test_user.py). Different purposes = no shared fixture module.
- **Phase 2 follow-up**: Demo login via magic links ("Try Demo" button on Login page, bypasses Clerk for @deslabs.local accounts)

### Backend Bug Fixes
- **Invitation validate 500**: `TypeError: can't compare offset-naive and offset-aware datetimes` — MongoDB strips timezone info from stored datetimes. Fixed with `.replace(tzinfo=timezone.utc)` in `invitation_routes.py:174` and `auth.py:325`
- **Profile doc upload response format**: Backend returned flat dict for new uploads but frontend expected `{ document: {...}, duplicate: false }`. Fixed in `profile_doc_routes.py`

## Dev Mode Conventions
- Dev user: `dev@deslabs.local` (created automatically when `AUTH_ENABLED=false`)
- Demo users: `*@deslabs.local` email pattern
- Sample PDFs: Run `python generate_test_docs.py` to create 9 financial docs in `test_docs/financial/`
- Real estate test docs: 4 purchase agreements in `test_docs/`

## User Preferences
- DRY is important — flag repetition aggressively
- Well-tested code is non-negotiable
- "Engineered enough" — not under or over-engineered
- Handle more edge cases, not fewer
- Explicit over clever
- Don't add features beyond what was asked
- Don't handle errors gracefully in tests — everything must work end-to-end
