"""OPS-HEARTBEAT-02 배선 계약: 매일 조회가 실제로 돌고, 실패를 실패로 말하는가.

엔드포인트만 있고 부르는 사람이 없으면 오늘 이전과 같다(F-17 이 그 상태였다). 그래서
여기서 잠그는 것은 **연결**이다:

1. 워크플로가 존재하고, 실행 시각이 다른 매일 워크플로와 겹치지 않는다.
2. 워크플로가 부르는 스크립트 경로가 실재하고, 넘기는 비밀 이름이 스크립트가 읽는 이름과 같다.
3. 스크립트가 때리는 경로가 앱에 실제로 등록된 라우트다(오타 나면 매일 exit 3).
4. **판정** — 멎은 루프·판정 불가 kind 는 exit 1, 전부 신선하면 exit 0.
   음성 대조군 없이 양성만 보면 "언제나 0" 인 판정도 통과한다.
"""

from __future__ import annotations

import importlib.util
import pathlib
import re
from typing import Any

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "worker-heartbeat-daily.yml"
_SCRIPT = _REPO_ROOT / "tools" / "ops" / "heartbeat_report_http.py"


def _load_script():
    """조회 스크립트를 파일 경로로 읽는다(``tools/`` 는 패키지가 아니다)."""
    spec = importlib.util.spec_from_file_location("heartbeat_report_http_ut", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _cron_lines(path: pathlib.Path) -> list[str]:
    """워크플로 파일의 cron 식 목록."""
    return re.findall(r'cron:\s*"([^"]+)"', path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# 1. 워크플로 존재·시각
# --------------------------------------------------------------------------- #
def test_workflow_exists_and_is_scheduled():
    """매일 도는 배선이 없으면 이 판정은 사람이 부를 때만 돈다(=지금까지의 상태)."""
    text = _WORKFLOW.read_text(encoding="utf-8")
    assert "schedule:" in text and "workflow_dispatch:" in text
    assert _cron_lines(_WORKFLOW), "cron 이 없다"


def test_schedule_does_not_collide_with_other_daily_workflows():
    """같은 운영 인스턴스를 같은 시각에 때리지 않는다(드리프트 감사·RUM 과 분리)."""
    mine = _cron_lines(_WORKFLOW)
    others: list[str] = []
    for path in (_REPO_ROOT / ".github" / "workflows").glob("*.yml"):
        if path.name == _WORKFLOW.name:
            continue
        others.extend(_cron_lines(path))
    assert set(mine).isdisjoint(others), f"cron 충돌: {mine} vs {others}"


def test_workflow_calls_the_real_script_with_matching_secret_names():
    """스크립트 경로·비밀 이름이 어긋나면 매일 조용히 실패한다."""
    text = _WORKFLOW.read_text(encoding="utf-8")
    assert "tools/ops/heartbeat_report_http.py" in text
    assert _SCRIPT.exists()
    source = _SCRIPT.read_text(encoding="utf-8")
    for name in ("FOMS_STAGING_USERNAME", "FOMS_STAGING_PASSWORD"):
        assert name in text and name in source, name


def test_script_path_is_a_registered_route(app):
    """스크립트가 때리는 경로가 앱 라우트로 실재한다(오타면 매일 exit 3)."""
    module = _load_script()
    rules = {str(r.rule) for r in app.url_map.iter_rules()}
    assert module.REPORT_PATH in rules


# --------------------------------------------------------------------------- #
# 2. 판정 (양성 + 음성 대조군)
# --------------------------------------------------------------------------- #
def _run_main(monkeypatch, report: dict[str, Any]) -> int:
    """조회 결과를 주입하고 ``main()`` 의 exit code 를 받는다."""
    module = _load_script()
    monkeypatch.setattr(module, "fetch_report", lambda *a, **k: report)
    monkeypatch.setenv("FOMS_STAGING_USERNAME", "u")
    monkeypatch.setenv("FOMS_STAGING_PASSWORD", "p")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", "")
    monkeypatch.setattr("sys.argv", ["heartbeat_report_http.py"])
    return module.main()


def _report(**over: Any) -> dict[str, Any]:
    base = {
        "kinds": {
            "DELIVERY": {"age_seconds": 3, "interval_seconds": None, "limit_seconds": 30,
                         "ready": True, "reason": "ok", "required": True},
        },
        "not_ready": [], "not_ready_count": 0, "unknown_kinds": [], "elapsed_ms": 12,
    }
    base.update(over)
    return base


def test_all_fresh_exits_zero(monkeypatch):
    """양성 대조군 — 전부 신선하면 성공(매일 초록)."""
    assert _run_main(monkeypatch, _report()) == 0


def test_stopped_loop_exits_one(monkeypatch):
    """음성 대조군 — 멎은 루프가 있으면 실패해야 알림이 간다."""
    report = _report(
        kinds={"GEOCODE_SWEEP": {"age_seconds": 9999, "interval_seconds": 60,
                                 "limit_seconds": 180, "ready": False,
                                 "reason": "stale", "required": False}},
        not_ready=["GEOCODE_SWEEP"], not_ready_count=1)
    assert _run_main(monkeypatch, report) == 1


def test_unknown_kind_exits_one(monkeypatch):
    """판정할 수 없는 신호를 초록으로 넘기면 '아무도 안 읽는' 상태로 되돌아간다."""
    assert _run_main(monkeypatch, _report(unknown_kinds=["SOME_NEW_LOOP"])) == 1


def test_missing_credentials_exits_two(monkeypatch):
    """크리덴셜이 없으면 조회 실패(3)와 구분되는 코드로 끝난다."""
    module = _load_script()
    monkeypatch.delenv("FOMS_STAGING_USERNAME", raising=False)
    monkeypatch.delenv("FOMS_STAGING_PASSWORD", raising=False)
    monkeypatch.setattr("sys.argv", ["heartbeat_report_http.py"])
    assert module.main() == 2


def test_fetch_failure_exits_three(monkeypatch):
    """조회가 터지면 거짓 초록 대신 시끄럽게 실패한다."""
    module = _load_script()

    def _boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(module, "fetch_report", _boom)
    monkeypatch.setenv("FOMS_STAGING_USERNAME", "u")
    monkeypatch.setenv("FOMS_STAGING_PASSWORD", "p")
    monkeypatch.setattr("sys.argv", ["heartbeat_report_http.py"])
    assert module.main() == 3


@pytest.mark.parametrize("stale", [True, False])
def test_summary_table_says_which_kind_and_why(stale):
    """step summary 표에 kind·나이·예산·판정이 남는다(사람이 아침에 읽는 유일한 자료)."""
    module = _load_script()
    report = _report(kinds={"RQ_WORKER": {
        "age_seconds": 9999 if stale else 5, "interval_seconds": 405,
        "limit_seconds": 1215, "ready": not stale,
        "reason": "stale" if stale else "ok", "required": False}},
        not_ready=["RQ_WORKER"] if stale else [])
    text = module.render_summary(report)
    assert "RQ_WORKER" in text and "1215" in text
    assert ("STALE" in text) is stale
