"""DK-B9: Designer API/Data compatibility tests.

Tests schema v1/v2 dual-read, new project = v2, validator gate.
These are contract tests that don't require a live DB (offline).
"""

from __future__ import annotations

import pytest

from foms.services.designer.defaults import default_design_json, normalize_to_v2
from foms.services.designer.assembly_factories import WardrobeParams, create_wardrobe_assembly, default_design_json_v2
from foms.services.designer.validator import validate_design


class TestSchemaVersionDispatch:
    def test_default_design_json_is_v1(self):
        d = default_design_json()
        assert d["schema_version"] == 1

    def test_default_design_json_v2_is_v2(self):
        d = default_design_json_v2()
        assert d["schema_version"] == 2

    def test_v1_validates_valid(self):
        d = default_design_json()
        result = validate_design(d)
        assert result.valid is True

    def test_v2_validates_valid(self):
        d = default_design_json_v2()
        result = validate_design(d)
        assert result.valid is True

    def test_v2_invalid_design_fails(self):
        graph = create_wardrobe_assembly(WardrobeParams(width=2400, height=2200, depth=600))
        d = graph.to_dict()
        # Inject duplicate UUID
        if d["components"]:
            dupe = dict(d["components"][0])
            d["components"].append(dupe)
        result = validate_design(d)
        assert result.valid is False
        assert any(e.code == "DUPLICATE_COMPONENT_UUID" for e in result.errors)


class TestNormalizeToV2:
    def test_v1_normalizes_to_v2(self):
        v1 = default_design_json()
        v2 = normalize_to_v2(v1)
        assert v2["schema_version"] == 2
        assert "assembly" in v2
        assert "components" in v2

    def test_v2_passthrough(self):
        v2 = default_design_json_v2()
        result = normalize_to_v2(v2)
        assert result is v2  # same object

    def test_v1_normalized_passes_validator(self):
        v1 = default_design_json()
        v2 = normalize_to_v2(v1)
        result = validate_design(v2)
        assert result.valid is True

    def test_normalized_preserves_dimensions(self):
        v1 = {
            "schema_version": 1,
            "unit": "mm",
            "cabinet": {"width": 3000, "height": 2400, "depth": 620},
            "components": [],
            "relations": [],
        }
        v2 = normalize_to_v2(v1)
        asm_dims = v2["assembly"]["dimensions"]
        assert asm_dims["width"] == 3000
        assert asm_dims["height"] == 2400
        assert asm_dims["depth"] == 620

    def test_normalized_marks_migrated(self):
        v1 = default_design_json()
        v2 = normalize_to_v2(v1)
        assert v2.get("metadata", {}).get("migrated_from_v1") is True


class TestValidatorGate:
    """Validator gate must block invalid designs from being saved."""

    def test_invalid_v1_blocked(self):
        d = {
            "schema_version": 1,
            "unit": "mm",
            "cabinet": {"width": -1, "height": 2200, "depth": 600},
            "components": [],
            "relations": [],
        }
        result = validate_design(d)
        assert result.valid is False

    def test_valid_v2_allowed(self):
        d = default_design_json_v2()
        result = validate_design(d)
        assert result.valid is True

    def test_invalid_v2_blocked(self):
        graph = create_wardrobe_assembly(WardrobeParams(width=2400, height=2200, depth=600))
        d = graph.to_dict()
        d["assembly"]["dimensions"]["width"] = -999
        result = validate_design(d)
        assert result.valid is False

    def test_api_envelope_fields(self):
        """Validate that validate_design returns to_dict() compatible shape."""
        result = validate_design(default_design_json_v2())
        d = result.to_dict()
        assert "valid" in d
        assert "errors" in d
        assert "warnings" in d


class TestVersionSaveGate:
    """save_design_version must pass validator before creating DB version."""

    def test_save_requires_valid_design(self):
        from foms.persistence.designer.repositories import save_design_version

        invalid_design = {
            "schema_version": 2,
            "unit": "mm",
            "assembly": {},  # missing required fields
            "components": [],
            "constraints": [],
            "relations": [],
            "metadata": {},
        }
        # Should return None (not save) rather than raising
        # (offline test: no DB, so we just check validator pre-check)
        result = validate_design(invalid_design)
        assert result.valid is False
        # When valid=False, save_design_version returns None
        # (Actual DB call would fail, so just verify the validator rejects it)
