# Agent Error Log

> Give your AI coding agent a **memory for its own mistakes** — and make
> "log before fixing" mechanically enforced instead of merely encouraged.

[![CI](https://github.com/vartiainen1/agent-error-log/actions/workflows/ci.yml/badge.svg)](https://github.com/vartiainen1/agent-error-log/actions/workflows/ci.yml)
[![checks on master](https://img.shields.io/github/checks-status/vartiainen1/agent-error-log/master)](https://github.com/vartiainen1/agent-error-log/actions)
[![release](https://img.shields.io/github/v/release/vartiainen1/agent-error-log)](https://github.com/vartiainen1/agent-error-log/releases)
[![license](https://img.shields.io/github/license/vartiainen1/agent-error-log)](https://github.com/vartiainen1/agent-error-log/blob/master/LICENSE)
[![python](https://img.shields.io/badge/python-3.9%20%7C%203.11%20%7C%203.12-3776AB)](https://github.com/vartiainen1/agent-error-log/actions)
[![dependencies-0](https://img.shields.io/badge/dependencies-0-brightgreen)](https://github.com/vartiainen1/agent-error-log)
[![Visitors](https://visitor-badge.laobi.icu/badge?page_id=vartiainen1.agent-error-log&left_text=Visitors&right_color=2F80ED)](https://github.com/vartiainen1/agent-error-log)
[![companion](https://img.shields.io/badge/companion-agent--decision--log-2ea44f)](https://github.com/vartiainen1/agent-decision-log)

A tiny, dependency-free system for anyone who works with AI coding assistants
or builds their own agent loops. Three text files + two small tools + one git
hook + optional harness blockers = an agent that:

1. **Logs every error with its root cause** — *before* it fixes it
   (if you can't explain why it broke, you haven't understood it).
2. **Refuses to commit a fix unless the error was logged** — enforced by a
   git hook, not by good intentions.
3. **Boots every session calibrated** — health-checks the log, re-reads the
   open errors, and re-surfaces the distilled lessons from past failures.

No specific model, provider, or framework required. If your agent can read a
`.txt` file and run a terminal command, it can use this.

---

## Who is this for?

- **People using AI coding assistants** — Claude Code, Codex, Cursor, Gemini
  CLI, Copilot, or any chat-to-code tool that can execute commands.
- **People building custom agent loops** — local models (Ollama, llama.cpp),
  hosted APIs (OpenAI, Anthropic, any OpenAI-compatible endpoint), LangChain
  or hand-rolled `while` loops.
- **Anyone tired of the same bug being introduced twice.**

The workflow lives in plain text files and shell — it is **model-agnostic**.
The files that talk to your agent (`rules.txt`, `AGENTS.md`) use simple
imperative language any LLM follows.

## Why this exists

AI agents are stateless between sessions. They re-learn your project's
failure modes from scratch every single time — you fix a bug, and a week
later the agent reintroduces the exact same one because *nothing remembered
the cause*.

This system fixes that with three ideas:

| Idea | Implementation |
|---|---|
| **Structure** | Every error entry records `symptom → cause → fix → status` in a machine-validated template |
| **Causes before fixes** | The `CAUSE` field is written *before* the fix starts, and the linter refuses entries without it |
| **Enforcement** | A git hook *blocks* code commits that don't reference a logged error — the rule is mechanical, not motivational |

## What's inside

```
agent-error-log/
├── README.md               ← this file
├── AGENTS.md               ← instructions your AI agent should read
├── CHANGELOG.md            ← release history
├── CONTRIBUTING.md         ← how to contribute
├── SECURITY.md             ← vulnerability reporting policy
├── CODE_OF_CONDUCT.md      ← community guidelines
├── LICENSE                 ← MIT
├── pyproject.toml          ← optional pip packaging (no runtime deps)
├── .gitignore
├── start.py                session bootstrap (STEP 0 health check)
├── check_errors.py         error-log tooling: validate / gate / add / archive
├── _test_errors.py         140 unit tests for the tooling
├── git-commitmsg-hook.sh   the log-before-fix git gate
├── hooks/                  optional harness-level --no-verify blockers
├── rules.txt               RULES template (how the agent behaves)
├── errors.txt              ERROR LOG template (works out of the box)
├── notes.txt               NOTES template (session notes)
└── start.bat               Windows launcher for start.py
```

**stdlib-only Python 3** and plain shell — no pip installs, no build step.
Works on Windows / macOS / Linux.

## Quick start

1. **Copy the folder** to the root of your project (see *Git gate placement*
   below for other locations). Rename it if you like.
2. **Make it yours** — edit the `<YOUR PROJECT NAME>` / `<YOUR ASSISTANT NAME>`
   placeholders in `rules.txt` and `notes.txt`, fill in section 4 (your
   project map), and replace the example entries in `errors.txt` with your
   real ones (keep the section-5 template intact — it's the entry format).
   If you rename `errors.txt`, update `LOG` at the top of `check_errors.py`
   and the hook's `LOGNAME` env var.
3. **Run it:**
   ```sh
   python start.py        # boots the session: health check + open errors + notes
   python _test_errors.py # sanity-check the tooling (all 140 should pass)
   ```

### Adopting with a custom agent (no AGENTS.md support)

If your agent doesn't honor the `AGENTS.md` convention, just paste its
contents into your agent's system prompt / instructions. That's the whole
integration — the rest of the system is files and commands your agent
already knows how to use.

## See it in action

```sh
$ python start.py
================================================================================
AGENT SESSION BOOTSTRAP
when       : 2026-08-08 23:44
workspace  : /path/to/agent-error-log
================================================================================
--------------------------------------------------------------------------------
STEP 0 - ERROR-LOG HEALTH CHECK (check_errors.py):
3 entrie(s): 0 error(s), 0 warning(s).
  RESULT: log healthy - safe to code.

ACTIVE / UNRESOLVED ERRORS (non-FIXED, from the error log):
  [2026-08-07] AREA: image resize service timeouts
      STATUS: OPEN.
  [2026-08-08] AREA: search API rate limit
      STATUS: MITIGATED.
```

The git gate blocking a fix that was never logged:

```sh
$ git commit -m "fix sprite tracking (AREA: player sprite color WRONG)"
GATE FAILED — no entry for 'player sprite color WRONG'. LOG BEFORE FIXING:
add an entry first (python check_errors.py --add), then fix.
commit-msg BLOCKED: the error "player sprite color WRONG" is NOT logged.
```

And passing, once the error is logged:

```sh
$ git commit -m "fix sprite tracking (AREA: player sprite color WRONG)"
found: [2026-08-08] AREA: player sprite color WRONG  (line 30)
GATE PASSED — the error is logged. You may now apply the fix.
commit-msg OK: "player sprite color WRONG" is logged — fix may land.
```

## The workflow it enforces

```
session start  →  python start.py        (health check + context, STEP 0)
error happens  →  check_errors.py --add  (log FIRST — CAUSE before the fix)
about to fix   →  check_errors.py --has-entry "<AREA>"   (gate: exit 0 only
                                             if the error is logged)
fix lands      →  git commit -m "... (AREA: <what broke>)"
log grows      →  check_errors.py --archive-days 30 --apply
                             (old FIXED entries move to an ARCHIVED section)
drift appears  →  the linter flags it at the next session start, automatically
```

### Install the git gate (optional but recommended)

```sh
git init                 # if your project isn't a repo yet
cp git-commitmsg-hook.sh .git/hooks/commit-msg
chmod +x .git/hooks/commit-msg
```

Or do it all in one command — templates, hook, health check, self-test:

```sh
python check_errors.py --init
```

**Git gate placement** — the hook assumes `check_errors.py` sits at the **repo
root**. If you placed the folder elsewhere, tell the hook where:

```sh
# e.g. folder at tools/agent-error-log/
export AGENT_ERROR_LOG_DIR="$PWD/tools/agent-error-log"   # before committing
```

Docs-only commits and log-only commits pass automatically (the log itself
must still validate).

### Known limitation: `--no-verify`

Git's `--no-verify` flag skips **all** hooks — including this one. Any agent
or human that commits with `git commit --no-verify` bypasses the gate
entirely.

This is accepted **by design**: git hooks are advisory, not a security
boundary. What we can do is make the bypass deliberate instead of silent, at
the layers where the agent actually lives. The `hooks/` folder ships
ready-to-use blockers for the common cases.

**Practical layers, in order of value:**

1. **Instruct your agent** — the most effective layer. `AGENTS.md` (and
   `rules.txt` §2) say: *never use `git commit --no-verify`; if the hook
   blocks you, log the error first and commit again.* LLM agents follow
   explicit instructions reliably — this closes the loop for the common
   case.
2. **CI as a backstop (shipped)** — the `commit-gate` job re-runs the gate
   on every pushed commit: `python check_errors.py --check-commit` fails the
   build if the commit message names no logged error, and the `tests + linter`
   matrix catches a broken log. Both can be required before merge.
3. **Harness-level blocking (shipped in `hooks/`)** — block the flag where
   the agent runs:
   - `hooks/block-no-verify.sh` — a git alias wrapper for your own shell
     (rejects `git commit --no-verify` / `-n`).
   - `hooks/block-no-verify-hook.sh` + `claude-code-settings.json` — a
     Claude Code `PreToolUse` hook that blocks the command (exit 2, reason
     shown to the model).
   - `hooks/block-no-verify-hook.sh` + `vscode-agent-hooks.json` — a VS
     Code agent hook with the same guard (self-filters on `tool_name`, since
     VS Code does not apply matchers).
   Install steps for all three: `hooks/README.md`.
4. **Server-side hooks** — pre-receive hooks on self-hosted git
   (Gitea/GitLab) run on the server and cannot be skipped by the client.
   Overkill for a solo project, but the only truly unbypassable option.

### Making the gate required (branch protection)

The CI checks report failures but don't block pushes by default (a red check
on `master` is advisory for the owner). To make the gate a hard requirement:

1. GitHub → **Settings → Branches → Add branch protection rule**.
2. Branch name pattern: `master` (or `main`).
3. Tick **Require status checks to pass before merging**.
4. Tick the checks: `commit-message gate (log-before-fix)` and `CI`.
5. (Optional) tick **Do not allow bypassing the above settings** for admins.

With that, a `--no-verify` commit cannot land on `master` — the message is
re-checked on the server, where the flag does not exist.

### Shipping a change (PR workflow)

With branch protection live, **direct pushes to `master` are rejected** —
`GH006: Protected branch update failed … 7 of 7 required status checks are
expected` — because a fresh commit has no CI checks yet. Every change lands
via pull request:

1. **Branch off `master`** and commit with the `(AREA: <logged error>)`
   marker in the message (matching an entry in `errors.txt`):
   `git commit -m "fix: … (AREA: search API rate limit)"`.
2. **Push the branch, open a PR** against `master`. The six
   `tests + linter` matrix jobs run on the PR head.
3. **Squash-merge** once checks are green, keeping the `(AREA: …)` marker in
   the squash title. The merge push re-runs CI **and the commit-message
   gate** on `master` — a missing marker leaves the gate red.

The gate job skips PR events on purpose: PRs are gated when the merge
lands, so the squash title is exactly what gets re-checked on `master`.

## Tooling reference

| Command | What it does |
|---|---|
| `python check_errors.py` | validates every entry (template fields + canonical statuses `FIXED \| PARTIAL \| OPEN \| MITIGATED \| WORKAROUND`), flags duplicates and bad dates. Exit 0 = healthy |
| `--has-entry "<AREA>"` | mechanical gate: exit 0 only if the error is already logged |
| `--add` | interactive scaffolder — writes a template-perfect entry above section 5 |
| `--archive-days N` | preview FIXED entries older than N days |
| `--archive-days N --apply` | actually move them into the ARCHIVED section (idempotent) |
| `--log PATH` | point the tooling at any error log |
| `--lessons` | distill recurring cause keywords from the error log into lessons (preview) |
| `--lessons --apply` | write the distilled LESSONS section into `rules.txt` |
| `--check-commit FILE` | gate on a commit-message file: exit 0 only if it names a logged error (`AREA:`/`LOG:` marker) — the CI server-side backstop |
| `--init` | one-command adoption: scaffold `errors.txt`/`rules.txt`/`notes.txt`, install the commit-msg hook, health-check, run the tests (`--target DIR`, `--no-tests`) |

## Customization

- **Filenames** — rename `rules.txt` / `errors.txt` / `notes.txt` and update
  the constants at the top of `start.py`, `LOG` in `check_errors.py`, and
  the hook's `LOGNAME` env var (default `errors.txt`).
- **Statuses** — edit `STATUSES` in `check_errors.py` (and the docs in
  `errors.txt`) to match your vocabulary.
- **Lessons** — `rules.txt` §7 ships five generic root-cause lessons
  (data robustness, model quirks, environment, screen-vision, log
  discipline). Replace them with your own as your log grows — that section
  is the permanent memory. Regenerate it automatically from your error
  log: `python check_errors.py --lessons --apply`.
- **Lesson clusters** — lessons group by shared keywords, so two entries that
  merely share a word can chain into one cluster. Good enough to group
  related failures, not a perfect taxonomy — inspect before `--apply`.
- **Python interpreter** — the hook uses `python` by default; override with
  the `PYTHON` env var.
- **Hook placement** — the hook finds `check_errors.py` at the repo root by
  default; override with `AGENT_ERROR_LOG_DIR` (see *Git gate placement*).
- **Log path** — `LOGNAME` defaults to `errors.txt` at the repo root. If the
  log lives in a subfolder, set it to the repo-root-relative path (e.g.
  `LOGNAME=docs/errors.txt`) — the hook matches staged paths verbatim.

## FAQ

- **Do I need a specific LLM?** No. Any model that can read text and run
  commands works.
- **Do I need pip / npm?** No. Zero dependencies.
- **Does it work on Windows?** Yes — UTF-8 handling is built in, plus a
  `start.bat` launcher.
- **Can I log unicode (café, em-dash) on Windows?** Yes — both `stdout`
  and `stdin` are reconfigured to UTF-8, so piped unicode text is stored
  as-is, never double-encoded.
- **I already keep a NOTES.md — why this?** NOTES.md is unstructured and
  unenforced. This adds a machine-validated format, a hard commit gate, and
  automated session checks on top of the same idea.
- **Can I use my own file names?** Yes — see Customization.
- **I copied the tool to a scratch folder — will it touch my real repo?** No.
  Default paths resolve relative to the script location (`HERE`), so a scratch
  copy logs next to itself. Point at your real log from anywhere with
  `--log path/to/errors.txt`.

## Development

```sh
python _test_errors.py   # 140 tests: parsing, validation, gate, add, archive, lessons, init
```

The tests build throwaway logs in temp dirs — they never touch your real
`errors.txt`.

Parsing walks each entry forward to the next header, so worst case is O(n²)
on pathological files; for real logs (tens to hundreds of entries) it is
instant, and the validator is fine at thousands of lines.

**CI** — a GitHub Actions workflow (`.github/workflows/ci.yml`) runs the unit
tests, the linter, and a syntax check of every hook script (`git-commitmsg-hook.sh`
and `hooks/*.sh`) on every push and pull request, across Python 3.9 / 3.11 /
3.12 on Linux and Windows. This is the enforcement backstop described in
*Known limitation: `--no-verify`*: even a bypassed hook can't hide a broken
log or a failing test.

**Releases** — the version at the top of `CHANGELOG.md` is the single source
of truth. Bump it and push to `master`: the release workflow
(`.github/workflows/release.yml`) creates a `vX.Y.Z` tag and opens a **draft**
GitHub Release with that changelog section as the body — publish it on the
Releases page when ready.

## Security

- **Python 3.9+**, stdlib only. The shell hook runs under git-bash / sh
  (Windows, macOS, Linux).
- The error log may contain sensitive details (paths, payloads, stack
  traces). **Never log credentials or secrets** — keep the repo private if
  in doubt. `.gitignore` already excludes `__pycache__/` and `*.pyc`.
- The hook invokes Python from `PATH`; override with `PYTHON` if your
  interpreter is elsewhere.
- To report a vulnerability, use the private advisory path in
  [`SECURITY.md`](SECURITY.md) — never a public issue.

## Companion tools

The agent-memory family — same shape, same lifecycle verbs, four layers:

| Repo | What it remembers | How it works |
|---|---|---|
| **agent-error-log (this)** | what BROKE | text log + linter + git gate |
| [agent-decision-log](https://github.com/vartiainen1/agent-decision-log) | what was CHOSEN and why | append-only decisions + currency chain |
| [agent-log-ai](https://github.com/vartiainen1/agent-log-ai) | *why* it kept happening | heuristics select → LLM reasons |
| [agent-diff-gate](https://github.com/vartiainen1/agent-diff-gate) | what must never be COMMITTED | pre-commit diff scan + gate |

## Installing with pip (optional)

The single-file adoption story is unchanged - copy `check_errors.py` into your
project and you are done. The tool is *also* pip-installable with zero runtime
dependencies:

```sh
pip install agent-error-log
error-log --help
```

- The package version is derived from the git tag (setuptools-scm), which the
  release workflow creates from CHANGELOG.md - there is no version to drift.
- Run from the installed package, default paths (`errors.txt`, `rules.txt`)
  resolve against your current directory; an in-place copy keeps resolving
  against the file's folder.
- `--init` works identically from an installed copy (built-in templates).


## Dogfood ledger

This repo is reviewed by its own family gate — **agent-diff-gate**, a
pre-commit diff analyzer that flags risky patterns in added code. The
ledger below is the gate's output over this repo's entire history
(initial commit → `HEAD`), recorded so the tool's claims are backed by
its own findings.

The gate numbers its rules R1–R14 (`python check_diff.py --list-rules`
prints the full list). The classes that appear in this repo's history:

- **R2** — silent failure: an exception swallowed without a trace
- **R4** — duplicate logic: near-identical lines added in the same diff
- **R6** — hardcoded URL: a non-placeholder URL in added code


| | |
|---|---|
| Commits scanned | 42 (~2,800 diff lines) |
| Findings | **17** — 6 HIGH · 6 MEDIUM · 5 LOW |
| Classes | R2 ×6 (HIGH) · R4 ×6 (MEDIUM) · R6 ×5 (LOW) |
| Suppressed | **none** — every finding is fixed, tracked in `errors.txt`, or documented here |

- **R2 (HIGH)** — best-effort cleanup swallows in `check_errors.py` (stale
  lock-file unlink, best-effort `chmod`) and a test-teardown swallow in
  `_test_errors.py`. Deliberate by intent — cleanup failure is non-fatal —
  and documented here as the accepted class.
- **R4 (MEDIUM)** — the documented test-fixture duplication class.
- **R6 (LOW)** — URL literals in docs and fixtures. R6 flags all
  non-placeholder URLs in added lines, including test files, by design.

Reproduce from this repo:

```sh
git diff $(git rev-list --max-parents=0 HEAD) HEAD \
  | python <path-to>/agent-diff-gate/check_diff.py --stdin --json
```

[Changelog](CHANGELOG.md) · [Contributing](CONTRIBUTING.md)

## License

MIT — see [LICENSE](LICENSE).
