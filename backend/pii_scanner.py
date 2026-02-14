"""PII detection with regex patterns and risk scoring."""

import re

from schemas import PIIFinding, PIIType, PIISeverity, PIIReport

# Regex patterns for PII detection
PII_PATTERNS: dict[PIIType, list[dict]] = {
    PIIType.SSN: [
        {
            "pattern": r"\b\d{3}-\d{2}-\d{4}\b",
            "severity": PIISeverity.HIGH,
            "redact": lambda m: f"***-**-{m.group(0)[-4:]}",
            "recommendation": "CRITICAL: SSN detected. Encrypt before transmission. Verify if SSN is required for this request.",
        },
    ],
    PIIType.PHONE: [
        {
            "pattern": r"(?<!\d)(?:\+?1[-.\s]?)?\(\d{3}\)[-.\s]?\d{3}[-.\s]?\d{4}(?!\d)|\b(?:\+?1[-.\s]?)?\d{3}[-.\s]\d{3}[-.\s]?\d{4}\b",
            "severity": PIISeverity.MEDIUM,
            "redact": lambda m: f"(***) ***-{m.group(0)[-4:]}",
            "recommendation": "Phone number detected. Required for FOIA contact. Ensure secure transmission channel.",
        },
    ],
    PIIType.EMAIL: [
        {
            "pattern": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
            "severity": PIISeverity.MEDIUM,
            "redact": lambda m: f"{m.group(0)[0]}***@{m.group(0).split('@')[1]}",
            "recommendation": "Email address detected. Required for FOIA correspondence. Standard handling applies.",
        },
    ],
    PIIType.ADDRESS: [
        {
            "pattern": r"\b\d{1,6}\s+[A-Z][a-zA-Z\s]{2,40}(?:Street|St|Avenue|Ave|Boulevard|Blvd|Drive|Dr|Lane|Ln|Road|Rd|Court|Ct|Place|Pl|Way|Circle|Cir|Trail|Trl|Parkway|Pkwy)\.?\b",
            "severity": PIISeverity.MEDIUM,
            "redact": lambda m: f"[ADDRESS REDACTED]",
            "recommendation": "Physical address detected. Contains location data that can identify individuals. Redact if not required.",
        },
        {
            "pattern": r"\b(?:P\.?O\.?\s*Box|PO\s*Box)\s+\d+\b",
            "severity": PIISeverity.MEDIUM,
            "redact": lambda m: f"[P.O. BOX REDACTED]",
            "recommendation": "P.O. Box address detected. May identify individuals. Redact if not required.",
        },
    ],
    PIIType.DATE_OF_BIRTH: [
        {
            "pattern": r"\b(?:DOB|Date of Birth|Birth ?Date|Born)[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b",
            "severity": PIISeverity.HIGH,
            "redact": lambda m: f"DOB: **/**/****",
            "recommendation": "Date of birth detected. HIGH sensitivity — can be used for identity theft. Redact if not required.",
        },
    ],
    PIIType.DRIVERS_LICENSE: [
        {
            "pattern": r"\b(?:DL|Driver'?s?\s*License|License\s*(?:No|Number|#))[:\s#]*([A-Z0-9]{5,15})\b",
            "severity": PIISeverity.HIGH,
            "redact": lambda m: f"DL: [REDACTED]",
            "recommendation": "Driver's license number detected. HIGH sensitivity — government-issued ID. Encrypt and restrict access.",
        },
    ],
    PIIType.BANK_ACCOUNT: [
        {
            "pattern": r"\b(?:Account|Acct|Routing)\s*(?:No|Number|#)?[:\s#]*(\d{8,17})\b",
            "severity": PIISeverity.HIGH,
            "redact": lambda m: f"[ACCOUNT REDACTED]",
            "recommendation": "Bank account or routing number detected. HIGH sensitivity — financial data. Encrypt before transmission.",
        },
    ],
    PIIType.CREDIT_CARD: [
        {
            "pattern": r"\b(?:4\d{3}|5[1-5]\d{2}|3[47]\d{2}|6(?:011|5\d{2}))[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",
            "severity": PIISeverity.HIGH,
            "redact": lambda m: f"****-****-****-{m.group(0)[-4:]}",
            "recommendation": "CRITICAL: Credit card number detected. Must be handled per PCI-DSS. Do not store unencrypted.",
        },
    ],
}


def scan_text_for_pii(text: str, page_number: int) -> list[PIIFinding]:
    """Scan a page of text for PII using regex patterns.

    Args:
        text: Raw text content of a document page.
        page_number: 1-indexed page number for location reporting.

    Returns:
        List of PIIFinding objects for detected PII.
    """
    findings: list[PIIFinding] = []

    for pii_type, configs in PII_PATTERNS.items():
        for config in configs:
            for match in re.finditer(config["pattern"], text, re.IGNORECASE):
                # Calculate approximate line number
                line_num = text[: match.start()].count("\n") + 1

                findings.append(
                    PIIFinding(
                        pii_type=pii_type,
                        value_redacted=config["redact"](match),
                        severity=config["severity"],
                        confidence=0.95,
                        location=f"Page {page_number}, line {line_num}",
                        recommendation=config["recommendation"],
                    )
                )

    return findings


def scan_all_pages(page_texts: list[str]) -> PIIReport:
    """Scan all pages of a document for PII.

    Args:
        page_texts: List of raw text strings, one per page.

    Returns:
        PIIReport with all findings and computed risk score.
    """
    all_findings: list[PIIFinding] = []

    for i, text in enumerate(page_texts):
        page_findings = scan_text_for_pii(text, page_number=i + 1)
        all_findings.extend(page_findings)

    return PIIReport(findings=all_findings)
