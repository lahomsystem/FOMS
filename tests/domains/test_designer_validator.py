"""Tests for POST /api/designer/validate."""

import pytest


def test_validate_valid_design(auth_client):
    """Valid default design should pass validation."""
    design = {
        "schema_version": 1,
        "unit": "mm",
        "cabinet": {"width": 2400, "height": 2200, "depth": 600},
        "components": [
            {"id": "left-side", "type": "panel", "name": "좌측판", "width": 18, "height": 2200, "depth": 600, "position": {"x": 0, "y": 0, "z": 0}},
        ],
        "relations": [],
    }
    resp = auth_client.post("/api/designer/validate", json={"design_json": design})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["data"]["valid"] is True
    assert data["data"]["errors"] == []


def test_validate_width_too_large(auth_client):
    """Width > 10000mm should fail validation."""
    design = {
        "schema_version": 1,
        "unit": "mm",
        "cabinet": {"width": 99999, "height": 2200, "depth": 600},
        "components": [],
        "relations": [],
    }
    resp = auth_client.post("/api/designer/validate", json={"design_json": design})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["data"]["valid"] is False
    codes = [e["code"] for e in data["data"]["errors"]]
    assert "WIDTH_TOO_LARGE" in codes


def test_validate_duplicate_component_id(auth_client):
    """Duplicate component IDs should fail validation."""
    design = {
        "schema_version": 1,
        "unit": "mm",
        "cabinet": {"width": 2400, "height": 2200, "depth": 600},
        "components": [
            {"id": "dup", "type": "panel", "name": "A", "width": 18, "height": 100, "depth": 600, "position": {"x": 0, "y": 0, "z": 0}},
            {"id": "dup", "type": "panel", "name": "B", "width": 18, "height": 100, "depth": 600, "position": {"x": 18, "y": 0, "z": 0}},
        ],
        "relations": [],
    }
    resp = auth_client.post("/api/designer/validate", json={"design_json": design})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["data"]["valid"] is False
    codes = [e["code"] for e in data["data"]["errors"]]
    assert "DUPLICATE_COMPONENT_ID" in codes


def test_validate_panel_zero_thickness(auth_client):
    """Panel with zero thickness should fail validation."""
    design = {
        "schema_version": 1,
        "unit": "mm",
        "cabinet": {"width": 2400, "height": 2200, "depth": 600},
        "components": [
            {"id": "zero-panel", "type": "panel", "name": "제로판", "width": 0, "height": 100, "depth": 600, "position": {"x": 0, "y": 0, "z": 0}},
        ],
        "relations": [],
    }
    resp = auth_client.post("/api/designer/validate", json={"design_json": design})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["data"]["valid"] is False


def test_validate_unit_directly():
    """Test validator service directly."""
    from foms.services.designer.validator import validate_design

    # Valid
    result = validate_design({
        "cabinet": {"width": 2400, "height": 2200, "depth": 600},
        "components": [],
    })
    assert result.valid is True

    # Invalid - height too large
    result = validate_design({
        "cabinet": {"width": 2400, "height": 5000, "depth": 600},
        "components": [],
    })
    assert result.valid is False
    assert any(e.code == "HEIGHT_TOO_LARGE" for e in result.errors)
