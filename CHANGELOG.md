---
type: changelog
owner: repo-agent
scope: repo/aos
reviewed: 2026-08-31
---

# Changelog

All notable changes are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning is
[SemVer](https://semver.org/spec/v2.0.0.html).

Pre-1.0: the public API may change in a minor release. `.agent-loop.yml` sets
`flag_on_public_api_change: false` on that basis and the reviewer verifies an
entry here instead, so an in-rubric change to the public surface must be
recorded below.

## [Unreleased]

### Fixed
- **The calendar driver broke on pyshal 0.3.0.** A request envelope's reply is
  now `{status, headers, json | text}` (shal#104), not the bare body.
  `determlab,google-calendar` reads the events from `reply["json"]` and refuses
  a reply with no 2xx `status` or no JSON `items` with a `HopError`. The pyshal
  pin is raised to `>=0.3.0` so an install cannot pair this driver with the old
  reply shape. (#13)
- **An installed brick pack was a granted capability.** The kernel called
  `bricks.build_default_registry()`, which loads *every* `bricks.packs` entry
  point — so `pip install <io-pack>` would have added world-touching bricks to
  a processor's registry with no grant, no capability contract and no run
  record. The registry is now built by `aos.packs.build_registry()` from an
  explicit `packs:` allowlist in the processor manifest. **D13**, extending D8
  to the bricks the kernel did not write. (#8, eval row aos E2)
  - A pack that is installed but not named is **absent** from the registry, the
    same mechanism that makes an ungranted capability not exist. There is no
    call-time check: a check can be forgotten on one path, absence cannot.
  - Omitting `packs:` is an error, not an empty allowlist. A kernel that
    quietly built an empty registry would deny everything, and "denies
    everything" is indistinguishable from a gate working — so it raises
    `PackAllowlistError` and the run is a loud `failed`, never a plausible
    `denied`. So is naming a pack that is not installed: skipping it would
    silently turn a processor into a different processor.
  - The DSL builtins (`__for_each__`, `__branch__`) come from the engine, not
    from a pack, and are still always registered.
  - Public surface: `PackAllowlistError` is exported from `aos`.
    `processors/daily-calendar-summary.yaml` gains `packs: [stdlib]`; every
    manifest now needs one.
- **The kernel path fences were inert.** `.agent-loop.yml` declared the stop list
  under `hard_stops.paths:`, which agent-loop reads nothing from — the key is
  `hard_stops.protected_paths:`. All ten entries, including `grants/**` and
  `aos/capability.py`, fenced nothing from the day they were written. Renamed;
  the list itself was correct and is unchanged. (#5)
  - `.agent-loop.yml` now fences itself. It defines what counts as routine work,
    and a system where routine work can redefine "routine" has no third layer.
  - `**/.env*` carries a `not-yet:` marker: it is gitignored, so it can only ever
    match through `git add -f` — the act it exists to stop.
  - Dropped `review.spec_source`, retired in agent-loop 0.2.0.
  - Corrected two stale claims in the same file: `agent:go` became a ladder on
    2026-09-01, and auto-merge is **not** armed here — `main` is unprotected, so
    every PR merges by hand.

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

- `docs/DECISIONS.md` — the decision ledger (ops decision-ledger-standard v1.0).
  D1-D10 are spec §2's locked decisions, moved out of a version-scoped file so
  the numbers are stable for the life of the product. Adds **D11** (capability
  contracts use SHAL's four `side_effect` values, superseding the `risk:` field
  still shown in spec §4.1) and **D12** (AOS ships its own SHAL drivers via the
  `shal.drivers` entry point). Registered in `.agent-loop.yml`.

- `docs/agents/issue-tracker.md` and `docs/agents/triage-labels.md` — how work
  reaches this repo and what each label does. The issue body is the spec —
  there is no design doc between an issue and its branch — issues cite decisions
  by number, and only the founder applies `agent:go`.
- `.github/ISSUE_TEMPLATE/bug.yml` and `feature.yml` — the agent-ready forms,
  adapted from shal. Both now ask which decisions the work cites, and default
  the acceptance checkboxes to commands anyone can run.

### Changed
- **Adopted `ops/doc-standard.md` v1.0.** `README.md` (readme/CMO),
  `CHANGELOG.md` (changelog/repo-agent), `docs/DECISIONS.md` (ledger/repo-agent),
  `spec/v0.2.md` (spec/CTO) and `CLAUDE.md` (charter/repo-agent) declare
  front-matter, and `tools/doc-check.py` passes. `reviewed` is each file's last
  substantive date, not today's: the spec and `CLAUDE.md` still read 2026-08-29.
  `CLAUDE.md`'s `charter` type is provisional — the standard puts the working
  context at `docs/agents/context.md`, and that move is deferred because it
  changes what every session in this repo loads at startup.
- **`spec/v0.2.md` §2 no longer restates D1–D10.** It points at
  `docs/DECISIONS.md` and keeps only the reasoning a one-line ledger claim
  cannot hold. Both files were `review.standards_sources`, so two copies of the
  same ten claims meant the reviewer read the drift as agreement — §4.1's
  `risk:` field had already gone stale against D11. The ledger is now the only
  place a decision is stated.
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
