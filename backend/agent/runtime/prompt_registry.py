"""Immutable prompt registry with semantic versions and content hashes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from string import Formatter
from typing import Any, Literal

from pydantic import Field, field_validator

from backend.agent.runtime.contracts import StrictContract
from backend.agent.runtime.structured_output import validate_json_schema


class PromptRegistryError(ValueError):
    pass


class PromptSnapshot(StrictContract):
    prompt_id: str
    semantic_version: str
    agent_id: str
    purpose: str
    template_path: str
    sha256: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    required_capabilities: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    created_at: str
    status: Literal["active", "deprecated", "disabled"]

    @field_validator("semantic_version")
    @classmethod
    def validate_semantic_version(cls, value: str) -> str:
        parts = value.split(".")
        if len(parts) != 3 or any(not part.isdigit() for part in parts):
            raise ValueError("Prompt semantic_version must use MAJOR.MINOR.PATCH")
        return value

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value.lower()):
            raise ValueError("Prompt sha256 must be a 64-character hexadecimal digest")
        return value.lower()


class RenderedPrompt(StrictContract):
    prompt_id: str
    version: str
    sha256: str
    content: str
    output_schema: dict[str, Any]
    required_capabilities: list[str]
    allowed_tools: list[str]


class PromptRegistry:
    def __init__(self, registry_path: str | Path | None = None):
        default = Path(__file__).resolve().parents[1] / "prompts" / "registry.json"
        self.registry_path = Path(registry_path or default).resolve()
        self.base_dir = self.registry_path.parent
        self._entries = self._load_registry()

    def get(self, prompt_id: str, version: str | None = None) -> PromptSnapshot:
        matches = [entry for entry in self._entries if entry.prompt_id == prompt_id]
        if version is not None:
            matches = [entry for entry in matches if entry.semantic_version == version]
        else:
            matches = [entry for entry in matches if entry.status == "active"]
        if len(matches) != 1:
            suffix = f" version {version}" if version else " active version"
            raise PromptRegistryError(f"Expected exactly one prompt {prompt_id}{suffix}; found {len(matches)}")
        entry = matches[0]
        self._verify_entry(entry)
        return entry

    def render(self, prompt_id: str, version: str, values: dict[str, Any]) -> RenderedPrompt:
        entry = self.get(prompt_id, version)
        validate_json_schema(values, entry.input_schema)
        template = self._template_path(entry).read_text(encoding="utf-8")
        required_variables = {
            field_name
            for _, field_name, _, _ in Formatter().parse(template)
            if field_name
        }
        missing = required_variables - set(values)
        if missing:
            raise PromptRegistryError(f"Missing prompt variables: {', '.join(sorted(missing))}")
        unused_required = set(entry.input_schema.get("required", [])) - required_variables
        if unused_required:
            raise PromptRegistryError(
                f"Registered required inputs are not used by template: {', '.join(sorted(unused_required))}"
            )
        try:
            content = template.format_map(values)
        except (KeyError, ValueError) as exc:
            raise PromptRegistryError("Prompt template could not be rendered") from exc
        return RenderedPrompt(
            prompt_id=entry.prompt_id,
            version=entry.semantic_version,
            sha256=entry.sha256,
            content=content,
            output_schema=entry.output_schema,
            required_capabilities=entry.required_capabilities,
            allowed_tools=entry.allowed_tools,
        )

    def validate_all(self) -> None:
        active: dict[str, int] = {}
        prompt_ids: set[str] = set()
        for entry in self._entries:
            self._verify_entry(entry)
            prompt_ids.add(entry.prompt_id)
            if entry.status == "active":
                active[entry.prompt_id] = active.get(entry.prompt_id, 0) + 1
        duplicates = [prompt_id for prompt_id in prompt_ids if active.get(prompt_id, 0) != 1]
        if duplicates:
            raise PromptRegistryError(f"Prompt ids must have one active version: {', '.join(sorted(duplicates))}")

    def _load_registry(self) -> list[PromptSnapshot]:
        try:
            raw = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PromptRegistryError(f"Prompt registry cannot be loaded: {self.registry_path}") from exc
        if raw.get("schema_version") != "1.0" or not isinstance(raw.get("prompts"), list):
            raise PromptRegistryError("Unsupported or invalid prompt registry schema")
        entries = [PromptSnapshot.model_validate(item) for item in raw["prompts"]]
        keys = [(entry.prompt_id, entry.semantic_version) for entry in entries]
        if len(keys) != len(set(keys)):
            raise PromptRegistryError("Prompt id and version pairs must be unique")
        return entries

    def _verify_entry(self, entry: PromptSnapshot) -> None:
        path = self._template_path(entry)
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise PromptRegistryError(f"Prompt template not found: {entry.template_path}") from exc
        actual_hash = hashlib.sha256(content).hexdigest()
        if actual_hash != entry.sha256:
            raise PromptRegistryError(
                f"Prompt hash drift for {entry.prompt_id}@{entry.semantic_version}"
            )
        if entry.output_schema.get("type") != "object":
            raise PromptRegistryError("Prompt output schema root must be an object")
        try:
            template = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PromptRegistryError("Prompt template must be UTF-8") from exc
        variables = {field_name for _, field_name, _, _ in Formatter().parse(template) if field_name}
        declared = set(entry.input_schema.get("properties", {}))
        required = set(entry.input_schema.get("required", []))
        if variables - declared:
            raise PromptRegistryError(
                f"Prompt variables are not declared in input schema: {', '.join(sorted(variables - declared))}"
            )
        if required - variables:
            raise PromptRegistryError(
                f"Required prompt inputs are unused: {', '.join(sorted(required - variables))}"
            )

    def _template_path(self, entry: PromptSnapshot) -> Path:
        path = (self.base_dir / entry.template_path).resolve()
        if self.base_dir not in path.parents:
            raise PromptRegistryError("Prompt template path escapes registry directory")
        return path
