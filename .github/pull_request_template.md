## What and why
<!-- Link the issue. One line on the change; the issue carries the detail. -->

Closes #

## Rubric
- [ ] Every issue-rubric item passes, evidence linked
- [ ] Tests cover the change and fail without it

## Kernel invariants
<!-- spec/v0.2.md is the contract. These three are the ones worth breaking a PR over. -->
- [ ] **One door** — every capability call still goes manifest → grant check → driver → run record
- [ ] **Policy by construction** — an ungranted capability still cannot reach the registry, so it fails validation rather than being blocked at call time
- [ ] **`write_run_record` still runs in `finally`** — success, failure and denial all produce a record
- [ ] A public API change, if any, is recorded in `CHANGELOG.md`

## Scope
- [ ] Nothing from spec "Deliberately missing" was added (workflow state, inter-processor events, sandbox, multi-tenant identity)

## Reviewer verdict
<!-- agent-loop: PASS | CHANGES (n) | (flagged). Rounds used: r / max. -->
- **Verdict:**
- **Rounds:**
