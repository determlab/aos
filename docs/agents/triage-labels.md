---
type: agent-context
owner: repo-agent
scope: repo/aos
reviewed: 2026-08-31
---

# Triage labels

**Labels are the loop's only persisted state.** There is no database, no JSON
file, no round counter on disk. The orchestrator keeps the round number in
memory; everything a later run needs to know is written on the issue as a
label. So a label here is not a note — it is a commit point, and mislabelling
an issue changes what the machine does.

Do not invent a parallel state vocabulary.

## The four `agent:*` labels

| Label | Means | Who applies it |
|---|---|---|
| `agent:go` | Queued for the loop. The trigger. | **The founder, and nobody else.** |
| `agent:working` | A run is in flight on this issue. Do not touch it. | The loop |
| `agent:done` | The merge gate was satisfied and auto-merge is armed (or the PR merged). | The loop |
| `agent:needs-human` | Flagged and stopped. A comment always says why. | The loop |

```
(none) --founder--> agent:go --loop picks up--> agent:working
                                                     |
                    PASS + merge gate ok ----------> agent:done
                    hard-stop / no CI gate --------> agent:needs-human (+ comment)
                    rounds exhausted (4) ----------> agent:needs-human (+ draft PR)
```

The swap `agent:go` → `agent:working` happens **before** the branch is created,
so a crashed run leaves a visible, recoverable state rather than a silent one.

### `agent:go` is the human gate

Recorded in `.agent-loop.yml`: *"The founder gate is at the ISSUE: only the
founder applies `agent:go` (decision 2026-07-19)."* An agent may write an
issue, fill the form, argue that it is ready, and label it `ready-for-agent` —
that is a recommendation. It may not apply `agent:go` to its own work or to
anyone else's. This is the single point where a person decides that autonomous
work may start in this repo, and it is worth exactly nothing if an agent can
apply it.

### `agent:working` means hands off

Never pick up an issue already carrying it. If a run died mid-flight the label
is left behind on purpose — it is the signal. Recovery branches fresh from
`main` with an `-r2` / `-r3` suffix and starts at round 1; it never resets or
deletes the dead branch, and any uncommitted pre-crash work is abandoned rather
than merged. Losing a round of work is cheaper than merging a half-reviewed
diff.

### `agent:done` is not always "merged this instant"

With `gh pr merge --auto`, GitHub finishes the merge when required CI turns
green. If CI then fails, the PR simply stays open. The label means *the loop
did its part and armed a gated merge*; the PR is the source of truth for merge
state.

### `agent:needs-human` is terminal

It stays until a person acts: read the comment, then close the issue, open a
follow-up, or re-queue it by adding `agent:go` again. The loop will not clear
its own flag.

## The readiness labels

These are triage vocabulary, not loop state. The loop does not read them; they
tell a human which pile an issue belongs in.

| Label | Means | Who applies it |
|---|---|---|
| `ready-for-agent` | Fully specified: goal, testable acceptance criteria, verification. A candidate for `agent:go`. | Anyone triaging — human or agent |
| `ready-for-human` | Needs a person. Judgement call, an open decision, or a hard-stop path. | Anyone triaging |

`ready-for-agent` is the *proposal*; `agent:go` is the *decision*. Keeping them
as two labels is what lets an agent do triage without being able to start
itself.

Reach for `ready-for-human` when the issue depends on an open decision (O1–O3
in [`docs/DECISIONS.md`](../DECISIONS.md)), when it would touch
`.agent-loop.yml`, or when the work is inside a hard-stop path — the loop would
only flag it back.

## The stock GitHub labels

`bug`, `enhancement`, `documentation`, `question`, `duplicate`, `invalid`,
`wontfix`, `good first issue`, `help wanted` — kind and disposition, applied by
whoever triages. `.github/ISSUE_TEMPLATE/bug.yml` auto-applies `bug` and
`feature.yml` auto-applies `enhancement`; nothing else is applied
automatically. None of them affect the loop.

This repo has no `needs-triage` label. An issue with no `agent:*` and no
readiness label is untriaged.
