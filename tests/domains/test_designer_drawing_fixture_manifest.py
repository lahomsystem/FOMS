"""PG-B2: Drawing Fixture Manifest + Corpus Harness Tests.

Tests the drawing fixture corpus infrastructure:
- Manifest structure and completeness (17 fixtures)
- Expected JSON schema validation
- Fixture manager CLI contract
- Scorecard runner with available fixtures
- Corpus progression gates
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
MANIFEST_PATH = ROOT / "tests" / "fixtures" / "designer" / "drawings" / "manifest.json"
EXPECTED_DIR = MANIFEST_PATH.parent / "expected_extractions"
SCHEMA_PATH = EXPECTED_DIR / "_SCHEMA.json"
FIXTURE_TOOL = ROOT / "tools" / "designer" / "build_drawing_fixture_manifest.py"


# ──────────────────────────────────────────────────────────
# PG-B2-01: Manifest structure tests
# ──────────────────────────────────────────────────────────

class TestManifestStructure:
    """Manifest v1.0 has 17 fixtures with correct structure."""

    def test_manifest_exists(self):
        """tests/fixtures/designer/drawings/manifest.json exists."""
        assert MANIFEST_PATH.exists(), f"Manifest missing: {MANIFEST_PATH}"

    def test_manifest_version(self):
        """Manifest version is 1.0."""
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            data = json.load(f)
        assert data.get("version") == "1.0"

    def test_manifest_has_17_fixtures(self):
        """Manifest contains exactly 17 fixtures for corpus v1."""
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            data = json.load(f)
        count = len(data.get("fixtures", []))
        assert count == 17, f"Expected 17 fixtures, got {count}"

    def test_all_fixtures_have_required_fields(self):
        """Every fixture has: id, category, description, file_path, file_status, furniture_type_expected, expected_json_path, approval_status."""
        required = {
            "id", "category", "description", "file_path",
            "file_status", "furniture_type_expected",
            "expected_json_path", "approval_status"
        }
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            data = json.load(f)
        for fix in data["fixtures"]:
            missing = required - set(fix.keys())
            assert not missing, f"Fixture {fix.get('id')} missing: {missing}"

    def test_fixture_ids_unique(self):
        """All fixture IDs are unique."""
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            data = json.load(f)
        ids = [f["id"] for f in data["fixtures"]]
        assert len(ids) == len(set(ids)), f"Duplicate fixture IDs: {[x for x in ids if ids.count(x) > 1]}"

    def test_furniture_types_valid(self):
        """All fixtures have valid furniture_type_expected."""
        valid = {"wardrobe", "shoe_rack", "kitchen_base", "kitchen_wall", "custom_storage"}
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            data = json.load(f)
        for fix in data["fixtures"]:
            ft = fix.get("furniture_type_expected")
            assert ft in valid, f"Fixture {fix['id']} invalid type: {ft!r}"

    def test_fixture_type_distribution(self):
        """Corpus covers required furniture types: wardrobe, shoe_rack, kitchen, other."""
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            data = json.load(f)
        types = {f["furniture_type_expected"] for f in data["fixtures"]}
        assert "wardrobe" in types, "Must have wardrobe fixtures"
        assert "shoe_rack" in types, "Must have shoe_rack fixtures"
        assert "kitchen_base" in types or "kitchen_wall" in types, "Must have kitchen fixtures"

    def test_wardrobe_fixture_count(self):
        """Wardrobe fixtures cover >= 10 entries (main product type)."""
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            data = json.load(f)
        wardrobe_count = sum(
            1 for f in data["fixtures"]
            if f["furniture_type_expected"] == "wardrobe"
        )
        assert wardrobe_count >= 10, f"Need >= 10 wardrobe fixtures, got {wardrobe_count}"

    def test_expected_json_paths_reference_correct_dir(self):
        """All expected_json_path values point into expected_extractions/ directory."""
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            data = json.load(f)
        for fix in data["fixtures"]:
            path = fix.get("expected_json_path", "")
            assert "expected_extractions" in path, (
                f"Fixture {fix['id']} expected_json_path should be in expected_extractions/: {path}"
            )

    def test_all_fixtures_start_as_pending(self):
        """New corpus: all 17 fixtures start as file_status=pending, approval_status=draft."""
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            data = json.load(f)
        for fix in data["fixtures"]:
            fst = fix.get("file_status")
            ast = fix.get("approval_status")
            assert fst == "pending", f"{fix['id']}: expected file_status=pending, got {fst!r}"
            assert ast == "draft", f"{fix['id']}: expected approval_status=draft, got {ast!r}"

    def test_corpus_plan_exists(self):
        """Manifest has corpus_plan with v0/v1 entries."""
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            data = json.load(f)
        cp = data.get("corpus_plan", {})
        assert "v0" in cp, "corpus_plan missing v0"
        assert "v1" in cp, "corpus_plan missing v1"
        assert cp["v1"]["target"] == 17


# ──────────────────────────────────────────────────────────
# PG-B2-02: Expected JSON schema tests
# ──────────────────────────────────────────────────────────

class TestExpectedJsonSchema:
    """Expected JSON schema definition exists and is correct."""

    def test_schema_file_exists(self):
        """expected_extractions/_SCHEMA.json exists."""
        assert SCHEMA_PATH.exists(), f"Schema missing: {SCHEMA_PATH}"

    def test_schema_has_required_fields(self):
        """Schema defines all required extraction fields."""
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            data = json.load(f)
        fields = data.get("_fields", {})
        required = {
            "drawing_id", "page_no", "furniture_type",
            "parts_table", "dimension_candidates", "views",
            "site_size", "customer_name"
        }
        missing = required - set(fields.keys())
        assert not missing, f"Schema missing fields: {missing}"

    def test_schema_has_valid_example(self):
        """Schema has a valid _example with correct types."""
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            data = json.load(f)
        ex = data.get("_example", {})
        assert isinstance(ex.get("drawing_id"), str)
        assert isinstance(ex.get("page_no"), int)
        assert isinstance(ex.get("parts_table"), list)
        assert isinstance(ex.get("dimension_candidates"), list)
        assert isinstance(ex.get("views"), list)
        assert isinstance(ex.get("site_size"), dict)

    def test_expected_extractions_dir_exists(self):
        """expected_extractions/ directory exists."""
        assert EXPECTED_DIR.exists(), f"Missing dir: {EXPECTED_DIR}"


# ──────────────────────────────────────────────────────────
# PG-B2-03: Fixture tool CLI contract
# ──────────────────────────────────────────────────────────

class TestFixtureToolContract:
    """tools/designer/build_drawing_fixture_manifest.py CLI contract."""

    def test_tool_file_exists(self):
        """build_drawing_fixture_manifest.py exists."""
        assert FIXTURE_TOOL.exists(), f"Tool missing: {FIXTURE_TOOL}"

    def test_tool_status_command_runs(self):
        """'status' command executes without error."""
        result = subprocess.run(
            [sys.executable, str(FIXTURE_TOOL), "status"],
            capture_output=True, text=True, cwd=str(ROOT)
        )
        assert result.returncode == 0, (
            f"status command failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "17" in result.stdout, "Status should show 17 fixtures"

    def test_tool_list_command_runs(self):
        """'list' command executes and shows all 17 fixtures."""
        result = subprocess.run(
            [sys.executable, str(FIXTURE_TOOL), "list"],
            capture_output=True, text=True, cwd=str(ROOT)
        )
        assert result.returncode == 0, (
            f"list command failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        # Should show all fixture IDs
        assert "wrd_001" in result.stdout
        assert "shr_001" in result.stdout
        assert "ktc_001" in result.stdout

    def test_tool_validate_command_on_empty_corpus(self):
        """'validate' command succeeds on empty corpus (no expected JSONs yet)."""
        result = subprocess.run(
            [sys.executable, str(FIXTURE_TOOL), "validate"],
            capture_output=True, text=True, cwd=str(ROOT)
        )
        assert result.returncode == 0, (
            f"validate failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        # 0 files validated is OK (all pending)
        assert "0" in result.stdout or "OK" in result.stdout

    def test_generate_tool_exists(self):
        """tools/designer/generate_expected_json.py exists."""
        gen_tool = ROOT / "tools" / "designer" / "generate_expected_json.py"
        assert gen_tool.exists(), f"Generator tool missing: {gen_tool}"


# ──────────────────────────────────────────────────────────
# PG-B2-04: Corpus progression gates
# ──────────────────────────────────────────────────────────

class TestCorpusProgressionGates:
    """Track corpus v0/v1 progression status."""

    def test_corpus_v0_not_yet_complete(self):
        """Corpus v0 (5 approved) not complete — files not yet provided."""
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            data = json.load(f)
        approved = sum(
            1 for f in data["fixtures"] if f.get("approval_status") == "approved"
        )
        # At this stage, no files provided yet, so 0 approved is expected
        assert approved < 5, (
            f"Corpus v0 gate: expected < 5 approved (files not yet provided), got {approved}. "
            "If 5+ are approved, update this test."
        )

    def test_corpus_v1_not_yet_complete(self):
        """Corpus v1 (17 approved) not complete — files not yet provided."""
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            data = json.load(f)
        approved = sum(
            1 for f in data["fixtures"] if f.get("approval_status") == "approved"
        )
        assert approved < 17, (
            f"Corpus v1 requires 17 approved, got {approved}. "
            "If all 17 are approved, update PRODUCT_GRADE_GATES."
        )

    def test_scorecard_runner_on_empty_corpus(self):
        """Scorecard runner returns empty report on all-pending corpus."""
        from foms.services.designer.extraction_scorecard import (
            run_scorecard_from_manifest, load_fixture_manifest, get_available_fixtures,
        )
        manifest = load_fixture_manifest(MANIFEST_PATH)
        available = get_available_fixtures(manifest)
        assert len(available) == 0, (
            f"Expected 0 available (files pending), got {len(available)}"
        )
        report = run_scorecard_from_manifest(MANIFEST_PATH, lambda p: {})
        assert report.total_fixtures == 0

    def test_expected_json_schema_for_future_approved_fixtures(self):
        """When expected JSONs ARE present, they must conform to schema."""
        existing_jsons = list(EXPECTED_DIR.glob("*_expected.json"))
        if not existing_jsons:
            pytest.skip("No expected JSONs present yet — will validate when files are added")

        required_fields = {
            "drawing_id", "page_no", "furniture_type",
            "parts_table", "dimension_candidates", "views", "site_size"
        }
        errors = []
        for jpath in existing_jsons:
            if jpath.name.startswith("_"):
                continue
            with open(jpath, encoding="utf-8") as f:
                ej = json.load(f)
            missing = required_fields - set(ej.keys())
            if missing:
                errors.append(f"{jpath.name}: missing {missing}")
        assert not errors, f"Schema violations: {errors}"


# ──────────────────────────────────────────────────────────
# PG-B2-05: README and documentation
# ──────────────────────────────────────────────────────────

class TestFixtureDocumentation:
    def test_readme_exists(self):
        """tests/fixtures/designer/drawings/README.md exists."""
        readme = MANIFEST_PATH.parent / "README.md"
        assert readme.exists(), f"README missing: {readme}"

    def test_readme_mentions_ingest_workflow(self):
        """README documents the ingest workflow."""
        readme = MANIFEST_PATH.parent / "README.md"
        content = readme.read_text(encoding="utf-8")
        assert "ingest" in content.lower(), "README should document the ingest workflow"
        assert "approve" in content.lower(), "README should document the approval workflow"
        assert "GEMINI_API_KEY" in content or "gemini" in content.lower(), (
            "README should mention Gemini API"
        )
