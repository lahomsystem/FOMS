"""Shim: Wave 1 root hygiene moved implementation to scripts/ops (import 경로 호환)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_impl = Path(__file__).resolve().parent / "scripts" / "ops" / "erp_automation.py"
_spec = importlib.util.spec_from_file_location(__name__, _impl)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Cannot load erp_automation from {_impl}")
_module = importlib.util.module_from_spec(_spec)
sys.modules[__name__] = _module
_spec.loader.exec_module(_module)
