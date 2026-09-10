"""tests/harness 공용 픽스처 — 훅 로그를 실 파일에서 격리한다(ablation v2 §5, 2026-09-10).

2026-09-09 감사: 실 `SHELL_GUARD_LOG.md` 300행 중 164행(55%)이 이 디렉토리의 테스트가
훅을 subprocess 로 돌리며 남긴 오염이었다. 모든 하네스 테스트는 `FOMS_HARNESS_LOG_DIR` 를
tmp 로 받는다 — 훅·공용 유틸이 이 env 를 존중하는지는 `test_harness_drift_guard.py` 가 본다.
"""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_harness_logs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """실 `docs/harness/logs` 대신 tmp 로그 디렉토리를 모든 테스트에 주입한다."""
    log_dir = tmp_path / "_harness_logs"
    log_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("FOMS_HARNESS_LOG_DIR", str(log_dir))
    return log_dir
