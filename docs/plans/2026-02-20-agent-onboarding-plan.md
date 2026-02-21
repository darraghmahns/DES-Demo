# Agent Onboarding Flow — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a 4-step modal wizard that walks new agents through connecting an integration and uploading their first document.

**Architecture:** Backend-persisted onboarding state on UserRecord (MongoDB). Two new API endpoints (GET status, PATCH complete). New `OnboardingWizard.tsx` component rendered as an overlay in App.tsx. localStorage preserves wizard step across OAuth redirects.

**Tech Stack:** Python/FastAPI (backend), React/TypeScript (frontend), MongoDB/Beanie (persistence), Clerk (auth)

**Design doc:** `docs/plans/2026-02-20-agent-onboarding-design.md`

---

### Task 1: Add Onboarding Fields to UserRecord

**Files:**
- Modify: `backend/db.py:70-90` (UserRecord class)
- Test: `backend/tests/test_onboarding.py` (create new)

**Step 1: Write the failing test**

Create `backend/tests/test_onboarding.py`:

```python
"""Tests for onboarding data model and API endpoints."""

from __future__ import annotations

import pytest


class TestUserRecordOnboardingDefaults:
    """New UserRecord instances should have onboarding fields with correct defaults."""

    def test_onboarding_completed_defaults_false(self):
        from db import UserRecord
        user = UserRecord(clerk_user_id="test_123")
        assert user.onboarding_completed is False

    def test_onboarding_completed_at_defaults_none(self):
        from db import UserRecord
        user = UserRecord(clerk_user_id="test_123")
        assert user.onboarding_completed_at is None

    def test_onboarding_skipped_steps_defaults_empty(self):
        from db import UserRecord
        user = UserRecord(clerk_user_id="test_123")
        assert user.onboarding_skipped_steps == []
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_onboarding.py::TestUserRecordOnboardingDefaults -v`
Expected: FAIL — `onboarding_completed` attribute not found on UserRecord

**Step 3: Add onboarding fields to UserRecord**

In `backend/db.py`, add three fields to the `UserRecord` class after line 82 (`last_login`):

```python
    # Onboarding wizard state
    onboarding_completed: bool = False
    onboarding_completed_at: Optional[datetime] = None
    onboarding_skipped_steps: List[str] = Field(default_factory=list)
```

Also add `List` to the typing imports at the top of `db.py` if not already present.

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_onboarding.py::TestUserRecordOnboardingDefaults -v`
Expected: 3 PASSED

**Step 5: Commit**

```bash
git add backend/db.py backend/tests/test_onboarding.py
git commit -m "feat(onboarding): add onboarding fields to UserRecord"
```

---

### Task 2: Add GET /api/onboarding/status Endpoint

**Files:**
- Modify: `backend/server.py` (add endpoint after line 88, near other route registrations)
- Test: `backend/tests/test_onboarding.py` (add to existing file)

**Step 1: Write the failing test**

Append to `backend/tests/test_onboarding.py`:

```python
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone


class TestOnboardingStatusEndpoint:
    """GET /api/onboarding/status returns onboarding + integration state."""

    def _make_user(self, **overrides):
        """Build a mock UserRecord."""
        user = MagicMock()
        user.onboarding_completed = False
        user.onboarding_completed_at = None
        user.onboarding_skipped_steps = []
        user.dotloop_tokens = None
        user.docusign_tokens = None
        for k, v in overrides.items():
            setattr(user, k, v)
        return user

    @pytest.mark.asyncio
    async def test_new_user_returns_not_completed(self):
        from server import app
        from httpx import ASGITransport, AsyncClient

        user = self._make_user()

        with patch("server.get_current_user", return_value=user):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/api/onboarding/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["completed"] is False
        assert data["completed_at"] is None
        assert data["skipped_steps"] == []
        assert data["dotloop_connected"] is False
        assert data["docusign_connected"] is False

    @pytest.mark.asyncio
    async def test_completed_user_returns_completed(self):
        from server import app
        from httpx import ASGITransport, AsyncClient

        ts = datetime(2026, 2, 20, 12, 0, 0, tzinfo=timezone.utc)
        user = self._make_user(
            onboarding_completed=True,
            onboarding_completed_at=ts,
            onboarding_skipped_steps=["integration"],
        )

        with patch("server.get_current_user", return_value=user):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/api/onboarding/status")

        data = resp.json()
        assert data["completed"] is True
        assert data["skipped_steps"] == ["integration"]

    @pytest.mark.asyncio
    async def test_dotloop_connected_when_tokens_present(self):
        from server import app
        from httpx import ASGITransport, AsyncClient

        tokens = MagicMock()
        tokens.access_token = "tok_123"
        user = self._make_user(dotloop_tokens=tokens)

        with patch("server.get_current_user", return_value=user):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/api/onboarding/status")

        assert resp.json()["dotloop_connected"] is True

    @pytest.mark.asyncio
    async def test_returns_401_when_no_auth(self):
        """With AUTH_ENABLED, missing token should 401."""
        from server import app
        from httpx import ASGITransport, AsyncClient
        from fastapi import HTTPException

        async def raise_401(request):
            raise HTTPException(status_code=401, detail="Auth required")

        with patch("server.get_current_user", side_effect=raise_401):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/api/onboarding/status")

        assert resp.status_code == 401
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_onboarding.py::TestOnboardingStatusEndpoint -v`
Expected: FAIL — 404 (endpoint doesn't exist yet)

**Step 3: Add the endpoint to server.py**

Add after the `app.include_router(integrations_router)` line (line 88 in `backend/server.py`):

```python
# ---------------------------------------------------------------------------
# Onboarding
# ---------------------------------------------------------------------------

@app.get("/api/onboarding/status")
async def onboarding_status(user=Depends(get_current_user)):
    """Return onboarding completion state and integration status for the wizard."""
    if not user:
        # Auth disabled — no onboarding
        return {"completed": True, "completed_at": None, "skipped_steps": [],
                "dotloop_connected": False, "docusign_connected": False}
    return {
        "completed": user.onboarding_completed,
        "completed_at": user.onboarding_completed_at.isoformat() if user.onboarding_completed_at else None,
        "skipped_steps": user.onboarding_skipped_steps,
        "dotloop_connected": bool(user.dotloop_tokens and user.dotloop_tokens.access_token),
        "docusign_connected": bool(user.docusign_tokens and user.docusign_tokens.access_token),
    }
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_onboarding.py::TestOnboardingStatusEndpoint -v`
Expected: 4 PASSED

**Step 5: Commit**

```bash
git add backend/server.py backend/tests/test_onboarding.py
git commit -m "feat(onboarding): add GET /api/onboarding/status endpoint"
```

---

### Task 3: Add PATCH /api/onboarding/complete Endpoint

**Files:**
- Modify: `backend/server.py` (add after the GET endpoint from Task 2)
- Test: `backend/tests/test_onboarding.py` (add new test class)

**Step 1: Write the failing test**

Append to `backend/tests/test_onboarding.py`:

```python
class TestOnboardingCompleteEndpoint:
    """PATCH /api/onboarding/complete marks onboarding done."""

    @pytest.mark.asyncio
    async def test_marks_completed(self):
        from server import app
        from httpx import ASGITransport, AsyncClient

        user = MagicMock()
        user.onboarding_completed = False
        user.onboarding_completed_at = None
        user.onboarding_skipped_steps = []
        user.save = AsyncMock()

        with patch("server.get_current_user", return_value=user):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.patch(
                    "/api/onboarding/complete",
                    json={"skipped_steps": ["integration"]},
                )

        assert resp.status_code == 200
        assert user.onboarding_completed is True
        assert user.onboarding_completed_at is not None
        assert user.onboarding_skipped_steps == ["integration"]
        user.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty_skipped_steps(self):
        from server import app
        from httpx import ASGITransport, AsyncClient

        user = MagicMock()
        user.onboarding_completed = False
        user.onboarding_completed_at = None
        user.onboarding_skipped_steps = []
        user.save = AsyncMock()

        with patch("server.get_current_user", return_value=user):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.patch(
                    "/api/onboarding/complete",
                    json={"skipped_steps": []},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["completed"] is True
        assert user.onboarding_skipped_steps == []

    @pytest.mark.asyncio
    async def test_idempotent_when_already_completed(self):
        from server import app
        from httpx import ASGITransport, AsyncClient

        ts = datetime(2026, 2, 20, 12, 0, 0, tzinfo=timezone.utc)
        user = MagicMock()
        user.onboarding_completed = True
        user.onboarding_completed_at = ts
        user.onboarding_skipped_steps = ["extraction"]
        user.save = AsyncMock()

        with patch("server.get_current_user", return_value=user):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.patch(
                    "/api/onboarding/complete",
                    json={"skipped_steps": []},
                )

        # Should succeed but not overwrite the original timestamp
        assert resp.status_code == 200
        assert user.onboarding_completed_at == ts
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_onboarding.py::TestOnboardingCompleteEndpoint -v`
Expected: FAIL — 404/405 (endpoint doesn't exist)

**Step 3: Add the PATCH endpoint**

Add below the GET endpoint in `backend/server.py`:

```python
class OnboardingCompleteRequest(BaseModel):
    skipped_steps: List[str] = Field(default_factory=list)


@app.patch("/api/onboarding/complete")
async def onboarding_complete(request: OnboardingCompleteRequest, user=Depends(get_current_user)):
    """Mark onboarding as completed. Idempotent — won't overwrite existing timestamp."""
    if not user:
        return {"completed": True}
    if not user.onboarding_completed:
        user.onboarding_completed = True
        user.onboarding_completed_at = datetime.now(timezone.utc)
        user.onboarding_skipped_steps = request.skipped_steps
        await user.save()
    return {
        "completed": user.onboarding_completed,
        "completed_at": user.onboarding_completed_at.isoformat() if user.onboarding_completed_at else None,
    }
```

Make sure `List` is in the typing imports at the top of `server.py`. It should already be there from the existing `from typing import AsyncGenerator, List, Optional` on line 12.

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_onboarding.py::TestOnboardingCompleteEndpoint -v`
Expected: 3 PASSED

**Step 5: Run all onboarding tests together**

Run: `cd backend && python -m pytest tests/test_onboarding.py -v`
Expected: 10 PASSED (3 model + 4 status + 3 complete)

**Step 6: Commit**

```bash
git add backend/server.py backend/tests/test_onboarding.py
git commit -m "feat(onboarding): add PATCH /api/onboarding/complete endpoint"
```

---

### Task 4: Add Frontend API Functions

**Files:**
- Modify: `frontend/src/api.ts` (append at end, ~line 787)

**Step 1: Add onboarding API types and functions**

Append to `frontend/src/api.ts`:

```typescript
// ---------------------------------------------------------------------------
// Onboarding
// ---------------------------------------------------------------------------

export interface OnboardingStatus {
  completed: boolean;
  completed_at: string | null;
  skipped_steps: string[];
  dotloop_connected: boolean;
  docusign_connected: boolean;
}

export async function fetchOnboardingStatus(): Promise<OnboardingStatus> {
  try {
    const resp = await fetch(`${API_BASE}/api/onboarding/status`, {
      headers: { ...await authHeaders() },
    });
    if (!resp.ok) {
      // Fail open: treat as completed so onboarding doesn't block the app
      return { completed: true, completed_at: null, skipped_steps: [], dotloop_connected: false, docusign_connected: false };
    }
    return resp.json();
  } catch {
    return { completed: true, completed_at: null, skipped_steps: [], dotloop_connected: false, docusign_connected: false };
  }
}

export async function completeOnboarding(skippedSteps: string[]): Promise<void> {
  await fetch(`${API_BASE}/api/onboarding/complete`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...await authHeaders() },
    body: JSON.stringify({ skipped_steps: skippedSteps }),
  });
}
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/api.ts
git commit -m "feat(onboarding): add frontend API functions for onboarding status/complete"
```

---

### Task 5: Build OnboardingWizard Component

**Files:**
- Create: `frontend/src/components/OnboardingWizard.tsx`
- Create: `frontend/src/components/OnboardingWizard.css`

**Step 1: Create component directory**

```bash
mkdir -p frontend/src/components
```

**Step 2: Create OnboardingWizard.tsx**

Create `frontend/src/components/OnboardingWizard.tsx`:

```tsx
import { useState, useRef, useEffect } from 'react';
import { getDotloopConnectUrl, getDocuSignConnectUrl, uploadFile } from '../api';
import './OnboardingWizard.css';

const STEP_KEY = 'des_onboarding_step';

interface OnboardingWizardProps {
  dotloopConnected: boolean;
  docusignConnected: boolean;
  onComplete: (skippedSteps: string[]) => void;
  onFileUploaded: (fileName: string) => void;
}

type WizardStep = 'welcome' | 'integrations' | 'extraction' | 'done';
const STEPS: WizardStep[] = ['welcome', 'integrations', 'extraction', 'done'];

export default function OnboardingWizard({
  dotloopConnected,
  docusignConnected,
  onComplete,
  onFileUploaded,
}: OnboardingWizardProps) {
  const savedStep = localStorage.getItem(STEP_KEY);
  const initialIdx = savedStep ? Math.min(Number(savedStep), STEPS.length - 1) : 0;
  const [stepIdx, setStepIdx] = useState(initialIdx);
  const [skippedSteps, setSkippedSteps] = useState<string[]>([]);
  const [uploadState, setUploadState] = useState<'idle' | 'uploading' | 'done' | 'error'>('idle');
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadedFileName, setUploadedFileName] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const step = STEPS[stepIdx];

  useEffect(() => {
    localStorage.setItem(STEP_KEY, String(stepIdx));
  }, [stepIdx]);

  function goNext() {
    setStepIdx((prev) => Math.min(prev + 1, STEPS.length - 1));
  }

  function skipStep(stepName: string) {
    setSkippedSteps((prev) => [...prev, stepName]);
    goNext();
  }

  function handleFinish() {
    localStorage.removeItem(STEP_KEY);
    onComplete(skippedSteps);
  }

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadState('uploading');
    setUploadError(null);
    try {
      const result = await uploadFile(file);
      setUploadState('done');
      setUploadedFileName(result.name);
      onFileUploaded(result.name);
    } catch (err) {
      setUploadState('error');
      setUploadError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      if (fileRef.current) fileRef.current.value = '';
    }
  }

  const integrationConnected = dotloopConnected || docusignConnected;

  return (
    <div className="onboarding-overlay">
      <div className="onboarding-modal">
        {/* Progress indicator */}
        <div className="onboarding-progress">
          {STEPS.map((s, i) => (
            <div
              key={s}
              className={`onboarding-dot ${i === stepIdx ? 'active' : ''} ${i < stepIdx ? 'completed' : ''}`}
            />
          ))}
        </div>

        {/* Step 1: Welcome */}
        {step === 'welcome' && (
          <div className="onboarding-step">
            <h1 className="onboarding-title">Welcome to D.E.S.</h1>
            <p className="onboarding-subtitle">Document Extract System</p>
            <p className="onboarding-body">
              Upload real estate documents and extract structured data in seconds.
              Sync directly to Dotloop or DocuSign.
            </p>
            <button className="onboarding-btn primary" onClick={goNext}>
              Get Started
            </button>
          </div>
        )}

        {/* Step 2: Connect an Integration */}
        {step === 'integrations' && (
          <div className="onboarding-step">
            <h2 className="onboarding-heading">Connect Your Platform</h2>
            <p className="onboarding-body">
              Link your transaction management platform to push extracted data directly.
            </p>
            <div className="onboarding-cards">
              <div className={`onboarding-card ${dotloopConnected ? 'connected' : ''}`}>
                <span className="onboarding-card-icon">&#x1F517;</span>
                <span className="onboarding-card-label">Dotloop</span>
                {dotloopConnected ? (
                  <span className="onboarding-card-status">&#x2713; Connected</span>
                ) : (
                  <a href={getDotloopConnectUrl()} className="onboarding-btn secondary">
                    Connect
                  </a>
                )}
              </div>
              <div className={`onboarding-card ${docusignConnected ? 'connected' : ''}`}>
                <span className="onboarding-card-icon">&#x1F4DD;</span>
                <span className="onboarding-card-label">DocuSign</span>
                {docusignConnected ? (
                  <span className="onboarding-card-status">&#x2713; Connected</span>
                ) : (
                  <a href={getDocuSignConnectUrl()} className="onboarding-btn secondary">
                    Connect
                  </a>
                )}
              </div>
            </div>
            <div className="onboarding-actions">
              <button className="onboarding-btn text" onClick={() => skipStep('integration')}>
                Skip for now
              </button>
              <button
                className="onboarding-btn primary"
                onClick={goNext}
                disabled={!integrationConnected}
                title={integrationConnected ? '' : 'Connect at least one platform or skip'}
              >
                Next
              </button>
            </div>
          </div>
        )}

        {/* Step 3: First Extraction */}
        {step === 'extraction' && (
          <div className="onboarding-step">
            <h2 className="onboarding-heading">Upload Your First Document</h2>
            <p className="onboarding-body">
              Try it out with a purchase agreement, listing contract, or any real estate PDF.
            </p>

            {uploadState === 'idle' && (
              <>
                <label className="onboarding-upload-area">
                  <input
                    type="file"
                    accept=".pdf"
                    ref={fileRef}
                    onChange={handleUpload}
                    hidden
                  />
                  <span className="onboarding-upload-icon">&#x1F4C4;</span>
                  <span className="onboarding-upload-text">Click to upload a PDF</span>
                </label>
              </>
            )}

            {uploadState === 'uploading' && (
              <div className="onboarding-upload-progress">
                <span className="spinner" /> Uploading...
              </div>
            )}

            {uploadState === 'done' && (
              <div className="onboarding-upload-success">
                <span>&#x2713;</span> Uploaded {uploadedFileName}
              </div>
            )}

            {uploadState === 'error' && (
              <div className="onboarding-upload-error">
                {uploadError}
                <button className="onboarding-btn text" onClick={() => setUploadState('idle')}>
                  Try again
                </button>
              </div>
            )}

            <div className="onboarding-actions">
              <button className="onboarding-btn text" onClick={() => skipStep('extraction')}>
                Skip for now
              </button>
              <button
                className="onboarding-btn primary"
                onClick={goNext}
                disabled={uploadState !== 'done'}
              >
                {uploadState === 'done' ? 'Finish Setup' : 'Next'}
              </button>
            </div>
          </div>
        )}

        {/* Step 4: Done */}
        {step === 'done' && (
          <div className="onboarding-step">
            <h2 className="onboarding-heading">You're All Set!</h2>
            <div className="onboarding-summary">
              <div className="onboarding-summary-item">
                {integrationConnected ? '✓' : '—'}{' '}
                {integrationConnected
                  ? `Connected to ${dotloopConnected ? 'Dotloop' : ''}${dotloopConnected && docusignConnected ? ' & ' : ''}${docusignConnected ? 'DocuSign' : ''}`
                  : 'Integration skipped'}
              </div>
              <div className="onboarding-summary-item">
                {uploadedFileName ? '✓' : '—'}{' '}
                {uploadedFileName ? `Uploaded ${uploadedFileName}` : 'First extraction skipped'}
              </div>
            </div>
            <button className="onboarding-btn primary" onClick={handleFinish}>
              Go to Dashboard
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
```

**Step 3: Create OnboardingWizard.css**

Create `frontend/src/components/OnboardingWizard.css`:

```css
/* Onboarding Wizard Modal */

.onboarding-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  backdrop-filter: blur(4px);
}

.onboarding-modal {
  background: var(--bg-primary, #1a1a2e);
  border: 1px solid var(--border, #2a2a4a);
  border-radius: 16px;
  padding: 40px;
  max-width: 520px;
  width: 90%;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}

/* Progress dots */
.onboarding-progress {
  display: flex;
  gap: 8px;
  justify-content: center;
  margin-bottom: 32px;
}

.onboarding-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-muted, #555);
  transition: background 0.2s, transform 0.2s;
}

.onboarding-dot.active {
  background: var(--accent, #6366f1);
  transform: scale(1.3);
}

.onboarding-dot.completed {
  background: var(--green, #22c55e);
}

/* Step content */
.onboarding-step {
  text-align: center;
}

.onboarding-title {
  font-size: 28px;
  font-weight: 700;
  margin: 0 0 8px;
  color: var(--text-primary, #fff);
}

.onboarding-subtitle {
  font-size: 14px;
  color: var(--text-muted, #888);
  margin: 0 0 20px;
  letter-spacing: 1px;
  text-transform: uppercase;
}

.onboarding-heading {
  font-size: 22px;
  font-weight: 600;
  margin: 0 0 12px;
  color: var(--text-primary, #fff);
}

.onboarding-body {
  font-size: 15px;
  line-height: 1.5;
  color: var(--text-secondary, #aaa);
  margin: 0 0 24px;
}

/* Integration cards */
.onboarding-cards {
  display: flex;
  gap: 16px;
  justify-content: center;
  margin-bottom: 24px;
}

.onboarding-card {
  flex: 1;
  max-width: 200px;
  border: 1px solid var(--border, #2a2a4a);
  border-radius: 12px;
  padding: 20px 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  transition: border-color 0.2s;
}

.onboarding-card.connected {
  border-color: var(--green, #22c55e);
}

.onboarding-card-icon {
  font-size: 28px;
}

.onboarding-card-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, #fff);
}

.onboarding-card-status {
  font-size: 13px;
  color: var(--green, #22c55e);
  font-weight: 500;
}

/* Upload area */
.onboarding-upload-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  border: 2px dashed var(--border, #2a2a4a);
  border-radius: 12px;
  padding: 32px 16px;
  cursor: pointer;
  margin-bottom: 24px;
  transition: border-color 0.2s;
}

.onboarding-upload-area:hover {
  border-color: var(--accent, #6366f1);
}

.onboarding-upload-icon {
  font-size: 32px;
}

.onboarding-upload-text {
  font-size: 14px;
  color: var(--text-secondary, #aaa);
}

.onboarding-upload-progress,
.onboarding-upload-success,
.onboarding-upload-error {
  padding: 20px;
  border-radius: 12px;
  margin-bottom: 24px;
  font-size: 14px;
}

.onboarding-upload-progress {
  color: var(--text-secondary, #aaa);
}

.onboarding-upload-success {
  color: var(--green, #22c55e);
  background: rgba(34, 197, 94, 0.1);
}

.onboarding-upload-error {
  color: var(--red, #ef4444);
  background: rgba(239, 68, 68, 0.1);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* Summary */
.onboarding-summary {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 28px;
  text-align: left;
  padding: 16px 20px;
  background: var(--bg-secondary, #16162a);
  border-radius: 10px;
}

.onboarding-summary-item {
  font-size: 14px;
  color: var(--text-secondary, #aaa);
}

/* Action buttons */
.onboarding-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.onboarding-btn {
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: opacity 0.15s;
  text-decoration: none;
  display: inline-block;
}

.onboarding-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.onboarding-btn.primary {
  background: var(--accent, #6366f1);
  color: #fff;
  padding: 10px 24px;
}

.onboarding-btn.primary:hover:not(:disabled) {
  opacity: 0.9;
}

.onboarding-btn.secondary {
  background: transparent;
  border: 1px solid var(--accent, #6366f1);
  color: var(--accent, #6366f1);
  padding: 8px 16px;
}

.onboarding-btn.secondary:hover {
  background: rgba(99, 102, 241, 0.1);
}

.onboarding-btn.text {
  background: none;
  color: var(--text-muted, #888);
  padding: 8px 12px;
}

.onboarding-btn.text:hover {
  color: var(--text-primary, #fff);
}
```

**Step 4: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 5: Commit**

```bash
git add frontend/src/components/OnboardingWizard.tsx frontend/src/components/OnboardingWizard.css
git commit -m "feat(onboarding): add OnboardingWizard component and styles"
```

---

### Task 6: Wire OnboardingWizard into App.tsx

**Files:**
- Modify: `frontend/src/App.tsx` (imports at top, state + effect in function body, render in JSX)

**Step 1: Add imports**

At the top of `frontend/src/App.tsx`, add to the `api` import block (line 2-33):

```typescript
  fetchOnboardingStatus,
  completeOnboarding,
```

Add after the existing component imports (around line 36):

```typescript
import OnboardingWizard from './components/OnboardingWizard';
```

**Step 2: Add onboarding state**

Inside the `App()` function, after the existing state declarations (around line 215, after the DocuSign state block), add:

```typescript
  // Onboarding
  const [showOnboarding, setShowOnboarding] = useState(false);
```

**Step 3: Add onboarding effect**

Inside the mount useEffect (line 619-661), add before the `checkDotloopStatus()` call at line 620:

```typescript
    // Check onboarding status
    fetchOnboardingStatus().then((status) => {
      if (!status.completed) {
        setShowOnboarding(true);
      }
    });
```

**Step 4: Add onboarding completion handler**

Add a handler function inside `App()` (near the other handler functions, around line 500):

```typescript
  async function handleOnboardingComplete(skippedSteps: string[]) {
    await completeOnboarding(skippedSteps);
    setShowOnboarding(false);
    // Refresh integration status in case user connected during onboarding
    checkDotloopStatus().then(setDotloopConfigured);
    checkDocuSignStatus().then(setDocusignConfigured);
  }

  function handleOnboardingFileUploaded(fileName: string) {
    // Refresh doc list and select the uploaded file
    fetchDocuments(mode).then((docs) => {
      setDocuments(docs);
      setSelectedDoc(fileName);
    });
  }
```

**Step 5: Add wizard to render**

In `renderMainApp()`, add right after the opening `<div className="app">` (line 795):

```tsx
        {showOnboarding && (
          <OnboardingWizard
            dotloopConnected={dotloopConfigured}
            docusignConnected={docusignConfigured}
            onComplete={handleOnboardingComplete}
            onFileUploaded={handleOnboardingFileUploaded}
          />
        )}
```

**Step 6: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 7: Verify dev server renders**

Run: `cd frontend && npm run dev`
Manual test: Open browser, sign in, verify onboarding modal appears.

**Step 8: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(onboarding): wire OnboardingWizard into App.tsx"
```

---

### Task 7: Handle OAuth Redirect Survival

**Files:**
- Modify: `frontend/src/App.tsx` (update mount useEffect, lines 643-660)

**Step 1: Update OAuth redirect handling to recheck onboarding**

In the mount useEffect in `App.tsx` (lines 643-660), after the existing OAuth redirect handling, add a re-check of onboarding status so the wizard reopens at the correct step:

```typescript
    // After OAuth redirect, re-check onboarding so wizard reopens at correct step
    if (params.get('dotloop_connected') === 'true' || params.get('docusign_connected') === 'true') {
      fetchOnboardingStatus().then((status) => {
        if (!status.completed) {
          setShowOnboarding(true);
        }
      });
    }
```

This ensures that when a user returns from a Dotloop/DocuSign OAuth flow mid-wizard, the modal reopens. The localStorage `des_onboarding_step` value (saved by OnboardingWizard) will restore the wizard to step 2 (integrations), where the checkmark will now appear on the connected service.

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(onboarding): handle OAuth redirect survival in wizard"
```

---

### Task 8: Manual End-to-End Testing

**No files changed — verification only.**

**Step 1: Reset test state**

In MongoDB, clear your user's onboarding fields so the wizard shows:

```bash
cd backend && python -c "
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os

load_dotenv()

async def reset():
    client = AsyncIOMotorClient(os.getenv('MONGODB_URI'))
    db = client.get_default_database()
    result = await db.users.update_many({}, {'\$set': {'onboarding_completed': False, 'onboarding_completed_at': None, 'onboarding_skipped_steps': []}})
    print(f'Reset {result.modified_count} user(s)')
    client.close()

asyncio.run(reset())
"
```

**Step 2: Test happy path**

1. Start backend: `cd backend && uvicorn server:app --reload --port 8000`
2. Start frontend: `cd frontend && npm run dev`
3. Open `http://localhost:5173`, sign in
4. Verify: Onboarding modal appears at Step 1 (Welcome)
5. Click "Get Started" → Step 2 (Integrations)
6. Click "Connect" on Dotloop → OAuth redirect → return to app → wizard reopens at Step 2 with checkmark
7. Click "Next" → Step 3 (Extraction)
8. Upload a PDF → shows uploading → shows success
9. Click "Finish Setup" → Step 4 (Done) with summary
10. Click "Go to Dashboard" → modal closes, main app visible
11. Refresh page → wizard should NOT reappear

**Step 3: Test skip path**

1. Reset onboarding state (repeat Step 1)
2. Step 1: Click "Get Started"
3. Step 2: Click "Skip for now"
4. Step 3: Click "Skip for now"
5. Step 4: Verify summary shows "Integration skipped" and "First extraction skipped"
6. Click "Go to Dashboard"
7. Refresh → wizard should NOT reappear

**Step 4: Test page refresh mid-wizard**

1. Reset onboarding state
2. Get to Step 2
3. Refresh the page
4. Verify wizard reopens at Step 2 (not Step 1)

**Step 5: Commit test confirmation**

```bash
git add -A && git commit -m "feat(onboarding): complete onboarding wizard implementation"
```
