"""DESIGNER-RETIRE-01: FOMS Brain(Designer, /wdplanner-v2) 전 표면 삭제 회귀 가드.

P0-13(IDOR·무인증)·P0-24(stored/DOM XSS)를 auth/XSS 패치가 아니라 **표면 제거**로
근본 소멸시킨다. 고정하는 계약:
- designer route(/wdplanner-v2, /wdplanner-v2/app, /api/designer/*) → 404 (라우팅 미존재).
- designer blueprint 가 app.blueprints 에 미등록.
- nav(layout_nav.html) 포함 페이지 실렌더 200 — 삭제된 designer.* url_for BuildError 0.
  (blueprint 만 지우고 nav url_for 를 남기면 여기서 500 → 이게 핵심 가드.)
- persistence(designer_* 테이블 매핑, retention)는 **보존** → 모듈 import 유지.
"""
from __future__ import annotations

import importlib

import pytest


_DESIGNER_GET_ROUTES = [
    "/wdplanner-v2",
    "/wdplanner-v2/app",
    "/wdplanner-v2/app/main.js",
    "/api/designer/projects",
    "/api/designer/ontology/current",
    "/api/designer/evolution/candidates",
]

_DESIGNER_POST_ROUTES = [
    "/api/designer/projects",
    "/api/designer/validate",
    "/api/designer/lui/parse",
]


@pytest.mark.parametrize("path", _DESIGNER_GET_ROUTES)
def test_designer_get_routes_return_404(auth_client, path):
    """모든 designer GET route 는 삭제되어 404 (라우팅 단계에서 미존재)."""
    resp = auth_client.get(path)
    assert resp.status_code == 404, f"{path} → {resp.status_code} (retire 후 404 기대)"


@pytest.mark.parametrize("path", _DESIGNER_POST_ROUTES)
def test_designer_post_routes_return_404(auth_client, path):
    """designer POST API 도 삭제되어 404."""
    resp = auth_client.post(path, json={})
    assert resp.status_code == 404, f"POST {path} → {resp.status_code} (retire 후 404 기대)"


def test_designer_blueprint_not_registered(app):
    """designer blueprint 는 app.blueprints 에 없어야 한다."""
    remaining = [name for name in app.blueprints if name.startswith("designer")]
    assert remaining == [], f"잔존 designer blueprint: {remaining}"


def test_no_designer_url_rules(app):
    """url_map 에 designer.* endpoint / wdplanner / /api/designer 경로가 없어야 한다."""
    endpoints = [r.endpoint for r in app.url_map.iter_rules() if r.endpoint.startswith("designer.")]
    assert endpoints == [], f"잔존 designer endpoint: {endpoints}"
    paths = [str(r) for r in app.url_map.iter_rules()]
    assert not any("wdplanner" in p for p in paths), "잔존 wdplanner 경로"
    assert not any(p.startswith("/api/designer") for p in paths), "잔존 /api/designer 경로"


def test_nav_page_renders_without_designer_build_error(auth_client):
    """nav(layout_nav.html) 포함 페이지가 dangling designer.* url_for 없이 200 렌더.

    핵심 회귀 가드: blueprint 만 지우고 nav url_for 를 남기면 BuildError → 500.
    """
    resp = auth_client.get("/erp/dashboard")
    assert resp.status_code == 200, f"/erp/dashboard → {resp.status_code} (BuildError/500 의심)"
    assert b"/wdplanner-v2" not in resp.data, "nav 에 삭제된 designer 링크 잔존"


def test_persistence_designer_models_preserved():
    """designer_* 테이블 매핑(retention)은 보존 — persistence 모듈 import 유지."""
    mod = importlib.import_module("foms.persistence.designer.models")
    assert mod is not None
