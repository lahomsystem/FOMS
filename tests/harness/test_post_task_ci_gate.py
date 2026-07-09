"""Unit tests for the Cursor CI-GATE 논블로킹 루프 (`.cursor/hooks/post_task_quality_check.py`).

`_consume_ci_gate_marker` 가 `ci_watch.py --quick` 결과별로 마커를 유지/삭제하고
올바른 리마인더를 만드는지 검증한다. quick subprocess(`_run_quick`)는 모킹하며
gh 는 절대 실호출하지 않는다.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_PATH = REPO_ROOT / ".cursor" / "hooks" / "post_task_quality_check.py"
MARKER_REL = Path("docs") / "harness" / "runtime" / ".cursor_ci_gate_pending.json"


def _load_module():
    """Cursor 훅 모듈을 파일 경로에서 직접 로드한다(.cursor/hooks 를 sys.path 에 추가)."""
    hooks_dir = str(HOOK_PATH.parent)
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)
    spec = importlib.util.spec_from_file_location("post_task_qc_under_test", HOOK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def mod():
    return _load_module()


def _make_marker(root: Path, *, branch: str = "deploy", age_sec: float = 0.0) -> Path:
    """tmp project_root 에 CI-GATE 마커를 기록하고 경로를 반환한다."""
    marker = root / MARKER_REL
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        json.dumps({"branch": branch, "ts": time.time() - age_sec, "command": "git push origin deploy"}),
        encoding="utf-8",
    )
    return marker


def test_no_marker_returns_none(mod, tmp_path) -> None:
    assert mod._consume_ci_gate_marker(str(tmp_path)) is None


def test_marker_kept_when_in_progress(mod, monkeypatch, tmp_path) -> None:
    """exit 4(진행 중) → 논블로킹 안내 + 마커 유지(다음 턴 자동 재확인)."""
    marker = _make_marker(tmp_path)
    monkeypatch.setattr(
        mod, "_run_quick", lambda *_a, **_k: (4, "[ci-watch:quick] 진행 중: FOMS CI (경과 12s)")
    )
    msg = mod._consume_ci_gate_marker(str(tmp_path))
    assert msg and "진행 중" in msg and "블로킹 대기 금지" in msg
    assert marker.exists()  # 유지


def test_marker_deleted_when_green(mod, monkeypatch, tmp_path) -> None:
    """exit 0(green) → 통과 안내 + 마커 삭제(루프 종료)."""
    marker = _make_marker(tmp_path)
    monkeypatch.setattr(mod, "_run_quick", lambda *_a, **_k: (0, "[ci-watch:quick] ALL GREEN ✓"))
    msg = mod._consume_ci_gate_marker(str(tmp_path))
    assert msg and "ALL GREEN" in msg
    assert not marker.exists()  # 삭제


def test_marker_deleted_when_failed(mod, monkeypatch, tmp_path) -> None:
    """exit 1(코드 실패) → 근본 수정 안내 + 실패 요약 + 마커 삭제."""
    marker = _make_marker(tmp_path)
    monkeypatch.setattr(
        mod, "_run_quick", lambda *_a, **_k: (1, "FOMS CI\n    step: pytest\nassert failed")
    )
    msg = mod._consume_ci_gate_marker(str(tmp_path))
    assert msg and "실패" in msg and "재푸시" in msg
    assert "assert failed" in msg  # quick 출력 요약 포함
    assert not marker.exists()


def test_marker_deleted_when_gh_unavailable(mod, monkeypatch, tmp_path) -> None:
    """exit 3(gh 미준비) → 수동 안내 + 마커 삭제."""
    marker = _make_marker(tmp_path)
    monkeypatch.setattr(mod, "_run_quick", lambda *_a, **_k: (3, "[ci-watch] 게이트 불가: gh 미설치"))
    msg = mod._consume_ci_gate_marker(str(tmp_path))
    assert msg and "[CI-GATE]" in msg
    assert not marker.exists()


def test_marker_deleted_on_quick_timeout(mod, monkeypatch, tmp_path) -> None:
    """quick subprocess 타임아웃 → fail-open 수동 안내 + 마커 삭제(무한 재시도 방지)."""
    marker = _make_marker(tmp_path)

    def _boom(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="ci_watch", timeout=15)

    monkeypatch.setattr(mod, "_run_quick", _boom)
    msg = mod._consume_ci_gate_marker(str(tmp_path))
    assert msg and "[CI-GATE]" in msg
    assert not marker.exists()


def test_stale_marker_cleaned_without_running_quick(mod, monkeypatch, tmp_path) -> None:
    """stale(1시간 초과) 마커 → quick 실행 없이 조용히 삭제, 메시지 없음."""
    marker = _make_marker(tmp_path, age_sec=7200)

    def _fail(*_a, **_k):
        raise AssertionError("stale 마커에서 quick 을 실행하면 안 됨")

    monkeypatch.setattr(mod, "_run_quick", _fail)
    msg = mod._consume_ci_gate_marker(str(tmp_path))
    assert msg is None
    assert not marker.exists()


def test_production_branch_passed_to_quick(mod, monkeypatch, tmp_path) -> None:
    """마커 branch(production)가 _run_quick 에 그대로 전달된다."""
    _make_marker(tmp_path, branch="production")
    captured = {}

    def fake_quick(project_root, branch, *_a, **_k):
        captured["branch"] = branch
        return (0, "green")

    monkeypatch.setattr(mod, "_run_quick", fake_quick)
    mod._consume_ci_gate_marker(str(tmp_path))
    assert captured["branch"] == "production"
