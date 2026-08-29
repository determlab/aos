"""The run record (spec §4.5) — the fifth artifact, the only one the runtime
writes.

A denial with no audit trail is the one unacceptable outcome, so the engine
writes this in ``finally``: success, failure, and denial all produce a record.

Determinism note: a record needs a wall clock and a unique id, which the rest of
the kernel does not. Both enter here and only here, and both are injectable, so
a test gets a byte-stable record.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class RunRecord:
    """One run, start to finish. Mutable while running, written once at the end."""

    run: str
    processor: str
    run_date: date
    started: datetime
    status: str = "running"
    calls: list[dict[str, Any]] = field(default_factory=list)
    ended: datetime | None = None
    output_ref: str | None = None
    error: str | None = None

    @classmethod
    def new(cls, processor: str, run_date: date, *,
            now: datetime | None = None, run_id: str | None = None) -> RunRecord:
        started = now or _utc_now()
        return cls(
            run=run_id or f"run-{started.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}",
            processor=processor,
            run_date=run_date,
            started=started,
        )

    # -- during the run ---------------------------------------------------
    def add_call(self, capability: str, grant: str, *, shal_txn: str,
                 result: str, error: str | None = None) -> None:
        """One capability call, granted or refused. Appended by the single door
        in :mod:`aos.capability` — nothing else may write here."""
        entry: dict[str, Any] = {"capability": capability, "grant": grant,
                                 "shal_txn": shal_txn, "result": result}
        if error is not None:
            entry["error"] = error
        self.calls.append(entry)

    def finish(self, status: str, *, error: str | None = None,
               output_ref: str | None = None, now: datetime | None = None) -> None:
        self.status = status
        self.error = error
        self.output_ref = output_ref
        self.ended = now or _utc_now()

    # -- serialization ----------------------------------------------------
    def as_dict(self) -> dict[str, Any]:
        return {
            "run": self.run,
            "processor": self.processor,
            "run_date": self.run_date.isoformat(),
            "started": _stamp(self.started),
            "ended": _stamp(self.ended) if self.ended else None,
            "status": self.status,
            "calls": self.calls,
            "output_ref": self.output_ref,
            "error": self.error,
        }


def write_run_record(record: RunRecord, runs_dir: Path) -> Path:
    """Persist one record. Called from ``finally`` — must not raise on a path
    that has not been created yet, and must not care why the run ended."""
    runs_dir.mkdir(parents=True, exist_ok=True)
    path = runs_dir / f"{record.run}.yaml"
    path.write_text(
        yaml.safe_dump(record.as_dict(), sort_keys=False, allow_unicode=True),
        encoding="utf-8")
    return path
