"""The Anthropic provider that drives a Coach turn.

Requirement families: `HC-PRODUCT`, `HC-COMPANION`; sources `SRC-070…075`.

Lives in `hermes_cli`, not `hermes_coach`: the architecture boundary forbids the
Coach package from importing `agent.*`, and reading Claude Code credentials and
building the client is exactly that. The CLI edge is allowed to know both sides,
so the provider is wired there and injected. Its test lives here because the
thing being tested is Coach's provider.

These tests use a fake Anthropic client. A live call is a separate, explicit
check — this file must stay runnable with no credential and no network.
"""

from __future__ import annotations

import pytest

from hermes_cli.coach_provider import (
    HAIKU_MODEL,
    AnthropicDirectAgent,
    NoCoachCredential,
    build_coach_agent_factory,
)


class Unauthorized(Exception):
    """What the SDK raises when the OAuth access token has expired."""

    status_code = 401


class Broken(Exception):
    """A failure that is not about the credential."""

    status_code = 500


PROMPT = "Bạn là Hermes Coach."


class FakeMessages:
    def __init__(self, text: str = '{"question": "Bạn muốn gì?"}') -> None:
        self.text = text
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)

        class Block:
            type = "text"

        block = Block()
        block.text = self.text

        class Reply:
            content = [block]

        return Reply()


class FakeClient:
    def __init__(self, text: str = '{"question": "Bạn muốn gì?"}') -> None:
        self.messages = FakeMessages(text)


def agent(client: FakeClient | None = None, **overrides) -> AnthropicDirectAgent:
    kwargs = {
        "client": client or FakeClient(),
        "model": HAIKU_MODEL,
        "ephemeral_system_prompt": PROMPT,
        "enabled_toolsets": [],
        "skip_memory": True,
        "skip_context_files": True,
    }
    kwargs.update(overrides)
    return AnthropicDirectAgent(**kwargs)


def test_the_model_is_haiku() -> None:
    assert "haiku" in HAIKU_MODEL


def test_a_turn_returns_the_model_text() -> None:
    assert agent().run("Xin chào") == '{"question": "Bạn muốn gì?"}'


def test_the_system_prompt_is_sent_as_system_not_as_a_message() -> None:
    """A prompt smuggled into the history would break the cached prefix."""
    client = FakeClient()
    agent(client).run("Xin chào")
    sent = client.messages.calls[0]
    assert sent["system"] == PROMPT
    assert all(message["role"] != "system" for message in sent["messages"])


def test_no_tools_are_offered_to_the_model() -> None:
    client = FakeClient()
    agent(client).run("Xin chào")
    assert "tools" not in client.messages.calls[0]


def test_the_agent_reports_an_empty_tool_list() -> None:
    """`CoachRuntimeAdapter` fails closed unless this is empty."""
    assert agent().tools == []


def test_the_system_prompt_is_byte_identical_across_turns() -> None:
    client = FakeClient()
    subject = agent(client)
    subject.run("một")
    subject.run("hai")
    assert client.messages.calls[0]["system"] == client.messages.calls[1]["system"]


def test_history_alternates_strictly() -> None:
    client = FakeClient()
    subject = agent(client)
    subject.run("một")
    subject.run("hai")
    roles = [message["role"] for message in client.messages.calls[1]["messages"]]
    assert roles == ["user", "assistant", "user"]


def test_the_turn_is_appended_not_replaced() -> None:
    client = FakeClient()
    subject = agent(client)
    subject.run("một")
    subject.run("hai")
    contents = [m["content"] for m in client.messages.calls[1]["messages"]]
    assert contents[0] == "một"
    assert contents[2] == "hai"


def test_several_text_blocks_are_joined() -> None:
    client = FakeClient()

    class Block:
        type = "text"

    first, second = Block(), Block()
    first.text, second.text = '{"question": "a', 'b?"}'

    class Reply:
        content = [first, second]

    client.messages.create = lambda **kwargs: Reply()  # type: ignore[method-assign]
    assert agent(client).run("x") == '{"question": "ab?"}'


def test_non_text_blocks_are_ignored() -> None:
    client = FakeClient()

    class TextBlock:
        type = "text"
        text = "chỉ phần này"

    class OtherBlock:
        type = "thinking"
        text = "không phải phần này"

    class Reply:
        content = [OtherBlock(), TextBlock()]

    client.messages.create = lambda **kwargs: Reply()  # type: ignore[method-assign]
    assert agent(client).run("x") == "chỉ phần này"


def test_an_empty_reply_is_an_empty_string_not_a_crash() -> None:
    client = FakeClient()

    class Reply:
        content: list = []

    client.messages.create = lambda **kwargs: Reply()  # type: ignore[method-assign]
    assert agent(client).run("x") == ""


def test_output_is_bounded() -> None:
    client = FakeClient()
    agent(client).run("x")
    assert client.messages.calls[0]["max_tokens"] > 0


def test_the_factory_refuses_when_no_credential_exists(monkeypatch) -> None:
    """No credential is a reportable state, not a stack trace at first turn."""
    import hermes_cli.coach_provider as provider

    monkeypatch.setattr(provider, "resolve_claude_code_token", lambda: None)
    with pytest.raises(NoCoachCredential):
        build_coach_agent_factory()


def test_the_factory_refuses_a_credential_that_cannot_be_refreshed(monkeypatch) -> None:
    """An expired token the resolver could not renew must fail at wiring time.

    This is the failure that shipped: a stale `accessToken` was accepted here
    and then 401ed on every turn, in front of the Coachee.
    """
    import hermes_cli.coach_provider as provider

    monkeypatch.setattr(provider, "resolve_claude_code_token", lambda: "")
    with pytest.raises(NoCoachCredential):
        build_coach_agent_factory()


def test_the_factory_builds_an_agent_the_adapter_can_use(monkeypatch) -> None:
    import hermes_cli.coach_provider as provider

    monkeypatch.setattr(provider, "resolve_claude_code_token", lambda: "tok")
    monkeypatch.setattr(provider, "build_anthropic_client", lambda key: FakeClient())

    factory = build_coach_agent_factory()
    built = factory(
        provider="anthropic",
        model=HAIKU_MODEL,
        ephemeral_system_prompt=PROMPT,
        enabled_toolsets=[],
        skip_memory=True,
        skip_context_files=True,
        load_soul_identity=False,
        save_trajectories=False,
        quiet_mode=True,
    )
    assert built.tools == []
    assert built.run("Xin chào") == '{"question": "Bạn muốn gì?"}'


def test_the_factory_ignores_hermes_only_knobs(monkeypatch) -> None:
    """The adapter passes Hermes flags; a direct client has no use for them."""
    import hermes_cli.coach_provider as provider

    monkeypatch.setattr(provider, "resolve_claude_code_token", lambda: "tok")
    monkeypatch.setattr(provider, "build_anthropic_client", lambda key: FakeClient())

    factory = build_coach_agent_factory()
    built = factory(
        ephemeral_system_prompt=PROMPT,
        enabled_toolsets=[],
        something_hermes_specific="ignored",
    )
    assert built.run("x")


def test_a_credential_is_never_written_into_the_agent_repr(monkeypatch) -> None:
    import hermes_cli.coach_provider as provider

    monkeypatch.setattr(provider, "resolve_claude_code_token", lambda: "sk-secret")
    monkeypatch.setattr(provider, "build_anthropic_client", lambda key: FakeClient())

    built = build_coach_agent_factory()(ephemeral_system_prompt=PROMPT)
    assert "sk-secret" not in repr(built)


def test_an_expired_token_is_refreshed_and_the_turn_retried_once() -> None:
    """An access token lives about an hour; a Coach session outlives one."""
    expired, renewed = FakeClient(), FakeClient()

    def reject(**kwargs):
        raise Unauthorized("OAuth access token has expired")

    expired.messages.create = reject  # type: ignore[method-assign]
    minted: list[int] = []

    def reauthenticate():
        minted.append(1)
        return renewed

    subject = agent(expired, reauthenticate=reauthenticate)
    assert subject.run("Xin chào") == '{"question": "Bạn muốn gì?"}'
    assert len(minted) == 1
    assert len(renewed.messages.calls) == 1


def test_the_retried_turn_carries_the_same_message() -> None:
    """A retry must be the same turn, not a new one with the message lost."""
    expired, renewed = FakeClient(), FakeClient()
    expired.messages.create = lambda **kwargs: (_ for _ in ()).throw(  # type: ignore[method-assign]
        Unauthorized("expired")
    )
    agent(expired, reauthenticate=lambda: renewed).run("một")
    assert renewed.messages.calls[0]["messages"] == [{"role": "user", "content": "một"}]


def test_a_second_unauthorized_surfaces() -> None:
    """One re-auth, one retry. A credential that stays bad is a real failure."""
    def reject(**kwargs):
        raise Unauthorized("expired")

    first, second = FakeClient(), FakeClient()
    first.messages.create = reject  # type: ignore[method-assign]
    second.messages.create = reject  # type: ignore[method-assign]

    with pytest.raises(Unauthorized):
        agent(first, reauthenticate=lambda: second).run("x")


def test_a_non_auth_failure_is_not_retried() -> None:
    """Only 401 means the credential; retrying anything else doubles the cost."""
    client = FakeClient()
    calls: list[int] = []

    def reject(**kwargs):
        calls.append(1)
        raise Broken("upstream is down")

    client.messages.create = reject  # type: ignore[method-assign]
    with pytest.raises(Broken):
        agent(client, reauthenticate=lambda: FakeClient()).run("x")
    assert len(calls) == 1


def test_a_failed_turn_leaves_no_dangling_user_message() -> None:
    """Two user messages in a row are rejected by the API.

    The adapter caches one agent per session, so a turn that failed and left its
    message behind would poison every later turn in that session, not just its
    own.
    """
    client = FakeClient()
    real_create = client.messages.create
    client.messages.create = lambda **kwargs: (_ for _ in ()).throw(  # type: ignore[method-assign]
        Broken("upstream is down")
    )
    subject = agent(client)
    with pytest.raises(Broken):
        subject.run("một")

    client.messages.create = real_create  # type: ignore[method-assign]
    subject.run("hai")
    roles = [message["role"] for message in client.messages.calls[0]["messages"]]
    assert roles == ["user"]
