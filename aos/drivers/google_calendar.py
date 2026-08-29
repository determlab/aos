"""determlab,google-calendar — one calendar, one read op.

Modelled on SHAL's ``ti,tmp102``: one class, one ``@op`` read,
``side_effect="none"``. It ships in the *aos* distribution rather than in shal,
and reaches SHAL through the ``shal.drivers`` entry point — the framework never
imports a module named by a config string, so a driver is free to live with the
processor that needs it.

``kind = MessageTransport`` binds it under any message bus: ``shal,http`` for
the real calendar, ``shal,sim-msg`` for the offline twin at the bottom of this
file. Same driver code either way — that is the point of the transport split.

The op is a *read*: ``side_effect="none"`` and ``@idempotent``, so SHAL's
approval interlock does not fire and a transient drop is safely retried once.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from shal import registry
from shal.driver import Driver, idempotent, op
from shal.errors import HopError, LimitError
from shal.log import current_txn
from shal.transport import MessageTransport

_DEFAULT_MAX = 250


@runtime_checkable
class Calendar(Protocol):
    """v1.0.0 — read_events(date_from, date_to) returns the events in an
    inclusive ISO-date window, each as
    ``{title, start, end, date, start_time, end_time, all_day, attendees}``.
    Order is unspecified; sort downstream. Errors: raises shal.HopError on
    transport failure."""

    def read_events(self, date_from: str, date_to: str) -> list[dict]: ...


@registry.register
class GoogleCalendar(Driver, Calendar):
    """A single Google Calendar, read-only."""

    compatible = "determlab,google-calendar"
    kind = MessageTransport
    llm_ready = True

    @property
    def _config(self) -> dict[str, Any]:
        return self.node.spec.get("config") or {}

    @idempotent  # a read: safe to auto-retry across transient drops
    @op("List this calendar's events between two dates, inclusive. Call when you "
        "need what is scheduled on this calendar for a given day or date range.",
        side_effect="none",
        params={"date_from": {"type": "string",
                              "description": "ISO 8601 date, inclusive start"},
                "date_to": {"type": "string",
                            "description": "ISO 8601 date, inclusive end"}})
    def read_events(self, date_from: str, date_to: str) -> list[dict]:
        cfg = self._config
        token = cfg.get("access_token")
        # the window is inclusive of date_to, the API's timeMax is exclusive
        # -> ask up to the start of the following day. Both bounds are parsed
        # before anything is sent, so a malformed date is a structured refusal
        # rather than an exception escaping through call_tool.
        window = self._window(date_from, date_to)
        reply = self.bus.exchange(self.addr, {
            "method": "GET",
            "path": "events",
            "query": {
                **window,
                "singleEvents": "true",   # expand recurrences into real events
                "orderBy": "startTime",   # only legal with singleEvents
                "maxResults": int(cfg.get("max_events", _DEFAULT_MAX)),
            },
            "headers": {"Authorization": f"Bearer {token}"} if token else {},
        })
        if not isinstance(reply, dict) or "items" not in reply:
            raise HopError(
                f"calendar reply carries no 'items' (got "
                f"{sorted(reply)[:5] if isinstance(reply, dict) else type(reply).__name__})",
                path=self.node.path, hop="google-calendar",
                txn=current_txn.get(), delivered="unknown")
        return [_normalize(item) for item in reply["items"]
                if item.get("status") != "cancelled"]

    def _window(self, date_from: str, date_to: str) -> dict[str, str]:
        """The API's timeMin/timeMax for an inclusive ISO-date window.

        Raises ``LimitError`` — SHAL's "rejected, nothing was sent" refusal — on
        a malformed or inverted window. SHAL's ``params`` limits allow only
        numeric/enum keywords, not ``pattern``, so this check lives here; it
        still runs before any bus I/O, which is the property that matters.
        """
        bounds = {}
        for name, value in (("date_from", date_from), ("date_to", date_to)):
            try:
                bounds[name] = date.fromisoformat(str(value))
            except ValueError:
                raise LimitError(
                    f"{name} must be an ISO 8601 date (YYYY-MM-DD), got {value!r}",
                    path=self.node.path, op="read_events",
                    violations=[{"param": name, "value": value,
                                 "expected": "ISO 8601 date"}]) from None
        if bounds["date_to"] < bounds["date_from"]:
            raise LimitError(
                f"date_to {date_to} is before date_from {date_from}",
                path=self.node.path, op="read_events",
                violations=[{"param": "date_to", "value": date_to,
                             "expected": f"on or after {date_from}"}])
        return {
            "timeMin": f"{bounds['date_from'].isoformat()}T00:00:00Z",
            "timeMax": f"{(bounds['date_to'] + timedelta(days=1)).isoformat()}"
                       f"T00:00:00Z",
        }

    @classmethod
    def authoring_meta(cls) -> dict:
        return {
            "address_schema": {
                "type": "string",
                "description": "calendar resource path under the API base",
                "examples": ["calendars/primary"],
            },
            "config_schema": {
                "type": "object",
                "properties": {
                    "access_token": {
                        "type": "string",
                        "description": "OAuth bearer token. Supply as ${ENV} so "
                                       "the secret never sits in the topology.",
                    },
                    "max_events": {"type": "integer", "minimum": 1, "maximum": 2500},
                },
                "additionalProperties": False,
            },
        }


# ---- normalization: API shape -> the capability contract --------------------

def _normalize(item: dict) -> dict:
    """One API event -> the flat, template-ready shape the capability promises.

    Pure: no clock, no locale, no tz database. Google returns an offset-aware
    stamp already expressed in the calendar's own timezone, so the wall-clock
    reading is a slice of that string — nothing to convert.
    """
    start_raw, all_day = _edge(item.get("start") or {})
    end_raw, _ = _edge(item.get("end") or {})
    return {
        "title": item.get("summary") or "(no title)",
        "start": start_raw,
        "end": end_raw,
        "date": start_raw[:10],
        "start_time": "all-day" if all_day else _hhmm(start_raw),
        "end_time": "" if all_day else _hhmm(end_raw),
        "all_day": all_day,
        "attendees": [a.get("email", "") for a in (item.get("attendees") or [])],
    }


def _edge(edge: dict) -> tuple[str, bool]:
    """(stamp, all_day) for one end of an event."""
    if "dateTime" in edge:
        return str(edge["dateTime"]), False
    return str(edge.get("date", "")), True


def _hhmm(stamp: str) -> str:
    try:
        return datetime.fromisoformat(stamp).strftime("%H:%M")
    except ValueError:
        return stamp[11:16]


# ---- offline twin -----------------------------------------------------------
# Registered against `shal,sim-msg` so `lab.sim.yaml` exercises the real driver
# with no network and no credentials. The model answers the same request
# envelope the http bus would have carried.

SAMPLE_ITEMS: list[dict] = [
    {"summary": "Standup", "status": "confirmed",
     "start": {"dateTime": "2026-08-31T09:00:00+03:00"},
     "end": {"dateTime": "2026-08-31T09:15:00+03:00"},
     "attendees": [{"email": "hemipaska@gmail.com"}]},
    {"summary": "Spec review - AOS v0.2", "status": "confirmed",
     "start": {"dateTime": "2026-08-31T11:00:00+03:00"},
     "end": {"dateTime": "2026-08-31T12:00:00+03:00"},
     "attendees": [{"email": "hemipaska@gmail.com"},
                   {"email": "coo@determlab.local"}]},
    {"summary": "Cancelled thing", "status": "cancelled",
     "start": {"dateTime": "2026-08-31T13:00:00+03:00"},
     "end": {"dateTime": "2026-08-31T13:30:00+03:00"}},
    {"summary": "Deep work", "status": "confirmed",
     "start": {"dateTime": "2026-08-31T14:00:00+03:00"},
     "end": {"dateTime": "2026-08-31T16:00:00+03:00"}},
    {"summary": "Out of office", "status": "confirmed",
     "start": {"date": "2026-09-01"}, "end": {"date": "2026-09-02"}},
]


def _sim_items() -> list[dict]:
    """Fixture events. ``AOS_SIM_CALENDAR`` names a JSON file of API-shaped
    items to serve instead; otherwise a fixed sample week."""
    path = os.environ.get("AOS_SIM_CALENDAR")
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return list(SAMPLE_ITEMS)


def _install_sim_model() -> None:
    """Register the sim twin. Best-effort: a shal build without the sim bus
    must not stop the real driver from loading."""
    try:
        from shal.buses.sim_msg import msg_sim_model
    except ImportError:  # pragma: no cover - the sim bus always ships today
        return

    @msg_sim_model(GoogleCalendar.compatible)
    class _SimCalendar:
        """Answers the driver's request envelope with an API-shaped payload."""

        def handle(self, msg: dict) -> dict:
            query = msg.get("query") or {}
            lo = str(query.get("timeMin", ""))[:10]
            hi = str(query.get("timeMax", ""))[:10]  # exclusive, per the API
            items = [i for i in _sim_items()
                     if lo <= _edge(i.get("start") or {})[0][:10] < hi]
            return {"items": items[: int(query.get("maxResults", _DEFAULT_MAX))]}


_install_sim_model()
