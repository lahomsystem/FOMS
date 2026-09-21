"""일반 화면 경로의 관리자 강제 진행(ADMIN-OVERRIDE-01 W2).

두 축을 섞지 않는지 확인한다.
* **권한 축**: ADMIN 이 ``admin_override`` 를 켜고 사유를 적으면 역행·건너뛰기·완료 경로
  차단을 뚫는다. 평소(키 없음)에는 지금과 똑같이 막힌다 — 음성 대조군을 함께 둔다.
* **정합 축**: If-Match 불일치·없는 주문·이미 삭제된 주문은 ``admin_override`` 가 있어도
  그대로 막힌다.

휴지통 미러는 삭제부터 복구까지가 한 계약이라 복구 왕복도 함께 못박는다.
"""

from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, SecurityLog, User
from foms.services.orders.stage_override import OVERRIDE_BLOCK_MESSAGE
from foms.services.orders.trash_mirror import soft_delete_with_trash_mirror


def _login(client, username: str, role: str = "ADMIN") -> int:
    """테스트용 사용자를 만들고 세션에 로그인시킨 뒤 user id 를 돌려준다."""
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team="CS",
        name=username,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    user_id = int(user.id)
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = username
        sess["role"] = role
    return user_id


def _make_erp(*, status: str, stage: str) -> int:
    """메인 파이프라인 위에 깨끗이 올라와 있는 ERP 주문 1건을 만들고 id 를 돌려준다.

    id(int)만 들고 다닌다 — 요청 뒤에 ORM 객체를 만지면 세션이 끊겨 있어(DetachedInstance)
    테스트가 내용과 무관한 이유로 깨진다.
    """
    order = Order(
        received_date="2026-09-01",
        customer_name="강제진행-고객",
        phone="010-7777-8888",
        address="Seoul",
        product="붙박이장",
        status=status,
        manager_name="Mgr",
        is_erp_order=True,
        structured_data={"workflow": {"stage": stage}},
    )
    db_session.add(order)
    db_session.commit()
    return int(order.id)


def _reload(order_id: int) -> Order:
    """현재 커밋된 주문 상태를 다시 읽는다."""
    db_session.expire_all()
    return db_session.get(Order, order_id)


def _override_events(order_id: int) -> list:
    """주문에 남은 ``ADMIN_OVERRIDE_USED`` 이벤트 전부."""
    return (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == "ADMIN_OVERRIDE_USED",
        )
        .all()
    )


def _denied_logs(order_id: int | None = None) -> list:
    """거부된 뚫기 시도가 남긴 감사행(``ADMIN_OVERRIDE_DENIED``).

    성공한 뚫기만 주문 이력에 남고, 실패한 시도는 이 원장에만 남는다 — 둘을 함께 세야
    "몇 번 시도했고 몇 번 통과했나" 를 알 수 있다.
    """
    db_session.expire_all()
    query = db_session.query(SecurityLog).filter(
        SecurityLog.action == "ADMIN_OVERRIDE_DENIED"
    )
    if order_id is not None:
        query = query.filter(SecurityLog.target_id == order_id)
    return query.all()



# ---------------------------------------------------------------------------
# 단건 상태 변경 — 역행·건너뛰기
# ---------------------------------------------------------------------------

def test_단건_상태_역행은_평소처럼_403_으로_막힌다(client):
    """음성 대조군 — 관리자라도 ``admin_override`` 없이 역행하면 지금 그대로 403."""
    _login(client, "ov_single_control")
    order_id = _make_erp(status="CONFIRM", stage="CONFIRM")
    resp = client.post(
        "/api/update_order_status",
        json={"order_id": order_id, "status": "MEASURE"},
    )
    assert resp.status_code == 403, resp.get_json()
    assert OVERRIDE_BLOCK_MESSAGE in (resp.get_json() or {}).get("message", "")
    assert _reload(order_id).status == "CONFIRM"
    assert _override_events(order_id) == []


def test_단건_상태_역행이_관리자_강제_진행이면_통과한다(client):
    """ADMIN + 사유면 역행이 통과하고 강제 진행 이벤트가 1행 남는다."""
    _login(client, "ov_single_pass")
    order_id = _make_erp(status="CONFIRM", stage="CONFIRM")
    resp = client.post(
        "/api/update_order_status",
        json={
            "order_id": order_id,
            "status": "MEASURE",
            "admin_override": True,
            "override_reason": "고객이 실측을 다시 요청했다",
        },
    )
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["new_status"] == "MEASURE"
    assert _reload(order_id).status == "MEASURE"

    events = _override_events(order_id)
    assert len(events) == 1
    payload = events[0].payload or {}
    assert payload["gate"] == "OVERRIDE_BLOCK"
    assert payload["gates"] == ["OVERRIDE_BLOCK"]
    assert payload["route"] == "orders.update_order_status"
    assert payload["axis"] == "MAIN"
    assert payload["to"] == "MEASURE"
    assert payload["reason"] == "고객이 실측을 다시 요청했다"
    assert payload["bulk"] is False
    assert payload["actor"]["role"] == "ADMIN"


# ---------------------------------------------------------------------------
# 일괄 상태 변경
# ---------------------------------------------------------------------------

def test_일괄_상태_역행은_평소엔_차단목록에_담긴다(client):
    """음성 대조군 — 일괄 경로도 ``admin_override`` 없이는 blocked_override_required 다."""
    _login(client, "ov_bulk_control")
    order_id = _make_erp(status="CONFIRM", stage="CONFIRM")
    resp = client.post(
        "/api/bulk_update_order_status",
        json={"order_ids": [order_id], "status": "MEASURE"},
    )
    body = resp.get_json()
    assert body["updated"] == 0, body
    assert body["blocked_override_required"] == [order_id]
    assert _reload(order_id).status == "CONFIRM"


def test_일괄_상태_역행이_관리자_강제_진행이면_updated_에_들어간다(client):
    """일괄 경로도 최상위 키 한 벌로 뚫리고, 주문마다 이벤트가 1행씩 남는다."""
    _login(client, "ov_bulk_pass")
    order_id = _make_erp(status="CONFIRM", stage="CONFIRM")
    resp = client.post(
        "/api/bulk_update_order_status",
        json={
            "order_ids": [order_id],
            "status": "MEASURE",
            "admin_override": True,
            "override_reason": "일괄 되돌리기",
        },
    )
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["updated"] == 1, body
    assert body["blocked_override_required"] == []
    assert _reload(order_id).status == "MEASURE"

    events = _override_events(order_id)
    assert len(events) == 1
    assert (events[0].payload or {})["bulk"] is True


# ---------------------------------------------------------------------------
# 음성 — 권한 축 거부는 업무 게이트보다 먼저 돈다
# ---------------------------------------------------------------------------

def test_비관리자가_강제_진행을_켜면_ADMIN_ONLY_다(client):
    """음성 — STAFF 의 ``admin_override`` 는 게이트 문구가 아니라 403 ADMIN_ONLY 로 끊긴다."""
    _login(client, "ov_staff", role="STAFF")
    order_id = _make_erp(status="CONFIRM", stage="CONFIRM")
    resp = client.post(
        "/api/update_order_status",
        json={
            "order_id": order_id,
            "status": "MEASURE",
            "admin_override": True,
            "override_reason": "내가 하고 싶다",
        },
    )
    assert resp.status_code == 403, resp.get_json()
    body = resp.get_json()
    assert body["code"] == "ADMIN_ONLY"
    # 역행 차단 문구가 아니라 권한 축의 정확한 오답을 준다.
    assert OVERRIDE_BLOCK_MESSAGE not in body.get("message", "")
    assert _reload(order_id).status == "CONFIRM"
    # 거부된 시도도 감사 원장에는 정확히 1행 남는다(주문 이력에는 남기지 않는다).
    denied = _denied_logs(order_id)
    assert len(denied) == 1
    assert (denied[0].detail or {}).get("gate") == "ADMIN_ONLY"
    assert (denied[0].detail or {}).get("route") == "orders.update_order_status"
    assert _override_events(order_id) == []


def test_사유가_비면_REASON_REQUIRED_이고_상태는_불변이다(client):
    """음성 — 관리자라도 사유가 공백이면 422 이고 아무것도 바뀌지 않는다."""
    _login(client, "ov_no_reason")
    order_id = _make_erp(status="CONFIRM", stage="CONFIRM")
    resp = client.post(
        "/api/update_order_status",
        json={
            "order_id": order_id,
            "status": "MEASURE",
            "admin_override": True,
            "override_reason": "   ",
        },
    )
    assert resp.status_code == 422, resp.get_json()
    assert resp.get_json()["code"] == "REASON_REQUIRED"
    assert _reload(order_id).status == "CONFIRM"
    assert _override_events(order_id) == []
    denied = _denied_logs(order_id)
    assert len(denied) == 1
    assert (denied[0].detail or {}).get("gate") == "REASON_REQUIRED"


def test_주문별로_다른_강제_진행_모양은_받지_않는다(client):
    """음성 — 일괄 요청의 override 는 최상위 한 번뿐이다(dict/list 는 400)."""
    _login(client, "ov_shape")
    order_id = _make_erp(status="CONFIRM", stage="CONFIRM")
    resp = client.post(
        "/api/bulk_update_order_status",
        json={
            "order_ids": [order_id],
            "status": "MEASURE",
            "admin_override": {str(order_id): True},
            "override_reason": "주문별로 다르게",
        },
    )
    assert resp.status_code == 400, resp.get_json()
    assert resp.get_json()["code"] == "ADMIN_OVERRIDE_SHAPE"
    assert _reload(order_id).status == "CONFIRM"


# ---------------------------------------------------------------------------
# 음성 — 정합 축은 뚫리지 않는다
# ---------------------------------------------------------------------------

def test_없는_주문은_강제_진행이어도_404_다(client):
    """음성(정합 축) — 존재하지 않는 주문은 권한으로 뚫을 수 있는 것이 아니다."""
    _login(client, "ov_missing_order")
    resp = client.post(
        "/api/update_order_status",
        json={
            "order_id": 99999123,
            "status": "MEASURE",
            "admin_override": True,
            "override_reason": "없는 주문",
        },
    )
    assert resp.status_code == 404, resp.get_json()


def test_일괄_삭제의_If_Match_불일치는_강제_진행이어도_409_다(client):
    """음성(정합 축) — version 충돌은 권한 문제가 아니라 동시 편집 보호다."""
    _login(client, "ov_ifmatch")
    order_id = _make_erp(status="CONFIRM", stage="CONFIRM")
    current_version = getattr(_reload(order_id), "mutation_version", 0) or 0
    resp = client.post(
        "/api/bulk_update_order_status",
        json={
            "order_ids": [order_id],
            "status": "DELETED",
            "versions": {str(order_id): current_version + 7},
            "admin_override": True,
            "override_reason": "그래도 지우고 싶다",
        },
    )
    assert resp.status_code == 409, resp.get_json()
    saved = _reload(order_id)
    assert saved.status == "CONFIRM"
    assert saved.deleted_at is None


def test_이미_삭제된_주문은_강제_진행으로도_되살아나지_않는다(client):
    """음성(정합 축) — 삭제 축은 권한 축이 아니다. 강제 진행 이벤트도 남지 않는다."""
    user_id = _login(client, "ov_deleted")
    order_id = _make_erp(status="CONFIRM", stage="CONFIRM")
    soft_delete_with_trash_mirror(
        db_session, order_id=order_id, actor_user_id=user_id, reason="정리"
    )
    db_session.commit()

    client.post(
        "/api/update_order_field",
        json={
            "order_id": order_id,
            "field": "status",
            "value": "MEASURE",
            "admin_override": True,
            "override_reason": "되살려 본다",
        },
    )
    assert _reload(order_id).deleted_at is not None
    assert _override_events(order_id) == []


# ---------------------------------------------------------------------------
# 휴지통 미러 — 삭제부터 복구까지가 한 계약
# ---------------------------------------------------------------------------

def test_휴지통_미러는_상태와_원상태를_함께_남긴다(client):
    """``soft_delete_with_trash_mirror`` 1건 = deleted_at + status/original_status 미러."""
    user_id = _login(client, "ov_trash_mirror")
    order_id = _make_erp(status="CONFIRM", stage="CONFIRM")

    deleted_now = soft_delete_with_trash_mirror(
        db_session, order_id=order_id, actor_user_id=user_id, reason="정리"
    )
    db_session.commit()

    assert deleted_now is True
    saved = _reload(order_id)
    assert saved.deleted_at is not None          # canonical 축
    assert saved.status == "DELETED"             # 휴지통 목록 술어
    assert saved.original_status == "CONFIRM"    # 복구 목표값

    # 두 번째 호출은 멱등 no-op 이다(이미 삭제됨).
    assert soft_delete_with_trash_mirror(
        db_session, order_id=order_id, actor_user_id=user_id
    ) is False
    db_session.commit()
    assert _reload(order_id).original_status == "CONFIRM"


def test_휴지통_미러로_지운_주문은_복구하면_원상태로_돌아온다(client):
    """복구 왕복 — 휴지통 복구가 original_status 를 되살리고 삭제 축도 함께 푼다."""
    user_id = _login(client, "ov_trash_restore")
    order_id = _make_erp(status="CONFIRM", stage="CONFIRM")
    soft_delete_with_trash_mirror(
        db_session, order_id=order_id, actor_user_id=user_id, reason="오입력"
    )
    db_session.commit()

    resp = client.post("/restore_orders", data={"selected_order": [str(order_id)]})
    assert resp.status_code in (200, 302), resp.status_code

    saved = _reload(order_id)
    assert saved.status == "CONFIRM"       # 원상태 복귀
    assert saved.original_status is None   # 복구 뒤에는 비워 둔다
    assert saved.deleted_at is None        # canonical 축도 함께 풀린다
