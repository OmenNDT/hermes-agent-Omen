"""The `python -m hermes_coach` launcher.

Requirement families: `HC-PRODUCT`, `HC-PRIVACY`; sources `SRC-100`,
`SRC-104…106`.

The server itself is exercised elsewhere; what matters here is what the
launcher does around it — argument handling, the profile lock, and refusing to
start a second writer instead of racing it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hermes_coach.__main__ import build_parser, main, register_methods
from hermes_coach.bootstrap import coach_profile, profile_lock


@pytest.fixture
def hermes_home(tmp_path, monkeypatch) -> Path:
    home = tmp_path / "hermes-home"
    monkeypatch.setenv("HERMES_HOME", str(home))
    return home


def test_the_default_profile_and_port_need_no_arguments() -> None:
    arguments = build_parser().parse_args([])
    assert arguments.profile == "default"
    assert arguments.port == 0


def test_a_profile_and_port_can_be_chosen() -> None:
    arguments = build_parser().parse_args(["--profile", "work", "--port", "8731"])
    assert (arguments.profile, arguments.port) == ("work", 8731)


def test_there_is_no_flag_for_lan_login_or_voice() -> None:
    """The launcher must not offer what the product does not have."""
    help_text = build_parser().format_help().lower()
    for absent in ("--host", "--lan", "--login", "--password", "--voice", "0.0.0.0"):
        assert absent not in help_text


def test_a_locked_profile_is_reported_instead_of_raced(
    hermes_home: Path, capsys
) -> None:
    profile = coach_profile("busy")
    profile.root.mkdir(parents=True, exist_ok=True)

    with profile_lock(profile):
        exit_code = main(["--profile", "busy"])

    assert exit_code == 1
    assert "already holds profile" in capsys.readouterr().out


def test_the_console_is_switched_to_utf8_before_anything_prints() -> None:
    """This bug shipped once and killed the launcher at startup.

    The disclosure is Vietnamese and a Windows console defaults to a legacy
    codepage, so the first print raised `UnicodeEncodeError` before the server
    existed. Only running the launcher for real surfaced it.
    """
    reconfigured: list[dict] = []

    class LegacyStream:
        def reconfigure(self, **kwargs) -> None:
            reconfigured.append(kwargs)

    import hermes_coach.__main__ as launcher

    original_out, original_err = launcher.sys.stdout, launcher.sys.stderr
    launcher.sys.stdout, launcher.sys.stderr = LegacyStream(), LegacyStream()
    try:
        launcher.use_utf8_console()
    finally:
        launcher.sys.stdout, launcher.sys.stderr = original_out, original_err

    assert reconfigured == [
        {"encoding": "utf-8", "errors": "replace"},
        {"encoding": "utf-8", "errors": "replace"},
    ]


def test_a_stream_without_reconfigure_is_left_alone() -> None:
    """Captured streams under pytest need not support it."""
    import hermes_coach.__main__ as launcher

    original_out = launcher.sys.stdout
    launcher.sys.stdout = object()
    try:
        launcher.use_utf8_console()
    finally:
        launcher.sys.stdout = original_out


def test_the_disclosure_survives_a_console_that_cannot_render_it() -> None:
    """`errors="replace"` means a limited console degrades, never crashes."""
    from hermes_coach.bootstrap import disclosure

    encoded = disclosure()["note"].encode("cp1252", errors="replace")
    assert encoded


def test_the_launcher_registers_the_whole_coach_surface(hermes_home: Path) -> None:
    """The launcher exposes exactly what `register_coach_methods` defines.

    A relation, not a second copy of the list: the literal surface lives in
    `test_rpc_methods.py`, and duplicating it here only produced two places to
    forget.
    """
    from hermes_coach.api.app import MethodRegistry
    from hermes_coach.api.methods import register_coach_methods
    from hermes_coach.bootstrap import start

    _handshake, database = start(coach_profile(), port=0, now="2026-06-01T00:00:00Z")
    try:
        reference = MethodRegistry()
        register_coach_methods(
            reference, database, adapter=None, clock=lambda: "2026-06-01T00:00:00Z"
        )
        assert set(register_methods(database).names()) == set(reference.names())
    finally:
        database.close()


def test_the_launcher_starts_without_a_provider(hermes_home: Path) -> None:
    """First run has no provider configured; the server must still come up."""
    from hermes_coach.bootstrap import start

    _handshake, database = start(coach_profile(), port=0, now="2026-06-01T00:00:00Z")
    try:
        registry = register_methods(database)
        # `coach.turn` is registered either way — it answers
        # `provider_not_configured` rather than being absent, so the UI gets a
        # reason instead of `unknown_method`.
        assert registry.get("coach.turn") is not None
    finally:
        database.close()


# Where the built UI comes from. Two locations because there are two ways to
# run Coach: from a wheel and from a checkout.


def test_a_checkout_finds_the_vite_build() -> None:
    from hermes_coach.__main__ import resolve_ui_directory

    found = resolve_ui_directory()
    # This repo has a build, so the resolver must find one. Asserting the name
    # rather than the full path keeps the test honest on any checkout.
    assert found is not None
    assert found.name in {"dist", "web"}
    assert (found / "index.html").is_file()


def test_a_packaged_build_wins_over_a_checkout(monkeypatch, tmp_path) -> None:
    """A wheel must serve its own UI, not one left in a sibling directory."""
    import hermes_coach.__main__ as launcher

    packaged = tmp_path / "hermes_coach" / "web"
    packaged.mkdir(parents=True)
    (packaged / "index.html").write_text("packaged", encoding="utf-8")
    checkout = tmp_path / "apps" / "hermes-coach" / "dist"
    checkout.mkdir(parents=True)
    (checkout / "index.html").write_text("checkout", encoding="utf-8")

    monkeypatch.setattr(launcher, "__file__", str(tmp_path / "hermes_coach" / "x.py"))
    assert launcher.resolve_ui_directory() == packaged


def test_no_build_anywhere_is_not_an_error(monkeypatch, tmp_path) -> None:
    import hermes_coach.__main__ as launcher

    (tmp_path / "hermes_coach").mkdir()
    monkeypatch.setattr(launcher, "__file__", str(tmp_path / "hermes_coach" / "x.py"))
    assert launcher.resolve_ui_directory() is None


# Opening the browser. A single-user local app prints a URL carrying a
# one-time token, and copying that by hand is the whole friction the
# double-click launcher exists to remove.


def test_the_browser_is_not_opened_unless_asked() -> None:
    """Default off, so an automated run never launches a browser."""
    assert build_parser().parse_args([]).open is False


def test_the_browser_can_be_asked_for() -> None:
    assert build_parser().parse_args(["--open"]).open is True


def test_the_opened_url_carries_the_port_and_token() -> None:
    """A URL without the token loads a page that cannot reach the socket."""
    from hermes_coach.__main__ import browser_url

    assert browser_url(8990, "tok-123") == "http://127.0.0.1:8990?token=tok-123"


def test_the_browser_waits_until_the_port_accepts(monkeypatch) -> None:
    """Opening too early shows the browser a connection error, not the app."""
    import hermes_coach.__main__ as launcher

    accepting: list[bool] = [False, False, True]
    opened: list[str] = []
    monkeypatch.setattr(launcher, "_port_accepts", lambda port: accepting.pop(0))
    monkeypatch.setattr(launcher.webbrowser, "open", lambda url: opened.append(url))

    launcher._open_when_ready(8990, "tok", attempts=5, pause=0)
    assert opened == ["http://127.0.0.1:8990?token=tok"]


def test_a_port_that_never_accepts_opens_nothing(monkeypatch) -> None:
    import hermes_coach.__main__ as launcher

    opened: list[str] = []
    monkeypatch.setattr(launcher, "_port_accepts", lambda port: False)
    monkeypatch.setattr(launcher.webbrowser, "open", lambda url: opened.append(url))

    launcher._open_when_ready(8990, "tok", attempts=3, pause=0)
    assert opened == []


def test_a_browser_that_fails_to_open_does_not_take_the_server_down(monkeypatch) -> None:
    """The server is the product; the browser is a convenience."""
    import hermes_coach.__main__ as launcher

    def explode(url: str) -> None:
        raise OSError("no browser on this machine")

    monkeypatch.setattr(launcher, "_port_accepts", lambda port: True)
    monkeypatch.setattr(launcher.webbrowser, "open", explode)

    launcher._open_when_ready(8990, "tok", attempts=1, pause=0)


# Which model is in use, said at startup.
#
# Printed by the launcher rather than by the CLI edge that resolves it: the
# edge runs before `use_utf8_console`, so its Vietnamese reached a cp1252
# console as mojibake. Every other startup line already prints from here.


def test_the_chosen_model_is_announced(capsys) -> None:
    from hermes_coach.__main__ import announce_provider

    class Choice:
        label = "Google Gemini"
        model = "gemini-2.0-flash"

    class Factory:
        choice = Choice()

    announce_provider(Factory())
    printed = capsys.readouterr().out
    assert "Google Gemini" in printed
    assert "gemini-2.0-flash" in printed


def test_a_run_without_a_provider_announces_nothing(capsys) -> None:
    from hermes_coach.__main__ import announce_provider

    announce_provider(None)
    assert capsys.readouterr().out == ""


def test_a_factory_with_no_choice_is_not_an_error(capsys) -> None:
    """A test double, or an older factory, must not break startup."""
    from hermes_coach.__main__ import announce_provider

    announce_provider(lambda **kwargs: None)
    assert capsys.readouterr().out == ""
