"""AS 타임라인 fragment 라우트(GET /erp/as/timeline/<id>) + register 첫 reception 항목 계약.

세 가지를 고정한다.
1) fragment 라우트: AS 상태 주문만 200(모바일 card-detail 과 동일한 권한·게이트), `?full=1` 은
   recent_limit 을 200 까지 올려 렌더한다(무제한 아님, `?full=0` 은 미적용).
2) 대시보드 display 보강이 행마다 `as_timeline_view` 를 세팅한다(셀 요약·fragment 공용 SSOT).
3) `POST /as/register` 가 접수 원문을 첫 `reception` 로그 항목으로 남기고, 이전 as_content 는
   legacy 항목으로 영구화한다(새 접수 원문이 legacy 로 중복 시드되지 않는다).
"""

from __future__ import annotations

from datetime import date

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User


def _login_as_admin(client, username="as-timeline-admin") -> int:
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role="ADMIN",
        team="CS",
        name="AS 타임라인 관리자",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    user_id = user.id
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    return user_id


def _create_as_order(*, status="AS_RECEIVED", shipment_extra=None) -> int:
    """AS 주문 1건 생성 후 id 반환(요청 teardown detach 회피)."""
    today = date.today().strftime("%Y-%m-%d")
    order = Order(
        received_date=today,
        customer_name="AS 타임라인 고객",
        phone="010-1234-5678",
        address="Seoul",
        product="붙박이장",
        status=status,
        manager_name="Alice",
        as_received_date=today if status.startswith("AS") else None,
        is_erp_order=True,
        structured_data={"workflow": {"stage": status}, "shipment": dict(shipment_extra or {})},
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _shipment(order_id: int) -> dict:
    db_session.expire_all()
    return db_session.get(Order, order_id).structured_data["shipment"]


def _entry(log_id, ts, log_type, text):
    return {"id": log_id, "ts": ts, "by": "김", "by_id": None, "type": log_type, "text": text}


# ---------------------------------------------------------------------------
# GET /erp/as/timeline/<id>
# ---------------------------------------------------------------------------


def test_timeline_fragment_renders(client):
    """접수 앵커 + 스트림 항목이 파셜 HTML 에 나온다."""
    _login_as_admin(client)
    order_id = _create_as_order(shipment_extra={"as_log": [
        _entry("al_1", "2026-07-24T01:00:00", "reception", "문 처짐"),
        _entry("al_2", "2026-07-24T02:00:00", "call", "고객 통화 완료"),
    ]})

    res = client.get(f"/erp/as/timeline/{order_id}")
    assert res.status_code == 200
    body = res.get_data(as_text=True)
    assert "문 처짐" in body
    assert "고객 통화 완료" in body
    assert 'data-log-id="al_1"' in body


def test_timeline_fragment_full_param_lifts_recent_limit(client):
    """기본은 최근 8건만, `?full=1` 이면 전량. 절단된 오래된 항목으로 분기를 증명한다."""
    _login_as_admin(client, username="as-timeline-full-admin")
    logs = [
        _entry(f"al_{i}", f"2026-07-{10 + i:02d}T01:00:00", "memo", f"기록{i}")
        for i in range(12)
    ]
    order_id = _create_as_order(shipment_extra={"as_log": logs})

    default_body = client.get(f"/erp/as/timeline/{order_id}").get_data(as_text=True)
    assert "기록11" in default_body  # 최신
    assert "기록0" not in default_body  # 8건 절단으로 탈락

    full_body = client.get(f"/erp/as/timeline/{order_id}?full=1").get_data(as_text=True)
    assert "기록0" in full_body
    assert "기록11" in full_body

    # ?full=0 은 더보기가 아니다(truthy 판정 금지 — '1' 정확 비교)
    off_body = client.get(f"/erp/as/timeline/{order_id}?full=0").get_data(as_text=True)
    assert "기록0" not in off_body


def test_timeline_fragment_full_is_capped(client):
    """`?full=1` 은 무제한이 아니라 200 캡. append-only as_log 가 fragment 를 폭증시키면 안 된다."""
    _login_as_admin(client, username="as-timeline-cap-admin")
    logs = [
        _entry(f"al_{i}", f"2026-01-01T00:00:{i % 60:02d}", "memo", f"항목{i}")
        for i in range(205)
    ]
    order_id = _create_as_order(shipment_extra={"as_log": logs})

    body = client.get(f"/erp/as/timeline/{order_id}?full=1").get_data(as_text=True)
    assert body.count("data-log-id=") == 200


def test_timeline_fragment_gate_matches_card_detail(client):
    """비-AS 주문·없는 주문 404, 비로그인 리다이렉트 (card-detail 과 동일 게이트)."""
    _login_as_admin(client, username="as-timeline-gate-admin")
    as_order_id = _create_as_order()
    non_as_order_id = _create_as_order(status="RECEIVED")

    assert client.get(f"/erp/as/timeline/{as_order_id}").status_code == 200
    assert client.get(f"/erp/as/timeline/{non_as_order_id}").status_code == 404
    assert client.get("/erp/as/timeline/99999999").status_code == 404

    fresh = client.application.test_client()
    unauth = fresh.get(f"/erp/as/timeline/{as_order_id}")
    assert unauth.status_code in (301, 302)


def test_dashboard_rows_get_timeline_view(client):
    """display 보강이 행마다 as_timeline_view 를 세팅한다(fragment 없이도 셀이 쓸 수 있어야 함)."""
    from foms.services.as_dashboard_display import apply_as_dashboard_row_display_fields

    order_id = _create_as_order(shipment_extra={"as_log": [
        _entry("al_1", "2026-07-24T01:00:00", "reception", "접수 원문"),
    ]})
    db_session.expire_all()
    row = db_session.get(Order, order_id)
    apply_as_dashboard_row_display_fields([row], db_session, mobile_v2_active=False)

    view = row.as_timeline_view
    assert view["reception"]["text"] == "접수 원문"
    assert view["count"] == 1


def test_dashboard_legacy_anchor_reuses_sanitized_values(client, monkeypatch):
    """행 루프는 이미 정리한 as_content/as_content_2 를 주입한다(행당 중복 sanitize 제거).

    주입이 실제로 쓰이는지 증명하려고 sanitize 를 호출 카운터로 감싼다. as_content·as_content_2
    각각 1회씩(표시용)만 돌아야 하고, legacy 앵커가 그 결과를 재파싱하면 카운트가 늘어난다.
    """
    import foms.services.as_dashboard_display as display_mod

    order_id = _create_as_order(shipment_extra={
        "as_content": "<div>옛 기록</div>", "as_content_2": "<div>탭2 기록</div>",
    })
    db_session.expire_all()
    row = db_session.get(Order, order_id)

    calls = []
    real = display_mod.sanitize_as_content_html
    monkeypatch.setattr(
        display_mod, "sanitize_as_content_html",
        lambda value: (calls.append(value), real(value))[1],
    )
    display_mod.apply_as_dashboard_row_display_fields([row], db_session, mobile_v2_active=False)

    assert len(calls) == 2  # as_content 1 + as_content_2 1, legacy 앵커용 재파싱 0
    legacy_ids = [e["id"] for e in row.as_timeline_view["legacy"]]
    assert legacy_ids == ["al_legacy_as_content", "al_legacy_as_content_2"]
    assert row.as_timeline_view["legacy"][0]["text"] == "<div>옛 기록</div>"


def test_dashboard_legacy_anchor_ignores_notes_fallback(client):
    """as_content_2 가 없을 때의 notes 화면 폴백이 legacy 앵커로 새면 안 된다."""
    from foms.services.as_dashboard_display import apply_as_dashboard_row_display_fields

    order_id = _create_as_order(shipment_extra={"as_content": "옛 기록"})
    db_session.expire_all()
    row = db_session.get(Order, order_id)
    row.notes = "화면 폴백용 비고"
    apply_as_dashboard_row_display_fields([row], db_session, mobile_v2_active=False)

    assert row.as_content_2_html == "화면 폴백용 비고"  # 화면 폴백은 유지
    legacy_ids = [e["id"] for e in row.as_timeline_view["legacy"]]
    assert legacy_ids == ["al_legacy_as_content"]  # 타임라인엔 notes 없음


# ---------------------------------------------------------------------------
# POST /api/orders/<id>/as/register — 첫 reception 항목
# ---------------------------------------------------------------------------


def test_register_creates_reception_log(client):
    """접수 원문이 reception 로그로 남는다. legacy as_content 병행 저장도 유지."""
    _login_as_admin(client, username="as-timeline-register-admin")
    order_id = _create_as_order(status="CS")

    res = client.post(f"/api/orders/{order_id}/as/register", json={"as_content": "경첩 불량"})
    assert res.status_code == 200

    shipment = _shipment(order_id)
    log = shipment["as_log"]
    assert any(e.get("type") == "reception" and "경첩 불량" in e.get("text", "") for e in log)
    # T12 퇴역 전까지 legacy 폴백용 as_content 병행 유지
    assert shipment["as_content"] == "경첩 불량"


def test_register_does_not_seed_new_content_as_legacy(client):
    """새 접수 원문이 legacy(이전 기록) 로 중복 시드되면 안 된다.

    append 가 as_content 덮어쓰기 뒤에 오면 migrate_legacy_into_log 가 방금 쓴 원문을
    `al_legacy_as_content` 로 굳혀 같은 문장이 앵커+legacy 로 두 번 남고 count 가 부푼다.
    """
    _login_as_admin(client, username="as-timeline-legacy-admin")
    order_id = _create_as_order(status="CS")

    client.post(f"/api/orders/{order_id}/as/register", json={"as_content": "경첩 불량"})

    log = _shipment(order_id)["as_log"]
    assert [e["id"] for e in log if e.get("legacy") is True] == []
    assert len(log) == 1


def test_register_preserves_previous_content_as_legacy(client):
    """재접수: 기존 as_content 는 legacy 로 영구화되고 새 원문은 reception 으로 append."""
    _login_as_admin(client, username="as-timeline-relegacy-admin")
    order_id = _create_as_order(status="CS", shipment_extra={"as_content": "예전 AS 메모"})

    client.post(f"/api/orders/{order_id}/as/register", json={"as_content": "새 접수 내용"})

    log = _shipment(order_id)["as_log"]
    legacy = [e for e in log if e.get("legacy") is True]
    assert [e["id"] for e in legacy] == ["al_legacy_as_content"]
    assert legacy[0]["text"] == "예전 AS 메모"
    assert log[-1]["type"] == "reception" and log[-1]["text"] == "새 접수 내용"


def test_register_enforces_log_text_cap(client):
    """접수 원문도 as_log 본문 캡(10,000자)을 지나야 한다 — register 가 우회로가 되면 안 된다."""
    _login_as_admin(client, username="as-timeline-cap-register-admin")
    order_id = _create_as_order(status="CS")

    res = client.post(f"/api/orders/{order_id}/as/register", json={"as_content": "가" * 10001})
    assert res.status_code == 400
    assert res.get_json()["success"] is False

    shipment = _shipment(order_id)
    assert shipment.get("as_log") in (None, [])
    assert shipment.get("as_content") in (None, "")  # 미저장(접수 자체가 거부)


def test_register_without_content_creates_no_log_entry(client):
    """빈 접수 원문은 로그 항목을 만들지 않는다(빈 reception 잡음 금지)."""
    _login_as_admin(client, username="as-timeline-empty-admin")
    order_id = _create_as_order(status="CS")

    client.post(f"/api/orders/{order_id}/as/register", json={"as_content": ""})

    assert _shipment(order_id).get("as_log") in (None, [])
