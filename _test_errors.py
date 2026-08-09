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

print(f"\nAll {PASS} tests passed.")
