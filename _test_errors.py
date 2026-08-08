"""Unit tests for check_errors.py — parsing, validation, gate, add, archive.
Run: python _test_errors.py"""

import io
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

import check_errors as ce

PASS = 0

BAR = "=" * 80
TODAY = date.today()


def t(name, cond):
    global PASS
    assert cond, f"FAIL: {name}"
    PASS += 1
    print(f"PASS {PASS}: {name}")


def quiet(fn, *args, **kwargs):
    """Run fn with stdout captured so PASS lines stay readable."""
    old = sys.stdout
    sys.stdout = io.StringIO()
    try:
        return fn(*args, **kwargs)
    finally:
        sys.stdout = old


def entry(tag, area, status, with_error=True, with_cause=True, with_fix=True):
    """One template-formatted entry."""
    e = f"[{tag}] AREA: {area}\n"
    if with_error:
        e += "  ERROR: symptom\n"
    if with_cause:
        e += "  CAUSE: root cause\n"
    if with_fix:
        e += "  FIX: the fix\n"
    e += f"  STATUS: {status}.\n"
    return e


def sample_log(fixed_days=10):
    """Small representative log: one old FIXED, one today OPEN, one evergreen."""
    fixed = (TODAY - timedelta(days=fixed_days)).isoformat()
    today = TODAY.isoformat()
    return (
        BAR + "\n1) TEST AREA\n" + BAR + "\n\n"
        + entry(fixed, "old fixed bug", "FIXED")
        + "\n"
        + entry(today, "new open bug", "OPEN")
        + "\n"
        + entry("always", "evergreen issue", "MITIGATED")
        + "\n"
        + BAR + "\n5) TO ADD A NEW ENTRY\n" + BAR + "\n"
        + "  [YYYY-MM-DD] AREA: <what broke>\n"
        + "    ERROR: <symptom>\n"
        + "    STATUS: FIXED | PARTIAL | OPEN | MITIGATED | WORKAROUND\n"
    )


def tmp_log(text):
    """Write text to a throwaway file; returns (cleaner, path)."""
    d = tempfile.TemporaryDirectory()
    p = Path(d.name) / "errors.txt"
    p.write_text(text, encoding="utf-8")
    return d, p


# --- parse_entries ---------------------------------------------------------
S = sample_log()
es = ce.parse_entries(S)
t("parses the 3 real entries", len(es) == 3)
t("indented template is not an entry", not any("what broke" in e["area"] for e in es))
t("tags parsed", es[0]["tag"] == (TODAY - timedelta(days=10)).isoformat())
t("evergreen tag", es[2]["tag"] == "always")
t("fields extracted", es[0]["fields"]["STATUS"] == "FIXED." and es[1]["fields"]["ERROR"] == "symptom")
t("line index points at the header", S.splitlines()[es[0]["line"]] == es[0]["block"].splitlines()[0])
t("body stops before section bar", not any("5) TO ADD" in l for e in es for l in e["body"]))
t("empty text parses to nothing", ce.parse_entries("") == [])

# --- status_token ----------------------------------------------------------
t("status_token strips dot", ce.status_token("FIXED.") == "FIXED")
t("status_token keeps note prefix", ce.status_token("WORKAROUND SHIPPED; root fix") == "WORKAROUND")
t("status_token splits dash note", ce.status_token("PARTIAL — measured later") == "PARTIAL")
t("status_token empty", ce.status_token("") == "")

# --- find_section5 / insert_before_section5 --------------------------------
idx = ce.find_section5(S)
t("find_section5 found", idx is not None and "5) TO ADD" in S.splitlines()[idx])
t("find_section5 none", ce.find_section5("no section here") is None)

BLOCK = "[2026-08-08] AREA: inserted\n  ERROR: x\n  STATUS: OPEN.\n"
ins = ce.insert_before_section5(S, BLOCK)
L = ins.splitlines()
t("insert keeps the section-5 bar attached", L[L.index("5) TO ADD A NEW ENTRY") - 1].startswith("==="))
t("insert places block before section 5", ins.index("[2026-08-08] AREA: inserted") < ins.index("5) TO ADD A NEW ENTRY"))
t("insert no double blank lines", "\n\n\n" not in ins)
t("insert appends when no section 5", ce.insert_before_section5("A\nB\n", BLOCK).endswith(BLOCK.rstrip("\n") + "\n"))
no_bar = "A\nB\n5) TO ADD A NEW ENTRY\n====\n"
ins2 = ce.insert_before_section5(no_bar, BLOCK)
t("insert falls back when no bar above section 5", ins2.index("AREA: inserted") < ins2.index("5) TO ADD A NEW ENTRY"))

# --- cmd_check -------------------------------------------------------------
t("clean log validates", quiet(ce.cmd_check, S) == 0)
t("missing CAUSE fails", quiet(ce.cmd_check, entry("2026-08-01", "no cause", "FIXED", with_cause=False)) == 1)
t("missing ERROR fails", quiet(ce.cmd_check, entry("2026-08-01", "no error", "FIXED", with_error=False)) == 1)
t("missing FIX warns only", quiet(ce.cmd_check, entry("2026-08-01", "no fix", "FIXED", with_fix=False)) == 0)
t("bad status warns only", quiet(ce.cmd_check, entry("2026-08-01", "bad status", "WEIRD")) == 0)
t("duplicate entry warns only", quiet(ce.cmd_check, entry("2026-08-01", "dup", "FIXED") + entry("2026-08-01", "dup", "FIXED")) == 0)
t("empty log validates", quiet(ce.cmd_check, "") == 0)
t("unusual tag warns only", quiet(ce.cmd_check, entry("weirdtag", "odd tag", "FIXED")) == 0)

# --- cmd_has_entry (gate) --------------------------------------------------
t("gate finds entry", quiet(ce.cmd_has_entry, S, "old fixed bug") == 0)
t("gate is case-insensitive", quiet(ce.cmd_has_entry, S, "OLD FIXED") == 0)
t("gate rejects unknown", quiet(ce.cmd_has_entry, S, "totally unknown") == 1)

# --- cmd_archive -----------------------------------------------------------
d, p = tmp_log(sample_log())
try:
    before = p.read_text(encoding="utf-8")
    t("archive dry run returns 0", quiet(ce.cmd_archive, before, 7, False, p) == 0)
    t("archive dry run does not write", p.read_text(encoding="utf-8") == before)
    t("archive apply returns 0", quiet(ce.cmd_archive, before, 7, True, p) == 0)
    after = p.read_text(encoding="utf-8")
    live, archived = after.split("ARCHIVED ENTRIES")
    t("archive creates ARCHIVED section", "ARCHIVED ENTRIES" in after)
    t("archive moved the old FIXED entry", "AREA: old fixed bug" in archived)
    t("archive removed it from the live section", "AREA: old fixed bug" not in live)
    t("archive leaves today's OPEN entry live", "AREA: new open bug" in live)
    t("archive never moves OPEN entries", "AREA: new open bug" not in archived)
    t("archived log still validates", quiet(ce.cmd_check, after) == 0)
    t("archive leaves no double blanks", "\n\n\n" not in after)
    quiet(ce.cmd_archive, p.read_text(encoding="utf-8"), 7, True, p)
    again = p.read_text(encoding="utf-8")
    t("re-archive does not duplicate", again.count("AREA: old fixed bug") == 1)
    t("re-archive keeps one ARCHIVED header", again.count("ARCHIVED ENTRIES") == 1)
    t("re-archive still validates", quiet(ce.cmd_check, again) == 0)
    quiet(ce.cmd_archive, again, 7, True, p)
    t("archive is idempotent", p.read_text(encoding="utf-8") == again)
    # consolidation: a second old FIXED entry plus the existing archived entry
    cons_base = (
        entry((TODAY - timedelta(days=9)).isoformat(), "second old fixed", "FIXED")
        + "\n"
        + entry(TODAY.isoformat(), "brand new open", "OPEN")
        + "\n\n"
        + again
    )
    p.write_text(cons_base, encoding="utf-8")
    quiet(ce.cmd_archive, p.read_text(encoding="utf-8"), 7, True, p)
    cons = p.read_text(encoding="utf-8")
    clive, carch = cons.split("ARCHIVED ENTRIES")
    t("consolidation archives the new old entry", "AREA: second old fixed" in carch)
    t("consolidation keeps the earlier archived entry", "AREA: old fixed bug" in carch)
    t("consolidation no duplicates", cons.count("AREA: old fixed bug") == 1 and cons.count("AREA: second old fixed") == 1)
    t("consolidation keeps one ARCHIVED header", cons.count("ARCHIVED ENTRIES") == 1)
    t("consolidation keeps live section clean", "AREA: second old fixed" not in clive)
    t("consolidation still validates", quiet(ce.cmd_check, cons) == 0)
    quiet(ce.cmd_archive, cons, 7, True, p)
    t("consolidation is idempotent", p.read_text(encoding="utf-8") == cons)
finally:
    d.cleanup()

# invalid dates are skipped, not crashed on
bad = entry("2026-13-99", "bad date", "FIXED") + entry((date.today() - timedelta(days=20)).isoformat(), "good fixed", "FIXED")
d2, p2 = tmp_log(bad)
try:
    t("archive skips invalid date without crashing", quiet(ce.cmd_archive, p2.read_text(encoding="utf-8"), 7, True, p2) == 0)
    t("valid entry still archived", "AREA: good fixed" in p2.read_text(encoding="utf-8").split("ARCHIVED ENTRIES")[1])
finally:
    d2.cleanup()

# nothing qualifies -> no-op, file untouched
d3, p3 = tmp_log(sample_log(fixed_days=0))
try:
    t("nothing to archive returns 0", quiet(ce.cmd_archive, p3.read_text(encoding="utf-8"), 1, True, p3) == 0)
    t("nothing to archive leaves file", "ARCHIVED ENTRIES" not in p3.read_text(encoding="utf-8"))
finally:
    d3.cleanup()

# --- cmd_add (scaffolder) --------------------------------------------------
with mock.patch("check_errors.input", side_effect=["my area", "boom", "the cause", "the fix", "OPEN"]):
    d4, p4 = tmp_log(sample_log())
    try:
        t("add returns 0", quiet(ce.cmd_add, p4.read_text(encoding="utf-8"), p4) == 0)
        added = p4.read_text(encoding="utf-8")
        t("add writes the entry", "AREA: my area" in added and "STATUS: OPEN." in added)
        t("added entry validates", quiet(ce.cmd_check, added) == 0)
        L4 = added.splitlines()
        t("add above the section-5 bar", L4[L4.index("5) TO ADD A NEW ENTRY") - 1].startswith("==="))
        t("add leaves no double blanks", "\n\n\n" not in added)
    finally:
        d4.cleanup()

# invalid status is retried until canonical
with mock.patch("check_errors.input", side_effect=["a2", "e", "c", "f", "NOPE", "OPEN"]):
    d5, p5 = tmp_log(sample_log())
    try:
        t("add retries bad status", quiet(ce.cmd_add, p5.read_text(encoding="utf-8"), p5) == 0)
        t("add status becomes canonical", "STATUS: OPEN." in p5.read_text(encoding="utf-8"))
    finally:
        d5.cleanup()

# EOF aborts cleanly
with mock.patch("check_errors.input", side_effect=EOFError):
    try:
        ce.ask("x", required=True)
        t("ask aborts on EOF", False)
    except SystemExit:
        t("ask aborts on EOF", True)

with mock.patch("check_errors.input", return_value=""):
    try:
        ce.ask("x", required=True)
        t("ask rejects empty required", False)
    except SystemExit:
        t("ask rejects empty required", True)

print(f"\nAll {PASS} tests passed.")
