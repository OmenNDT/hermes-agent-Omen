"""The Anthropic provider for Hermes Coach.

This lives in `hermes_cli` rather than `hermes_coach` on purpose. The Coach
package is forbidden from importing `agent.*` — a boundary enforced by
`test_has_no_login_lan_or_dashboard_pty_surface`'s sibling check — and reading
Claude Code credentials plus building the client is exactly that import. The CLI
edge is the layer allowed to know both sides, so the provider is assembled here
and injected into `CoachRuntimeAdapter`, which keeps Coach's core free of Hermes
internals.

Credential: the Claude Code OAuth token, and only that. It is a subscription
credential issued for Claude Code, reused at the operator's explicit
instruction, so this is a deliberate choice rather than the default one. An
`ANTHROPIC_API_KEY` would be the unambiguous path; supporting it is three lines
whenever one exists, and is deliberately not written until then. Nothing here
logs, stores or renders the token.

The token is *resolved*, not merely read. `read_claude_code_credentials` hands
back whatever is on disk including an expired credential, so a provider that
only checked for a non-empty `accessToken` started cleanly and then failed every
turn with `401 OAuth access token has expired` — which is what happened, and is
what the resolver below prevents. An access token is good for about an hour and
a Coach session outlives one, so the check cannot be a startup-only gate either:
a 401 mid-session re-authenticates once and retries the same turn.
"""

from __future__ import annotations

from collections.abc import Callable
import os
from dataclasses import dataclass
from typing import Any

from agent.anthropic_adapter import (
    # Private on purpose, imported on purpose. It re-reads the live credential
    # sources first and adopts a token Claude Code has already rotated to,
    # rather than racing it with a refresh token that may now be spent —
    # single-use refresh tokens make that race real. Reimplementing the public
    # pieces here would drop exactly that handling.
    _resolve_claude_code_token_from_credentials as resolve_claude_code_token,
    build_anthropic_client,
)


HAIKU_MODEL = "claude-haiku-4-5-20251001"

# One Coach question is short. A large ceiling would only pay for a model that
# ignored the single-question contract.
MAX_OUTPUT_TOKENS = 1024

UNAUTHORIZED = 401


# Gemini speaks OpenAI's wire format at this endpoint, so one agent class and
# one SDK serve both it and GPT. A native Gemini client would be a second code
# path and a new dependency for no behaviour Coach uses.
GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

# Overridable because providers rename models far more often than this project
# ships. A rejected model name is then a one-line fix for the operator.
MODEL_OVERRIDE_ENV = "COACH_MODEL"


@dataclass(frozen=True)
class ProviderChoice:
    """One way to reach a model, resolved before the first coaching turn."""

    name: str
    label: str
    env_var: str
    model: str
    # OpenAI's newer models require `max_completion_tokens`; the Gemini
    # endpoint accepts only `max_tokens`. Naming it per provider beats
    # discovering the difference from a rejected request mid-session.
    token_param: str = "max_completion_tokens"
    base_url: str | None = None
    api_key: str | None = None

    def with_key(self, api_key: str, model: str) -> "ProviderChoice":
        return ProviderChoice(
            name=self.name,
            label=self.label,
            env_var=self.env_var,
            model=model,
            token_param=self.token_param,
            base_url=self.base_url,
            api_key=api_key,
        )


# Order is the fallback order when nothing was asked for explicitly.
PROVIDERS: tuple[ProviderChoice, ...] = (
    ProviderChoice(
        name="anthropic",
        label="Claude (API key)",
        env_var="ANTHROPIC_API_KEY",
        model=HAIKU_MODEL,
        token_param="max_tokens",
    ),
    ProviderChoice(
        name="openai",
        label="OpenAI GPT",
        env_var="OPENAI_API_KEY",
        model="gpt-4o-mini",
    ),
    ProviderChoice(
        name="gemini",
        label="Google Gemini",
        env_var="GEMINI_API_KEY",
        model="gemini-2.0-flash",
        token_param="max_tokens",
        base_url=GEMINI_OPENAI_BASE_URL,
    ),
)

CLAUDE_CODE = ProviderChoice(
    name="claude-code",
    label="Claude (tài khoản Claude Code)",
    env_var="(không cần)",
    model=HAIKU_MODEL,
    token_param="max_tokens",
)


class NoCoachCredential(RuntimeError):
    """No usable credential was found. Reportable, not a crash mid-turn."""


def _is_unauthorized(error: Exception) -> bool:
    """Recognise a 401 without importing the SDK's exception hierarchy.

    Every Anthropic status error carries `status_code`; matching on the class
    would tie this module to one SDK version for no extra certainty.
    """
    return getattr(error, "status_code", None) == UNAUTHORIZED


def resolve_provider(
    requested: str | None, *, has_claude_code: bool
) -> ProviderChoice:
    """Decide which model Coach will use, before it is needed.

    A Claude Code subscription still wins when nothing was asked for, so an
    existing install keeps the provider it had. Anything else would let an
    `OPENAI_API_KEY` that happens to be set for the rest of Hermes silently
    move Coach onto a different model.

    An explicit choice is never quietly downgraded: asking for Gemini without a
    Gemini key is an error, not a reason to run something else.
    """
    by_name = {entry.name: entry for entry in PROVIDERS}
    override = os.environ.get(MODEL_OVERRIDE_ENV, "").strip()

    if requested:
        if requested == CLAUDE_CODE.name:
            if not has_claude_code:
                raise NoCoachCredential(
                    "chọn claude-code nhưng máy chưa đăng nhập; chạy `claude auth login`"
                )
            return CLAUDE_CODE.with_key("", override or CLAUDE_CODE.model)
        entry = by_name.get(requested)
        if entry is None:
            known = ", ".join([*by_name, CLAUDE_CODE.name])
            raise NoCoachCredential(
                f"không biết nhà cung cấp {requested!r}; chọn một trong: {known}"
            )
        key = os.environ.get(entry.env_var, "").strip()
        if not key:
            raise NoCoachCredential(
                f"chọn {entry.name} nhưng chưa đặt {entry.env_var}"
            )
        return entry.with_key(key, override or entry.model)

    if has_claude_code:
        return CLAUDE_CODE.with_key("", override or CLAUDE_CODE.model)

    for entry in PROVIDERS:
        key = os.environ.get(entry.env_var, "").strip()
        if key:
            return entry.with_key(key, override or entry.model)

    keys = ", ".join(entry.env_var for entry in PROVIDERS)
    raise NoCoachCredential(
        "chưa có cách nào để gọi mô hình. Chọn một trong hai:\n"
        "  - đăng nhập tài khoản Claude: `claude auth login`\n"
        f"  - hoặc đặt một trong các biến môi trường: {keys}"
    )


class OpenAICompatibleAgent:
    """The adapter's agent, over any endpoint that speaks OpenAI's wire format.

    Serves GPT and Gemini alike. The system prompt leads every request as the
    first message rather than being folded into the history, which is what
    keeps the cached prefix byte-identical as the conversation grows.
    """

    # The adapter refuses any agent that reports tools. None are ever sent.
    tools: list[str] = []

    def __init__(
        self,
        *,
        client: Any,
        ephemeral_system_prompt: str,
        model: str,
        max_tokens: int = MAX_OUTPUT_TOKENS,
        token_param: str = "max_completion_tokens",
        **_hermes_only: Any,
    ) -> None:
        self._client = client
        self._model = model
        self._system = ephemeral_system_prompt
        self._max_tokens = max_tokens
        self._token_param = token_param
        self._history: list[dict[str, str]] = []

    def run(self, message: str) -> str:
        self._history.append({"role": "user", "content": message})
        try:
            reply = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": self._system},
                    *self._history,
                ],
                **{self._token_param: self._max_tokens},
            )
        except Exception:
            # A turn that never reached the model is not part of the
            # conversation. Leaving it in would send two consecutive user
            # messages next time, which every provider rejects.
            self._history.pop()
            raise
        text = _text_of_choice(reply)
        self._history.append({"role": "assistant", "content": text})
        return text

    def __repr__(self) -> str:
        # Explicit, so a traceback cannot spill the client and its credential.
        return f"OpenAICompatibleAgent(model={self._model!r}, turns={len(self._history)})"


def _text_of_choice(reply: Any) -> str:
    """The assistant text, or empty when the model returned none."""
    choices = getattr(reply, "choices", None) or []
    if not choices:
        return ""
    return getattr(getattr(choices[0], "message", None), "content", "") or ""


class AnthropicDirectAgent:
    """The slice of an agent `CoachRuntimeAdapter` needs, over the Messages API.

    No tools are offered, so there is nothing for the model to call. The system
    prompt is sent in the `system` field on every request, byte-identical, which
    is what keeps the cached prefix stable — putting it in the message history
    would move it as the conversation grows.
    """

    def __init__(
        self,
        *,
        client: Any,
        ephemeral_system_prompt: str,
        model: str = HAIKU_MODEL,
        max_tokens: int = MAX_OUTPUT_TOKENS,
        reauthenticate: Callable[[], Any] | None = None,
        **_hermes_only: Any,
    ) -> None:
        # `**_hermes_only` swallows the flags the adapter passes for an
        # `AIAgent` — skip_memory, enabled_toolsets and friends. A direct client
        # has no memory, no toolsets and no context files to skip, so honouring
        # them is a no-op rather than something to translate.
        self._client = client
        self._model = model
        self._system = ephemeral_system_prompt
        self._max_tokens = max_tokens
        self._reauthenticate = reauthenticate
        self._history: list[dict[str, str]] = []

    # The adapter refuses any agent that reports tools. An empty list is the
    # honest answer here: none are ever sent.
    tools: list[str] = []

    def run(self, message: str) -> str:
        self._history.append({"role": "user", "content": message})
        try:
            reply = self._create()
        except Exception as error:
            if not (_is_unauthorized(error) and self._reauthenticate is not None):
                # A turn that never reached the model is not part of the
                # conversation. Leaving it in would send two consecutive user
                # messages on the next attempt, which the API rejects — and the
                # adapter caches one agent per session, so the damage would
                # outlast the failed turn.
                self._history.pop()
                raise
            # The access token expired under a live session. One re-auth, one
            # retry: a second failure is a real failure and must surface.
            self._client = self._reauthenticate()
            try:
                reply = self._create()
            except Exception:
                self._history.pop()
                raise
        text = _text_of(reply)
        self._history.append({"role": "assistant", "content": text})
        return text

    def _create(self) -> Any:
        return self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=self._system,
            messages=list(self._history),
        )

    def __repr__(self) -> str:
        # Explicit, so a traceback or a log line cannot spill the client and the
        # credential it holds.
        return f"AnthropicDirectAgent(model={self._model!r}, turns={len(self._history)})"


def build_coach_agent_factory(provider: str | None = None):
    """Return the factory `CoachRuntimeAdapter` calls to create its agent.

    Resolves the provider here, at wiring time, rather than letting the first
    coaching turn fail in front of the Coachee. The returned factory also
    carries `choice`, so the launcher can say which model it is about to use —
    a silent provider switch is worse than a missing one.
    """
    choice = resolve_provider(provider, has_claude_code=_has_claude_code())

    if choice.name == CLAUDE_CODE.name:
        factory = _claude_code_factory(choice.model)
    else:
        factory = _api_key_factory(choice)

    # Attached rather than returned as a pair: `agent_factory` is passed on to
    # the adapter as a bare callable, and widening that seam to a tuple would
    # change a contract three modules rely on for one line of console output.
    factory.choice = choice
    return factory


def _claude_code_factory(model: str):
    """The subscription path: a refreshable OAuth token, no API key."""
    # One client, shared by every session and replaced in place when a token
    # expires, so a re-auth in one session does not leave the others stale.
    holder: dict[str, Any] = {"client": _fresh_client()}

    def reauthenticate() -> Any:
        holder["client"] = _fresh_client()
        return holder["client"]

    def factory(**kwargs: Any) -> AnthropicDirectAgent:
        kwargs.pop("model", None)
        return AnthropicDirectAgent(
            client=holder["client"],
            model=model,
            reauthenticate=reauthenticate,
            **kwargs,
        )

    return factory


def _api_key_factory(choice: ProviderChoice):
    """The API-key path, shared by Claude, GPT and Gemini.

    Anthropic keeps its own SDK because its request shape differs; GPT and
    Gemini share one, because Gemini's compatible endpoint speaks the same
    wire format. The client is built once and reused: an API key does not
    expire mid-session the way an OAuth token does.
    """
    if choice.name == "anthropic":
        client = build_anthropic_client(choice.api_key or "")

        def anthropic_factory(**kwargs: Any) -> AnthropicDirectAgent:
            kwargs.pop("model", None)
            return AnthropicDirectAgent(
                client=client, model=choice.model, **kwargs
            )

        return anthropic_factory

    from openai import OpenAI

    client = OpenAI(api_key=choice.api_key, base_url=choice.base_url)

    def openai_factory(**kwargs: Any) -> OpenAICompatibleAgent:
        kwargs.pop("model", None)
        return OpenAICompatibleAgent(
            client=client,
            model=choice.model,
            token_param=choice.token_param,
            **kwargs,
        )

    return openai_factory


def _has_claude_code() -> bool:
    """Whether a Claude Code credential is usable right now.

    Asked without raising, because a missing subscription is now an ordinary
    state: it just means one of the API-key providers is used instead.
    """
    try:
        return bool(resolve_claude_code_token())
    except Exception:
        return False


def _fresh_client() -> Any:
    """A client holding a token that is valid right now.

    The resolver refreshes an expired credential and writes the rotated pair
    back, so this is cheap when the token is still good and self-healing when it
    is not. Only a credential that cannot be refreshed reaches the operator.
    """
    token = resolve_claude_code_token()
    if not token:
        raise NoCoachCredential(
            "no valid Claude Code credential; run `claude auth login`, then start Coach again"
        )
    return build_anthropic_client(token)


def _text_of(reply: Any) -> str:
    """Join the text blocks, ignoring anything else the model returned."""
    return "".join(
        getattr(block, "text", "")
        for block in getattr(reply, "content", [])
        if getattr(block, "type", None) == "text"
    )
