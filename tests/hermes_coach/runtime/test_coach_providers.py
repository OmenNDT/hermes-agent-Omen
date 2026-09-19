"""Choosing a model provider: Claude, GPT or Gemini.

Requirement families: `HC-PRODUCT`, `HC-COMPANION`; sources `SRC-070…075`.

Coach needed a paid Claude subscription, which is a wall for anyone it is
shared with. The runtime contract never required Anthropic — the adapter asks
for an object with `run(message) -> str` and an empty `tools` list — so the
other providers are additional agents behind that same contract, not a second
code path through Coach.

Gemini is reached through its OpenAI-compatible endpoint, so one agent class
serves both it and GPT and no new dependency enters the project.

Every test here uses a fake client: this file must stay runnable with no
credential of any kind and no network.
"""

from __future__ import annotations

import pytest

from hermes_cli.coach_provider import (
    PROVIDERS,
    NoCoachCredential,
    OpenAICompatibleAgent,
    resolve_provider,
)


PROMPT = "Bạn là Hermes Coach."
REPLY = '{"question": "Bạn muốn gì?", "coaching_stage": "goal"}'


class FakeCompletions:
    def __init__(self, text: str = REPLY) -> None:
        self.text = text
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)

        class Message:
            content = self.text

        class Choice:
            message = Message()

        class Reply:
            choices = [Choice()]

        return Reply()


class FakeOpenAIClient:
    def __init__(self, text: str = REPLY) -> None:
        self.completions = FakeCompletions(text)

        class Chat:
            pass

        self.chat = Chat()
        self.chat.completions = self.completions


def agent(client: FakeOpenAIClient | None = None, **overrides) -> OpenAICompatibleAgent:
    kwargs = {
        "client": client or FakeOpenAIClient(),
        "model": "gpt-test",
        "ephemeral_system_prompt": PROMPT,
        "enabled_toolsets": [],
        "skip_memory": True,
    }
    kwargs.update(overrides)
    return OpenAICompatibleAgent(**kwargs)


# ── The agent meets the same contract the Anthropic one does ────────────────


def test_a_turn_returns_the_model_text() -> None:
    assert agent().run("Xin chào") == REPLY


def test_the_agent_reports_an_empty_tool_list() -> None:
    """`CoachRuntimeAdapter` fails closed unless this is empty."""
    assert agent().tools == []


def test_no_tools_are_offered_to_the_model() -> None:
    client = FakeOpenAIClient()
    agent(client).run("Xin chào")
    assert "tools" not in client.completions.calls[0]


def test_the_system_prompt_leads_every_request() -> None:
    """Byte-stable prefix: the same first message on every turn."""
    client = FakeOpenAIClient()
    subject = agent(client)
    subject.run("một")
    subject.run("hai")
    for call in client.completions.calls:
        assert call["messages"][0] == {"role": "system", "content": PROMPT}


def test_history_alternates_strictly() -> None:
    client = FakeOpenAIClient()
    subject = agent(client)
    subject.run("một")
    subject.run("hai")
    roles = [m["role"] for m in client.completions.calls[1]["messages"]]
    assert roles == ["system", "user", "assistant", "user"]


def test_the_turn_is_appended_not_replaced() -> None:
    client = FakeOpenAIClient()
    subject = agent(client)
    subject.run("một")
    subject.run("hai")
    contents = [m["content"] for m in client.completions.calls[1]["messages"]]
    assert contents[1] == "một"
    assert contents[3] == "hai"


def test_output_is_bounded() -> None:
    client = FakeOpenAIClient()
    agent(client).run("x")
    sent = client.completions.calls[0]
    assert sent.get("max_completion_tokens") or sent.get("max_tokens")


def test_the_token_parameter_name_is_configurable() -> None:
    """OpenAI wants `max_completion_tokens`; the Gemini endpoint wants
    `max_tokens`. Naming it per provider beats guessing at call time."""
    client = FakeOpenAIClient()
    agent(client, token_param="max_tokens").run("x")
    assert "max_tokens" in client.completions.calls[0]


def test_an_empty_reply_is_an_empty_string_not_a_crash() -> None:
    assert agent(FakeOpenAIClient(text=None)).run("x") == ""


def test_a_failed_turn_leaves_no_half_message_in_the_history() -> None:
    """Two consecutive user messages are rejected by every provider, and the
    adapter keeps one agent per session, so the damage would outlast the turn."""
    client = FakeOpenAIClient()

    def explode(**kwargs):
        raise RuntimeError("mạng hỏng")

    subject = agent(client)
    client.completions.create = explode
    with pytest.raises(RuntimeError):
        subject.run("hỏng")

    client.completions.create = FakeCompletions().create
    subject.run("lần sau")
    assert len(subject._history) == 2


def test_hermes_only_knobs_are_ignored() -> None:
    assert agent(something_hermes_specific="ignored").run("x")


def test_a_credential_is_never_written_into_the_repr() -> None:
    subject = agent(model="gpt-test")
    assert "sk-" not in repr(subject)


# ── Choosing between providers ──────────────────────────────────────────────


def clear_keys(monkeypatch) -> None:
    for entry in PROVIDERS:
        monkeypatch.delenv(entry.env_var, raising=False)
    monkeypatch.delenv("COACH_MODEL", raising=False)


def test_the_claude_subscription_still_wins_by_default(monkeypatch) -> None:
    """Additive, not a change: an existing install must keep its provider."""
    clear_keys(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert resolve_provider(None, has_claude_code=True).name == "claude-code"


def test_an_api_key_is_used_when_there_is_no_subscription(monkeypatch) -> None:
    clear_keys(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert resolve_provider(None, has_claude_code=False).name == "openai"


def test_gemini_is_found_by_its_own_key(monkeypatch) -> None:
    clear_keys(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "g-test")
    assert resolve_provider(None, has_claude_code=False).name == "gemini"


def test_an_explicit_choice_beats_whatever_else_is_present(monkeypatch) -> None:
    clear_keys(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "g-test")
    assert resolve_provider("gemini", has_claude_code=True).name == "gemini"


def test_an_explicit_choice_without_its_key_is_refused(monkeypatch) -> None:
    """Silently falling back would run the Coachee on a model they did not pick."""
    clear_keys(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    with pytest.raises(NoCoachCredential, match="GEMINI_API_KEY"):
        resolve_provider("gemini", has_claude_code=False)


def test_an_unknown_provider_name_is_refused(monkeypatch) -> None:
    clear_keys(monkeypatch)
    with pytest.raises(NoCoachCredential, match="llama"):
        resolve_provider("llama", has_claude_code=True)


def test_no_credential_at_all_names_every_way_out(monkeypatch) -> None:
    """The message is the whole help a stuck user gets, so it lists them all."""
    clear_keys(monkeypatch)
    with pytest.raises(NoCoachCredential) as refusal:
        resolve_provider(None, has_claude_code=False)
    message = str(refusal.value)
    assert "claude auth login" in message
    for entry in PROVIDERS:
        assert entry.env_var in message


def test_the_model_can_be_overridden_without_touching_code(monkeypatch) -> None:
    """A provider renames a model more often than this project ships."""
    clear_keys(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "g-test")
    monkeypatch.setenv("COACH_MODEL", "gemini-experimental")
    assert resolve_provider(None, has_claude_code=False).model == "gemini-experimental"


def test_every_provider_declares_what_it_needs() -> None:
    for entry in PROVIDERS:
        assert entry.env_var and entry.model and entry.label
        assert entry.token_param in ("max_tokens", "max_completion_tokens")


def test_gemini_is_reached_through_its_openai_compatible_endpoint() -> None:
    """This is what lets one agent class serve both, with no new dependency."""
    gemini = next(entry for entry in PROVIDERS if entry.name == "gemini")
    assert gemini.base_url and gemini.base_url.rstrip("/").endswith("/openai")
