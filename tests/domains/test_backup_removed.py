"""BACKUP-01: deprecated 로컬 pg_dump 백업 서비스 제거 회귀 가드.

2026-06-05 백업 은퇴(blueprint 등록 해제·admin UI 제거)로 이미 런타임에서
도달 불가였던 dead code `foms/api/backup.py`(`SimpleBackupSystem` REST 래퍼)와
`foms/services/admin/backup_service.py`(pg_dump subprocess)를 제거한다.
production 백업 정본은 Railway PostgreSQL 스냅샷, 로컬 운영자 백업은
`scripts/ops/sync_local_to_railway.ps1` — restore 절차는 docs/runbooks/backup-restore.md.

고정 계약:
- backup 모듈 2종 import → ModuleNotFoundError (파일 삭제).
- `/api/simple_backup`(POST)·`/api/backup_status`(GET) → 404 (미등록).
- foms/ 런타임 패키지 어떤 모듈도 backup_service/foms.api.backup import 안 함 (호출처 0, 정적).
- app 부팅 정상 (APP_OK) — 제거 후 dangling import·BuildError 없음.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

import foms


@pytest.mark.parametrize(
    "module_name",
    ["foms.api.backup", "foms.services.admin.backup_service"],
)
def test_backup_modules_removed(module_name):
    """제거된 backup 모듈은 import 불가여야 한다(파일 삭제)."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module_name)


def test_simple_backup_route_removed(client):
    """`POST /api/simple_backup` 은 미등록 → 404 (라우팅 단계에서 미존재)."""
    assert client.post("/api/simple_backup").status_code == 404


def test_backup_status_route_removed(client):
    """`GET /api/backup_status` 은 미등록 → 404."""
    assert client.get("/api/backup_status").status_code == 404


def test_no_runtime_importers_of_backup(app):
    """foms/ 런타임 패키지 어떤 모듈도 backup_service/foms.api.backup 를 참조하지 않는다(호출처 0)."""
    foms_dir = Path(foms.__file__).resolve().parent
    forbidden = ("backup_service", "foms.api.backup")
    offenders = []
    for py in foms_dir.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        if any(token in text for token in forbidden):
            offenders.append(str(py))
    assert offenders == [], f"backup 참조 잔존(호출처 0 위반): {offenders}"


def test_app_boots_after_removal(app):
    """제거 후에도 app 부팅 정상(APP_OK) — url_map 에 backup 라우트 없음."""
    rules = [r.rule for r in app.url_map.iter_rules()]
    assert "/api/simple_backup" not in rules
    assert "/api/backup_status" not in rules
