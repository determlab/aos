"""Spec decisions 9 and 10: AOS seats itself as SHAL's Approver, and the two
layers do not overlap. AOS gates by processor identity (grants); SHAL gates by
op risk (actuator/config). A read never stops; a gated op stops unless the
grant's mode says otherwise — and either way the run record says so.
"""
from __future__ import annotations

from datetime import date

import pytest
import shal
from shal.approval import ApprovalRequest
from shal.driver import Driver, op
from shal.errors import ApprovalDenied
from shal.transport import MessageTransport

from aos.approval import ProcessorApprover, install
from aos.record import RunRecord

RUN_DATE = date(2026, 8, 31)
READ_ONLY = {"grant": "grant-001", "mode": "read_only"}


def request(side_effect: str, node_id: str = "cal_personal",
            opname: str = "read_events") -> ApprovalRequest:
    return ApprovalRequest(op=opname, path=f"/services/{node_id}", id=node_id,
                           side_effect=side_effect, params={}, txn="beef")


@pytest.fixture
def record() -> RunRecord:
    return RunRecord.new("daily-calendar-summary", RUN_DATE)


def test_a_read_only_grant_cannot_actuate(record):
    """The MVP's grant says `read_only`. If the blueprint ever reaches for an
    actuator op, identity — not just risk — has to refuse it."""
    approver = ProcessorApprover(record, {"cal_personal.read_events": READ_ONLY})

    assert approver.approve(request("actuator")) is False
    assert approver.approve(request("config")) is False
    assert approver.approve(request("write")) is False


def test_an_ungranted_capability_is_refused_by_default(record):
    approver = ProcessorApprover(record, {})

    assert approver.approve(request("actuator", node_id="robot",
                                    opname="move")) is False


def test_a_matching_mode_approves(record):
    approver = ProcessorApprover(
        record, {"printer.print_page": {"grant": "grant-009", "mode": "read_write"}})

    assert approver.approve(request("write", "printer", "print_page")) is True


def test_every_approval_decision_lands_in_the_run_record(record):
    approver = ProcessorApprover(record, {"cal_personal.read_events": READ_ONLY})

    approver.approve(request("actuator"))

    assert len(record.calls) == 1
    call = record.calls[0]
    assert call["capability"] == "cal_personal.read_events"
    assert call["result"] == "denied-by-approver"
    assert call["shal_txn"] == "beef"
    assert "read_only" in call["error"]


# ---- through SHAL, not around it -------------------------------------------

class _Siren(Driver):
    """A test-local driver with something SHAL actually gates."""

    compatible = "test,siren"
    kind = MessageTransport

    @op("Sound the siren.", side_effect="actuator")
    def sound(self) -> str:
        return "WOO"  # pragma: no cover - the gate must stop us first


SIREN_LAB = {
    "shal_version": 1,
    "root": {"bus": {"driver": "shal,sim-msg", "address": "sim", "children": {
        "siren": {"id": "siren", "driver": "test,siren", "address": "s1"}}}},
}


def test_the_gate_stops_a_gated_op_before_any_io(record):
    """SHAL consults the approver after limits and before the bus. With AOS in
    the seat, a processor holding only a read grant never reaches the device."""
    shal.registry.register(_Siren)

    with shal.load(SIREN_LAB) as hal, install(record, {}):
        reply = hal.call_tool("siren__sound", {})

    assert reply["ok"] is False
    assert reply["rejected"] == "approval"
    assert record.calls[-1]["result"] == "denied-by-approver"


def test_the_previous_approver_is_restored(record):
    shal.registry.register(_Siren)
    before = shal.get_approver()

    with install(record, {}):
        assert isinstance(shal.get_approver(), ProcessorApprover)

    assert shal.get_approver() is before


def test_a_read_never_reaches_the_gate_at_all(record):
    """Decision 10 in one line: the calendar read is `side_effect: none`, so the
    approver is not even consulted — no approval entries on the record."""
    from tests.test_driver import SIM_LAB

    with shal.load(SIM_LAB) as hal, install(record, {}):
        reply = hal.call_tool("cal_personal__read_events",
                              {"date_from": "2026-08-31", "date_to": "2026-08-31"})

    assert reply["ok"] is True
    assert record.calls == []


def test_a_denied_actuation_raises_on_the_raw_path_too():
    """`hal.call_tool` turns the refusal into a structured reply; the direct
    Python path raises. Both go through the same wrapper — there is no way in."""
    shal.registry.register(_Siren)
    record = RunRecord.new("p", RUN_DATE)

    with (shal.load(SIREN_LAB) as hal, install(record, {}),
          pytest.raises(ApprovalDenied)):
        hal.get_device("siren").sound()
