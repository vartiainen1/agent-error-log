"""check_errors.py — Agent error-log tooling (stdlib only, Windows-safe).

Keeps the error log healthy and bakes the LOG-BEFORE-FIXING rule into
tooling so it does not rely on memory. Run from the folder holding this
script (or point --log at any error log):

    python check_errors.py                              validate every entry
    python check_errors.py --has-entry "webhook"        gate a fix: exit 0
                                                        only if an entry with
                                                        that AREA is logged
    python check_errors.py --add                        scaffold a new entry
    python check_errors.py --archive-days 30            preview FIXED entries
                                                        older than 30 days
    python check_errors.py --archive-days 30 --apply    actually move them
    python check_errors.py --lessons                   preview distilled lessons
    python check_errors.py --lessons --apply           write them into rules.txt
    python check_errors.py --check-commit msg.txt      gate on a commit message
                                                       (server-side CI backstop)
    python check_errors.py --init [--target DIR]       one-command adoption:
                                                       scaffold the templates,
                                                       install the commit-msg
                                                       hook, health-check, test

Exit codes: 0 = ok / gate passed, 1 = validation errors or gate failed.
"""

import argparse
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
# Default error log filename. Rename to match your project, or pass --log PATH.
LOG = HERE / "errors.txt"

STATUSES = ("FIXED", "PARTIAL", "OPEN", "MITIGATED", "WORKAROUND")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ENTRY_RE = re.compile(r"^\[(?P<tag>[^\]]+)\] AREA: (?P<area>.+)$")
FIELD_RE = re.compile(r"^  (?P<field>ERROR|CAUSE|FIX|STATUS):\s*(?P<value>.*)$")
SEP_RE = re.compile(r"^={10,}$")
ARCHIVE_TITLE = "ARCHIVED ENTRIES"
SECTION5 = "5) TO ADD A NEW ENTRY"
RULES = HERE / "rules.txt"          # rules file holding the LESSONS section
LESSONS_HEADER = "LESSONS LEARNED"
STOPWORDS = frozenset({"about","after","also","and","are","been","before","being","but","can","cause","causes","could","did","does","error","errors","even","every","first","fix","fixed","from","have","into","issue","issues","just","logged","make","more","most","must","other","over","same","should","some","still","such","than","that","their","them","then","there","these","they","this","those","through","under","used","using","very","was","were","what","when","where","which","while","will","with","without","would","your"})


def load(path):
    """Read a text file with UTF-8 fallback."""
    return path.read_text(encoding="utf-8", errors="replace")


def parse_entries(text):
    """Return a list of entry dicts, in file order.

    An entry starts at a column-0 "[tag] AREA: ..." line (the template in
    section 5 is indented, so it never matches) and runs until the next
    entry header or a "====" section separator.
    """
    lines = text.splitlines()
    entries = []
    for i, line in enumerate(lines):
        m = ENTRY_RE.match(line)
        if not m:
            continue
        j = i + 1
        body = []
        while j < len(lines) and not (ENTRY_RE.match(lines[j]) or SEP_RE.match(lines[j])):
            body.append(lines[j])
            j += 1
        fields = {}
        for bl in body:
            fm = FIELD_RE.match(bl)
            if fm:
                fields.setdefault(fm.group("field"), fm.group("value").strip())
        entries.append({
            "tag": m.group("tag"),
            "area": m.group("area"),
            "line": i,
            "body": body,
            "fields": fields,
            "block": "\n".join([line] + body),
        })
    return entries


def status_token(status):
    """First word of a STATUS value, punctuation stripped ('FIXED.' -> 'FIXED')."""
    if not status:
        return ""
    return re.split(r"\s", status.strip())[0].rstrip(".,;—-")


def find_section5(text):
    """Line index of the section-5 header, or None."""
    for i, l in enumerate(text.splitlines()):
        if l.strip() == SECTION5:
            return i
    return None


def insert_before_section5(text, block):
    """Insert a block (already formatted) directly above section 5's bar.

    The block goes between the last live content and the separator bar that
    belongs to section 5, so the bar stays attached to its header and no
    stray bar or blank line is left behind.
    """
    idx = find_section5(text)
    lines = text.splitlines()
    if idx is None:
        return text.rstrip("\n") + "\n\n" + block.rstrip("\n") + "\n"
    k = idx
    while k > 0 and not SEP_RE.match(lines[k]):
        k -= 1
    if k == 0 and not SEP_RE.match(lines[0]):
        k = idx  # no bar above section 5 — insert directly above the header
    before, after = lines[:k], lines[k:]
    while before and before[-1].strip() == "":
        before.pop()
    while after and after[0].strip() == "":
        after.pop(0)
    return "\n".join(before) + "\n\n" + block.rstrip("\n") + "\n\n" + "\n".join(after) + "\n"


def cmd_check(text):
    """Validate every entry against the template and the status vocabulary."""
    errors, warnings = [], []
    seen = set()
    entries = parse_entries(text)
    if not entries:
        print("No entries found in the error log.")
        return 0
    for e in entries:
        tag = e["tag"].strip("[]")
        loc = f"line {e['line'] + 1} [{e['tag']}] AREA: {e['area']}"
        if not (DATE_RE.match(tag) or tag == "always"):
            warnings.append(f"{loc}: unusual tag (expected YYYY-MM-DD or 'always')")
        for f in ("ERROR", "CAUSE", "STATUS"):
            if not e["fields"].get(f, ""):
                errors.append(f"{loc}: missing {f} field")
        if not e["fields"].get("FIX", ""):
            warnings.append(f"{loc}: FIX missing/blank (fill it in after fixing)")
        st = status_token(e["fields"].get("STATUS", ""))
        if st.upper() not in STATUSES:
            warnings.append(f"{loc}: STATUS '{st}' not in {STATUSES}")
        key = (e["tag"], e["area"])
        if key in seen:
            warnings.append(f"{loc}: duplicate entry")
        seen.add(key)
    for msg in errors:
        print(f"ERROR: {msg}")
    for msg in warnings:
        print(f"WARN : {msg}")
    print(f"{len(entries)} entrie(s): {len(errors)} error(s), {len(warnings)} warning(s).")
    return 1 if errors else 0


def cmd_has_entry(text, substr):
    """Mechanical gate: exit 0 only if an entry mentions substr."""
    needle = substr.lower()
    found = [e for e in parse_entries(text) if needle in (e["area"] + " " + e["tag"]).lower()]
    if found:
        for e in found:
            print(f"found: [{e['tag']}] AREA: {e['area']}  (line {e['line'] + 1})")
        print("GATE PASSED — the error is logged. You may now apply the fix.")
        return 0
    print(f"GATE FAILED — no entry for '{substr}'. LOG BEFORE FIXING:")
    print("add an entry first (python check_errors.py --add), then fix.")
    return 1


def ask(prompt, required=False, default=None):
    """Single-line interactive prompt (Ctrl-C/EOF aborts cleanly)."""
    if default:
        prompt += f" [{default}]"
    try:
        val = input(prompt + ": ").strip()
    except EOFError:
        print("\n(aborted)")
        raise SystemExit(1)
    if not val and default:
        val = default
    if required and not val:
        print("Required — aborting.")
        raise SystemExit(1)
    return val


def cmd_add(text, log_path):
    """Scaffold a new entry in the template format, then append it to the log."""
    area = ask("AREA (what broke)", required=True)
    error = ask("ERROR (symptom)", required=True)
    cause = ask("CAUSE (root cause)", required=True)
    fix = ask("FIX (what fixed it)", default="(pending — fill in after fixing)")
    while True:
        st = ask("STATUS", default="OPEN").upper()
        if st in STATUSES:
            break
        print(f"Status must be one of: {STATUSES}")
    block = (
        f"[{date.today():%Y-%m-%d}] AREA: {area}\n"
        f"  ERROR: {error}\n"
        f"  CAUSE: {cause}\n"
        f"  FIX: {fix}\n"
        f"  STATUS: {st}.\n"
    )
    log_path.write_text(insert_before_section5(text, block), encoding="utf-8")
    print("Logged:")
    print(block.rstrip("\n"))
    return 0


def cmd_archive(text, days, apply, log_path):
    """Move FIXED entries older than N days into an ARCHIVED section."""
    cutoff = date.today() - timedelta(days=days)
    lines = text.splitlines()
    entries = parse_entries(text)
    arch_start = next((i for i, l in enumerate(lines) if l.startswith(ARCHIVE_TITLE)), len(lines))
    already = [e for e in entries if e["line"] >= arch_start]
    moved = []
    for e in entries:
        if e["line"] >= arch_start:
            continue
        t = e["tag"].strip("[]")
        if not DATE_RE.match(t):
            continue
        try:
            d = date.fromisoformat(t)
        except ValueError:
            print(f"WARN : skipping entry with invalid date '{t}' ({e['area']})")
            continue
        if d > cutoff:
            continue
        if status_token(e["fields"].get("STATUS", "")).upper() != "FIXED":
            continue
        moved.append(e)
    if not moved and not already:
        print(f"No FIXED entries older than {days} days to archive (cutoff {cutoff}).")
        return 0
    print(f"{len(moved)} FIXED entrie(s) older than {days} days (cutoff {cutoff}):")
    for e in moved:
        print(f"  {e['block'].splitlines()[0]}")
    if already:
        print(f"({len(already)} entrie(s) already in the archived section.)")
    if not apply:
        print("Dry run — nothing changed. Re-run with --apply to move them.")
        return 0
    drop = set()
    for e in moved + already:
        for n in range(e["line"], e["line"] + 1 + len(e["body"])):
            drop.add(n)
    if already:
        # Drop the old ARCHIVED section header too (bar above + title + bar
        # below), so a re-run does not leave a stray bar or a second header
        # behind — the section is rebuilt from scratch below.
        arch_idx = next(i for i, l in enumerate(lines) if l.startswith(ARCHIVE_TITLE))
        top = arch_idx
        while top > 0 and not SEP_RE.match(lines[top - 1]):
            top -= 1
        bottom = arch_idx
        while bottom + 1 < len(lines) and not SEP_RE.match(lines[bottom + 1]):
            bottom += 1
        for n in range(top - 1, bottom + 2):
            drop.add(n)
    kept = [l for n, l in enumerate(lines) if n not in drop]
    out, prev_blank = [], True
    for l in kept:
        blank = l.strip() == ""
        if blank and prev_blank:
            continue
        out.append(l)
        prev_blank = blank
    blocks = [e["block"].rstrip() for e in sorted(moved + already, key=lambda e: e["line"])]
    section = (
        "=" * 80 + "\n"
        + ARCHIVE_TITLE + " (FIXED, moved by check_errors.py --archive-days)\n"
        + "=" * 80 + "\n\n"
        + "\n\n".join(blocks) + "\n"
    )
    rebuilt = insert_before_section5("\n".join(out).rstrip("\n") + "\n", section)
    log_path.write_text(rebuilt, encoding="utf-8")
    print(f"Archived {len(blocks)} entrie(s). Log updated.")
    return 0



# --- Lessons distillation (--lessons) --------------------------------------

def _tokens(text):
    """Yield significant lowercase words (len>=4, not stopwords, no digits)."""
    for w in re.split(r"[^A-Za-z0-9_']+", text.lower()):
        w = w.strip("_'")
        if len(w) >= 4 and w not in STOPWORDS and not any(c.isdigit() for c in w):
            yield w


def _entry_tokens(e):
    """Tokens of an entry's AREA + ERROR + CAUSE (the text that explains WHY)."""
    txt = " ".join([e["area"], e["fields"].get("ERROR", ""), e["fields"].get("CAUSE", "")])
    return list(_tokens(txt))


def cluster_entries(entries):
    """Group entries into lessons by shared cause keywords (deterministic).

    Each entry is represented by its 3 most frequent significant keywords;
    entries sharing at least one keyword join the same cluster. Returns
    (clusters, counts) where counts is the global keyword frequency map.
    """
    counts = Counter(t for e in entries for t in _entry_tokens(e))
    clusters = []
    for e in entries:
        sig = sorted({t for t in _entry_tokens(e)}, key=lambda t: (-counts[t], t))[:3]
        for c in clusters:
            if set(sig) & c["keywords"]:
                c["entries"].append(e)
                c["keywords"] |= set(sig)
                break
        else:
            clusters.append({"keywords": set(sig), "entries": [e]})
    return clusters, counts


def render_lessons(clusters, counts, total):
    """Render the LESSONS section text from clusters (stdout + rules.txt)."""
    lines = [
        "Distilled from the error log by: python check_errors.py --lessons [--apply]",
        f"Generated: {date.today():%Y-%m-%d}  |  source: {total} error log entrie(s).",
        "",
    ]
    for n, c in enumerate(clusters, 1):
        kws = c["keywords"] or {"(no keywords)"}
        title = max(kws, key=lambda k: (counts.get(k, 0), k))
        areas = "; ".join(e["area"] for e in c["entries"])
        lines += [
            f"{n}. {title}",
            f"   {len(c['entries'])} entrie(s): {areas}",
            f"   Common cause keywords: {', '.join(sorted(kws))}",
            "   Action: re-read the CAUSE fields of these entries before touching",
            "   related code, so the same mistake is not repeated.",
            "",
        ]
    return "\n".join(lines).rstrip("\n") + "\n"


def _patch_rules_lessons(rules_path, body):
    """Replace the LESSONS section in rules.txt with body; append if absent.

    The header is anchored to a real section title (a numbered section
    line or exactly 'LESSONS LEARNED'), so a stray mention of the words in
    the body is never mistaken for the section. Original line endings are
    preserved (CRLF in, CRLF out).
    """
    raw = rules_path.read_bytes() if rules_path.exists() else b""
    crlf = b"\r\n" in raw
    text = raw.decode("utf-8", errors="replace")
    bar = "=" * 80
    lines = text.splitlines()
    idx = next((i for i, l in enumerate(lines)
                if LESSONS_HEADER in l
                and (re.match(r"^\s*\d+\)", l) or l.strip() == LESSONS_HEADER)), None)
    if idx is not None:
        head = "\n".join(lines[: idx + 1])
        out = head + "\n" + bar + "\n" + body
    else:
        block = f"{bar}\n{LESSONS_HEADER}\n{bar}\n{body}"
        out = block if not text.strip() else text.rstrip("\r\n") + "\n\n" + block
    return out.replace("\n", "\r\n") if crlf else out


def cmd_lessons(text, rules_path, apply):
    """Distill recurring causes into lessons; --apply writes rules.txt."""
    entries = parse_entries(text)
    if not entries:
        print("No entries in the error log - nothing to distill.")
        return 0
    clusters, counts = cluster_entries(entries)
    body = render_lessons(clusters, counts, len(entries))
    print(body, end="")
    print(f"{len(clusters)} lesson(s) distilled from {len(entries)} entrie(s).")
    if not apply:
        print("Dry run - nothing changed. Re-run with --apply to write this")
        print("LESSONS section into the rules file (rules.txt).")
        return 0
    if not rules_path.exists():
        print(f"WARN : rules file not found: {rules_path} (creating it)")
    rules_path.write_bytes(_patch_rules_lessons(rules_path, body).encode("utf-8"))
    print(f"LESSONS section written to: {rules_path}")
    return 0
def _extract_area(msg):
    """Pull the last AREA:/LOG: marker value from a commit message, or None."""
    for line in msg.splitlines():
        marks = list(re.finditer(r"(?:AREA|LOG)\s*:", line, re.IGNORECASE))
        if not marks:
            continue
        area = line[marks[-1].end():]
        area = re.sub(r"[),.;:]+\s*$", "", area)
        return re.sub(r"\s+", " ", area).strip()
    return None


def cmd_check_commit(text, msg_path):
    """Gate on a commit message file: exit 0 only if it names a logged error.

    Mirrors the commit-msg hook's core rule so CI can re-run it server-side,
    where --no-verify cannot reach. The message must carry an 'AREA:' (or
    'LOG:') marker naming an error that is already logged.
    """
    if not msg_path.exists():
        print(f"commit-gate: message file not found: {msg_path}")
        return 1
    area = _extract_area(load(msg_path))
    if not area:
        print("commit-gate BLOCKED: no 'AREA:' marker in the commit message.")
        print("  Log the error first:  python check_errors.py --add")
        print('  Then commit with:     git commit -m "... (AREA: <what broke>)"')
        return 1
    # Mirrors cmd_has_entry / the hook's --has-entry search -- keep in sync.
    needle = area.lower()
    found = [e for e in parse_entries(text)
             if needle in (e["area"] + " " + e["tag"]).lower()]
    if found:
        print(f'commit-gate OK: "{area}" is logged — fix may land.')
        return 0
    print(f'commit-gate BLOCKED: "{area}" is NOT logged in the error log.')
    print("  LOG BEFORE FIXING: add an entry first (python check_errors.py --add),")
    print("  then commit again.")
    return 1


# --- One-command adoption (--init) ------------------------------------------
# --init scaffolds the three template files (errors / rules / notes), installs
# the commit-msg gate, health-checks the log, and runs the tooling's own unit
# tests. Templates are copied from the folder holding this script; when only
# check_errors.py was copied into a project (no templates), built-in minimal
# scaffolds are used instead. Existing files are NEVER overwritten.

# The errors.txt template is a STATIC scaffold, never a copy of this repo's
# live errors.txt: the repo's log legitimately accumulates this project's own
# dev entries, and pre-seeding a consumer's log with them would let the gate
# "pass" for errors that were never logged in the consumer's project.
# NOTE: every continuation line starts with '+' so adjacent string literals
# are never implicitly concatenated (a '\n"' line followed by '"=' would make
# '* 80' multiply the merged pair).
MINIMAL_ERRORS = (
    "=" * 80 + "\n"
    + "ERROR LOG — scaffolded by check_errors.py --init\n"
    + "=" * 80 + "\n"
    + "\n"
    + "MANDATORY: log FIRST, fix AFTER (enforced by check_errors.py and the\n"
    + "git commit-msg hook). Statuses: FIXED | PARTIAL | OPEN | MITIGATED |\n"
    + "WORKAROUND. Write the CAUSE before fixing — if you cannot explain why it\n"
    + "broke, you have not understood it yet.\n"
    + "\n"
    + "=" * 80 + "\n"
    + "EXAMPLE ENTRIES (replace with your own; delete this section header)\n"
    + "=" * 80 + "\n"
    + "\n"
    + "[2026-08-05] AREA: payment webhook parser\n"
    + "  ERROR: KeyError: 'amount' on webhook payloads without an amount field\n"
    + "  CAUSE: the payload dict has no 'amount' key; payload['amount'] raises\n"
    + "  FIX: use payload.get('amount', 0) and guard None before .strip()\n"
    + "  STATUS: FIXED.\n"
    + "\n"
    + "[2026-08-07] AREA: image resize service timeouts\n"
    + "  ERROR: resize job hangs for >60s on 50MP inputs\n"
    + "  CAUSE: Pillow opens the full image into memory before resizing\n"
    + "  FIX: (pending — use progressive downscaling / streaming resize)\n"
    + "  STATUS: OPEN.\n"
    + "\n"
    + "=" * 80 + "\n"
    + "5) TO ADD A NEW ENTRY\n"
    + "=" * 80 + "\n"
    + "  [YYYY-MM-DD] AREA: <what broke>\n"
    + "    ERROR: <symptom>\n"
    + "    CAUSE: <root cause — write this BEFORE fixing>\n"
    + "    FIX: <what fixed it — fill in after fixing>\n"
    + "    STATUS: FIXED | PARTIAL | OPEN | MITIGATED | WORKAROUND\n"
)

MINIMAL_RULES = (
    "=" * 80 + "\n"
    + "<YOUR PROJECT NAME> — RULES OF ENGAGEMENT\n"
    + "(scaffolded by check_errors.py --init)\n"
    + "=" * 80 + "\n"
    + "\n"
    + "1. CHECK BEFORE CODING: read errors.txt before writing or debugging code,\n"
    + "   so past mistakes are not repeated.\n"
    + "2. LOG BEFORE FIXING: found an error? log it in errors.txt FIRST, only\n"
    + "   then fix it. No exceptions (enforced by the commit-msg hook).\n"
    + "3. Notes go in notes.txt; behavior rules live in this file.\n"
)

MINIMAL_NOTES = (
    "=" * 80 + "\n"
    + "<YOUR PROJECT NAME> — NOTES\n"
    + "(scaffolded by check_errors.py --init)\n"
    + "=" * 80 + "\n"
    + "\n"
    + "SESSION NOTE (YYYY-MM-DD): <title>\n"
    + "- what happened this session, decisions taken, and the next step\n"
)

MINIMAL_HOOK = (
    "#!/bin/sh\n"
    "# commit-msg hook scaffolded by check_errors.py --init\n"
    "ROOT=\"$(git rev-parse --show-toplevel 2>/dev/null)\" || { echo \"not a git repository\"; exit 1; }\n"
    "LOGPATH=\"${LOGNAME:-errors.txt}\"\n"
    "CHECKER=\"${AGENT_ERROR_LOG_DIR:-$ROOT}/check_errors.py\"\n"
    "PY=\"${PYTHON:-python}\"\n"
    "if [ ! -f \"$CHECKER\" ]; then\n"
    "    echo \"commit-msg: cannot find $CHECKER — place check_errors.py at the repo root\"\n"
    "    exit 1\n"
    "fi\n"
    "staged=\"$(git diff --cached --name-only)\"\n"
    "if printf '%s\\n' \"$staged\" | grep -qx \"$LOGPATH\"; then\n"
    "    \"$PY\" \"$CHECKER\" || { echo \"commit-msg: error log invalid\"; exit 1; }\n"
    "fi\n"
    "if ! printf '%s\\n' \"$staged\" | grep -Eq '\\.(py|js|ts|jsx|tsx|html|bat|sh|cmd)$'; then\n"
    "    exit 0\n"
    "fi\n"
    "line=\"$(tr -d '\\r' < \"$1\" 2>/dev/null | grep -i -m1 -E 'AREA:|LOG:')\"\n"
    "area=\"$(printf '%s\\n' \"$line\" | sed -E 's/^.*(AREA|LOG):[[:space:]]*//I' | sed -E 's/[),.;:]+[[:space:]]*$//' | tr -s ' ')\"\n"
    "if [ -z \"$area\" ]; then\n"
    "    echo \"commit-msg BLOCKED: code staged but no 'AREA:' marker in the message.\"\n"
    "    echo \"  Log the error first: python check_errors.py --add\"\n"
    "    exit 1\n"
    "fi\n"
    "\"$PY\" \"$CHECKER\" --has-entry \"$area\"\n"
    "exit $?\n"
)


def _template_text(name, fallback):
    """Content for a template file: the real template next to this script (for
    rules.txt / notes.txt / the hook), or a minimal built-in scaffold when it
    is missing (e.g. only check_errors.py was copied into the target project).

    NOTE: errors.txt does NOT go through here — it is always the static
    MINIMAL_ERRORS scaffold, so a consumer never inherits this repo's dev log.
    rules.txt / notes.txt are copied from HERE only because they are verified
    generic templates; keep them free of project-specific content, or they
    will need the same static treatment."""
    p = HERE / name
    if p.exists():
        return p.read_text(encoding="utf-8", errors="replace")
    return fallback


def _install_hook(target):
    """Install the commit-msg gate into target/.git/hooks.

    Returns (installed: bool, note: str). Never fails on a missing repo —
    --init warns and continues, so it stays a one-command setup even before
    'git init'. An existing hook is backed up, not clobbered.
    """
    git_dir = target / ".git"
    if not git_dir.exists():
        return False, ("not a git repository — hook NOT installed (run 'git init' "
                       "here first, then re-run --init)")
    if git_dir.is_file():
        # git worktree / submodule: .git is a pointer file to the real gitdir.
        m = re.match(r"gitdir:\s*(.+)$", git_dir.read_text(encoding="utf-8", errors="replace").strip())
        if not m:
            return False, "cannot resolve .git pointer (worktree) — hook NOT installed"
        p = Path(m.group(1).strip())
        git_dir = p if p.is_absolute() else (target / p).resolve()
        if not git_dir.is_dir():
            return False, f"resolved gitdir missing: {git_dir} — hook NOT installed"
    hooks = git_dir / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    dest = hooks / "commit-msg"
    if dest.exists():
        bak = hooks / "commit-msg.agent-error-log.bak"
        if bak.exists():
            bak.unlink()
        dest.rename(bak)
        print(f"  backed up previous hook to: {bak}")
    dest.write_text(_template_text("git-commitmsg-hook.sh", MINIMAL_HOOK), encoding="utf-8")
    try:
        os.chmod(dest, 0o755)  # executable bit (best-effort on Windows)
    except OSError:
        pass
    return True, f"installed commit-msg hook: {dest}"


def cmd_init(target, run_tests=True):
    """One-command adoption: scaffold the templates, install the git hook,
    health-check the error log, and (optionally) run the unit tests.

    Existing files are never overwritten; a missing git repo only warns.
    """
    target = Path(target)
    if target.exists() and not target.is_dir():
        print(f"--init target is not a directory: {target}")
        return 1
    target.mkdir(parents=True, exist_ok=True)
    print(f"--init target: {target}")
    # errors.txt is always the clean static scaffold (see MINIMAL_ERRORS);
    # rules.txt / notes.txt / the hook are copied from this repo's templates.
    for name, content in (("errors.txt", MINIMAL_ERRORS),
                          ("rules.txt", _template_text("rules.txt", MINIMAL_RULES)),
                          ("notes.txt", _template_text("notes.txt", MINIMAL_NOTES))):
        dest = target / name
        if dest.exists():
            print(f"  exists: {name} (left untouched)")
            continue
        dest.write_text(content, encoding="utf-8")
        print(f"  created: {name}")
    ok, note = _install_hook(target)
    if ok:
        print(f"  hook: {note}")
    else:
        print(f"  WARN: {note}")
    log = target / "errors.txt"
    if log.exists():
        rc = cmd_check(load(log))
        print(f"  health check: error log {'OK' if rc == 0 else 'HAS PROBLEMS (see above)'}")
    else:
        print("  WARN: no errors.txt to health-check")
    selftest = HERE / "_test_errors.py"
    if run_tests and selftest.exists():
        print(f"  self-test: running the tooling's unit tests ({selftest}) ...")
        ret = subprocess.run([sys.executable, str(selftest)], check=False)
        if ret.returncode != 0:
            print(f"  self-test FAILED (exit {ret.returncode}) — the tooling is broken")
            print("  in this environment; adoption continues but fix it before relying on")
            print("  the gate.")
            return 1
        print("  self-test: all tests passed")
    else:
        print("  self-test: skipped (run_tests off, or no _test_errors.py next to")
        print("             check_errors.py)")
    print("  NEXT: python check_errors.py to validate; start.py for the session")
    print("        bootstrap. Behavior rules live in rules.txt.")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="Validate and maintain the error log (stdlib only). "
                    "Exit 0 = ok / gate passed, 1 = validation errors / gate failed.")
    ap.add_argument("--log", metavar="PATH",
                    help="error log to use (default: errors.txt in this folder)")
    ap.add_argument("--has-entry", metavar="SUBSTR",
                    help="gate: exit 0 only if an entry with this AREA is logged")
    ap.add_argument("--add", action="store_true", help="scaffold a new entry (interactive)")
    ap.add_argument("--archive-days", type=int, metavar="N",
                    help="preview FIXED entries older than N days")
    ap.add_argument("--apply", action="store_true",
                    help="with --archive-days: actually move them; with "
                         "--lessons: write the LESSONS section into rules.txt")
    ap.add_argument("--lessons", action="store_true",
                    help="distill recurring cause keywords from the error log "
                         "into lessons (preview; --apply writes rules.txt)")
    ap.add_argument("--rules", metavar="PATH",
                    help="rules file to update with --lessons --apply "
                         "(default: rules.txt in this folder)")
    ap.add_argument("--check-commit", metavar="FILE",
                    help="gate: exit 0 only if the commit message in FILE "
                         "names a logged error (AREA:/LOG: marker)")
    ap.add_argument("--init", action="store_true",
                    help="one-command adoption: scaffold errors/rules/notes, "
                         "install the commit-msg hook, health-check, self-test")
    ap.add_argument("--target", metavar="DIR",
                    help="with --init: directory to adopt (default: current "
                         "directory)")
    ap.add_argument("--no-tests", action="store_true",
                    help="with --init: skip the tooling's unit-test run")
    args = ap.parse_args()

    if args.init:
        return cmd_init(args.target or ".", run_tests=not args.no_tests)

    log_path = Path(args.log) if args.log else LOG
    if not log_path.exists():
        print(f"missing error log: {log_path}")
        return 1
    text = load(log_path)

    if args.has_entry is not None:
        return cmd_has_entry(text, args.has_entry)
    if args.add:
        return cmd_add(text, log_path)
    if args.archive_days is not None:
        return cmd_archive(text, args.archive_days, args.apply, log_path)
    if args.lessons:
        rules_path = Path(args.rules) if args.rules else RULES
        return cmd_lessons(text, rules_path, args.apply)
    if args.check_commit:
        return cmd_check_commit(text, Path(args.check_commit))
    return cmd_check(text)


if __name__ == "__main__":
    sys.exit(main())
