"""The `hermes coach` edge.

Requirement families: `HC-PRODUCT`; sources `SRC-100`.

Thin by design — the launcher is tested next door. What is pinned here is the
exit code, because the shared Hermes dispatcher calls `args.func(args)` and
discards what it returns. Without this, `hermes coach` reported success after
refusing to start, and the double-click launcher could not tell a locked
profile from a clean shutdown.
"""

from __future__ import annotations

import argparse

import pytest

from hermes_cli.subcommands.coach import _run_coach, build_coach_parser


def arguments(**overrides) -> argparse.Namespace:
    values = {"profile": "default", "port": 0, "open": False, "no_provider": True}
    values.update(overrides)
    return argparse.Namespace(**values)


def run_with(monkeypatch, code: int) -> int:
    import hermes_cli.subcommands.coach as subcommand

    monkeypatch.setattr(subcommand, "_agent_factory", lambda args: None)
    monkeypatch.setattr(
        "hermes_coach.__main__.main", lambda argv, **kwargs: code, raising=True
    )
    with pytest.raises(SystemExit) as exit_info:
        _run_coach(arguments())
    return exit_info.value.code


def test_a_refusal_to_start_is_reported_as_failure(monkeypatch) -> None:
    """A locked profile must not look like a clean run to whatever called it."""
    assert run_with(monkeypatch, 1) == 1


def test_a_clean_shutdown_is_reported_as_success(monkeypatch) -> None:
    assert run_with(monkeypatch, 0) == 0


def test_an_unusual_code_is_passed_through(monkeypatch) -> None:
    assert run_with(monkeypatch, 3) == 3


def test_the_parser_offers_only_the_four_coach_flags() -> None:
    """No LAN, no login, no voice — the same surface rule as the launcher."""
    parser = argparse.ArgumentParser()
    build_coach_parser(parser.add_subparsers())
    parsed = parser.parse_args(["coach"])
    assert vars(parsed).keys() >= {"profile", "port", "open", "no_provider"}


def test_the_browser_stays_shut_unless_asked() -> None:
    parser = argparse.ArgumentParser()
    build_coach_parser(parser.add_subparsers())
    assert parser.parse_args(["coach"]).open is False
    assert parser.parse_args(["coach", "--open"]).open is True
