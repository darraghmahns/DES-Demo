"""Verification pass — cites source locations for each extracted value."""

import json

from openai import OpenAI

from schemas import VerificationCitation

VERIFICATION_SYSTEM_PROMPT = """You are a document verification specialist. You previously extracted structured data from a document. Now you must VERIFY each extracted value by citing its exact source location in the document.

For EACH field in the extraction result below, provide:
1. field_name: The schema field name
2. extracted_value: The value that was extracted
3. page_number: Which page (1-indexed) the value appears on
4. line_or_region: Approximate line number or region description (e.g., "line 5", "top-right", "Section 3, paragraph 2")
5. surrounding_text: A short snippet (~20 characters) of text immediately surrounding the value in the document
6. confidence: Your confidence (0.0-1.0) that this extraction is correct

You MUST return a JSON object with this structure:
{
  "citations": [
    {
      "field_name": "...",
      "extracted_value": "...",
      "page_number": 1,
      "line_or_region": "...",
      "surrounding_text": "...",
      "confidence": 0.95
    }
  ]
}

Rules:
- Include a citation for EVERY non-null field in the extraction.
- If you cannot find a value in the document, set confidence to 0.0 and note "NOT FOUND" in surrounding_text.
- Be precise about page numbers — do not guess.
- surrounding_text should be the actual text from the document, not paraphrased.
"""


def verify_extraction(
    images_b64: list[str],
    extracted_data: dict,
    client: OpenAI,
) -> list[VerificationCitation]:
    """Second-pass verification: ask GPT-4o to cite source locations.

    Args:
        images_b64: List of base64-encoded page images.
        extracted_data: The previously extracted data dict.
        client: OpenAI client instance.

    Returns:
        List of VerificationCitation objects.
    """
    content: list[dict] = []

    # Include all page images
    for i, img_b64 in enumerate(images_b64):
        content.append({"type": "text", "text": f"--- Page {i + 1} of {len(images_b64)} ---"})
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{img_b64}", "detail": "high"},
        })

    # Add the extraction to verify
    content.append({
        "type": "text",
        "text": (
            "Here is the data that was extracted from the above document. "
            "Verify each field by citing its exact source location.\n\n"
            f"Extracted data:\n{json.dumps(extracted_data, indent=2)}"
        ),
    })

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": VERIFICATION_SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        response_format={"type": "json_object"},
        temperature=0.0,
        max_tokens=4096,
    )

    raw = json.loads(response.choices[0].message.content)

    # Parse into VerificationCitation objects
    citations_raw = raw.get("citations", [])
    citations: list[VerificationCitation] = []
    for c in citations_raw:
        try:
            citations.append(VerificationCitation.model_validate(c))
        except Exception:
            # Skip malformed citations rather than failing
            continue

    return citations


def compute_overall_confidence(citations: list[VerificationCitation]) -> float:
    """Compute the mean confidence across all citations.

    Returns:
        Float between 0.0 and 1.0, or 0.0 if no citations.
    """
    if not citations:
        return 0.0
    return sum(c.confidence for c in citations) / len(citations)
