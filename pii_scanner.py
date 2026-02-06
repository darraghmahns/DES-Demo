"""PII detection with regex patterns and risk scoring."""

import re

from schemas import PIIFinding, PIIType, PIISeverity, PIIReport

# Regex patterns for PII detection
PII_PATTERNS: dict[PIIType, dict] = {
    PIIType.SSN: {
        "pattern": r"\b\d{3}-\d{2}-\d{4}\b",
        "severity": PIISeverity.HIGH,
        "redact": lambda m: f"***-**-{m.group(0)[-4:]}",
        "recommendation": "CRITICAL: SSN detected. Encrypt before transmission. Verify if SSN is required for this request.",
    },
    PIIType.PHONE: {
        "pattern": r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
        "severity": PIISeverity.MEDIUM,
        "redact": lambda m: f"(***) ***-{m.group(0)[-4:]}",
        "recommendation": "Phone number detected. Required for FOIA contact. Ensure secure transmission channel.",
    },
    PIIType.EMAIL: {
        "pattern": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        "severity": PIISeverity.MEDIUM,
        "redact": lambda m: f"{m.group(0)[0]}***@{m.group(0).split('@')[1]}",
        "recommendation": "Email address detected. Required for FOIA correspondence. Standard handling applies.",
    },
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

    for pii_type, config in PII_PATTERNS.items():
        for match in re.finditer(config["pattern"], text):
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
