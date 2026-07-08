"""Unit tests for `tools/harness/ci_watch.py` (CI 감시·복구 게이트).

gh CLI 는 절대 실호출하지 않는다 — `run_gh`/`list_runs`/`check_healthz` seam 을
monkeypatch 해 분류 로직과 종료 코드 계약만 검증한다. 폴링은 sleep_fn=noop 로
실시간 대기 없이 돈다.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WATCH_PATH = REPO_ROOT / "tools" / "harness" / "ci_watch.py"

_NOOP_SLEEP = lambda *_a, **_k: None  # noqa: E731 - 테스트용 no-op sleep
_SINK = lambda *_a, **_k: None  # noqa: E731 - printer 출력 무시


def _load_module():
    """ci_watch 모듈을 저장소 경로에서 직접 로드한다(부작용 없음)."""
    spec = importlib.util.spec_from_file_location("ci_watch_under_test", CI_WATCH_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def mod():
    """모듈 fresh 로드 fixture."""
    return _load_module()


# ---------------------------------------------------------------------------
# classify_perf_gate (순수)
# ---------------------------------------------------------------------------
def test_classify_deploy_timeout(mod) -> None:
    log = "some log\nWait for staging deploy ... 실패\n"
    category, _info = mod.classify_perf_gate(log)
    assert category == "deploy_timeout"


def test_classify_deploy_timeout_korean(mod) -> None:
    log = "step wait-deploy: 배포 대기 타임아웃 초과"
    assert mod.classify_perf_gate(log)[0] == "deploy_timeout"


def test_classify_flaky_ms(mod) -> None:
    log = "assert render 812ms > budget 700ms"
    assert mod.classify_perf_gate(log)[0] == "flaky"


def test_classify_bytes_with_suggestion(mod) -> None:
    log = "GET /erp/measurement?view=fragment\nassert bytes 100000 > budget 80000"
    category, info = mod.classify_perf_gate(log)
    assert category == "bytes"
    assert info["obs"] == 100000
    assert info["budget"] == 80000
    assert info["suggest"] == 130000  # 관측 × 1.3
    assert info["path"] == "/erp/measurement?view=fragment"


def test_classify_unknown(mod) -> None:
    assert mod.classify_perf_gate("something unrelated exploded")[0] == "unknown"


# ---------------------------------------------------------------------------
# failures / exit_code_for (순수)
# ---------------------------------------------------------------------------
def test_failures_filters_only_failure(mod) -> None:
    runs = [
        {"conclusion": "success"},
        {"conclusion": "failure", "workflowName": "x"},
        {"conclusion": None},
    ]
    assert mod.failures(runs) == [{"conclusion": "failure", "workflowName": "x"}]


@pytest.mark.parametrize(
    "actions,expected",
    [
        ([], 0),
        (["rerun"], 2),
        (["wait_deploy"], 2),
        (["budget"], 1),
        (["code_fail"], 1),
        (["unclassified"], 1),
        (["rerun", "code_fail"], 1),  # 조치 필요가 재실행보다 우선
        (["rerun", "wait_deploy"], 2),
    ],
)
def test_exit_code_for(mod, actions, expected) -> None:
    assert mod.exit_code_for(actions) == expected


# ---------------------------------------------------------------------------
# gh_ready (seam monkeypatch)
# ---------------------------------------------------------------------------
def test_gh_ready_not_installed(mod, monkeypatch) -> None:
    monkeypatch.setattr(mod, "run_gh", lambda *_a, **_k: (mod._GH_NOT_FOUND, "", "not found"))
    ready, reason = mod.gh_ready()
    assert ready is False and "미설치" in reason


def test_gh_ready_unauthenticated(mod, monkeypatch) -> None:
    monkeypatch.setattr(mod, "run_gh", lambda *_a, **_k: (1, "", "auth required"))
    ready, reason = mod.gh_ready()
    assert ready is False and "미인증" in reason


def test_gh_ready_ok(mod, monkeypatch) -> None:
    monkeypatch.setattr(mod, "run_gh", lambda *_a, **_k: (0, "Logged in", ""))
    assert mod.gh_ready() == (True, "")


# ---------------------------------------------------------------------------
# handle_perf_gate (복구 분기)
# ---------------------------------------------------------------------------
def test_handle_perf_gate_bytes_is_budget(mod, monkeypatch) -> None:
    log = "GET /erp/shipment?view=fragment\nassert bytes 200000 > budget 150000"
    monkeypatch.setattr(mod, "run_gh", lambda *_a, **_k: (0, "", ""))
    action, message = mod.handle_perf_gate(11, log, "abc12345", "http://hz", set())
    assert action == "budget"
    assert "260000" in message  # 200000 × 1.3


def test_handle_perf_gate_deploy_timeout_reruns_when_deployed(mod, monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(mod, "run_gh", lambda args, **_k: (calls.append(args) or (0, "", "")))
    monkeypatch.setattr(mod, "check_healthz", lambda *_a, **_k: True)
    already: set = set()
    action, _msg = mod.handle_perf_gate(
        22, "Wait for staging deploy timeout", "abc12345", "http://hz", already
    )
    assert action == "rerun"
    assert 22 in already
    assert ["run", "rerun", "22"] in calls


def test_handle_perf_gate_deploy_timeout_waits_when_not_deployed(mod, monkeypatch) -> None:
    monkeypatch.setattr(mod, "run_gh", lambda *_a, **_k: (0, "", ""))
    monkeypatch.setattr(mod, "check_healthz", lambda *_a, **_k: False)
    action, _msg = mod.handle_perf_gate(
        33, "Wait for staging deploy timeout", "abc12345", "http://hz", set()
    )
    assert action == "wait_deploy"


def test_handle_perf_gate_rerun_repeat_escalates(mod, monkeypatch) -> None:
    monkeypatch.setattr(mod, "run_gh", lambda *_a, **_k: (0, "", ""))
    monkeypatch.setattr(mod, "check_healthz", lambda *_a, **_k: True)
    already = {44}  # 이미 재실행했던 run
    action, _msg = mod.handle_perf_gate(
        44, "Wait for staging deploy timeout", "abc12345", "http://hz", already
    )
    assert action == "code_fail"  # 재발 → 자동 재실행 중단, 에이전트 조치


# ---------------------------------------------------------------------------
# watch_once / watch (종료 코드 계약)
# ---------------------------------------------------------------------------
def test_watch_once_all_green(mod, monkeypatch) -> None:
    monkeypatch.setattr(
        mod,
        "list_runs",
        lambda *_a, **_k: [
            {"headSha": "abc12345x", "status": "completed", "conclusion": "success",
             "databaseId": 1, "workflowName": "FOMS CI"}
        ],
    )
    code = mod.watch_once("abc12345", "deploy", "http://hz", set(), sleep_fn=_NOOP_SLEEP, printer=_SINK)
    assert code == 0


def test_watch_once_no_runs_is_green(mod, monkeypatch) -> None:
    monkeypatch.setattr(mod, "list_runs", lambda *_a, **_k: [])
    code = mod.watch_once("deadbeef", "deploy", "http://hz", set(), sleep_fn=_NOOP_SLEEP, printer=_SINK)
    assert code == 0


def test_watch_once_code_failure_exits_1(mod, monkeypatch) -> None:
    monkeypatch.setattr(
        mod,
        "list_runs",
        lambda *_a, **_k: [
            {"headSha": "abc12345", "status": "completed", "conclusion": "failure",
             "databaseId": 7, "workflowName": "FOMS CI"}
        ],
    )
    monkeypatch.setattr(mod, "run_gh", lambda *_a, **_k: (0, "    step: pytest\nassert failed", ""))
    code = mod.watch_once("abc12345", "deploy", "http://hz", set(), sleep_fn=_NOOP_SLEEP, printer=_SINK)
    assert code == 1


def test_watch_once_perf_bytes_exits_1(mod, monkeypatch) -> None:
    monkeypatch.setattr(
        mod,
        "list_runs",
        lambda *_a, **_k: [
            {"headSha": "abc12345", "status": "completed", "conclusion": "failure",
             "databaseId": 8, "workflowName": "FOMS perf-gate"}
        ],
    )
    monkeypatch.setattr(
        mod, "run_gh", lambda *_a, **_k: (0, "/erp/x?view=fragment\nassert bytes 90000 > budget 80000", "")
    )
    code = mod.watch_once("abc12345", "deploy", "http://hz", set(), sleep_fn=_NOOP_SLEEP, printer=_SINK)
    assert code == 1


def test_watch_until_final_rerun_then_green(mod, monkeypatch) -> None:
    """1라운드 perf-gate 배포 타임아웃 → 재실행(exit2) → 2라운드 green → 최종 0."""
    state = {"round": 0}

    def fake_list_runs(_branch, _sha_short):
        state["round"] += 1
        if state["round"] == 1:
            return [
                {"headSha": "abc12345", "status": "completed", "conclusion": "failure",
                 "databaseId": 99, "workflowName": "FOMS perf-gate"}
            ]
        return [
            {"headSha": "abc12345", "status": "completed", "conclusion": "success",
             "databaseId": 99, "workflowName": "FOMS perf-gate"}
        ]

    monkeypatch.setattr(mod, "list_runs", fake_list_runs)
    monkeypatch.setattr(mod, "run_gh", lambda *_a, **_k: (0, "Wait for staging deploy timeout", ""))
    monkeypatch.setattr(mod, "check_healthz", lambda *_a, **_k: True)

    code = mod.watch("abc12345", "deploy", "http://hz", until_final=True, sleep_fn=_NOOP_SLEEP, printer=_SINK)
    assert code == 0
    assert state["round"] == 2


def test_watch_no_until_final_returns_2(mod, monkeypatch) -> None:
    monkeypatch.setattr(
        mod,
        "list_runs",
        lambda *_a, **_k: [
            {"headSha": "abc12345", "status": "completed", "conclusion": "failure",
             "databaseId": 55, "workflowName": "FOMS perf-gate"}
        ],
    )
    monkeypatch.setattr(mod, "run_gh", lambda *_a, **_k: (0, "Wait for staging deploy timeout", ""))
    monkeypatch.setattr(mod, "check_healthz", lambda *_a, **_k: True)
    code = mod.watch("abc12345", "deploy", "http://hz", until_final=False, sleep_fn=_NOOP_SLEEP, printer=_SINK)
    assert code == 2


# ---------------------------------------------------------------------------
# main (gh 부재 → exit 3, fail-open 아님)
# ---------------------------------------------------------------------------
def test_main_exit_3_when_gh_absent(mod, monkeypatch) -> None:
    monkeypatch.setattr(mod, "run_gh", lambda *_a, **_k: (mod._GH_NOT_FOUND, "", "not found"))
    assert mod.main([]) == 3
