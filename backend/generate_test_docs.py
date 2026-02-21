"""Generate sample PDF documents for every document type in the system.

Creates realistic-looking documents that the AI extraction pipeline
can parse to validate the full upload -> extract -> profile flow.

Document types covered:
  1. Pre-Approval Letter
  2. Bank Statement
  3. Pay Stub
  4. Tax Return (1040)
  5. W-2
  6. Proof of Funds
  7. Driver's License
  8. Proof of Insurance
  9. Other (generic letter)
"""

from fpdf import FPDF
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "test_docs" / "financial"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# 1. Pre-Approval Letter
# ---------------------------------------------------------------------------

def create_pre_approval_letter():
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, "Summit National Bank", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, "1200 Financial Plaza, Suite 400", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.cell(0, 6, "Denver, CO 80202", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.cell(0, 6, "NMLS #: 445521", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(10)

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "PRE-APPROVAL LETTER", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(8)

    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 6, "Date: 01/15/2026", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.multi_cell(0, 6,
        "To Whom It May Concern:\n\n"
        "This letter confirms that the following borrower(s) have been pre-approved "
        "for a mortgage loan based on preliminary review of their financial information.\n"
    )
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Borrower Information:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    for label, value in [("Primary Borrower:", "Jane Marie Doe"), ("Co-Borrower:", "N/A")]:
        pdf.cell(55, 6, label)
        pdf.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Loan Details:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    for label, value in [
        ("Approved Amount:", "$485,000.00"),
        ("Loan Type:", "Conventional"),
        ("Interest Rate:", "6.375%"),
        ("Loan Term:", "30-year fixed"),
        ("Property Type:", "Single Family Residence"),
        ("Approval Date:", "01/15/2026"),
        ("Expiration Date:", "04/15/2026"),
    ]:
        pdf.cell(55, 6, label)
        pdf.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Conditions for Final Approval:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    for c in [
        "1. Satisfactory property appraisal",
        "2. Verification of employment within 10 days of closing",
        "3. Clear title search and title insurance",
        "4. Homeowner's insurance declaration page",
    ]:
        pdf.cell(10, 6, "")
        pdf.cell(0, 6, c, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    pdf.multi_cell(0, 6,
        "This pre-approval is subject to the conditions listed above and a satisfactory "
        "review of the complete loan application. This is not a commitment to lend.\n"
    )
    pdf.ln(8)
    pdf.cell(0, 6, "Sincerely,", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, "Michael R. Thompson", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 6, "Senior Loan Officer, NMLS #: 887234", new_x="LMARGIN", new_y="NEXT")

    path = OUTPUT_DIR / "sample_pre_approval.pdf"
    pdf.output(str(path))
    print(f"  Created: {path.name}")


# ---------------------------------------------------------------------------
# 2. Bank Statement
# ---------------------------------------------------------------------------

def create_bank_statement():
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Pacific Coast Credit Union", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, "4500 Harbor Blvd, Long Beach, CA 90802", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(6)

    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, "ACCOUNT STATEMENT", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(6)

    pdf.set_font("Helvetica", "", 11)
    for label, value in [
        ("Account Holder:", "Jane Marie Doe"),
        ("Account Type:", "Savings"),
        ("Account Number:", "****-****-****-7823"),
        ("Statement Period:", "12/01/2025 - 12/31/2025"),
    ]:
        pdf.cell(55, 6, label)
        pdf.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Account Summary", new_x="LMARGIN", new_y="NEXT")
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(2)

    pdf.set_font("Helvetica", "", 11)
    for label, value in [
        ("Beginning Balance:", "$42,318.56"),
        ("Total Deposits:", "$8,750.00"),
        ("Total Withdrawals:", "$3,215.42"),
        ("Ending Balance:", "$47,853.14"),
        ("Average Daily Balance:", "$44,892.33"),
    ]:
        pdf.cell(80, 7, label)
        pdf.cell(0, 7, value, new_x="LMARGIN", new_y="NEXT", align="R")
    pdf.ln(6)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Transaction Detail", new_x="LMARGIN", new_y="NEXT")
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(28, 6, "Date")
    pdf.cell(80, 6, "Description")
    pdf.cell(30, 6, "Debit", align="R")
    pdf.cell(30, 6, "Credit", align="R")
    pdf.cell(0, 6, "Balance", new_x="LMARGIN", new_y="NEXT", align="R")

    pdf.set_font("Helvetica", "", 9)
    for date, desc, debit, credit, bal in [
        ("12/01", "Beginning Balance", "", "", "$42,318.56"),
        ("12/03", "Direct Deposit - Employer", "", "$4,375.00", "$46,693.56"),
        ("12/05", "Online Transfer to Checking", "$1,500.00", "", "$45,193.56"),
        ("12/10", "ATM Withdrawal", "$200.00", "", "$44,993.56"),
        ("12/15", "Auto Insurance Payment", "$215.42", "", "$44,778.14"),
        ("12/17", "Direct Deposit - Employer", "", "$4,375.00", "$49,153.14"),
        ("12/20", "Rent Payment - ACH", "$1,300.00", "", "$47,853.14"),
        ("12/31", "Ending Balance", "", "", "$47,853.14"),
    ]:
        pdf.cell(28, 5, date)
        pdf.cell(80, 5, desc)
        pdf.cell(30, 5, debit, align="R")
        pdf.cell(30, 5, credit, align="R")
        pdf.cell(0, 5, bal, new_x="LMARGIN", new_y="NEXT", align="R")

    path = OUTPUT_DIR / "sample_bank_statement.pdf"
    pdf.output(str(path))
    print(f"  Created: {path.name}")


# ---------------------------------------------------------------------------
# 3. Pay Stub
# ---------------------------------------------------------------------------

def create_pay_stub():
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Meridian Technology Solutions", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 5, "8900 Innovation Drive, Suite 200, Austin, TX 78759", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(6)

    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, "EARNINGS STATEMENT", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(6)

    pdf.set_font("Helvetica", "", 10)
    for label, value in [
        ("Employee Name:", "Jane Marie Doe"),
        ("Employee ID:", "EMP-20847"),
        ("Department:", "Software Engineering"),
        ("Pay Period:", "12/01/2025 - 12/15/2025"),
        ("Pay Date:", "12/20/2025"),
        ("Pay Frequency:", "Semi-Monthly"),
    ]:
        pdf.cell(45, 6, label)
        pdf.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Earnings", new_x="LMARGIN", new_y="NEXT")
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(60, 6, "Description")
    pdf.cell(30, 6, "Hours", align="R")
    pdf.cell(30, 6, "Rate", align="R")
    pdf.cell(35, 6, "Current", align="R")
    pdf.cell(0, 6, "YTD", new_x="LMARGIN", new_y="NEXT", align="R")

    pdf.set_font("Helvetica", "", 9)
    pdf.cell(60, 6, "Regular Salary")
    pdf.cell(30, 6, "86.67", align="R")
    pdf.cell(30, 6, "$57.69/hr", align="R")
    pdf.cell(35, 6, "$5,000.00", align="R")
    pdf.cell(0, 6, "$115,000.00", new_x="LMARGIN", new_y="NEXT", align="R")

    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(120, 6, "")
    pdf.cell(35, 6, "---------", align="R")
    pdf.cell(0, 6, "----------", new_x="LMARGIN", new_y="NEXT", align="R")
    pdf.cell(60, 6, "Gross Pay")
    pdf.cell(60, 6, "")
    pdf.cell(35, 6, "$5,000.00", align="R")
    pdf.cell(0, 6, "$115,000.00", new_x="LMARGIN", new_y="NEXT", align="R")
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Deductions", new_x="LMARGIN", new_y="NEXT")
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(2)

    pdf.set_font("Helvetica", "", 9)
    for desc, current, ytd in [
        ("Federal Income Tax", "$762.50", "$17,537.50"),
        ("State Income Tax (TX)", "$0.00", "$0.00"),
        ("Social Security (FICA)", "$310.00", "$7,130.00"),
        ("Medicare", "$72.50", "$1,667.50"),
        ("Health Insurance", "$175.00", "$4,025.00"),
        ("401(k) Contribution (6%)", "$300.00", "$6,900.00"),
    ]:
        pdf.cell(80, 5, desc)
        pdf.cell(35, 5, current, align="R")
        pdf.cell(0, 5, ytd, new_x="LMARGIN", new_y="NEXT", align="R")
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(80, 8, "Net Pay (Current):")
    pdf.cell(0, 8, "$3,380.00", new_x="LMARGIN", new_y="NEXT", align="R")
    pdf.cell(80, 8, "Net Pay (YTD):")
    pdf.cell(0, 8, "$77,740.00", new_x="LMARGIN", new_y="NEXT", align="R")

    path = OUTPUT_DIR / "sample_pay_stub.pdf"
    pdf.output(str(path))
    print(f"  Created: {path.name}")


# ---------------------------------------------------------------------------
# 4. Tax Return (1040 summary)
# ---------------------------------------------------------------------------

def create_tax_return():
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "U.S. Individual Income Tax Return", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 12)
    pdf.cell(0, 8, "Form 1040 - Tax Year 2025", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(8)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Taxpayer Information", new_x="LMARGIN", new_y="NEXT")
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(2)

    pdf.set_font("Helvetica", "", 11)
    for label, value in [
        ("Name:", "Jane Marie Doe"),
        ("SSN:", "***-**-4523"),
        ("Filing Status:", "Single"),
        ("Address:", "456 Elm Avenue, Denver, CO 80202"),
    ]:
        pdf.cell(50, 6, label)
        pdf.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Income", new_x="LMARGIN", new_y="NEXT")
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(2)

    pdf.set_font("Helvetica", "", 11)
    for label, value in [
        ("1. Wages, salaries, tips (W-2):", "$120,000.00"),
        ("2a. Tax-exempt interest:", "$0.00"),
        ("2b. Taxable interest:", "$342.18"),
        ("3a. Qualified dividends:", "$0.00"),
        ("3b. Ordinary dividends:", "$128.50"),
        ("7. Capital gain or (loss):", "$0.00"),
        ("8. Other income:", "$0.00"),
        ("9. Total income:", "$120,470.68"),
    ]:
        pdf.cell(100, 6, label)
        pdf.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT", align="R")
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Adjustments & Deductions", new_x="LMARGIN", new_y="NEXT")
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(2)

    pdf.set_font("Helvetica", "", 11)
    for label, value in [
        ("10. Adjustments to income:", "$0.00"),
        ("11. Adjusted gross income:", "$120,470.68"),
        ("12. Standard deduction:", "$14,600.00"),
        ("13. Qualified business income deduction:", "$0.00"),
        ("14. Total deductions:", "$14,600.00"),
        ("15. Taxable income:", "$105,870.68"),
    ]:
        pdf.cell(100, 6, label)
        pdf.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT", align="R")
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Tax & Payments", new_x="LMARGIN", new_y="NEXT")
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(2)

    pdf.set_font("Helvetica", "", 11)
    for label, value in [
        ("16. Tax:", "$18,234.00"),
        ("24. Total tax:", "$18,234.00"),
        ("25. Federal income tax withheld:", "$19,100.00"),
        ("34. Total payments:", "$19,100.00"),
        ("35. Overpaid:", "$866.00"),
        ("36a. Refunded to you:", "$866.00"),
    ]:
        pdf.cell(100, 6, label)
        pdf.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT", align="R")

    path = OUTPUT_DIR / "sample_tax_return.pdf"
    pdf.output(str(path))
    print(f"  Created: {path.name}")


# ---------------------------------------------------------------------------
# 5. W-2
# ---------------------------------------------------------------------------

def create_w2():
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "Form W-2 Wage and Tax Statement", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 7, "Tax Year 2025 | Copy B - To Be Filed With Employee's Federal Tax Return", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(8)

    # Employer info
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "Employer Information", new_x="LMARGIN", new_y="NEXT")
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 10)
    for label, value in [
        ("Employer Name:", "Meridian Technology Solutions"),
        ("Employer EIN:", "84-2957301"),
        ("Employer Address:", "8900 Innovation Drive, Suite 200, Austin, TX 78759"),
    ]:
        pdf.cell(50, 6, label)
        pdf.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Employee info
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "Employee Information", new_x="LMARGIN", new_y="NEXT")
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 10)
    for label, value in [
        ("Employee Name:", "Jane Marie Doe"),
        ("Employee SSN:", "***-**-4523"),
        ("Employee Address:", "456 Elm Avenue, Denver, CO 80202"),
    ]:
        pdf.cell(50, 6, label)
        pdf.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    # Boxes
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Wage and Tax Data", new_x="LMARGIN", new_y="NEXT")
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(2)

    pdf.set_font("Helvetica", "", 10)
    for box, label, value in [
        ("Box 1", "Wages, tips, other compensation", "$120,000.00"),
        ("Box 2", "Federal income tax withheld", "$19,100.00"),
        ("Box 3", "Social security wages", "$120,000.00"),
        ("Box 4", "Social security tax withheld", "$7,440.00"),
        ("Box 5", "Medicare wages and tips", "$120,000.00"),
        ("Box 6", "Medicare tax withheld", "$1,740.00"),
        ("Box 12a", "401(k) contributions (Code D)", "$7,200.00"),
        ("Box 16", "State wages, tips, etc.", "$120,000.00"),
        ("Box 17", "State income tax", "$0.00"),
    ]:
        pdf.cell(20, 6, box)
        pdf.cell(80, 6, label)
        pdf.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT", align="R")
    pdf.ln(4)

    pdf.set_font("Helvetica", "", 10)
    for label, value in [
        ("State:", "TX"),
        ("State ID:", "84-2957301"),
    ]:
        pdf.cell(50, 6, label)
        pdf.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")

    path = OUTPUT_DIR / "sample_w2.pdf"
    pdf.output(str(path))
    print(f"  Created: {path.name}")


# ---------------------------------------------------------------------------
# 6. Proof of Funds
# ---------------------------------------------------------------------------

def create_proof_of_funds():
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, "Pacific Coast Credit Union", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, "4500 Harbor Blvd, Long Beach, CA 90802", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.cell(0, 6, "Phone: (562) 555-0100", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(10)

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "PROOF OF FUNDS LETTER", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(8)

    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 6, "Date: 01/18/2026", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.multi_cell(0, 6,
        "To Whom It May Concern:\n\n"
        "This letter serves as verification that the following account holder maintains "
        "sufficient funds on deposit with Pacific Coast Credit Union.\n"
    )
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Account Details:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    for label, value in [
        ("Account Holder:", "Jane Marie Doe"),
        ("Account Type:", "Savings Account"),
        ("Available Funds:", "$47,853.14"),
        ("Currency:", "USD"),
        ("As of Date:", "01/18/2026"),
    ]:
        pdf.cell(55, 6, label)
        pdf.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    pdf.multi_cell(0, 6,
        "The above-referenced funds are immediately available and unencumbered. "
        "This verification is provided at the request of the account holder and does not "
        "constitute a guarantee or commitment by Pacific Coast Credit Union.\n\n"
        "If you require additional information, please contact our office.\n"
    )
    pdf.ln(8)
    pdf.cell(0, 6, "Sincerely,", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, "Sarah L. Martinez", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 6, "Branch Manager", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, "Pacific Coast Credit Union", new_x="LMARGIN", new_y="NEXT")

    path = OUTPUT_DIR / "sample_proof_of_funds.pdf"
    pdf.output(str(path))
    print(f"  Created: {path.name}")


# ---------------------------------------------------------------------------
# 7. Driver's License
# ---------------------------------------------------------------------------

def create_drivers_license():
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "STATE OF COLORADO", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, "DRIVER LICENSE", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(8)

    # Draw a border box for the license card
    pdf.rect(20, pdf.get_y(), 170, 90)
    y_start = pdf.get_y() + 5
    pdf.set_y(y_start)

    pdf.set_font("Helvetica", "", 10)
    fields = [
        ("DL Number:", "CO-2025-087234"),
        ("Class:", "R (Regular)"),
        ("Name:", "DOE, JANE MARIE"),
        ("Address:", "456 Elm Avenue"),
        ("City/State/ZIP:", "Denver, CO 80202"),
        ("Date of Birth:", "03/15/1990"),
        ("Sex:", "F"),
        ("Height:", "5-06"),
        ("Eyes:", "BRN"),
        ("Issue Date:", "06/01/2024"),
        ("Expiration Date:", "03/15/2029"),
    ]
    for label, value in fields:
        pdf.cell(10, 6, "")
        pdf.cell(45, 6, label)
        pdf.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")

    pdf.ln(15)
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(0, 5, "This is a sample document for testing purposes only.", new_x="LMARGIN", new_y="NEXT", align="C")

    path = OUTPUT_DIR / "sample_drivers_license.pdf"
    pdf.output(str(path))
    print(f"  Created: {path.name}")


# ---------------------------------------------------------------------------
# 8. Proof of Insurance
# ---------------------------------------------------------------------------

def create_proof_of_insurance():
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, "Rocky Mountain Insurance Group", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, "2200 Insurance Way, Denver, CO 80203", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.cell(0, 6, "Phone: (303) 555-0200 | Fax: (303) 555-0201", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(10)

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "HOMEOWNER'S INSURANCE DECLARATION", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(8)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Policy Information:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    for label, value in [
        ("Policy Number:", "HO-2026-445521"),
        ("Policy Type:", "HO-3 (Special Form)"),
        ("Named Insured:", "Jane Marie Doe"),
        ("Mailing Address:", "456 Elm Avenue, Denver, CO 80202"),
        ("Policy Period:", "02/01/2026 - 02/01/2027"),
    ]:
        pdf.cell(55, 6, label)
        pdf.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Property Information:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    for label, value in [
        ("Property Address:", "456 Elm Avenue, Denver, CO 80202"),
        ("Property Type:", "Single Family Residence"),
        ("Year Built:", "2005"),
        ("Square Footage:", "2,150"),
    ]:
        pdf.cell(55, 6, label)
        pdf.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Coverage Summary:", new_x="LMARGIN", new_y="NEXT")
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(2)

    pdf.set_font("Helvetica", "", 11)
    for label, value in [
        ("Dwelling (Coverage A):", "$450,000"),
        ("Other Structures (Coverage B):", "$45,000"),
        ("Personal Property (Coverage C):", "$225,000"),
        ("Loss of Use (Coverage D):", "$90,000"),
        ("Personal Liability (Coverage E):", "$300,000"),
        ("Medical Payments (Coverage F):", "$5,000"),
        ("Deductible:", "$2,500"),
        ("Annual Premium:", "$1,842.00"),
    ]:
        pdf.cell(80, 6, label)
        pdf.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT", align="R")
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Mortgage Clause:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 6,
        "Summit National Bank, ISAOA/ATIMA\n"
        "1200 Financial Plaza, Suite 400\n"
        "Denver, CO 80202\n"
        "Loan #: MTG-2026-00234"
    )

    path = OUTPUT_DIR / "sample_proof_of_insurance.pdf"
    pdf.output(str(path))
    print(f"  Created: {path.name}")


# ---------------------------------------------------------------------------
# 9. Other (generic letter)
# ---------------------------------------------------------------------------

def create_other_document():
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "Supplementary Document", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(8)

    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 6, "Date: 01/20/2026", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.multi_cell(0, 6,
        "To Whom It May Concern:\n\n"
        "This document serves as additional supporting material for the real estate "
        "transaction involving Jane Marie Doe at 456 Elm Avenue, Denver, CO 80202.\n\n"
        "The undersigned confirms that all information provided in the transaction "
        "documentation is accurate and complete to the best of their knowledge.\n\n"
        "This letter may be used for verification purposes in connection with the "
        "purchase of the above-referenced property.\n"
    )
    pdf.ln(8)

    pdf.cell(0, 6, "Sincerely,", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, "Jane Marie Doe", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 6, "456 Elm Avenue, Denver, CO 80202", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, "(303) 555-7890", new_x="LMARGIN", new_y="NEXT")

    path = OUTPUT_DIR / "sample_other.pdf"
    pdf.output(str(path))
    print(f"  Created: {path.name}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Generating sample document library...")
    print()
    create_pre_approval_letter()
    create_bank_statement()
    create_pay_stub()
    create_tax_return()
    create_w2()
    create_proof_of_funds()
    create_drivers_license()
    create_proof_of_insurance()
    create_other_document()
    print(f"\nAll 9 documents created in: {OUTPUT_DIR}")
