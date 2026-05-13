"""Tests for /api/designer/projects endpoints."""

import pytest


VALID_DESIGN = {
    "schema_version": 1,
    "unit": "mm",
    "cabinet": {"width": 2400, "height": 2200, "depth": 600},
    "components": [
        {"id": "left-side", "type": "panel", "name": "좌측판",
         "width": 18, "height": 2200, "depth": 600,
         "position": {"x": 0, "y": 0, "z": 0}},
    ],
    "relations": [],
}

INVALID_DESIGN = {
    "schema_version": 1,
    "unit": "mm",
    "cabinet": {"width": 99999, "height": 2200, "depth": 600},
    "components": [],
    "relations": [],
}


def test_create_project(auth_client):
    """Creating a project returns 201 with project data."""
    resp = auth_client.post("/api/designer/projects", json={"name": "테스트 프로젝트"})
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["success"] is True
    assert data["data"]["name"] == "테스트 프로젝트"
    assert data["data"]["id"] is not None


def test_list_projects(auth_client):
    """Listing projects returns a list."""
    auth_client.post("/api/designer/projects", json={"name": "목록테스트"})
    resp = auth_client.get("/api/designer/projects")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert isinstance(data["data"], list)


def test_get_project(auth_client):
    """Getting a project by ID returns its data."""
    create_resp = auth_client.post("/api/designer/projects", json={"name": "조회테스트"})
    project_id = create_resp.get_json()["data"]["id"]
    resp = auth_client.get(f"/api/designer/projects/{project_id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["data"]["id"] == project_id


def test_get_project_not_found(auth_client):
    """Non-existent project returns 404."""
    resp = auth_client.get("/api/designer/projects/99999")
    assert resp.status_code == 404


def test_create_version_valid(auth_client):
    """Creating a version with valid design succeeds."""
    create_resp = auth_client.post("/api/designer/projects", json={"name": "버전테스트"})
    project_id = create_resp.get_json()["data"]["id"]
    resp = auth_client.post(f"/api/designer/projects/{project_id}/versions", json={"design_json": VALID_DESIGN})
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["success"] is True
    assert data["data"]["design_json"]["cabinet"]["width"] == 2400


def test_create_version_invalid_blocked(auth_client):
    """Invalid design version is blocked (422)."""
    create_resp = auth_client.post("/api/designer/projects", json={"name": "차단테스트"})
    project_id = create_resp.get_json()["data"]["id"]
    resp = auth_client.post(f"/api/designer/projects/{project_id}/versions", json={"design_json": INVALID_DESIGN})
    assert resp.status_code == 422
    data = resp.get_json()
    assert data["success"] is False
    assert data["error"]["code"] == "VALIDATION_FAILED"
