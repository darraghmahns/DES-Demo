# D.E.S. User Management & Transaction System — Implementation Plan

## Overview

Add a complete user management system to D.E.S. with multiple user types (Buyers, Sellers, Agents, Loan Officers), document upload with AI extraction, transaction "lobbies" that link parties, and an AI chatbot-driven profile builder.

---

## Architecture Decisions

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | User Profile Architecture | Single MongoDB collection, multi-role, embedded sub-docs | MongoDB-idiomatic; supports users with multiple roles (agent + buyer) |
| 2 | Transaction Design | Embedded participant list on Transaction document | Idiomatic MongoDB; indexed for user lookups; soft-remove for history |
| 3 | Document Ownership | Dual: UserDocument (persists across deals) + TransactionDocument (deal-specific, references UserDocs) | "Fill it out once" philosophy; clear lifecycle separation |
| 4 | Frontend Architecture | React Router refactor | Current 2500-line App.tsx is unmaintainable; standard SPA pattern |
| 5 | Profile Fields | Comprehensive per role | AI extraction needs structured fields to populate; supports "fill once" |
| 6 | Document Requirements | Enum types + role-based templates + agent overrides | Structure for AI extraction schemas + flexibility for agents |
| 7 | Transaction Lifecycle | DRAFT→ACTIVE→UNDER_CONTRACT→PENDING_CLOSE→CLOSED/CANCELLED/EXPIRED | Maps to real estate industry standards; natural workflow trigger points |
| 8 | Auto-fill Mechanism | Docs → AI Extract → Profile Fields → Transaction Auto-fill | Core D.E.S. value prop: upload once, auto-fill everywhere |
| 9 | Profile API | Role-specific sub-routes (PUT /profile/agent, etc.) | Clean validation per role; /profile/completion for progress tracking |
| 10 | Transaction API | Nested REST (/transactions/{id}/participants) | Intuitive hierarchy; clear ownership semantics |
| 11 | Doc Upload API | Separate /profile/documents with auto-extraction | Keeps user doc workflow separate from extraction tool workflow |
| 12 | Invitations | Magic links → profile completion → Clerk account upgrade | Low friction entry; great for testing; natural onboarding |
| 13 | Page Structure | Shared layout, role-adaptive pages | No DRY violation; content adapts per user_type |
| 14 | Transaction Lobby UX | Tabbed detail + participant sidebar | Industry standard (Dotloop, Skyslope, DocuSign Rooms pattern) |
| 15 | Profile UX | AI Chatbot-style (Phase 4; wizard scaffolding in Phase 2) | Differentiator; aligns with D.E.S. AI-first identity |
| 16 | Component Architecture | Feature-based directory structure | "Engineered enough" — scales to 50+ components, evolves to atomic later |
| 17 | Phasing | Foundation → Profiles → Transactions → Chatbot | Each phase independently shippable; foundation first |
| 18 | Testing | Three-layer pyramid (unit + integration + frontend) | Well-tested is non-negotiable; catches edge cases at every level |
| 19 | Financial Doc Schemas | 5 core types (pre-approval, bank statement, pay stub, W-2, proof of funds) | Covers 90% of buyer needs; PII scanner already handles SSN flagging |
| 20 | Migration | Clean redesign (app not live, no prod data) | No backward compat overhead; design clean for long term |

---

## Data Models

### UserProfile (replaces UserRecord)

```python
class UserType(str, Enum):
    BUYER = "buyer"
    SELLER = "seller"
    AGENT = "agent"
    LOAN_OFFICER = "loan_officer"

class AgentProfile(BaseModel):
    license_number: Optional[str]
    license_state: Optional[str]
    license_expiry: Optional[datetime]
    brokerage_name: Optional[str]
    brokerage_id: Optional[PydanticObjectId]  # links to BrokerageProfile
    mls_id: Optional[str]
    nar_member_id: Optional[str]
    areas_served: List[str] = []  # cities/counties/states

class BuyerProfile(BaseModel):
    pre_approval_status: Optional[str]  # none, pre_qualified, pre_approved, fully_approved
    pre_approval_amount: Optional[float]
    pre_approval_lender: Optional[str]
    purchase_budget_min: Optional[float]
    purchase_budget_max: Optional[float]
    property_preferences: Optional[dict]  # property_type, bedrooms, location
    first_time_buyer: Optional[bool]
    employment_status: Optional[str]
    employer_name: Optional[str]
    annual_income: Optional[float]  # populated from extraction

class SellerProfile(BaseModel):
    property_addresses: List[dict] = []  # addresses of properties being sold
    ownership_type: Optional[str]  # sole, joint, trust, LLC

class LoanOfficerProfile(BaseModel):
    nmls_id: Optional[str]
    company_name: Optional[str]
    company_nmls: Optional[str]
    license_states: List[str] = []
    loan_types_offered: List[str] = []  # conventional, FHA, VA, USDA, jumbo
    contact_preference: Optional[str]  # email, phone, text

class UserProfile(Document):
    # Shared fields
    clerk_user_id: Optional[str]  # None for magic-link-only users
    email: Indexed(str, unique=True)
    name: str
    phone: Optional[str]
    address: Optional[dict]  # street, city, state, zip
    profile_photo_url: Optional[str]

    # Multi-role support
    user_types: List[UserType] = []

    # Role-specific sub-documents (populated when user has that role)
    agent_profile: Optional[AgentProfile]
    buyer_profile: Optional[BuyerProfile]
    seller_profile: Optional[SellerProfile]
    loan_officer_profile: Optional[LoanOfficerProfile]

    # OAuth tokens (preserved from current UserRecord)
    dotloop_tokens: Optional[OAuthTokenSet]
    docusign_tokens: Optional[OAuthTokenSet]

    # Magic link support
    magic_link_token: Optional[str]
    magic_link_expires: Optional[datetime]
    has_clerk_account: bool = False

    # Metadata
    org_id: Optional[str]
    org_name: Optional[str]
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: Optional[datetime]

    class Settings:
        name = "user_profiles"
```

### Transaction

```python
class TransactionStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    UNDER_CONTRACT = "under_contract"
    PENDING_CLOSE = "pending_close"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"

class ParticipantStatus(str, Enum):
    INVITED = "invited"       # magic link sent, not yet accepted
    ACTIVE = "active"         # accepted and participating
    REMOVED = "removed"       # soft-removed from transaction

class TransactionParticipant(BaseModel):
    user_id: PydanticObjectId  # references UserProfile
    role: ParticipantRole      # reuse existing enum (BUYER, SELLER, LISTING_AGENT, etc.)
    status: ParticipantStatus = ParticipantStatus.INVITED
    added_at: datetime = Field(default_factory=datetime.utcnow)
    added_by: Optional[PydanticObjectId]  # who invited them
    removed_at: Optional[datetime]
    profile_completion: Optional[float]  # cached percentage

class DocumentRequirement(BaseModel):
    doc_type: UserDocumentType
    role: ParticipantRole       # which participant role needs this
    required: bool = True       # can be toggled off by agent
    satisfied: bool = False     # auto-computed: has the participant uploaded this?
    satisfied_by: Optional[PydanticObjectId]  # reference to UserDocument

class Transaction(Document):
    # Core info
    name: str  # "123 Main St Purchase" or custom name
    transaction_type: str  # purchase, sale, lease, etc.
    status: TransactionStatus = TransactionStatus.DRAFT

    # Property
    property_address: Optional[DotloopPropertyAddress]  # reuse existing schema
    mls_number: Optional[str]

    # Participants
    participants: List[TransactionParticipant] = []

    # Financial summary (auto-filled from extraction/profiles)
    purchase_price: Optional[float]
    earnest_money: Optional[float]
    closing_date: Optional[datetime]

    # Document requirements
    document_requirements: List[DocumentRequirement] = []

    # Linked extractions (from the existing extraction pipeline)
    extraction_ids: List[PydanticObjectId] = []

    # Compliance
    compliance_report_id: Optional[PydanticObjectId]

    # Metadata
    created_by: PydanticObjectId  # UserProfile ID of creator (typically agent)
    org_id: Optional[str]
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "transactions"
        indexes = [
            "participants.user_id",
            "status",
            "created_by",
        ]
```

### UserDocument

```python
class UserDocumentType(str, Enum):
    PRE_APPROVAL_LETTER = "pre_approval_letter"
    BANK_STATEMENT = "bank_statement"
    PAY_STUB = "pay_stub"
    TAX_RETURN = "tax_return"
    W2 = "w2"
    PROOF_OF_FUNDS = "proof_of_funds"
    DRIVERS_LICENSE = "drivers_license"
    PROOF_OF_INSURANCE = "proof_of_insurance"
    OTHER = "other"

class UserDocument(Document):
    user_id: PydanticObjectId          # owner (UserProfile)
    doc_type: UserDocumentType
    filename: str
    file_path: str
    file_hash: str
    file_size_bytes: int

    # Extraction results (populated after AI extraction)
    extraction_status: str = "pending"  # pending, processing, completed, failed
    extracted_data: Optional[dict]      # structured data from extraction
    extraction_id: Optional[str]        # task ID for SSE streaming
    overall_confidence: Optional[float]
    citations: List[dict] = []

    # PII detection
    pii_report: Optional[dict]

    # Metadata
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    description: Optional[str]

    class Settings:
        name = "user_documents"
        indexes = [
            "user_id",
            "doc_type",
            "file_hash",
        ]
```

### TransactionDocument

```python
class TransactionDocument(Document):
    transaction_id: PydanticObjectId    # which transaction
    doc_type: str                       # purchase_offer, addendum, etc. (existing DocumentType enum)
    source: str                         # upload, dotloop, docusign, user_profile

    # If sourced from a user's profile document:
    source_user_document_id: Optional[PydanticObjectId]  # references UserDocument

    # File info (may be a copy or reference)
    filename: str
    file_path: str
    file_hash: str

    # Extraction (uses existing DocumentRecord/ExtractionRecord pattern)
    document_record_id: Optional[PydanticObjectId]  # links to existing DocumentRecord

    # Metadata
    uploaded_by: PydanticObjectId       # UserProfile who uploaded/linked it
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "transaction_documents"
        indexes = [
            "transaction_id",
            "doc_type",
        ]
```

---

## Financial Document Extraction Schemas

### PreApprovalExtraction
```python
class PreApprovalExtraction(BaseModel):
    lender_name: Optional[str]
    lender_address: Optional[str]
    lender_nmls: Optional[str]
    loan_officer_name: Optional[str]
    loan_officer_nmls: Optional[str]
    borrower_name: Optional[str]
    co_borrower_name: Optional[str]
    approval_amount: Optional[float]
    loan_type: Optional[str]           # conventional, FHA, VA, USDA, jumbo
    interest_rate: Optional[float]
    approval_date: Optional[str]
    expiration_date: Optional[str]
    conditions: List[str] = []          # conditions for final approval
    property_type: Optional[str]        # SFR, condo, townhouse, etc.
```

### BankStatementExtraction
```python
class BankStatementExtraction(BaseModel):
    institution_name: Optional[str]
    account_holder: Optional[str]
    account_type: Optional[str]         # checking, savings, money market
    account_number_last4: Optional[str]  # only last 4 digits (PII safety)
    statement_period_start: Optional[str]
    statement_period_end: Optional[str]
    beginning_balance: Optional[float]
    ending_balance: Optional[float]
    total_deposits: Optional[float]
    total_withdrawals: Optional[float]
    average_daily_balance: Optional[float]
```

### PayStubExtraction
```python
class PayStubExtraction(BaseModel):
    employer_name: Optional[str]
    employer_address: Optional[str]
    employee_name: Optional[str]
    employee_id: Optional[str]
    pay_period_start: Optional[str]
    pay_period_end: Optional[str]
    pay_date: Optional[str]
    pay_frequency: Optional[str]        # weekly, biweekly, semi-monthly, monthly
    gross_pay: Optional[float]
    net_pay: Optional[float]
    federal_tax: Optional[float]
    state_tax: Optional[float]
    ytd_gross: Optional[float]
    ytd_net: Optional[float]
```

### W2Extraction
```python
class W2Extraction(BaseModel):
    tax_year: Optional[int]
    employer_name: Optional[str]
    employer_ein: Optional[str]
    employer_address: Optional[str]
    employee_name: Optional[str]
    employee_ssn_last4: Optional[str]    # only last 4 (PII safety)
    wages_tips_compensation: Optional[float]  # Box 1
    federal_tax_withheld: Optional[float]     # Box 2
    social_security_wages: Optional[float]    # Box 3
    social_security_tax: Optional[float]      # Box 4
    medicare_wages: Optional[float]           # Box 5
    medicare_tax: Optional[float]             # Box 6
    state: Optional[str]
    state_wages: Optional[float]              # Box 16
    state_tax_withheld: Optional[float]       # Box 17
```

### ProofOfFundsExtraction
```python
class ProofOfFundsExtraction(BaseModel):
    institution_name: Optional[str]
    account_holder: Optional[str]
    letter_date: Optional[str]
    account_type: Optional[str]
    available_funds: Optional[float]
    currency: Optional[str]
    officer_name: Optional[str]          # bank officer who signed
    officer_title: Optional[str]
    contact_phone: Optional[str]
```

---

## API Endpoints (New)

### Profile Management

```
GET    /api/profile                         → Current user's full profile
PUT    /api/profile                         → Update shared fields (name, phone, address)
PUT    /api/profile/agent                   → Update agent-specific fields
PUT    /api/profile/buyer                   → Update buyer-specific fields
PUT    /api/profile/seller                  → Update seller-specific fields
PUT    /api/profile/loan-officer            → Update loan officer fields
POST   /api/profile/roles                   → Add a new role (e.g., agent adds "buyer")
DELETE /api/profile/roles/{role}            → Remove a role
GET    /api/profile/completion              → Profile completion % per role
GET    /api/users/{user_id}                 → View another user's profile (permission-filtered)
GET    /api/users/search?email=...          → Search users by email (for invitations)
```

### Profile Documents

```
POST   /api/profile/documents               → Upload user doc (multipart, specify doc_type)
GET    /api/profile/documents               → List my documents
GET    /api/profile/documents/{id}          → Get doc detail + extraction results
DELETE /api/profile/documents/{id}          → Remove document
POST   /api/profile/documents/{id}/extract  → Trigger/re-trigger extraction
GET    /api/profile/documents/{id}/stream   → SSE stream for extraction progress
```

### Transactions

```
POST   /api/transactions                              → Create transaction
GET    /api/transactions                              → List my transactions (filtered by involvement)
GET    /api/transactions/{id}                         → Get transaction detail + participants
PUT    /api/transactions/{id}                         → Update transaction (status, property info)
DELETE /api/transactions/{id}                         → Delete transaction (draft only)

POST   /api/transactions/{id}/participants            → Add participant (by email, generates magic link)
DELETE /api/transactions/{id}/participants/{uid}       → Remove participant (soft-remove)
PUT    /api/transactions/{id}/participants/{uid}       → Update participant role

GET    /api/transactions/{id}/documents               → List all docs for this transaction
POST   /api/transactions/{id}/documents               → Upload/link document to transaction
GET    /api/transactions/{id}/completion              → Transaction readiness check
POST   /api/transactions/{id}/auto-fill               → Pull profile data into transaction
```

### Magic Links & Invitations

```
POST   /api/invitations                    → Generate magic link invitation (for agent use)
GET    /api/invitations/{token}/validate   → Validate magic link, return invitation details
POST   /api/invitations/{token}/accept     → Accept invitation, link to transaction
POST   /api/invitations/{token}/profile    → Submit profile data via magic link (no Clerk needed)
POST   /api/invitations/{token}/upgrade    → Link Clerk account to magic-link profile
```

### AI Chatbot Profile Builder (Phase 4)

```
POST   /api/profile/chat                   → Send message, get AI response + extracted fields
GET    /api/profile/chat/history           → Get chat history for current session
POST   /api/profile/chat/upload            → Upload document within chat context
```

---

## Document Requirement Templates

Default required documents per role per transaction type:

### Purchase Transaction — Buyer
- PRE_APPROVAL_LETTER (required)
- BANK_STATEMENT (required)
- PROOF_OF_FUNDS (required)
- PAY_STUB (optional)
- W2 (optional)
- DRIVERS_LICENSE (required)

### Purchase Transaction — Seller
- PROOF_OF_INSURANCE (optional)
- DRIVERS_LICENSE (required)

### Purchase Transaction — Loan Officer
- (no document uploads — they provide the pre-approval letter on the buyer's behalf)

### Agent Override
Agents can add/remove requirements per transaction via:
```
PUT /api/transactions/{id}
body: { document_requirements: [...] }
```

---

## Frontend Structure

### Directory Layout

```
frontend/src/
├── components/
│   ├── layout/
│   │   ├── AppShell.tsx           → Main layout (navbar + sidebar + content area)
│   │   ├── Navbar.tsx             → Top navigation bar
│   │   ├── Sidebar.tsx            → Left sidebar (role-adaptive menu)
│   │   └── ProtectedRoute.tsx     → Auth + role guard wrapper
│   ├── common/
│   │   ├── Button.tsx
│   │   ├── Input.tsx
│   │   ├── Modal.tsx
│   │   ├── StatusBadge.tsx
│   │   ├── ProgressBar.tsx
│   │   ├── FileUpload.tsx         → Drag-and-drop file upload
│   │   └── CompletionIndicator.tsx → Profile/transaction completion %
│   ├── extraction/
│   │   ├── ExtractionView.tsx     → Moved from App.tsx
│   │   ├── CitationsTab.tsx
│   │   ├── ComplianceTab.tsx
│   │   ├── PIITab.tsx
│   │   └── JSONTab.tsx
│   ├── profile/
│   │   ├── ProfileWizard.tsx      → Step-by-step profile completion (Phase 2)
│   │   ├── AgentForm.tsx
│   │   ├── BuyerForm.tsx
│   │   ├── SellerForm.tsx
│   │   ├── LoanOfficerForm.tsx
│   │   ├── DocumentUpload.tsx     → Profile document upload with extraction status
│   │   └── RoleSelector.tsx       → Add/remove roles
│   ├── transaction/
│   │   ├── TransactionCard.tsx    → Transaction list item
│   │   ├── TransactionLobby.tsx   → Main lobby component (tabs + sidebar)
│   │   ├── ParticipantSidebar.tsx → Participant list with completion indicators
│   │   ├── OverviewTab.tsx        → Key dates, financials, property info
│   │   ├── DocumentsTab.tsx       → Document checklist with upload status
│   │   ├── ComplianceTab.tsx      → Transaction compliance (from JACE)
│   │   ├── ActivityTab.tsx        → Timeline of actions
│   │   └── InviteParticipant.tsx  → Email input + role selection + send magic link
│   └── chat/                      → Phase 4
│       ├── ChatInterface.tsx      → Chat UI (messages, input, file drop)
│       ├── ChatMessage.tsx        → Message bubble (user vs AI)
│       └── ExtractedFieldsPanel.tsx → Live profile fields updating from chat
├── pages/
│   ├── Dashboard.tsx              → Role-adaptive dashboard
│   ├── Profile.tsx                → Profile editor page
│   ├── ProfileDocuments.tsx       → My documents page
│   ├── TransactionList.tsx        → List of my transactions
│   ├── TransactionDetail.tsx      → Transaction lobby page
│   ├── InviteLanding.tsx          → Magic link landing (/invite/:token)
│   ├── Extraction.tsx             → Existing extraction tool (preserved)
│   └── Login.tsx                  → Login/signup page
├── hooks/
│   ├── useAuth.ts                 → Authentication state + user info
│   ├── useProfile.ts             → Profile CRUD operations
│   ├── useTransaction.ts         → Transaction CRUD + participant management
│   ├── useDocumentUpload.ts      → File upload + extraction progress
│   ├── useSSE.ts                 → Server-sent events subscription (extracted from App.tsx)
│   └── useCompletion.ts          → Profile/transaction completion tracking
├── api/
│   ├── client.ts                 → Base HTTP client (axios/fetch wrapper)
│   ├── profile.ts                → Profile API functions
│   ├── transactions.ts           → Transaction API functions
│   ├── documents.ts              → Document upload/management API functions
│   ├── invitations.ts            → Magic link API functions
│   ├── extraction.ts             → Existing extraction API (moved from api.ts)
│   └── chat.ts                   → Chatbot API (Phase 4)
├── types/
│   ├── user.ts                   → UserProfile, AgentProfile, BuyerProfile, etc.
│   ├── transaction.ts            → Transaction, TransactionParticipant, etc.
│   ├── document.ts               → UserDocument, TransactionDocument, etc.
│   └── extraction.ts             → Existing extraction types (moved from api.ts)
├── context/
│   ├── AuthContext.tsx            → Clerk auth + user profile context
│   └── NotificationContext.tsx   → Toast notifications for invitations, uploads, etc.
├── App.tsx                        → Slim: just Router + AuthProvider + routes
├── main.tsx                       → React DOM mount (unchanged)
└── App.css                        → Global styles (unchanged, extended)
```

### Route Structure

```tsx
<Routes>
  {/* Public */}
  <Route path="/login" element={<Login />} />
  <Route path="/invite/:token" element={<InviteLanding />} />

  {/* Protected (requires auth) */}
  <Route element={<AppShell />}>
    <Route path="/" element={<Navigate to="/dashboard" />} />
    <Route path="/dashboard" element={<Dashboard />} />
    <Route path="/profile" element={<Profile />} />
    <Route path="/profile/documents" element={<ProfileDocuments />} />
    <Route path="/transactions" element={<TransactionList />} />
    <Route path="/transactions/:id" element={<TransactionDetail />} />
    <Route path="/extraction" element={<Extraction />} />
  </Route>
</Routes>
```

---

## Implementation Phases

### Phase 1 — Foundation

**Goal**: New data models, frontend restructure, auth updates. No new UI features yet — just plumbing.

**Backend tasks:**
1. Create new Pydantic models and enums in `backend/schemas.py`:
   - `UserType`, `UserDocumentType`, `TransactionStatus`, `ParticipantStatus`
   - `AgentProfile`, `BuyerProfile`, `SellerProfile`, `LoanOfficerProfile`
   - `TransactionParticipant`, `DocumentRequirement`
   - Financial extraction schemas (5 types)
2. Create new Beanie document models in `backend/db.py`:
   - `UserProfile` (replaces `UserRecord`)
   - `Transaction`
   - `UserDocument`
   - `TransactionDocument`
3. Update `backend/auth.py`:
   - Magic link token generation and validation
   - Update `get_current_user` to work with new `UserProfile`
   - Add magic-link-based auth dependency
4. Update `backend/server.py`:
   - Initialize new Beanie document models
   - Update existing endpoints that reference `UserRecord`
5. Write unit tests for all new models
6. Write integration tests for auth + magic link flow

**Frontend tasks:**
1. Install `react-router-dom`
2. Create directory structure (`components/`, `pages/`, `hooks/`, `api/`, `types/`, `context/`)
3. Create `AppShell.tsx` (layout with navbar + sidebar)
4. Create route structure in `App.tsx` (slim router)
5. Move existing extraction UI from `App.tsx` into `pages/Extraction.tsx`
6. Create stub pages: `Dashboard.tsx`, `Profile.tsx`, `TransactionList.tsx`
7. Create `AuthContext.tsx` wrapping Clerk
8. Create TypeScript types matching new backend models

**Tests:**
- Unit: All Pydantic models, enum validation, profile completion calculation
- Integration: Auth flow with new UserProfile, magic link generation/validation
- Frontend: Route rendering, auth guards, layout shell

**Definition of done**: App runs with new models, existing extraction tool works at `/extraction`, new routes render stub pages.

---

### Phase 2 — Profile System

**Goal**: Users can create profiles with role-specific data, upload documents, and see AI extraction results.

**Backend tasks:**
1. Profile CRUD endpoints in `backend/server.py`:
   - `GET/PUT /api/profile` (shared fields)
   - `PUT /api/profile/{role}` (role-specific fields)
   - `POST /api/profile/roles` (add role)
   - `GET /api/profile/completion` (completion %)
   - `GET /api/users/{user_id}` (view other user's profile)
   - `GET /api/users/search` (search by email)
2. Profile document endpoints:
   - `POST /api/profile/documents` (upload + auto-extract)
   - `GET /api/profile/documents` (list)
   - `GET /api/profile/documents/{id}` (detail)
   - `DELETE /api/profile/documents/{id}` (remove)
   - `POST /api/profile/documents/{id}/extract` (re-extract)
   - `GET /api/profile/documents/{id}/stream` (SSE)
3. Create extraction prompts for 5 financial doc types in `backend/extractor.py`
4. Create mapping logic: extraction results → profile field population
5. File storage for user documents (local or cloud)

**Frontend tasks:**
1. `Profile.tsx` page with role-specific forms
2. `ProfileWizard.tsx` (step-by-step: personal → role → docs → review)
3. Role-specific form components (`AgentForm.tsx`, `BuyerForm.tsx`, etc.)
4. `RoleSelector.tsx` (add/remove roles from profile)
5. `ProfileDocuments.tsx` page (upload, view, extraction status)
6. `DocumentUpload.tsx` component (drag-and-drop, doc type selection)
7. `useProfile.ts` hook (profile CRUD)
8. `useDocumentUpload.ts` hook (upload + SSE extraction progress)
9. `CompletionIndicator.tsx` (profile completion % component)
10. Update `Dashboard.tsx` with profile completion prompts

**Tests:**
- Unit: Financial doc schemas, extraction → profile field mapping, completion calculation
- Integration: Profile CRUD, document upload + extraction trigger, SSE streaming
- Frontend: Profile forms per role, document upload, completion indicator

**Definition of done**: Users can sign up, select roles, fill in profile data, upload financial documents, see AI extraction results, and view their profile completion percentage.

---

### Phase 2.5 — End-to-End Test Validation

**Goal**: Create a test user with sample financial documents that validates the entire Phase 2 pipeline: upload → AI extraction → schema validation → profile field mapping → completion tracking.

**Tasks:**
1. Create sample financial PDFs in `test_docs/financial/`:
   - `sample_pre_approval.pdf` — Pre-approval letter with lender, borrower, amount, loan type, dates
   - `sample_bank_statement.pdf` — Bank statement with institution, balances, statement period, deposits
   - `sample_pay_stub.pdf` — Pay stub with employer, employee, gross/net pay, YTD, pay frequency
2. Create `backend/seed_test_user.py` script that:
   - Creates a test user "Jane Doe" (jane.doe@test.deslabs.local) with buyer + agent roles
   - Uploads each sample financial doc as a profile document
   - Triggers AI extraction on each document
   - Validates extraction results against financial schemas
   - Confirms profile fields were auto-populated (annual income, employer, pre-approval amount, etc.)
   - Prints completion % before and after to show progression
3. Add integration tests in `backend/tests/test_e2e_profile.py`:
   - Test full upload → extract → map pipeline per document type
   - Test profile completion increases after each document
   - Test duplicate detection (uploading same doc twice)
   - Test that extraction doesn't overwrite existing profile data

**Validation matrix:**
| Document | Extracts | Populates Profile Field |
|----------|----------|------------------------|
| Pre-approval letter | lender_name, approval_amount, loan_type, borrower_name | buyer_profile.pre_approval_amount, pre_approval_lender, pre_approval_status → PRE_APPROVED |
| Bank statement | institution_name, ending_balance, account_holder | user.name (if empty) |
| Pay stub | employer_name, gross_pay, pay_frequency, ytd_gross | buyer_profile.employer_name, annual_income, employment_status |

**Definition of done**: Running `python seed_test_user.py` creates a fully populated test user with extracted financial data, profile completion goes from 0% → 60%+, and all integration tests pass.

---

### Phase 3 — Transaction System

**Goal**: Agents can create transactions, invite participants, manage the "lobby", and auto-fill from profiles.

**Backend tasks:**
1. Transaction CRUD endpoints:
   - `POST /api/transactions` (create)
   - `GET /api/transactions` (list, filtered by user involvement)
   - `GET /api/transactions/{id}` (detail)
   - `PUT /api/transactions/{id}` (update status, property info)
   - `DELETE /api/transactions/{id}` (draft only)
2. Participant management endpoints:
   - `POST /api/transactions/{id}/participants` (invite by email)
   - `DELETE /api/transactions/{id}/participants/{uid}` (soft-remove)
   - `PUT /api/transactions/{id}/participants/{uid}` (change role)
3. Invitation endpoints:
   - `POST /api/invitations` (generate magic link)
   - `GET /api/invitations/{token}/validate`
   - `POST /api/invitations/{token}/accept`
   - `POST /api/invitations/{token}/profile`
   - `POST /api/invitations/{token}/upgrade`
4. Transaction document endpoints:
   - `GET /api/transactions/{id}/documents`
   - `POST /api/transactions/{id}/documents`
5. Auto-fill endpoint:
   - `POST /api/transactions/{id}/auto-fill`
   - `GET /api/transactions/{id}/completion`
6. Email notification system (invitation emails with magic links)
7. Document requirement templates (default required docs per role)

**Frontend tasks:**
1. `TransactionList.tsx` page (card view, filtered by involvement)
2. `TransactionDetail.tsx` page (lobby wrapper)
3. `TransactionLobby.tsx` (tabbed view)
4. `ParticipantSidebar.tsx` (participant list + completion indicators)
5. `OverviewTab.tsx` (property, dates, financials)
6. `DocumentsTab.tsx` (checklist with upload status per participant)
7. `ComplianceTab.tsx` (JACE integration)
8. `ActivityTab.tsx` (timeline)
9. `InviteParticipant.tsx` (email + role input → send invite)
10. `InviteLanding.tsx` (magic link → profile completion → Clerk upgrade)
11. `useTransaction.ts` hook
12. `TransactionCard.tsx` component

**Tests:**
- Unit: Transaction state machine, participant add/remove, document requirement logic
- Integration: Transaction CRUD, participant management, magic link invitation flow, auto-fill
- Frontend: Transaction list, lobby tabs, participant sidebar, invitation flow

**Definition of done**: Agents can create deals, invite buyers/sellers/loan officers, participants receive magic links, complete profiles, documents are checked against requirements, profile data auto-fills into transactions.

---

### Phase 4 — AI Chatbot Profile Builder

**Goal**: Replace/complement the wizard with a conversational AI that collects profile data through natural dialogue.

**Backend tasks:**
1. Chat endpoint: `POST /api/profile/chat`
   - System prompt knows profile schema + required fields + completion state
   - Parses user responses to extract structured data
   - Updates profile fields in real-time
   - Handles document upload prompts inline
2. Chat history: `GET /api/profile/chat/history`
3. Chat document upload: `POST /api/profile/chat/upload`
4. GPT-4o system prompt engineering for conversational profile building

**Frontend tasks:**
1. `ChatInterface.tsx` (message list, input field, file drop zone)
2. `ChatMessage.tsx` (user vs AI message bubbles)
3. `ExtractedFieldsPanel.tsx` (side panel showing profile fields updating live)
4. "Switch to form view" toggle
5. Integration into `InviteLanding.tsx` (magic link → chatbot onboarding)
6. `useChat.ts` hook (WebSocket or polling for chat)

**Tests:**
- Unit: Chat message → field extraction logic, system prompt construction
- Integration: Chat endpoint, profile field updates from chat, document upload in chat
- Frontend: Chat UI, live field updates, form view toggle

**Definition of done**: Users can complete their profile through natural conversation with an AI chatbot. The chatbot asks relevant questions based on their role, prompts for document uploads, and live-updates their profile fields as the conversation progresses.

---

## Key Technical Considerations

### Security
- Magic link tokens: signed with HMAC (reuse existing `sign_oauth_state` pattern), 24-hour expiry
- PII handling: Financial docs go through existing PII scanner; SSNs are stored as last-4 only
- File uploads: Validate file types (PDF, images), scan for malware (future), size limits
- Profile access: Users can only view other profiles within shared transactions
- Agent permissions: Only agents (or transaction creators) can add/remove participants

### Performance
- Profile completion %: Cached on UserProfile, recalculated on profile/document changes
- Transaction participant queries: Index on `participants.user_id` in Transaction collection
- File storage: Start with local filesystem (existing pattern), migrate to S3/GCS when scaling
- Extraction: Reuse existing task manager + SSE streaming for financial doc extraction

### Existing Code Impact
- `backend/db.py`: UserRecord → UserProfile (clean replacement)
- `backend/auth.py`: Update dependencies to use new model, add magic link auth
- `backend/server.py`: Update Beanie init, update existing endpoints referencing UserRecord
- `backend/schemas.py`: Add new schemas (financial extractions, enums)
- `backend/extractor.py`: Add extraction prompts for financial document types
- `frontend/src/App.tsx`: Slim down to router + providers (move everything to components/)
- `frontend/src/api.ts`: Split into `api/` directory with domain-specific modules

### Integration with Existing Features
- **Dotloop sync**: Transactions can link to Dotloop loops; participant data syncs
- **DocuSign sync**: Transaction documents can be sent for signature via DocuSign
- **JACE compliance**: Transaction compliance pulls from jurisdiction + brokerage rules
- **Property enrichment**: Transaction property address triggers Regrid lookup
- **PII scanning**: Runs on all uploaded financial documents
- **Extraction caching**: Financial doc extractions cached by file_hash + doc_type
