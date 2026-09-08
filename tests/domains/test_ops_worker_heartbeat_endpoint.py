"""OPS-HEARTBEAT-02 계약: ``/api/foms/ops/worker-heartbeats`` (admin 전용 조회).

``worker-heartbeat-daily`` 워크플로가 매일 이 엔드포인트 하나만 본다. 잠글 것:

1. 미인증 **401**(JSON 계약 — 로그인 리다이렉트 금지)
2. 로그인했지만 ``role != ADMIN`` → **403**
3. ADMIN → 200 + 워크플로가 읽는 키 전부 존재
4. **양성/음성 대조군** — 살아 있는 하트비트는 ready, 예산을 넘긴 하트비트는 not-ready.
   양성만 보면 "언제나 ready" 인 판정도 통과한다.
5. 필수 kind 누락은 fail-closed, 등록부에 없는 kind 는 조용히 지나가지 않는다.

판정 규약은 ``foms/api/ops_worker_heartbeat.py`` 모듈 docstring 이 정본이고, 이 파일은 그
규약이 실제 응답으로 재현되는지만 본다.
"""

from __future__ import annotations

from typing import Any

from werkzeug.security import generate_password_hash

from db import db_session
from foms.api.ops_worker_heartbeat import summarize_heartbeats
from foms.services.sidefx_worker import (
    WORKER_KIND_DELIVERY,
    WORKER_KIND_EXPIRY_SCAN,
    WORKER_KIND_GEOCODE_SWEEP,
    WORKER_KIND_NAVER_ORDER_SYNC,
    WORKER_KIND_RETENTION,
    WORKER_KINDS,
)
from models import User

HEARTBEAT_URL = "/api/foms/ops/worker-heartbeats"


def _obs(**heartbeats: Any) -> dict[str, Any]:
    """관측치 dict 를 만든다(kind → {age_seconds, interval_seconds})."""
    return {"heartbeats": dict(heartbeats), "oldest_pending_lag": None, "dead_count": 0}


def _healthy_outbox() -> dict[str, Any]:
    """outbox 3종이 모두 신선한 관측치 조각."""
    return {k: {"age_seconds": 5, "oldest_lag_seconds": 1} for k in WORKER_KINDS}


# --------------------------------------------------------------------------- #
# 1. 인가
# --------------------------------------------------------------------------- #
def test_unauthenticated_401(client):
    """미인증 요청은 401 JSON — 로그인 페이지로 리다이렉트하지 않는다."""
    resp = client.get(HEARTBEAT_URL)
    assert resp.status_code == 401
    assert resp.get_json()["success"] is False


def test_non_admin_403(app):
    """로그인했어도 ADMIN 이 아니면 403(운영 워커 상태는 전사 통계다)."""
    if not db_session.query(User).filter_by(username="hb_viewer").first():
        db_session.add(User(username="hb_viewer", password=generate_password_hash("pw"),
                            role="MEASURE", name="Viewer"))
        db_session.commit()
    client = app.test_client()
    client.post("/login", data={"username": "hb_viewer", "password": "pw"},
                follow_redirects=True)

    resp = client.get(HEARTBEAT_URL)
    assert resp.status_code == 403
    assert resp.get_json()["success"] is False


# --------------------------------------------------------------------------- #
# 2. 응답 계약
# --------------------------------------------------------------------------- #
def test_admin_returns_required_keys(auth_client):
    """ADMIN 200 + 워크플로·조회 도구가 읽는 키가 전부 있다."""
    resp = auth_client.get(HEARTBEAT_URL)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["success"] is True
    data = body["data"]
    for key in ("kinds", "not_ready", "not_ready_count", "unknown_kinds", "elapsed_ms"):
        assert key in data, key


def test_missing_outbox_kind_is_not_ready(auth_client):
    """하트비트 표가 비어 있으면 outbox 3종이 전부 not-ready 다(fail-closed).

    소비 프로세스가 안 도는 상태를 초록으로 보면 이 배선은 존재 이유가 없다.
    """
    resp = auth_client.get(HEARTBEAT_URL)
    data = resp.get_json()["data"]
    for kind in WORKER_KINDS:
        entry = data["kinds"][kind]
        assert entry["required"] is True
        assert entry["ready"] is False and entry["reason"] == "missing"
    assert set(WORKER_KINDS) <= set(data["not_ready"])


# --------------------------------------------------------------------------- #
# 3. 판정 규약 (순수 함수 — 양성/음성 대조군)
# --------------------------------------------------------------------------- #
def test_fresh_heartbeats_are_ready():
    """양성 대조군 — 전부 신선하면 not_ready 가 비어 있다."""
    summary = summarize_heartbeats(_obs(**_healthy_outbox()))
    assert summary["not_ready"] == []
    assert summary["not_ready_count"] == 0


def test_stale_heartbeat_is_caught():
    """음성 대조군 — 예산을 넘긴 kind 하나가 정확히 잡힌다."""
    hb = _healthy_outbox()
    hb[WORKER_KIND_DELIVERY] = {"age_seconds": 999, "oldest_lag_seconds": 1}
    summary = summarize_heartbeats(_obs(**hb))
    assert summary["not_ready"] == [WORKER_KIND_DELIVERY]
    assert summary["kinds"][WORKER_KIND_DELIVERY]["reason"] == "stale"


def test_observed_optional_kind_is_judged():
    """표에 있는 loop kind 는 필수가 아니어도 신선도를 본다."""
    hb = _healthy_outbox()
    hb[WORKER_KIND_GEOCODE_SWEEP] = {"age_seconds": 9999, "interval_seconds": 60}
    summary = summarize_heartbeats(_obs(**hb))
    assert WORKER_KIND_GEOCODE_SWEEP in summary["not_ready"]
    assert summary["kinds"][WORKER_KIND_GEOCODE_SWEEP]["required"] is False


def test_absent_optional_kind_is_not_judged():
    """음성 대조군 — 표에 없는 선택 kind 는 판정 대상이 아니다.

    스테이징처럼 그 루프를 안 켠 환경에서 매일 빨간불이 되면, 오늘 걷어낸 그 문제
    (빨간불이 일상이 되어 아무도 안 본다)가 그대로 되살아난다.
    """
    summary = summarize_heartbeats(_obs(**_healthy_outbox()))
    assert WORKER_KIND_GEOCODE_SWEEP not in summary["kinds"]


def test_declared_interval_widens_the_budget():
    """루프가 신고한 간격이 예산을 넓힌다 — env 로 간격을 바꿔도 오판하지 않는다."""
    hb = _healthy_outbox()
    hb[WORKER_KIND_NAVER_ORDER_SYNC] = {"age_seconds": 2000, "interval_seconds": 1800}
    summary = summarize_heartbeats(_obs(**hb))
    entry = summary["kinds"][WORKER_KIND_NAVER_ORDER_SYNC]
    assert entry["ready"] is True and entry["limit_seconds"] == 5400


def test_unknown_kind_is_reported_not_swallowed():
    """등록부에 없는 kind 는 판정 불가라고 말한다 — 조용히 지나가면 안 읽는 것과 같다."""
    hb = _healthy_outbox()
    hb["SOME_NEW_LOOP"] = {"age_seconds": 5}
    summary = summarize_heartbeats(_obs(**hb))
    assert summary["unknown_kinds"] == ["SOME_NEW_LOOP"]
    assert "SOME_NEW_LOOP" not in summary["kinds"]


def test_expiry_and_retention_are_required_too():
    """필수 kind 는 delivery 하나가 아니다 — 세 개 전부가 fail-closed 대상이다."""
    hb = {WORKER_KIND_DELIVERY: {"age_seconds": 5, "oldest_lag_seconds": 1}}
    summary = summarize_heartbeats(_obs(**hb))
    assert set(summary["not_ready"]) == {WORKER_KIND_EXPIRY_SCAN, WORKER_KIND_RETENTION}
