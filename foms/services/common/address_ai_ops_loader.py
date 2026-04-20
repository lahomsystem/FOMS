"""Load address AI classes from ``scripts/ops`` (owner path). Root shims removed (SFC-B12)."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_ops_module(unique_name: str, filename: str):
    """Load a module from ``scripts/ops/<filename>`` relative to repo root."""
    root = Path(__file__).resolve().parents[3]
    impl = root / "scripts" / "ops" / filename
    spec = importlib.util.spec_from_file_location(unique_name, impl)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {unique_name} from {impl}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_learning = _load_ops_module("foms_address_learning_impl", "foms_address_learning.py")
_processor = _load_ops_module("foms_advanced_address_processor_impl", "foms_advanced_address_processor.py")

FOMSAddressLearningSystem = _learning.FOMSAddressLearningSystem
FOMSAdvancedAddressProcessor = _processor.FOMSAdvancedAddressProcessor

__all__ = ("FOMSAddressLearningSystem", "FOMSAdvancedAddressProcessor")
