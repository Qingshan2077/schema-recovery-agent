import pytest

from backend.agent.runtime.model_profiles import CapabilityError, ModelProfileRegistry


class LegacyCompatibleConfig:
    LLM_MODEL = "legacy-model"
    MODEL_PROVIDER_MODE = "live"
    MODEL_PROVIDER = "openai_compatible"
    MODEL_TIMEOUT_SECONDS = 30
    MODEL_MAX_RETRIES = 1
    MODEL_STRICT_SCHEMA_PROFILES = ()
    MODEL_STREAMING_PROFILES = ("synthesis",)
    MODEL_TOOL_PROFILES = ("reasoning",)
    MODEL_MAX_CONTEXT_TOKENS = 32000
    MODEL_FAST_TEMPERATURE = 0.1
    MODEL_REASONING_TEMPERATURE = 0.1
    MODEL_SYNTHESIS_TEMPERATURE = 0.2
    MODEL_JUDGE_TEMPERATURE = 0.1
    MODEL_EMBEDDING_TEMPERATURE = None


def test_legacy_model_populates_all_profiles():
    profiles = ModelProfileRegistry.from_config(LegacyCompatibleConfig)

    assert profiles.get("fast").model == "legacy-model"
    assert profiles.get("judge").model == "legacy-model"
    assert profiles.get("reasoning").capabilities.supports_tools is True


def test_missing_capability_is_explicit_or_locally_declared():
    profiles = ModelProfileRegistry.from_config(LegacyCompatibleConfig)

    with pytest.raises(CapabilityError):
        profiles.validate_capabilities("judge", ["strict_schema"])
    assert profiles.validate_capabilities(
        "judge",
        ["strict_schema"],
        allow_local_schema_validation=True,
    ) == ["strict_schema_local_validation"]
