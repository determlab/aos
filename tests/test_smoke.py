"""Smoke tests.

These exist so `main` is green from the first commit. A repo whose main is red
blocks every PR the agent-loop opens -- determlab/bricks sat in exactly that
state and its first PR could not merge until the lint failure was fixed
(bricks#14).
"""

import aos


def test_package_imports() -> None:
    assert aos.__version__ == "0.1.0"
