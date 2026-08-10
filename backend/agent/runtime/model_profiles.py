"""Model profile construction, capability validation, and legacy mapping."""

from __future__ import annotations

from collections.abc import Iterable

from backend.agent.runtime.contracts import ModelCapabilities, ModelProfile


class CapabilityError(ValueError):
    pass


class ModelProfileRegistry:
    def __init__(self, profiles: Iterable[ModelProfile]):
        self._profiles = {profile.name: profile for profile in profiles}
        missing = {"fast", "reasoning", "synthesis", "judge", "embedding"} - set(self._profiles)
        if missing:
            raise ValueError(f"Missing model profiles: {', '.join(sorted(missing))}")

    @classmethod
    def from_config(cls, config: object) -> "ModelProfileRegistry":
        default_model = str(getattr(config, "LLM_MODEL", ""))
        provider_mode = str(getattr(config, "MODEL_PROVIDER_MODE", "live")).strip().lower()
        provider = "fake" if provider_mode == "fake" else str(getattr(config, "MODEL_PROVIDER", "openai_compatible"))
        timeout = float(getattr(config, "MODEL_TIMEOUT_SECONDS", 60.0))
        retries = int(getattr(config, "MODEL_MAX_RETRIES", 2))
        strict_profiles = set(getattr(config, "MODEL_STRICT_SCHEMA_PROFILES", ()))
        streaming_profiles = set(getattr(config, "MODEL_STREAMING_PROFILES", ()))
        tool_profiles = set(getattr(config, "MODEL_TOOL_PROFILES", ()))
        profiles: list[ModelProfile] = []
        for name in ("fast", "reasoning", "synthesis", "judge", "embedding"):
            model = str(getattr(config, f"MODEL_{name.upper()}", "") or default_model)
            profiles.append(
                ModelProfile(
                    name=name,
                    provider=provider,
                    model=model,
                    capabilities=ModelCapabilities(
                        supports_tools=name in tool_profiles,
                        supports_strict_schema=name in strict_profiles,
                        supports_streaming=name in streaming_profiles,
                        max_context_tokens=getattr(config, "MODEL_MAX_CONTEXT_TOKENS", None),
                    ),
                    timeout_seconds=timeout,
                    max_retries=retries,
                    temperature=_temperature(config, name),
                    available=bool(model),
                )
            )
        return cls(profiles)

    def get(self, name: str) -> ModelProfile:
        try:
            profile = self._profiles[name]
        except KeyError as exc:
            raise CapabilityError(f"Unknown model profile: {name}") from exc
        if not profile.available:
            raise CapabilityError(f"Model profile is unavailable: {name}")
        return profile

    def validate_capabilities(
        self,
        name: str,
        required: Iterable[str],
        *,
        allow_local_schema_validation: bool = False,
    ) -> list[str]:
        profile = self.get(name)
        degraded: list[str] = []
        for capability in required:
            field = f"supports_{capability}"
            if not hasattr(profile.capabilities, field):
                raise CapabilityError(f"Unknown capability requirement: {capability}")
            if getattr(profile.capabilities, field):
                continue
            if capability == "strict_schema" and allow_local_schema_validation:
                degraded.append("strict_schema_local_validation")
                continue
            raise CapabilityError(f"Profile '{name}' does not support required capability '{capability}'")
        return degraded

    def public_inventory(self) -> list[dict[str, object]]:
        return [
            {
                "name": profile.name,
                "provider": profile.provider,
                "model": profile.model,
                "available": profile.available,
                "capabilities": profile.capabilities.model_dump(),
            }
            for profile in self._profiles.values()
        ]


def _temperature(config: object, profile_name: str) -> float | None:
    value = getattr(config, f"MODEL_{profile_name.upper()}_TEMPERATURE", None)
    return float(value) if value is not None else None
