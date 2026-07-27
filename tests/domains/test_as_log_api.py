"""AS 타임라인 로그 쓰기 API 계약 테스트 (POST /as/log · PATCH /as/log/<log_id>)."""

from datetime import date

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User


def _make_user(username, *, role="ADMIN", team="CS", name="AS 로그 사용자") -> int:
    """AS 로그 API 호출자(관리자/일반 CS 팀원)를 만들고 id만 반환.

    요청 teardown이 세션을 remove 하면 ORM 인스턴스가 detached 되므로
    테스트는 항상 스칼라 id만 들고 다닌다(test_as_billing과 동일한 함정).
    """
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team=team,
        name=name,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user.id


def _login(client, user_id: int):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def _login_as_admin(client, username="as-log-admin") -> int:
    user_id = _make_user(username, role="ADMIN", name="AS 로그 관리자")
    _login(client, user_id)
    return user_id


def _create_as_order(*, status="AS_RECEIVED", shipment_extra=None):
    today = date.today().strftime("%Y-%m-%d")
    order = Order(
        received_date=today,
        customer_name="AS 로그 고객",
        phone="010-1234-5678",
        address="Seoul",
        product="붙박이장",
        status=status,
        manager_name="Alice",
        is_erp_order=True,
        structured_data={"workflow": {"stage": status}, "shipment": dict(shipment_extra or {})},
    )
    db_session.add(order)
    db_session.commit()
    return order


def _as_log(order_id):
    db_session.expire_all()
    return db_session.get(Order, order_id).structured_data["shipment"]["as_log"]


# ---------------------------------------------------------------------------
# POST /api/orders/<id>/as/log
# ---------------------------------------------------------------------------


def test_log_append_returns_entry(client):
    _login_as_admin(client)
    order_id = _create_as_order().id
    res = client.post(f"/api/orders/{order_id}/as/log", json={"type": "call", "text": "고객 통화"})
    data = res.get_json()
    assert res.status_code == 200 and data["success"] is True
    assert data["entry"]["type"] == "call" and "고객 통화" in data["entry"]["text"]
    # 응답 HTML은 낙관적 DOM 삽입용 단건 렌더 — 항목 id와 본문을 포함한다.
    assert data["entry"]["id"] in data["html"] and "고객 통화" in data["html"]
    assert _as_log(order_id)[-1]["id"] == data["entry"]["id"]


def test_log_append_rejects_system_type(client):
    """system 유형은 서버 전용 — 클라이언트 요청은 400(검증 실패)."""
    _login_as_admin(client, username="as-log-system-admin")
    order_id = _create_as_order().id
    res = client.post(f"/api/orders/{order_id}/as/log", json={"type": "system", "text": "x"})
    assert res.status_code == 400 and res.get_json()["success"] is False
    db_session.expire_all()
    assert "as_log" not in db_session.get(Order, order_id).structured_data["shipment"]


def test_log_append_rejects_empty_text(client):
    _login_as_admin(client, username="as-log-empty-admin")
    order_id = _create_as_order().id
    res = client.post(f"/api/orders/{order_id}/as/log", json={"type": "memo", "text": "   "})
    assert res.status_code == 400 and res.get_json()["success"] is False


def test_log_append_persists_legacy_first(client):
    """최초 append가 legacy(as_content)를 영구화한 뒤 새 항목을 남긴다."""
    _login_as_admin(client, username="as-log-legacy-admin")
    order_id = _create_as_order(shipment_extra={"as_content": "<div>옛 기록</div>"}).id
    res = client.post(f"/api/orders/{order_id}/as/log", json={"type": "memo", "text": "새 메모"})
    assert res.status_code == 200
    log = _as_log(order_id)
    assert [e["id"] for e in log] == ["al_legacy_as_content", res.get_json()["entry"]["id"]]
    assert log[0]["legacy"] is True


def test_log_append_ignores_client_ts(client):
    """ts는 서버 생성 전용 — 클라이언트가 보낸 값은 무시한다."""
    _login_as_admin(client, username="as-log-ts-admin")
    order_id = _create_as_order().id
    res = client.post(
        f"/api/orders/{order_id}/as/log",
        json={"type": "memo", "text": "메모", "ts": "1999-01-01T00:00:00", "by": "위조"},
    )
    entry = res.get_json()["entry"]
    assert not entry["ts"].startswith("1999") and "T" in entry["ts"]
    assert entry["by"] == "AS 로그 관리자"


def test_log_append_sanitizes_text(client):
    """본문은 sanitize를 통과한 뒤에만 저장·렌더된다(매크로가 |safe로 뿌리는 값).

    sanitize 배선이 빠지면 script와 미종결 태그가 저장·응답 html에 원문으로 남는다.
    """
    _login_as_admin(client, username="as-log-sanitize-admin")
    order_id = _create_as_order().id
    res = client.post(f"/api/orders/{order_id}/as/log", json={
        "type": "memo",
        "text": '<script>alert(1)</script><b>굵게</b><a href="http://x">링크</a> hi <img src=x onerror=alert(9);//',
    })
    data = res.get_json()
    assert res.status_code == 200
    for payload in (data["entry"]["text"], data["html"], _as_log(order_id)[-1]["text"]):
        assert "<script" not in payload and "<img" not in payload and "<a " not in payload
        assert "&lt;img" in payload
    assert "<b>굵게</b>" in data["entry"]["text"]  # 허용 서식은 보존


def test_log_append_rejects_overlong_text(client):
    """append-only 리스트의 무한 성장 방지 — 상한 초과는 400이고 저장되지 않는다."""
    _login_as_admin(client, username="as-log-toolong-admin")
    order_id = _create_as_order().id
    res = client.post(f"/api/orders/{order_id}/as/log",
                      json={"type": "memo", "text": "가" * 10001})
    assert res.status_code == 400 and res.get_json()["success"] is False
    db_session.expire_all()
    assert "as_log" not in db_session.get(Order, order_id).structured_data["shipment"]


def test_log_append_404_for_missing_order(client):
    _login_as_admin(client, username="as-log-404-admin")
    res = client.post("/api/orders/999999/as/log", json={"type": "memo", "text": "메모"})
    assert res.status_code == 404 and res.get_json()["success"] is False


# ---------------------------------------------------------------------------
# PATCH /api/orders/<id>/as/log/<log_id>
# ---------------------------------------------------------------------------


def _append_as(client, user_id, order_id, text="원본 메모"):
    """지정 사용자로 로그인해 항목 1건을 append하고 그 id를 반환."""
    _login(client, user_id)
    res = client.post(f"/api/orders/{order_id}/as/log", json={"type": "memo", "text": text})
    assert res.status_code == 200
    return res.get_json()["entry"]["id"]


def test_log_patch_by_author(client):
    author = _make_user("as-log-author", role="STAFF", name="작성자")
    order_id = _create_as_order().id
    log_id = _append_as(client, author, order_id)

    res = client.patch(f"/api/orders/{order_id}/as/log/{log_id}", json={"text": "수정된 메모"})
    data = res.get_json()
    assert res.status_code == 200 and data["success"] is True
    assert data["entry"]["text"] == "수정된 메모" and data["entry"]["edited_by"] == "작성자"
    assert data["entry"]["edited_at"] and log_id in data["html"]
    saved = _as_log(order_id)[-1]
    assert saved["text"] == "수정된 메모" and saved["id"] == log_id


def test_log_patch_by_non_author_forbidden(client):
    """작성자 아닌 비관리자는 403 — 본문은 그대로 남는다."""
    author = _make_user("as-log-author2", role="STAFF", name="작성자")
    other = _make_user("as-log-other", role="STAFF", name="타인")
    order_id = _create_as_order().id
    log_id = _append_as(client, author, order_id)

    _login(client, other)
    res = client.patch(f"/api/orders/{order_id}/as/log/{log_id}", json={"text": "남의 글 수정"})
    assert res.status_code == 403 and res.get_json()["success"] is False
    assert _as_log(order_id)[-1]["text"] == "원본 메모"


def test_log_patch_by_admin_allowed(client):
    admin = _make_user("as-log-admin3", role="ADMIN", name="관리자")
    author = _make_user("as-log-author3", role="STAFF", name="작성자")
    order_id = _create_as_order().id
    log_id = _append_as(client, author, order_id)

    _login(client, admin)
    res = client.patch(f"/api/orders/{order_id}/as/log/{log_id}", json={"text": "관리자 정정"})
    assert res.status_code == 200
    assert _as_log(order_id)[-1]["edited_by"] == "관리자"


def test_log_patch_rejects_legacy_entry(client):
    """legacy(이전 기록)는 읽기 전용 — 400."""
    _login_as_admin(client, username="as-log-legacy-patch-admin")
    order_id = _create_as_order(shipment_extra={"as_content": "<div>옛 기록</div>"}).id
    client.post(f"/api/orders/{order_id}/as/log", json={"type": "memo", "text": "새 메모"})

    res = client.patch(
        f"/api/orders/{order_id}/as/log/al_legacy_as_content", json={"text": "덮어쓰기"}
    )
    assert res.status_code == 400 and res.get_json()["success"] is False
    assert _as_log(order_id)[0]["text"] == "<div>옛 기록</div>"


def test_log_patch_rejects_system_entry(client):
    """시스템 항목은 감사 기록 — 수정 불가(400)."""
    _login_as_admin(client, username="as-log-system-patch-admin")
    order_id = _create_as_order(shipment_extra={"as_log": [{
        "id": "al_sys_1", "ts": "2026-07-20T10:00:00", "by": "시스템", "by_id": None,
        "type": "system", "text": "AS 비용 확정", "edited_at": None, "edited_by": None,
    }]}).id

    res = client.patch(f"/api/orders/{order_id}/as/log/al_sys_1", json={"text": "위조"})
    assert res.status_code == 400 and res.get_json()["success"] is False
    assert _as_log(order_id)[0]["text"] == "AS 비용 확정"


def test_log_patch_sanitizes_text(client):
    """PATCH도 append와 같은 sanitize·길이 검증을 통과해야 한다(우회 경로 금지)."""
    _login_as_admin(client, username="as-log-patch-sanitize-admin")
    order_id = _create_as_order().id
    log_id = _append_as(client, _make_user("as-log-author6", role="STAFF"), order_id)
    _login_as_admin(client, username="as-log-patch-sanitize-admin2")

    res = client.patch(f"/api/orders/{order_id}/as/log/{log_id}", json={
        "text": '<script>alert(1)</script><b>수정</b> hi <img src=x onerror=alert(9);//',
    })
    data = res.get_json()
    assert res.status_code == 200
    for payload in (data["entry"]["text"], data["html"], _as_log(order_id)[-1]["text"]):
        assert "<script" not in payload and "<img" not in payload
        assert "&lt;img" in payload
    assert "<b>수정</b>" in data["entry"]["text"]

    too_long = client.patch(f"/api/orders/{order_id}/as/log/{log_id}",
                            json={"text": "가" * 10001})
    assert too_long.status_code == 400 and too_long.get_json()["success"] is False
    assert "<b>수정</b>" in _as_log(order_id)[-1]["text"]  # 거부된 요청은 본문 불변


def test_log_patch_unknown_id_404(client):
    _login_as_admin(client, username="as-log-unknown-admin")
    order_id = _create_as_order().id
    _append_as(client, _make_user("as-log-author4", role="STAFF"), order_id)
    res = client.patch(f"/api/orders/{order_id}/as/log/al_nope_0", json={"text": "x"})
    assert res.status_code == 404 and res.get_json()["success"] is False


def test_log_patch_rejects_empty_text(client):
    _login_as_admin(client, username="as-log-empty-patch-admin")
    order_id = _create_as_order().id
    log_id = _append_as(client, _make_user("as-log-author5", role="STAFF"), order_id)
    res = client.patch(f"/api/orders/{order_id}/as/log/{log_id}", json={"text": ""})
    assert res.status_code == 400 and res.get_json()["success"] is False
    assert _as_log(order_id)[-1]["text"] == "원본 메모"


# ---------------------------------------------------------------------------
# 시스템 이벤트 자동 기록 (T14) — register · schedule · billing 전환 · complete
# ---------------------------------------------------------------------------


def _system_texts(order_id) -> list[str]:
    """저장된 as_log 중 system 항목 본문만."""
    return [e["text"] for e in _as_log(order_id) if e.get("type") == "system"]


def test_register_appends_system_log(client):
    """AS 접수는 수기 reception 원문과 별개로 system 이벤트를 남긴다."""
    _login_as_admin(client, username="as-sys-register-admin")
    order_id = _create_as_order(status="CS").id

    res = client.post(f"/api/orders/{order_id}/as/register", json={"as_content": "문짝 처짐 접수"})
    assert res.status_code == 200, res.get_data(as_text=True)

    log = _as_log(order_id)
    assert any(e["type"] == "reception" and "문짝 처짐 접수" in e["text"] for e in log)
    assert "AS 접수됨" in _system_texts(order_id)


def test_register_appends_system_log_without_content(client):
    """접수 원문이 비어도 접수 사실 자체는 이벤트로 남는다(수기 항목만 없다)."""
    _login_as_admin(client, username="as-sys-register-empty-admin")
    order_id = _create_as_order(status="CS").id

    res = client.post(f"/api/orders/{order_id}/as/register", json={"as_content": ""})
    assert res.status_code == 200

    log = _as_log(order_id)
    assert [e["type"] for e in log] == ["system"]
    assert log[0]["text"] == "AS 접수됨"


def test_schedule_appends_system_log(client):
    """방문일 확정은 확정된 날짜를 담은 system 이벤트를 남긴다(as_info 기록은 병행 유지)."""
    _login_as_admin(client, username="as-sys-schedule-admin")
    order_id = _create_as_order(shipment_extra={"as_log": []}).id

    res = client.post(f"/api/orders/{order_id}/as/schedule", json={"visit_date": "2026-08-01"})
    assert res.status_code == 200, res.get_data(as_text=True)

    assert any("방문일 확정: 2026-08-01" in text for text in _system_texts(order_id))
    db_session.expire_all()
    sd = db_session.get(Order, order_id).structured_data
    assert sd["schedule"]["as_visit"]["date"] == "2026-08-01"  # 기존 경로 불변


def test_complete_appends_system_log(client):
    """AS 완료는 system 이벤트를 남기고, as_info/OrderEvent 기록은 그대로 병행한다."""
    from models import OrderEvent

    _login_as_admin(client, username="as-sys-complete-admin")
    order_id = _create_as_order(status="AS").id
    db_session.get(Order, order_id).structured_data = {
        "workflow": {"stage": "AS"},
        "shipment": {},
        "as_info": [{"id": 1, "status": "OPEN"}],
    }
    db_session.commit()

    res = client.post(f"/api/orders/{order_id}/as/complete", json={"as_id": 1})
    assert res.status_code == 200, res.get_data(as_text=True)

    assert "AS 완료" in _system_texts(order_id)
    db_session.expire_all()
    order = db_session.get(Order, order_id)
    assert order.structured_data["as_info"][0]["status"] == "COMPLETED"
    assert db_session.query(OrderEvent).filter_by(
        order_id=order_id, event_type="AS_COMPLETED").count() == 1


def test_billing_switch_appends_system_log_with_reason(client):
    """무상↔유상 전환은 사유까지 담아 남긴다 — 매출 판정 변경은 감사 대상이다."""
    _login_as_admin(client, username="as-sys-billing-admin")
    order_id = _create_as_order(shipment_extra={
        "as_billing": {"type": "free", "confirmed": True, "amount": None, "reason": ""},
    }).id

    res = client.post(f"/api/orders/{order_id}/as/billing",
                      json={"type": "paid", "amount": 150000, "reason": "고객 과실"})
    assert res.status_code == 200, res.get_data(as_text=True)

    assert "무상→유상 전환: 고객 과실" in _system_texts(order_id)


def test_billing_reconfirm_same_type_appends_nothing(client):
    """같은 유형 재확정은 전환이 아니다 — 이벤트 로그가 재확정 노이즈로 차면 안 된다."""
    _login_as_admin(client, username="as-sys-billing-same-admin")
    order_id = _create_as_order(shipment_extra={
        "as_billing": {"type": "paid", "confirmed": True, "amount": 100000, "reason": "최초"},
        "as_log": [],
    }).id

    res = client.post(f"/api/orders/{order_id}/as/billing",
                      json={"type": "paid", "amount": 120000})
    assert res.status_code == 200, res.get_data(as_text=True)

    assert _system_texts(order_id) == []


def test_billing_first_decision_logs_confirmation_not_switch(client):
    """as_billing 이 없던 상태의 판정은 최초 확정 — "무상→유상 전환" 은 감사 기록 오기다.

    prev_type 은 dict 부재 시에도 기본값 free 로 떨어지므로, 존재 여부로 분기하지 않으면
    첫 유상 확정이 있지도 않았던 무상 판정에서 바뀐 것처럼 남는다.
    """
    _login_as_admin(client, username="as-sys-billing-first-admin")
    paid_id = _create_as_order().id  # shipment 에 as_billing 키 자체가 없다
    undecided_id = _create_as_order().id

    assert client.post(f"/api/orders/{paid_id}/as/billing",
                       json={"type": "paid", "amount": 90000}).status_code == 200
    assert client.post(f"/api/orders/{undecided_id}/as/billing",
                       json={"type": "undecided"}).status_code == 200

    assert _system_texts(paid_id) == ["유상 확정"]
    assert _system_texts(undecided_id) == ["미정 처리"]


def test_billing_switch_without_reason_omits_colon(client):
    """사유가 없으면 콜론 접미를 붙이지 않는다(영구 기록에 매달린 ': ' 금지)."""
    _login_as_admin(client, username="as-sys-billing-nocolon-admin")
    order_id = _create_as_order(shipment_extra={
        "as_billing": {"type": "free", "confirmed": False, "amount": None, "reason": ""},
    }).id

    res = client.post(f"/api/orders/{order_id}/as/billing", json={"type": "paid", "amount": 5000})
    assert res.status_code == 200, res.get_data(as_text=True)

    assert _system_texts(order_id) == ["무상→유상 전환"]


def test_billing_switch_system_log_escapes_reason(client):
    """사유는 사용자 입력이라 저장 시점에 escape 된다(렌더는 |safe)."""
    _login_as_admin(client, username="as-sys-billing-xss-admin")
    order_id = _create_as_order(shipment_extra={
        "as_billing": {"type": "free", "confirmed": True, "amount": None, "reason": ""},
    }).id

    res = client.post(f"/api/orders/{order_id}/as/billing", json={
        "type": "paid", "amount": 1000,
        "reason": '<img src=x onerror="alert(1)">현장 과실',
    })
    assert res.status_code == 200

    text = _system_texts(order_id)[0]
    assert "<img" not in text and "&lt;img" in text
    assert "현장 과실" in text
