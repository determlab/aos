---
type: readme
owner: CMO
scope: repo/aos
reviewed: 2026-08-29
---

# AOS — Agent Processor SDK

A tiny kernel that runs **processors**. One processor = one capability set + one
trigger + one policy, declared in a YAML manifest. The contract is
[`spec/v0.2.md`](spec/v0.2.md).

The MVP processor is `daily-calendar-summary`: it reads one calendar, writes a
morning summary, and needs exactly one revocable read-grant.

```
$ aos run daily-calendar-summary --date 2026-08-31
2026-08-31 - 3 event(s)
  09:00  Standup
  11:00  Spec review - AOS v0.2
  14:00  Deep work
```

## One door

Every capability call goes **manifest → grant check → driver → run record**.

```
processors/daily-calendar-summary.yaml    what it is allowed to want
grants/grant-001.yaml                     who authorized it, until when
blueprints/daily-summary.yaml             what it does, deterministically
lab.sim.yaml / lab.yaml                   how it reaches the calendar (SHAL)
runs/run-*.yaml                           what happened — written every time
```

The kernel is `aos/`: ~500 lines of manifests, grants, and run records.
Everything else is a plugin. [`bricks`](../bricks) is the engine,
[`shal`](../shal) is the driver layer.

## Policy is validation, not an `if`

Per run, the brick registry is built **from the grants** — only a granted
capability becomes a brick. An ungranted capability therefore does not exist,
`run_blueprint` refuses the blueprint before executing a single step, and the run
comes back `denied`. Denial by construction (spec decision 8).

```
$ rm grants/grant-001.yaml
$ aos run daily-calendar-summary --date 2026-08-31 ; echo "exit $?"
[denied] run-20260829T113234-4c840f -> runs/run-20260829T113234-4c840f.yaml
daily-calendar-summary is not granted cal_personal.read_events on 2026-08-31
exit 2
```

The record is still written. `write_run_record` runs in `finally`: success,
failure, and denial all produce one. A denial with no audit trail is the single
unacceptable outcome.

## Determinism

Zero tokens per run — no LLM is in the loop. The blueprint is
filter → sort → template, and the run date arrives as a blueprint **input**, so
the same date and the same calendar produce the same bytes. Nothing under
`blueprints/` may read a clock (`bricks` does not enforce this; the blueprint
does it on purpose). The kernel's only nondeterminism is the run id and the
record's timestamps, and both are injectable so a test can pin them.

## Two layers of safety, no overlap

* **AOS gates by processor identity.** A grant says who may do what, and expiry
  is judged against the *run date*, so replaying an old run sees the
  authorization that was in force then.
* **SHAL gates by op risk.** It stops `actuator` and `config` ops pre-I/O for
  whatever `Approver` is installed; AOS installs one for the duration of a run.

Capability contracts use SHAL's four-value `side_effect`
(`none | write | actuator | config`), not the spec §4.1 three-value `risk`.
Folding three into four loses the distinction that decides whether the approver
fires.

## Layout

| Path | What |
|---|---|
| `aos/engine.py` | the run loop — grants, registry, execute, record |
| `aos/capability.py` | the single door: grant + audit + `hal.call_tool` |
| `aos/grants.py` | the runtime rule, no exceptions |
| `aos/record.py` | the run record, written in `finally` |
| `aos/approval.py` | AOS as SHAL's `Approver` |
| `aos/store.py` | the four hand-written artifacts on disk |
| `aos/drivers/google_calendar.py` | `determlab,google-calendar` + its sim twin |

## Install

`bricks` is alpha and not on PyPI, so install it from a **pinned** checkout
alongside this package. `pluggy` has to be asked for by name: `bricks.core.hooks`
imports it at module level but does not declare it as a runtime dependency.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ..\shal -e ..\bricks -e . pytest
.venv\Scripts\python -m pytest
```

## Status

Green end-to-end against `lab.sim.yaml`, which needs no network and no
credentials — the sim twin ships beside the driver, so the *same* driver code
runs in both topologies.

**`lab.yaml` (the real calendar) does not work yet**, for one reason:
`shal,http` only POSTs the whole message as a JSON body, and the Google Calendar
events endpoint is a `GET` that needs an `Authorization` header. The driver
already emits a `{method, path, query, headers}` request envelope; the bus needs
to understand it. That is a change in the `shal` repo. Also parked (spec §7):
where `${GOOGLE_CALENDAR_TOKEN}` comes from — the OAuth flow is not solved.

Until then the cron line (spec §8 step 9) would summarize the sim calendar, not
the real one.
