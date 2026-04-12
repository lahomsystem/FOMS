"""Legacy import path; canonical implementation: foms.web.measurement.dashboard."""
import importlib
import sys

_mod = importlib.import_module('foms.web.measurement.dashboard')
sys.modules[__name__] = _mod
