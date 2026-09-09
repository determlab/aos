"""The five artifacts on disk (spec §4). Four are read here; the fifth — the run
record — is written by :mod:`aos.record`.

Everything is addressed relative to a *root*, so a test can point the kernel at
a tmp dir and get a whole isolated estate. Grant storage stays flat YAML until a
second principal forces sqlite (spec §7).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from aos.errors import ManifestError

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Store:
    """Where the artifacts live."""

    root: Path = REPO_ROOT

    # -- directories ------------------------------------------------------
    @property
    def capabilities(self) -> Path:
        return self.root / "capabilities"

    @property
    def grants(self) -> Path:
        return self.root / "grants"

    @property
    def processors(self) -> Path:
        return self.root / "processors"

    @property
    def runs(self) -> Path:
        return self.root / "runs"

    @property
    def outputs(self) -> Path:
        return self.root / "outputs"

    # -- reads ------------------------------------------------------------
    def manifest(self, processor_id: str) -> dict[str, Any]:
        """The processor manifest (spec §4.4)."""
        m = _read(self.processors / f"{processor_id}.yaml", "processor manifest")
        declared = m.get("processor")
        if declared != processor_id:
            raise ManifestError(
                f"processors/{processor_id}.yaml declares processor "
                f"{declared!r} — the file name is the id, keep them equal")
        if not m.get("blueprint"):
            raise ManifestError(f"{processor_id}: manifest has no `blueprint`")
        return m

    def pack_allowlist(self, manifest: dict[str, Any]) -> list[str]:
        """The brick packs this processor may use (spec §4.4, decision 8).

        Names are ``bricks.packs`` entry point names. An absent key returns an
        empty list; :func:`aos.packs.build_registry` is what refuses it, so
        "declared nothing" and "declared []" fail the same loud way.
        """
        names = manifest.get("packs") or []
        if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
            raise ManifestError(
                f"{manifest.get('processor')}: `packs` must be a list of brick "
                f"pack names, got {names!r}")
        return list(names)

    def capability(self, capability_id: str) -> dict[str, Any]:
        """One capability contract (spec §4.1)."""
        return _read(self.capabilities / f"{capability_id}.yaml", "capability")

    def capability_ids(self) -> set[str]:
        """Every declared capability. This is what lets the engine tell a
        *denial* (a brick that only a grant could have supplied) apart from a
        blueprint that simply names a brick that does not exist."""
        return {p.stem for p in sorted(self.capabilities.glob("*.yaml"))}

    def all_grants(self) -> list[dict[str, Any]]:
        """Every grant on disk, in a stable order (file name)."""
        return [_read(p, "grant") for p in sorted(self.grants.glob("*.yaml"))]

    def blueprint(self, manifest: dict[str, Any]) -> Path:
        """The blueprint a manifest points at, resolved against the root."""
        path = self.root / str(manifest["blueprint"])
        if not path.exists():
            raise ManifestError(
                f"{manifest.get('processor')}: blueprint {manifest['blueprint']!r} "
                f"does not exist at {path}")
        return path


def _read(path: Path, what: str) -> dict[str, Any]:
    if not path.exists():
        raise ManifestError(f"no {what} at {path}")
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ManifestError(f"{path}: {e}") from e
    if not isinstance(doc, dict):
        raise ManifestError(f"{path}: expected a mapping, got "
                            f"{type(doc).__name__}")
    return doc
