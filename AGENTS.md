# Agent instructions

This repo uses the **Agent Error Log** system — your working instructions
live in three companion files. This file is read by AI coding agents that
honor the `AGENTS.md` convention (Claude Code, Codex, and others); if yours
doesn't, paste this into your system prompt instead.

Follow this exactly:

## Every session

1. Start by running `python start.py` (Windows: `start.bat`). It health-checks
   the error log and prints the reading order, the open errors, and the
   latest session note.
2. Read, in order:
   1. `rules.txt`  — the RULES: how to behave, conventions, non-negotiables
   2. `errors.txt` — check BEFORE debugging and BEFORE writing code
   3. `notes.txt`  — general context + session notes

## Mandatory rules (no exceptions)

- **CHECK BEFORE CODING** — review `errors.txt` before writing or modifying
  any code, so past mistakes are not repeated.
- **LOG BEFORE FIXING** — found an error? Do NOT fix it immediately. Log it
  first:
  ```sh
  python check_errors.py --add
  ```
  Only after the entry exists (STATUS written BEFORE the fix) may you apply
  the fix. Verify with:
  ```sh
  python check_errors.py --has-entry "<what broke>"
  ```

## Committing

The git commit-msg hook blocks code commits whose message lacks an
`AREA: <text>` marker matching a logged entry. Convention:

```sh
git commit -m "fix <thing> (AREA: <what broke>)"
```

- Docs/notes-only commits pass automatically.
- Never use `git commit --no-verify` — it skips every hook, including this
  gate. If the hook blocks you, the error isn't logged; log it first, then
  commit again.
- If your harness supports agent hooks (Claude Code, VS Code), install the
  blockers in `hooks/` (see `hooks/README.md`) so `--no-verify` is rejected
  at the tool-call layer too, not just by instruction.
- If the hook blocks you, it means the error isn't logged — that's the
  system working, not a bug.

## Housekeeping

- Keep entries short and factual. Write the CAUSE before fixing.
- End sessions with a dated note in `notes.txt`:
  `SESSION NOTE (YYYY-MM-DD): TITLE`.
- Archive old FIXED entries occasionally:
  `python check_errors.py --archive-days 30 --apply`.
## Companion tool

`agent-decision-log` (decisions.txt) records what was CHOSEN and why -
proactive memory. This log records what BROKE - reactive memory. Use both.
