from __future__ import annotations

from types import SimpleNamespace

from extractor import extract_from_images, recover_missing_fields_from_images, _parse_json_payload
from verifier import verify_extraction


class DummyCompletions:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("No more mocked responses available")
        return self._responses.pop(0)


class DummyClient:
    def __init__(self, responses):
        self.chat = SimpleNamespace(completions=DummyCompletions(responses))


def _response(content: str, *, finish_reason: str = "stop", prompt_tokens: int = 10, completion_tokens: int = 20):
    usage = SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )
    choice = SimpleNamespace(
        message=SimpleNamespace(content=content),
        finish_reason=finish_reason,
    )
    return SimpleNamespace(choices=[choice], usage=usage)


def test_parse_json_payload_extracts_balanced_object_from_wrapped_text():
    parsed = _parse_json_payload("Here you go:\n```json\n{\"a\": 1, \"b\": 2}\n```\nThanks")
    assert parsed == {"a": 1, "b": 2}


def test_extract_from_images_repairs_truncated_json():
    malformed = '{"loop_name":"Example","participants":[{"full_name":"Buyer Name"}],"notes":"truncated'
    repaired = '{"loop_name":"Example","participants":[{"full_name":"Buyer Name"}],"notes":"truncated"}'
    client = DummyClient([
        _response(malformed, finish_reason="length", prompt_tokens=100, completion_tokens=200),
        _response(repaired, prompt_tokens=25, completion_tokens=30),
    ])

    parsed, usage = extract_from_images(["base64data"], "real_estate", client)

    assert parsed["loop_name"] == "Example"
    assert parsed["notes"] == "truncated"
    assert usage["prompt_tokens"] == 125
    assert usage["completion_tokens"] == 230
    assert len(client.chat.completions.calls) == 2
    assert client.chat.completions.calls[0]["max_tokens"] == 8192


def test_verify_extraction_repairs_malformed_json():
    malformed = '{"citations":[{"field_name":"loop_name","extracted_value":"Example","page_number":1,"line_or_region":"top","surrounding_text":"Example","confidence":0.9}'
    repaired = '{"citations":[{"field_name":"loop_name","extracted_value":"Example","page_number":1,"line_or_region":"top","surrounding_text":"Example","confidence":0.9}]}'
    client = DummyClient([
        _response(malformed, finish_reason="length", prompt_tokens=120, completion_tokens=180),
        _response(repaired, prompt_tokens=20, completion_tokens=25),
    ])

    citations, usage = verify_extraction(["base64data"], {"loop_name": "Example"}, client)

    assert len(citations) == 1
    assert citations[0].field_name == "loop_name"
    assert usage["total_tokens"] == 345


def test_recover_missing_fields_from_images_returns_recoveries():
    client = DummyClient([
        _response('{"recoveries":{"financials.earnest_money_amount":15000,"terms.inspection_contingency":false}}'),
    ])

    recoveries, usage = recover_missing_fields_from_images(
        ["base64data"],
        {"financials": {"purchase_price": 612500.0}},
        [
            {"path": "financials.earnest_money_amount", "label": "Earnest Money", "type": "currency", "value": None},
            {"path": "terms.inspection_contingency", "label": "Inspection Contingency", "type": "boolean", "value": None},
        ],
        client,
    )

    assert recoveries["financials.earnest_money_amount"] == 15000
    assert recoveries["terms.inspection_contingency"] is False
    assert usage["total_tokens"] == 30


def test_recover_missing_fields_from_images_repairs_malformed_json():
    malformed = '{"recoveries":{"financials.earnest_money_amount":15000,"terms.inspection_contingency":false'
    repaired = '{"recoveries":{"financials.earnest_money_amount":15000,"terms.inspection_contingency":false}}'
    client = DummyClient([
        _response(malformed, finish_reason="length", prompt_tokens=40, completion_tokens=50),
        _response(repaired, prompt_tokens=10, completion_tokens=12),
    ])

    recoveries, usage = recover_missing_fields_from_images(
        ["base64data"],
        {"financials": {"purchase_price": 612500.0}},
        [
            {"path": "financials.earnest_money_amount", "label": "Earnest Money", "type": "currency", "value": None},
            {"path": "terms.inspection_contingency", "label": "Inspection Contingency", "type": "boolean", "value": None},
        ],
        client,
    )

    assert recoveries["financials.earnest_money_amount"] == 15000
    assert recoveries["terms.inspection_contingency"] is False
    assert usage["prompt_tokens"] == 50
    assert usage["completion_tokens"] == 62


def test_verify_extraction_ensures_required_not_found_citations():
    repaired = '{"citations":[{"field_name":"financials.purchase_price","extracted_value":"612500.0","page_number":1,"line_or_region":"Section 2","surrounding_text":"Purchase price","confidence":0.95}]}'
    client = DummyClient([_response(repaired, prompt_tokens=20, completion_tokens=25)])

    citations, _ = verify_extraction(
        ["base64data"],
        {"financials": {"purchase_price": 612500.0}, "terms": {"inspection_contingency": None}},
        client,
        [
            {"path": "financials.purchase_price", "value": 612500.0},
            {"path": "terms.inspection_contingency", "value": None},
        ],
    )

    by_field = {citation.field_name: citation for citation in citations}
    assert by_field["financials.purchase_price"].confidence == 0.95
    assert by_field["terms.inspection_contingency"].surrounding_text == "NOT FOUND"
    assert by_field["terms.inspection_contingency"].confidence == 0.0
