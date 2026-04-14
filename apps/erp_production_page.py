"""Legacy import path; canonical implementation: foms.web.production.dashboard (Wave 4)."""
import importlib
import sys

_mod = importlib.import_module('foms.web.production.dashboard')
sys.modules[__name__] = _mod
