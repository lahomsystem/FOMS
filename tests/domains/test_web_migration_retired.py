"""MIG-WEB-RETIRE-01: 위험 웹 마이그레이션 라우트·helper 제거 회귀 가드.

P0-1(웹 migration reset이 원본 사전검증 전 WDC/main 데이터를 삭제) 제거를 고정한다:
- `/admin/migration` GET·POST → 404 (route 삭제).
- `scripts.migrations.web_migration` import → 실패 (위험 helper 파일 삭제).
- admin 페이지 실렌더 200 (삭제된 route를 가리키는 dangling url_for BuildError 없음).
"""
from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize("method", ["get", "post"])
def test_admin_migration_route_removed(client, method):
    """`/admin/migration` 은 삭제되어 404 (라우팅 단계에서 미존재)."""
    response = getattr(client, method)("/admin/migration")
    assert response.status_code == 404


def test_web_migration_helper_module_gone():
    """위험 reset helper 모듈은 import 불가여야 한다(파일 삭제)."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("scripts.migrations.web_migration")


def test_admin_page_renders_without_build_error(auth_client):
    """admin 페이지가 dangling migration url_for 없이 정상 렌더된다(BuildError 0)."""
    response = auth_client.get("/admin")
    assert response.status_code == 200
