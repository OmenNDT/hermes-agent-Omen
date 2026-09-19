"""``hermes coach`` subcommand parser.

Thin edge registration only. The launcher lives in ``hermes_coach.__main__``
and is imported lazily so a Hermes session that never runs Coach pays nothing
for it and cannot be broken by it.
"""

from __future__ import annotations

import argparse


def _run_coach(args: argparse.Namespace) -> int:
    """Run the backend and exit with its code.

    `SystemExit` rather than a plain return, because the shared Hermes
    dispatcher calls `args.func(args)` and discards the result. Returning was
    enough to make `hermes coach` report success after refusing to start on a
    locked profile, which left the double-click launcher unable to tell that
    apart from a clean shutdown. Raising here fixes the coach edge without
    changing dispatch for every other Hermes subcommand.
    """
    from hermes_coach.__main__ import main as coach_main

    argv = ["--profile", args.profile, "--port", str(args.port)]
    if args.open:
        argv.append("--open")
    raise SystemExit(coach_main(argv, agent_factory=_agent_factory(args)))


def _agent_factory(args: argparse.Namespace):
    """Build the model provider, or None to run without one.

    A missing credential is reported and the backend still starts: every read
    keeps working and only `coach.turn` answers `provider_not_configured`.
    """
    if args.no_provider:
        return None
    from hermes_cli.coach_provider import NoCoachCredential, build_coach_agent_factory

    try:
        factory = build_coach_agent_factory(getattr(args, "provider", None))
    except NoCoachCredential as missing:
        print(f"warning: {missing}")
        print("  Coach starts without a model; stored data stays usable.")
        return None

    # The launcher announces which provider this is, once the console can
    # render Vietnamese. Printing it here would be too early.
    return factory


def build_coach_parser(subparsers) -> None:
    """Attach the ``coach`` subcommand to ``subparsers``."""
    coach_parser = subparsers.add_parser(
        "coach",
        help="Run the Hermes Coach local web app",
        description=(
            "Start the Hermes Coach backend on loopback. Single user, no login, "
            "no LAN access."
        ),
    )
    coach_parser.add_argument(
        "--profile", default="default", help="Coach profile name"
    )
    coach_parser.add_argument(
        "--port", type=int, default=0, help="0 picks a free loopback port"
    )
    coach_parser.add_argument(
        "--open",
        action="store_true",
        help="Open the browser on the token URL once the server accepts",
    )
    coach_parser.add_argument(
        "--provider",
        choices=["claude-code", "anthropic", "openai", "gemini"],
        help=(
            "Which model to use. Default: the Claude Code account if signed "
            "in, otherwise whichever API key is set."
        ),
    )
    coach_parser.add_argument(
        "--no-provider",
        action="store_true",
        help="Start without a model; reads and stored data still work",
    )
    coach_parser.set_defaults(func=_run_coach)
