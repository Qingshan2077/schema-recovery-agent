"""Immutable JSON schemas shared by QA code and the prompt registry."""

QUERY_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": [
                "table_columns", "table_metadata", "relations", "indexes",
                "schema_overview", "analysis_status", "evidence_explain", "unknown",
            ],
        },
        "entities": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "object",
                "properties": {
                    "mention": {"type": "string", "minLength": 1, "maxLength": 256},
                    "kind": {"type": "string", "enum": ["table", "column", "relation", "database"]},
                    "parent_mention": {"type": ["string", "null"], "maxLength": 256},
                },
                "required": ["mention", "kind", "parent_mention"],
                "additionalProperties": False,
            },
        },
        "required_information": {"type": "array", "maxItems": 12, "items": {"type": "string"}},
        "suggested_tools": {"type": "array", "maxItems": 6, "items": {"type": "string"}},
        "clarification_question": {"type": ["string", "null"], "maxLength": 1000},
        "language": {"type": "string", "enum": ["zh-CN", "en"]},
        "plan_summary": {"type": "string", "maxLength": 2000},
    },
    "required": [
        "intent", "entities", "required_information", "suggested_tools",
        "clarification_question", "language", "plan_summary",
    ],
    "additionalProperties": False,
}

SYNTHESIS_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string", "minLength": 1, "maxLength": 16000},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim_id": {"type": "string"},
                    "text": {"type": "string", "minLength": 1, "maxLength": 4000},
                    "fact_ids": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                },
                "required": ["claim_id", "text", "fact_ids"],
                "additionalProperties": False,
            },
        },
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "citation_id": {"type": "string"},
                    "claim_id": {"type": "string"},
                    "fact_ids": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                    "label": {"type": "string"},
                    "locator": {"type": "object"},
                },
                "required": ["citation_id", "claim_id", "fact_ids", "label", "locator"],
                "additionalProperties": False,
            },
        },
        "artifacts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "artifact_id": {"type": "string"},
                    "type": {"type": "string", "enum": ["column_table", "relation_cards", "evidence_cards", "clarification_options", "metadata_card", "index_table", "overview"]},
                    "title": {"type": "string"},
                    "data": {"type": "object"},
                    "fact_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["artifact_id", "type", "title", "data", "fact_ids"],
                "additionalProperties": False,
            },
        },
        "follow_up_questions": {"type": "array", "maxItems": 3, "items": {"type": "string"}},
    },
    "required": ["answer", "claims", "citations", "artifacts", "follow_up_questions"],
    "additionalProperties": False,
}
