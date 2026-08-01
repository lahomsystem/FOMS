"""DELETE-TRASH-01: 휴지통 route/UI 의 canonical(deleted_at) 이관 계약 테스트.

trash 서브시스템(:mod:`foms.web.orders.trash`)이 legacy ``status=='DELETED'`` 술어에서
canonical delete projection(``deleted_at``)로 이관됐음을 route 레벨에서 고정한다:

* **list/restore 술어 = ``deleted_at IS NOT NULL``**: status 미러 없이 deleted_at 만으로
  휴지통에 표시되고, deleted_at 없는 stale status 미러는 표시되지 않는다.
* **단일 delete = POST 전용(GET 405) + canonical :func:`soft_delete_order`**: deleted_at
  projection + ORDER_SOFT_DELETED event, ``order.status`` 직접 'DELETED' 저장 없음,
  hard delete 없음(row 잔존).
* **restore = canonical :func:`restore_order`**: deleted 축(deleted_at + delete metadata)만
  clear 하고 main/overlay(hold/logistics/AS) 축은 보존한다(original_status 복원 의존 제거).
* **공용 CSRF/Origin write guard 소비**: 토큰 없는 mutation 은 핸들러 실행 전 403(DB 0).
* **web hard-delete 제거**: 물리 영구 삭제 route 는 없다(retention 승인만 물리 삭제).

DB lane 은 root ``client``/``app`` 픽스처의 SQLite in-memory(``db_session`` 공유)다 —
``soft_delete_order``/``restore_order`` 의 ``FOR UPDATE`` 는 SQLite 에서 no-op 이나
projection/version/event 는 Python 수준이라 그대로 성립한다(test_delete_bulk 와 동일 lane).
"""

import os

import pytest
from itsdangerous import URLSafeSerializer
from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, User
from foms.services.orders.soft_delete import (
    EVENT_RESTORED,
    EVENT_SOFT_DELETED,
    soft_delete_order,
)
from foms.services.orders.state_axes import read_state_axes
from foms.services.request_write_guard import (
    _CSRF_SALT,
    _CSRF_SESSION_KEY,
)


# --------------------------------------------------------------------------
# 픽스처 / 헬퍼
# --------------------------------------------------------------------------
@pytest.fixture
def guard_on(app):
    """이 테스트 동안만 공용 write guard 를 강제 활성화하고 원복한다."""
    sentinel = object()
    prev = app.config.get("WRITE_GUARD_ENABLED", sentinel)
    app.config["WRITE_GUARD_ENABLED"] = True
    yield
    if prev is sentinel:
        app.config.pop("WRITE_GUARD_ENABLED", None)
    else:
        app.config["WRITE_GUARD_ENABLED"] = prev


def _make_user(username, *, role="ADMIN"):
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        name=f"{username}-name",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user):
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _make_order(*, status="PRODUCTION", customer_name="홍길동", deleted_at=None,
                original_status=None, structured_data=None):
    order = Order(
        received_date="2026-07-24",
        customer_name=customer_name,
        phone="010-0000-0000",
        address="서울",
        product="침대",
        status=status,
        original_status=original_status,
        deleted_at=deleted_at,
        is_erp_order=True,
        erp_stage_code=status,
        structured_data=structured_data or {"workflow": {"stage": status}},
    )
    db_session.add(order)
    db_session.commit()
    return order


def _fresh(oid):
    """route commit 후 stale 세션 상태를 피하려 새로 조회한다."""
    db_session.remove()
    return db_session.query(Order).filter_by(id=oid).first()


def _issue_csrf(client, app):
    """서버 검증(_serializer + 세션 seed)과 동일 방식으로 유효 CSRF 토큰을 만든다."""
    seed = os.urandom(16).hex()
    with client.session_transaction() as sess:
        sess[_CSRF_SESSION_KEY] = seed
    return URLSafeSerializer(app.secret_key, salt=_CSRF_SALT).dumps(seed)


def _event_count(order_id, event_type):
    return (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id, OrderEvent.event_type == event_type)
        .count()
    )


def _in_active_list(order_id):
    """active_filter(status!='DELETED' AND deleted_at IS NULL) 에 포함되는지 = ghost 아님."""
    db_session.remove()
    return (
        db_session.query(Order)
        .filter(Order.active_filter(), Order.id == order_id)
        .first()
        is not None
    )


# --------------------------------------------------------------------------
# 1. list 술어 = deleted_at (status 미러 비의존)
# --------------------------------------------------------------------------
def test_trash_lists_by_deleted_at_not_status_mirror(client):
    """휴지통 표시는 ``deleted_at`` 로 판정: status 미러 없이도 표시되고,
    deleted_at 없는 stale status='DELETED' 는 표시되지 않는다."""
    _login(client, _make_user("trash_admin_1"))
    # A: canonical soft-deleted(deleted_at O, status 미러 X) → 표시돼야 한다.
    _make_order(customer_name="TRASHVISIBLEA", status="PRODUCTION",
                deleted_at="2026-07-24 09:00:00")
    # B: legacy stale mirror(status='DELETED', deleted_at X) → 표시되면 안 된다.
    _make_order(customer_name="GHOSTMIRRORB", status="DELETED", deleted_at=None)

    resp = client.get("/trash")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "TRASHVISIBLEA" in html, "deleted_at 세팅분이 휴지통에 안 보임"
    assert "GHOSTMIRRORB" not in html, "deleted_at 없는 stale status 미러가 새어 나옴"


# --------------------------------------------------------------------------
# 2. 단일 delete = POST 전용(GET 405) + canonical soft_delete_order
# --------------------------------------------------------------------------
def test_single_delete_get_returns_405(client):
    """soft delete route 는 POST 전용 — GET 은 405(상태 변경 GET 금지)."""
    _login(client, _make_user("trash_admin_2"))
    order = _make_order(customer_name="GETBLOCK")
    assert client.get(f"/delete/{order.id}").status_code == 405
    assert _fresh(order.id).deleted_at is None  # GET 은 아무 것도 삭제하지 않음


def test_single_delete_routes_through_soft_delete_canonical(client):
    """POST /delete/<id> → canonical soft delete: deleted_at 세팅·status 보존·
    ORDER_SOFT_DELETED event·hard delete 없음(row 잔존)·original_status clobber 없음."""
    _login(client, _make_user("trash_admin_3"))
    order = _make_order(customer_name="SOFTDEL", status="PRODUCTION")
    oid = order.id

    resp = client.post(f"/delete/{oid}", follow_redirects=False)
    assert resp.status_code in (302, 303)

    fresh = _fresh(oid)
    assert fresh is not None, "hard delete 됨 — row 가 사라졌다(canonical 은 잔존이어야 함)"
    assert fresh.deleted_at is not None                 # canonical delete projection
    assert fresh.status == "PRODUCTION"                 # status 를 'DELETED' 로 덮지 않음
    assert fresh.original_status is None                # original_status clobber 제거
    assert read_state_axes(fresh).deleted == "DELETED"  # canonical delete 축
    assert (fresh.structured_data or {}).get("delete")  # delete metadata projection
    assert _event_count(oid, EVENT_SOFT_DELETED) == 1


def test_single_delete_csrf_blocked_no_db_change(client, app, guard_on):
    """write guard ON 에서 CSRF 토큰 없는 POST /delete 는 핸들러 전 403·삭제 0."""
    _login(client, _make_user("trash_admin_4"))
    order = _make_order(customer_name="CSRFBLOCK")
    oid = order.id

    resp = client.post(f"/delete/{oid}")
    assert resp.status_code == 403 and resp.headers.get("X-Write-Guard") == "blocked"
    assert _fresh(oid).deleted_at is None  # 핸들러 실행 전 차단 → DB 0


def test_single_delete_csrf_valid_same_origin_passes(client, app, guard_on):
    """유효 CSRF + same-origin 이면 POST /delete 통과(canonical soft delete)."""
    _login(client, _make_user("trash_admin_5"))
    order = _make_order(customer_name="CSRFPASS")
    oid = order.id
    token = _issue_csrf(client, app)

    resp = client.post(
        f"/delete/{oid}",
        headers={"X-CSRF-Token": token, "Origin": "http://localhost"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)
    assert resp.headers.get("X-Write-Guard") is None
    assert _fresh(oid).deleted_at is not None


# --------------------------------------------------------------------------
# 3. restore = canonical restore_order (overlay 보존·original_status 비의존)
# --------------------------------------------------------------------------
def test_restore_uses_restore_order_preserves_status_and_overlay(client):
    """복원은 restore_order 로 deleted 축만 clear: deleted_at·delete metadata 제거,
    status/main/overlay(hold) 축은 보존, original_status 에 의존하지 않는다."""
    admin = _make_user("trash_admin_6")
    _login(client, admin)
    # main=PRODUCTION + hold overlay 활성. original_status 는 절대 세팅하지 않는다.
    order = _make_order(
        customer_name="RESTOREOVL",
        status="PRODUCTION",
        structured_data={"workflow": {"stage": "PRODUCTION", "hold": {"active": True}}},
    )
    oid = order.id
    # canonical soft delete(전이기 status 미러 없이) → deleted_at 만 세팅.
    soft_delete_order(db_session, order_id=oid, actor_user_id=admin.id)
    db_session.commit()

    deleted = _fresh(oid)
    axes_before = read_state_axes(deleted)
    assert axes_before.deleted == "DELETED"
    assert axes_before.hold == "HELD"        # overlay 축 삭제 전 활성
    assert deleted.original_status is None    # 미러 경로 아님

    resp = client.post(
        "/restore_orders", data={"selected_order": str(oid)}, follow_redirects=False
    )
    assert resp.status_code in (302, 303)

    restored = _fresh(oid)
    axes_after = read_state_axes(restored)
    assert restored.deleted_at is None                     # deleted 축 clear
    assert axes_after.deleted == "NONE"
    assert restored.status == "PRODUCTION"                 # status 보존
    assert axes_after.main == "PRODUCTION"                 # main 축 보존
    assert axes_after.hold == "HELD"                       # overlay(hold) 보존
    assert "delete" not in (restored.structured_data or {})  # delete metadata 제거
    assert restored.original_status is None                # original_status 복원 의존 없음
    assert _event_count(oid, EVENT_RESTORED) == 1
    assert _in_active_list(oid)                             # ghost 아님(active_filter 포함)


def test_restore_roundtrip_bulk_mirror_deleted_returns_to_list_no_ghost(client):
    """DELETE-BULK(전이기 미러: status='DELETED'+original_status) 삭제 → trash restore →
    주문이 원상태로 리스트 복귀(status==원상태·deleted_at None·active_filter 포함=ghost 아님)."""
    _login(client, _make_user("trash_bulk_rt", role="MANAGER"))
    order = _make_order(customer_name="BULKRT", status="PRODUCTION")
    oid = order.id
    # 실제 DELETE-BULK route 경유(미러 status='DELETED'+original_status 세팅).
    resp = client.post(
        "/api/bulk_update_order_status", json={"order_ids": [oid], "status": "DELETED"}
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    mirror = _fresh(oid)
    assert mirror.status == "DELETED" and mirror.original_status == "PRODUCTION"  # 미러 확인
    assert mirror.deleted_at is not None

    r = client.post("/restore_orders", data={"selected_order": str(oid)}, follow_redirects=False)
    assert r.status_code in (302, 303)

    back = _fresh(oid)
    assert back.status == "PRODUCTION"          # 원상태 복귀(ghost 아님)
    assert back.original_status is None
    assert back.deleted_at is None
    assert read_state_axes(back).deleted == "NONE"
    assert _in_active_list(oid)                  # active_filter 포함(리스트 복귀)


def test_restore_legacy_status_mirror_fixture_recovers_original_status(client):
    """legacy/cron fixture(status='DELETED'+original_status='MEASURE'+deleted_at) →
    restore → status=='MEASURE'·deleted_at None·리스트 복귀(ghost 아님)."""
    _login(client, _make_user("trash_legacy_rt"))
    order = _make_order(customer_name="LEGACYRT", status="DELETED",
                        original_status="MEASURE", deleted_at="2026-07-24 09:00:00")
    oid = order.id

    r = client.post("/restore_orders", data={"selected_order": str(oid)}, follow_redirects=False)
    assert r.status_code in (302, 303)

    back = _fresh(oid)
    assert back.status == "MEASURE"
    assert back.original_status is None
    assert back.deleted_at is None
    assert _in_active_list(oid)                  # active_filter 포함(ghost 아님)


def test_restore_ignores_stale_status_mirror_without_projection(client):
    """deleted_at 없는(=진짜 휴지통 아님) 항목은 restore 술어(deleted_at)에서 제외돼
    restore_order 대상이 아니다(canonical 술어 확인)."""
    _login(client, _make_user("trash_admin_7"))
    stale = _make_order(customer_name="NOPROJ", status="DELETED", deleted_at=None)
    oid = stale.id

    resp = client.post(
        "/restore_orders", data={"selected_order": str(oid)}, follow_redirects=False
    )
    assert resp.status_code in (302, 303)
    # deleted_at 이 없으므로 복원 대상 아님 → RESTORED event 0(술어가 deleted_at 임을 증명).
    assert _event_count(oid, EVENT_RESTORED) == 0


# --------------------------------------------------------------------------
# 4. web hard-delete 제거 (물리 삭제 route 부재)
# --------------------------------------------------------------------------
@pytest.mark.parametrize("path", ["/permanent_delete_orders", "/permanent_delete_all_orders"])
def test_web_hard_delete_routes_removed(client, path):
    """web 영구 삭제(hard delete) route 는 제거됐다 — 물리 삭제 경로 부재(404)."""
    _login(client, _make_user(f"trash_admin_h{hash(path) & 0xffff}"))
    order = _make_order(customer_name="HARDDELGONE", deleted_at="2026-07-24 09:00:00")
    oid = order.id

    resp = client.post(path, data={"selected_order": str(oid)})
    assert resp.status_code == 404, f"{path} 가 아직 살아있음(web hard-delete 미제거)"
    assert _fresh(oid) is not None  # 물리 삭제되지 않고 잔존
