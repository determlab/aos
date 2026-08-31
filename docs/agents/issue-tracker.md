---
type: agent-context
owner: repo-agent
scope: repo/aos
reviewed: 2026-08-31
---

# Issue tracker

How work reaches this repo, and what an issue has to say before an agent may
start on it.

- **Tracker:** GitHub Issues on `determlab/aos`, driven by the `gh` CLI.
- **Base branch:** `main`. The loop branches `agent/<issue#>-<slug>` off it
  (`.agent-loop.yml: branch_base`).
- **Linking:** every PR body carries `Closes #<n>`. One issue, one PR.

## An issue is the specification

`.agent-loop.yml` sets `spec_source: issue`. There is no design doc between the
issue and the branch — the issue body *is* the brief the coder works from and
the rubric the reviewer scores against. The loop reads it, and if it does not
find a goal plus **testable acceptance criteria** it refuses the issue, labels
it `agent:needs-human`, and comments what is missing. It will not code against
a guess.

That is what the two forms in `.github/ISSUE_TEMPLATE/` are for. `feature.yml`
asks for goal, binary acceptance checkboxes, verification, constraints, and
out-of-scope; `bug.yml` asks for a reproduction and expected-vs-actual, and
defaults the acceptance criterion to "the repro is now a passing regression
test". Filling either one honestly produces a runnable issue. Writing an issue
freehand usually does not.

Scope one outcome per issue. If the work grows more than ~20% past the stated
scope mid-run, the answer is to stop and re-plan, not to push through.

## Cite decisions by number

The locked decisions are in [`docs/DECISIONS.md`](../DECISIONS.md), numbered
D1–D12 and stable for the life of the product. An issue that touches settled
ground says so — `implements D8`, `supersedes D11` — rather than re-arguing it
in the body. The reviewer loads that ledger as a standards source
(`.agent-loop.yml: review.standards_sources`) and will flag a diff that
contradicts a decision the issue never mentioned.

The ledger's **Open decisions** section (O1–O3) is the other half of that rule.
An issue whose answer depends on an open decision is **not** ready for
`agent:go`; settle the decision first, record it as a new D-number, then queue
the work.

## Who starts a run

Only the founder applies `agent:go` (decision of 2026-07-19, cited in
`.agent-loop.yml`). Anybody — human or agent — may file an issue, fill the form,
and mark it `ready-for-agent`; none of that starts anything. `agent:go` is the
single human gate on autonomous work in this repo, and it is deliberately not
delegable. See [`triage-labels.md`](triage-labels.md) for the full lifecycle.

## Hard stops start at the issue

Before writing code the loop scans the issue itself. If the work it describes
obviously requires a gated change — a new runtime dependency, a schema or data
migration, deleting a file, anything under `.agent-loop.yml: hard_stops.paths`
(the kernel gate, `grants/`, `capabilities/`, `processors/`, `lab.yaml` — but
see #5 below, that key is currently misspelled and the path fences are inert) —
it flags a human immediately rather than burning rounds. Writing "and also touch
`aos/grants.py`" into an issue does not authorize it; the stop is not a
permission the issue can grant.

The loop runs at most `max_rounds: 4` coder/reviewer rounds. Exhausted rounds
produce a draft PR plus `agent:needs-human`, never a merge.

## Open issues (as of 2026-08-31)

| # | Title | State |
|---|---|---|
| [#3](https://github.com/determlab/aos/issues/3) | Enforce grant mode, and gate writes — a `read_only` grant currently executes a write | Open, **blocked**. The mode-validation half is doable now; the second half seats SHAL's gated-effects policy beside the approver and needs determlab/shal#114 first. Cites D8: grants are all-or-nothing today. Latent, not live — no processor declares a write capability yet. |
| [#4](https://github.com/determlab/aos/issues/4) | Adopt doc-standard: decisions exist twice, and both copies are standards sources | Open, `agent:working`, `ready-for-agent`. This document is part of its output. |
| [#5](https://github.com/determlab/aos/issues/5) | `hard_stops.paths` is not a key agent-loop reads — all ten path stops are inert | Open. `.agent-loop.yml` writes `hard_stops.paths:` where agent-loop 0.1.0 reads `hard_stops.protected_paths:`, so every path fence above is currently doing nothing. Only the founder can fix it — `.agent-loop.yml` governs what an agent may change unreviewed, so an agent may not change it. |

Keep this table honest or delete it. A stale list of "current" issues is worse
than no list; check `gh issue list --state open` before trusting it.
