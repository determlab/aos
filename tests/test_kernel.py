"""The kernel's contract: grants decide, and every run leaves a record."""
from __future__ import annotations

from datetime import date

import pytest
import yaml

import aos
from aos.store import Store
from tests.conftest import CAPABILITY, PROCESSOR, SAMPLE_DATE

RUN_DATE = date.fromisoformat(SAMPLE_DATE)


def run(estate: Store, **kwargs):
    return aos.run(PROCESSOR, root=estate.root, on_date=RUN_DATE, **kwargs)


def record_on_disk(estate: Store, run_id: str) -> dict:
    path = estate.runs / f"{run_id}.yaml"
    assert path.exists(), f"no run record was written at {path}"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


# ---- the one test that matters ---------------------------------------------

def test_no_grant_is_denied_and_still_audited(estate: Store):
    """Spec decision 8. Delete the grant, run, expect `denied` — AND a run
    record written anyway. A denial with no audit trail is the one unacceptable
    outcome."""
    (estate.grants / "grant-001.yaml").unlink()

    record = run(estate)

    assert record.status == "denied"
    on_disk = record_on_disk(estate, record.run)
    assert on_disk["status"] == "denied"
    assert CAPABILITY in on_disk["error"]
    assert on_disk["ended"] is not None


def test_revoked_grant_is_denied(estate: Store):
    _patch_grant(estate, revoked=True)
    assert run(estate).status == "denied"


def test_expired_grant_is_denied(estate: Store):
    """Expiry is judged against the run date, not the wall clock — so a replay
    of an old run sees the authorization that was in force then."""
    _patch_grant(estate, expires="2026-08-30")
    assert run(estate).status == "denied"

    _patch_grant(estate, expires=SAMPLE_DATE)  # expires ON the run date: still valid
    assert run(estate).status == "success"


def test_grant_for_another_processor_does_not_carry(estate: Store):
    _patch_grant(estate, processor="some-other-processor")
    assert run(estate).status == "denied"


def test_ungranted_capability_cannot_exist_as_a_brick(estate: Store):
    """The other face of decision 8: drop the capability from `requires` and the
    brick is never registered, so validation refuses the blueprint *before*
    anything executes. Denied by construction, not by a runtime check."""
    manifest = estate.processors / f"{PROCESSOR}.yaml"
    doc = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    doc["requires"] = []
    manifest.write_text(yaml.safe_dump(doc), encoding="utf-8")

    record = run(estate)

    assert record.status == "denied"
    assert "cal_personal__read_events" in record.error
    assert record.calls == [], "nothing may execute once validation refuses"


def test_a_missing_brick_that_is_not_a_capability_is_a_failure(estate: Store):
    """A typo is not an authorization problem. `denied` must stay meaningful."""
    blueprint = estate.root / "blueprints" / "daily-summary.yaml"
    blueprint.write_text(
        blueprint.read_text(encoding="utf-8").replace("sort_dict_list",
                                                      "sort_dict_lst"),
        encoding="utf-8")

    assert run(estate).status == "failed"


# ---- the happy path ---------------------------------------------------------

def test_success_writes_summary_record_and_output(estate: Store):
    record = run(estate)

    assert record.status == "success", record.error
    on_disk = record_on_disk(estate, record.run)
    assert on_disk["status"] == "success"
    assert on_disk["run_date"] == SAMPLE_DATE

    # every capability call is on the record, with its grant and its SHAL txn
    assert len(on_disk["calls"]) == 1
    call = on_disk["calls"][0]
    assert call["capability"] == CAPABILITY
    assert call["grant"] == "grant-001"
    assert call["result"] == "ok"
    assert call["shal_txn"] not in (None, "", "----"), "trace id must reach the record"

    output = estate.root / on_disk["output_ref"]
    assert output.exists()
    body = output.read_text(encoding="utf-8")
    assert "Standup" in body
    assert "Cancelled thing" not in body, "cancelled events must not be reported"


def test_run_is_deterministic_and_token_free(estate: Store):
    """Same date, same calendar, same bytes — twice. The date is an input, so
    nothing in the blueprint reads a clock."""
    first, second = run(estate), run(estate)

    assert first.status == second.status == "success"
    assert first.run != second.run  # distinct runs...
    body = [(estate.root / r.output_ref).read_text(encoding="utf-8")
            for r in (first, second)]
    assert body[0] == body[1]  # ...identical output


def test_events_are_ordered_and_windowed(estate: Store):
    record = run(estate)
    lines = (estate.root / record.output_ref).read_text(encoding="utf-8").splitlines()

    assert lines[0] == f"{SAMPLE_DATE} - 3 event(s)"
    assert [line.split()[0] for line in lines[1:]] == ["09:00", "11:00", "14:00"]
    assert "Out of office" not in "\n".join(lines), "next day's event is out of window"


def test_a_day_with_nothing_on_it_still_succeeds(estate: Store):
    record = aos.run(PROCESSOR, root=estate.root, on_date=date(2026, 9, 15))

    assert record.status == "success", record.error
    assert (estate.root / record.output_ref).read_text(
        encoding="utf-8").startswith("2026-09-15 - 0 event(s)")


# ---- failures still leave a record ------------------------------------------

def test_unknown_processor_fails_with_a_record(estate: Store):
    record = aos.run("no-such-processor", root=estate.root, on_date=RUN_DATE)

    assert record.status == "failed"
    assert record_on_disk(estate, record.run)["status"] == "failed"


def test_broken_topology_fails_with_a_record(estate: Store):
    (estate.root / "lab.sim.yaml").write_text("shal_version: 1\nroot: {}\n",
                                              encoding="utf-8")
    record = run(estate)

    assert record.status == "failed"
    assert record_on_disk(estate, record.run)["status"] == "failed"


@pytest.mark.parametrize("run_id", ["run-fixed-id"])
def test_run_id_and_clock_are_injectable(estate: Store, run_id: str):
    """The kernel's only nondeterminism is the record's id and timestamps, and
    both enter through one door so a test can pin them."""
    from datetime import datetime, timezone
    moment = datetime(2026, 8, 31, 7, 0, tzinfo=timezone.utc)

    run(estate, now=moment, run_id=run_id)

    on_disk = record_on_disk(estate, run_id)
    assert on_disk["run"] == run_id
    assert on_disk["started"] == "2026-08-31T07:00:00Z"


# ---- mode is enforced at the door (D14) -------------------------------------

def test_a_write_capability_under_a_read_only_grant_is_denied(estate: Store):
    """Before D14 this ran: the grant matched and `mode` was never read. Now the
    brick is refused at construction, so the run is denied before any step."""
    path = estate.capabilities / f"{CAPABILITY}.yaml"
    path.write_text(path.read_text(encoding="utf-8").replace(
        "side_effect: none", "side_effect: write"), encoding="utf-8")

    record = run(estate)

    assert record.status == "denied"
    on_disk = record_on_disk(estate, record.run)
    assert on_disk["status"] == "denied"
    assert "grant-001" in on_disk["error"] and "read_only" in on_disk["error"]
    assert record.calls == [], "nothing may execute"
    assert record.output_ref is None


def test_an_unknown_mode_is_rejected_with_the_file_and_valid_values(estate: Store):
    _patch_grant(estate, mode="admin")

    record = run(estate)

    assert record.status == "failed"
    assert record_on_disk(estate, record.run)["status"] == "failed"
    assert "grant-001" in record.error and str(estate.grants) in record.error
    for mode in ("read_only", "read_write", "actuate", "configure"):
        assert mode in record.error


def test_every_shipped_grant_has_a_valid_mode_that_permits_its_capability():
    """Migration check: the repo's own grants already satisfy D14."""
    from aos.capability import MODE_PERMITS

    store = Store()
    for grant in store.all_grants():
        contract = store.capability(grant["capability"])
        assert grant["mode"] in MODE_PERMITS, grant
        assert contract.get("side_effect", "none") in MODE_PERMITS[grant["mode"]]


def _patch_grant(estate: Store, **changes) -> None:
    path = estate.grants / "grant-001.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    doc.update(changes)
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
