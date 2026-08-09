# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
