"""FOMS Brain Design Kernel V1 — Component & Material Catalog (Python backend).

DK-B1: component kind / material seed definitions.
"""

from __future__ import annotations

from foms.services.designer.ontology_types import Material

# ──────────────────────────────────────────────────────────
# Material catalog seed
# ──────────────────────────────────────────────────────────

MATERIAL_CATALOG: dict[str, Material] = {
    "PB_18T_WHITE": Material(
        id="PB_18T_WHITE",
        name="PB 18T 화이트",
        thickness=18,
        max_width=2440,
        max_height=1220,
        category="board",
    ),
    "MDF_18T": Material(
        id="MDF_18T",
        name="MDF 18T",
        thickness=18,
        max_width=2440,
        max_height=1220,
        category="board",
    ),
    "PB_9T_BACK": Material(
        id="PB_9T_BACK",
        name="PB 9T (후판)",
        thickness=9,
        max_width=2440,
        max_height=1220,
        category="board",
    ),
    "PET_DOOR_WHITE": Material(
        id="PET_DOOR_WHITE",
        name="PET 도어 화이트",
        thickness=18,
        max_width=1000,
        max_height=2500,
        category="door",
    ),
    "HARDWARE_RAIL": Material(
        id="HARDWARE_RAIL",
        name="슬라이딩 레일",
        thickness=0,
        max_width=3000,
        max_height=100,
        category="hardware",
    ),
}

# ──────────────────────────────────────────────────────────
# Component kind metadata
# ──────────────────────────────────────────────────────────

COMPONENT_KIND_META: dict[str, dict] = {
    "box":      {"label_ko": "내부 박스",  "default_material_id": None,              "is_structural": True},
    "panel":    {"label_ko": "판재",       "default_material_id": "PB_18T_WHITE",    "is_structural": True},
    "door":     {"label_ko": "도어",       "default_material_id": "PET_DOOR_WHITE",  "is_structural": False},
    "shelf":    {"label_ko": "선반",       "default_material_id": "PB_18T_WHITE",    "is_structural": False},
    "drawer":   {"label_ko": "서랍",       "default_material_id": "PB_18T_WHITE",    "is_structural": False},
    "ep":       {"label_ko": "엔드패널",   "default_material_id": "PB_18T_WHITE",    "is_structural": True},
    "sr":       {"label_ko": "스카이레일", "default_material_id": "PB_18T_WHITE",    "is_structural": True},
    "base":     {"label_ko": "받침대",     "default_material_id": "PB_18T_WHITE",    "is_structural": True},
    "hardware": {"label_ko": "하드웨어",   "default_material_id": "HARDWARE_RAIL",   "is_structural": False},
    "cutout":   {"label_ko": "홈/개구부",  "default_material_id": None,              "is_structural": False},
}

# ──────────────────────────────────────────────────────────
# Role → Kind mapping
# ──────────────────────────────────────────────────────────

ROLE_TO_KIND: dict[str, str] = {
    "left_ep": "ep",
    "right_ep": "ep",
    "top_ep": "ep",
    "top_sr": "sr",
    "bottom_sr": "sr",
    "base": "base",
    "left_side": "panel",
    "right_side": "panel",
    "top_panel": "panel",
    "bottom_panel": "panel",
    "back_panel": "panel",
    "shelf": "shelf",
    "door": "door",
    "drawer": "drawer",
    "inner_box": "box",
    "generic": "panel",
}


def get_material_for_role(role: str) -> str | None:
    """Return default material id for a given component role."""
    kind = ROLE_TO_KIND.get(role, "panel")
    return COMPONENT_KIND_META.get(kind, {}).get("default_material_id")


def get_material(material_id: str) -> Material | None:
    """Lookup material by id."""
    return MATERIAL_CATALOG.get(material_id)
