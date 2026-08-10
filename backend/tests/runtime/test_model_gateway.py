import asyncio

from backend.agent.runtime.contracts import ModelCapabilities, ModelProfile, ModelRequest, RunBudget
from backend.agent.runtime.model_gateway import ModelGateway
from backend.agent.runtime.model_profiles import ModelProfileRegistry
from backend.agent.runtime.prompt_registry import PromptRegistry
from backend.agent.runtime.providers.fake import FakeProvider, FakeScenario
from backend.agent.runtime.run_context import RunContext
from backend.agent.runtime.tracing import InMemoryEventSink
from backend.core.identity import RunIdentity


VALID_JUDGE_OUTPUT = {
    "accuracy": 80,
    "evidence_quality": 75,
    "confidence_calibration": 70,
    "completeness": 65,
    "overall_comment": "Evidence is usable.",
    "improvement_suggestions": ["Add coverage evidence."],
}


def _profiles(max_retries=1):
    return ModelProfileRegistry(
        [
            ModelProfile(
                name=name,
                provider="fake",
                model=f"fake-{name}",
                capabilities=ModelCapabilities(
                    supports_strict_schema=True,
                    supports_streaming=True,
                    supports_tools=False,
                ),
                timeout_seconds=1,
                max_retries=max_retries,
                temperature=0,
            )
            for name in ("fast", "reasoning", "synthesis", "judge", "embedding")
        ]
    )


def _context(event_sink=None):
    return RunContext.from_identity(
        RunIdentity.create(),
        agent_id="llm_judge",
        budget=RunBudget(
            max_model_calls=8,
            max_tool_calls=2,
            max_input_tokens=10000,
            max_output_tokens=10000,
            max_cost_usd=None,
            max_loop_iterations=2,
        ),
        event_sink=event_sink,
    )


def _request(registry):
    prompt = registry.get("judge.analysis", "1.0.0")
    return ModelRequest(
        profile="judge",
        prompt_id=prompt.prompt_id,
        prompt_version=prompt.semantic_version,
        input={"analysis_summary": "one relation"},
        output_schema=prompt.output_schema,
        metadata={"max_output_tokens": 512},
    )


def test_gateway_returns_strict_parsed_output_and_trace():
    prompts = PromptRegistry()
    provider = FakeProvider([FakeScenario(kind="success", output=VALID_JUDGE_OUTPUT)])
    sink = InMemoryEventSink()
    gateway = ModelGateway(profiles=_profiles(), prompts=prompts, providers={"fake": provider})

    result = asyncio.run(gateway.generate_structured(_request(prompts), _context(sink)))

    assert result.status == "success"
    assert result.parsed == VALID_JUDGE_OUTPUT
    assert result.prompt_hash
    assert {event.event_type for event in sink.events} >= {"model.started", "model.completed", "usage.updated"}


def test_gateway_retries_only_retryable_provider_failure():
    prompts = PromptRegistry()
    provider = FakeProvider(
        [
            FakeScenario(kind="rate_limit"),
            FakeScenario(kind="success", output=VALID_JUDGE_OUTPUT),
        ]
    )
    gateway = ModelGateway(profiles=_profiles(max_retries=1), prompts=prompts, providers={"fake": provider})

    result = asyncio.run(gateway.generate_structured(_request(prompts), _context()))

    assert result.status == "success"
    assert result.attempt_count == 2
    assert len(provider.calls) == 2


def test_gateway_allows_exactly_one_schema_repair():
    prompts = PromptRegistry()
    provider = FakeProvider(
        [
            FakeScenario(kind="schema_mismatch"),
            FakeScenario(kind="success", output=VALID_JUDGE_OUTPUT),
        ]
    )
    gateway = ModelGateway(profiles=_profiles(), prompts=prompts, providers={"fake": provider}, repair_enabled=True)

    result = asyncio.run(gateway.generate_structured(_request(prompts), _context()))

    assert result.status == "success"
    assert result.repaired is True
    assert len(provider.calls) == 2


def test_gateway_cancellation_is_structured():
    prompts = PromptRegistry()
    provider = FakeProvider([FakeScenario(kind="cancelled")])
    gateway = ModelGateway(profiles=_profiles(), prompts=prompts, providers={"fake": provider})

    result = asyncio.run(gateway.generate_structured(_request(prompts), _context()))

    assert result.status == "cancelled"
    assert result.error.category == "cancelled"


def test_gateway_fallback_is_explicitly_degraded():
    prompts = PromptRegistry()
    provider = FakeProvider(
        [
            FakeScenario(kind="schema_mismatch"),
            FakeScenario(kind="success", output=VALID_JUDGE_OUTPUT),
        ]
    )
    gateway = ModelGateway(
        profiles=_profiles(),
        prompts=prompts,
        providers={"fake": provider},
        repair_enabled=False,
    )
    request = _request(prompts).model_copy(update={"fallback_profile": "fast"})

    result = asyncio.run(gateway.generate_structured(request, _context()))

    assert result.status == "degraded"
    assert result.fallback_used is True
    assert "fallback_from:judge" in result.degradation_reasons
