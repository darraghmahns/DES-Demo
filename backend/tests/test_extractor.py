from __future__ import annotations

from types import SimpleNamespace

from extractor import extract_from_images, _parse_json_payload
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
