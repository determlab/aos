"""The single door (spec §5, rule 2).

Every capability call goes manifest → grant check → driver → run record. There
is exactly one function that turns a granted capability into something a
blueprint can execute, and it does all four. If a processor could reach a
driver another way this would be a script runner, not a kernel.

Capability id ``<node>.<op>`` maps 1:1 onto the SHAL tool name ``<node>__<op>``
(spec decision 7), and the brick is registered under the SHAL name so a blueprint
step, a run-record entry, and a SHAL txn all say the same word.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date
from typing import Any

from bricks.core.models import BrickMeta

from aos.errors import CapabilityCallError
from aos.grants import require_grant
from aos.record import RunRecord
from aos.store import Store

# SHAL's own vocabulary, not the spec §4.1 three-value one: SHAL has four
# side effects and gates {actuator, config} (CLAUDE.md correction 4). Mapping
# three into four loses the distinction that decides whether the approver fires.
SIDE_EFFECTS = frozenset({"none", "write", "actuator", "config"})


def tool_name(capability_id: str) -> str:
    """``cal_personal.read_events`` -> ``cal_personal__read_events``."""
    node, _, opname = capability_id.partition(".")
    if not node or not opname:
        raise CapabilityCallError(
            f"capability id {capability_id!r} is not '<node>.<op>'")
    return f"{node}__{opname}"


def make_capability_brick(
    hal: Any,
    capability_id: str,
    grant: dict[str, Any],
    record: RunRecord,
    store: Store,
) -> tuple[Callable[..., dict[str, Any]], BrickMeta]:
    """Build the one callable a granted capability is allowed to become.

    The returned brick re-checks the grant on every call. The pre-flight check
    in the engine is what makes a denial fail *fast*; this one is what makes a
    grant revoked mid-run take effect immediately.
    """
    name = tool_name(capability_id)
    contract = store.capability(capability_id)
    side_effect = str(contract.get("side_effect", "none"))
    if side_effect not in SIDE_EFFECTS:
        raise CapabilityCallError(
            f"{capability_id}: side_effect {side_effect!r} is not one of "
            f"{sorted(SIDE_EFFECTS)} — capabilities use SHAL's vocabulary")

    def brick(**kwargs: Any) -> dict[str, Any]:
        # 1. grant — again, at call time
        require_grant(store, record.processor, capability_id, record.run_date)
        # 2. driver — through SHAL, in-process
        with _TxnCapture() as captured:
            reply = hal.call_tool(name, kwargs)
        txn = captured.txn
        # 3. run record — before deciding whether to raise, so a refusal that
        #    stops the run is on the record just as firmly as a success
        if not reply.get("ok"):
            record.add_call(capability_id, grant.get("grant", "?"), shal_txn=txn,
                            result=str(reply.get("rejected") or "error"),
                            error=str(reply.get("error")))
            raise CapabilityCallError(f"{capability_id}: {reply.get('error')}")
        record.add_call(capability_id, grant.get("grant", "?"), shal_txn=txn,
                        result="ok")
        # bricks convention: every brick returns a dict keyed `result`
        return {"result": reply["result"]}

    meta = BrickMeta(
        name=name,
        tags=["aos", "capability", side_effect],
        category="capability",
        destructive=side_effect in ("actuator", "config"),
        idempotent=side_effect == "none",
        description=str(contract.get("description")
                        or f"AOS capability {capability_id} (granted)."),
    )
    return brick, meta


class _TxnCapture(logging.Handler):
    """Read SHAL's txn id off its own log stream for the duration of one call.

    SHAL stamps ``extra['txn']`` on every record and resets the context var when
    the call returns, so the id cannot be read afterwards. Listening is the
    honest way to get it from outside — SHAL is a library that emits structured
    records and leaves handler policy to the application, and here the kernel is
    the application. Spec §6 leverage move 3 (one id flowing AOS → Bricks → SHAL)
    would replace this with a passed-in id; until then, this is the trace.
    """

    _PLACEHOLDER = "----"

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.txn = self._PLACEHOLDER
        self._logger = logging.getLogger("shal")
        self._level: int | None = None
        self._propagate = True

    def emit(self, record: logging.LogRecord) -> None:
        txn = getattr(record, "txn", None)
        if txn and txn != self._PLACEHOLDER:
            self.txn = txn

    def __enter__(self) -> _TxnCapture:
        # Never add or remove a line the application asked for: if it already
        # wants SHAL at DEBUG, just listen alongside. Only when the level has to
        # be forced does propagation go off for the duration, so turning the tap
        # on to read the txn does not also flood the host's log.
        self._level, self._propagate = self._logger.level, self._logger.propagate
        if not self._logger.isEnabledFor(logging.DEBUG):
            self._logger.setLevel(logging.DEBUG)
            self._logger.propagate = False
        self._logger.addHandler(self)
        return self

    def __exit__(self, *exc: object) -> None:
        self._logger.removeHandler(self)
        if self._level is not None:
            self._logger.setLevel(self._level)
        self._logger.propagate = self._propagate


def today_utc() -> date:
    """The kernel's one clock read, kept in a single named place so every other
    module takes the date as an input."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).date()
