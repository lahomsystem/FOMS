"""Reusable block library contract checks."""

from __future__ import annotations


def test_instantiate_geometry_returns_module_with_cloned_components():
    from foms.services.designer.block_library import _instantiate_geometry

    geometry = {
        "schema_version": "v2",
        "components": [
            {
                "id": "left",
                "kind": "ep",
                "role": "left_ep",
                "name": "좌측 EP",
                "parent_id": "old_module",
                "material_id": None,
                "dimensions": {"width": 18, "height": 800, "depth": 600},
                "position": {"x": 100, "y": 0, "z": 0},
                "formula_refs": [],
            },
            {
                "id": "shelf",
                "kind": "shelf",
                "role": "shelf",
                "name": "선반",
                "parent_id": "old_module",
                "material_id": None,
                "dimensions": {"width": 600, "height": 18, "depth": 580},
                "position": {"x": 118, "y": 300, "z": 0},
                "formula_refs": [],
            },
        ],
    }

    instance = _instantiate_geometry(
        block_id=7,
        block_key="test.module",
        label_ko="테스트 모듈",
        category="module",
        geometry=geometry,
        at_position={"x": 20, "y": 10, "z": 5},
    )

    assert set(instance) >= {"module", "components", "relations"}
    assert instance["module"]["component_ids"] == [
        comp["id"] for comp in instance["components"]
    ]
    assert len(instance["components"]) == 2
    assert {comp["kind"] for comp in instance["components"]} == {"ep", "shelf"}
    assert all(comp["kind"] != "module" for comp in instance["components"])
    assert all(
        comp["parent_id"] == instance["module"]["id"]
        for comp in instance["components"]
    )
    assert instance["components"][0]["position"] == {"x": 20.0, "y": 10.0, "z": 5.0}
    assert instance["components"][0]["custom_props"]["from_block_id"] == 7

