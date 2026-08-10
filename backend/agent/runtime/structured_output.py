"""Strict JSON parsing and deterministic JSON Schema subset validation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


class StructuredOutputError(ValueError):
    def __init__(self, code: str, message: str, *, path: str = "$"):
        super().__init__(message)
        self.code = code
        self.path = path


@dataclass(frozen=True)
class ValidationOutcome:
    value: dict[str, Any]
    schema_valid: bool = True


def parse_and_validate(raw: str | dict[str, Any], schema: dict[str, Any]) -> ValidationOutcome:
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise StructuredOutputError("invalid_json", "Provider output is not valid JSON") from exc
    elif isinstance(raw, dict):
        value = raw
    else:
        raise StructuredOutputError("invalid_root", "Structured output must be a JSON object")
    if not isinstance(value, dict):
        raise StructuredOutputError("invalid_root", "Structured output must be a JSON object")
    validate_json_schema(value, schema)
    return ValidationOutcome(value=value)


def validate_json_schema(
    value: Any,
    schema: dict[str, Any],
    *,
    path: str = "$",
    root_schema: dict[str, Any] | None = None,
) -> None:
    root_schema = root_schema or schema
    if "$ref" in schema:
        validate_json_schema(value, _resolve_ref(root_schema, schema["$ref"]), path=path, root_schema=root_schema)
        return
    for subschema in schema.get("allOf", []):
        validate_json_schema(value, subschema, path=path, root_schema=root_schema)
    if "anyOf" in schema:
        successes = sum(_schema_matches(value, item, path, root_schema) for item in schema["anyOf"])
        if successes == 0:
            raise StructuredOutputError("schema_any_of", f"Value at {path} matches no allowed schema", path=path)
    if "oneOf" in schema:
        successes = sum(_schema_matches(value, item, path, root_schema) for item in schema["oneOf"])
        if successes != 1:
            raise StructuredOutputError("schema_one_of", f"Value at {path} must match exactly one schema", path=path)
    expected_type = schema.get("type")
    if expected_type and not _matches_type(value, expected_type):
        raise StructuredOutputError("schema_type", f"Expected {expected_type} at {path}", path=path)
    if "enum" in schema and value not in schema["enum"]:
        raise StructuredOutputError("schema_enum", f"Value at {path} is not in enum", path=path)
    if "const" in schema and value != schema["const"]:
        raise StructuredOutputError("schema_const", f"Value at {path} does not match const", path=path)
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        for field in required:
            if field not in value:
                raise StructuredOutputError("schema_required", f"Missing required field {path}.{field}", path=path)
        if schema.get("additionalProperties") is False:
            unknown = set(value) - set(properties)
            if unknown:
                raise StructuredOutputError(
                    "schema_unknown_field", f"Unknown fields at {path}: {', '.join(sorted(unknown))}", path=path
                )
        if "minProperties" in schema and len(value) < schema["minProperties"]:
            raise StructuredOutputError("schema_min_properties", f"Too few properties at {path}", path=path)
        if "maxProperties" in schema and len(value) > schema["maxProperties"]:
            raise StructuredOutputError("schema_max_properties", f"Too many properties at {path}", path=path)
        for key, item in value.items():
            if key in properties:
                validate_json_schema(item, properties[key], path=f"{path}.{key}", root_schema=root_schema)
            elif isinstance(schema.get("additionalProperties"), dict):
                validate_json_schema(
                    item,
                    schema["additionalProperties"],
                    path=f"{path}.{key}",
                    root_schema=root_schema,
                )
    elif isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            raise StructuredOutputError("schema_min_items", f"Too few items at {path}", path=path)
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise StructuredOutputError("schema_max_items", f"Too many items at {path}", path=path)
        if schema.get("uniqueItems") and len({json.dumps(item, sort_keys=True, default=str) for item in value}) != len(value):
            raise StructuredOutputError("schema_unique_items", f"Items are not unique at {path}", path=path)
        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(value):
                validate_json_schema(item, item_schema, path=f"{path}[{index}]", root_schema=root_schema)
    elif isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            raise StructuredOutputError("schema_min_length", f"String is too short at {path}", path=path)
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise StructuredOutputError("schema_max_length", f"String is too long at {path}", path=path)
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            raise StructuredOutputError("schema_pattern", f"String does not match pattern at {path}", path=path)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise StructuredOutputError("schema_minimum", f"Number is below minimum at {path}", path=path)
        if "maximum" in schema and value > schema["maximum"]:
            raise StructuredOutputError("schema_maximum", f"Number is above maximum at {path}", path=path)


def repair_instruction(error: StructuredOutputError, output_schema: dict[str, Any]) -> str:
    return json.dumps(
        {
            "task": "Return a corrected JSON object only.",
            "validation_error": {"code": error.code, "path": error.path, "message": str(error)},
            "output_schema": output_schema,
            "constraints": ["Do not add prose", "Do not add unknown fields", "Do not reveal hidden reasoning"],
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _matches_type(value: Any, expected: str | list[str]) -> bool:
    if isinstance(expected, list):
        return any(_matches_type(value, item) for item in expected)
    checks = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "null": lambda item: item is None,
    }
    return checks.get(expected, lambda item: False)(value)


def _schema_matches(value: Any, schema: dict[str, Any], path: str, root_schema: dict[str, Any]) -> bool:
    try:
        validate_json_schema(value, schema, path=path, root_schema=root_schema)
        return True
    except StructuredOutputError:
        return False


def _resolve_ref(root_schema: dict[str, Any], reference: str) -> dict[str, Any]:
    if not reference.startswith("#/"):
        raise StructuredOutputError("schema_ref", "Only local JSON Schema references are supported")
    current: Any = root_schema
    for component in reference[2:].split("/"):
        key = component.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or key not in current:
            raise StructuredOutputError("schema_ref", f"Unresolvable JSON Schema reference: {reference}")
        current = current[key]
    if not isinstance(current, dict):
        raise StructuredOutputError("schema_ref", f"JSON Schema reference is not an object: {reference}")
    return current
