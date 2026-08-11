#!/usr/bin/env python3
"""Family README style drift guard.

Fails if this repo's README drifts from the canonical agent-memory family
contract that the README-consistency audit standardized across the four
repos:

  * H1 title is the lowercase repo-name style      (# agent-<repo>)
  * exactly three companion badges in the header block, linking the three
    sibling repos (each badge's label and link must name the same repo)
  * canonical section tail, in order:
        ## Companion tools
        ## Installing with pip (optional)
        ## Dogfood ledger
        ## License            <- the LAST section; nothing after it
  * ## Development appears before ## Security
  * agent-diff-gate additionally requires ## Security before ## Limits

The guard is identical in all four repos: it derives the repo name from the
folder it lives in, so no per-repo edits are ever needed.

Usage: python _check_readme_style.py [--readme PATH] [--repo NAME]
"""

import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

FAMILY = {"agent-error-log", "agent-decision-log", "agent-log-ai", "agent-diff-gate"}

# The family badge hosts are on the diff-gate R6 allow-list, so declaring
# them here documents the format instead of baking in an endpoint.
BADGE_URL = "https://img.shields.io/badge/"
LINK_URL = "https://github.com/vartiainen1/"

# [![companion-decision](https://img.shields.io/badge/companion-agent--decision--log-2ea44f)](https://github.com/vartiainen1/agent-decision-log)
# The link target is the ground truth (shields.io encodes hyphens as '--' in
# the label, so the label is cosmetic and never compared against the link).
COMPANION_RE = re.compile(
    r"\[!\[companion-[^\]]*\]\(" + re.escape(BADGE_URL) + r"companion-[^)]*\)\]\("
    + re.escape(LINK_URL) + r"([a-z0-9-]+)\)"
)
HEADING_RE = re.compile(r"^##\s+(.+)$")

CANONICAL_TAIL = [
    "Companion tools",
    "Installing with pip (optional)",
    "Dogfood ledger",
    "License",
]


def issues(repo, text):
    """Return a list of human-readable contract violations (empty = OK)."""
    out = []
    lines = text.splitlines()

    # 1. H1 title: lowercase repo-name style.
    h1 = next((ln.strip() for ln in lines if ln.strip()), "")
    if h1 != "# {0}".format(repo):
        out.append("H1 title is {0!r}; expected '# {1}' (lowercase repo-name style)".format(h1, repo))

    # 2. Companion badges: exactly the three siblings, all in the header block.
    headings = [(i, m.group(1).strip())
                for i, ln in enumerate(lines)
                for m in [HEADING_RE.match(ln)] if m]
    header_end = headings[0][0] if headings else len(lines)

    badges = list(COMPANION_RE.finditer(text))
    linked = []
    for m in badges:
        link_slug = m.group(1)
        line_no = text[:m.start()].count("\n") + 1
        if line_no > header_end:
            out.append("line {0}: companion badge must live in the header block (before the first '## ' section)".format(line_no))
        linked.append(link_slug)

    expected = sorted(FAMILY - {repo})
    missing = [s for s in expected if s not in linked]
    extras = [s for s in sorted(set(linked)) if s not in expected]
    dupes = [s for s in sorted(set(linked)) if linked.count(s) > 1]
    if not badges:
        out.append("no companion badges found (expected exactly three)")
    if missing:
        out.append("missing companion badge(s): {0}".format(", ".join(missing)))
    if extras:
        out.append("unexpected companion badge(s): {0}".format(", ".join(extras)))
    if dupes:
        out.append("duplicate companion badge(s): {0}".format(", ".join(dupes)))

    # 3. Canonical section tail + License last.
    names = [n for _, n in headings]
    pos = {name: i for i, name in enumerate(names)}

    for want in CANONICAL_TAIL:
        if want not in pos:
            out.append("missing canonical section '## {0}'".format(want))

    idx = [pos[w] for w in CANONICAL_TAIL if w in pos]
    if idx != sorted(idx):
        out.append("canonical tail out of order: expected " + " -> ".join("'## {0}'".format(w) for w in CANONICAL_TAIL))

    if "License" in pos and pos["License"] != len(headings) - 1:
        last = headings[-1][1] if headings else "?"
        out.append("'## License' must be the LAST section; '{0}' is after it".format(last))
    if "Dogfood ledger" in pos and "License" in pos and pos["License"] - pos["Dogfood ledger"] != 1:
        out.append("'## Dogfood ledger' must be immediately before '## License'")

    # 4. Development before Security (family-wide).
    if "Development" in pos and "Security" in pos and pos["Development"] >= pos["Security"]:
        out.append("'## Development' must appear before '## Security'")

    # 5. diff-gate: Security before Limits.
    if repo == "agent-diff-gate":
        if "Limits" not in pos:
            out.append("agent-diff-gate requires a '## Limits' section after '## Security'")
        elif "Security" in pos and pos["Security"] >= pos["Limits"]:
            out.append("'## Security' must appear before '## Limits'")

    return out


def main():
    ap = argparse.ArgumentParser(description="Family README style drift guard")
    ap.add_argument("--readme", default=str(HERE / "README.md"))
    ap.add_argument("--repo", default=HERE.name)
    args = ap.parse_args()

    text = Path(args.readme).read_text(encoding="utf-8", errors="replace")
    problems = issues(args.repo, text)
    if problems:
        print("drift-guard FAIL ({0} README):".format(args.repo))
        for p in problems:
            print("  - {0}".format(p))
        print("  Fix the README so it matches the family contract (see the README-consistency audit).")
        return 1
    print("drift-guard OK: {0} README matches the family contract "
          "(title, 3 companion badges, canonical tail, Development/Security order).".format(args.repo))
    return 0


if __name__ == "__main__":
    sys.exit(main())
