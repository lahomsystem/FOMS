"""FOMS Brain AX Designer – BOM (Bill of Materials) generation stub."""

from __future__ import annotations


def generate_bom(design_json: dict) -> dict:
    """Generate a basic BOM from design_json.

    MVP: enumerates components with dimensions and material type.
    """
    components = design_json.get("components", [])
    items = []
    for comp in components:
        if not isinstance(comp, dict):
            continue
        w = comp.get("width", 0)
        h = comp.get("height", 0)
        d = comp.get("depth", 0)
        area_m2 = round((w * h) / 1_000_000, 4) if w and h else 0
        items.append({
            "id": comp.get("id"),
            "name": comp.get("name", ""),
            "type": comp.get("type", "panel"),
            "dimensions": {"width": w, "height": h, "depth": d},
            "area_m2": area_m2,
        })
    return {
        "bom_version": "1.0",
        "unit": "mm",
        "items": items,
        "total_items": len(items),
    }
