"""AOS as SHAL's Approver (spec decision 9).

Two-layer safety with no overlap (decision 10): AOS gates by *processor
identity* — a grant says who may do what. SHAL gates by *op risk* — it stops
``write``, ``actuator`` and ``config`` ops pre-I/O (the set :func:`install`
seats) for whatever approver is installed.
Plugging the kernel in gives the ``APPROVAL_REQUIRED`` state for free, audited.

The MVP processor only reads, so this approver never fires on the happy path.
It is installed anyway: a processor that later asks for a gated op must find a
policy already in the seat, and the run record must show the refusal.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import shal

from aos.capability import MODE_PERMITS
from aos.record import RunRecord

#: the SHAL side effects that ask the approver while AOS is in the seat (D15).
#: SHAL's own default gates only {actuator, config}; AOS also gates `write`, so
#: a write op reaches the grant's mode instead of running unasked.
GATED_EFFECTS = frozenset({"write", "actuator", "config"})


class ProcessorApprover:
    """Approve a gated SHAL op iff this processor holds a grant whose mode says
    so. The default answer is no — a processor that was granted ``read_only``
    cannot actuate, whatever the blueprint asks for.
    """

    def __init__(self, record: RunRecord, grants_by_capability: dict[str, dict]) -> None:
        self._record = record
        self._grants = grants_by_capability

    def approve(self, request: Any) -> bool:
        capability = f"{getattr(request, 'id', '') or ''}.{request.op}"
        grant = self._grants.get(capability)
        mode = str((grant or {}).get("mode", ""))
        # the one mode table (aos.capability.MODE_PERMITS); unknown mode -> no
        allowed = request.side_effect in MODE_PERMITS.get(mode, frozenset())
        # SHAL audits its own decision; the kernel keeps its own line so one
        # run record answers "what did this processor touch" on its own
        self._record.add_call(
            capability, (grant or {}).get("grant", "-"),
            shal_txn=getattr(request, "txn", "----"),
            result="approved" if allowed else "denied-by-approver",
            error=None if allowed else
            f"grant mode {mode or '(none)'} does not permit a "
            f"{request.side_effect} op")
        return allowed


@contextmanager
def install(record: RunRecord,
            grants_by_capability: dict[str, dict]) -> Iterator[ProcessorApprover]:
    """Seat the gated set and the approver for one run, together (D15): they
    are one policy. SHAL restores the previous set and approver afterwards, and
    its default stays unchanged for everyone else."""
    with (shal.gated_effects(GATED_EFFECTS),
          shal.approver(ProcessorApprover(record, grants_by_capability)) as seated):
        yield seated
