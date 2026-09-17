#!/usr/bin/env bash
# Canonical test runner for hermes-agent. Run this instead of calling
# `pytest` directly to guarantee your local run matches CI behavior.
#
# What this script enforces:
#   * Per-file isolation via scripts/run_tests_parallel.py — each test
#     file runs in its own freshly-spawned `python -m pytest <file>`
#     subprocess. No xdist, no shared workers, no module-level leakage
#     between files.
#   * TZ=UTC, LANG=C.UTF-8, PYTHONUTF8=1, PYTHONHASHSEED=0 (deterministic).
#     PYTHONUTF8 is load-bearing on Windows: Python ignores LANG/LC_ALL
#     there, so without it ~11 tests fail on cp1252 decoding alone. No-op
#     on Linux/CI, which is already UTF-8.
#   * Env vars blanked (conftest.py also does this, but this
#     is belt-and-suspenders for anyone running pytest outside our
#     conftest path — e.g. on a single file)
#   * Proper venv activation (probes .venv, venv, then ~/.hermes/...;
#     accepts both bin/python and Windows Scripts/python.exe layouts)
#
# Usage:
#   scripts/run_tests.sh                            # full suite
#   scripts/run_tests.sh -j 4                       # cap parallelism
#   scripts/run_tests.sh tests/agent/               # discover only here
#   scripts/run_tests.sh tests/agent/ tests/acp/    # multiple roots
#   scripts/run_tests.sh tests/foo.py               # single file
#   scripts/run_tests.sh tests/foo.py -q            # path + bare pytest flag
#   scripts/run_tests.sh tests/foo.py -v --tb=long  # bare flags "just work"
#   scripts/run_tests.sh -k 'pattern'               # value flags pass through too
#   scripts/run_tests.sh tests/foo.py -- --tb=long  # explicit '--' still works
#
# Bare pytest flags (anything starting with '-' that isn't one of this
# runner's own options: -j/--jobs, --paths, --slice, --file-timeout, etc.)
# are forwarded to each per-file pytest invocation automatically — no '--'
# separator required. The explicit '--' form still works and stacks with
# bare flags. Positional path arguments override the default discovery
# root (tests/).

set -euo pipefail

# ── Locate repo root ────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Activate venv ───────────────────────────────────────────────────────────
# Probes both layouts: POSIX venvs put the interpreter in bin/, Windows venvs
# (what `uv sync` creates under Git Bash) put it in Scripts/ with an .exe
# suffix. Checking only bin/activate made this script unusable on Windows.
VENV=""
PYTHON=""
for candidate in "$REPO_ROOT/.venv" "$REPO_ROOT/venv" "$HOME/.hermes/hermes-agent/venv"; do
  if [ -x "$candidate/bin/python" ]; then
    VENV="$candidate"
    PYTHON="$candidate/bin/python"
    break
  elif [ -x "$candidate/Scripts/python.exe" ]; then
    VENV="$candidate"
    PYTHON="$candidate/Scripts/python.exe"
    break
  fi
done

if [ -z "$PYTHON" ]; then
  echo "error: no virtualenv found in $REPO_ROOT/.venv or $REPO_ROOT/venv" >&2
  exit 1
fi


# ── Live-gateway plugin (computed before we drop env) ───────────────────────
EXTRA_PYTHONPATH=""
EXTRA_PYTEST_PLUGINS=""
if [ -f "$HOME/.hermes/pytest_live_guard.py" ]; then
  EXTRA_PYTHONPATH="$HOME/.hermes"
  EXTRA_PYTEST_PLUGINS="pytest_live_guard"
fi


# ── Platform plumbing that env -i must not strip ────────────────────────────
# On POSIX, HOME alone is enough for the interpreter to function. On Windows it
# is not: without USERPROFILE, `Path.expanduser()` raises outright; without
# LOCALAPPDATA, `get_hermes_home()` cannot resolve its default; without TEMP,
# `tempfile` has nowhere to write. Stripping them turned ~110 otherwise-passing
# tests red. None of these is a credential — they are the same class of plumbing
# as PATH, which the block below already keeps.
PLATFORM_ENV=()
case "$(uname -s 2>/dev/null || echo unknown)" in
  MINGW*|MSYS*|CYGWIN*|Windows_NT)
    # ProgramData is here because without it Windows shell APIs fall back to the
    # unexpanded literal `%SystemDrive%` and create a junk directory of that name
    # under the working tree. SystemDrive is what makes that expansion possible.
    for _var in USERPROFILE LOCALAPPDATA APPDATA ProgramData SystemDrive TEMP TMP SystemRoot ComSpec PATHEXT; do
      _value="$(printenv "$_var" 2>/dev/null || true)"
      if [ -n "$_value" ]; then
        PLATFORM_ENV+=("$_var=$_value")
      fi
    done
    ;;
esac


# ── Run in hermetic env ──────────────────────────────────────────────────────
# env -i: start with empty environment, opt-in only what we need.
# No credential var can leak — you'd have to explicitly add it here.
echo "▶ running per-file parallel test suite via run_tests_parallel.py"
echo "  (TZ=UTC LANG=C.UTF-8 PYTHONUTF8=1 PYTHONHASHSEED=0; clean env)"

cd "$REPO_ROOT"

exec env -i \
  PATH="$PATH" \
  HOME="$HOME" \
  TZ=UTC \
  LANG=C.UTF-8 \
  LC_ALL=C.UTF-8 \
  PYTHONUTF8=1 \
  PYTHONHASHSEED=0 \
  PYTHONDONTWRITEBYTECODE=1 \
  ${HERMES_RUN_SLOW_PET_TESTS:+HERMES_RUN_SLOW_PET_TESTS="$HERMES_RUN_SLOW_PET_TESTS"} \
  ${EXTRA_PYTHONPATH:+PYTHONPATH="$EXTRA_PYTHONPATH"} \
  ${EXTRA_PYTEST_PLUGINS:+PYTEST_PLUGINS="$EXTRA_PYTEST_PLUGINS"} \
  ${PLATFORM_ENV[@]+"${PLATFORM_ENV[@]}"} \
  "$PYTHON" "$SCRIPT_DIR/run_tests_parallel.py" "$@"
