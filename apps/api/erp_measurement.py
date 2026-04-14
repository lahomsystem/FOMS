"""Legacy import path; canonical implementation: foms.api.measurement (Wave 2 canonical alias shim)."""
import importlib
import sys

_mod = importlib.import_module('foms.api.measurement')
sys.modules[__name__] = _mod
