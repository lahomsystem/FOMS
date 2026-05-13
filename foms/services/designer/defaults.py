"""FOMS Brain AX Designer – default design factory."""

from __future__ import annotations


def default_design_json() -> dict:
    """Return the canonical default design JSON for a new project."""
    return {
        "schema_version": 1,
        "unit": "mm",
        "cabinet": {
            "width": 2400,
            "height": 2200,
            "depth": 600,
        },
        "components": [
            {"id": "left-side", "type": "panel", "name": "좌측판", "width": 18, "height": 2200, "depth": 600, "position": {"x": 0, "y": 0, "z": 0}},
            {"id": "right-side", "type": "panel", "name": "우측판", "width": 18, "height": 2200, "depth": 600, "position": {"x": 2382, "y": 0, "z": 0}},
            {"id": "top-panel", "type": "panel", "name": "천장판", "width": 2364, "height": 18, "depth": 600, "position": {"x": 18, "y": 2182, "z": 0}},
            {"id": "bottom-panel", "type": "panel", "name": "바닥판", "width": 2364, "height": 18, "depth": 600, "position": {"x": 18, "y": 0, "z": 0}},
            {"id": "back-panel", "type": "panel", "name": "후판", "width": 2400, "height": 2200, "depth": 9, "position": {"x": 0, "y": 0, "z": 591}},
        ],
        "relations": [],
    }
