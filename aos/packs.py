"""Registry construction from an explicit pack allowlist (decisions 3 and 8).

``bricks.build_default_registry()`` loads *every* installed ``bricks.packs``
entry point, so ``pip install <some-io-pack>`` would add world-touching bricks
to a processor's registry with no grant, no capability contract and no run
record. Installation is not authorization: under D8 the registry *is* the
policy, so the kernel names the packs it wants and builds the registry itself.

A pack that is installed but not named is **absent** from the registry — the
same mechanism that makes an ungranted capability not exist. There is no
call-time check here, deliberately: a check can be forgotten on one path, and
absence cannot.

**No allowlist is not an empty allowlist — it is an error.** A kernel that
quietly builds an empty registry denies everything, and "denies everything"
looks exactly like a permission system working. So an omitted or empty
``packs:`` raises :class:`~aos.errors.PackAllowlistError` and the run is a
loud ``failed``, never a plausible ``denied``. The same goes for a pack that is
named but not installed: silently skipping it would degrade a processor into a
different processor. When a real builtins-only processor turns up, it will
declare ``packs:`` explicitly and this default is revisited then.
"""
from __future__ import annotations

import importlib
import importlib.metadata
from collections.abc import Iterable, Sequence

from bricks.core.builtins import register_builtins
from bricks.core.registry import BrickRegistry

from aos.errors import PackAllowlistError

#: The entry point group Bricks publishes its packs under.
PACK_GROUP = "bricks.packs"


def build_registry(allowlist: Sequence[str]) -> BrickRegistry:
    """Build a registry holding *only* the named packs, plus the DSL builtins.

    ``__for_each__`` / ``__branch__`` come from ``bricks.core.builtins``, not
    from a pack, and every blueprint that iterates needs them — they are part
    of the engine, not a capability, so they are always registered.

    Raises:
        PackAllowlistError: if *allowlist* is empty, names a pack that is not
            installed, or names one that two installed distributions claim.
    """
    names = list(dict.fromkeys(allowlist))  # de-duplicated, order kept
    installed = _installed_packs()
    if not names:
        raise PackAllowlistError(
            "no brick packs are allowlisted: the processor manifest must "
            "declare `packs:` naming each pack it may use. An installed pack "
            "is not a granted capability (decision 8). Installed packs: "
            f"{sorted(installed) or 'none — run: pip install bricks'}")
    unknown = [name for name in names if name not in installed]
    if unknown:
        raise PackAllowlistError(
            f"allowlisted brick pack(s) {unknown} are not installed — "
            f"installed packs: {sorted(installed) or 'none'}")
    ambiguous = [name for name in names if len(installed[name]) > 1]
    if ambiguous:
        raise PackAllowlistError(
            f"brick pack name(s) {ambiguous} are claimed by more than one "
            "installed distribution, so the allowlist cannot say which one it "
            "means")

    registry = BrickRegistry()
    for name in names:
        importlib.import_module(installed[name][0].value).register(registry)
    register_builtins(registry)
    return registry


def _installed_packs() -> dict[str, list[importlib.metadata.EntryPoint]]:
    """Installed packs by entry point *name*.

    Selecting by name rather than by module path means the manifest never gets
    to name an arbitrary importable module: it can only pick from what a
    distribution has published as a brick pack.
    """
    packs: dict[str, list[importlib.metadata.EntryPoint]] = {}
    entry_points: Iterable[importlib.metadata.EntryPoint] = (
        importlib.metadata.entry_points(group=PACK_GROUP))
    for entry_point in entry_points:
        packs.setdefault(entry_point.name, []).append(entry_point)
    return packs
