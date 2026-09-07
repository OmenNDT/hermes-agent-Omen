"""Loopback-only access control.

Requirement families: `HC-PRIVACY`, `HC-PRODUCT`; sources `SRC-026`, `SRC-091`,
`SRC-104…106`.

Single-user, single-machine: there is no account model, so the whole access
story is "the request came from this machine, from a page this server served,
carrying the token this process minted". Each of those is checked separately —
any one of them alone is forgeable.
"""

from __future__ import annotations

import pytest

from hermes_coach.api.security import (
    LOOPBACK_HOSTS,
    AccessRejected,
    LoopbackGuard,
    new_token,
)


PORT = 8731


def guard(token: str = "t" * 32) -> LoopbackGuard:
    return LoopbackGuard(token=token, port=PORT)


def authorize(
    *,
    token: str | None = "t" * 32,
    peer: str | None = "127.0.0.1",
    host: str | None = f"127.0.0.1:{PORT}",
    origin: str | None = f"http://127.0.0.1:{PORT}",
) -> None:
    guard().authorize(token=token, peer=peer, host=host, origin=origin)


def test_a_well_formed_loopback_request_is_accepted() -> None:
    authorize()


def test_a_minted_token_is_unguessable_and_long() -> None:
    first, second = new_token(), new_token()
    assert first != second
    assert len(first) >= 32


@pytest.mark.parametrize("peer", ["127.0.0.1", "::1"])
def test_both_loopback_families_are_accepted(peer: str) -> None:
    authorize(peer=peer)


@pytest.mark.parametrize(
    "peer", ["192.168.1.10", "10.0.0.5", "0.0.0.0", "203.0.113.7", ""]
)
def test_a_non_loopback_peer_is_rejected(peer: str) -> None:
    with pytest.raises(AccessRejected, match="peer"):
        authorize(peer=peer)


def test_a_missing_peer_is_rejected() -> None:
    with pytest.raises(AccessRejected, match="peer"):
        authorize(peer=None)


def test_a_wrong_token_is_rejected() -> None:
    with pytest.raises(AccessRejected, match="token"):
        authorize(token="x" * 32)


def test_a_missing_token_is_rejected() -> None:
    with pytest.raises(AccessRejected, match="token"):
        authorize(token=None)


def test_an_empty_token_is_rejected() -> None:
    with pytest.raises(AccessRejected, match="token"):
        authorize(token="")


def test_a_token_that_is_a_prefix_of_the_real_one_is_rejected() -> None:
    with pytest.raises(AccessRejected, match="token"):
        authorize(token="t" * 16)


@pytest.mark.parametrize("host", LOOPBACK_HOSTS)
def test_every_loopback_host_spelling_is_accepted(host: str) -> None:
    authorize(host=f"{host}:{PORT}", origin=f"http://{host}:{PORT}")


def test_a_foreign_host_header_is_rejected() -> None:
    """DNS rebinding arrives as a loopback peer with someone else's Host."""
    with pytest.raises(AccessRejected, match="host"):
        authorize(host=f"coach.attacker.invalid:{PORT}")


def test_a_host_on_another_port_is_rejected() -> None:
    with pytest.raises(AccessRejected, match="host"):
        authorize(host=f"127.0.0.1:{PORT + 1}")


def test_a_host_without_a_port_is_rejected() -> None:
    with pytest.raises(AccessRejected, match="host"):
        authorize(host="127.0.0.1")


def test_a_missing_host_is_rejected() -> None:
    with pytest.raises(AccessRejected, match="host"):
        authorize(host=None)


def test_a_foreign_origin_is_rejected() -> None:
    with pytest.raises(AccessRejected, match="origin"):
        authorize(origin="https://evil.invalid")


def test_an_origin_on_another_port_is_rejected() -> None:
    with pytest.raises(AccessRejected, match="origin"):
        authorize(origin=f"http://127.0.0.1:{PORT + 1}")


def test_an_absent_origin_is_allowed_for_a_non_browser_client() -> None:
    """Browsers always send Origin; a local script has none to send.

    Absent Origin cannot be a rebinding victim, and peer plus token still apply.
    """
    authorize(origin=None)


def test_an_absent_origin_still_needs_the_token() -> None:
    with pytest.raises(AccessRejected, match="token"):
        authorize(origin=None, token="x" * 32)


def test_allowed_origins_are_exactly_the_loopback_ones() -> None:
    assert guard().allowed_origins() == tuple(
        f"http://{host}:{PORT}" for host in LOOPBACK_HOSTS
    )


def test_the_guard_refuses_to_bind_beyond_loopback() -> None:
    for address in ("0.0.0.0", "192.168.1.10", "::"):
        with pytest.raises(ValueError, match="loopback"):
            LoopbackGuard(token="t" * 32, port=PORT, bind_host=address)


def test_the_rejection_never_quotes_the_expected_token() -> None:
    secret = "s" * 32
    try:
        LoopbackGuard(token=secret, port=PORT).authorize(
            token="x" * 32,
            peer="127.0.0.1",
            host=f"127.0.0.1:{PORT}",
            origin=None,
        )
    except AccessRejected as rejected:
        assert secret not in str(rejected)
    else:  # pragma: no cover - the call above must reject
        pytest.fail("expected rejection")


def test_checks_are_independent_so_one_pass_cannot_carry_another() -> None:
    """A loopback peer must not excuse a bad token, and vice versa."""
    with pytest.raises(AccessRejected, match="peer"):
        authorize(peer="192.168.1.10", token="t" * 32)
    with pytest.raises(AccessRejected, match="token"):
        authorize(peer="127.0.0.1", token="x" * 32)
