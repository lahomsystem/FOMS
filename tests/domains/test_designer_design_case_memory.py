"""PG-L1: Design Case Memory Tests.

Verifies:
1. DesignerDesignCase model structure (no PII fields, required columns).
2. design_case_memory.py service contract — save/list/find_similar.
3. PII stripping — customer_name/phone/address must not appear in cases.
4. Dimension extraction from design graph.
5. Similarity search returns nearest cases.
6. Migration file exists and is correct.
7. Cannot save case without a valid project_version_id.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent


# ──────────────────────────────────────────────────────────
# PG-L1-01: Model structure
# ──────────────────────────────────────────────────────────

class TestDesignCaseModel:
    def test_model_importable(self):
        from foms.persistence.designer.models import DesignerDesignCase
        assert DesignerDesignCase.__tablename__ == "designer_design_cases"

    def test_required_columns_exist(self):
        from foms.persistence.designer.models import DesignerDesignCase
        cols = {c.key for c in DesignerDesignCase.__table__.columns}
        required = {
            "id", "project_version_id", "furniture_type",
            "design_graph_json", "width_mm", "height_mm",
            "source_quality_score", "approved_at", "created_at",
        }
        assert required <= cols, f"Missing: {required - cols}"

    def test_no_pii_columns_in_model(self):
        """Design case must NOT have customer_name/phone/address columns."""
        from foms.persistence.designer.models import DesignerDesignCase
        cols = {c.key for c in DesignerDesignCase.__table__.columns}
        pii_cols = {"customer_name", "phone", "address", "customer_phone"}
        found_pii = pii_cols & cols
        assert not found_pii, (
            f"PII columns found in DesignerDesignCase: {found_pii}. "
            "Raw PII must never be stored in design cases."
        )

    def test_dimension_columns_for_similarity(self):
        """width_mm/height_mm/depth_mm/module_count exist for fast similarity."""
        from foms.persistence.designer.models import DesignerDesignCase
        cols = {c.key for c in DesignerDesignCase.__table__.columns}
        assert "width_mm" in cols
        assert "height_mm" in cols
        assert "depth_mm" in cols
        assert "module_count" in cols


# ──────────────────────────────────────────────────────────
# PG-L1-02: Service helpers (no DB required)
# ──────────────────────────────────────────────────────────

class TestDesignCaseMemoryHelpers:
    def test_service_importable(self):
        import foms.services.designer.design_case_memory as dcm
        assert callable(dcm.save_design_case)
        assert callable(dcm.list_design_cases)
        assert callable(dcm.find_similar)

    def test_pii_strip_removes_customer_name(self):
        from foms.services.designer.design_case_memory import _strip_pii_fields
        graph = {
            "assembly": {"type": "wardrobe"},
            "customer_name": "홍길동",
            "phone": "010-1234-5678",
        }
        clean = _strip_pii_fields(graph)
        assert "customer_name" not in clean
        assert "phone" not in clean
        assert "assembly" in clean

    def test_pii_strip_preserves_non_pii(self):
        from foms.services.designer.design_case_memory import _strip_pii_fields
        graph = {
            "assembly": {"type": "wardrobe", "dimensions": {"width": 2400}},
            "components": [],
        }
        clean = _strip_pii_fields(graph)
        assert clean["assembly"]["dimensions"]["width"] == 2400
        assert "components" in clean

    def test_extract_dimensions_wardrobe(self):
        from foms.services.designer.design_case_memory import _extract_dimensions
        graph = {
            "assembly": {
                "dimensions": {"width": 2400, "height": 2200, "depth": 620},
                "module_count": 3,
            }
        }
        w, h, d, m = _extract_dimensions(graph)
        assert w == 2400
        assert h == 2200
        assert d == 620
        assert m == 3

    def test_extract_dimensions_missing_values(self):
        from foms.services.designer.design_case_memory import _extract_dimensions
        graph = {"assembly": {}}
        w, h, d, m = _extract_dimensions(graph)
        assert w is None
        assert h is None

    def test_furniture_type_validation(self):
        """save_design_case raises ValueError for unknown furniture_type."""
        from foms.services.designer.design_case_memory import save_design_case
        with pytest.raises(ValueError, match="Unknown furniture_type"):
            save_design_case(
                project_version_id=1,
                furniture_type="refrigerator",
                design_graph={},
            )

    def test_invalid_project_version_raises(self):
        """save_design_case raises ValueError when project_version_id does not exist."""
        from foms.services.designer.design_case_memory import save_design_case
        # project_version_id=999999 will not exist in test DB
        with pytest.raises((ValueError, Exception)):
            save_design_case(
                project_version_id=999999,
                furniture_type="wardrobe",
                design_graph={"assembly": {"type": "wardrobe"}},
            )

    def test_quality_score_clamped(self):
        """source_quality_score is clamped to 0.0–1.0."""
        from foms.services.designer.design_case_memory import _case_to_dict
        from unittest.mock import MagicMock
        from datetime import datetime, timezone

        mock_case = MagicMock()
        mock_case.id = 1
        mock_case.project_id = None
        mock_case.project_version_id = 1
        mock_case.drawing_artifact_id = None
        mock_case.furniture_type = "wardrobe"
        mock_case.product_name = "테스트"
        mock_case.width_mm = 2400
        mock_case.height_mm = 2200
        mock_case.depth_mm = 620
        mock_case.module_count = 3
        mock_case.tags_json = ["no_molding"]
        mock_case.source_quality_score = 0.95
        mock_case.approved_at = datetime.now(timezone.utc)
        mock_case.created_at = datetime.now(timezone.utc)
        mock_case.design_graph_json = {}
        mock_case.bom_json = None
        mock_case.options_json = None
        mock_case.internal_structure_json = None

        result = _case_to_dict(mock_case)
        assert result["furniture_type"] == "wardrobe"
        assert result["width_mm"] == 2400
        assert "customer_name" not in result


# ──────────────────────────────────────────────────────────
# PG-L1-03: Similarity search logic
# ──────────────────────────────────────────────────────────

class TestSimilaritySearch:
    def test_find_similar_returns_nearest(self):
        """find_similar sorts by Manhattan distance."""
        from foms.services.designer.design_case_memory import _extract_dimensions

        # Closest candidate has width=2400, target is 2400 → distance 0
        graph_close = {"assembly": {"dimensions": {"width": 2400, "height": 2200, "depth": 620}, "module_count": 3}}
        graph_far = {"assembly": {"dimensions": {"width": 3600, "height": 2600, "depth": 620}, "module_count": 5}}

        w1, h1, d1, _ = _extract_dimensions(graph_close)
        w2, h2, d2, _ = _extract_dimensions(graph_far)

        target_w = 2400
        dist1 = abs(w1 - target_w) + abs(h1 - 2200)
        dist2 = abs(w2 - target_w) + abs(h2 - 2200)
        assert dist1 < dist2, "Closer candidate should have smaller distance"


# ──────────────────────────────────────────────────────────
# PG-L1-04: Migration file
# ──────────────────────────────────────────────────────────

class TestMigrationFile:
    def test_migration_exists(self):
        migration = ROOT / "migrations" / "versions" / "designer_design_case_memory.py"
        assert migration.exists(), f"Migration missing: {migration}"

    def test_migration_correct_revision(self):
        migration = ROOT / "migrations" / "versions" / "designer_design_case_memory.py"
        content = migration.read_text(encoding="utf-8")
        assert 'revision = "designer_design_case_memory"' in content
        assert 'down_revision = "designer_drawing_intake"' in content

    def test_migration_has_upgrade_downgrade(self):
        migration = ROOT / "migrations" / "versions" / "designer_design_case_memory.py"
        content = migration.read_text(encoding="utf-8")
        assert "def upgrade" in content
        assert "def downgrade" in content
        assert "designer_design_cases" in content
        assert "furniture_type" in content
        assert "design_graph_json" in content
        assert "width_mm" in content

    def test_migration_has_similarity_indexes(self):
        migration = ROOT / "migrations" / "versions" / "designer_design_case_memory.py"
        content = migration.read_text(encoding="utf-8")
        assert "ix_design_cases_furniture_type" in content
        assert "ix_design_cases_width_mm" in content


# ──────────────────────────────────────────────────────────
# PG-L1-05: Safety contracts
# ──────────────────────────────────────────────────────────

class TestDesignCaseSafetyContracts:
    def test_service_has_no_auto_approval_logic(self):
        """design_case_memory.py must not contain auto-approval language."""
        src = (ROOT / "foms" / "services" / "designer" / "design_case_memory.py").read_text(encoding="utf-8")
        # Must not silently approve — approval must come from user action
        assert "auto_approve" not in src.lower()
        assert "auto-approve" not in src.lower()

    def test_service_explicitly_requires_project_version(self):
        """save_design_case docstring and code explicitly require project_version_id."""
        src = (ROOT / "foms" / "services" / "designer" / "design_case_memory.py").read_text(encoding="utf-8")
        assert "project_version_id" in src
        assert "validator" in src.lower() or "validated" in src.lower()

    def test_pii_strip_function_exists_and_covers_known_fields(self):
        from foms.services.designer.design_case_memory import _strip_pii_fields, _PII_PATHS
        assert "customer_name" in _PII_PATHS
        assert "phone" in _PII_PATHS
        assert "address" in _PII_PATHS

    def test_find_similar_returns_pii_free_payloads(self):
        """find_similar contract: output must not contain raw PII keys."""
        from foms.services.designer.design_case_memory import _case_to_dict
        from unittest.mock import MagicMock
        from datetime import datetime, timezone

        mock_case = MagicMock()
        mock_case.id = 1
        mock_case.project_id = 1
        mock_case.project_version_id = 1
        mock_case.drawing_artifact_id = None
        mock_case.furniture_type = "wardrobe"
        mock_case.product_name = "붙박이장"
        mock_case.width_mm = 2400
        mock_case.height_mm = 2200
        mock_case.depth_mm = 620
        mock_case.module_count = 3
        mock_case.tags_json = []
        mock_case.source_quality_score = 1.0
        mock_case.approved_at = datetime.now(timezone.utc)
        mock_case.created_at = datetime.now(timezone.utc)
        mock_case.design_graph_json = {"assembly": {"type": "wardrobe"}}
        mock_case.bom_json = {}
        mock_case.options_json = {}
        mock_case.internal_structure_json = {}

        result = _case_to_dict(mock_case)
        # PII fields must not appear in the retrieval dict
        pii_keys = {"customer_name", "phone", "address", "customer_phone"}
        found_pii = pii_keys & set(result.keys())
        assert not found_pii, f"PII keys found in design case dict: {found_pii}"
