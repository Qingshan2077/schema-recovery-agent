import pytest

from backend.agent.runtime.structured_output import StructuredOutputError, parse_and_validate


SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}, "confidence": {"type": "number", "minimum": 0, "maximum": 1}},
    "required": ["answer", "confidence"],
    "additionalProperties": False,
}


def test_strict_json_output_is_validated_without_text_extraction():
    outcome = parse_and_validate('{"answer":"ok","confidence":0.8}', SCHEMA)
    assert outcome.value["answer"] == "ok"


@pytest.mark.parametrize(
    "payload,code",
    [
        ("prefix {\"answer\":\"ok\",\"confidence\":1}", "invalid_json"),
        ('{"answer":"ok"}', "schema_required"),
        ('{"answer":"ok","confidence":1,"extra":true}', "schema_unknown_field"),
    ],
)
def test_invalid_structured_output_has_stable_error_code(payload, code):
    with pytest.raises(StructuredOutputError) as caught:
        parse_and_validate(payload, SCHEMA)
    assert caught.value.code == code
