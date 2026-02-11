#!/usr/bin/env python3
"""Generate mock PDF documents for testing the DocExtract CLI.

Creates:
  - test_docs/sample_purchase_agreement.pdf  (3-page real estate contract)
  - test_docs/sample_foia_request.pdf         (1-page FOIA request letter)
"""

import os
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    HRFlowable,
)
from reportlab.lib import colors

OUTPUT_DIR = Path(__file__).parent / "test_docs"


def create_purchase_agreement():
    """Generate a realistic 3-page residential purchase agreement."""
    output_path = OUTPUT_DIR / "sample_purchase_agreement.pdf"
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        leftMargin=1 * inch,
        rightMargin=1 * inch,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "ContractTitle",
        parent=styles["Heading1"],
        fontSize=16,
        alignment=TA_CENTER,
        spaceAfter=6,
        textColor=colors.HexColor("#1a1a2e"),
    )
    subtitle_style = ParagraphStyle(
        "ContractSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        alignment=TA_CENTER,
        spaceAfter=18,
        textColor=colors.grey,
    )
    section_style = ParagraphStyle(
        "SectionHeader",
        parent=styles["Heading2"],
        fontSize=12,
        spaceBefore=14,
        spaceAfter=6,
        textColor=colors.HexColor("#16213e"),
        borderWidth=0,
        borderPadding=0,
    )
    body_style = ParagraphStyle(
        "ContractBody",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        alignment=TA_JUSTIFY,
        spaceAfter=8,
    )
    small_style = ParagraphStyle(
        "SmallText",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        textColor=colors.grey,
    )
    label_style = ParagraphStyle(
        "FieldLabel",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.grey,
    )

    story = []

    # === PAGE 1: Header & Parties ===
    story.append(Paragraph("RESIDENTIAL PURCHASE AGREEMENT", title_style))
    story.append(Paragraph("State of Montana — Standard Form", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1a1a2e")))
    story.append(Spacer(1, 12))

    story.append(Paragraph("SECTION 1: PARTIES TO THE AGREEMENT", section_style))
    story.append(Paragraph(
        'This Residential Purchase Agreement ("Agreement") is entered into as of '
        "<b>January 28, 2025</b> by and between the following parties:",
        body_style,
    ))

    parties_data = [
        ["", "Name(s)", "Role"],
        ["BUYER(S):", "Michael B. Curtis & Sarah A. Curtis", "Purchaser"],
        ["SELLER(S):", "Tiffany J. Selong & Jason R. Selong", "Vendor"],
    ]
    parties_table = Table(parties_data, colWidths=[1.2 * inch, 3.5 * inch, 1.3 * inch])
    parties_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f5")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
    ]))
    story.append(Spacer(1, 8))
    story.append(parties_table)

    story.append(Spacer(1, 16))
    story.append(Paragraph("SECTION 2: PROPERTY DESCRIPTION", section_style))
    story.append(Paragraph(
        "The Seller agrees to sell and the Buyer agrees to purchase the following described "
        "real property, together with all improvements, fixtures, and appurtenances:",
        body_style,
    ))

    prop_data = [
        ["Street Address:", "2100 Waterview Dr, Unit B"],
        ["City:", "Billings"],
        ["State:", "Montana (MT)"],
        ["ZIP Code:", "59101"],
        ["County:", "Yellowstone"],
        ["MLS Number:", "MT-2024-88712"],
        ["Parcel/Tax ID:", "S06-2100-0045-00B"],
        ["Legal Description:", "Lot 45, Block 12, Waterview Subdivision, Yellowstone County, MT"],
    ]
    prop_table = Table(prop_data, colWidths=[1.8 * inch, 4.2 * inch])
    prop_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#333333")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f8f8fc")),
    ]))
    story.append(Spacer(1, 8))
    story.append(prop_table)

    story.append(Spacer(1, 16))
    story.append(Paragraph(
        "The property is being sold in its present, as-is condition, subject to the inspection "
        "contingencies outlined in Section 5 of this Agreement. Buyer acknowledges that Buyer "
        "has had the opportunity to inspect the property and accepts its current condition unless "
        "otherwise specified herein.",
        body_style,
    ))

    story.append(PageBreak())

    # === PAGE 2: Financial Terms & Dates ===
    story.append(Paragraph("SECTION 3: PURCHASE PRICE AND FINANCIAL TERMS", section_style))

    fin_data = [
        ["Purchase Price:", "$485,000.00"],
        ["Earnest Money Deposit:", "$10,000.00"],
        ["Earnest Money Held By:", "First American Title"],
        ["Deposit Due Within:", "3 business days of acceptance"],
        ["Financing Type:", "Conventional Mortgage"],
        ["Down Payment:", "$97,000.00 (20%)"],
        ["Loan Amount:", "$388,000.00"],
    ]
    fin_table = Table(fin_data, colWidths=[2.2 * inch, 3.8 * inch])
    fin_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f8f8fc")),
    ]))
    story.append(Spacer(1, 8))
    story.append(fin_table)

    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "The Buyer shall secure financing within thirty (30) days of the effective date of this "
        "Agreement. If Buyer is unable to secure financing under the terms described above, "
        "Buyer may terminate this Agreement and the earnest money deposit shall be returned in "
        "full to the Buyer.",
        body_style,
    ))

    story.append(Spacer(1, 16))
    story.append(Paragraph("SECTION 4: IMPORTANT DATES", section_style))

    dates_data = [
        ["Offer Date:", "01/28/2025"],
        ["Offer Expiration:", "02/01/2025 at 5:00 PM MST"],
        ["Inspection Deadline:", "02/10/2025"],
        ["Appraisal Deadline:", "02/20/2025"],
        ["Financing Contingency:", "02/28/2025"],
        ["Closing Date:", "03/15/2025"],
        ["Possession Date:", "At closing, upon recording of deed"],
    ]
    dates_table = Table(dates_data, colWidths=[2.2 * inch, 3.8 * inch])
    dates_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f8f8fc")),
    ]))
    story.append(Spacer(1, 8))
    story.append(dates_table)

    story.append(Spacer(1, 16))
    story.append(Paragraph("SECTION 5: INSPECTION CONTINGENCY", section_style))
    story.append(Paragraph(
        "Buyer shall have until the Inspection Deadline to conduct any and all inspections of "
        "the property at Buyer's expense. Buyer may, at Buyer's sole discretion, terminate this "
        "Agreement if inspections reveal material defects. Upon termination under this section, "
        "the earnest money deposit shall be returned to the Buyer in full.",
        body_style,
    ))
    story.append(Paragraph(
        "Buyer may request repairs from Seller. Seller may accept, reject, or counter any "
        "repair request. If the parties cannot reach agreement on repairs by the Inspection "
        "Deadline, either party may terminate this Agreement.",
        body_style,
    ))

    story.append(PageBreak())

    # === PAGE 3: Agent Info & Signatures ===
    story.append(Paragraph("SECTION 6: REAL ESTATE AGENTS AND BROKERAGES", section_style))

    agent_data = [
        ["", "Name", "Brokerage", "Phone", "Email"],
        [
            "Listing Agent:",
            "Julie Henderson",
            "Engel & Volkers",
            "(406) 555-0187",
            "julie.h@evmontana.com",
        ],
        [
            "Buying Agent:",
            "Robert Chen",
            "RE/MAX Realty",
            "(406) 555-0234",
            "robert.chen@remax.com",
        ],
    ]
    agent_table = Table(
        agent_data,
        colWidths=[1.1 * inch, 1.3 * inch, 1.2 * inch, 1.2 * inch, 1.8 * inch],
    )
    agent_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f5")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
    ]))
    story.append(Spacer(1, 8))
    story.append(agent_table)

    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "Sale Commission Rate: 6% of the purchase price, to be split equally between "
        "the listing and buying brokerages (3% each).",
        body_style,
    ))

    story.append(Spacer(1, 24))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1a1a2e")))
    story.append(Spacer(1, 12))
    story.append(Paragraph("SECTION 7: SIGNATURES", section_style))
    story.append(Paragraph(
        "By signing below, the parties acknowledge that they have read, understand, and agree "
        "to all terms and conditions of this Residential Purchase Agreement.",
        body_style,
    ))
    story.append(Spacer(1, 20))

    sig_data = [
        ["Buyer: ______________________________", "Date: _______________"],
        ["Michael B. Curtis", ""],
        ["", ""],
        ["Buyer: ______________________________", "Date: _______________"],
        ["Sarah A. Curtis", ""],
        ["", ""],
        ["Seller: ______________________________", "Date: _______________"],
        ["Tiffany J. Selong", ""],
        ["", ""],
        ["Seller: ______________________________", "Date: _______________"],
        ["Jason R. Selong", ""],
    ]
    sig_table = Table(sig_data, colWidths=[3.5 * inch, 2.5 * inch])
    sig_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("FONTNAME", (0, 1), (0, 1), "Helvetica-Oblique"),
        ("FONTNAME", (0, 4), (0, 4), "Helvetica-Oblique"),
        ("FONTNAME", (0, 7), (0, 7), "Helvetica-Oblique"),
        ("FONTNAME", (0, 10), (0, 10), "Helvetica-Oblique"),
        ("TEXTCOLOR", (0, 1), (0, 1), colors.grey),
        ("TEXTCOLOR", (0, 4), (0, 4), colors.grey),
        ("TEXTCOLOR", (0, 7), (0, 7), colors.grey),
        ("TEXTCOLOR", (0, 10), (0, 10), colors.grey),
    ]))
    story.append(sig_table)

    story.append(Spacer(1, 20))
    story.append(Paragraph(
        "This agreement constitutes the entire understanding between the parties and supersedes "
        "all prior negotiations, representations, and agreements. This agreement may only be "
        "modified in writing signed by all parties.",
        small_style,
    ))

    doc.build(story)
    print(f"  Created: {output_path}")


def create_foia_request():
    """Generate a realistic 1-page FOIA request letter."""
    output_path = OUTPUT_DIR / "sample_foia_request.pdf"
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        topMargin=1 * inch,
        bottomMargin=1 * inch,
        leftMargin=1.25 * inch,
        rightMargin=1.25 * inch,
    )

    styles = getSampleStyleSheet()

    header_style = ParagraphStyle(
        "LetterHeader",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        alignment=TA_LEFT,
    )
    body_style = ParagraphStyle(
        "LetterBody",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        alignment=TA_JUSTIFY,
        spaceAfter=10,
    )
    bold_style = ParagraphStyle(
        "BoldBody",
        parent=body_style,
        fontName="Helvetica-Bold",
    )

    story = []

    # Sender info
    story.append(Paragraph("Sarah Mitchell", header_style))
    story.append(Paragraph("Springfield Daily Register", header_style))
    story.append(Paragraph("742 Evergreen Terrace", header_style))
    story.append(Paragraph("Springfield, IL 62704", header_style))
    story.append(Paragraph("Phone: (217) 555-0134", header_style))
    story.append(Paragraph("Email: s.mitchell@springfield-news.org", header_style))

    story.append(Spacer(1, 24))

    # Date
    story.append(Paragraph("January 15, 2025", header_style))

    story.append(Spacer(1, 18))

    # Recipient
    story.append(Paragraph("FOIA/PA Mail Referral Unit", header_style))
    story.append(Paragraph("Department of Homeland Security", header_style))
    story.append(Paragraph("Office of Privacy", header_style))
    story.append(Paragraph("245 Murray Lane SW, STOP-0655", header_style))
    story.append(Paragraph("Washington, DC 20528-0655", header_style))

    story.append(Spacer(1, 24))

    # Subject line
    story.append(Paragraph(
        "<b>Re: Freedom of Information Act Request</b>",
        body_style,
    ))

    story.append(Spacer(1, 12))

    # Body
    story.append(Paragraph("Dear FOIA Officer:", body_style))

    story.append(Paragraph(
        "Pursuant to the Freedom of Information Act (FOIA), 5 U.S.C. § 552, I am requesting "
        "access to and copies of the following records from the Department of Homeland Security:",
        body_style,
    ))

    story.append(Paragraph(
        "<b>Requested Records:</b> All contracts, purchase orders, invoices, and related "
        "correspondence pertaining to the procurement of border surveillance technology "
        "systems, including but not limited to: autonomous surveillance towers, ground-based "
        "radar systems, and integrated sensor platforms. This request covers all such records "
        "from the period of <b>January 1, 2023</b> through <b>December 31, 2024</b>.",
        body_style,
    ))

    story.append(Paragraph(
        "This request includes, but is not limited to, records related to contract award "
        "notices, vendor selection criteria, cost-benefit analyses, performance evaluations, "
        "and any internal memoranda discussing the effectiveness or limitations of these "
        "systems. Reference case file: 078-05-1120.",
        body_style,
    ))

    story.append(Paragraph(
        "<b>Fee Waiver Request:</b> I am a representative of the news media as defined in "
        "5 U.S.C. § 552(a)(4)(A)(ii)(II). The Springfield Daily Register is a daily newspaper "
        "serving the greater Springfield metropolitan area with a circulation of approximately "
        "45,000 readers. The information requested is sought for the purpose of disseminating "
        "information about government operations to the public. I therefore request a waiver "
        "of all fees associated with this request.",
        body_style,
    ))

    story.append(Paragraph(
        "<b>Expedited Processing:</b> I am requesting expedited processing of this FOIA request "
        "pursuant to 6 C.F.R. § 5.5(e). There is a compelling need for the expedited processing "
        "of this request as there is an urgency to inform the public concerning ongoing "
        "federal government procurement activities, particularly given recent Congressional "
        "oversight hearings on border technology spending.",
        body_style,
    ))

    story.append(Paragraph(
        "If my request is denied in whole or in part, I ask that you justify all deletions "
        "by reference to specific exemptions of the Act. I also expect you to release all "
        "segregable portions of otherwise exempt material. I reserve the right to appeal "
        "your decision to withhold any information.",
        body_style,
    ))

    story.append(Paragraph(
        "I am willing to pay fees for this request up to a maximum of <b>$250.00</b>. "
        "Please inform me if the estimated fees will exceed this amount before processing "
        "the request.",
        body_style,
    ))

    story.append(Paragraph(
        "Thank you for your consideration of this request. I look forward to receiving "
        "your response within the statutory twenty (20) business day time frame.",
        body_style,
    ))

    story.append(Spacer(1, 20))
    story.append(Paragraph("Sincerely,", body_style))
    story.append(Spacer(1, 28))
    story.append(Paragraph("<i>Sarah Mitchell</i>", body_style))
    story.append(Paragraph("Investigative Reporter", header_style))
    story.append(Paragraph("Springfield Daily Register", header_style))

    doc.build(story)
    print(f"  Created: {output_path}")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Generating mock documents...")
    create_purchase_agreement()
    create_foia_request()
    print("Done.")


if __name__ == "__main__":
    main()
