---
name: Bug report
about: Report something that does not work as documented
title: ''
labels: bug
assignees: ''
---

## What happened
<!-- Describe the symptom. -->

## Expected vs actual
- Expected:
- Actual:

## Environment
- OS (Windows / macOS / Linux):
- Python version:
- Git version (if relevant):
- How the tool was adopted: `python check_errors.py --init` / manual copy / other

## Reproduction
<!-- Minimal steps, or paste the failing command + output. -->

## Log the error first (this repo's rule)
Before or with this report, add an entry to `errors.txt`:

```
[YYYY-MM-DD] AREA: <what broke>
  ERROR: <symptom>
  CAUSE: <root cause>
  FIX: <what fixed it>
  STATUS: FIXED.   (or OPEN)
```

Run `python check_errors.py` to validate. See [CONTRIBUTING.md](https://github.com/vartiainen1/agent-error-log/blob/master/CONTRIBUTING.md).
