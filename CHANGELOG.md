# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]



## [0.8.0] - 2026-08-10

### Fixed
- Typed entries: `parse_entries()` now returns `ErrorEntry` dataclasses (dict-compatible via `__getitem__`), full type hints on all functions, and a small exception vocabulary (`AgentLogError` / `ValidationError` / `LockTimeoutError`) — same behavior, same exit codes.
- stdin reconfigured to UTF-8 on Windows: piped unicode no longer double-encodes into the log (stdout-only reconfigure bug).
- L10: `load()` no longer crashes on a locked/unreadable log file (graceful `OSError` fallback; regression tests added).
- Concurrent `--add` appends no longer lose entries: the append is
  now serialized by a cross-process lock file (`<log>.lock`, stdlib-only,
  atomic `O_CREAT|O_EXCL` create with 5s wait and stale-lock recovery)
  and the log is re-read inside the lock before writing (lost-update fix).

- `_extract_area()` marker semantics documented and pinned by tests:
  the CI gate and the shell hooks agree on the marker (first matching
  line, last `AREA:`/`LOG:` on it — the hooks' `grep -m1` + greedy `sed`).
- `status_token()` strips the en-dash as well as the em-dash (`OPEN–` ->
  `OPEN`).
- `start.py` `active_errors()` delegates to `check_errors.parse_entries()`
  (the canonical parser) instead of re-implementing entry splitting, so
  the boot briefing can never drift from the tool's format.
- `load()` reads with `utf-8-sig` so a BOM-prefixed log is parsed, not
  silently ignored.

### Added

- Robustness tests: 100-entry fuzz, BOM / invalid UTF-8, en-dash
  statuses, an empty section-5-only log, and multi-marker precedence in
  `--check-commit` (last marker on the first matching line).

### Docs

- Add a permanent visitor badge to the README (GitHub traffic stats
  only keep 14 days).
- README: document the lessons-clustering chain limitation, the parser's
  worst-case O(n²) on pathological logs, and `LOGNAME` repo-root-relative
  paths.

## [0.7.0] - 2026-08-09

### Docs

- Add CODE_OF_CONDUCT.md (Contributor Covenant 2.1) to complete the
  community-standards checklist.

## [0.6.0] - 2026-08-09

### Docs

- README: fix stale test count in the file listing (90 -> 117).
- Add issue templates (bug report, feature request), a pull-request
  template that enforces the `(AREA: ...)` log-before-fix marker, and a
  SECURITY.md policy.

## [0.5.0] - 2026-08-09

### Added

- **One-command adoption** — `check_errors.py --init [--target DIR]`
  scaffolds `errors.txt` / `rules.txt` / `notes.txt` (never overwriting
  existing files), installs the `commit-msg` gate (backup-safe),
  health-checks the log, and runs the unit-test suite. Built-in
  minimal scaffolds kick in when only `check_errors.py` was copied.

## [0.4.0] - 2026-08-09

### Docs

- README: document the PR-based shipping workflow (branch → PR →
  squash merge with the `(AREA: …)` marker in the title) — direct
  pushes to `master` are blocked by branch protection.

## [0.3.0] - 2026-08-09

### Added

- **Server-side commit-message gate** — `check_errors.py --check-commit`
  re-runs the log-before-fix rule on a commit-message file, and the new
  `commit-gate` CI job applies it to every pushed commit — so a
  `--no-verify` bypass is caught at the server, where the flag cannot reach.
- **`hooks/install.sh`** — one-command setup for every `--no-verify` blocker
  (commit-msg gate, git wrapper alias, Claude Code + VS Code hooks).
  Idempotent; backs up files before changing them; self-tests the Python
  interpreter (Windows Store stubs are detected and skipped).

## [0.2.0] - 2026-08-09

### Added

- **`hooks/` — harness-level `--no-verify` blockers** — close the documented
  bypass of the commit gate at the layer where agents run:
  - `block-no-verify.sh` — git alias wrapper rejecting `git commit
    --no-verify` / `-n`.
  - `block-no-verify-hook.sh` + `claude-code-settings.json` — Claude Code
    `PreToolUse` hook blocking the command (exit 2, reason shown to the
    model).
  - `block-no-verify-hook.sh` + `vscode-agent-hooks.json` — VS Code agent
    hook with the same guard, self-filtering on `tool_name` (VS Code does
    not apply matchers).
- **CI** — the hook syntax check now covers every hook script
  (`git-commitmsg-hook.sh` and `hooks/*.sh`).
- **LICENSE** — copyright holder set.
- **`check_errors.py --lessons`** — distills recurring CAUSE keywords
  from the error log into a LESSONS LEARNED section (preview by default;
  `--apply` writes it into `rules.txt`). The agent's memory now
  compounds on its own.

## [0.1.0] - 2026-08-08

Initial release — a model-agnostic error-log and log-before-fix system for
AI coding agents.

### Added

- **Three-file system** — `rules.txt`, `errors.txt`, `notes.txt` templates
  with placeholders for any project, plus example data that works out of the
  box (`python start.py` boots a fully working demo).
- **`check_errors.py` tooling** (stdlib only) — linter (template fields +
  canonical statuses `FIXED | PARTIAL | OPEN | MITIGATED | WORKAROUND`),
  `--add` scaffolder, `--has-entry` mechanical gate, `--archive-days`
  archiver (idempotent, dry-run by default), `--log` for any file.
- **`start.py` session bootstrap** — STEP 0 error-log health check, reading
  order, open errors, latest session note; configurable filenames.
- **`git-commitmsg-hook.sh`** — the log-before-fix git gate: blocks code
  commits whose message lacks an `AREA: <text>` marker matching a logged
  entry, lints the log when it is staged, and exposes env-var overrides
  (`LOGNAME`, `PYTHON`, `AGENT_ERROR_LOG_DIR`).
- **`_test_errors.py`** — 64 unit tests (parsing, validation, gate, add,
  archive, idempotency).
- **CI** — GitHub Actions workflow running the tests, linter, and hook
  syntax check on Linux and Windows across Python 3.9–3.12.
- **Docs** — README, AGENTS.md, CONTRIBUTING.md, MIT license.

### Known limitations

- `git commit --no-verify` bypasses the local hook; documented with
  practical workarounds in the README.
