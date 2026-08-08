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

Exit codes: 0 = ok / gate passed, 1 = validation errors or gate failed.
"""

import argparse
import re
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
    args = ap.parse_args()

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
    return cmd_check(text)


if __name__ == "__main__":
    sys.exit(main())
