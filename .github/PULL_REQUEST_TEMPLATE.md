## What this PR does
<!-- One or two sentences. -->

## Log-before-fix (required by this repo's gate)
This change fixes a logged error:

- [ ] `errors.txt` entry exists for the AREA named below (add one if not)
- [ ] Commit/PR title carries the marker, e.g. `fix: ... (AREA: <what broke>)`

```
AREA: <what broke>
```

## Checklist
- [ ] `python _test_errors.py` passes (all tests)
- [ ] `python check_errors.py` reports 0 errors / 0 warnings
- [ ] `sh -n` passes on any changed shell hooks
- [ ] CHANGELOG updated under `[Unreleased]` if user-facing

See [CONTRIBUTING.md](https://github.com/vartiainen1/agent-error-log/blob/master/CONTRIBUTING.md) for the full flow.
