#!/bin/sh
# block-no-verify-hook.sh — PreToolUse hook for Claude Code AND VS Code agent
# hooks. Blocks tool calls that run `git commit --no-verify`, which would skip
# the log-before-fix commit gate (git-commitmsg-hook.sh).
#
# Both harnesses pass the same thing on stdin: a JSON object like
#   {"tool_name": "Bash", "tool_input": {"command": "git commit --no-verify"}}
# Exit code 2 = block the tool call; the stderr text is shown to the model as
# the reason. Exit 0 = let it through.
#
# VS Code note: agent-hook MATCHERS ARE NOT APPLIED — every PreToolUse hook
# runs on EVERY tool event. This script must therefore self-filter on the
# tool_name itself (the guard below), not rely on the settings matcher.
#
# Only the long form `--no-verify` is blocked here (the short `-n` is left to
# the git wrapper — inside a raw JSON payload, `-n` is too easily a false
# positive, e.g. `grep -n`). The tool-name list below may need extending if
# your harness version uses a different name for its command tool.
#
# Install:
#   Claude Code  -> copy the hooks section of claude-code-settings.json into
#                   .claude/settings.json (project) or ~/.claude/settings.json
#   VS Code      -> copy vscode-agent-hooks.json to .github/hooks/block-no-verify.json
#                   (or ~/.copilot/hooks/), and this script next to it
# See hooks/README.md for details.

json="$(cat 2>/dev/null || true)"

# Extract the tool_name field — order-independent, so it works whatever order
# the harness emits the JSON fields in. Empty or unknown -> pass through.
tool="$(printf '%s' "$json" | sed -n 's/.*"tool_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)"

case "$tool" in
    Bash|bash|sh|Sh|runCommand|RunCommand|executeCommand|terminal|Terminal|runTerminalCommand|shell)
        ;;
    *)
        # Not a command-executing tool (e.g. Edit/Write) — let it through even
        # if the file content merely mentions --no-verify.
        exit 0
        ;;
esac

if printf '%s' "$json" | grep -q -- '--no-verify'; then
    echo "BLOCKED: 'git commit --no-verify' would skip the log-before-fix commit gate." >&2
    echo "If the hook blocked you, the error isn't logged yet — run:" >&2
    echo "  python check_errors.py --add" >&2
    echo "then commit again WITHOUT --no-verify:" >&2
    echo "  git commit -m \"fix <thing> (AREA: <what broke>)\"" >&2
    exit 2
fi

exit 0
