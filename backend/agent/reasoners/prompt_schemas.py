"""Immutable structured-output schema for all worker reasoning prompts."""

WORKER_REASONING_SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "maxItems": 500,
            "items": {
                "type": "object",
                "properties": {
                    "source_table": {"type": "string"},
                    "source_columns": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                    "target_table": {"type": "string"},
                    "target_columns": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                    "cardinality": {"type": "string", "enum": ["1:1", "1:N", "N:1", "N:N", "unknown"]},
                    "alternatives": {"type": "array", "items": {"type": "string"}},
                    "validation_flags": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["source_table", "source_columns", "target_table", "target_columns", "cardinality", "alternatives", "validation_flags"],
                "additionalProperties": false
            }
        },
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "uncertainties": {"type": "array", "items": {"type": "string"}},
        "evidence_requests": {
            "type": "array",
            "maxItems": 20,
            "items": {
                "type": "object",
                "properties": {
                    "target_worker": {"type": "string", "enum": ["survey", "column", "name", "code", "orm", "merge"]},
                    "requested_fact": {"type": "string"},
                    "subject_refs": {"type": "array", "items": {"type": "string"}},
                    "allowed_tools": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string"},
                    "expected_information_gain": {"type": "number", "minimum": 0, "maximum": 1}
                },
                "required": ["target_worker", "requested_fact", "subject_refs", "allowed_tools", "reason", "expected_information_gain"],
                "additionalProperties": false
            }
        },
        "decision_summary": {"type": "string", "maxLength": 3000},
        "used_memory_ids": {"type": "array", "items": {"type": "string"}, "maxItems": 100}
    },
    "required": ["candidates", "assumptions", "uncertainties", "evidence_requests", "decision_summary", "used_memory_ids"],
    "additionalProperties": false
}
