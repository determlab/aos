---
type: charter
owner: repo-agent
scope: repo/aos
reviewed: 2026-08-29
---

> **Type is provisional.** `doc-standard.md` §5 puts the working-context file at
> `docs/agents/context.md` (type `agent-context`); until that move happens this
> file stays at the root and is typed `charter`, the only type whose `HOMES`
> entry covers `CLAUDE.md`.

# AOS — Agent Processor SDK

Read `spec/v0.2.md` first. It is the contract. This file is the working context
around it.

## What you are building

A tiny kernel that runs **processors**. One processor = one capability set + one
trigger + one policy, declared in a YAML manifest. Not a general agent OS — the OS
is supposed to emerge from shipping one processor a week.

MVP: `daily-calendar-summary`. Reads one calendar, writes a morning summary, needs
exactly one revocable read-grant.

**Definition of done:** one manifest, one grant, one blueprint, zero tokens per run,
and an audit record for every run — including denials.

## Sibling repos (already cloned on this machine)

| Path | Role |
|---|---|
| `C:\PlayGround\shal` | SHAL — driver/resource layer. Topology, transports, approval gate |
| `C:\PlayGround\bricks` | Bricks — deterministic execution engine |
| `C:\PlayGround\ops` | determlab company docs (`priorities.md`, `projects/`) |
| `C:\PlayGround\shal-capture` | scratch venv with `pyshal[mcp]` 0.2.1 + a working `bench.yaml` |

All three are determlab's own repos with zero external users, so **API changes are
free**. Don't work around a sibling's rough edge — fix it there.

Git is not on PATH: use `& "$env:ProgramFiles\Git\cmd\git.exe"`.

## Verified facts — do not re-derive these

Checked directly against the repos on 2026-08-29.

**The architecture works.** These are real, not aspirational:

- `run_blueprint` validates *before* executing (`bricks/src/bricks/api.py:86`), and
  validation fails on a brick missing from the registry
  (`bricks/src/bricks/core/validation.py:83`). **This is what makes spec decision 8
  true** — an ungranted capability genuinely cannot execute.
- `build_default_registry` and `run_blueprint` are both exported from `bricks`.
- SHAL exports `set_approver`, `approver`, `get_approver`, `CallableApprover`,
  `Approver` — decision 9 needs no new SHAL code.
- `Hal.tool_schemas()` (`hal.py:70`) and `Hal.call_tool()` (`hal.py:97`) exist.
- SHAL tool names are `<node_id>__<op>` — confirmed on a live bench
  (`rail__output`, `dut_power__write_pin`). The spec's `<node>.<op>` → `<node>__<op>`
  mapping is correct.
- `shal,http` has `kind = None`, so it sits at root and provides `MessageTransport`
  to children. The `lab.yaml` shape in spec §4.2 is right.

**Four things the spec gets wrong or leaves as traps:**

1. `Registry.register` takes **three** args — `register(name, callable_, meta)`
   (`bricks/core/registry.py:22`). The §5 sketch passes two. Every capability brick
   needs a `BrickMeta`.
2. **Bricks does not enforce determinism.** 4 of 101 stdlib bricks read the clock or
   a CSPRNG; guard conditions run through a bare `eval()`
   (`bricks/core/engine.py:346`); no test runs a blueprint twice and compares. The
   MVP blueprint is filter/sort/template so it is deterministic by accident — keep it
   that way on purpose: pass the date in as an input, never call `now_timestamp`
   inside a blueprint.
3. **Bricks will fail to import on a clean venv.** `pluggy` is imported at module
   level but is not a declared runtime dependency (it only arrives via pytest in
   `[dev]`). Either `pip install pluggy` alongside, or fix it in the bricks repo —
   it's their issue #1 and a 10-minute change.
4. **`risk: read|write|dangerous` does not map onto SHAL.** SHAL has four values
   (`none|write|actuator|config`) and gates `{actuator, config}`
   (`shal/driver.py:39,43`). Three-into-four loses the distinction that decides
   whether the approver fires. Use SHAL's vocabulary directly.

**Known broken, but does not block you:** `shal mcp` crashes on MCP ≥2.0
(`shal/mcp/server.py:40`, `AttributeError: 'Server' object has no attribute
'list_tools'`). The kernel calls `hal.call_tool()` in-process, so this path is not on
your critical route. Don't "fix" it as a side quest.

## Ground rules

- **One door.** Every capability call goes manifest → grant check → driver → run
  record. If a processor can skip a step, this is a script runner, not a kernel.
- **`write_run_record` runs in `finally`.** Success, failure, and denial all produce a
  record. A denial with no audit trail is the one unacceptable outcome.
- **The kernel stays deterministic.** All nondeterminism lives inside the executor.
- **Resist scope.** Spec §"Deliberately missing" lists what stays out until a real
  processor forces it: multi-step workflow state, inter-processor events, sandbox
  spec, multi-tenant identity. Adding any of them early is the failure mode.
- Target ~500 lines for the kernel. If it's growing past that, something belongs in a
  plugin.

## Build order

Spec §8. Steps 1–2 are done (this repo exists, spec is committed). Start at step 3:
the `determlab,google-calendar` SHAL driver — one class, one `@op` read with
`side_effect="none"`, modelled on `shal/src/shal/drivers/tmp102.py`.
