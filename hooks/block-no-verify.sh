#!/bin/sh
# block-no-verify.sh — git wrapper that refuses `git commit --no-verify` / `-n`.
#
# Why: `git commit --no-verify` skips ALL git hooks, including the
# log-before-fix commit gate (git-commitmsg-hook.sh). This wrapper makes the
# bypass a deliberate, annoying act instead of a silent default.
#
# Install (pick one — note the alias does NOT repeat 'git'):
#   alias git='block-no-verify'               # ~/.bashrc / ~/.zshrc / ~/.profile
#   git() { block-no-verify "$@"; }           # shell-function wrapper
#
# Behaviour: only commits attempted with --no-verify / -n are blocked. Every
# other git invocation passes straight through. This is a best-effort layer —
# git hooks are advisory, and a direct call to /usr/bin/git (or another
# shell's PATH) still bypasses it. See hooks/README.md for the full stack of
# enforcement layers.

# Find the git subcommand: the first non-option argument. Options that take a
# value (-c <k=v>, -C <dir>) consume the next argument, so `git -C dir commit
# ...` still resolves to the subcommand 'commit' and is blocked correctly.
cmd=""
skip_next=false
for arg in "$@"; do
    if [ "$skip_next" = true ]; then
        skip_next=false
        continue
    fi
    case "$arg" in
        -c|-C) skip_next=true ;;
        --*) continue ;;
        -*) continue ;;
        *) cmd="$arg"; break ;;
    esac
done

if [ "$cmd" = "commit" ]; then
    for arg in "$@"; do
        case "$arg" in
            --no-verify|-n)
                echo "block-no-verify: 'git commit --no-verify' blocked — it skips the" >&2
                echo "  log-before-fix commit gate. If the hook blocked you, the error" >&2
                echo "  isn't logged yet:" >&2
                echo "    python check_errors.py --add" >&2
                echo "  then commit again WITHOUT --no-verify:" >&2
                echo "    git commit -m \"fix <thing> (AREA: <what broke>)\"" >&2
                exit 1
                ;;
        esac
    done
fi

exec git "$@"
