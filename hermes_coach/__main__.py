"""Run one Coach backend: `python -m hermes_coach`.

Requirement families: `HC-PRODUCT`, `HC-PRIVACY`; sources `SRC-100`,
`SRC-104…106`.

One process, one profile, loopback only. The disclosure is printed before the
server starts, because a user should learn the store is unencrypted before they
put anything in it.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import uvicorn

from hermes_coach.api.app import MethodRegistry, create_app
from hermes_coach.api.methods import register_coach_methods
from hermes_coach.bootstrap import (
    DEFAULT_PROFILE,
    LOOPBACK,
    PortUnavailable,
    ProfileLocked,
    coach_profile,
    profile_lock,
    start,
    use_selector_event_loop,
)
from hermes_coach.application.coaching_turn_service import (
    DEFAULT_PROMPT_VERSION,
)
from hermes_coach.domain.clock import render
from hermes_coach.infrastructure.sqlite.database import CoachDatabase


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hermes-coach", description="Hermes Coach")
    parser.add_argument("--profile", default=DEFAULT_PROFILE)
    parser.add_argument(
        "--port", type=int, default=0, help="0 picks a free loopback port"
    )
    return parser


def register_methods(
    database: CoachDatabase, adapter: object | None = None
) -> MethodRegistry:
    """Coach RPC surface.

    `adapter=None` until a provider is wired: `coach.turn` then answers with a
    typed `provider_not_configured` and every read keeps working, which is the
    correct first-run state rather than a failure.
    """
    from datetime import datetime, timezone

    registry = MethodRegistry()
    register_coach_methods(
        registry,
        database,
        adapter=adapter,
        clock=lambda: render(datetime.now(timezone.utc)),
    )
    return registry


def use_utf8_console() -> None:
    """Make the console able to print Vietnamese.

    A Windows console defaults to a legacy codepage, and the disclosure text is
    Vietnamese — printing it raised `UnicodeEncodeError` and killed the launcher
    before the server ever started. `errors="replace"` so a console that still
    cannot render a glyph degrades instead of crashing.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def _configure_logging() -> None:
    """Send Coach's own log to the console.

    uvicorn installs handlers for its own loggers only, so without this an
    `internal_error` traceback is written to a logger nobody is listening to —
    the client is told nothing, by design, and the operator is told nothing
    either, by accident.
    """
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    logger = logging.getLogger("hermes_coach")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.propagate = False


def main(argv: list[str] | None = None, *, agent_factory=None) -> int:
    """Run the backend.

    `agent_factory` is injected by the CLI edge: the Coach package may not
    import `agent.*`, so the provider is assembled outside it. Running
    `python -m hermes_coach` directly therefore starts without a model.
    """
    use_utf8_console()
    _configure_logging()
    arguments = build_parser().parse_args(argv)
    profile = coach_profile(arguments.profile)

    try:
        with profile_lock(profile):
            return _serve(profile, arguments.port, agent_factory)
    except (ProfileLocked, PortUnavailable) as refused:
        # Both mean the same thing to the operator: something is already there.
        # Said in one line, before any URL is printed.
        print(f"error: {refused}")
        return 1


def _serve(profile, port: int, agent_factory=None) -> int:
    from datetime import datetime, timezone

    handshake, database = start(profile, port=port, now=render(datetime.now(timezone.utc)))
    try:
        print(f"Hermes Coach — profile {profile.name}")
        print(f"  {handshake.disclosure['note']}")
        ui = resolve_ui_directory()
        print(f"  http://{LOOPBACK}:{handshake.port}?token={handshake.token}")
        if ui is None:
            print("  UI chua build; mo link tren se 404.")
            print("  Chay: npm run -w apps/hermes-coach build")
        if handshake.retention_purged:
            print(f"  retention removed {handshake.retention_purged} expired rows")
        # Stated every start, not only when it breaks: a safety net nobody can
        # see is one nobody checks, and the first time it matters is the worst
        # time to find out it stopped running.
        if handshake.backup_failed:
            print("  CANH BAO: khong sao luu duoc coach.db. Hay kiem tra dung luong")
            print("  o dia va quyen ghi truoc khi dung tiep.")
        elif handshake.backup_path:
            print(f"  da sao luu: {handshake.backup_path}")

        use_selector_event_loop()
        uvicorn.run(
            create_app(
                handshake.guard,
                register_methods(database, _adapter_for(agent_factory)),
                database=database,
                ui_directory=ui,
            ),
            host=LOOPBACK,
            port=handshake.port,
            log_level="warning",
        )
    finally:
        database.close()
    return 0


def resolve_ui_directory() -> Path | None:
    """Where the built web UI lives, or None if it was never built.

    Two locations, because there are two ways to run this: from a wheel, where
    the build is packaged beside the code, and from a checkout, where it sits
    where `vite build` left it. A missing UI is not an error — the backend still
    serves RPC, and the launcher says what to run.
    """
    packaged = Path(__file__).resolve().parent / "web"
    checkout = Path(__file__).resolve().parents[1] / "apps" / "hermes-coach" / "dist"
    for candidate in (packaged, checkout):
        if (candidate / "index.html").is_file():
            return candidate
    return None


def _adapter_for(agent_factory):
    """Wrap the injected factory in the Coach runtime adapter."""
    if agent_factory is None:
        return None
    from hermes_coach.infrastructure.hermes_runtime_adapter import (
        AdapterConfiguration,
        CoachRuntimeAdapter,
    )

    return CoachRuntimeAdapter(
        AdapterConfiguration(
            prompt_version=DEFAULT_PROMPT_VERSION, provider="anthropic", model="haiku"
        ),
        agent_factory=agent_factory,
    )


if __name__ == "__main__":
    raise SystemExit(main())
