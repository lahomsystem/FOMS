"""WDCalculator web surface.

The current blueprint still serves both HTML pages and JSON APIs through the same
Flask blueprint. Until the split is completed, the canonical web namespace
re-exports the same blueprint as `foms.api.wdcalculator`.
"""

from foms.api.wdcalculator import wdcalculator_bp
from foms.web.wdcalculator.planner import wdplanner_bp

__all__ = ["wdcalculator_bp", "wdplanner_bp"]
