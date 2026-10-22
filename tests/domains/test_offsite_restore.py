"""오프사이트 복원 스크립트 안전장치 — tools/ops/offsite_restore.py (DB 없이 도는 부분만)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("offsite_restore_under_test", REPO_ROOT / "tools" / "ops" / "offsite_restore.py")
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def test_refuses_railway_public_host_before_connecting() -> None:
    """운영일 수 있는 Railway 공개 주소는 접속 전에 거부한다."""
    with pytest.raises(SystemExit, match="Railway 공개 주소"):
        mod.check_target("postgresql://u:p@yamanote.proxy.rlwy.net:34306/railway", allow_railway=False)


def test_sha256_of_matches_hashlib(tmp_path: Path) -> None:
    f = tmp_path / "x.bin"
    f.write_bytes(b"foms")
    assert mod.sha256_of(f) == "7f65913827fdb9695f43e44196bee993e9d010e308ac41e6a79bf40412c947be"
