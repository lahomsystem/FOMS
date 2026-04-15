"""Compatibility entrypoint for Step 3 runtime namespace smoke tests.

Wave 7 (W7-B3): substantive tests live in
``tests/contracts/runtime/foms_namespace_surface_tests.py`` (not ``test_*.py`` — avoids
duplicate collection when running ``pytest tests/``). This module stays a stable
CLI path (``pytest tests/domains/test_foms_namespace_imports.py``) and re-exports tests for
collection.

TR3 / TR6: parity and bridge-aware assertions are unchanged — only location moved.
"""

from tests.contracts.runtime.foms_namespace_surface_tests import *  # noqa: F403
