#!/bin/sh
# hooks/install.sh — one-command setup for the agent-error-log --no-verify
# blockers. Git hooks are advisory (--no-verify skips them), so these layers
# make the bypass deliberate instead of silent, where the agent actually lives.
#
# Installs any combination of:
#   --git     the log-before-fix commit-msg hook        (.git/hooks/commit-msg)
#   --alias   git wrapper that rejects --no-verify      (~/.local/bin + shell rc)
#   --claude  Claude Code PreToolUse hook               (.claude/settings.json)
#   --vscode  VS Code agent hooks                       (.github/hooks/)
#
# Usage:
#   ./hooks/install.sh            # install everything (same as --all)
#   ./hooks/install.sh --git      # just the commit-msg gate
#   ./hooks/install.sh --claude --vscode
#   ./hooks/install.sh --status   # report what is installed
#   ./hooks/install.sh --help
#
# Idempotent: safe to re-run; nothing is duplicated; existing settings files
# are backed up before they are changed.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOKS="$ROOT/hooks"
ALIAS_BIN="${XDG_BIN_HOME:-$HOME/.local/bin}"
ALIAS_LINE="alias git='block-no-verify'"

say()  { printf '%s\n' "$*"; }
ok()   { say "OK   $*"; }
skip() { say "SKIP $*"; }

find_rc() {
    if [ -f "$HOME/.zshrc" ]; then printf '%s\n' "$HOME/.zshrc"; return 0; fi
    if [ -f "$HOME/.bashrc" ]; then printf '%s\n' "$HOME/.bashrc"; return 0; fi
    printf '%s\n' "$HOME/.bashrc"
}

have_python() {
    # Some Windows machines put a Store alias (python3) on PATH that exists
    # but fails at runtime — so probe each candidate by actually running it.
    for cand in python3 python py; do
        if command -v "$cand" >/dev/null 2>&1 && "$cand" -c "import json" >/dev/null 2>&1; then
            printf '%s\n' "$cand"
            return 0
        fi
    done
    return 1
}

install_git() {
    [ -d "$ROOT/.git" ] || { skip "--git: $ROOT is not a git repository (run: git init)"; return 0; }
    [ -f "$ROOT/git-commitmsg-hook.sh" ] || { say "ERR  --git: git-commitmsg-hook.sh not found"; return 1; }
    mkdir -p "$ROOT/.git/hooks"
    cp "$ROOT/git-commitmsg-hook.sh" "$ROOT/.git/hooks/commit-msg"
    chmod +x "$ROOT/.git/hooks/commit-msg"
    ok "--git: commit-msg gate installed at .git/hooks/commit-msg"
}

install_alias() {
    [ -f "$HOOKS/block-no-verify.sh" ] || { say "ERR  --alias: block-no-verify.sh not found"; return 1; }
    mkdir -p "$ALIAS_BIN"
    cp "$HOOKS/block-no-verify.sh" "$ALIAS_BIN/block-no-verify"
    chmod +x "$ALIAS_BIN/block-no-verify"
    rc="$(find_rc)"
    if [ -f "$rc" ] && grep -Fqx "$ALIAS_LINE" "$rc"; then
        ok "--alias: wrapper at $ALIAS_BIN/block-no-verify, already active in $rc"
    else
        printf '\n# agent-error-log: reject git commit --no-verify\n%s\n' "$ALIAS_LINE" >> "$rc"
        ok "--alias: wrapper at $ALIAS_BIN/block-no-verify, added to $rc (re-source it or open a new shell)"
    fi
    if printf '%s' "$PATH" | tr ':' '\n' | grep -Fqx "$ALIAS_BIN"; then
        say "      $ALIAS_BIN is already on your PATH"
    else
        say "      NOTE: add '$ALIAS_BIN' to your PATH (e.g. in the same rc file)"
    fi
}

install_claude() {
    PY="$(have_python)" || { skip "--claude: python3/python not found — merge manually (see hooks/README.md)"; return 1; }
    [ -f "$HOOKS/claude-code-settings.json" ] || { say "ERR  --claude: claude-code-settings.json not found"; return 1; }
    # The merged JSON points at $CLAUDE_PROJECT_DIR/hooks/block-no-verify-hook.sh
    # — make sure that file actually exists in the target project.
    mkdir -p "$ROOT/hooks"
    cp "$HOOKS/block-no-verify-hook.sh" "$ROOT/hooks/block-no-verify-hook.sh"
    chmod +x "$ROOT/hooks/block-no-verify-hook.sh"
    settings="$ROOT/.claude/settings.json"
    settings_bak=0
    mkdir -p "$ROOT/.claude"
    if [ -f "$settings" ]; then cp "$settings" "$settings.bak"; settings_bak=1; fi
    out=$("$PY" - "$settings" "$HOOKS/claude-code-settings.json" <<'PY'
import json, os, sys
target, source = sys.argv[1], sys.argv[2]
data = {}
if os.path.exists(target):
    with open(target, encoding="utf-8") as fh:
        data = json.load(fh) or {}
entry = json.load(open(source, encoding="utf-8"))
pre = data.setdefault("hooks", {}).setdefault("PreToolUse", [])
if not isinstance(pre, list):
    pre = data["hooks"]["PreToolUse"] = []
def has_blocker(arr):
    return any("block-no-verify-hook.sh" in json.dumps(x) for x in arr)
added = 0
for group in entry["hooks"]["PreToolUse"]:
    if not has_blocker(pre):
        pre.append(group)
        added += 1
with open(target, "w", encoding="utf-8", newline="\n") as fh:
    json.dump(data, fh, indent=2)
    fh.write("\n")
print(added)
PY
)
    rc=$?
    [ $rc -ne 0 ] && { say "ERR  --claude: merge failed"; return 1; }
    if [ "${out:-0}" -gt 0 ] 2>/dev/null; then
        if [ "$settings_bak" -eq 1 ]; then
            ok "--claude: PreToolUse hook added to $settings (backup: $settings.bak)"
        else
            ok "--claude: PreToolUse hook added to $settings"
        fi
    else
        ok "--claude: already present in $settings"
    fi
}

install_vscode() {
    [ -f "$HOOKS/vscode-agent-hooks.json" ] || { say "ERR  --vscode: vscode-agent-hooks.json not found"; return 1; }
    mkdir -p "$ROOT/.github/hooks"
    cp "$HOOKS/block-no-verify-hook.sh" "$ROOT/.github/hooks/block-no-verify-hook.sh"
    cp "$HOOKS/vscode-agent-hooks.json" "$ROOT/.github/hooks/block-no-verify.json"
    chmod +x "$ROOT/.github/hooks/block-no-verify-hook.sh"
    ok "--vscode: hooks at .github/hooks/ (block-no-verify.json + script)"
}

status_all() {
    say ""
    say "agent-error-log --no-verify blocker status:"
    if [ -x "$ROOT/.git/hooks/commit-msg" ]; then ok "--git   installed (.git/hooks/commit-msg)"; else skip "--git   not installed"; fi
    if [ -x "$ALIAS_BIN/block-no-verify" ]; then ok "--alias wrapper at $ALIAS_BIN/block-no-verify"; else skip "--alias wrapper not installed"; fi
    rc="$(find_rc)"
    if [ -f "$rc" ] && grep -Fqx "$ALIAS_LINE" "$rc"; then ok "--alias active in $rc"; else skip "--alias not in $rc"; fi
    if [ -f "$ROOT/.claude/settings.json" ] && grep -q "block-no-verify-hook.sh" "$ROOT/.claude/settings.json"; then ok "--claude installed (.claude/settings.json)"; else skip "--claude not installed"; fi
    if [ -f "$ROOT/.github/hooks/block-no-verify.json" ]; then ok "--vscode installed (.github/hooks/)"; else skip "--vscode not installed"; fi
}

usage() {
    cat <<'EOF'
hooks/install.sh — one-command setup for the --no-verify blockers

Usage:
  ./hooks/install.sh [--git] [--alias] [--claude] [--vscode] [--all] [--status]

  (no flags)        install everything (same as --all)
  --git             install the commit-msg log-before-fix gate
  --alias           install the git wrapper that rejects --no-verify
  --claude          install the Claude Code PreToolUse hook
  --vscode          install the VS Code agent hooks
  --status          report what is installed (no changes)
  --help            show this help

Every step is idempotent and backs up files before changing them.
EOF
}

if [ $# -eq 0 ]; then
    set -- --all
fi

for arg in "$@"; do
    case "$arg" in
        --help)   usage; exit 0 ;;
        --status) status_all; exit 0 ;;
    esac
done

rc_=0
for arg in "$@"; do
    case "$arg" in
        --git)    install_git || rc_=1 ;;
        --alias)  install_alias || rc_=1 ;;
        --claude) install_claude || rc_=1 ;;
        --vscode) install_vscode || rc_=1 ;;
        --all)    install_git || rc_=1; install_alias || rc_=1; install_claude || rc_=1; install_vscode || rc_=1 ;;
        *)        say "unknown option: $arg (see --help)"; rc_=1 ;;
    esac
done
exit $rc_
