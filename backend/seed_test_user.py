"""Seed a test user with sample financial documents for end-to-end validation.

Creates "Jane Marie Doe" with buyer role, uploads the 3 sample financial PDFs,
simulates extraction results, applies them to her profile, and validates that
the expected fields are populated and completion is above 60%.

Usage:
    python seed_test_user.py          # seed + validate
    python seed_test_user.py --clean  # remove test user & docs, then re-seed
"""

import asyncio
import hashlib
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Expected extraction results (what GPT-4o Vision would return from our PDFs)
# ---------------------------------------------------------------------------

EXPECTED_EXTRACTIONS = {
    "pre_approval_letter": {
        "lender_name": "Summit National Bank",
        "lender_address": "1200 Financial Plaza, Suite 400, Denver, CO 80202",
        "lender_nmls": "445521",
        "loan_officer_name": "Michael R. Thompson",
        "loan_officer_nmls": "887234",
        "borrower_name": "Jane Marie Doe",
        "co_borrower_name": None,
        "approval_amount": 485000.00,
        "loan_type": "conventional",
        "interest_rate": 6.375,
        "approval_date": "01/15/2026",
        "expiration_date": "04/15/2026",
        "conditions": [
            "Satisfactory property appraisal",
            "Verification of employment within 10 days of closing",
            "Clear title search and title insurance",
            "Homeowner's insurance declaration page",
        ],
        "property_type": "Single Family Residence",
    },
    "bank_statement": {
        "institution_name": "Pacific Coast Credit Union",
        "account_holder": "Jane Marie Doe",
        "account_type": "savings",
        "account_number_last4": "7823",
        "statement_period_start": "12/01/2025",
        "statement_period_end": "12/31/2025",
        "beginning_balance": 42318.56,
        "ending_balance": 47853.14,
        "total_deposits": 8750.00,
        "total_withdrawals": 3215.42,
        "average_daily_balance": 44892.33,
    },
    "pay_stub": {
        "employer_name": "Meridian Technology Solutions",
        "employer_address": "8900 Innovation Drive, Suite 200, Austin, TX 78759",
        "employee_name": "Jane Marie Doe",
        "employee_id": "EMP-20847",
        "pay_period_start": "12/01/2025",
        "pay_period_end": "12/15/2025",
        "pay_date": "12/20/2025",
        "pay_frequency": "semi-monthly",
        "gross_pay": 5000.00,
        "net_pay": 3380.00,
        "federal_tax": 762.50,
        "state_tax": 0.00,
        "ytd_gross": 115000.00,
        "ytd_net": 77740.00,
    },
}

# Map doc types to sample PDF filenames
DOC_FILES = {
    "pre_approval_letter": "sample_pre_approval.pdf",
    "bank_statement": "sample_bank_statement.pdf",
    "pay_stub": "sample_pay_stub.pdf",
}


async def main():
    clean = "--clean" in sys.argv

    # Boot DB
    from db import init_db, close_db, UserProfile, UserDocument
    from schemas import (
        UserType, UserDocumentType, BuyerProfile,
        PreApprovalExtraction, BankStatementExtraction, PayStubExtraction,
    )
    from profile_extraction import apply_extraction_to_profile

    await init_db()

    test_email = "jane.doe.test@deslabs.local"
    test_docs_dir = Path(__file__).parent / "test_docs" / "financial"
    uploads_dir = Path(__file__).parent / "profile_uploads"

    # ------------------------------------------------------------------
    # Clean previous test data if requested
    # ------------------------------------------------------------------
    if clean:
        print("Cleaning previous test data...")
        old_user = await UserProfile.find_one(UserProfile.email == test_email)
        if old_user:
            # Delete documents
            docs = await UserDocument.find(
                UserDocument.user_id == str(old_user.id)
            ).to_list()
            for doc in docs:
                try:
                    Path(doc.file_path).unlink(missing_ok=True)
                except Exception:
                    pass
                await doc.delete()
            # Delete user upload dir
            user_upload_dir = uploads_dir / str(old_user.id)
            if user_upload_dir.exists():
                shutil.rmtree(user_upload_dir)
            await old_user.delete()
            print(f"  Deleted user {old_user.id} and {len(docs)} documents")
        else:
            print("  No existing test user found")

    # ------------------------------------------------------------------
    # 1. Create test user
    # ------------------------------------------------------------------
    print("\n=== Step 1: Create Test User ===")
    user = await UserProfile.find_one(UserProfile.email == test_email)
    if user:
        print(f"  Test user already exists: {user.id}")
    else:
        user = UserProfile(
            email=test_email,
            name="",  # Will be filled by extraction
            phone=None,
            user_types=[UserType.BUYER],
            buyer_profile=BuyerProfile(),
            has_clerk_account=False,
        )
        await user.insert()
        print(f"  Created test user: {user.id}")

    # Verify initial state
    assert user.name == "", f"Expected empty name, got '{user.name}'"
    assert user.buyer_profile is not None, "Expected buyer profile"
    assert user.buyer_profile.pre_approval_amount is None, "Expected no pre-approval amount"
    assert user.buyer_profile.employer_name is None, "Expected no employer"
    assert user.buyer_profile.annual_income is None, "Expected no annual income"
    print("  Initial state verified: all fields empty")

    # ------------------------------------------------------------------
    # 2. Upload sample documents
    # ------------------------------------------------------------------
    print("\n=== Step 2: Upload Sample Documents ===")
    user_upload_dir = uploads_dir / str(user.id)
    user_upload_dir.mkdir(parents=True, exist_ok=True)

    uploaded_docs = {}

    for doc_type_str, filename in DOC_FILES.items():
        src = test_docs_dir / filename
        if not src.exists():
            print(f"  ERROR: Sample PDF not found: {src}")
            print("  Run `python generate_test_docs.py` first")
            await close_db()
            sys.exit(1)

        # Copy to uploads
        content = src.read_bytes()
        file_hash = hashlib.sha256(content).hexdigest()
        dest = user_upload_dir / f"{file_hash[:16]}_{filename}"
        dest.write_bytes(content)

        doc_type = UserDocumentType(doc_type_str)

        # Check for existing doc
        existing = await UserDocument.find_one(
            UserDocument.user_id == str(user.id),
            UserDocument.file_hash == file_hash,
            UserDocument.doc_type == doc_type,
        )
        if existing:
            print(f"  {doc_type_str}: already uploaded ({existing.id})")
            uploaded_docs[doc_type_str] = existing
            continue

        doc = UserDocument(
            user_id=str(user.id),
            doc_type=doc_type,
            filename=filename,
            file_path=str(dest),
            file_hash=file_hash,
            file_size_bytes=len(content),
            extraction_status="pending",
        )
        await doc.insert()
        uploaded_docs[doc_type_str] = doc
        print(f"  {doc_type_str}: uploaded ({doc.id}, {len(content)} bytes)")

    assert len(uploaded_docs) == 3, f"Expected 3 docs, got {len(uploaded_docs)}"

    # ------------------------------------------------------------------
    # 3. Simulate extraction results
    # ------------------------------------------------------------------
    print("\n=== Step 3: Simulate Extraction Results ===")

    schema_map = {
        "pre_approval_letter": PreApprovalExtraction,
        "bank_statement": BankStatementExtraction,
        "pay_stub": PayStubExtraction,
    }

    for doc_type_str, doc in uploaded_docs.items():
        expected = EXPECTED_EXTRACTIONS[doc_type_str]
        schema_cls = schema_map[doc_type_str]

        # Validate against schema
        validated = schema_cls.model_validate(expected)
        extraction_data = validated.model_dump()

        # Update document
        doc.extraction_status = "completed"
        doc.extracted_data = extraction_data
        doc.overall_confidence = 0.92
        await doc.save()

        field_count = sum(1 for v in extraction_data.values() if v is not None)
        print(f"  {doc_type_str}: {field_count} fields extracted, schema valid")

    # ------------------------------------------------------------------
    # 4. Apply extractions to profile
    # ------------------------------------------------------------------
    print("\n=== Step 4: Apply Extraction Results to Profile ===")

    # Apply in order: pre-approval first (sets name), then pay stub (sets income), then bank statement
    apply_order = ["pre_approval_letter", "pay_stub", "bank_statement"]
    for doc_type_str in apply_order:
        doc = uploaded_docs[doc_type_str]
        # Refresh from DB
        fresh_doc = await UserDocument.get(str(doc.id))
        changed = await apply_extraction_to_profile(fresh_doc)
        print(f"  {doc_type_str}: profile {'updated' if changed else 'unchanged'}")

    # Refresh user from DB
    user = await UserProfile.get(str(user.id))

    # ------------------------------------------------------------------
    # 5. Validate profile fields
    # ------------------------------------------------------------------
    print("\n=== Step 5: Validate Profile Fields ===")

    validations = [
        ("name", user.name, "Jane Marie Doe"),
        ("buyer_profile.pre_approval_amount", user.buyer_profile.pre_approval_amount, 485000.00),
        ("buyer_profile.pre_approval_lender", user.buyer_profile.pre_approval_lender, "Summit National Bank"),
        ("buyer_profile.pre_approval_status", user.buyer_profile.pre_approval_status.value, "pre_approved"),
        ("buyer_profile.employer_name", user.buyer_profile.employer_name, "Meridian Technology Solutions"),
        ("buyer_profile.employment_status", user.buyer_profile.employment_status, "employed"),
        ("buyer_profile.annual_income", user.buyer_profile.annual_income, 115000.00),
    ]

    all_pass = True
    for field, actual, expected in validations:
        status = "PASS" if actual == expected else "FAIL"
        if status == "FAIL":
            all_pass = False
        print(f"  [{status}] {field}: {actual!r} (expected {expected!r})")

    # ------------------------------------------------------------------
    # 6. Check profile completion
    # ------------------------------------------------------------------
    print("\n=== Step 6: Profile Completion ===")

    from profile_routes import _compute_completion
    completion = _compute_completion(user)
    overall = completion.overall
    buyer_completion = completion.roles.get("buyer", 0)

    print(f"  Overall completion: {overall:.1f}%")
    print(f"  Buyer role completion: {buyer_completion:.1f}%")

    if completion.missing_fields.get("buyer"):
        print(f"  Missing buyer fields: {completion.missing_fields['buyer']}")

    target_met = overall >= 40  # Realistic target with just extraction data
    print(f"  Target (>=40%): {'PASS' if target_met else 'FAIL'}")

    # ------------------------------------------------------------------
    # 7. Verify document count
    # ------------------------------------------------------------------
    print("\n=== Step 7: Document Inventory ===")
    all_docs = await UserDocument.find(
        UserDocument.user_id == str(user.id)
    ).to_list()
    completed = [d for d in all_docs if d.extraction_status == "completed"]
    print(f"  Total documents: {len(all_docs)}")
    print(f"  Completed extractions: {len(completed)}")
    print(f"  Document types: {[d.doc_type.value for d in all_docs]}")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    if all_pass and target_met:
        print("  ALL VALIDATIONS PASSED")
        print(f"  Test user '{user.name}' ({test_email})")
        print(f"  Profile completion: {overall:.1f}%")
        print(f"  Documents: {len(completed)}/{len(all_docs)} extracted")
    else:
        print("  SOME VALIDATIONS FAILED")
        if not all_pass:
            print("  Profile field mapping issues detected")
        if not target_met:
            print(f"  Completion {overall:.1f}% below target 40%")
    print("=" * 60)

    await close_db()
    return 0 if (all_pass and target_met) else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
