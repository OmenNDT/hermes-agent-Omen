"""Choosing the port the launcher is about to announce.

Requirement families: `HC-PRODUCT`; sources `SRC-104…106`.

The launcher prints a URL and then starts uvicorn. So the port in that URL has
to be one this process can actually bind — otherwise the operator is handed a
link that answers, served by whatever else holds the port. That happened: an
older Coach process kept 8799, every restart printed a fresh token for a server
that never came up, and the browser loaded the page (the static route needs no
token) while every WebSocket closed with no reason given. Three tokens in a row
failed identically, which is what a mismatch looks like from the client.

A bind test cannot make the choice atomic — something can still take the port
between the probe and uvicorn's listener. It converts a silent wrong answer into
an ordinary error, which is the part that matters.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator

import pytest

from hermes_coach.bootstrap import LOOPBACK, PortUnavailable, select_port


@pytest.fixture
def occupied() -> Iterator[int]:
    """A loopback port held open for the duration of one test."""
    holder = socket.socket()
    holder.bind((LOOPBACK, 0))
    holder.listen(1)
    try:
        yield holder.getsockname()[1]
    finally:
        holder.close()


def test_zero_resolves_to_a_port_that_can_be_bound() -> None:
    chosen = select_port(0)
    assert 1024 < chosen < 65536
    with socket.socket() as check:
        check.bind((LOOPBACK, chosen))


def test_a_free_requested_port_is_honoured() -> None:
    free = select_port(0)
    assert select_port(free) == free


def test_a_taken_port_is_refused_rather_than_announced(occupied: int) -> None:
    with pytest.raises(PortUnavailable):
        select_port(occupied)


def test_the_refusal_names_the_port_and_what_to_do(occupied: int) -> None:
    """The operator has to be able to act on it without reading the source."""
    with pytest.raises(PortUnavailable) as refused:
        select_port(occupied)
    message = str(refused.value)
    assert str(occupied) in message
    assert "--port" in message


def test_the_probe_does_not_keep_the_port_it_checked() -> None:
    """A probe that held the port would make the server unable to use it."""
    chosen = select_port(0)
    assert select_port(chosen) == chosen
    with socket.socket() as server:
        server.bind((LOOPBACK, chosen))
        server.listen(1)


def test_binding_only_loopback_is_what_gets_checked(occupied: int) -> None:
    """Coach serves loopback, so availability elsewhere is not the question."""
    with pytest.raises(PortUnavailable):
        select_port(occupied)
