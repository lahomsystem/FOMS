"""FOMS Brain AX Designer — default design factory.

DK-B9: includes v1→v2 normalize helper.
"""

from __future__ import annotations


def default_design_json() -> dict:
    """Return the canonical default design JSON (schema v1, kept for backward compat)."""
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


def normalize_to_v2(design_json: dict) -> dict:
    """Normalize a schema v1 design_json to schema v2 DesignGraph.

    DK-B9: old projects load as v2 on read. Uses the v1 cabinet dimensions
    to create a wardrobe assembly factory result.

    If design_json is already v2, returns it unchanged.
    """
    if design_json.get("schema_version") == 2:
        return design_json

    # Extract v1 cabinet dimensions
    cabinet = design_json.get("cabinet", {})
    width = int(cabinet.get("width", 2400))
    height = int(cabinet.get("height", 2200))
    depth = int(cabinet.get("depth", 600))

    from foms.services.designer.assembly_factories import default_design_json_v2
    v2 = default_design_json_v2(
        width=width,
        height=height,
        depth=depth,
        module_count=2,
        door_type="sliding",
    )
    # Mark as migrated
    v2.setdefault("metadata", {})["migrated_from_v1"] = True
    return v2
