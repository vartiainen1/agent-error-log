#!/usr/bin/env python3
"""README test-count drift guard.

Fails if the number of tests reported by the suite does not match every
test-count stated in the README. Prevents the stale-count bug (the README
once said 90 while the suite had 117) from ever landing again.

Usage: python _check_readme_count.py [--test PATH] [--readme PATH]
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_TEST = HERE / "_test_errors.py"


def suite_count(test_py):
    out = subprocess.run([sys.executable, str(test_py)],
                         capture_output=True, text=True)
    m = re.search(r"All (\d+) tests passed", out.stdout)
    if not m:
        sys.stderr.write(
            f"drift-guard: could not parse the suite result from {test_py}\n")
        sys.exit(1)
    return int(m.group(1))


def stated_counts(readme_text):
    """Every test-count the README states, from its count-carrying idioms."""
    counts = []
    for m in re.finditer(r"all\s+(\d+)\s+should pass", readme_text, re.IGNORECASE):
        counts.append(int(m.group(1)))
    for m in re.finditer(r"\((\d+),\s*100%\s*pass expected\)", readme_text):
        counts.append(int(m.group(1)))
    for m in re.finditer(r"(\d+)\s+(?:unit\s+)?tests?\b", readme_text):
        counts.append(int(m.group(1)))
    return counts


def main():
    ap = argparse.ArgumentParser(description="README test-count drift guard")
    ap.add_argument("--test", default=str(DEFAULT_TEST))
    ap.add_argument("--readme", default=str(HERE / "README.md"))
    args = ap.parse_args()

    actual = suite_count(Path(args.test))
    text = Path(args.readme).read_text(encoding="utf-8", errors="replace")
    stated = stated_counts(text)
    if not stated:
        print("drift-guard FAIL: README states no test count - state it explicitly.")
        return 1
    bad = [n for n in stated if n != actual]
    if bad:
        print(f"drift-guard FAIL: README states {bad} but the suite reports {actual}.")
        print("  Added tests? Update every README count in the SAME commit.")
        return 1
    print(f"drift-guard OK: README states {actual} tests, matches the suite.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
