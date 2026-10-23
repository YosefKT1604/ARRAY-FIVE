"""Test setup for Person 3's impact engine tests, which are copied here unchanged.

The engine finds the demo data through SCDC_FIXTURES (impact_engine/scenarios.py, read at import time),
so it is pointed at the repository's shared fixtures/demo/ before any test module imports it.
"""

import os
from pathlib import Path

os.environ.setdefault("SCDC_FIXTURES", str(Path(__file__).resolve().parents[2] / "fixtures" / "demo"))
