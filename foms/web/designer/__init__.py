"""FOMS Brain AX Designer web surface.

Serves the /wdplanner-v2 route group.
V1 /wdplanner remains untouched; V2 runs in parallel.
"""

from foms.web.designer.routes import designer_bp

__all__ = ["designer_bp"]
