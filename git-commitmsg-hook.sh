#!/bin/sh
# Agent Error Log commit-msg hook — "LOG BEFORE FIXING": a code commit cannot
# land unless the error it fixes is already logged.
#
# Why commit-msg and not pre-commit: git runs pre-commit BEFORE the commit
# message exists (COMMIT_EDITMSG is not written yet), so the message can only
# be read from the commit-msg hook, which receives the message file as $1.
# A non-zero exit here aborts the commit, so this is still a hard gate.
#
# Convention: fix commits must name the logged error in the commit message:
#     git commit -m "fix sprite tracking (AREA: player sprite color WRONG)"
# The hook extracts the AREA and runs:  check_errors.py --has-entry "<AREA>"
#
# Exempt: commits that stage no code files, and log-only commits (the staged
# log must still pass the full linter).
#
# CONFIG (all optional env vars):
#   LOGNAME              — your error log filename (default: errors.txt; must
#                          match check_errors.py's LOG constant)
#   PYTHON               — python interpreter to use (default: python)
#   AGENT_ERROR_LOG_DIR  — folder that contains check_errors.py, when it is
#                          NOT at the repo root (default: repo root)
#
# Install with:
#     cp git-commitmsg-hook.sh .git/hooks/commit-msg
#     chmod +x .git/hooks/commit-msg

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "not a git repository"; exit 1; }

LOGPATH="${LOGNAME:-errors.txt}"
CHECKER="${AGENT_ERROR_LOG_DIR:-$ROOT}/check_errors.py"
PY="${PYTHON:-python}"

if [ ! -f "$CHECKER" ]; then
    echo "commit-msg: cannot find $CHECKER"
    echo "  Place the agent-error-log folder at the repo root, or set"
    echo "  AGENT_ERROR_LOG_DIR to the folder that contains check_errors.py."
    exit 1
fi

staged="$(git diff --cached --name-only)"

# 1) The error log was staged -> it must be valid.
if printf '%s\n' "$staged" | grep -qx "$LOGPATH"; then
    "$PY" "$CHECKER" || {
        echo "commit-msg: error log ($LOGPATH) is invalid — fix it first."
        exit 1
    }
fi

# 2) No code staged -> nothing to gate (notes/docs commits pass).
if ! printf '%s\n' "$staged" | grep -Eq '\.(py|js|ts|jsx|tsx|html|bat|sh|cmd)$'; then
    exit 0
fi

# 3) The fix must name the logged error: "AREA: <text>" (or "LOG: <text>").
msgfile="$1"
line="$(tr -d '\r' < "$msgfile" 2>/dev/null | grep -i -m1 -E 'AREA:|LOG:')"
area="$(printf '%s\n' "$line" | sed -E 's/^.*(AREA|LOG):[[:space:]]*//I' \
        | sed -E 's/[),.;:]+[[:space:]]*$//' | tr -s ' ')"

if [ -z "$area" ]; then
    echo "commit-msg BLOCKED: code staged but the commit message has no 'AREA:' marker."
    echo "  Log the error first:  python check_errors.py --add"
    echo "  Then commit with:     git commit -m \"... (AREA: <what broke>)\""
    exit 1
fi

"$PY" "$CHECKER" --has-entry "$area"
if [ $? -ne 0 ]; then
    echo "commit-msg BLOCKED: the error \"$area\" is NOT logged in $LOGPATH."
    echo "  LOG BEFORE FIXING: add an entry first (python check_errors.py --add),"
    echo "  then commit again."
    exit 1
fi

echo "commit-msg OK: \"$area\" is logged — fix may land."
exit 0
