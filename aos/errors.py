"""Kernel errors.

``GrantDenied`` is a ``PermissionError`` on purpose: the engine loop separates
*denied* from *failed* by exception class, and a denial is exactly "you are not
permitted", not "it broke".
"""
from __future__ import annotations


class AosError(Exception):
    """Base for every kernel error."""


class GrantDenied(PermissionError, AosError):
    """No matching, unexpired, unrevoked grant. Spec §4.3, no exceptions."""


class ManifestError(AosError):
    """A manifest, capability, or grant file is missing or malformed."""


class CapabilityCallError(AosError):
    """A granted capability was called and the driver refused or failed."""


class PackAllowlistError(AosError):
    """The brick packs a processor may use could not be resolved.

    Not a denial: a missing or empty allowlist is a mis-declared processor, and
    it must read as `failed`. A run that quietly built an empty registry would
    deny everything and look like the gate working (spec decision 8).
    """
