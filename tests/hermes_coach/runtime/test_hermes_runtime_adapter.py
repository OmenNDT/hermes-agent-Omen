"""Runtime adapter against a fake provider.

Requirement families: `HC-COMPANION`, `HC-PRIVACY`, `HC-PRODUCT`; sources
`SRC-001`, `SRC-026…029`, `SRC-070…075`, `SRC-092`, `SRC-096`.

The adapter is the only place Coach touches a model. These tests pin the
boundary: no tools, no Hermes memory, no context files, no Hermes session DB, a
byte-stable system prompt, strict role alternation, bounded regeneration, and
nothing reaching a sink before validation.

The provider here is a fake. Real-provider behaviour on Windows is a named
release gate, not something this file may claim.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from hermes_coach.contracts.runtime_contract import (
    CoachingStage,
    CoachOutput,
    RuntimeRequest,
    stable_prompt_fingerprint,
)
from hermes_coach.infrastructure.hermes_runtime_adapter import (
    AdapterConfiguration,
    CoachRuntimeAdapter,
    RuntimeRejected,
)
from hermes_coach.prompt.system_prompt import COACH_SYSTEM_PROMPT


PROMPT_VERSION = "coach-1"
SESSION = "session-1"


class FakeAgent:
    """Stands in for `AIAgent`, recording exactly how it was constructed."""

    instances: list["FakeAgent"] = []

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.calls: list[str] = []
        self.history: list[dict[str, str]] = []
        self.tools: list[str] = []
        self.replies: list[str] = []
        FakeAgent.instances.append(self)

    def run(self, message: str) -> str:
        self.calls.append(message)
        self.history.append({"role": "user", "content": message})
        reply = self.replies.pop(0) if self.replies else valid_payload()
        self.history.append({"role": "assistant", "content": reply})
        return reply


@pytest.fixture(autouse=True)
def reset_agents() -> Iterator[None]:
    FakeAgent.instances = []
    yield
    FakeAgent.instances = []


def valid_payload(question: str = "Điều gì khiến việc này quan trọng với bạn?") -> str:
    return (
        '{"question": "' + question + '", "coaching_stage": "goal"}'
    )


def make_factory(replies: list[str] | None = None, agent_class=None):
    """Bind scripted replies at construction so production needs no test hook."""

    def factory(**kwargs: object):
        agent = (agent_class or FakeAgent)(**kwargs)
        agent.replies = list(replies or [])
        return agent

    return factory


def adapter(replies: list[str] | None = None) -> CoachRuntimeAdapter:
    return CoachRuntimeAdapter(
        AdapterConfiguration(
            prompt_version=PROMPT_VERSION, provider="fake", model="fake-model"
        ),
        agent_factory=make_factory(replies),
    )


def request(
    *,
    turn_id: str = "turn-1",
    stage: CoachingStage = CoachingStage.GOAL,
    message: str = "Tôi muốn chuyển sang vai trò kiến trúc sư",
    prompt_hash: str | None = None,
) -> RuntimeRequest:
    return RuntimeRequest(
        session_id=SESSION,
        turn_id=turn_id,
        prompt_version=PROMPT_VERSION,
        system_prompt_hash=prompt_hash or stable_prompt_fingerprint(COACH_SYSTEM_PROMPT),
        current_stage=stage,
        user_message=message,
        structured_context={"stage": stage.value},
    )


def test_a_valid_reply_becomes_a_validated_result() -> None:
    result = adapter().generate(request())
    assert isinstance(result.output, CoachOutput)
    assert result.output.question.endswith("?")
    assert result.attempts == 1


def test_the_agent_is_constructed_with_no_toolsets() -> None:
    adapter().generate(request())
    assert FakeAgent.instances[0].kwargs["enabled_toolsets"] == []


def test_the_agent_is_constructed_without_hermes_memory_or_context_files() -> None:
    adapter().generate(request())
    kwargs = FakeAgent.instances[0].kwargs
    assert kwargs["skip_memory"] is True
    assert kwargs["skip_context_files"] is True


def test_the_agent_is_given_no_hermes_session_id() -> None:
    """Coach SQLite is the durable truth; a Hermes session DB would be a second."""
    adapter().generate(request())
    kwargs = FakeAgent.instances[0].kwargs
    assert kwargs.get("session_id") is None
    assert kwargs.get("pass_session_id") in (None, False)


def test_the_post_construction_tool_list_is_empty() -> None:
    """Declaring no toolsets is not the same as ending up with no tools."""
    adapter().generate(request())
    assert FakeAgent.instances[0].tools == []


def test_a_tool_capable_agent_fails_closed() -> None:
    class ToolfulAgent(FakeAgent):
        def __init__(self, **kwargs: object) -> None:
            super().__init__(**kwargs)
            self.tools = ["shell"]

    runtime = CoachRuntimeAdapter(
        AdapterConfiguration(
            prompt_version=PROMPT_VERSION, provider="fake", model="fake-model"
        ),
        agent_factory=make_factory(agent_class=ToolfulAgent),
    )
    with pytest.raises(RuntimeRejected, match="tool"):
        runtime.generate(request())


def test_one_agent_serves_the_whole_session() -> None:
    runtime = adapter()
    runtime.generate(request(turn_id="turn-1"))
    runtime.generate(request(turn_id="turn-2"))
    assert len(FakeAgent.instances) == 1


def test_the_system_prompt_is_byte_stable_across_turns() -> None:
    runtime = adapter()
    runtime.generate(request(turn_id="turn-1"))
    first = FakeAgent.instances[0].kwargs["ephemeral_system_prompt"]
    runtime.generate(request(turn_id="turn-2"))
    assert FakeAgent.instances[0].kwargs["ephemeral_system_prompt"] == first
    assert len(FakeAgent.instances) == 1


def test_a_changed_prompt_hash_is_refused_before_inference() -> None:
    """A drifted cache prefix must fail before a request is billed."""
    runtime = adapter()
    with pytest.raises(RuntimeRejected, match="prompt"):
        runtime.generate(request(prompt_hash="0" * 64))
    assert FakeAgent.instances == []


def test_a_changed_prompt_version_is_refused() -> None:
    runtime = adapter()
    other = request().model_copy(update={"prompt_version": "coach-2"})
    with pytest.raises(RuntimeRejected, match="prompt"):
        runtime.generate(other)


def test_dynamic_state_travels_in_the_turn_not_the_system_prompt() -> None:
    """The prompt names the six steps; it must not name the *current* one.

    Checking for the word "options" would fail on the framework description, so
    the real property is that the prompt bytes do not vary with stage.
    """
    adapter().generate(request(stage=CoachingStage.OPTIONS))
    options_prompt = FakeAgent.instances[0].kwargs["ephemeral_system_prompt"]
    options_turn = FakeAgent.instances[0].calls[0]

    FakeAgent.instances.clear()
    adapter().generate(request(stage=CoachingStage.REVIEW))
    review_prompt = FakeAgent.instances[0].kwargs["ephemeral_system_prompt"]
    review_turn = FakeAgent.instances[0].calls[0]

    assert options_prompt == review_prompt == COACH_SYSTEM_PROMPT
    assert "stage: options" in options_turn
    assert "stage: review" in review_turn


def test_role_alternation_is_strict() -> None:
    runtime = adapter()
    runtime.generate(request(turn_id="turn-1"))
    runtime.generate(request(turn_id="turn-2"))
    roles = [entry["role"] for entry in FakeAgent.instances[0].history]
    assert roles == ["user", "assistant", "user", "assistant"]


def test_regeneration_does_not_inject_a_synthetic_user_turn() -> None:
    """A retry is a new attempt at the same turn, not hidden history."""
    runtime = adapter(
        [valid_payload("Bạn nên làm thế này ngay?"), valid_payload()]
    )
    runtime.generate(request())
    agent = FakeAgent.instances[0]
    assert [entry["role"] for entry in agent.history].count("user") == len(agent.calls)


def test_a_rejected_question_is_regenerated_within_the_bound() -> None:
    runtime = adapter([valid_payload("Bạn nên nói chuyện với quản lý ngay?"), valid_payload()])
    result = runtime.generate(request())
    assert result.attempts == 2
    assert "nên" not in result.output.question


def test_regeneration_is_bounded_and_fails_closed() -> None:
    runtime = adapter([valid_payload("Bạn nên làm điều này ngay?")] * 6)
    with pytest.raises(RuntimeRejected, match="policy"):
        runtime.generate(request())


def test_nothing_reaches_the_sink_before_validation() -> None:
    delivered: list[CoachOutput] = []
    runtime = adapter([valid_payload("Bạn nên làm điều này ngay?")] * 6)
    with pytest.raises(RuntimeRejected):
        runtime.generate(request(), sink=delivered.append)
    assert delivered == []


def test_an_accepted_output_reaches_the_sink_exactly_once() -> None:
    delivered: list[CoachOutput] = []
    adapter().generate(request(), sink=delivered.append)
    assert len(delivered) == 1


def test_unparseable_provider_output_is_a_schema_failure() -> None:
    runtime = adapter(["this is not json"] * 6)
    with pytest.raises(RuntimeRejected, match="schema"):
        runtime.generate(request())


def test_a_provider_exception_becomes_a_neutral_error() -> None:
    class ExplodingAgent(FakeAgent):
        def run(self, message: str) -> str:
            raise ConnectionError("upstream 503 for key sk-live-secret")

    runtime = CoachRuntimeAdapter(
        AdapterConfiguration(
            prompt_version=PROMPT_VERSION, provider="fake", model="fake-model"
        ),
        agent_factory=make_factory(agent_class=ExplodingAgent),
    )
    with pytest.raises(RuntimeRejected) as raised:
        runtime.generate(request())
    assert "sk-live-secret" not in str(raised.value)
    assert raised.value.failure.code == "provider_error"
    assert raised.value.failure.retryable


def test_a_failure_carries_a_correlation_id_and_no_prompt() -> None:
    runtime = adapter(["not json"] * 6)
    with pytest.raises(RuntimeRejected) as raised:
        runtime.generate(request())
    failure = raised.value.failure
    assert raised.value.correlation_id
    assert COACH_SYSTEM_PROMPT[:40] not in failure.safe_message


def test_raw_rejected_content_is_never_in_the_error(
) -> None:
    runtime = adapter([valid_payload("Bạn nên bỏ việc ngay?")] * 6)
    with pytest.raises(RuntimeRejected) as raised:
        runtime.generate(request())
    assert "bỏ việc" not in str(raised.value)
    assert "bỏ việc" not in raised.value.failure.safe_message


def test_usage_is_accounted_across_regeneration_attempts() -> None:
    runtime = adapter([valid_payload("Bạn nên nói chuyện với quản lý ngay?"), valid_payload()])
    result = runtime.generate(request())
    assert result.usage.input_tokens > 0
    assert result.usage.output_tokens > 0


def test_the_adapter_exposes_no_hermes_shapes() -> None:
    """The caller sees Coach DTOs; `AIAgent` stays behind the boundary."""
    result = adapter().generate(request())
    assert type(result.output).__module__.startswith("hermes_coach.")
    assert not hasattr(result, "agent")


# The turn must state the output contract, and the reply must survive the
# markdown fence a text model puts around JSON. Both were found by running a
# real turn against Haiku: it guessed `stage` and `rationale` against a
# `extra="forbid"` model, and wrapped the object in ```json.


def test_the_turn_states_the_required_output_keys() -> None:
    """The model cannot satisfy a contract nobody showed it."""
    subject = adapter()
    subject.generate(request())
    sent = FakeAgent.instances[0].calls[0]
    assert "question" in sent
    assert "coaching_stage" in sent


def test_the_turn_lists_the_allowed_stage_values() -> None:
    subject = adapter()
    subject.generate(request())
    sent = FakeAgent.instances[0].calls[0]
    for stage in CoachingStage:
        assert stage.value in sent


def test_the_turn_forbids_extra_keys_because_the_schema_does() -> None:
    subject = adapter()
    subject.generate(request())
    assert "extra" in FakeAgent.instances[0].calls[0].lower()


def test_a_fenced_reply_is_accepted() -> None:
    fenced = "```json\n" + valid_payload() + "\n```"
    result = adapter([fenced]).generate(request())
    assert result.output.question.endswith("?")
    assert result.attempts == 1


def test_a_bare_fence_without_a_language_is_accepted() -> None:
    result = adapter(["```\n" + valid_payload() + "\n```"]).generate(request())
    assert result.attempts == 1


def test_prose_around_the_fence_is_discarded() -> None:
    reply = "Đây là câu hỏi:\n```json\n" + valid_payload() + "\n```\nHy vọng giúp ích."
    assert adapter([reply]).generate(request()).attempts == 1


def test_an_unfenced_reply_still_works() -> None:
    assert adapter([valid_payload()]).generate(request()).attempts == 1


def test_a_fence_around_something_that_is_not_json_still_fails() -> None:
    """Tolerating the fence must not tolerate a wrong payload."""
    with pytest.raises(RuntimeRejected) as rejected:
        adapter(["```json\nkhông phải JSON\n```"] * 6).generate(request())
    assert rejected.value.failure.code == "schema_error"


def test_a_reply_with_a_forbidden_extra_key_still_fails() -> None:
    payload = '{"question": "Bạn muốn gì?", "coaching_stage": "goal", "rationale": "x"}'
    with pytest.raises(RuntimeRejected) as rejected:
        adapter([payload] * 6).generate(request())
    assert rejected.value.failure.code == "schema_error"
