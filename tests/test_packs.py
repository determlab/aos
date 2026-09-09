"""Installing a brick pack must not grant it (decisions 3 and 8).

A pack that is installed but not named in the manifest is *absent* from the
registry the kernel builds — not refused at call time. These tests install a
fake pack the only way that proves anything: through a real ``bricks.packs``
entry point, exactly as ``pip install`` would.
"""
from __future__ import annotations

import importlib.metadata
import sys
import types
from datetime import date

import pytest
import yaml
from bricks.core.exceptions import BrickNotFoundError
from bricks.core.models import BrickMeta
from bricks.core.registry import BrickRegistry

import aos
from aos.errors import PackAllowlistError
from aos.packs import build_registry
from aos.store import Store
from tests.conftest import PROCESSOR, SAMPLE_DATE

RUN_DATE = date.fromisoformat(SAMPLE_DATE)

#: What a pack that touches the world would look like, named as a pack that is
#: plausibly installed alongside AOS (cf. bricks#2: bricks-files, bricks-http).
EVIL_PACK = "files"
EVIL_BRICK = "delete_tree"
EVIL_MODULE = "tests_fake_io_pack"
#: A second distribution claiming the *same* pack name — the squatting case.
RIVAL_MODULE = "tests_fake_rival_pack"


def _install(monkeypatch: pytest.MonkeyPatch, *modules: str) -> None:
    """`pip install`, simulated at the entry point layer: every module in
    *modules* publishes a `bricks.packs` entry point named EVIL_PACK."""
    fakes = []
    for module_name in modules:
        module = types.ModuleType(module_name)

        def register(registry: BrickRegistry) -> None:  # bricks' pack protocol
            registry.register(EVIL_BRICK, lambda **kw: {"result": "boom"},
                              BrickMeta(name=EVIL_BRICK, description="world-touching"))

        module.register = register  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, module_name, module)
        fakes.append(importlib.metadata.EntryPoint(
            name=EVIL_PACK, value=module_name, group="bricks.packs"))

    real = importlib.metadata.entry_points

    def entry_points(**kwargs):
        found = list(real(**kwargs))
        return [*found, *fakes] if kwargs.get("group") == "bricks.packs" else found

    monkeypatch.setattr(importlib.metadata, "entry_points", entry_points)


@pytest.fixture
def installed_evil_pack(monkeypatch: pytest.MonkeyPatch) -> None:
    """`pip install bricks-files`, simulated at the entry point layer."""
    _install(monkeypatch, EVIL_MODULE)


@pytest.fixture
def evil_pack_installed_twice(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two distributions both publishing a `bricks.packs` pack named `files`."""
    _install(monkeypatch, EVIL_MODULE, RIVAL_MODULE)


# ---- absence is the mechanism ----------------------------------------------

def test_an_installed_pack_is_absent_unless_allowlisted(installed_evil_pack: None):
    """The defect this closes: `bricks.build_default_registry()` loads every
    installed pack, so installation would be authorization."""
    registry = build_registry(["stdlib"])

    with pytest.raises(BrickNotFoundError):
        registry.get(EVIL_BRICK)
    assert EVIL_BRICK not in dict(registry.list_all())
    registry.get("sort_dict_list")  # the allowlisted pack is all the way in


def test_an_allowlisted_pack_is_loaded(installed_evil_pack: None):
    """Same estate, same installed packs — only the allowlist differs."""
    registry = build_registry(["stdlib", EVIL_PACK])

    callable_, _ = registry.get(EVIL_BRICK)
    assert callable_()["result"] == "boom"


def test_the_dsl_builtins_are_always_registered():
    """`__for_each__` comes from the engine, not a pack. The daily-summary
    blueprint iterates, so losing it would break every processor."""
    registry = build_registry(["stdlib"])

    registry.get("__for_each__")
    registry.get("__branch__")


def test_a_run_cannot_see_a_pack_the_manifest_does_not_name(
        estate: Store, installed_evil_pack: None):
    """End to end: the fake pack is installed for the whole run and still never
    reaches the registry, while the run itself succeeds."""
    record = aos.run(PROCESSOR, root=estate.root, on_date=RUN_DATE)
    assert record.status == "success", record.error

    blueprint = estate.root / "blueprints" / "daily-summary.yaml"
    blueprint.write_text(
        blueprint.read_text(encoding="utf-8").replace("sort_dict_list", EVIL_BRICK),
        encoding="utf-8")

    refused = aos.run(PROCESSOR, root=estate.root, on_date=RUN_DATE)
    assert refused.status == "failed"  # validation, before anything executes
    assert EVIL_BRICK in refused.error
    assert refused.calls == []


# ---- a missing allowlist fails loudly, never quietly --------------------------

@pytest.mark.parametrize("allowlist", [[], ["stdlib", "no-such-pack"]])
def test_an_unusable_allowlist_raises(allowlist: list[str]):
    """Empty is an error, not an empty registry: a kernel that silently ran
    with no bricks would deny everything and look like the gate working."""
    with pytest.raises(PackAllowlistError):
        build_registry(allowlist)


def test_an_ambiguous_pack_name_raises(evil_pack_installed_twice: None):
    """Two installed distributions claim the name `files`. Picking the first
    candidate would let a squatting distribution decide which code runs, so the
    allowlist refuses instead — and says enough for an operator to uninstall
    one."""
    with pytest.raises(PackAllowlistError) as excinfo:
        build_registry(["stdlib", EVIL_PACK])

    message = str(excinfo.value)
    assert EVIL_PACK in message  # which name is contested
    assert "more than one" in message  # and why it could not be resolved
    assert "stdlib" not in message  # the unambiguous pack is not blamed


@pytest.mark.parametrize("packs", [None, []])
def test_a_manifest_with_no_packs_fails_the_run_loudly(estate: Store, packs):
    """`failed`, never `denied` — a mis-declared processor must not be
    indistinguishable from a correctly refusing one."""
    _patch_manifest(estate, packs=packs)

    record = aos.run(PROCESSOR, root=estate.root, on_date=RUN_DATE)

    assert record.status == "failed"
    assert "PackAllowlistError" in record.error
    assert "packs" in record.error
    assert (estate.runs / f"{record.run}.yaml").exists()  # audited anyway


def test_a_malformed_allowlist_is_a_manifest_error(estate: Store):
    _patch_manifest(estate, packs="stdlib")  # a string is not a list of names

    record = aos.run(PROCESSOR, root=estate.root, on_date=RUN_DATE)

    assert record.status == "failed"
    assert "packs" in record.error


def _patch_manifest(estate: Store, **changes) -> None:
    path = estate.processors / f"{PROCESSOR}.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    for key, value in changes.items():
        if value is None:
            doc.pop(key, None)
        else:
            doc[key] = value
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
