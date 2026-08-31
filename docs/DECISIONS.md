---
type: ledger
owner: repo-agent
scope: repo/aos
reviewed: 2026-08-31
---

# AOS — Decision Ledger

Locked architectural decisions. **Append; never silently re-litigate.**
Issues cite these by number. Superseding a decision is itself a decision.

D1–D10 were locked in the chat session of 2026-08-29 and are reproduced here
verbatim in claim form; `spec/v0.2.md` §2 carries the reasoning behind each. They
moved out of the spec on 2026-08-30 because a decision number is stable for the
life of the product while `spec/v0.2.md` is a versioned snapshot — leaving
life-of-product identifiers inside a file that `v0.3` supersedes guarantees a
migration later, and doing it now (ten decisions, zero citations) is free.

| # | Decision | Source |
|---|---|---|
| D1 | **Processors, not a general OS** — ship one processor a week and let the spec harden from real use | spec v0.2 §2 |
| D2 | **Kernel = manifests + grants + run records** — everything else is a plugin; ~500 lines | spec v0.2 §2 |
| D3 | **One door** — every capability call goes manifest → grant check → driver → run record; if a processor can skip a step it is a script runner | spec v0.2 §2 |
| D4 | **Determinism boundary** — the kernel is deterministic; all nondeterminism lives inside the executor | spec v0.2 §2 |
| D5 | **Engine = Bricks** — one blueprint per processor, composed once, executed with no LLM in the loop, so zero tokens per run | spec v0.2 §2 |
| D6 | **Driver/Resource layer = SHAL** — the `lab.yaml` topology replaces v0.1's Driver and Resource objects; software and hardware are the same kind of node | spec v0.2 §2 |
| D7 | **Capability naming = SHAL convention** — capability id `<node>.<op>` maps 1:1 onto the SHAL tool name `<node>__<op>` | spec v0.2 §2 |
| D8 | **Policy enforcement = registry construction** — the registry is built from the grants, so an ungranted capability does not exist and validation refuses the blueprint before anything executes | spec v0.2 §2 |
| D9 | **AOS registers as SHAL's Approver** — the kernel supplies the approval-gate policy for actuator/config ops, audited | spec v0.2 §2 |
| D10 | **Two-layer safety, no overlap** — AOS gates by processor identity (grants), SHAL gates by op risk; keep both | spec v0.2 §2 |
| D11 | **Capability contracts use SHAL's `side_effect` vocabulary** (`none\|write\|actuator\|config`), not a three-value `risk:` field — three values cannot express the `{actuator, config}` boundary that decides whether the approver fires | this doc, 2026-08-30 |
| D12 | **AOS ships its own SHAL drivers**, registered through the `shal.drivers` entry point, rather than adding them to the shal repo — a driver belongs with the processor that needs it, and SHAL never imports a module named by a config string | this doc, 2026-08-30 |

## Verification

Whether a decision is true *in the code today* (standard §8 — the gap is the backlog).

- **D8 — confirmed real.** `run_blueprint` validates before executing
  (`bricks/api.py:86`) and validation fails on a brick missing from the registry
  (`bricks/core/validation.py:83`). Both faces are tested here:
  `test_no_grant_is_denied_and_still_audited` and
  `test_ungranted_capability_cannot_exist_as_a_brick`.
- **D9 — needs no new SHAL code.** `set_approver` / `approver` / `get_approver` /
  `CallableApprover` are already exported. Implemented in `aos/approval.py`.
- **D6 — partially blocked.** `shal,http` hardcodes POST with the message as the
  body, so it cannot express a `GET`, query params, or an `Authorization`
  header. That is determlab/shal#104, and it is the whole distance between the
  sim calendar and the real one. `lab.yaml` is written and inert until it lands.
- **D11 — supersedes the `risk: read|write|dangerous` field** shown in
  `spec/v0.2.md` §4.1. That spec text is stale; `capabilities/*.yaml` and
  `aos/capability.py` use SHAL's four values.

## Open decisions

<!-- Named, not yet decided. An issue that needs one of these is NOT ready for agent:go. -->

- **O1 — where the Google Calendar credential comes from.** `lab.yaml` reads
  `${GOOGLE_CALENDAR_TOKEN}` from the environment, which is a placeholder, not a
  decision. Settled by choosing an OAuth flow and where the refresh lives.
  Blocks running against the real calendar alongside D6/shal#104. (spec §7)
- **O2 — what `deliver: push` means.** Today every run writes
  `outputs/<run>.txt` and `push` also prints it. Settled by the first processor
  whose output has a real destination; a SHAL http node is one candidate. (spec §7)
- **O3 — grant storage beyond one principal.** Flat YAML in `grants/` is fine
  for `user:me`. Settled by the first second principal; sqlite is the expected
  answer. (spec §7)

## Superseded

<!-- Keep the history. A decision that is replaced moves here with its replacement. -->

*Nothing yet.* D11 corrects a field in `spec/v0.2.md` §4.1 but does not replace a
numbered decision.
