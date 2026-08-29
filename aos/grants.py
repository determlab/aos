"""Grant checking (spec §4.3).

Runtime rule, no exceptions: no matching, unexpired, unrevoked grant → the run
stops. Expiry is compared against the *run date the kernel was given*, never
against the clock — a replay of yesterday's run must reach yesterday's answer
(CLAUDE.md: the kernel stays deterministic; nondeterminism lives in the
executor).
"""
from __future__ import annotations

from datetime import date
from typing import Any

from aos.errors import GrantDenied
from aos.store import Store


def find_grant(store: Store, processor: str, capability: str,
               on_date: date) -> dict[str, Any] | None:
    """The first grant authorizing *capability* for *processor* on *on_date*."""
    for grant in store.all_grants():
        if grant.get("processor") != processor:
            continue
        if grant.get("capability") != capability:
            continue
        if grant.get("revoked"):
            continue
        if _expired(grant, on_date):
            continue
        return grant
    return None


def require_grant(store: Store, processor: str, capability: str,
                  on_date: date) -> dict[str, Any]:
    """*find_grant* or raise. The only way a capability becomes callable."""
    grant = find_grant(store, processor, capability, on_date)
    if grant is None:
        raise GrantDenied(
            f"{processor} is not granted {capability} on {on_date.isoformat()} "
            f"(no matching, unexpired, unrevoked grant in {store.grants})")
    return grant


def _expired(grant: dict[str, Any], on_date: date) -> bool:
    expires = grant.get("expires")
    if expires is None:
        return False  # an open-ended grant; revocation is the only way out
    if isinstance(expires, str):
        expires = date.fromisoformat(expires)
    return expires < on_date
