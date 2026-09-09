"""The kernel loop (spec §5).

Three rules the code must keep:

1. The blueprint can only see bricks that exist in the registry, and the
   registry is built *from the grants* — so policy is validation. An ungranted
   capability does not exist, ``run_blueprint`` refuses it before executing
   anything, and the run is ``denied`` by construction (decision 8). The
   ordinary bricks come from the manifest's pack allowlist for the same reason
   — see :mod:`aos.packs`.
2. :func:`aos.capability.make_capability_brick` is the single door.
3. ``write_run_record`` runs in ``finally`` — success, failure, and denial all
   produce a record.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

import shal
from bricks import run_blueprint
from bricks.core.exceptions import BlueprintValidationError

from aos import approval
from aos.capability import make_capability_brick, today_utc, tool_name
from aos.errors import GrantDenied
from aos.grants import require_grant
from aos.packs import build_registry
from aos.record import RunRecord, write_run_record
from aos.store import REPO_ROOT, Store

logger = logging.getLogger("aos.engine")

DEFAULT_LAB = "lab.yaml"


def run(processor_id: str, *, root: Path | None = None, lab: str | Path | None = None,
        on_date: date | None = None, now: datetime | None = None,
        run_id: str | None = None) -> RunRecord:
    """Run one processor once. Always returns a record; never raises for a
    denial or a processor-level failure — those *are* the outcome, and the
    record is the report."""
    store = Store(root=Path(root) if root else REPO_ROOT)
    run_date = on_date or today_utc()
    record = RunRecord.new(processor_id, run_date, now=now, run_id=run_id)
    hal = None
    try:
        manifest = store.manifest(processor_id)
        required: list[str] = list(manifest.get("requires") or [])

        # 1. grants — fail fast, before a topology is even loaded
        grants = {cap: require_grant(store, processor_id, cap, run_date)
                  for cap in required}

        # 2. resources — SHAL owns transports, retry, and the write gate
        hal = shal.load(_lab_path(store, manifest, lab))

        # 3. registry — grants become bricks; nothing else can. The pack
        #    allowlist is the other half of that sentence: `bricks` would
        #    otherwise load every installed pack, so installing a package would
        #    grant its bricks. Named packs only — an unnamed one is absent.
        registry = build_registry(store.pack_allowlist(manifest))
        for capability_id, grant in grants.items():
            brick, meta = make_capability_brick(hal, capability_id, grant,
                                                record, store)
            registry.register(tool_name(capability_id), brick, meta)

        # 4. execute — deterministic, zero tokens. The date is an *input*, never
        #    a clock read inside the blueprint (CLAUDE.md correction 2).
        with approval.install(record, grants):
            result = run_blueprint(store.blueprint(manifest),
                                   inputs=_inputs(manifest, run_date),
                                   registry=registry)

        output_ref = deliver(manifest, result.outputs, record, store)
        record.finish("success", output_ref=output_ref)
    except GrantDenied as e:
        record.finish("denied", error=str(e))
    except BlueprintValidationError as e:
        # the other face of decision 8: the blueprint asked for a capability
        # brick that no grant supplied, so validation refused it pre-execution.
        # The detail lives on `.errors`, and it is the detail that names what
        # was refused — a record saying only "1 validation error" audits nothing.
        status = "denied" if _names_a_capability(e, store) else "failed"
        record.finish(status, error="; ".join([str(e), *_details(e)]))
    except Exception as e:  # the record is the report, whatever went wrong
        record.finish("failed", error=f"{type(e).__name__}: {e}")
    finally:
        if hal is not None:
            hal.close()
        path = write_run_record(record, store.runs)  # ALWAYS
        logger.info("%s %s -> %s (%s)", record.run, processor_id, record.status,
                    path)
    return record


def deliver(manifest: dict[str, Any], outputs: dict[str, Any],
            record: RunRecord, store: Store) -> str:
    """Write the output and hand it over.

    Spec §7 parks "what is push?". Until a processor forces the answer, every
    run writes ``outputs/<run>.txt`` — that file *is* the ``output_ref`` the run
    record points at — and ``deliver: push`` additionally prints it. Making the
    file unconditional keeps the audit trail complete whatever delivery becomes.
    """
    spec = manifest.get("output") or {}
    body = outputs.get("summary")
    if body is None:  # no named summary: fall back to the whole output map
        body = "\n".join(f"{k}: {v}" for k, v in sorted(outputs.items()))
    store.outputs.mkdir(parents=True, exist_ok=True)
    path = store.outputs / f"{record.run}.txt"
    path.write_text(str(body), encoding="utf-8")
    if spec.get("deliver") == "push":
        print(body)
    # posix separators: a run record is read on whatever machine reviews it
    return (path.relative_to(store.root).as_posix()
            if path.is_relative_to(store.root) else path.as_posix())


def _inputs(manifest: dict[str, Any], run_date: date) -> dict[str, Any]:
    """Blueprint inputs. ``date`` is supplied by the kernel; anything under the
    manifest's ``inputs:`` is a literal the processor pins."""
    return {"date": run_date.isoformat(), **(manifest.get("inputs") or {})}


def _lab_path(store: Store, manifest: dict[str, Any],
              override: str | Path | None) -> Path:
    return store.root / str(override or manifest.get("lab") or DEFAULT_LAB)


def _details(error: BlueprintValidationError) -> list[str]:
    """The per-error detail bricks keeps beside the summary message."""
    return [str(item) for item in (getattr(error, "errors", None) or [])]


def _names_a_capability(error: BlueprintValidationError, store: Store) -> bool:
    """Did validation fail because a *capability* brick was missing?

    Answered against the declared capability catalog rather than by pattern
    matching, so a plain typo in a blueprint stays a ``failed`` run and only a
    real authorization gap reads as ``denied``.
    """
    text = " ".join(_details(error) or [str(error)])
    return any(f"'{tool_name(cap)}'" in text for cap in store.capability_ids())
