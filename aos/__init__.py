"""AOS — purpose-built agent processors.

One processor = one capability set + one trigger + one policy, declared in a
manifest. A tiny kernel runs them: manifest -> grant check -> driver -> run
record. Everything else is a plugin.

See spec/v0.2.md for the contract.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
