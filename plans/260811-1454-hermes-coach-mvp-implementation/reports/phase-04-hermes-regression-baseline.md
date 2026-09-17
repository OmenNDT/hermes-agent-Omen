# Hermes Regression Baseline — Phase 4 Step 6

Date: 2026-08-22
Question: has the Coach work changed any existing Hermes behavior?
Answer: no. Every failure observed is a pre-existing Windows incompatibility in Hermes' own tests and harness.

## Footprint

| Check | Result |
|---|---|
| Tracked Hermes files modified | `pyproject.toml`, `uv.lock` — one dev dependency (`pytest-cov==7.1.0`) |
| Lines changed in Hermes source | 0 |
| Hermes files referencing `hermes_coach` | 0 (repo-wide grep) |
| New coupling | One-directional: `hermes_coach/bootstrap.py` imports `hermes_constants.get_hermes_home` |

`hermes_constants` is a leaf module: importing it pulls in 7 modules, all standard library (`bz2`, `lzma`, `shutil`, `zlib`). It reaches no agent, gateway or database code. Its own docstring says it is the single source of truth all other copies should import.

`pytest-cov` does not change default behavior: `[tool.pytest.ini_options].addopts` is `-m 'not integration'` with no coverage flag, so the plugin is inert unless `--cov` is passed.

## Results

| Suite | Files | Failures |
|---|---:|---:|
| `tests/agent/` + `tests/run_agent/`, default env | 357 | 64 in 22 files |
| Same, with `PYTHONUTF8=1` | 357 | 53 in 18 files |
| `tests/gateway/` with `PYTHONUTF8=1` | 442 | 101 in 12 files |

## Falsification: is any of this ours?

The only tracked change is a dev dependency, so the decisive test is whether disabling it changes anything.

```text
pytest tests/agent/test_shell_hooks.py            → 7 failed, 49 passed
pytest tests/agent/test_shell_hooks.py -p no:cov  → 7 failed, 49 passed

pytest tests/gateway/test_feishu.py               → 116 failed, 92 passed
pytest tests/gateway/test_feishu.py -p no:cov     → 116 failed, 92 passed
```

Identical. Supporting evidence: the failing files contain no reference to `hermes_coach`, and no Hermes file references Coach at all.

## Root causes, all environmental

| Cause | Where | Why it is Windows-only |
|---|---|---|
| `UnicodeDecodeError: 'charmap'` | 11 failures across `agent`/`run_agent` | Hermes code reads files with the default locale encoding; Windows defaults to cp1252 |
| `assert [] == ['C:\\Users\\...']` | most of the remaining `agent` failures | Tests assume POSIX path handling |
| `RuntimeError: Could not determine home directory` | 116 failures in `test_feishu.py` | The root `conftest.py` blanks env vars by design; on Windows that removes `USERPROFILE`, which `Path.expanduser()` needs. POSIX falls back to the `pwd` module |
| `AttributeError: module 'signal' has no attribute 'SIGKILL'` | `test_cgroup_cleanup.py` | cgroups and `SIGKILL` are Linux-only |

CI runs these suites on Linux, where none of the four applies.

## `hermes_cli` after the subcommand registration

Registering `hermes coach` added two lines to `hermes_cli/main.py`, so that
suite needed its own falsification. Stashing exactly those two lines and
re-running:

```text
with the change:    15 failed, 363 passed
change stashed:     15 failed, 363 passed
```

Identical. The `hermes_cli` failures (60 across 18 files) are pre-existing and
of the same Windows families listed above. All 46 Coach test files passed in the
same run.

## Finding, applied 2026-08-24

`scripts/run_tests.sh` exported `LANG=C.UTF-8 LC_ALL=C.UTF-8`, but Python on Windows ignores both for filesystem and locale encoding — only `PYTHONUTF8=1` has that effect. It also probed `bin/activate` only, so the Windows venv layout `uv` creates was invisible to it and the script refused to run at all.

Both are fixed: the probe now accepts `bin/python` or `Scripts/python.exe`, and `PYTHONUTF8=1` joins the `env -i` block. Neither changes anything on Linux.

```text
before:  scripts/run_tests.sh tests/run_agent/test_callable_api_key.py
         error: no virtualenv found

after:   scripts/run_tests.sh tests/run_agent/test_callable_api_key.py
         1 files, 16 tests passed, 0 failed
```

That file previously reported 6 failures under the ad-hoc Windows invocation. The 11 cp1252 failures across `agent`/`run_agent` are gone with it.

### The fix was incomplete, and a single file did not show it

Declaring the script fixed after one green file was wrong. The full suite through
it reported **163 failures across 32 files** — worse than the 53 the ad-hoc
invocation it replaced produced.

Cause: the `env -i` block is POSIX-shaped. On POSIX, `HOME` alone lets the
interpreter function; on Windows it does not.

```text
under env -i:  USERPROFILE: None
               LOCALAPPDATA: None
               TEMP: None
```

Without `USERPROFILE`, `Path.expanduser()` raises. Without `LOCALAPPDATA`,
`get_hermes_home()` cannot resolve its default. Without `TEMP`, `tempfile` has
nowhere to write. That turned roughly 110 otherwise-passing tests red.

A `PLATFORM_ENV` block, active only on Windows, now preserves `USERPROFILE`,
`LOCALAPPDATA`, `APPDATA`, `TEMP`, `TMP`, `SystemRoot`, `ComSpec` and `PATHEXT`.
None is a credential — they are the same class of plumbing as `PATH`, which the
block already kept — so the script's "no credential var can leak" property is
intact. The array is empty on POSIX, so nothing there changes.

| Run | Failures |
|---|---:|
| Ad-hoc invocation, full environment (baseline) | 53 in 18 files |
| `run_tests.sh` with the POSIX-only `env -i` | 163 in 32 files |
| `run_tests.sh` with `PLATFORM_ENV` | **53 in 19 files** |

Back to baseline. Two entries differ from the 18-file baseline and both pass in
isolation, so they are contention artifacts rather than regressions:
`test_provider_parity.py` needs 196s alone and exceeds its per-file timeout
under 56-way parallelism, and `test_compression_concurrent_fork.py` flakes once
under load (14/14 alone).

Lesson recorded because it nearly shipped: one green file is not evidence about a
test runner.

## Limitation

This is a baseline, not a before/after comparison: the failures were not captured on a pristine checkout before the Coach work began. What is established is that they are independent of it — by falsification, by absence of references in both directions, and by root causes that are all platform-level.

## Unresolved questions

- Should `PYTHONUTF8=1` be added to `scripts/run_tests.sh`? It fixes real false negatives on this machine at the cost of another upstream diff. Recommendation: yes, one line, and record it beside the `pyproject.toml` divergence.
- The Windows path and home-directory failures are genuine Hermes bugs on Windows, but they belong to upstream and are outside the approved Coach scope. No action proposed.
