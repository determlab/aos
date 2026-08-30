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
- **The kernel.** `aos.run(processor_id)` runs one processor once and always
  returns a `RunRecord`. Public surface: `run`, `RunRecord`, `Store`,
  `AosError`, `GrantDenied`, `ManifestError`, `CapabilityCallError`.
  - Policy is validation: the brick registry is built from the grants, so an
    ungranted capability does not exist and the blueprint is refused before
    anything executes (spec decision 8).
  - `write_run_record` runs in `finally` — success, failure, and denial all
    produce a record.
  - Grant expiry is judged against the run date, not the clock, so replaying an
    old run sees the authorization that was in force then.
  - AOS installs itself as SHAL's `Approver` for the duration of a run
    (decision 9): a `read_only` grant cannot actuate.
- **`determlab,google-calendar`** SHAL driver plus its `shal,sim-msg` twin,
  registered through the `shal.drivers` entry point. One `@op` read,
  `side_effect="none"`.
- **`daily-calendar-summary`** — manifest, grant, capability contract, blueprint,
  and both topologies. Zero tokens per run.
- `aos` CLI: `run`, `processors`, `grants`, `record`. Exit 2 on a denial.
- Repository scaffolding: CI (lint + test matrix, weekly cron), agent-loop
  config, PR template.
- `spec/v0.2.md` — the kernel contract.
- `CLAUDE.md` — working context: verified sibling-repo facts and known traps.

### Changed
- `[dev]` extra now pins `bricks` by commit and carries `ruff`/`mypy`, so
  `pip install -e ".[dev]"` is one install command identical locally and in CI.
  `bricks` is alpha and not on PyPI; never float the ref (spec §8 step 5).
- CI test matrix covers 3.10-3.13, matching `requires-python`.
- CI runs `ruff check` but not `ruff format --check`. The source is hand-laid
  out in shal's style, which the formatter rewrites wholesale (629 diff lines in
  the kernel alone, at any line length); shal makes the same call.

### Known gaps
- `lab.yaml` (the real calendar) is inert: `shal,http` only POSTs a JSON body
  and the Google events endpoint is a `GET` needing an `Authorization` header —
  determlab/shal#104. The driver already emits the request envelope, so nothing
  here changes when the bus learns it.
- `pluggy` is declared as a direct dependency only because `bricks.core.hooks`
  imports it without declaring it — determlab/bricks#9. Drop it when that ships.
