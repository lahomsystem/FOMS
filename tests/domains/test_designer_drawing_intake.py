"""PG-B3: Drawing Intake + Persistent Extraction Data Model Tests.

Tests the ORM model shape, relationship, and safety contracts.
(No live DB — uses SQLite in-memory via pytest fixtures.)
"""

from __future__ import annotations

import pytest


class TestDrawingArtifactModel:
    """DesignerDrawingArtifact model shape."""

    def test_model_importable(self):
        from foms.persistence.designer.models import DesignerDrawingArtifact
        assert DesignerDrawingArtifact is not None

    def test_model_has_required_columns(self):
        from foms.persistence.designer.models import DesignerDrawingArtifact
        cols = {c.key for c in DesignerDrawingArtifact.__table__.columns}
        required = {"id", "project_id", "file_url", "file_type", "page_count",
                    "source", "status", "created_at"}
        missing = required - cols
        assert not missing, f"Missing columns: {missing}"

    def test_model_has_pages_relationship(self):
        from foms.persistence.designer.models import DesignerDrawingArtifact
        assert hasattr(DesignerDrawingArtifact, "pages")

    def test_intake_does_not_auto_create_project_version(self):
        """Artifact model has no project_version_id — intake is separate from version creation."""
        from foms.persistence.designer.models import DesignerDrawingArtifact
        cols = {c.key for c in DesignerDrawingArtifact.__table__.columns}
        assert "project_version_id" not in cols, (
            "Artifact must not have project_version_id — "
            "intake never creates a project version directly."
        )


class TestDrawingPageModel:
    """DesignerDrawingPage model shape."""

    def test_model_importable(self):
        from foms.persistence.designer.models import DesignerDrawingPage
        assert DesignerDrawingPage is not None

    def test_model_has_required_columns(self):
        from foms.persistence.designer.models import DesignerDrawingPage
        cols = {c.key for c in DesignerDrawingPage.__table__.columns}
        required = {"id", "artifact_id", "page_no", "template_key", "created_at"}
        missing = required - cols
        assert not missing, f"Missing columns: {missing}"

    def test_model_has_extractions_relationship(self):
        from foms.persistence.designer.models import DesignerDrawingPage
        assert hasattr(DesignerDrawingPage, "extractions")


class TestDrawingExtractionModel:
    """DesignerDrawingExtraction model shape and safety."""

    def test_model_importable(self):
        from foms.persistence.designer.models import DesignerDrawingExtraction
        assert DesignerDrawingExtraction is not None

    def test_model_has_required_columns(self):
        from foms.persistence.designer.models import DesignerDrawingExtraction
        cols = {c.key for c in DesignerDrawingExtraction.__table__.columns}
        required = {"id", "page_id", "extractor_version", "parsed_json",
                    "status", "model_name", "cost_usd", "created_at"}
        missing = required - cols
        assert not missing, f"Missing columns: {missing}"

    def test_status_default_is_draft(self):
        """Extraction status default must be 'draft' (not auto-approved)."""
        from foms.persistence.designer.models import DesignerDrawingExtraction
        status_col = DesignerDrawingExtraction.__table__.columns["status"]
        default = str(status_col.default.arg) if status_col.default else None
        assert default == "draft", (
            f"Extraction status default must be 'draft', got {default!r}. "
            "Extractions must never be auto-approved."
        )

    def test_model_has_candidates_relationship(self):
        from foms.persistence.designer.models import DesignerDrawingExtraction
        assert hasattr(DesignerDrawingExtraction, "candidates")


class TestExtractionCandidateModel:
    """DesignerExtractionCandidate model safety."""

    def test_model_importable(self):
        from foms.persistence.designer.models import DesignerExtractionCandidate
        assert DesignerExtractionCandidate is not None

    def test_model_has_required_columns(self):
        from foms.persistence.designer.models import DesignerExtractionCandidate
        cols = {c.key for c in DesignerExtractionCandidate.__table__.columns}
        required = {"id", "extraction_id", "furniture_type", "extracted_params_json",
                    "unresolved_fields_json", "confidence", "approved", "created_at"}
        missing = required - cols
        assert not missing, f"Missing columns: {missing}"

    def test_approved_default_is_false(self):
        """Candidate approved must default to False — never auto-approved."""
        from foms.persistence.designer.models import DesignerExtractionCandidate
        approved_col = DesignerExtractionCandidate.__table__.columns["approved"]
        default = approved_col.default.arg if approved_col.default else None
        assert default is False or default == False, (
            f"Candidate approved default must be False, got {default!r}. "
            "Candidates must never be auto-approved — human review required."
        )

    def test_unresolved_fields_json_column_exists(self):
        """unresolved_fields_json gates approval — must exist."""
        from foms.persistence.designer.models import DesignerExtractionCandidate
        cols = {c.key for c in DesignerExtractionCandidate.__table__.columns}
        assert "unresolved_fields_json" in cols, (
            "unresolved_fields_json must exist to gate approval."
        )


class TestMigrationFileExists:
    """Migration file for PG-B3 drawing intake exists."""

    def test_migration_file_exists(self):
        from pathlib import Path
        migration = Path(__file__).parent.parent.parent / "migrations" / "versions" / "designer_drawing_intake.py"
        assert migration.exists(), f"Migration file missing: {migration}"

    def test_migration_has_upgrade_and_downgrade(self):
        from pathlib import Path
        content = (Path(__file__).parent.parent.parent / "migrations" / "versions" / "designer_drawing_intake.py").read_text(encoding="utf-8")
        assert "def upgrade" in content
        assert "def downgrade" in content
        assert "designer_drawing_artifacts" in content
        assert "designer_drawing_pages" in content
        assert "designer_drawing_extractions" in content
        assert "designer_extraction_candidates" in content
