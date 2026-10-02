"""PERF-GATE-ST: 성능 게이트가 서버 처리시간(Server-Timing app;dur)으로 판정하는 계약.

2026-10-01 PR #487 승격 때 healthz min 이 7표본 안에서 134~258ms 로 흔들려, 절대 TTFB 가
같은데도 TTFB 델타가 부풀어 4연속 오탐했다. 서버가 잰 처리시간은 네트워크가 안 섞인다.

고정하는 것:
* 헤더 파싱 — ``app;dur=`` 만 읽고, 다른 항목·잘못된 값은 무시한다.
* 서버 시간 예산과 측정이 둘 다 있으면 서버 시간으로 판정하고 TTFB 델타는 FAIL 사유가 아니다.
* 헤더가 없거나(옛 배포) 일부 표본에만 있으면 예전 TTFB 델타 판정으로 폴백한다.
* 시드가 서버 시간 예산을 만든다.
* 앱은 인증된 응답에만 헤더를 붙인다(무인증 healthz 에는 없음).
"""

from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from models import User
from tools.perf import staging_perf_gate as gate

GLOBAL_BUDGET = {"render_ms_max": 500, "etag_required": True, "conditional_304_required": True}


def _sample(ttfb_ms: int, server_ms: float | None) -> dict:
    return {
        "ttfb_ms": ttfb_ms,
        "bytes": 1000,
        "wire_bytes": 1000,
        "wire_measured": True,
        "render_ms": 40.0,
        "server_ms": server_ms,
        "etag_present": True,
        "content_encoding": "br",
        "status": 200,
    }


def test_parse_server_timing_reads_only_app_entry():
    assert gate.parse_server_timing_app_ms("app;dur=123.4") == 123.4
    assert gate.parse_server_timing_app_ms("db;dur=9, app;dur=80") == 80.0
    assert gate.parse_server_timing_app_ms("db;dur=9") is None
    assert gate.parse_server_timing_app_ms("app;dur=abc") is None
    assert gate.parse_server_timing_app_ms(None) is None


def test_server_budget_judges_and_ttfb_delta_is_info_only():
    """healthz 가 낮게 나와 TTFB 델타가 예산을 넘어도, 서버 시간이 예산 안이면 PASS."""
    warm = [_sample(378, 120.0), _sample(390, 118.0), _sample(400, 125.0)]
    summary = gate.summarize_samples(warm)
    budget = {"ttfb_delta_min_ms": 100, "server_ms_min_max": 200, "body_bytes_max": 5000}
    row = gate.judge_path("/x", summary, True, budget, GLOBAL_BUDGET, base_ttfb_ms=134)
    assert row["delta_ttfb_ms"] == 244
    assert row["min_server_ms"] == 118
    assert row["judged_by"] == "server"
    assert row["passed"] is True, row["reasons"]


def test_server_budget_catches_real_server_regression():
    warm = [_sample(300, 260.0), _sample(310, 270.0), _sample(305, 265.0)]
    summary = gate.summarize_samples(warm)
    budget = {"ttfb_delta_min_ms": 500, "server_ms_min_max": 200, "body_bytes_max": 5000}
    row = gate.judge_path("/x", summary, True, budget, GLOBAL_BUDGET, base_ttfb_ms=250)
    assert row["passed"] is False
    assert any("server min 260ms" in r for r in row["reasons"])


def test_missing_header_falls_back_to_ttfb_delta():
    """옛 배포(헤더 없음)는 예전 판정 — 배포·게이트 순서가 엇갈려도 판정이 비지 않는다."""
    warm = [_sample(700, None), _sample(720, None)]
    summary = gate.summarize_samples(warm)
    budget = {"ttfb_delta_min_ms": 100, "server_ms_min_max": 200, "body_bytes_max": 5000}
    row = gate.judge_path("/x", summary, True, budget, GLOBAL_BUDGET, base_ttfb_ms=380)
    assert row["judged_by"] == "ttfb_delta"
    assert row["passed"] is False
    assert any("TTFB delta-min" in r for r in row["reasons"])


def test_partial_header_is_not_trusted():
    """표본 일부만 헤더가 있으면(롤링 배포 혼재) 서버 시간을 쓰지 않는다."""
    summary = gate.summarize_samples([_sample(400, 50.0), _sample(410, None)])
    assert summary["min_server_ms"] is None


def test_seed_adds_server_budget_with_margin_and_floor():
    summary = gate.summarize_samples([_sample(400, 100.0), _sample(420, 110.0)])
    budget = gate.seed_budget(summary, base_ttfb_ms=250)
    assert budget["server_ms_min_max"] == max(130, 100 + gate.SEED_SERVER_FLOOR_MS)
    no_header = gate.summarize_samples([_sample(400, None)])
    assert "server_ms_min_max" not in gate.seed_budget(no_header, base_ttfb_ms=250)


def test_app_sets_server_timing_only_for_authenticated(client):
    assert "Server-Timing" not in client.get("/healthz").headers

    user = User(
        username="perfgate-st-user",
        password=generate_password_hash("pw"),
        role="STAFF",
        team="CS",
        name="perfgate-st-user",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    header = client.get("/healthz").headers.get("Server-Timing")
    assert gate.parse_server_timing_app_ms(header) is not None


# --------------------------------------------------------------------------
# 기계 빠르기 보정 (Railway 공유 호스트 — 같은 코드가 시간대마다 100→190ms)
# --------------------------------------------------------------------------
def test_cpu_scale_only_loosens_never_tightens():
    g = {"cpu_calib_ref_ms": 20}
    assert gate.cpu_scale_factor(g, 40.0) == 2.0
    assert gate.cpu_scale_factor(g, 10.0) == 1.0, "빠른 날 예산을 조이면 정상 코드가 오탐한다"
    assert gate.cpu_scale_factor(g, None) == 1.0, "옛 배포(보정 엔드포인트 없음)는 보정 안 함"
    assert gate.cpu_scale_factor({}, 40.0) == 1.0


def test_slow_host_day_passes_with_scale_but_real_regression_still_fails():
    budget = {"ttfb_delta_min_ms": 100, "server_ms_min_max": 150, "body_bytes_max": 5000}
    slow_day = gate.summarize_samples([_sample(400, 190.0), _sample(410, 195.0)])
    row = gate.judge_path("/x", slow_day, True, budget, GLOBAL_BUDGET, base_ttfb_ms=200, cpu_scale=1.9)
    assert row["passed"] is True, row["reasons"]
    assert row["budget_server_ms"] == 285

    regressed = gate.summarize_samples([_sample(500, 320.0), _sample(510, 330.0)])
    row = gate.judge_path("/x", regressed, True, budget, GLOBAL_BUDGET, base_ttfb_ms=200, cpu_scale=1.9)
    assert row["passed"] is False
    assert any("기계 보정 1.90" in r for r in row["reasons"])


def test_cpu_calib_endpoint_requires_login(client):
    assert client.get("/healthz/cpu").status_code == 403

    user = User(
        username="perfgate-cpu-user",
        password=generate_password_hash("pw"),
        role="STAFF",
        team="CS",
        name="perfgate-cpu-user",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    res = client.get("/healthz/cpu")
    assert res.status_code == 200
    body = res.get_json()
    assert body["success"] is True and body["data"]["cpu_ms"] > 0
