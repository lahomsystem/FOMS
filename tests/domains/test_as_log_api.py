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
