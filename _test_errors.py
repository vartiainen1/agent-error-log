"""Unit tests for check_errors.py — parsing, validation, gate, add, archive.
Run: python _test_errors.py"""

import io
import random
import re
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

# --- non-interactive --stdin mode (family finding: truncated piped stdin) ---
def _set_stdin_queue(q):
    old = ce._STDIN_QUEUE
    ce._STDIN_QUEUE = list(q)
    return old


def _stdin_add(text, log, answers):
    old = _set_stdin_queue(answers)
    try:
        return ce.cmd_add(text, log)
    finally:
        ce._STDIN_QUEUE = old


def _exit_code(fn, *a, **kw):
    try:
        fn(*a, **kw)
        return None
    except SystemExit as e:
        return e.code


d7, p7 = tmp_log(sample_log())
try:
    t("stdin add full answers returns 0",
      quiet(_stdin_add, p7.read_text(encoding="utf-8"), p7,
            ["s area", "s boom", "s cause", "s fix", "OPEN"]) == 0)
    a7 = p7.read_text(encoding="utf-8")
    t("stdin add writes the entry",
      "AREA: s area" in a7 and "STATUS: OPEN." in a7 and "FIX: s fix" in a7)
    t("stdin added entry validates", quiet(ce.cmd_check, a7) == 0)
finally:
    d7.cleanup()

# exhausted answers fall back to defaults (as pressing Enter would)
d8, p8 = tmp_log(sample_log())
try:
    t("stdin add truncated answers fall back to defaults",
      quiet(_stdin_add, p8.read_text(encoding="utf-8"), p8,
            ["s8", "e8", "c8", "f8"]) == 0)
    a8 = p8.read_text(encoding="utf-8")
    t("stdin add truncated defaults applied",
      "AREA: s8" in a8 and "STATUS: OPEN." in a8)
finally:
    d8.cleanup()

# missing required answer fails loudly, writes nothing
d9, p9 = tmp_log(sample_log())
try:
    t("stdin add missing required aborts",
      _exit_code(_stdin_add, p9.read_text(encoding="utf-8"), p9,
                 ["", "e9", "c9", "f9", "OPEN"]) == 1)
    t("stdin add missing required writes nothing",
      "AREA: " not in [l for l in p9.read_text(encoding="utf-8").splitlines()
                       if l.startswith("[")])
finally:
    d9.cleanup()

# invalid STATUS fails loudly instead of the interactive retry loop
d10, p10 = tmp_log(sample_log())
try:
    t("stdin add invalid status aborts",
      _exit_code(_stdin_add, p10.read_text(encoding="utf-8"), p10,
                 ["a10", "e10", "c10", "f10", "NOPE"]) == 1)
    t("stdin add invalid status writes nothing",
      "AREA: a10" not in p10.read_text(encoding="utf-8"))
finally:
    d10.cleanup()

# full CLI: --add --stdin through main() with piped stdin
d11, p11 = tmp_log(sample_log())
try:
    with mock.patch("check_errors.sys.argv", ["check_errors.py", "--add", "--stdin", "--log", str(p11)]), \
          mock.patch("check_errors.sys.stdin", io.StringIO("m11\ne11\nc11\nf11\nOPEN\n")):
        t("stdin add via main returns 0", quiet(ce.main) == 0)
    t("stdin add via main writes entry", "AREA: m11" in p11.read_text(encoding="utf-8"))
finally:
    ce._STDIN_QUEUE = None
    d11.cleanup()


# --- scaffold example policy: no OPEN example entries (finding: image-resize) ---
def _example_section(text):
    """The EXAMPLE ENTRIES section of a scaffolded/log text, or '' if absent."""
    m = re.search(r"EXAMPLE ENTRIES.*?\n(?P<body>.*?)(?:\n={10,}|\n5\) TO ADD|\Z)", text, re.S)
    return m.group("body") if m else ""


t("scaffold example section ships no OPEN status",
  "STATUS: OPEN." not in _example_section(ce.MINIMAL_ERRORS))
t("scaffold image-resize example is FIXED",
  re.search(r"AREA: image resize service timeouts\n  ERROR: resize job hangs[^\n]*\n"
            r"  CAUSE: Pillow opens the full image[^\n]*\n"
            r"  FIX: stream-resize[^\n]*\n(?:       [^\n]*\n)?  STATUS: FIXED\.\n",
            ce.MINIMAL_ERRORS) is not None)
t("scaffold example entries all resolved (no OPEN in section)",
  "STATUS: OPEN." not in _example_section(ce.MINIMAL_ERRORS))
t("scaffold still documents OPEN in the vocabulary header",
  "Statuses: FIXED | PARTIAL | OPEN | MITIGATED |" in ce.MINIMAL_ERRORS)
t("live errors.txt example section has no OPEN",
  "STATUS: OPEN." not in _example_section(Path(__file__).resolve().parent.joinpath("errors.txt").read_text(encoding="utf-8")))

# --init scaffold (real file) ships a healthy example section
dI = tempfile.TemporaryDirectory()
try:
    tI = Path(dI.name)
    quiet(ce.cmd_init, tI, False)  # run_tests=False
    created = (tI / "errors.txt").read_text(encoding="utf-8")
    t("init scaffold has zero OPEN example entries",
      "STATUS: OPEN." not in _example_section(created))
    t("init scaffold has the FIXED image-resize example",
      "AREA: image resize service timeouts" in created
      and "STATUS: FIXED." in created)
finally:
    dI.cleanup()


# --- lessons (--lessons) -----------------------------------------------------

def lessons_log():
    return (
        BAR + "\n1) TEST\n" + BAR + "\n\n"
        + "[2026-08-01] AREA: payment webhook parser\n"
        + "  ERROR: KeyError: 'amount' on payloads without an amount field\n"
        + "  CAUSE: the payload dict has no amount key; payload['amount'] raises\n"
        + "  FIX: use payload.get('amount', 0) and guard None\n"
        + "  STATUS: FIXED.\n\n"
        + "[2026-08-02] AREA: CSV importer crash\n"
        + "  ERROR: None.strip() on missing cells\n"
        + "  CAUSE: csv.DictReader fills missing columns with None; code calls .strip()\n"
        + "  FIX: (row.get('x') or '').strip()\n"
        + "  STATUS: FIXED.\n\n"
        + "[2026-08-03] AREA: search API rate limit\n"
        + "  ERROR: HTTP 429 Too Many Requests on back-to-back queries\n"
        + "  CAUSE: the API throttles rapid consecutive requests without gaps\n"
        + "  FIX: exponential backoff + jitter; fallback backend\n"
        + "  STATUS: MITIGATED.\n\n"
        + BAR + "\n5) TO ADD A NEW ENTRY\n" + BAR + "\n"
        + "  [YYYY-MM-DD] AREA: <what broke>\n"
        + "    ERROR: <symptom>\n"
        + "    STATUS: FIXED | PARTIAL | OPEN | MITIGATED | WORKAROUND\n"
    )

t("tokens drop stopwords and short words",
  set(ce._tokens("the payload amount raises without xyz")) == {"payload", "amount", "raises"})

cl, counts = ce.cluster_entries(ce.parse_entries(lessons_log()))
t("lessons: 3 distinct clusters", len(cl) == 3)
t("lessons: every entry clustered",
  sum(len(c["entries"]) for c in cl) == 3)

shared = (
    "[2026-08-04] AREA: rate limit A\n"
    + "  ERROR: 429 again\n"
    + "  CAUSE: API throttles rapid requests\n"
    + "  STATUS: OPEN.\n\n"
    + "[2026-08-05] AREA: rate limit B\n"
    + "  ERROR: 429 twice\n"
    + "  CAUSE: gateway throttles the client\n"
    + "  STATUS: OPEN.\n"
)
cl2, _ = ce.cluster_entries(ce.parse_entries(shared))
t("lessons: shared keyword merges clusters",
  len(cl2) == 1 and len(cl2[0]["entries"]) == 2)

body = ce.render_lessons(cl, counts, 3)
t("lessons: render mentions areas",
  "payment webhook parser" in body and "search API rate limit" in body)
t("lessons: render newline-terminated", body.endswith("\n"))

d6, p6 = tmp_log(lessons_log())
rp6 = Path(d6.name) / "rules.txt"
rp6.write_text(
    "OLD RULES\n7) LESSONS LEARNED FROM THE ERROR LOG\n========\nOLD BODY\n",
    encoding="utf-8",
)
try:
    t("lessons dry run returns 0",
      quiet(ce.cmd_lessons, p6.read_text(encoding="utf-8"), rp6, False) == 0)
    t("lessons dry run leaves rules", "OLD BODY" in rp6.read_text(encoding="utf-8"))
    t("lessons apply returns 0",
      quiet(ce.cmd_lessons, p6.read_text(encoding="utf-8"), rp6, True) == 0)
    after6 = rp6.read_text(encoding="utf-8")
    t("lessons apply replaces old body", "OLD BODY" not in after6)
    t("lessons apply keeps the header",
      "7) LESSONS LEARNED FROM THE ERROR LOG" in after6)
    t("lessons apply writes distilled body",
      "Distilled from the error log" in after6 and "payment webhook parser" in after6)
    rp7 = Path(d6.name) / "rules2.txt"
    rp7.write_text("JUST RULES\n", encoding="utf-8")
    quiet(ce.cmd_lessons, p6.read_text(encoding="utf-8"), rp7, True)
    t("lessons appends when no section",
      "LESSONS LEARNED" in rp7.read_text(encoding="utf-8"))
    d8, p8 = tmp_log(BAR + "\n5) TO ADD A NEW ENTRY\n" + BAR + "\n")
    t("lessons empty log ok",
      quiet(ce.cmd_lessons, p8.read_text(encoding="utf-8"), rp6, True) == 0)
    d8.cleanup()
    nk, pnk = tmp_log(
        "[2026-08-06] AREA: the was\n"
        + "  ERROR: that was then\n"
        + "  CAUSE: when was the\n"
        + "  FIX: n/a\n"
        + "  STATUS: OPEN.\n"
    )
    t("lessons no-keyword entry handled",
      quiet(ce.cmd_lessons, pnk.read_text(encoding="utf-8"), rp6, True) == 0)
    t("lessons no-keyword renders safely",
      "(no keywords)" in rp6.read_text(encoding="utf-8"))
    nk.cleanup()
    rp9 = Path(d6.name) / "rules3.txt"
    rp9.write_bytes(b"OLD RULES\r\n7) LESSONS LEARNED FROM THE ERROR LOG\r\n====\r\nOLD\r\n")
    quiet(ce.cmd_lessons, p6.read_text(encoding="utf-8"), rp9, True)
    t("lessons preserves CRLF endings",
      b"\r\n" in rp9.read_bytes())
    rpa = Path(d6.name) / "rules_crlf_append.txt"
    rpa.write_bytes(b"JUST RULES\r\n")
    quiet(ce.cmd_lessons, p6.read_text(encoding="utf-8"), rpa, True)
    rab = rpa.read_bytes()
    t("lessons CRLF append has no stray CR",
      b"\r\r" not in rab and b"LESSONS LEARNED" in rab)
    rpb = Path(d6.name) / "rules_renumbered.txt"
    rpb.write_bytes(b"OLD RULES\n8) LESSONS LEARNED FROM THE ERROR LOG\n====\nOLD BODY\n")
    quiet(ce.cmd_lessons, p6.read_text(encoding="utf-8"), rpb, True)
    afterb = rpb.read_text(encoding="utf-8")
    t("lessons renumbered header replaced not duplicated",
      afterb.count("LESSONS LEARNED FROM THE ERROR LOG") == 1 and "OLD BODY" not in afterb)
    d8.cleanup()
finally:
    d6.cleanup()# --- commit-message gate (--check-commit) -----------------------------------


def t_checkcommit(tmp, text, msg):
    p = Path(tmp) / "msg.txt"
    p.write_text(msg, encoding="utf-8")
    return quiet(ce.cmd_check_commit, text, p)


d9, p9 = tmp_log(lessons_log())
t("check-commit: no marker blocked",
  t_checkcommit(d9.name, p9.read_text(encoding="utf-8"), "fix stuff\n") == 1)
t("check-commit: logged AREA passes",
  t_checkcommit(d9.name, p9.read_text(encoding="utf-8"),
                "fix webhook (AREA: payment webhook parser)\n") == 0)
t("check-commit: unlogged AREA blocked",
  t_checkcommit(d9.name, p9.read_text(encoding="utf-8"),
                "fix (AREA: never logged thing)\n") == 1)
t("check-commit: LOG: alt marker passes",
  t_checkcommit(d9.name, p9.read_text(encoding="utf-8"),
                "fix importer (LOG: CSV importer crash)\n") == 0)
t("check-commit: case-insensitive AREA passes",
  t_checkcommit(d9.name, p9.read_text(encoding="utf-8"),
                "fix (area: SEARCH API RATE LIMIT)\n") == 0)
t("check-commit: missing msg file blocked",
  quiet(ce.cmd_check_commit, p9.read_text(encoding="utf-8"),
        Path(d9.name) / "nope.txt") == 1)
t("check-commit: internal spaces collapsed like the hook",
  t_checkcommit(d9.name, p9.read_text(encoding="utf-8"),
                "fix (AREA:  payment   webhook parser)\n") == 0)
t("check-commit: GitHub squash-merge (#NN) suffix stripped",
  t_checkcommit(d9.name, p9.read_text(encoding="utf-8"),
                "fix webhook (AREA: payment webhook parser) (#31)\n") == 0)
d9.cleanup()

# --- --init (one-command adoption) ------------------------------------------


def tmp_target():
    d = tempfile.TemporaryDirectory()
    return d, Path(d.name)


dI, tI = tmp_target()
try:
    quiet(ce.cmd_init, tI, False)  # run_tests=False
    for f in ("errors.txt", "rules.txt", "notes.txt"):
        t(f"init creates {f}", (tI / f).exists())
    t("init scaffold validates",
      quiet(ce.cmd_check, (tI / "errors.txt").read_text(encoding="utf-8")) == 0)
    t("init scaffold keeps section-5 template",
      "5) TO ADD A NEW ENTRY" in (tI / "errors.txt").read_text(encoding="utf-8"))
    t("init scaffold has the example entries",
      "EXAMPLE ENTRIES" in (tI / "errors.txt").read_text(encoding="utf-8"))
    t("init scaffold never ships the repo's dev log",
      "CI commit-message gate missing" not in (tI / "errors.txt").read_text(encoding="utf-8"))
    created_err = (tI / "errors.txt").read_text(encoding="utf-8")
    t("init scaffold is compact (single copy, no implicit-concat blowup)",
      len(created_err) < 3000 and len(created_err.splitlines()) < 60)
    t("init scaffold has exactly one section-5 template",
      created_err.count("5) TO ADD A NEW ENTRY") == 1)
    t("init scaffold has exactly one EXAMPLE ENTRIES header",
      created_err.count("EXAMPLE ENTRIES") == 1)
    t("init scaffold bars are full width",
      created_err.splitlines()[0] == "=" * 80)
    quiet(ce.cmd_init, tI, False)
    t("init is idempotent (no new files)",
      sorted(p.name for p in tI.iterdir()) == ["errors.txt", "notes.txt", "rules.txt"])
    (tI / "errors.txt").write_text("USER DATA\n", encoding="utf-8")
    quiet(ce.cmd_init, tI, False)
    t("init never overwrites existing files",
      (tI / "errors.txt").read_text(encoding="utf-8") == "USER DATA\n")
finally:
    dI.cleanup()

# hook installation / backup / skip-without-git
dJ, tJ = tmp_target()
try:
    (tJ / ".git" / "hooks").mkdir(parents=True)
    quiet(ce.cmd_init, tJ, False)
    t("init installs the hook", (tJ / ".git" / "hooks" / "commit-msg").exists())
    t("installed hook has the gate logic",
      "AREA:" in (tJ / ".git" / "hooks" / "commit-msg").read_text(encoding="utf-8"))
    (tJ / ".git" / "hooks" / "commit-msg").write_text("OLD HOOK\n", encoding="utf-8")
    quiet(ce.cmd_init, tJ, False)
    t("init backs up an existing hook",
      (tJ / ".git" / "hooks" / "commit-msg.agent-error-log.bak").exists())
    t("existing hook is replaced",
      (tJ / ".git" / "hooks" / "commit-msg").read_text(encoding="utf-8") != "OLD HOOK\n")
    t("re-init keeps a single backup",
      (tJ / ".git" / "hooks" / "commit-msg.agent-error-log.bak").read_text(encoding="utf-8") == "OLD HOOK\n")
finally:
    dJ.cleanup()

dK, tK = tmp_target()
try:
    quiet(ce.cmd_init, tK, False)
    t("init without git skips the hook and still exits 0",
      not (tK / ".git" / "hooks" / "commit-msg").exists())
finally:
    dK.cleanup()

# .git as a FILE (git worktree / submodule) resolves the gitdir pointer
dW, tW = tmp_target()
try:
    gitdir = tW / "real-gitdir"
    (gitdir / "hooks").mkdir(parents=True)
    (tW / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")
    quiet(ce.cmd_init, tW, False)
    t("init installs the hook when .git is a pointer file (worktree)",
      (gitdir / "hooks" / "commit-msg").exists())
    (tW / ".git").write_text("not a gitdir pointer\n", encoding="utf-8")
    t("init warns cleanly on an unresolvable .git pointer",
      quiet(ce.cmd_init, tW, False) == 0)
finally:
    dW.cleanup()

# --target naming an existing FILE errors out cleanly
dF, tF = tmp_target()
try:
    f = tF / "afile"
    f.write_text("x", encoding="utf-8")
    t("init rejects a file as --target", quiet(ce.cmd_init, f, False) == 1)
finally:
    dF.cleanup()

# fallback scaffolds when only check_errors.py was copied (HERE has no templates)
dL, tL = tmp_target()
try:
    with mock.patch("check_errors.HERE", tL):
        dM, tM = tmp_target()
        try:
            quiet(ce.cmd_init, tM, False)
            t("init falls back to scaffolds when templates missing",
              "5) TO ADD A NEW ENTRY" in (tM / "errors.txt").read_text(encoding="utf-8"))
            t("fallback rules file scaffolded",
              "RULES OF ENGAGEMENT" in (tM / "rules.txt").read_text(encoding="utf-8"))
            t("fallback notes file scaffolded",
              "NOTES" in (tM / "notes.txt").read_text(encoding="utf-8"))
        finally:
            dM.cleanup()
finally:
    dL.cleanup()

# selftest invocation
dN, tN = tmp_target()
try:
    with mock.patch("check_errors.subprocess.run") as mr:
        quiet(ce.cmd_init, tN, True)
        t("init runs the unit-test selftest",
          mr.call_count == 1 and "_test_errors.py" in str(mr.call_args[0][0]))
    with mock.patch("check_errors.subprocess.run") as mr2:
        quiet(ce.cmd_init, tN, False)
        t("init skips the selftest when disabled", mr2.call_count == 0)
finally:
    dN.cleanup()

# --- review-driven robustness: fuzz + edge cases ----------------------------
random.seed(7)
fuzz_parts = []
for i in range(100):
    d = (date(2020, 1, 1) + timedelta(days=i * 3)).isoformat()
    fuzz_parts.append(entry(d, f"area {i}",
                            random.choice(["OPEN", "FIXED", "MITIGATED", "WORKAROUND", "PARTIAL"])))
t("fuzz: 100 random entries validate clean",
  quiet(ce.cmd_check, "\n\n".join(fuzz_parts)) == 0)

dU = tempfile.TemporaryDirectory()
try:
    pU = Path(dU.name) / "errors.txt"
    pU.write_bytes(b"\xef\xbb\xbf" + entry("2026-08-09", "bom file", "OPEN").encode("utf-8"))
    t("BOM-prefixed log parses", len(ce.parse_entries(ce.load(pU))) == 1)
    pU2 = Path(dU.name) / "bad.txt"
    pU2.write_bytes(b"[2026-08-09] AREA: \xff\xfe broken\n"
                    b"  ERROR: x\n  CAUSE: y\n  FIX: z\n  STATUS: OPEN.\n")
    t("invalid UTF-8 bytes never crash the parser",
      len(ce.parse_entries(ce.load(pU2))) == 1)
    t("invalid UTF-8 bytes never crash cmd_check",
      quiet(ce.cmd_check, ce.load(pU2)) == 0)
finally:
    dU.cleanup()

t("status_token strips en-dash too", ce.status_token("OPEN\u2013").upper() == "OPEN")

# Windows console safety: stdin must be UTF-8 too (stdout-only reconfigure
# double-encoded piped unicode on Windows - regression).
t("stdin is reconfigured to utf-8", getattr(sys.stdin, "encoding", "utf-8") == "utf-8")
with mock.patch("check_errors.input", side_effect=["café 7 — dash", "boom", "the cause", "the fix", "OPEN"]):
    du, pu = tmp_log(sample_log())
    try:
        t("add stores unicode as proper utf-8 bytes", quiet(ce.cmd_add, pu.read_text(encoding="utf-8"), pu) == 0)
        raw = pu.read_bytes()
        t("add unicode bytes are single-encoded", b"caf\xc3\xa9 7 \xe2\x80\x94 dash" in raw)
        t("add unicode round-trips as text", "café 7 — dash" in raw.decode("utf-8"))
    finally:
        du.cleanup()

only5 = BAR + "\n5) TO ADD A NEW ENTRY\n" + BAR + "\n"
t("file with only section 5 validates clean", quiet(ce.cmd_check, only5) == 0)

d9b, p9b = tmp_log(lessons_log())
try:
    # the gate and the hooks both take the LAST marker on the first
    # matching line (hooks: grep -m1 + greedy sed) - tests pin the sync.
    t("check-commit: last marker wins, matching the hooks (unlogged LOG later)",
      t_checkcommit(d9b.name, p9b.read_text(encoding="utf-8"),
                    "fix webhook (AREA: payment webhook parser) - see also LOG: never logged thing\n") == 1)
    t("check-commit: last marker wins, matching the hooks (logged LOG later)",
      t_checkcommit(d9b.name, p9b.read_text(encoding="utf-8"),
                    "fix (AREA: never logged thing) - and LOG: payment webhook parser\n") == 0)
finally:
    d9b.cleanup()


# --- L9 regression: concurrent appends never lose an entry -----------------
import queue as _q
import shutil as _sh
import threading as _th
import time as _time


def _concurrent_add_all_survive():
    d = tempfile.mkdtemp()
    try:
        log = Path(d) / "errors.txt"
        log.write_text(sample_log(), encoding="utf-8")
        per_thread = {}
        barrier = _th.Barrier(3)
        results = {}

        def fake_input(prompt="", **kw):
            return per_thread[_th.current_thread().name].get(timeout=10)

        def worker(tag, answers):
            q = _q.Queue()
            for a in answers:
                q.put(a)
            per_thread[_th.current_thread().name] = q
            barrier.wait()
            try:
                # read first, then sleep: both threads hold the SAME stale
                # text before either writes - this makes the old unlocked
                # code lose an entry deterministically, while the locked
                # re-read inside cmd_add still saves both.
                text = log.read_text(encoding="utf-8")
                _time.sleep(0.1)
                results[tag] = ce.cmd_add(text, log)
            except Exception as ex:
                results[tag] = f"EXC {type(ex).__name__}"

        # patch print to a no-op so the threads' 'Logged:' output cannot
        # leak into - or race with - the main thread's stdout (quiet()
        # swaps the GLOBAL sys.stdout and is not thread-safe).
        with mock.patch("check_errors.print", lambda *a, **k: None), \
             mock.patch("check_errors.input", fake_input):
            t1 = _th.Thread(target=worker, args=("A", ["area A", "e", "c", "f", "FIXED"]))
            t2 = _th.Thread(target=worker, args=("B", ["area B", "e", "c", "f", "FIXED"]))
            t1.start(); t2.start()
            barrier.wait()
            t1.join(); t2.join()
        final = log.read_text(encoding="utf-8")
        both = "AREA: area A" in final and "AREA: area B" in final
        lock_gone = not log.with_name(log.name + ".lock").exists()
        return (both and lock_gone
                and results.get("A") == 0 and results.get("B") == 0)
    finally:
        _sh.rmtree(d, ignore_errors=True)


t("L9 concurrent appends lose nothing (both entries + lock cleaned)", _concurrent_add_all_survive())



# --- L10 regression: load() must not crash on a locked/unreadable file ------
def _locked_load_fallback():
    import tempfile
    d = tempfile.mkdtemp()
    try:
        p = Path(d) / "locked.txt"
        p.write_text("content", encoding="utf-8")
        with mock.patch.object(Path, "read_text",
                               side_effect=PermissionError(13, "denied")):
            val = ce.load(p)
            return val == ""
    finally:
        _sh.rmtree(d, ignore_errors=True)


t("L10 locked/unreadable file degrades, never crashes", _locked_load_fallback())

# Real msvcrt lock probe on Windows (skips elsewhere)
def _real_lock_probe():
    try:
        import msvcrt
    except ImportError:
        return True  # non-Windows: portable test above covers it
    import tempfile
    d = tempfile.mkdtemp()
    try:
        p = Path(d) / "locked.txt"
        p.write_text("content", encoding="utf-8")
        fh = open(p, "r+", encoding="utf-8")
        try:
            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                return True  # lock unavailable in this environment
            val = ce.load(p)
            return val == ""
        finally:
            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            fh.close()
    finally:
        _sh.rmtree(d, ignore_errors=True)


t("L10 real locked-file read degrades (Windows msvcrt)", _real_lock_probe())

# --- reviewer-driven: typed entries + exception vocabulary ------------------
t("entries are ErrorEntry dataclasses", isinstance(es[0], ce.ErrorEntry))
t("entry attributes match the dict bridge",
  es[0].tag == es[0]["tag"] and es[0].area == es[0]["area"]
  and es[0].block == es[0]["block"] and es[0].line == es[0]["line"])
t("entry fields/body are the same objects via the bridge",
  es[0]["fields"] is es[0].fields and es[0]["body"] is es[0].body)
t("entry .get() bridge works",
  es[0].get("tag") == es[0]["tag"] and es[0].get("nope", "dflt") == "dflt")
t("exception vocabulary is a real hierarchy",
  issubclass(ce.ValidationError, ce.AgentLogError)
  and issubclass(ce.LockTimeoutError, ce.AgentLogError))

# --- professional packaging: installed-mode defaults guard ---------------
t("default base: in-place file resolves to its own folder",
  ce._default_base(Path("/home/user/project/check_errors.py"))
  == Path("/home/user/project/check_errors.py"))
t("default base: pip-installed module resolves to the cwd",
  ce._default_base(Path("/usr/local/lib/python3.12/site-packages/check_errors.py"))
  == Path.cwd())


# --- corrupt-log detection (family finding #4) ------------------------------
t("corrupt: empty text is not corrupt", not ce.is_corrupt_log(""))
t("corrupt: whitespace-only is not corrupt", not ce.is_corrupt_log("   \n  \n\n"))
t("corrupt: scaffolded-empty log (bars kept) is not corrupt",
  not ce.is_corrupt_log("=" * 40 + "\nEXAMPLE ENTRIES\n" + "=" * 40 + "\n"))
t("corrupt: real entry without bars is not corrupt",
  not ce.is_corrupt_log(entry("2026-08-01", "real", "FIXED")))
t("corrupt: garbage detected", ce.is_corrupt_log("\x00\x01garbage not a log\n\n  FIX: nope\n"))
t("corrupt: plain prose detected", ce.is_corrupt_log("hello world\nthis is not a log\n"))
t("corrupt: binary-ish detected", ce.is_corrupt_log("\x00\x01\x02\xff\nrandom bytes\n"))


def _main_rc(argv):
    old = sys.argv
    sys.argv = argv
    try:
        return ce.main()
    finally:
        sys.argv = old


with tempfile.TemporaryDirectory() as td:
    p = Path(td) / "errors.txt"
    p.write_bytes(b"\x00\x01garbage not a log\n\n  FIX: nope\n")
    rc = _main_rc(["check_errors.py", "--log", str(p)])
t("corrupt log via CLI exits 1 (fail loudly)", rc == 1)
with tempfile.TemporaryDirectory() as td:
    p = Path(td) / "errors.txt"
    p.write_bytes(b"")
    rc = _main_rc(["check_errors.py", "--log", str(p)])
t("empty log via CLI still exits 0 (No entries)", rc == 0)


# --- --version contract (family finding #1) --------------------------------
_ver_out = io.StringIO()
_saved_stdout = sys.stdout
sys.stdout = _ver_out
try:
    _ver_rc = _main_rc(["check_errors.py", "--version"])
finally:
    sys.stdout = _saved_stdout
t("version: flag exits 0", _ver_rc == 0)
t("version: prints module name and version",
  ("check_errors.py " + ce.VERSION) in _ver_out.getvalue())
# true self-sync: read the CHANGELOG at test time (diff-gate contract)
_cl = (Path(__file__).resolve().parent / "CHANGELOG.md").read_text(
    encoding="utf-8")
_first_versioned = next(
    (ln for ln in _cl.splitlines() if ln.startswith("## [") and "Unreleased" not in ln), None)
t("version: CHANGELOG first versioned header matches VERSION",
  _first_versioned is not None and _first_versioned[4:].split("]", 1)[0] == ce.VERSION)
t("version: constant is a semantic version triple",
  len(ce.VERSION.split(".")) == 3)

t("MINIMAL_HOOK: squash-merge (#NN) strip present like git-commitmsg-hook.sh",
  r"\(#[0-9]+\)" in ce.MINIMAL_HOOK)
t("MINIMAL_HOOK: sed chain = greedy + squash-strip + punctuation (3 steps)",
  ce.MINIMAL_HOOK.count("sed -E") == 3 and "tr -s ' '" in ce.MINIMAL_HOOK)

print(f"\nAll {PASS} tests passed.")
