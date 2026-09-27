"""The determlab,google-calendar driver, through SHAL rather than around it."""
from __future__ import annotations

import json

import pytest
import shal

from aos.drivers.google_calendar import GoogleCalendar, _normalize

SIM_LAB = {
    "shal_version": 1,
    "root": {"services": {"driver": "shal,sim-msg", "address": "sim", "children": {
        "cal": {"id": "cal_personal", "driver": "determlab,google-calendar",
                "address": "calendars/primary"}}}},
}


@pytest.fixture
def hal():
    with shal.load(SIM_LAB) as h:
        yield h


def test_the_op_is_a_read_so_the_approval_gate_never_fires(hal):
    """SHAL gates {actuator, config}. A calendar read must advertise `none`, or
    the morning summary would stop for a human every day."""
    entry = next(t for t in hal.tool_catalog() if t["name"] == "cal_personal__read_events")

    assert entry["side_effect"] == "none"
    assert entry["idempotent"] is True
    assert entry["annotations"]["readOnlyHint"] is True
    assert entry["annotations"]["destructiveHint"] is False


def test_tool_name_matches_the_capability_id(hal):
    """Spec decision 7: `<node>.<op>` maps 1:1 onto `<node>__<op>`."""
    assert "cal_personal__read_events" in {t["name"] for t in hal.tool_schemas()}


def test_read_events_windows_orders_and_drops_cancelled(hal):
    reply = hal.call_tool("cal_personal__read_events",
                          {"date_from": "2026-08-31", "date_to": "2026-08-31"})

    assert reply["ok"], reply
    titles = [e["title"] for e in reply["result"]]
    assert titles == ["Standup", "Spec review - AOS v0.2", "Deep work"]
    assert all(e["date"] == "2026-08-31" for e in reply["result"])


def test_the_window_is_inclusive_of_both_ends(hal):
    reply = hal.call_tool("cal_personal__read_events",
                          {"date_from": "2026-08-31", "date_to": "2026-09-01"})

    assert [e["date"] for e in reply["result"]][-1] == "2026-09-01"


def test_a_malformed_date_never_reaches_the_bus(hal):
    reply = hal.call_tool("cal_personal__read_events",
                          {"date_from": "not-a-date", "date_to": "2026-08-31"})
    assert reply["ok"] is False


def test_a_custom_calendar_can_be_simulated(hal, tmp_path, monkeypatch):
    fixture = tmp_path / "events.json"
    fixture.write_text(json.dumps([
        {"summary": "Only thing", "status": "confirmed",
         "start": {"dateTime": "2026-10-05T08:30:00+03:00"},
         "end": {"dateTime": "2026-10-05T09:00:00+03:00"}}]), encoding="utf-8")
    monkeypatch.setenv("AOS_SIM_CALENDAR", str(fixture))

    reply = hal.call_tool("cal_personal__read_events",
                          {"date_from": "2026-10-05", "date_to": "2026-10-05"})

    assert [e["title"] for e in reply["result"]] == ["Only thing"]
    assert reply["result"][0]["start_time"] == "08:30"


# ---- the shal,http envelope reply (pyshal >= 0.3.0, shal#104) ----------------

@pytest.mark.parametrize(("bus_reply", "said"), [
    ({"status": 503, "headers": {}, "json": {"items": []}}, "HTTP 503"),
    ({"headers": {}, "json": {"items": []}}, "no HTTP status"),
    ({"status": 200, "headers": {}, "text": "<html>login</html>"}, "no 'items'"),
    ({"items": []}, "no HTTP status"),  # the pre-0.3.0 bare body
])
def test_a_reply_that_is_not_a_2xx_json_calendar_is_refused(hal, monkeypatch,
                                                            bus_reply, said):
    """The bus answers ``{status, headers, json | text}``. Both SHAL buses
    already raise on non-2xx; the driver still checks, so a looser bus cannot
    hand it an error page as an empty calendar."""
    bus = hal.get_device("cal_personal").bus
    monkeypatch.setattr(bus, "exchange", lambda addr, msg: bus_reply)

    reply = hal.call_tool("cal_personal__read_events",
                          {"date_from": "2026-08-31", "date_to": "2026-08-31"})

    assert reply["ok"] is False
    assert said in str(reply["error"])


# ---- normalization is pure --------------------------------------------------

def test_normalize_reads_local_wall_clock_without_a_tz_database():
    """Google returns the stamp already in the calendar's timezone, so the
    displayed time is a slice of the string — no zoneinfo, no clock."""
    event = _normalize({"summary": "Standup",
                        "start": {"dateTime": "2026-08-31T09:00:00+03:00"},
                        "end": {"dateTime": "2026-08-31T09:15:00+03:00"},
                        "attendees": [{"email": "a@b.c"}]})

    assert event["start_time"] == "09:00"
    assert event["end_time"] == "09:15"
    assert event["date"] == "2026-08-31"
    assert event["all_day"] is False
    assert event["attendees"] == ["a@b.c"]


def test_normalize_handles_all_day_and_untitled_events():
    event = _normalize({"start": {"date": "2026-09-01"},
                        "end": {"date": "2026-09-02"}})

    assert event["all_day"] is True
    assert event["start_time"] == "all-day"
    assert event["title"] == "(no title)"
    assert event["attendees"] == []


def test_the_driver_declares_its_authoring_schema():
    meta = GoogleCalendar.authoring_meta()

    assert meta["address_schema"]["examples"] == ["calendars/primary"]
    assert "access_token" in meta["config_schema"]["properties"]
