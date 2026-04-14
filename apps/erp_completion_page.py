"""Legacy import path; canonical implementation: foms.web.cs.completion_dashboard (Wave 4)."""
import importlib
import sys

_mod = importlib.import_module('foms.web.cs.completion_dashboard')
sys.modules[__name__] = _mod
