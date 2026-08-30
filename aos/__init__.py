"""AOS — a tiny kernel that runs processors.

One processor = one capability set + one trigger + one policy, declared in a
manifest. The kernel is manifests + grants + run records; everything else is a
plugin. See spec/v0.2.md.
"""
from aos.engine import run
from aos.errors import AosError, CapabilityCallError, GrantDenied, ManifestError
from aos.record import RunRecord
from aos.store import Store

__all__ = ["run", "RunRecord", "Store", "AosError", "GrantDenied",
           "ManifestError", "CapabilityCallError"]
__version__ = "0.2.0"
