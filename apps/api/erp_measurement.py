"""Legacy import path; canonical implementation: foms.api.measurement."""
import importlib
import sys

_mod = importlib.import_module('foms.api.measurement')
sys.modules[__name__] = _mod
