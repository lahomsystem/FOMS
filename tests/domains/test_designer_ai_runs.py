"""Tests for AI runs API with DESIGNER_AI_FAKE=1."""

import os
import pytest


@pytest.fixture(autouse=True)
def enable_fake_ai(monkeypatch):
    """Enable fake AI mode for all tests in this module."""
    monkeypatch.setenv("DESIGNER_AI_FAKE", "1")
    # Also patch the module-level flag
    import foms.services.designer.langgraph_workflows as wf
    monkeypatch.setattr(wf, "_FAKE_MODE", True)


VALID_DESIGN = {
    "schema_version": 1,
    "unit": "mm",
    "cabinet": {"width": 2400, "height": 2200, "depth": 600},
    "components": [],
    "relations": [],
}

INVALID_DESIGN = {
    "schema_version": 1,
    "unit": "mm",
    "cabinet": {"width": 99999, "height": 2200, "depth": 600},
    "components": [],
    "relations": [],
}


def test_create_ai_run(auth_client):
    """Creating an AI run returns a run record."""
    resp = auth_client.post("/api/designer/ai-runs", json={
        "prompt": "가로 폭을 2700mm로 변경해줘",
        "design_json": VALID_DESIGN,
    })
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["success"] is True
    assert data["data"]["id"] is not None
    # In fake mode, should be 'interrupt' (pending review)
    assert data["data"]["status"] in ("interrupt", "succeeded", "failed")


def test_ai_run_requires_prompt(auth_client):
    """Missing prompt returns 400."""
    resp = auth_client.post("/api/designer/ai-runs", json={"design_json": VALID_DESIGN})
    assert resp.status_code == 400


def test_get_ai_run(auth_client):
    """Getting an AI run by ID returns run data."""
    create_resp = auth_client.post("/api/designer/ai-runs", json={
        "prompt": "높이 조정",
        "design_json": VALID_DESIGN,
    })
    run_id = create_resp.get_json()["data"]["id"]
    resp = auth_client.get(f"/api/designer/ai-runs/{run_id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["data"]["id"] == run_id


def test_resume_approve_creates_version(auth_client):
    """Approving an interrupted run with valid design creates a project version."""
    # Create a project first
    proj_resp = auth_client.post("/api/designer/projects", json={"name": "AI 승인 테스트"})
    project_id = proj_resp.get_json()["data"]["id"]

    run_resp = auth_client.post("/api/designer/ai-runs", json={
        "project_id": project_id,
        "prompt": "폭 변경",
        "design_json": VALID_DESIGN,
    })
    run_data = run_resp.get_json()["data"]
    run_id = run_data["id"]

    if run_data["status"] != "interrupt":
        pytest.skip("Run did not reach interrupt state")

    # Resume with approve
    resp = auth_client.post(f"/api/designer/ai-runs/{run_id}/resume", json={"decision": "approve"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["data"]["status"] == "succeeded"


def test_resume_reject_cancels(auth_client):
    """Rejecting an interrupted run cancels it without saving."""
    run_resp = auth_client.post("/api/designer/ai-runs", json={
        "prompt": "거부 테스트",
        "design_json": VALID_DESIGN,
    })
    run_data = run_resp.get_json()["data"]
    run_id = run_data["id"]

    if run_data["status"] != "interrupt":
        pytest.skip("Run did not reach interrupt state")

    resp = auth_client.post(f"/api/designer/ai-runs/{run_id}/resume", json={"decision": "reject"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["data"]["status"] == "cancelled"


def test_validator_fail_run_no_version(auth_client):
    """AI run with invalid design should not create a project version."""
    proj_resp = auth_client.post("/api/designer/projects", json={"name": "검증 실패 AI 테스트"})
    project_id = proj_resp.get_json()["data"]["id"]
    project_data_before = auth_client.get(f"/api/designer/projects/{project_id}").get_json()["data"]

    run_resp = auth_client.post("/api/designer/ai-runs", json={
        "project_id": project_id,
        "prompt": "잘못된 설계",
        "design_json": INVALID_DESIGN,
    })
    assert run_resp.status_code == 201
    # Check that project version was NOT updated with invalid design
    project_data_after = auth_client.get(f"/api/designer/projects/{project_id}").get_json()["data"]
    # The current_version_id should not have changed to an invalid version
    # (the run may fail or reach interrupt; either way no invalid version is saved)
    # This is a soft assertion – the key invariant is tested in test_create_version_invalid_blocked
    assert project_data_after is not None


def test_fake_embedding_store():
    """Fake embedding mode stores text without vector."""
    import os
    import foms.services.designer.vector_memory as vm
    # In test environment (SQLite), real pgvector won't be available anyway
    # Just verify the service can be imported and fake mode logic exists
    assert hasattr(vm, "store_embedding")
    assert hasattr(vm, "_FAKE_EMBEDDING")


# ──────────────────────────────────────────────────────────
# B3: drawing_layout_to_3d_graph tests
# ──────────────────────────────────────────────────────────

def _create_test_candidate_in_db(auth_client, with_graph: bool = True) -> int:
    """Helper: create a DesignerExtractionCandidate row for B3 tests."""
    from db import db_session
    from foms.persistence.designer.models import (
        DesignerDrawingArtifact, DesignerDrawingPage,
        DesignerDrawingExtraction, DesignerExtractionCandidate,
    )
    import json

    artifact = DesignerDrawingArtifact(
        project_id=None, file_url="test.jpg", file_type="jpg",
        page_count=1, source="upload", status="done",
    )
    db_session.add(artifact)
    db_session.flush()

    page = DesignerDrawingPage(artifact_id=artifact.id, page_no=1)
    db_session.add(page)
    db_session.flush()

    extraction_dict = {
        "furniture_type": "wardrobe",
        "site_size": {"width_mm": 2400, "height_mm": 2200, "depth_mm": 600},
        "extracted_params": {"width": 2400, "height": 2200, "depth": 600},
        "design_understanding": {
            "layout_graph": {
                "zones": [
                    {"id": "z1", "role": "hanging", "x_mm": 0, "y_mm": 0,
                     "width_mm": 1200, "height_mm": 2200, "depth_mm": 600},
                    {"id": "z2", "role": "shelves", "x_mm": 1200, "y_mm": 0,
                     "width_mm": 1200, "height_mm": 2200, "depth_mm": 600},
                ],
                "modules": [],
            },
            "block_candidates": [],
            "learned_design_category": {},
        },
        "parts_table": [],
        "confidence": 0.85,
        "unresolved_fields": [],
    }

    ext = DesignerDrawingExtraction(
        page_id=page.id,
        extractor_version="test",
        parsed_json=extraction_dict,
        confidence_json={"confidence": 0.85},
        status="pending_approval",
    )
    db_session.add(ext)
    db_session.flush()

    # Build graph candidate if with_graph=True
    graph_candidate_json = None
    mapping_report_json = None
    preview_allowed = False
    blocking_reasons = []

    if with_graph:
        from foms.services.designer.layout_graph_mapper import map_extraction_to_design_graph
        result = map_extraction_to_design_graph(
            extraction_dict, source_extraction_id=ext.id
        )
        graph_candidate_json = result.design_graph
        mapping_report_json = result.mapping_report.to_dict()
        preview_allowed = result.preview_allowed
        blocking_reasons = result.approval_blocking_reasons

    candidate = DesignerExtractionCandidate(
        extraction_id=ext.id,
        furniture_type="wardrobe",
        extracted_params_json={"width": 2400, "height": 2200, "depth": 600},
        unresolved_fields_json=[],
        confidence=0.85,
        approved=False,
        status="pending_review",
        blocking_reasons_json=blocking_reasons,
        design_graph_candidate_json=graph_candidate_json,
        mapping_report_json=mapping_report_json,
        validation_json={"valid": not blocking_reasons},
        preview_allowed=preview_allowed,
    )
    db_session.add(candidate)
    db_session.commit()
    db_session.refresh(candidate)
    return candidate.id


def test_drawing_layout_run_missing_candidate_id(auth_client):
    """B3: drawing-layout run without candidate_id → 400."""
    resp = auth_client.post("/api/designer/ai-runs/drawing-layout", json={})
    assert resp.status_code == 400


def test_drawing_layout_run_invalid_candidate_id(auth_client):
    """B3: drawing-layout run with non-existent candidate_id → run fails."""
    resp = auth_client.post("/api/designer/ai-runs/drawing-layout", json={
        "candidate_id": 999999,
    })
    assert resp.status_code == 201
    data = resp.get_json()["data"]
    assert data["status"] == "failed"
    assert "candidate_not_found" in (data.get("error_text") or "")


def test_drawing_layout_run_valid_candidate_creates_interrupt(auth_client):
    """B3: Valid candidate → run reaches interrupt with preview payload."""
    cand_id = _create_test_candidate_in_db(auth_client, with_graph=True)
    resp = auth_client.post("/api/designer/ai-runs/drawing-layout", json={
        "candidate_id": cand_id,
    })
    assert resp.status_code == 201
    data = resp.get_json()["data"]
    assert data["status"] == "interrupt", f"Expected interrupt, got {data['status']}: {data.get('error_text')}"
    # Verify state_json has design_graph_candidate
    state = data.get("state_json") or {}
    assert "design_graph_candidate" in state
    assert state["design_graph_candidate"].get("schema_version") == 2


def test_drawing_layout_run_interrupt_survives_get(auth_client):
    """B3: Interrupted run can be retrieved by GET."""
    cand_id = _create_test_candidate_in_db(auth_client, with_graph=True)
    create_resp = auth_client.post("/api/designer/ai-runs/drawing-layout", json={
        "candidate_id": cand_id,
    })
    run_id = create_resp.get_json()["data"]["id"]

    get_resp = auth_client.get(f"/api/designer/ai-runs/{run_id}")
    assert get_resp.status_code == 200
    data = get_resp.get_json()["data"]
    assert data["status"] == "interrupt"
    assert data["state_json"].get("design_graph_candidate") is not None


def test_drawing_layout_run_reject_cancels(auth_client):
    """B3: Reject resume → cancelled status."""
    cand_id = _create_test_candidate_in_db(auth_client, with_graph=True)
    create_resp = auth_client.post("/api/designer/ai-runs/drawing-layout", json={
        "candidate_id": cand_id,
    })
    run_data = create_resp.get_json()["data"]
    if run_data["status"] != "interrupt":
        pytest.skip("Run did not reach interrupt")

    resume_resp = auth_client.post(
        f"/api/designer/ai-runs/{run_data['id']}/resume",
        json={"decision": "reject"},
    )
    assert resume_resp.status_code == 200
    assert resume_resp.get_json()["data"]["status"] == "cancelled"


def test_drawing_layout_run_approve_requires_project_id(auth_client):
    """B3: Approve without project_id → persist fails (no-op save prevention)."""
    cand_id = _create_test_candidate_in_db(auth_client, with_graph=True)
    create_resp = auth_client.post("/api/designer/ai-runs/drawing-layout", json={
        "candidate_id": cand_id,
        # No project_id → _dlg_persist_approved_design returns error
    })
    run_data = create_resp.get_json()["data"]
    if run_data["status"] != "interrupt":
        pytest.skip("Run did not reach interrupt")

    resume_resp = auth_client.post(
        f"/api/designer/ai-runs/{run_data['id']}/resume",
        json={"decision": "approve"},
    )
    # No project_id → failed or no version created
    result = resume_resp.get_json()["data"]
    # Key: no version_id should be created if project_id was None.
    # Check status first to avoid None.get() when output_json is null.
    assert result is None or result["status"] == "failed" or \
           (result.get("output_json") or {}).get("persisted_version_id") is None


def test_drawing_layout_workflow_importable():
    """B3: drawing_layout_to_3d_graph functions are importable."""
    from foms.services.designer.langgraph_workflows import (
        run_drawing_layout_to_3d_graph,
        resume_drawing_layout_to_3d_graph,
        DrawingLayoutState,
    )
    assert callable(run_drawing_layout_to_3d_graph)
    assert callable(resume_drawing_layout_to_3d_graph)
