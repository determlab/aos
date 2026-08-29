"""A whole AOS estate in a tmp dir, copied from the repo's real artifacts.

Tests mutate grants, so they must never touch the repo's own `grants/`.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from aos.store import REPO_ROOT, Store

ESTATE = ("capabilities", "grants", "processors", "blueprints")
TOPOLOGIES = ("lab.sim.yaml", "lab.yaml")

PROCESSOR = "daily-calendar-summary"
CAPABILITY = "cal_personal.read_events"
# a date the sample calendar in aos/drivers/google_calendar.py has events on
SAMPLE_DATE = "2026-08-31"


@pytest.fixture
def estate(tmp_path: Path) -> Store:
    for name in ESTATE:
        shutil.copytree(REPO_ROOT / name, tmp_path / name)
    for name in TOPOLOGIES:
        shutil.copy(REPO_ROOT / name, tmp_path / name)
    return Store(root=tmp_path)
