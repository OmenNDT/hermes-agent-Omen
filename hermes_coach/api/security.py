"""Access control for a single-user loopback server.

Requirement families: `HC-PRIVACY`, `HC-PRODUCT`; sources `SRC-026`, `SRC-091`,
`SRC-104…106`.

There is no account model, and for a single-user local app there should not be
one — a login screen would be ceremony protecting nothing new. What replaces it
is three independent facts:

- the connection came from this machine (peer),
- it addressed this server by a loopback name and this port (Host),
- it carries the token this process minted at startup (token).

They are checked separately because each is forgeable alone. A page on a hostile
site can reach `127.0.0.1` from the victim's browser, so the peer address proves
little by itself; a rebinding attack arrives as a loopback peer carrying someone
else's Host; and a token in a URL someone pasted is no longer secret.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass


# Every spelling a browser or client may legitimately use for this machine.
LOOPBACK_HOSTS: tuple[str, ...] = ("127.0.0.1", "localhost", "[::1]")

LOOPBACK_PEERS: frozenset[str] = frozenset({"127.0.0.1", "::1"})

TOKEN_BYTES = 32


class AccessRejected(PermissionError):
    """The request failed one of the loopback checks."""


def new_token() -> str:
    """Mint the per-process token. It lives in memory and is never persisted."""
    return secrets.token_urlsafe(TOKEN_BYTES)


@dataclass(frozen=True)
class LoopbackGuard:
    token: str
    port: int
    bind_host: str = "127.0.0.1"

    def __post_init__(self) -> None:
        if self.bind_host not in LOOPBACK_PEERS:
            raise ValueError(
                f"Coach binds loopback only; {self.bind_host!r} is not a loopback address"
            )

    def allowed_origins(self) -> tuple[str, ...]:
        return tuple(f"http://{host}:{self.port}" for host in LOOPBACK_HOSTS)

    def allowed_hosts(self) -> tuple[str, ...]:
        return tuple(f"{host}:{self.port}" for host in LOOPBACK_HOSTS)

    def authorize_page(
        self,
        *,
        peer: str | None,
        host: str | None,
        origin: str | None,
    ) -> None:
        """The same checks as `authorize`, minus the token.

        A browser cannot attach a token to the asset requests `index.html`
        triggers, so a token-gated page is an unloadable page. The page and its
        bundle carry no Coachee data; the WebSocket, which is the only thing
        that reaches data, still needs the token. Machine and origin are checked
        here exactly as they are there, so serving the page opens nothing wider
        than the socket already allows.
        """
        if peer not in LOOPBACK_PEERS:
            raise AccessRejected("peer is not a loopback address")
        if host not in self.allowed_hosts():
            raise AccessRejected("host header is not this loopback server")
        if origin is not None and origin not in self.allowed_origins():
            raise AccessRejected("origin is not a loopback origin")

    def authorize(
        self,
        *,
        token: str | None,
        peer: str | None,
        host: str | None,
        origin: str | None,
    ) -> None:
        """Raise `AccessRejected` unless every check passes.

        Order is deliberate: cheapest and least secret-dependent first, so a
        probe learns "wrong machine" before it learns anything about the token.
        """
        # A browser always sends Origin. Its absence means a local script, which
        # cannot be the victim of a rebinding or cross-site request.
        self.authorize_page(peer=peer, host=host, origin=origin)
        if not token or not secrets.compare_digest(token, self.token):
            raise AccessRejected("token does not match this session")
