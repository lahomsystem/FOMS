"""DELETE-BULK-01: 주문 대량 삭제(all-or-none · body별 version · MANAGER 전용) 계약 테스트.

``POST /api/bulk_update_order_status`` 의 ``status="DELETED"`` 경로가 canonical
soft-delete(DELETE-CORE-00 :func:`soft_delete_order`)로 라우팅됨을 route 레벨에서 고정한다:

* 각 주문 → ``deleted_at`` projection set + ``mutation_version`` bump + ``ORDER_SOFT_DELETED``
  event. hard delete 없음(row 잔존)·status string 'DELETED' 직접 저장 없음(축 보존).
* **all-or-none**: 하나라도 stale version(권한/존재 포함) 실패면 전체 롤백(부분 삭제 0).
* **body별 version**: ``versions`` 맵의 order별 If-Match(expected ``mutation_version``) 검증.
* **STAFF/VIEWER 403**: 대량 삭제는 AUTH-01 ``MANAGER_MUTATION``(ADMIN/MANAGER) 정책 재사용.

DB lane 은 root ``client``/``app`` 픽스처의 SQLite in-memory(``db_session`` 공유)다 —
``soft_delete_order`` 의 ``FOR UPDATE`` 는 SQLite 에서 no-op 이나 version 검증/롤백은
Python 수준이라 그대로 성립한다(test_soft_delete_core 와 동일 lane).
"""

from unittest.mock import patch

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, User
from foms.services.orders.soft_delete import EVENT_SOFT_DELETED
from foms.services.orders.state_axes import read_state_axes


# --------------------------------------------------------------------------
# 픽스처 / 헬퍼
# --------------------------------------------------------------------------
@pytest.fixture
def policy_on(app):
    """AUTH-01 정책 가드를 이 테스트 동안만 활성화하고 원복한다(VIEWER 403 JSON 검증용)."""
    sentinel = object()
    prev = app.config.get("AUTH_POLICY_ENABLED", sentinel)
    app.config["AUTH_POLICY_ENABLED"] = True
    yield
    if prev is sentinel:
        app.config.pop("AUTH_POLICY_ENABLED", None)
    else:
        app.config["AUTH_POLICY_ENABLED"] = prev


def _make_user(username, *, role="MANAGER", team=None):
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team=team,
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


def _make_order(status="PRODUCTION", customer_name="홍길동"):
    """대량 삭제 대상 ERP 주문(main=status). soft-delete 후 canonical deleted_at 이 서고,
    전이기 dual-write 로 legacy status='DELETED'+original_status 가 미러된다."""
    order = Order(
        received_date="2026-07-24",
        customer_name=customer_name,
        phone="010-0000-0000",
        address="서울",
        product="침대",
        status=status,
        is_erp_order=True,
        structured_data={"workflow": {"stage": status}},
        erp_stage_code=status,
    )
    db_session.add(order)
    db_session.commit()
    return order


def _bulk_delete(client, order_ids, versions=None):
    body = {"order_ids": order_ids, "status": "DELETED"}
    if versions is not None:
        body["versions"] = versions
    return client.post("/api/bulk_update_order_status", json=body)


def _soft_delete_events(order_id):
    return (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == EVENT_SOFT_DELETED,
        )
        .count()
    )


# --------------------------------------------------------------------------
# soft-delete projection + version + event (hard delete·status 미기록 없음)
# --------------------------------------------------------------------------
def test_bulk_delete_soft_deletes_each_with_version_and_event(client, app):
    """대량 삭제 → 각 주문 canonical deleted_at·version++·event + 전이기 status/original 미러."""
    _login(client, _make_user("mgr-del", role="MANAGER"))
    o1, o2 = _make_order("PRODUCTION"), _make_order("DRAWING")
    id1, id2 = o1.id, o2.id
    v1, v2 = o1.mutation_version, o2.mutation_version

    resp = _bulk_delete(client, [id1, id2])

    assert resp.status_code == 200, resp.get_data(as_text=True)
    data = resp.get_json()
    assert data["success"] is True and data["updated"] == 2

    db_session.expire_all()
    for oid, before_v, before_status in [(id1, v1, "PRODUCTION"), (id2, v2, "DRAWING")]:
        o = db_session.get(Order, oid)
        assert o is not None                             # hard delete 아님 — row 잔존
        assert o.deleted_at is not None                  # canonical delete projection
        assert read_state_axes(o).deleted == "DELETED"   # canonical delete 축
        assert o.mutation_version == before_v + 1        # version bump(soft_delete_order)
        assert _soft_delete_events(oid) == 1
        # 전이기 dual-write(trash 호환): legacy status='DELETED' + 원상태 original_status.
        assert o.status == "DELETED"
        assert o.original_status == before_status


def test_bulk_delete_does_not_hard_delete(client, app):
    """soft-delete 는 물리 삭제가 아니다 — row 는 잔존한다(canonical deleted_at + status 미러)."""
    _login(client, _make_user("mgr-hard", role="MANAGER"))
    o1 = _make_order("PRODUCTION")
    id1 = o1.id

    assert _bulk_delete(client, [id1]).status_code == 200

    db_session.expire_all()
    survivor = db_session.get(Order, id1)
    assert survivor is not None                          # row 물리 잔존
    assert survivor.deleted_at is not None               # canonical projection
    assert survivor.original_status == "PRODUCTION"      # 원상태 보존(restore 대비)


def test_bulk_delete_route_trash_visibility_and_list_exclusion(client, app):
    """route 경유(실제 POST) 대량 삭제 → (1) /trash 표시 (2) original_status 기록
    (3) 메인 리스트 제외. 전이기 dual-write 가 없으면 (1)/(3) 이 사일런트 회귀한다."""
    _login(client, _make_user("mgr-trashvis", role="MANAGER"))
    marker = "TRASHMARK_델리트벌크01"
    o1 = _make_order("PRODUCTION", customer_name=marker)
    id1 = o1.id

    assert _bulk_delete(client, [id1]).status_code == 200   # 실제 POST(우회 아님)

    # (2) original_status 기록 + canonical deleted_at.
    db_session.expire_all()
    o = db_session.get(Order, id1)
    assert o.original_status == "PRODUCTION"
    assert o.deleted_at is not None

    # (1) /trash 실제 route 에 표시(trash.py 는 status=='DELETED' 술어).
    trash_resp = client.get("/trash")
    assert trash_resp.status_code == 200, trash_resp.status_code
    assert marker in trash_resp.get_data(as_text=True)

    # (3) 메인 리스트 실제 route 에서 제외(active_filter = deleted_at IS NULL).
    list_resp = client.get("/", follow_redirects=True)
    assert list_resp.status_code == 200, list_resp.status_code
    assert marker not in list_resp.get_data(as_text=True)


# --------------------------------------------------------------------------
# body별 version (각 주문 If-Match)
# --------------------------------------------------------------------------
def test_bulk_delete_respects_matching_versions(client, app):
    """versions 맵의 expected version 이 일치하면 삭제 성공(body별 If-Match)."""
    _login(client, _make_user("mgr-ver", role="MANAGER"))
    o1, o2 = _make_order("PRODUCTION"), _make_order("DRAWING")
    id1, id2 = o1.id, o2.id

    resp = _bulk_delete(
        client, [id1, id2],
        versions={str(id1): o1.mutation_version, str(id2): o2.mutation_version},
    )

    assert resp.status_code == 200, resp.get_data(as_text=True)
    db_session.expire_all()
    assert db_session.get(Order, id1).deleted_at is not None
    assert db_session.get(Order, id2).deleted_at is not None


# --------------------------------------------------------------------------
# all-or-none (중간 실패 → 전체 롤백·부분 삭제 0)
# --------------------------------------------------------------------------
def test_bulk_delete_all_or_none_stale_version_rolls_back(client, app):
    """중간 주문의 stale version → 409, 전체 롤백(앞 주문 삭제 0·단일 tx)."""
    _login(client, _make_user("mgr-aon", role="MANAGER"))
    o1, o2 = _make_order("PRODUCTION"), _make_order("DRAWING")
    id1, id2 = o1.id, o2.id
    good_v1 = o1.mutation_version

    # o1 은 올바른 version, o2 는 stale(999) → 하나라도 실패면 전체 롤백.
    resp = _bulk_delete(
        client, [id1, id2],
        versions={str(id1): good_v1, str(id2): 999},
    )

    assert resp.status_code == 409, resp.get_data(as_text=True)
    assert resp.get_json()["success"] is False

    db_session.expire_all()
    a, b = db_session.get(Order, id1), db_session.get(Order, id2)
    assert a.deleted_at is None and b.deleted_at is None       # 부분 삭제 0
    assert a.mutation_version == good_v1                       # 앞 주문 version 불변
    assert _soft_delete_events(id1) == 0 and _soft_delete_events(id2) == 0


def test_bulk_delete_all_or_none_missing_order_rolls_back(client, app):
    """존재하지 않는 주문 포함 → 404, 전체 롤백(실재 주문도 삭제 0)."""
    _login(client, _make_user("mgr-missing", role="MANAGER"))
    o1 = _make_order("PRODUCTION")
    id1 = o1.id
    ghost = id1 + 999999

    resp = _bulk_delete(client, [id1, ghost])

    assert resp.status_code == 404, resp.get_data(as_text=True)
    db_session.expire_all()
    assert db_session.get(Order, id1).deleted_at is None       # 부분 삭제 0
    assert _soft_delete_events(id1) == 0


# --------------------------------------------------------------------------
# STAFF/VIEWER delete 403 (MANAGER_MUTATION 재사용) — DB 변화 0
# --------------------------------------------------------------------------
def test_bulk_delete_staff_forbidden_no_db_change(client, app, policy_on):
    """STAFF 는 대량 삭제 403(in-handler MANAGER_MUTATION), DB 변화 0."""
    _login(client, _make_user("staff-del", role="STAFF", team="SALES"))
    o1 = _make_order("PRODUCTION")
    id1 = o1.id

    resp = _bulk_delete(client, [id1])

    assert resp.status_code == 403, resp.get_data(as_text=True)
    assert resp.get_json()["success"] is False
    db_session.expire_all()
    o = db_session.get(Order, id1)
    assert o.deleted_at is None and o.status == "PRODUCTION"
    assert o.mutation_version == 1
    assert _soft_delete_events(id1) == 0


def test_bulk_delete_viewer_forbidden_no_db_change(client, app, policy_on):
    """VIEWER 는 대량 삭제 403(정책 가드), DB 변화 0."""
    _login(client, _make_user("viewer-del", role="VIEWER"))
    o1 = _make_order("PRODUCTION")
    id1 = o1.id

    resp = _bulk_delete(client, [id1])

    assert resp.status_code == 403, resp.get_data(as_text=True)
    db_session.expire_all()
    o = db_session.get(Order, id1)
    assert o.deleted_at is None and o.status == "PRODUCTION"
    assert _soft_delete_events(id1) == 0


# --------------------------------------------------------------------------
# 정상 role 성공 (MANAGER/ADMIN)
# --------------------------------------------------------------------------
def test_bulk_delete_admin_and_manager_allowed(client, app):
    """ADMIN·MANAGER 는 대량 삭제 성공(권한 회귀 0)."""
    for role, status in [("ADMIN", "PRODUCTION"), ("MANAGER", "DRAWING")]:
        _login(client, _make_user(f"{role.lower()}-ok", role=role))
        oid = _make_order(status).id
        resp = _bulk_delete(client, [oid])
        assert resp.status_code == 200, (role, resp.get_data(as_text=True))
        db_session.expire_all()
        assert db_session.get(Order, oid).deleted_at is not None


def test_bulk_delete_invalidates_dashboard_caches(client, app):
    """대량 삭제도 commit 뒤 대시보드 read-slice 캐시를 무효화한다(즉시 반영).

    무효화가 없으면 삭제한 주문이 실측 날짜별 집계 등에 TTL(300초)까지 잔존한다
    (2026-08-10 운영 사고와 동일 원인).
    """
    _login(client, _make_user("mgr-del-inv", role="MANAGER"))
    order = _make_order("MEASURE")
    oid = order.id

    with patch(
        "foms.services.common.dashboard_cache."
        "invalidate_dashboard_caches_after_delete_transition"
    ) as inv:
        resp = _bulk_delete(client, [oid])

    assert resp.status_code == 200, resp.get_data(as_text=True)
    db_session.expire_all()
    assert db_session.get(Order, oid).deleted_at is not None
    inv.assert_called_once_with("order_bulk_delete")
