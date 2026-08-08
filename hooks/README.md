# Harness-level enforcement — closing the `--no-verify` hole

Git hooks are **advisory**: `git commit --no-verify` (or `-n`) skips every
hook, including the log-before-fix gate. The files in this folder make that
bypass deliberate instead of silent, at the layer where your agent actually
lives.

Three layers, from least to most invasive:

| Layer | File | Blocks |
|---|---|---|
| **git alias wrapper** | `block-no-verify.sh` | `git commit --no-verify` / `-n` in your own shell |
| **Claude Code hook** | `block-no-verify-hook.sh` + `claude-code-settings.json` | Claude Code running `git commit --no-verify` |
| **VS Code agent hook** | `block-no-verify-hook.sh` + `vscode-agent-hooks.json` | Copilot agent mode running `git commit --no-verify` |

All three are **best-effort**: a determined bypass (raw `git` binary, another
shell, `--no-verify` on a different machine) still escapes them. The only
truly unbypassable option is a **server-side pre-receive hook** on self-hosted
git (Gitea/GitLab) — overkill for a solo project.

The script that matters is `block-no-verify-hook.sh` — it reads the tool-call
JSON from stdin (both Claude Code and VS Code pass it there), checks the
`tool_name` and command for `--no-verify`, and exits `2` to block, printing
the reason on stderr. Exit code `2` is the "block with reason" code for both
harnesses.

Two deliberate trade-offs of the harness hook:

- It blocks only the long form `--no-verify`, not the short `-n`. Inside a raw
  JSON payload, `-n` is too easily a false positive (`grep -n`, `sed -n`).
  The git wrapper (`block-no-verify.sh`) blocks both forms.
- The `tool_name` guard list (Bash, runCommand, executeCommand, terminal,
  shell, …) covers the names both harnesses use today; if your harness
  version uses a different name for its command tool, add it to the list in
  `block-no-verify-hook.sh`.

---

## Layer 1 — git alias wrapper (everyone)

Put `block-no-verify.sh` on your PATH, then in `~/.bashrc` / `~/.zshrc`:

```sh
alias git='block-no-verify'
```

or, if aliases are awkward:

```sh
git() { block-no-verify "$@"; }
```

> Note: the alias must NOT repeat `git` — the wrapper appends it itself when
> passing commands through (`alias git='block-no-verify git'` would run
> `git git status`).

Test it:

```sh
sh hooks/block-no-verify.sh commit --no-verify -m "x"   # -> blocked, exit 1
sh hooks/block-no-verify.sh commit -n -m "x"            # -> blocked, exit 1
sh hooks/block-no-verify.sh status                       # -> passes through
sh hooks/block-no-verify.sh -C /some/dir commit --no-verify  # -> blocked too
```

## Layer 2 — Claude Code

Merge the `hooks` section of `claude-code-settings.json` into
`.claude/settings.json` (project) or `~/.claude/settings.json` (global), and
keep `hooks/block-no-verify-hook.sh` somewhere under your project (the
example command uses `$CLAUDE_PROJECT_DIR/hooks/`).

The `matcher` is `Bash`, so only shell-command tool calls hit the hook.

## Layer 3 — VS Code agent hooks

1. Create `.github/hooks/` in your repo (VS Code's convention for workspace
   agent hooks; `~/.copilot/hooks/` works user-wide).
2. Copy `vscode-agent-hooks.json` there as `block-no-verify.json`.
3. Copy `hooks/block-no-verify-hook.sh` to `.github/hooks/` next to it.

Note: VS Code parses but **does not apply** matchers — the hook runs on every
PreToolUse event, and `block-no-verify-hook.sh` self-filters on `tool_name`,
so non-command tools pass through untouched.

---

## Why not just make the git hook "stronger"?

You can't — that's the point of the README's *Known limitation*. Enforcement
has to happen where the agent lives (the harness) or where the repo lives
(the server). These files cover the harness; server-side pre-receive hooks
cover the server; everything else is the CI backstop in
`.github/workflows/ci.yml`.
