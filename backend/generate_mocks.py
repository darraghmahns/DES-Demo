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
        "<b>March 4, 2025</b> by and between the following parties:",
        body_style,
    ))

    parties_data = [
        ["", "Name(s)", "Role"],
        ["BUYER(S):", "Daniel R. Whitfield & Karen M. Whitfield", "Purchaser"],
        ["SELLER(S):", "Gregory T. Navarro & Lisa A. Navarro", "Vendor"],
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
        ["Street Address:", "4738 Ridgeline Ct"],
        ["City:", "Helena"],
        ["State:", "Montana (MT)"],
        ["ZIP Code:", "59601"],
        ["County:", "Lewis and Clark"],
        ["MLS Number:", "MT-2025-14209"],
        ["Parcel/Tax ID:", "R03-4738-0091-00"],
        ["Legal Description:", "Lot 91, Block 7, Ridgeline Estates, Lewis and Clark County, MT"],
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
        ["Purchase Price:", "$612,500.00"],
        ["Earnest Money Deposit:", "$15,000.00"],
        ["Earnest Money Held By:", "Montana Title & Escrow"],
        ["Deposit Due Within:", "3 business days of acceptance"],
        ["Financing Type:", "Conventional Mortgage"],
        ["Down Payment:", "$122,500.00 (20%)"],
        ["Loan Amount:", "$490,000.00"],
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
        ["Offer Date:", "03/04/2025"],
        ["Offer Expiration:", "03/08/2025 at 5:00 PM MST"],
        ["Inspection Deadline:", "03/18/2025"],
        ["Appraisal Deadline:", "03/25/2025"],
        ["Financing Contingency:", "04/03/2025"],
        ["Closing Date:", "04/18/2025"],
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
            "Patricia Owens",
            "Windermere Real Estate",
            "(406) 555-0312",
            "p.owens@windermere-mt.com",
        ],
        [
            "Buying Agent:",
            "Marcus Delgado",
            "Berkshire Hathaway",
            "(406) 555-0478",
            "marcus.d@bhhsmt.com",
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
        ["Daniel R. Whitfield", ""],
        ["", ""],
        ["Buyer: ______________________________", "Date: _______________"],
        ["Karen M. Whitfield", ""],
        ["", ""],
        ["Seller: ______________________________", "Date: _______________"],
        ["Gregory T. Navarro", ""],
        ["", ""],
        ["Seller: ______________________________", "Date: _______________"],
        ["Lisa A. Navarro", ""],
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
    story.append(Paragraph("James Callahan", header_style))
    story.append(Paragraph("Capital City Tribune", header_style))
    story.append(Paragraph("310 Wabash Ave, Suite 400", header_style))
    story.append(Paragraph("Indianapolis, IN 46204", header_style))
    story.append(Paragraph("Phone: (317) 555-0261", header_style))
    story.append(Paragraph("Email: j.callahan@capitaltribune.com", header_style))

    story.append(Spacer(1, 24))

    # Date
    story.append(Paragraph("February 3, 2025", header_style))

    story.append(Spacer(1, 18))

    # Recipient
    story.append(Paragraph("FOIA/PA Mail Referral Unit", header_style))
    story.append(Paragraph("Department of Justice", header_style))
    story.append(Paragraph("Office of Information Policy", header_style))
    story.append(Paragraph("441 G Street NW, 6th Floor", header_style))
    story.append(Paragraph("Washington, DC 20530", header_style))

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
        "correspondence pertaining to the procurement of automated license plate reader (ALPR) "
        "systems, including but not limited to: mobile ALPR units, fixed-mount camera arrays, "
        "and cloud-based analytics platforms. This request covers all such records "
        "from the period of <b>June 1, 2023</b> through <b>May 31, 2025</b>.",
        body_style,
    ))

    story.append(Paragraph(
        "This request includes, but is not limited to, records related to contract award "
        "notices, vendor selection criteria, cost-benefit analyses, performance evaluations, "
        "and any internal memoranda discussing the effectiveness or limitations of these "
        "systems. Reference case file: 041-12-3387.",
        body_style,
    ))

    story.append(Paragraph(
        "<b>Fee Waiver Request:</b> I am a representative of the news media as defined in "
        "5 U.S.C. § 552(a)(4)(A)(ii)(II). The Capital City Tribune is a daily newspaper "
        "serving the greater Indianapolis metropolitan area with a circulation of approximately "
        "62,000 readers. The information requested is sought for the purpose of disseminating "
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
        "I am willing to pay fees for this request up to a maximum of <b>$500.00</b>. "
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
    story.append(Paragraph("<i>James Callahan</i>", body_style))
    story.append(Paragraph("Senior Investigative Correspondent", header_style))
    story.append(Paragraph("Capital City Tribune", header_style))

    doc.build(story)
    print(f"  Created: {output_path}")


def create_purchase_agreement_2():
    """Generate a second purchase agreement — California condo."""
    output_path = OUTPUT_DIR / "sample_condo_offer.pdf"
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
        "ContractTitle2",
        parent=styles["Heading1"],
        fontSize=16,
        alignment=TA_CENTER,
        spaceAfter=6,
        textColor=colors.HexColor("#1a1a2e"),
    )
    subtitle_style = ParagraphStyle(
        "ContractSubtitle2",
        parent=styles["Normal"],
        fontSize=10,
        alignment=TA_CENTER,
        spaceAfter=18,
        textColor=colors.grey,
    )
    section_style = ParagraphStyle(
        "SectionHeader2",
        parent=styles["Heading2"],
        fontSize=12,
        spaceBefore=14,
        spaceAfter=6,
        textColor=colors.HexColor("#16213e"),
        borderWidth=0,
        borderPadding=0,
    )
    body_style = ParagraphStyle(
        "ContractBody2",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        alignment=TA_JUSTIFY,
        spaceAfter=8,
    )
    small_style = ParagraphStyle(
        "SmallText2",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        textColor=colors.grey,
    )

    story = []

    # === PAGE 1: Header & Parties ===
    story.append(Paragraph("RESIDENTIAL PURCHASE AGREEMENT", title_style))
    story.append(Paragraph("State of California — Standard Form RPA-CA", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1a1a2e")))
    story.append(Spacer(1, 12))

    story.append(Paragraph("SECTION 1: PARTIES TO THE AGREEMENT", section_style))
    story.append(Paragraph(
        'This Residential Purchase Agreement ("Agreement") is entered into as of '
        "<b>January 15, 2025</b> by and between the following parties:",
        body_style,
    ))

    parties_data = [
        ["", "Name(s)", "Role"],
        ["BUYER(S):", "Sarah J. Mitchell", "Purchaser"],
        ["SELLER(S):", "Robert Chen & Amy Chen", "Vendor"],
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
        ["Street Address:", "2150 Ocean Park Blvd, Unit #304"],
        ["City:", "Santa Monica"],
        ["State:", "California (CA)"],
        ["ZIP Code:", "90405"],
        ["County:", "Los Angeles"],
        ["MLS Number:", "CA-2025-88412"],
        ["Parcel/Tax ID:", "4276-021-034"],
        ["Legal Description:", "Unit 304, Building C, Ocean Park Towers, Book 2847, Page 112"],
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

    story.append(PageBreak())

    # === PAGE 2: Financial Terms & Dates ===
    story.append(Paragraph("SECTION 3: PURCHASE PRICE AND FINANCIAL TERMS", section_style))

    fin_data = [
        ["Purchase Price:", "$875,000.00"],
        ["Earnest Money Deposit:", "$25,000.00"],
        ["Earnest Money Held By:", "Pacific Coast Escrow"],
        ["Deposit Due Within:", "5 business days of acceptance"],
        ["Financing Type:", "FHA Mortgage"],
        ["Down Payment:", "$43,750.00 (5%)"],
        ["Loan Amount:", "$831,250.00"],
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

    story.append(Spacer(1, 16))
    story.append(Paragraph("SECTION 4: IMPORTANT DATES", section_style))

    dates_data = [
        ["Offer Date:", "01/15/2025"],
        ["Offer Expiration:", "01/19/2025 at 11:59 PM PST"],
        ["Inspection Deadline:", "01/29/2025"],
        ["Appraisal Deadline:", "02/05/2025"],
        ["Financing Contingency:", "02/14/2025"],
        ["Closing Date:", "02/28/2025"],
        ["Possession Date:", "At closing"],
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
    story.append(Paragraph("SECTION 5: AGENT INFORMATION", section_style))

    agent_data = [
        ["", "Name", "Brokerage", "Phone", "Email"],
        [
            "Listing Agent:",
            "Jennifer Wu",
            "Keller Williams Realty",
            "(310) 555-8821",
            "jennifer.wu@kwrealty.com",
        ],
        [
            "Buying Agent:",
            "David Okafor",
            "Compass Real Estate",
            "(310) 555-4417",
            "d.okafor@compass.com",
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
        "Sale Commission Rate: 5% of the purchase price, to be split between "
        "the listing brokerage (2.5%) and buying brokerage (2.5%).",
        body_style,
    ))

    story.append(Spacer(1, 20))
    story.append(Paragraph(
        "This agreement constitutes the entire understanding between the parties.",
        small_style,
    ))

    doc.build(story)
    print(f"  Created: {output_path}")


def create_purchase_agreement_3():
    """Generate a third purchase agreement — Texas ranch property."""
    output_path = OUTPUT_DIR / "sample_ranch_contract.pdf"
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
        "ContractTitle3",
        parent=styles["Heading1"],
        fontSize=16,
        alignment=TA_CENTER,
        spaceAfter=6,
        textColor=colors.HexColor("#1a1a2e"),
    )
    subtitle_style = ParagraphStyle(
        "ContractSubtitle3",
        parent=styles["Normal"],
        fontSize=10,
        alignment=TA_CENTER,
        spaceAfter=18,
        textColor=colors.grey,
    )
    section_style = ParagraphStyle(
        "SectionHeader3",
        parent=styles["Heading2"],
        fontSize=12,
        spaceBefore=14,
        spaceAfter=6,
        textColor=colors.HexColor("#16213e"),
        borderWidth=0,
        borderPadding=0,
    )
    body_style = ParagraphStyle(
        "ContractBody3",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        alignment=TA_JUSTIFY,
        spaceAfter=8,
    )

    story = []

    story.append(Paragraph("RESIDENTIAL PURCHASE AGREEMENT", title_style))
    story.append(Paragraph("State of Texas — TREC Standard Form", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1a1a2e")))
    story.append(Spacer(1, 12))

    story.append(Paragraph("SECTION 1: PARTIES", section_style))
    story.append(Paragraph(
        'This Residential Purchase Agreement is entered into as of '
        "<b>February 20, 2025</b> by and between:",
        body_style,
    ))

    parties_data = [
        ["", "Name(s)", "Role"],
        ["BUYER(S):", "Michael & Angela Torres", "Purchaser"],
        ["SELLER(S):", "William H. Crawford", "Vendor"],
    ]
    parties_table = Table(parties_data, colWidths=[1.2 * inch, 3.5 * inch, 1.3 * inch])
    parties_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f5")),
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

    prop_data = [
        ["Street Address:", "8901 Lonesome Oak Rd"],
        ["City:", "Dripping Springs"],
        ["State:", "Texas (TX)"],
        ["ZIP Code:", "78620"],
        ["County:", "Hays"],
        ["MLS Number:", "TX-2025-55731"],
        ["Parcel/Tax ID:", "R518273-0040-00"],
    ]
    prop_table = Table(prop_data, colWidths=[1.8 * inch, 4.2 * inch])
    prop_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f8f8fc")),
    ]))
    story.append(Spacer(1, 8))
    story.append(prop_table)

    story.append(Spacer(1, 16))
    story.append(Paragraph("SECTION 3: FINANCIAL TERMS", section_style))

    fin_data = [
        ["Purchase Price:", "$1,250,000.00"],
        ["Earnest Money:", "$40,000.00"],
        ["Earnest Money Held By:", "Austin Title Company"],
        ["Financing Type:", "Conventional Mortgage"],
        ["Down Payment:", "$250,000.00 (20%)"],
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

    story.append(Spacer(1, 16))
    story.append(Paragraph("SECTION 4: KEY DATES", section_style))

    dates_data = [
        ["Contract Date:", "02/20/2025"],
        ["Offer Expiration:", "02/24/2025"],
        ["Inspection Deadline:", "03/06/2025"],
        ["Closing Date:", "03/28/2025"],
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
    story.append(Paragraph("SECTION 5: AGENTS", section_style))

    agent_data = [
        ["", "Name", "Brokerage", "Phone"],
        ["Listing Agent:", "Hector Ramirez", "RE/MAX Central", "(512) 555-3301"],
        ["Buying Agent:", "Laura Bennett", "Sotheby's Intl.", "(512) 555-7722"],
    ]
    agent_table = Table(
        agent_data,
        colWidths=[1.2 * inch, 1.6 * inch, 1.6 * inch, 1.6 * inch],
    )
    agent_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f5")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
    ]))
    story.append(Spacer(1, 8))
    story.append(agent_table)

    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "Sale Commission Rate: 5.5% of the purchase price.",
        body_style,
    ))

    doc.build(story)
    print(f"  Created: {output_path}")


def create_dallas_purchase():
    """Generate a Dallas TX purchase agreement for Regrid integration testing."""
    output_path = OUTPUT_DIR / "sample_dallas_purchase.pdf"
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
        "ContractTitle4",
        parent=styles["Heading1"],
        fontSize=16,
        alignment=TA_CENTER,
        spaceAfter=6,
        textColor=colors.HexColor("#1a1a2e"),
    )
    subtitle_style = ParagraphStyle(
        "ContractSubtitle4",
        parent=styles["Normal"],
        fontSize=10,
        alignment=TA_CENTER,
        spaceAfter=18,
        textColor=colors.grey,
    )
    section_style = ParagraphStyle(
        "SectionHeader4",
        parent=styles["Heading2"],
        fontSize=12,
        spaceBefore=14,
        spaceAfter=6,
        textColor=colors.HexColor("#16213e"),
        borderWidth=0,
        borderPadding=0,
    )
    body_style = ParagraphStyle(
        "ContractBody4",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        alignment=TA_JUSTIFY,
        spaceAfter=8,
    )
    small_style = ParagraphStyle(
        "SmallText4",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        textColor=colors.grey,
    )

    story = []

    # === PAGE 1: Header & Parties ===
    story.append(Paragraph("RESIDENTIAL PURCHASE AGREEMENT", title_style))
    story.append(Paragraph("State of Texas \u2014 TREC Standard Form", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1a1a2e")))
    story.append(Spacer(1, 12))

    story.append(Paragraph("SECTION 1: PARTIES TO THE AGREEMENT", section_style))
    story.append(Paragraph(
        'This Residential Purchase Agreement ("Agreement") is entered into as of '
        "<b>February 10, 2025</b> by and between the following parties:",
        body_style,
    ))

    parties_data = [
        ["", "Name(s)", "Role"],
        ["BUYER(S):", "James R. Thompson & Maria L. Thompson", "Purchaser"],
        ["SELLER(S):", "Robert A. Chen & Susan K. Chen", "Vendor"],
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
        ["Street Address:", "5818 Diana Dr"],
        ["City:", "Dallas"],
        ["State:", "Texas (TX)"],
        ["ZIP Code:", "75043"],
        ["County:", "Dallas"],
        ["MLS Number:", "TX-2025-88412"],
        ["Parcel/Tax ID:", "26447580030140000"],
        ["Legal Description:", "Lot 14, Block 3, Northeast Dallas, Dallas County, TX"],
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
        ["Earnest Money Deposit:", "$12,000.00"],
        ["Earnest Money Held By:", "Lone Star Title Company"],
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
        ["Offer Date:", "02/10/2025"],
        ["Offer Expiration:", "02/14/2025 at 5:00 PM CST"],
        ["Inspection Deadline:", "02/24/2025"],
        ["Appraisal Deadline:", "03/03/2025"],
        ["Financing Contingency:", "03/12/2025"],
        ["Closing Date:", "03/28/2025"],
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
        "the property at Buyer\u2019s expense. Buyer may, at Buyer\u2019s sole discretion, terminate this "
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
            "Jennifer Walsh",
            "Keller Williams Realty",
            "(214) 555-0234",
            "j.walsh@kwdallas.com",
        ],
        [
            "Buying Agent:",
            "David Martinez",
            "RE/MAX Dallas",
            "(972) 555-0891",
            "d.martinez@remaxdfw.com",
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
        ["James R. Thompson", ""],
        ["", ""],
        ["Buyer: ______________________________", "Date: _______________"],
        ["Maria L. Thompson", ""],
        ["", ""],
        ["Seller: ______________________________", "Date: _______________"],
        ["Robert A. Chen", ""],
        ["", ""],
        ["Seller: ______________________________", "Date: _______________"],
        ["Susan K. Chen", ""],
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


def create_foia_request_2():
    """Generate a second FOIA request — EPA environmental records."""
    output_path = OUTPUT_DIR / "sample_epa_foia.pdf"
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
        "LetterHeader2",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        alignment=TA_LEFT,
    )
    body_style = ParagraphStyle(
        "LetterBody2",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        alignment=TA_JUSTIFY,
        spaceAfter=10,
    )

    story = []

    # Sender
    story.append(Paragraph("Dr. Maria Vasquez", header_style))
    story.append(Paragraph("Center for Environmental Accountability", header_style))
    story.append(Paragraph("1200 K Street NW, Suite 800", header_style))
    story.append(Paragraph("Washington, DC 20005", header_style))
    story.append(Paragraph("Phone: (202) 555-4891", header_style))
    story.append(Paragraph("Email: m.vasquez@envaccountability.org", header_style))

    story.append(Spacer(1, 24))
    story.append(Paragraph("January 8, 2025", header_style))
    story.append(Spacer(1, 18))

    # Recipient
    story.append(Paragraph("National FOIA Office", header_style))
    story.append(Paragraph("Environmental Protection Agency", header_style))
    story.append(Paragraph("1200 Pennsylvania Avenue NW", header_style))
    story.append(Paragraph("Washington, DC 20460", header_style))

    story.append(Spacer(1, 24))
    story.append(Paragraph("<b>Re: Freedom of Information Act Request</b>", body_style))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Dear FOIA Officer:", body_style))

    story.append(Paragraph(
        "Pursuant to the Freedom of Information Act, 5 U.S.C. § 552, I hereby request "
        "access to the following records maintained by the Environmental Protection Agency:",
        body_style,
    ))

    story.append(Paragraph(
        "<b>Requested Records:</b> All inspection reports, enforcement actions, notices of "
        "violation, consent decrees, and related correspondence pertaining to per- and "
        "polyfluoroalkyl substances (PFAS) contamination at military installations and "
        "surrounding communities. This request covers records from the period of "
        "<b>January 1, 2022</b> through <b>December 31, 2024</b>.",
        body_style,
    ))

    story.append(Paragraph(
        "Specifically, I request documents related to the following installations: "
        "Joint Base McGuire-Dix-Lakehurst (NJ), Peterson Space Force Base (CO), "
        "and Naval Air Station Pensacola (FL). This includes any communications between "
        "EPA regional offices and the Department of Defense regarding remediation timelines "
        "and public health advisories. Reference tracking number: EPA-HQ-2025-000847.",
        body_style,
    ))

    story.append(Paragraph(
        "<b>Fee Waiver Request:</b> I am requesting a fee waiver on the basis that "
        "disclosure of this information is in the public interest. The Center for "
        "Environmental Accountability is a 501(c)(3) nonprofit organization dedicated "
        "to transparency in environmental enforcement. The requested information will be "
        "used for public education and policy research, not for commercial purposes.",
        body_style,
    ))

    story.append(Paragraph(
        "I am willing to pay fees up to <b>$250.00</b> if the fee waiver is denied. "
        "Please contact me before processing if estimated fees exceed this amount.",
        body_style,
    ))

    story.append(Paragraph(
        "Thank you for your prompt attention to this request.",
        body_style,
    ))

    story.append(Spacer(1, 20))
    story.append(Paragraph("Sincerely,", body_style))
    story.append(Spacer(1, 28))
    story.append(Paragraph("<i>Dr. Maria Vasquez</i>", body_style))
    story.append(Paragraph("Director of Research", header_style))
    story.append(Paragraph("Center for Environmental Accountability", header_style))

    doc.build(story)
    print(f"  Created: {output_path}")


def create_foia_request_3():
    """Generate a third FOIA request — FBI records request."""
    output_path = OUTPUT_DIR / "sample_fbi_records_request.pdf"
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
        "LetterHeader3",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        alignment=TA_LEFT,
    )
    body_style = ParagraphStyle(
        "LetterBody3",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        alignment=TA_JUSTIFY,
        spaceAfter=10,
    )

    story = []

    # Sender
    story.append(Paragraph("Thomas K. Reeves, Esq.", header_style))
    story.append(Paragraph("Reeves & Morrison LLP", header_style))
    story.append(Paragraph("55 West Monroe Street, 38th Floor", header_style))
    story.append(Paragraph("Chicago, IL 60603", header_style))
    story.append(Paragraph("Phone: (312) 555-9104", header_style))
    story.append(Paragraph("Email: t.reeves@reevesmorrison.com", header_style))

    story.append(Spacer(1, 24))
    story.append(Paragraph("March 12, 2025", header_style))
    story.append(Spacer(1, 18))

    # Recipient
    story.append(Paragraph("Record/Information Dissemination Section", header_style))
    story.append(Paragraph("Federal Bureau of Investigation", header_style))
    story.append(Paragraph("170 Marcel Drive", header_style))
    story.append(Paragraph("Winchester, VA 22602", header_style))

    story.append(Spacer(1, 24))
    story.append(Paragraph("<b>Re: Freedom of Information Act Request</b>", body_style))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Dear FOIA Officer:", body_style))

    story.append(Paragraph(
        "Under the Freedom of Information Act, 5 U.S.C. § 552, I am writing on behalf "
        "of my client to request the following records from the Federal Bureau of Investigation:",
        body_style,
    ))

    story.append(Paragraph(
        "<b>Requested Records:</b> All records, including but not limited to surveillance "
        "applications, court orders, and supporting affidavits related to the use of cell-site "
        "simulator technology (commonly known as StingRay devices) by the FBI's Chicago Field "
        "Office during the period of <b>March 1, 2024</b> through <b>February 28, 2025</b>. "
        "This includes any internal policy memoranda, training materials, and after-action "
        "reports related to the deployment of such technology.",
        body_style,
    ))

    story.append(Paragraph(
        "This request is submitted in connection with an ongoing civil rights matter. "
        "File reference: FBI-CHI-2025-0034.",
        body_style,
    ))

    story.append(Paragraph(
        "<b>Expedited Processing:</b> I request expedited processing pursuant to "
        "28 C.F.R. § 16.5(e)(1)(ii). There is due process urgency as the records sought "
        "are directly relevant to pending federal litigation with court-imposed discovery "
        "deadlines.",
        body_style,
    ))

    story.append(Paragraph(
        "I am prepared to pay reasonable fees for the processing of this request up to "
        "<b>$1,000.00</b>. Please advise if costs are expected to exceed this amount.",
        body_style,
    ))

    story.append(Spacer(1, 20))
    story.append(Paragraph("Respectfully submitted,", body_style))
    story.append(Spacer(1, 28))
    story.append(Paragraph("<i>Thomas K. Reeves, Esq.</i>", body_style))
    story.append(Paragraph("Partner, Reeves & Morrison LLP", header_style))

    doc.build(story)
    print(f"  Created: {output_path}")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Generating mock documents...")
    create_purchase_agreement()
    create_purchase_agreement_2()
    create_purchase_agreement_3()
    create_dallas_purchase()
    create_foia_request()
    create_foia_request_2()
    create_foia_request_3()
    print("Done.")


if __name__ == "__main__":
    main()
