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


class NoCoachCredential(RuntimeError):
    """No usable credential was found. Reportable, not a crash mid-turn."""


def _is_unauthorized(error: Exception) -> bool:
    """Recognise a 401 without importing the SDK's exception hierarchy.

    Every Anthropic status error carries `status_code`; matching on the class
    would tie this module to one SDK version for no extra certainty.
    """
    return getattr(error, "status_code", None) == UNAUTHORIZED


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


def build_coach_agent_factory(model: str = HAIKU_MODEL):
    """Return the factory `CoachRuntimeAdapter` calls to create its agent.

    Raises `NoCoachCredential` here, at wiring time, rather than letting the
    first coaching turn fail in front of the Coachee.
    """
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


def _fresh_client() -> Any:
    """A client holding a token that is valid right now.

    The resolver refreshes an expired credential and writes the rotated pair
    back, so this is cheap when the token is still good and self-healing when it
    is not. Only a credential that cannot be refreshed reaches the operator.
    """
    token = resolve_claude_code_token()
    if not token:
        raise NoCoachCredential(
            "no valid Claude Code credential; run `claude login`, then start Coach again"
        )
    return build_anthropic_client(token)


def _text_of(reply: Any) -> str:
    """Join the text blocks, ignoring anything else the model returned."""
    return "".join(
        getattr(block, "text", "")
        for block in getattr(reply, "content", [])
        if getattr(block, "type", None) == "text"
    )
