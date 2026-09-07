from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).parents[3]
COACH_PACKAGE = ROOT / "hermes_coach"


def _python_files() -> list[Path]:
    return sorted(COACH_PACKAGE.rglob("*.py"))


def test_phase_one_does_not_register_a_new_hermes_core_tool() -> None:
    for relative_path in ("model_tools.py", "toolsets.py", "tools/registry.py"):
        content = (ROOT / relative_path).read_text(encoding="utf-8").lower()
        assert "hermes_coach" not in content
        assert "hermes coach" not in content


def test_contract_layer_does_not_import_hermes_core_or_infrastructure() -> None:
    forbidden_roots = {
        "agent",
        "gateway",
        "hermes_state",
        "model_tools",
        "run_agent",
        "tools",
        "tui_gateway",
    }
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module.split(".")[0])
        assert not (set(imports) & forbidden_roots), path


DEFERRED_CAPABILITY_NAMES = {
    "advice",
    "audio",
    "microphone",
    "research",
    "stt",
    "tts",
    "voice",
}

COACH_APP = ROOT / "apps" / "hermes-coach"

# Directories the app does not own and that carry thousands of third-party
# paths; scanning them would assert on npm's contents, not on ours.
_APP_SKIP = {"node_modules", "dist", ".vite"}


def test_deferred_or_rejected_capabilities_have_no_implementation_path() -> None:
    paths = [path.relative_to(COACH_PACKAGE) for path in COACH_PACKAGE.rglob("*")]
    for path in paths:
        lowered_path = "/".join(path.parts).lower()
        assert not any(
            name in lowered_path for name in DEFERRED_CAPABILITY_NAMES
        ), path


def test_the_web_app_ships_no_voice_surface_either() -> None:
    """The no-voice boundary covers the product, not just the Python half.

    Phase 5 adds a browser surface, which is exactly where a microphone
    permission would appear if one ever did.
    """
    if not COACH_APP.exists():
        return
    for path in COACH_APP.rglob("*"):
        relative = path.relative_to(COACH_APP)
        if _APP_SKIP & set(relative.parts):
            continue
        lowered_path = "/".join(relative.parts).lower()
        assert not any(
            name in lowered_path for name in DEFERRED_CAPABILITY_NAMES
        ), relative
        if path.suffix in {".ts", ".tsx", ".html"}:
            content = path.read_text(encoding="utf-8").lower()
            for api in ("getusermedia", "mediarecorder", "speechrecognition"):
                assert api not in content, f"{relative} references {api}"


def test_phase_one_has_no_direct_scheduler_state_dependency() -> None:
    for path in _python_files():
        content = path.read_text(encoding="utf-8").lower()
        assert "jobs.json" not in content
        assert "~/.hermes" not in content
        assert "state.db" not in content


def test_has_no_login_lan_or_dashboard_pty_surface() -> None:
    """No account model, no LAN binding, no terminal surface.

    Narrowed in Phase 4: `api`, `server` and `web` left the forbidden list. The
    approved MVP *is* a loopback API serving a web UI, so those terms said
    nothing about the invariants this guard exists for. What it actually
    protects — there is no login/account model, nothing binds beyond loopback,
    and no PTY is reachable — is unchanged and still enforced below.
    """
    forbidden_path_terms = {"auth", "login", "pty"}
    for path in COACH_PACKAGE.rglob("*"):
        relative = path.relative_to(COACH_PACKAGE)
        lowered_path = "/".join(relative.parts).lower()
        assert not any(term in lowered_path for term in forbidden_path_terms), relative
        if path.suffix == ".py":
            content = path.read_text(encoding="utf-8").lower()
            assert "0.0.0.0" not in content
            assert "dashboard pty" not in content
