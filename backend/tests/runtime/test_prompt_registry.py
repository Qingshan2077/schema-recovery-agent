import json

import pytest

from backend.agent.runtime.prompt_registry import PromptRegistry, PromptRegistryError


def test_registered_judge_prompt_hash_and_variables_are_verified():
    registry = PromptRegistry()
    rendered = registry.render("judge.analysis", "1.0.0", {"analysis_summary": "summary"})

    assert rendered.sha256
    assert "summary" in rendered.content
    assert rendered.output_schema["type"] == "object"


def test_hash_drift_fails_closed(tmp_path):
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Hello {value}", encoding="utf-8")
    registry_file = tmp_path / "registry.json"
    registry_file.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "prompts": [
                    {
                        "prompt_id": "test",
                        "semantic_version": "1.0.0",
                        "agent_id": "test",
                        "purpose": "test",
                        "template_path": "prompt.md",
                        "sha256": "0" * 64,
                        "input_schema": {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]},
                        "output_schema": {"type": "object"},
                        "required_capabilities": [],
                        "allowed_tools": [],
                        "created_at": "2026-08-10T00:00:00Z",
                        "status": "active"
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(PromptRegistryError, match="hash drift"):
        PromptRegistry(registry_file).get("test", "1.0.0")
