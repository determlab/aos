# Changelog

All notable changes are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning is
[SemVer](https://semver.org/spec/v2.0.0.html).

Pre-1.0: the public API may change in a minor release. `.agent-loop.yml` sets
`flag_on_public_api_change: false` on that basis and the reviewer verifies an
entry here instead, so an in-rubric change to the public surface must be
recorded below.

## [Unreleased]

### Added
- Repository scaffolding: CI (lint + test matrix on 3.11-3.13, weekly cron),
  agent-loop config, PR template.
- `spec/v0.2.md` — the kernel contract.
- `CLAUDE.md` — working context: verified sibling-repo facts and known traps.
