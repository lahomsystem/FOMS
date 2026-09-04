"""NAVER-INGEST-BACKFILL: 과거 주문 소급 수집 라우트 계약 테스트.

고정하는 계약:

* 실행은 **enqueue 만** 한다 — web 에서 네이버 클라이언트를 만들면 IP 가 달라 차단된다.
* 구간 검사는 **큐에 넣기 전에** 한다(넣고 나서 거절하면 사람은 아무 일도 없는 것을 늦게 안다).
* 종료일은 **그날 끝까지**로 읽는다 — 0시로 두면 마지막 날이 통째로 빠진다.
* 큐 장애·워커 0대면 성공한 척하지 않는다.
* 요청은 감사 원장에 남는다.
* 진행 조회는 읽기 전용 GET 이고 ADMIN 전용이다.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from db import db_session
from foms.services.integrations.naver_commerce import backfill as bf
from foms.services.datetime_kst import now_kst
from models import SecurityLog


def _dates(days_back: int = 3, span: int = 2) -> dict:
    """오늘 기준 과거 구간을 화면이 보내는 모양(YYYY-MM-DD)으로 만든다."""
    end = now_kst().date() - timedelta(days=days_back)
    return {"from": (end - timedelta(days=span)).isoformat(), "to": end.isoformat()}


def test_backfill_requires_admin(app, client):
    """로그인·권한 없이 실행할 수 없다."""
    response = client.post("/admin/naver-ingest/backfill", json=_dates())
    assert response.status_code in (302, 401, 403)


def test_backfill_only_enqueues_and_never_calls_naver(auth_client, monkeypatch):
    """web 은 큐에 넣기만 한다 — 네이버 클라이언트를 만들면 즉시 실패시킨다."""
    calls: list[tuple] = []
    monkeypatch.setattr("foms.web.admin.naver_ingest.enqueue_naver_backfill",
                        lambda start, end, *a, **kw: calls.append((start, end)) or True)

    def _explode(*args, **kwargs):
        raise AssertionError("web 프로세스에서 네이버 클라이언트를 만들면 안 된다")

    monkeypatch.setattr(
        "foms.services.integrations.naver_commerce.client.NaverCommerceClient.__init__", _explode
    )
    payload = _dates()
    response = auth_client.post("/admin/naver-ingest/backfill", json=payload)
    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert len(calls) == 1
    start_iso, end_iso = calls[0]
    assert start_iso.startswith(payload["from"])
    # 종료일은 그날 끝까지다 — 0시로 넘기면 마지막 날이 통째로 빠진다.
    assert end_iso.startswith(payload["to"])
    assert datetime.fromisoformat(end_iso).hour == 23


def test_bad_date_format_is_rejected_before_queueing(auth_client, monkeypatch):
    """날짜 형식이 틀리면 큐에 넣지 않는다(호출 0회)."""
    calls: list[tuple] = []
    monkeypatch.setattr("foms.web.admin.naver_ingest.enqueue_naver_backfill",
                        lambda *a, **kw: calls.append(a) or True)
    response = auth_client.post("/admin/naver-ingest/backfill",
                                json={"from": "2026/06/01", "to": "2026-06-02"})
    assert response.status_code == 400
    assert calls == []


def test_range_over_limit_is_rejected_before_queueing(auth_client, monkeypatch):
    """90일을 넘는 구간은 넣지 않고 사유를 말한다."""
    calls: list[tuple] = []
    monkeypatch.setattr("foms.web.admin.naver_ingest.enqueue_naver_backfill",
                        lambda *a, **kw: calls.append(a) or True)
    today = now_kst().date()
    response = auth_client.post("/admin/naver-ingest/backfill", json={
        "from": (today - bf.MAX_RANGE - timedelta(days=5)).isoformat(),
        "to": (today - timedelta(days=1)).isoformat(),
    })
    assert response.status_code == 400
    assert "90일" in response.get_json()["error"]
    assert calls == []


def test_future_range_is_rejected(auth_client, monkeypatch):
    """미래 구간은 거절한다."""
    monkeypatch.setattr("foms.web.admin.naver_ingest.enqueue_naver_backfill",
                        lambda *a, **kw: True)
    today = now_kst().date()
    response = auth_client.post("/admin/naver-ingest/backfill", json={
        "from": today.isoformat(), "to": (today + timedelta(days=3)).isoformat(),
    })
    assert response.status_code == 400


def test_queue_failure_is_reported_not_faked(auth_client, monkeypatch):
    """큐가 없으면 성공한 척하지 않는다(직접 호출 폴백은 없다)."""
    monkeypatch.setattr("foms.web.admin.naver_ingest.enqueue_naver_backfill",
                        lambda *a, **kw: False)
    response = auth_client.post("/admin/naver-ingest/backfill", json=_dates())
    assert response.status_code == 503
    assert response.get_json()["success"] is False


def test_backfill_request_is_audited(auth_client, monkeypatch):
    """쓰기 라우트는 감사 원장에 남는다(커버리지 게이트 계약)."""
    monkeypatch.setattr("foms.web.admin.naver_ingest.enqueue_naver_backfill",
                        lambda *a, **kw: True)
    auth_client.post("/admin/naver-ingest/backfill", json=_dates())
    actions = [row.action for row in db_session.query(SecurityLog).all()]
    assert "NAVER_INGEST_BACKFILL_ENQUEUE" in actions


def test_state_route_is_read_only_and_reports_progress(auth_client):
    """진행 조회는 워커가 쓴 값을 그대로 준다(쓰기 0)."""
    before = db_session.query(SecurityLog).count()
    response = auth_client.get("/admin/naver-ingest/backfill-state")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert set(data) >= {"rev", "running", "done_through", "last_summary"}
    assert db_session.query(SecurityLog).count() == before


def test_state_route_reflects_worker_progress(auth_client):
    """워커가 남긴 진척이 그대로 보인다."""
    bf._write_state(db_session, {  # noqa: SLF001 - 워커가 쓰는 자리를 직접 흉내낸다
        "rev": 7, "running": True, "done_through": "2026-06-10T23:59:59+09:00",
        "requested_from": "2026-06-01T00:00:00+09:00",
        "requested_to": "2026-06-20T23:59:59+09:00",
        "last_summary": {"collected": 12, "windows": 9},
    })
    db_session.commit()
    data = auth_client.get("/admin/naver-ingest/backfill-state").get_json()["data"]
    assert data["running"] is True
    assert data["rev"] == "7"
    assert data["done_through"].startswith("2026-06-10")
    assert data["last_summary"]["collected"] == 12


# --------------------------------------------------------------------------- #
# 화면 — 운영자가 1회 실행하는 자리
# --------------------------------------------------------------------------- #

_TEMPLATE = "templates/admin/naver_workbench.html"
_SCRIPT = "static/js/admin/naver-workbench.js"


def _read(path: str) -> str:
    from pathlib import Path

    return (Path(__file__).resolve().parents[3] / path).read_text(encoding="utf-8")


def test_workbench_has_backfill_form_and_progress_line():
    """소급 수집은 날짜 두 칸·버튼·진행 문구가 한 자리에 있어야 실행할 수 있다."""
    markup = _read(_TEMPLATE)
    assert 'id="wb-backfill-from"' in markup
    assert 'id="wb-backfill-to"' in markup
    assert 'id="wb-backfill-run"' in markup
    # 진행 문구는 상시 안내라 .alert 자동닫힘에 지워지면 안 된다.
    assert 'id="wb-backfill-note"' in markup
    assert markup.count("data-foms-no-autodismiss") >= 3


def test_workbench_asset_pins_move_together():
    """CSS·JS 를 고쳤으면 ``?v`` 핀이 함께 움직인다(SW staticCacheFirst)."""
    markup = _read(_TEMPLATE)
    assert markup.count("?v=20260902i") == 2


def test_backfill_script_polls_progress_and_never_calls_naver():
    """화면은 진행 상태를 폴링한다 — 끝을 안 말하면 사람이 다시 누른다."""
    script = _read(_SCRIPT)
    assert "/admin/naver-ingest/backfill-state" in script
    assert "submitBackfill" in script
    assert "api.commerce.naver.com" not in script


def test_backfill_defaults_end_yesterday_and_span_within_limit(auth_client):
    """기본값은 어제까지·상한 안이다(오늘 구간은 정상 스윕이 맡는다)."""
    from foms.web.admin.naver_ingest import _backfill_defaults

    defaults = _backfill_defaults()
    today = now_kst().date()
    end = datetime.fromisoformat(defaults["end"]).date()
    start = datetime.fromisoformat(defaults["start"]).date()
    assert end == today - timedelta(days=1)
    assert (end - start) < bf.MAX_RANGE


def test_strip_templates_speak_about_unsendable_orders():
    """두 띠 모두 '여기서는 못 보낸다'를 말한다 — 침묵하면 사람은 빠진 줄도 모른다."""
    for path in ("templates/admin/naver_workbench.html",
                 "templates/measurement/partials/naver_dispatch_strip.html"):
        markup = _read(path)
        assert "bulk_dispatch.foreign" in markup, path
        assert "bulk_dispatch.unknown" in markup, path
        assert "네이버 수집분이 없습니다" in markup, path
