"""Spec decisions 9 and 10: AOS seats itself as SHAL's Approver, and the two
layers do not overlap. AOS gates by processor identity (grants); SHAL gates by
op risk (actuator/config). A read never stops; a gated op stops unless the
grant's mode says otherwise — and either way the run record says so.
"""
from __future__ import annotations

from datetime import date

import pytest
import shal
import yaml
from shal.approval import ApprovalRequest
from shal.driver import Driver, op
from shal.errors import ApprovalDenied
from shal.transport import MessageTransport

from aos.approval import GATED_EFFECTS, ProcessorApprover, install
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


# ---- writes are gated too (D15), and there is one mode table (D14) ----------

class _Printer(Driver):
    """A test-local driver with a plain `write` op, which SHAL alone never gates."""

    compatible = "test,printer"
    kind = MessageTransport

    @op("Print a page.", side_effect="write")
    def print_page(self) -> str:
        return "printed"


PRINTER_LAB = {
    "shal_version": 1,
    "root": {"bus": {"driver": "shal,sim-msg", "address": "sim", "children": {
        "printer": {"id": "printer", "driver": "test,printer", "address": "p1"}}}},
}


def test_install_seats_the_gated_set_and_the_approver_together(record):
    gated_before, approver_before = shal.get_gated_effects(), shal.get_approver()

    with install(record, {}):
        assert shal.get_gated_effects() == GATED_EFFECTS
        assert isinstance(shal.get_approver(), ProcessorApprover)

    assert shal.get_gated_effects() == gated_before
    assert shal.get_approver() is approver_before


def test_a_read_write_grant_on_a_write_capability_is_asked(tmp_path):
    """Through the single door: the brick is built (mode permits write), and the
    write op reaches the approver instead of running unasked."""
    from aos.capability import make_capability_brick
    from aos.store import Store

    shal.registry.register(_Printer)
    grant = {"grant": "grant-009", "processor": "p", "principal": "user:me",
             "capability": "printer.print_page", "mode": "read_write"}
    (tmp_path / "capabilities").mkdir()
    (tmp_path / "capabilities" / "printer.print_page.yaml").write_text(
        "capability: printer.print_page\nside_effect: write\n", encoding="utf-8")
    (tmp_path / "grants").mkdir()
    (tmp_path / "grants" / "grant-009.yaml").write_text(
        yaml.safe_dump(grant), encoding="utf-8")
    store = Store(root=tmp_path)
    record = RunRecord.new("p", RUN_DATE)

    with shal.load(PRINTER_LAB) as hal, install(record, {"printer.print_page": grant}):
        brick, _ = make_capability_brick(hal, "printer.print_page", grant, record, store)
        brick()

    assert [c["result"] for c in record.calls] == ["approved", "ok"]


def test_the_mode_table_and_shal_agree_on_side_effects():
    """Every effect a mode permits is a SHAL effect, and every SHAL effect is
    permitted by some mode — a fifth SHAL value cannot drift in unseen."""
    from shal.driver import _SIDE_EFFECTS

    from aos.capability import MODE_PERMITS, SIDE_EFFECTS

    permitted = frozenset().union(*MODE_PERMITS.values())
    assert permitted <= _SIDE_EFFECTS
    assert permitted == _SIDE_EFFECTS == SIDE_EFFECTS
