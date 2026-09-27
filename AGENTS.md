---
type: agent-guide
owner: repo-agent
scope: repo/aos
reviewed: 2026-09-27
---

# AGENTS.md — using aos

For an agent that wants to *use* aos. Working *on* this repo is `CLAUDE.md`.

## What aos does

aos runs a **processor**: a YAML manifest naming the capabilities it needs, a
blueprint of deterministic steps, and a trigger. It runs a processor only when a
grant file authorizes every capability it requires, and writes a run record for
every run — success, failure or denial.

## Install

From a clone of this repo, in a fresh venv (Python >= 3.10, `git` on PATH):

```
pip install -e ".[dev]"
```

Install editable (`-e`): the CLI reads `processors/`, `grants/`, `capabilities/`
and `blueprints/` from the checkout it was installed from.

## First success

No account, no API key, no config file: the shipped processor reads a simulated
calendar (`lab.sim.yaml`) with no network.

```
aos run daily-calendar-summary --date 2026-08-31
```

The summary goes to stdout; one status line goes to stderr; exit code `0`.

```
2026-08-31 - 3 event(s)
  09:00  Standup
  11:00  Spec review - AOS v0.2
  14:00  Deep work
[success] run-<timestamp>-<id> -> <checkout>/runs/run-<timestamp>-<id>.yaml
```

## How an agent calls it

One CLI, `aos`. No MCP server. **No command takes
`--json`**: output is plain text, and run records are YAML.

| Command | Does | Output |
|---|---|---|
| `aos run <processor> [--date YYYY-MM-DD] [--lab FILE] [-v]` | run one processor once | summary on stdout; `[status] run-id -> path` on stderr |
| `aos processors` | list processor ids | one id per line |
| `aos grants` | list grant ids | one id per line |
| `aos record <run-id>` | print one run record | the record's YAML |

Global flag: `--root DIR` points at another estate (a directory holding
`processors/ grants/ capabilities/ blueprints/`).

Exit codes for `aos run`: `0` success, `2` denied (a required grant is missing,
expired or revoked), `1` failed. Branch on the exit code, then read the record.

## Side effects

- `aos run` always writes `runs/<run-id>.yaml`, including on denial, and on
  success also writes `outputs/<run-id>.txt`.
- Calls outside the process go only through capabilities. Each capability file
  in `capabilities/` declares `side_effect: none | write | actuator | config`;
  `actuator` and `config` ops are stopped before any I/O unless the grant's
  `mode` permits them, and the refusal lands in the run record.
  The shipped capability, `cal_personal.read_events`, is `side_effect: none`.
- `aos processors`, `aos grants` and `aos record` only read.
- Denial is not an error to work around: a missing grant is the policy. Do not
  create or edit files in `grants/` unless your principal told you to.

## Where the contract lives

- [`spec/v0.2.md`](spec/v0.2.md) — the kernel contract: the five artifacts and
  the run loop.
- [`docs/DECISIONS.md`](docs/DECISIONS.md) — the locked decisions (D1...),
  cited by number. On conflict with the spec, the ledger wins.
- [`CHANGELOG.md`](CHANGELOG.md) — the public surface and the known gaps.
