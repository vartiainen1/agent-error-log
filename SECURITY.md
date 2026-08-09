# Security Policy

## Reporting a vulnerability

This project is a small, dependency-free workflow tool. Please report
suspected vulnerabilities privately — do **not** open a public issue for
security problems:

- Open a **private advisory**: GitHub → *Security* → *Report a vulnerability*
- Or email the maintainer via the GitHub profile contact info.

You should get an acknowledgement within a few days. Please do not disclose
the issue publicly until it has been addressed.

## Scope & known limitations

- The log-before-fix gate is a **workflow discipline tool, not a security
  boundary**. `git commit --no-verify` bypasses local hooks by design.
- On GitHub-hosted repos the CI `commit-gate` job re-checks every pushed
  commit server-side, where `--no-verify` cannot reach — see the README
  "Known limitation: --no-verify" section for the full layered defense.
- Secrets or credentials must never be written into `errors.txt`,
  `rules.txt`, `notes.txt`, or commit messages — treat all of these as
  public once pushed.

## Supported versions

Security fixes land on `master` and are released per [SemVer](https://semver.org/).
Always use the latest release: https://github.com/vartiainen1/agent-error-log/releases
