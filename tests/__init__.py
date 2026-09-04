"""Test package: makes the flat modules under src/ importable by name.

Discovery must use the repository root as the top-level directory, as
``python -m unittest`` run from the root or ``scripts/run-checks.sh`` does,
so that the test modules are imported as ``tests.test_*`` and this file
runs. ``python -m unittest discover -s tests`` without ``-t .`` imports them
as bare modules and never puts src/ on the path.
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
