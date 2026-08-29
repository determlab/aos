"""AOS as SHAL's Approver (spec decision 9).

Two-layer safety with no overlap (decision 10): AOS gates by *processor
identity* — a grant says who may do what. SHAL gates by *op risk* — it stops
``actuator`` and ``config`` ops pre-I/O for whatever approver is installed.
Plugging the kernel in gives the ``APPROVAL_REQUIRED`` state for free, audited.

The MVP processor only reads, so this approver never fires on the happy path.
It is installed anyway: a processor that later asks for a gated op must find a
policy already in the seat, and the run record must show the refusal.
"""
from __future__ import annotations

from typing import Any

import shal

from aos.record import RunRecord


class ProcessorApprover:
    """Approve a gated SHAL op iff this processor holds a grant whose mode says
    so. The default answer is no — a processor that was granted ``read_only``
    cannot actuate, whatever the blueprint asks for.
    """

    #: grant modes that may answer yes, per SHAL side effect
    ALLOWED_MODES: dict[str, frozenset[str]] = {
        "write": frozenset({"read_write", "write"}),
        "actuator": frozenset({"actuate"}),
        "config": frozenset({"configure"}),
    }

    def __init__(self, record: RunRecord, grants_by_capability: dict[str, dict]) -> None:
        self._record = record
        self._grants = grants_by_capability

    def approve(self, request: Any) -> bool:
        capability = f"{getattr(request, 'id', '') or ''}.{request.op}"
        grant = self._grants.get(capability)
        mode = str((grant or {}).get("mode", ""))
        allowed = mode in self.ALLOWED_MODES.get(request.side_effect, frozenset())
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


def install(record: RunRecord, grants_by_capability: dict[str, dict]):
    """Seat the approver for one run. Returns the context manager SHAL exports,
    so the previous approver is restored afterwards."""
    return shal.approver(ProcessorApprover(record, grants_by_capability))
