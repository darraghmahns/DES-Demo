"""Generate sample financial PDF documents for end-to-end testing.

Creates realistic-looking financial documents that the AI extraction
pipeline can parse to validate the full upload → extract → profile flow.
"""

from fpdf import FPDF
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "test_docs" / "financial"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def create_pre_approval_letter():
    """Generate a sample pre-approval letter PDF."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Letterhead
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, "Summit National Bank", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, "1200 Financial Plaza, Suite 400", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.cell(0, 6, "Denver, CO 80202", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.cell(0, 6, "NMLS #: 445521", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(10)

    # Title
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "PRE-APPROVAL LETTER", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(8)

    # Date
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 6, "Date: 01/15/2026", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Body
    pdf.multi_cell(0, 6,
        "To Whom It May Concern:\n\n"
        "This letter confirms that the following borrower(s) have been pre-approved "
        "for a mortgage loan based on preliminary review of their financial information.\n"
    )
    pdf.ln(4)

    # Borrower info
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Borrower Information:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    fields = [
        ("Primary Borrower:", "Jane Marie Doe"),
        ("Co-Borrower:", "N/A"),
    ]
    for label, value in fields:
        pdf.cell(55, 6, label)
        pdf.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Loan details
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Loan Details:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    loan_fields = [
        ("Approved Amount:", "$485,000.00"),
        ("Loan Type:", "Conventional"),
        ("Interest Rate:", "6.375%"),
        ("Loan Term:", "30-year fixed"),
        ("Property Type:", "Single Family Residence"),
        ("Approval Date:", "01/15/2026"),
        ("Expiration Date:", "04/15/2026"),
    ]
    for label, value in loan_fields:
        pdf.cell(55, 6, label)
        pdf.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Conditions
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Conditions for Final Approval:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    conditions = [
        "1. Satisfactory property appraisal",
        "2. Verification of employment within 10 days of closing",
        "3. Clear title search and title insurance",
        "4. Homeowner's insurance declaration page",
    ]
    for c in conditions:
        pdf.cell(10, 6, "")
        pdf.cell(0, 6, c, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    # Signature
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
    pdf.cell(0, 6, "Senior Loan Officer", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, "NMLS #: 887234", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, "Summit National Bank", new_x="LMARGIN", new_y="NEXT")

    path = OUTPUT_DIR / "sample_pre_approval.pdf"
    pdf.output(str(path))
    print(f"Created: {path}")


def create_bank_statement():
    """Generate a sample bank statement PDF."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Header
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Pacific Coast Credit Union", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, "4500 Harbor Blvd, Long Beach, CA 90802", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(6)

    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, "ACCOUNT STATEMENT", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(6)

    # Account info
    pdf.set_font("Helvetica", "", 11)
    info = [
        ("Account Holder:", "Jane Marie Doe"),
        ("Account Type:", "Savings"),
        ("Account Number:", "****-****-****-7823"),
        ("Statement Period:", "12/01/2025 - 12/31/2025"),
    ]
    for label, value in info:
        pdf.cell(55, 6, label)
        pdf.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    # Summary
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Account Summary", new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(100, 100, 100)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(2)

    pdf.set_font("Helvetica", "", 11)
    summary = [
        ("Beginning Balance:", "$42,318.56"),
        ("Total Deposits:", "$8,750.00"),
        ("Total Withdrawals:", "$3,215.42"),
        ("Ending Balance:", "$47,853.14"),
        ("Average Daily Balance:", "$44,892.33"),
    ]
    for label, value in summary:
        pdf.cell(80, 7, label)
        pdf.cell(0, 7, value, new_x="LMARGIN", new_y="NEXT", align="R")
    pdf.ln(6)

    # Transaction table
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
    transactions = [
        ("12/01", "Beginning Balance", "", "", "$42,318.56"),
        ("12/03", "Direct Deposit - Employer", "", "$4,375.00", "$46,693.56"),
        ("12/05", "Online Transfer to Checking", "$1,500.00", "", "$45,193.56"),
        ("12/10", "ATM Withdrawal", "$200.00", "", "$44,993.56"),
        ("12/15", "Auto Insurance Payment", "$215.42", "", "$44,778.14"),
        ("12/17", "Direct Deposit - Employer", "", "$4,375.00", "$49,153.14"),
        ("12/20", "Rent Payment - ACH", "$1,300.00", "", "$47,853.14"),
        ("12/31", "Ending Balance", "", "", "$47,853.14"),
    ]
    for date, desc, debit, credit, bal in transactions:
        pdf.cell(28, 5, date)
        pdf.cell(80, 5, desc)
        pdf.cell(30, 5, debit, align="R")
        pdf.cell(30, 5, credit, align="R")
        pdf.cell(0, 5, bal, new_x="LMARGIN", new_y="NEXT", align="R")

    pdf.ln(10)
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(0, 5, "This statement is for informational purposes. Please review and report any discrepancies within 60 days.", new_x="LMARGIN", new_y="NEXT")

    path = OUTPUT_DIR / "sample_bank_statement.pdf"
    pdf.output(str(path))
    print(f"Created: {path}")


def create_pay_stub():
    """Generate a sample pay stub PDF."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Header
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Meridian Technology Solutions", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 5, "8900 Innovation Drive, Suite 200", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.cell(0, 5, "Austin, TX 78759", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(6)

    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, "EARNINGS STATEMENT", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(6)

    # Employee info (left) and pay info (right)
    pdf.set_font("Helvetica", "", 10)
    emp_info = [
        ("Employee Name:", "Jane Marie Doe"),
        ("Employee ID:", "EMP-20847"),
        ("Department:", "Software Engineering"),
    ]
    for label, value in emp_info:
        pdf.cell(45, 6, label)
        pdf.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    pay_info = [
        ("Pay Period:", "12/01/2025 - 12/15/2025"),
        ("Pay Date:", "12/20/2025"),
        ("Pay Frequency:", "Semi-Monthly"),
    ]
    for label, value in pay_info:
        pdf.cell(45, 6, label)
        pdf.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    # Earnings table
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
    pdf.ln(6)

    # Deductions
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Deductions", new_x="LMARGIN", new_y="NEXT")
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(80, 6, "Description")
    pdf.cell(35, 6, "Current", align="R")
    pdf.cell(0, 6, "YTD", new_x="LMARGIN", new_y="NEXT", align="R")

    pdf.set_font("Helvetica", "", 9)
    deductions = [
        ("Federal Income Tax", "$762.50", "$17,537.50"),
        ("State Income Tax (TX)", "$0.00", "$0.00"),
        ("Social Security (FICA)", "$310.00", "$7,130.00"),
        ("Medicare", "$72.50", "$1,667.50"),
        ("Health Insurance", "$175.00", "$4,025.00"),
        ("401(k) Contribution (6%)", "$300.00", "$6,900.00"),
    ]
    for desc, current, ytd in deductions:
        pdf.cell(80, 5, desc)
        pdf.cell(35, 5, current, align="R")
        pdf.cell(0, 5, ytd, new_x="LMARGIN", new_y="NEXT", align="R")

    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(80, 6, "Total Deductions")
    pdf.cell(35, 6, "$1,620.00", align="R")
    pdf.cell(0, 6, "$37,260.00", new_x="LMARGIN", new_y="NEXT", align="R")
    pdf.ln(6)

    # Net pay
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Net Pay Summary", new_x="LMARGIN", new_y="NEXT")
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(80, 8, "Net Pay (Current Period):")
    pdf.cell(0, 8, "$3,380.00", new_x="LMARGIN", new_y="NEXT", align="R")
    pdf.cell(80, 8, "Net Pay (YTD):")
    pdf.cell(0, 8, "$77,740.00", new_x="LMARGIN", new_y="NEXT", align="R")

    pdf.ln(10)
    pdf.set_font("Helvetica", "I", 8)
    pdf.cell(0, 5, "This is a confidential document. Direct deposit to account ending in 7823.", new_x="LMARGIN", new_y="NEXT")

    path = OUTPUT_DIR / "sample_pay_stub.pdf"
    pdf.output(str(path))
    print(f"Created: {path}")


if __name__ == "__main__":
    create_pre_approval_letter()
    create_bank_statement()
    create_pay_stub()
    print(f"\nAll test documents created in: {OUTPUT_DIR}")
