"""AS 타임라인 로그 쓰기 API 계약 테스트

(POST /as/log · PATCH /as/log/<log_id> · POST /as/log/<log_id>/delete)."""

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


def test_visit_date_field_update_appends_system_log(client):
    """방문일의 정본 쓰기 경로는 /api/update_order_field 다 — 여기서 이벤트가 나와야 한다.

    전용 `/as/schedule` 라우트는 UI 호출자가 0이라, 거기에만 배선하면 실사용에서는
    타임라인에 아무 것도 안 남는다.
    """
    _login_as_admin(client, username="as-sys-visit-field-admin")
    order_id = _create_as_order().id

    res = client.post("/api/update_order_field", json={
        "order_id": order_id, "field_name": "as_visit_date", "new_value": "2026-08-05"})
    assert res.status_code == 200, res.get_data(as_text=True)

    assert _system_texts(order_id) == ["방문일 확정: 2026-08-05"]
    db_session.expire_all()
    sd = db_session.get(Order, order_id).structured_data
    assert sd["schedule"]["as_visit"]["date"] == "2026-08-05"  # 기존 쓰기 불변


def test_field_update_same_value_appends_nothing(client):
    """값이 안 바뀌면 무기록 — 같은 값 재저장이 타임라인을 중복으로 채우면 안 된다."""
    _login_as_admin(client, username="as-sys-visit-noop-admin")
    order_id = _create_as_order().id

    for _ in range(2):
        client.post("/api/update_order_field", json={
            "order_id": order_id, "field_name": "as_visit_date", "new_value": "2026-08-05"})

    assert _system_texts(order_id) == ["방문일 확정: 2026-08-05"]


def test_completed_date_field_update_appends_system_log(client):
    """AS 완료의 정본 쓰기 경로도 field_update 다. 완료 해제는 취소로 남는다."""
    _login_as_admin(client, username="as-sys-complete-field-admin")
    order_id = _create_as_order().id

    client.post("/api/update_order_field", json={
        "order_id": order_id, "field_name": "as_completed_date", "new_value": "2026-08-06"})
    client.post("/api/update_order_field", json={
        "order_id": order_id, "field_name": "as_completed_date", "new_value": ""})

    assert _system_texts(order_id) == ["AS 접수됨(레거시 전환)", "AS 완료", "AS 완료 취소"]


def test_schedule_rejects_malformed_visit_date(client):
    """방문일은 저장 전에 형식 검증 — 무검증 문자열이 영구 기록으로 새면 안 된다."""
    _login_as_admin(client, username="as-sys-visit-bad-admin")
    order_id = _create_as_order().id

    res = client.post(f"/api/orders/{order_id}/as/schedule", json={"visit_date": "내일쯤"})

    assert res.status_code == 400 and res.get_json()["success"] is False
    db_session.expire_all()
    assert "as_log" not in db_session.get(Order, order_id).structured_data["shipment"]


def test_field_update_rejects_malformed_visit_date(client):
    """실흐름(field_update)도 정규화 실패면 400 — 「방문일 확정: None」 이 영구 기록되면 안 된다.

    /as/schedule 은 UI 호출자가 없다. 방문일의 정본 쓰기 경로인 여기서 정규화가 None 을
    돌려주는데도 통과시키면, as_log 는 append-only 라 그 오기를 되돌릴 수 없다.
    """
    _login_as_admin(client, username="as-sys-visit-field-bad-admin")
    order_id = _create_as_order().id

    res = client.post("/api/update_order_field", json={
        "order_id": order_id, "field_name": "as_visit_date", "new_value": "내일쯤"})

    assert res.status_code == 400, res.get_data(as_text=True)
    assert res.get_json()["success"] is False
    db_session.expire_all()
    sd = db_session.get(Order, order_id).structured_data
    assert "as_log" not in sd["shipment"]  # 「방문일 확정: None」 이 새지 않았다
    assert (sd.get("schedule") or {}).get("as_visit") in (None, {})


def test_system_log_text_is_capped_at_generation(client):
    """생성 지점 상한 — 무검증 입력(사유 등)이 조립돼도 JSONB 가 무한히 커지지 않는다."""
    from foms.services.orders.as_log import AS_LOG_TEXT_MAX, append_system_log

    sd = {"shipment": {}}
    entry = append_system_log(sd, text="가" * (AS_LOG_TEXT_MAX + 500))

    assert len(entry["text"]) == AS_LOG_TEXT_MAX


def test_log_text_cap_is_single_sourced():
    """라우트 검증 상한 = as_log 생성 상한(같은 객체). 이중 정의는 값이 갈리면 조용한 절단이다."""
    from foms.api.cs import as_orders
    from foms.services.orders import as_log

    assert not hasattr(as_orders, "_AS_LOG_TEXT_MAX")  # 로컬 사본 재도입 금지
    assert as_orders.AS_LOG_TEXT_MAX is as_log.AS_LOG_TEXT_MAX


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


def test_billing_unconfirmed_prev_logs_confirmation_not_switch(client):
    """미확정 추정(register 시드)에서의 첫 확정도 전환이 아니다 — 확정된 판정이 없었다.

    확정 여부가 기준이다. type 만 보면 register 가 심은 추정값이 "이전 판정"으로 둔갑한다.
    사유가 없으면 콜론 접미도 붙지 않는다(영구 기록에 매달린 ': ' 금지).
    """
    _login_as_admin(client, username="as-sys-billing-unconfirmed-admin")
    estimate = {"type": "free", "confirmed": False, "amount": None, "reason": ""}
    plain_id = _create_as_order(shipment_extra={"as_billing": dict(estimate)}).id
    reasoned_id = _create_as_order(shipment_extra={"as_billing": dict(estimate)}).id

    assert client.post(f"/api/orders/{plain_id}/as/billing",
                       json={"type": "paid", "amount": 5000}).status_code == 200
    assert client.post(f"/api/orders/{reasoned_id}/as/billing",
                       json={"type": "paid", "amount": 5000, "reason": "현장 과실"}).status_code == 200

    assert _system_texts(plain_id) == ["유상 확정"]
    assert _system_texts(reasoned_id) == ["유상 확정: 현장 과실"]


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


# ---------------------------------------------------------------------------
# ERP 폼 PUT 이 as_log 를 stale 스냅샷으로 덮지 못한다
# ---------------------------------------------------------------------------


def _erp_form_structured(stale_shipment: dict) -> dict:
    """ERP 편집 폼이 PUT 으로 되돌려 보내는 페이로드(shipment 는 페이지 로드 시점 스냅샷)."""
    return {
        "workflow": {"stage": "AS_RECEIVED"},
        "shipment": stale_shipment,
        "parties": {"customer": {"name": "AS 로그 고객", "phone": "010-1234-5678"}},
        "items": [{"product_name": "붙박이장"}],
        "site": {"address_full": "Seoul", "address_main": "Seoul", "address_detail": ""},
    }


def test_structured_put_cannot_clobber_as_log(client):
    """편집 폼의 stale as_log 스냅샷이 서버 항목을 지우지 못한다(lost update).

    deep-merge 는 리스트를 incoming 으로 통째 교체하므로, 편집 탭을 열어둔 사이 추가된
    기록이 폼 저장 한 번에 사라졌다. as_log 는 AS 전용 API 소관이라 항상 DB 값이 이긴다.
    """
    import copy

    _login_as_admin(client, username="as-log-stale-put-admin")
    order_id = _create_as_order(shipment_extra={"as_content": "문틀"}).id
    assert client.post(f"/api/orders/{order_id}/as/log",
                       json={"type": "call", "text": "고객 통화"}).status_code == 200
    saved = copy.deepcopy(_as_log(order_id))

    res = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": _erp_form_structured({"as_content": "문틀", "as_log": []})},
    )
    assert res.status_code == 200 and res.get_json()["success"] is True

    assert _as_log(order_id) == saved


def test_register_then_form_save_keeps_new_entries(client):
    """접수 모달은 register 성공 직후 erpSaveStructured() 를 호출한다(결정적 발현 경로).

    그 PUT 이 실어 보내는 shipment 는 페이지 로드 시점 스냅샷이라 as_log 가 재접수 이전
    상태다 — 가드가 없으면 방금 만든 reception/system 항목이 즉시 소실된다.
    """
    _login_as_admin(client, username="as-log-register-save-admin")
    stale_log = [{"id": "al_old", "ts": "2026-07-01T00:00:00", "by": "김", "by_id": None,
                  "type": "memo", "text": "이전 기록"}]
    order_id = _create_as_order(
        status="CS", shipment_extra={"as_log": [dict(stale_log[0])]}).id

    assert client.post(f"/api/orders/{order_id}/as/register",
                       json={"as_content": "문짝 처짐"}).status_code == 200

    res = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": _erp_form_structured(
            {"as_content": "문짝 처짐", "as_log": stale_log})},
    )
    assert res.status_code == 200 and res.get_json()["success"] is True

    assert [e["type"] for e in _as_log(order_id)] == ["memo", "reception", "system"]


def test_register_then_form_save_keeps_as_lifecycle(client):
    """접수 직후 폼 PUT 이 as_lifecycle 을 빼거나 stale cycle 로 덮지 못한다.

    as_lifecycle 은 폼 allowlist/운영키에 없어, register 직후 erpSaveStructured() 가
    페이지 로드 스냅샷으로 JSONB 를 갈아끼우면 방금 연 RECEIVED cycle 이 사라진다.
    """
    from foms.services.orders.state_axes import read_as_status

    _login_as_admin(client, username="as-lifecycle-stale-put-admin")
    order_id = _create_as_order(status="CS").id
    assert client.post(f"/api/orders/{order_id}/as/register",
                       json={"as_content": "문짝 처짐"}).status_code == 200
    db_session.expire_all()
    before = db_session.get(Order, order_id)
    cycle_id = before.structured_data["as_lifecycle"]["current_cycle_id"]

    res = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": _erp_form_structured({"as_content": "문짝 처짐"})},
    )
    assert res.status_code == 200 and res.get_json()["success"] is True
    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.structured_data["as_lifecycle"]["current_cycle_id"] == cycle_id
    assert read_as_status(saved) == "RECEIVED"
    assert saved.status == "AS_RECEIVED"


# ---------------------------------------------------------------------------
# 재접수 중복 reception 방지 · 원문 크기 선가드
# ---------------------------------------------------------------------------


def test_register_skips_unedited_duplicate_reception(client):
    """재접수 모달은 기존 as_content 를 프리필한다 — 무편집 제출이 같은 본문을 또 쌓지 않는다.

    접수 "사실"은 여전히 system 이벤트로 남는다(접수 자체를 거부하는 게 아니다).
    본문을 실제로 고쳤다면 새 reception 이 정상 append 된다.
    """
    _login_as_admin(client, username="as-log-dup-reception-admin")
    order_id = _create_as_order(status="CS").id

    for _ in range(2):
        assert client.post(f"/api/orders/{order_id}/as/register",
                           json={"as_content": "문짝 처짐"}).status_code == 200
    assert [e["type"] for e in _as_log(order_id)] == ["reception", "system", "system"]

    assert client.post(f"/api/orders/{order_id}/as/register",
                       json={"as_content": "문짝 처짐 + 경첩 파손"}).status_code == 200
    receptions = [e["text"] for e in _as_log(order_id) if e["type"] == "reception"]
    assert receptions == ["문짝 처짐", "문짝 처짐 + 경첩 파손"]


def test_log_append_rejects_oversized_raw_before_parsing(client, monkeypatch):
    """원문 크기 선가드는 sanitize(BeautifulSoup) 파싱 **앞**에 있어야 한다.

    상한(10,000자)은 sanitize 결과에 걸리므로, 그 전까지 수 MB 페이로드를 전부 파싱했다.
    """
    import foms.api.cs.as_orders as as_orders_mod

    parsed = []
    monkeypatch.setattr(
        as_orders_mod, "sanitize_as_content_html",
        lambda value: (parsed.append(value), "")[1],
    )
    _login_as_admin(client, username="as-log-rawcap-admin")
    order_id = _create_as_order().id

    res = client.post(f"/api/orders/{order_id}/as/log",
                      json={"type": "memo", "text": "a" * 100_001})
    assert res.status_code == 400 and res.get_json()["success"] is False
    assert parsed == []

    res = client.post(f"/api/orders/{order_id}/as/register",
                      json={"as_content": "a" * 100_001})
    assert res.status_code == 400 and res.get_json()["success"] is False
    assert parsed == []


# ---------------------------------------------------------------------------
# POST /api/orders/<id>/as/log/<log_id>/delete — 소프트 삭제
# ---------------------------------------------------------------------------
#
# 물리 삭제하지 않는 이유: as_log 는 AS 분쟁 시 "언제 누가 뭘 했는지"의 증거라
# append-only 가 원칙이다(스펙 §8). 화면·집계에서만 감추고 원문은 sd 에 남긴다.


def _delete(client, order_id, log_id):
    return client.post(f"/api/orders/{order_id}/as/log/{log_id}/delete")


def test_log_delete_by_author_soft_deletes(client):
    """작성자 삭제 → 200 + 원문 보존 + deleted 메타 3종."""
    author = _make_user("as-log-del-author", role="STAFF", name="작성자")
    order_id = _create_as_order().id
    log_id = _append_as(client, author, order_id)

    res = _delete(client, order_id, log_id)
    data = res.get_json()
    assert res.status_code == 200 and data["success"] is True

    saved = _as_log(order_id)[-1]
    assert saved["id"] == log_id
    assert saved["deleted"] is True
    assert saved["deleted_by"] == "작성자" and saved["deleted_at"]
    assert saved["text"] == "원본 메모"  # 물리 삭제 금지 — 원문은 그대로


def test_log_delete_by_non_author_forbidden(client):
    """작성자 아닌 비관리자는 403 — 플래그가 붙지 않는다."""
    author = _make_user("as-log-del-author2", role="STAFF", name="작성자")
    other = _make_user("as-log-del-other", role="STAFF", name="타인")
    order_id = _create_as_order().id
    log_id = _append_as(client, author, order_id)

    _login(client, other)
    res = _delete(client, order_id, log_id)
    assert res.status_code == 403 and res.get_json()["success"] is False
    assert _as_log(order_id)[-1].get("deleted") is not True


def test_log_delete_by_admin_allowed(client):
    admin = _make_user("as-log-del-admin", role="ADMIN", name="관리자")
    author = _make_user("as-log-del-author3", role="STAFF", name="작성자")
    order_id = _create_as_order().id
    log_id = _append_as(client, author, order_id)

    _login(client, admin)
    res = _delete(client, order_id, log_id)
    assert res.status_code == 200
    assert _as_log(order_id)[-1]["deleted_by"] == "관리자"


def test_log_delete_rejects_system_entry(client):
    """시스템 항목은 감사 기록 — 삭제 불가(400)."""
    _login_as_admin(client, username="as-log-del-system-admin")
    order_id = _create_as_order(shipment_extra={"as_log": [{
        "id": "al_sys_del", "ts": "2026-07-20T10:00:00", "by": "시스템", "by_id": None,
        "type": "system", "text": "AS 비용 확정", "edited_at": None, "edited_by": None,
    }]}).id

    res = _delete(client, order_id, "al_sys_del")
    assert res.status_code == 400 and res.get_json()["success"] is False
    assert _as_log(order_id)[0].get("deleted") is not True


def test_log_delete_rejects_legacy_entry(client):
    """legacy(이전 기록)는 읽기 전용 — 400. 영구화 전 lazy id 도 같은 경로로 막힌다."""
    _login_as_admin(client, username="as-log-del-legacy-admin")
    order_id = _create_as_order(shipment_extra={"as_content": "<div>옛 기록</div>"}).id
    client.post(f"/api/orders/{order_id}/as/log", json={"type": "memo", "text": "새 메모"})

    res = _delete(client, order_id, "al_legacy_as_content")
    assert res.status_code == 400 and res.get_json()["success"] is False
    assert _as_log(order_id)[0].get("deleted") is not True


def test_log_delete_unknown_id_404(client):
    _login_as_admin(client, username="as-log-del-404-admin")
    order_id = _create_as_order().id
    client.post(f"/api/orders/{order_id}/as/log", json={"type": "memo", "text": "메모"})
    assert _delete(client, order_id, "al_nope").status_code == 404


def test_log_delete_is_idempotent(client):
    """연타/뒤늦은 재시도는 성공으로 흘린다 — deleted_at 은 최초 값 그대로."""
    admin = _make_user("as-log-del-twice-admin", role="ADMIN", name="관리자")
    order_id = _create_as_order().id
    log_id = _append_as(client, admin, order_id)

    assert _delete(client, order_id, log_id).status_code == 200
    first_at = _as_log(order_id)[-1]["deleted_at"]
    res = _delete(client, order_id, log_id)
    assert res.status_code == 200 and res.get_json()["success"] is True
    assert _as_log(order_id)[-1]["deleted_at"] == first_at


def test_log_delete_hides_entry_from_view_and_count(client):
    """렌더 제외 + count 정합 — 감추기는 build_as_timeline_view 한 곳이 담당한다."""
    from foms.services.orders.as_log import build_as_timeline_view

    admin = _make_user("as-log-del-view-admin", role="ADMIN", name="관리자")
    order_id = _create_as_order().id
    keep_id = _append_as(client, admin, order_id, text="남길 메모")
    drop_id = _append_as(client, admin, order_id, text="지울 메모")

    db_session.expire_all()
    before = build_as_timeline_view(db_session.get(Order, order_id).structured_data)
    assert before["count"] == 2 and before["stream_total"] == 2

    assert _delete(client, order_id, drop_id).status_code == 200
    db_session.expire_all()
    after = build_as_timeline_view(db_session.get(Order, order_id).structured_data)
    assert after["count"] == 1 and after["stream_total"] == 1
    ids = [e["id"] for e in after["stream"]]
    assert ids == [keep_id] and drop_id not in ids


def test_log_delete_response_carries_fresh_cell_html(client):
    """응답 cell_html 은 삭제 반영된 요약 — 지운 본문이 '최근 1줄'에 남으면 안 된다."""
    admin = _make_user("as-log-del-cell-admin", role="ADMIN", name="관리자")
    order_id = _create_as_order().id
    _append_as(client, admin, order_id, text="남길 메모")
    drop_id = _append_as(client, admin, order_id, text="지울 메모")

    data = _delete(client, order_id, drop_id).get_json()
    html = data["cell_html"]
    assert "지울 메모" not in html
    assert "남길 메모" in html
    assert "타임라인 1" in html  # 배지 수도 삭제분을 뺀다


def test_log_delete_writes_only_flags_never_text(client):
    """삭제는 text 를 만지지 않는다 → sanitize 대상이 아니다.

    쓰기경로 스캔(test_as_timeline_contract._AS_LOG_WRITE_CALL_SITES)은 **항목 생성**을
    감시하는 계약이라 이 경로는 대상이 아니다. 대신 여기서 "플래그 말고는 안 건드린다"를
    고정한다 — 훗날 '삭제 사유' 같은 사용자 입력이 sanitize 없이 끼어드는 걸 막는 가드다.
    """
    admin = _make_user("as-log-del-keys-admin", role="ADMIN", name="관리자")
    order_id = _create_as_order().id
    log_id = _append_as(client, admin, order_id, text="원본 메모")
    before = dict(_as_log(order_id)[-1])

    assert _delete(client, order_id, log_id).status_code == 200
    after = _as_log(order_id)[-1]

    assert set(after) - set(before) == {"deleted", "deleted_at", "deleted_by"}
    for key, value in before.items():
        assert after[key] == value, key


# ---------------------------------------------------------------------------
# T15a 회차 규약 — 퇴역 유형 입력 차단 · 판정 항목 불변
# ---------------------------------------------------------------------------


def test_log_append_rejects_retired_and_verdict_types(client):
    """action/schedule(퇴역)·verdict(회차 전진 근거)는 quick-add 400 — 저장 흔적 없음."""
    _login_as_admin(client, username="as-log-retired-admin")
    order_id = _create_as_order().id
    for retired in ("action", "schedule", "verdict"):
        res = client.post(
            f"/api/orders/{order_id}/as/log", json={"type": retired, "text": "x"})
        assert res.status_code == 400 and res.get_json()["success"] is False, retired
    db_session.expire_all()
    assert "as_log" not in db_session.get(Order, order_id).structured_data["shipment"]


def test_log_append_stamps_current_round(client):
    """quick-add 항목은 현재 회차 스탬프를 받는다(미결 판정 뒤 append = 2회차)."""
    from foms.services.orders.as_log import append_verdict_log, build_as_log_entry

    _login_as_admin(client, username="as-log-round-admin")
    seed = build_as_log_entry(log_type="memo", text="1차 메모", by="김", by_id=1)
    sd = {"shipment": {"as_log": [seed]}}
    append_verdict_log(sd, verdict="unresolved", text="부품 불량", by="김", by_id=1)
    order_id = _create_as_order(shipment_extra=sd["shipment"]).id

    res = client.post(
        f"/api/orders/{order_id}/as/log", json={"type": "plan", "text": "부품 교체"})
    assert res.status_code == 200
    assert res.get_json()["entry"]["round"] == 2
    assert _as_log(order_id)[-1]["round"] == 2


def test_log_patch_and_delete_reject_verdict_entry(client):
    """판정 항목은 수정·삭제 불가(400) — 판정 수가 회차 파생의 근거라 불변이어야 한다."""
    from foms.services.orders.as_log import append_verdict_log

    _login_as_admin(client, username="as-log-verdict-admin")
    sd = {"shipment": {}}
    entry = append_verdict_log(sd, verdict="resolved", text="정상 마감", by="김", by_id=1)
    order_id = _create_as_order(shipment_extra=sd["shipment"]).id

    res = client.patch(
        f"/api/orders/{order_id}/as/log/{entry['id']}", json={"text": "고친 판정"})
    assert res.status_code == 400 and res.get_json()["success"] is False

    res = _delete(client, order_id, entry["id"])
    assert res.status_code == 400 and res.get_json()["success"] is False
    assert _as_log(order_id)[-1].get("deleted") is not True
