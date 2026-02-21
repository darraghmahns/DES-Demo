# Agent Onboarding Flow — Design Document

**Date**: 2026-02-20
**Status**: Approved
**Target users**: Individual real estate agents (not brokerage-invited)

## Goal

Walk new agents through connecting an integration (Dotloop or DocuSign) and uploading their first document via a step-by-step modal wizard on first login.

## Decisions

| Decision | Choice |
|---|---|
| State persistence | Backend-persisted on UserRecord |
| UI style | Full-screen modal wizard |
| Integration step | Single combined step (Dotloop + DocuSign side by side) |
| First extraction | Agent uploads their own real PDF |
| Required steps | All skippable |

## Wizard Steps

### Step 1: Welcome
- Value prop: "Upload real estate documents and extract structured data in seconds. Sync directly to Dotloop or DocuSign."
- Single CTA: "Get Started"

### Step 2: Connect an Integration
- Two cards side by side: Dotloop and DocuSign
- Each has a "Connect" button triggering the existing OAuth flow
- After OAuth redirect, wizard reopens at this step with a checkmark on the connected service
- "Skip for now" and "Next" buttons

### Step 3: First Extraction
- Prompt to upload a purchase agreement or listing contract
- Reuses existing upload handler and extraction pipeline
- Shows mini progress indicator inside the wizard
- "Skip for now" and "Finish Setup" buttons

### Step 4: Done
- Summary of what was connected and completed
- Shows checkmarks for completed steps, notes for skipped steps
- "Go to Dashboard" CTA calls PATCH /api/onboarding/complete

## Data Model

Add to `UserRecord` in `backend/db.py`:

```python
onboarding_completed: bool = False
onboarding_completed_at: Optional[datetime] = None
onboarding_skipped_steps: List[str] = Field(default_factory=list)
```

`onboarding_skipped_steps` records which steps were skipped (e.g., `["integration", "extraction"]`).

## API Endpoints

### GET /api/onboarding/status
Returns current onboarding state plus integration status for the wizard.

```json
{
  "completed": false,
  "completed_at": null,
  "skipped_steps": [],
  "dotloop_connected": true,
  "docusign_connected": false
}
```

### PATCH /api/onboarding/complete
Marks onboarding done. Request body:

```json
{
  "skipped_steps": ["integration"]
}
```

Sets `onboarding_completed=true`, `onboarding_completed_at=now()`, and records skipped steps.

## Frontend Components

### New files
- `frontend/src/components/OnboardingWizard.tsx` — Modal wizard (steps 1-4)
- `frontend/src/components/OnboardingWizard.css` — Wizard styles

### Integration with App.tsx
- On mount (after auth), fetch `GET /api/onboarding/status`
- If `completed=false`, show `<OnboardingWizard />`
- Wizard receives `dotloopConnected`, `docusignConnected`, `onComplete`, `onUploadPdf` as props
- Reuses existing `handleUpload` handler for the extraction step
- On "Go to Dashboard", calls PATCH endpoint and hides modal

### OAuth Redirect Survival
- Store current wizard step in `localStorage` (`des_onboarding_step`)
- On app reload after OAuth redirect: API returns `completed=false` + localStorage has step number = reopen wizard at correct step
- Existing OAuth redirect param handling in App.tsx updates integration status

## Edge Cases

| Scenario | Handling |
|---|---|
| OAuth redirect mid-wizard | localStorage preserves step, API confirms not complete, wizard reopens |
| Agent refreshes mid-wizard | Same as OAuth redirect |
| Agent closes modal (X) | Onboarding not marked complete; shows again next login |
| Extraction fails in step 3 | Error shown inline with retry button; "Skip" remains available |
| API status call fails | Fail open: don't show onboarding (broken app worse than missing wizard) |
| Already connected before wizard | Step 2 shows checkmark, agent clicks "Next" |

## Testing Plan

- Unit tests for new API endpoints (status, complete)
- Test UserRecord field defaults and update behavior
- Frontend: manual testing of wizard flow including OAuth redirect round-trip
- Edge case: verify wizard doesn't show when `onboarding_completed=true`
