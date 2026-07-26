"""TASK-01: OrderTask API·auto upsert 정본 계약 테스트 (red→green).

manual task(팔로업)를 정본 command 로 확정한다:

* **parent scope**: task 는 URL 부모 Order 에 종속 — 다른 order_id 로 접근하면 404
  (cross-order 재부모화/조회 불가).
* **manual role/owner + exact team enum**: actor 는 ERP_EDIT(STAFF+CS/SALES 또는
  ADMIN/MANAGER; VIEWER·타팀 STAFF deny = any-STAFF 금지). owner_team 은 canonical
  enum(TEAMS, MEASURE→SALES 정규화)만 허용하고 임의 문자열은 400. owner_user_id 는
  활성 User 만.
* **version/receipt/event one tx**: create/update/cancel 은 REV-00
  execute_order_mutation 경유로 부모 Order.mutation_version bump + receipt + OrderEvent
  parity 를 한 tx 에 묶고, task.version 도 증가한다.
* **cancel history / hard delete 금지**: DELETE 는 물리 삭제가 아니라 status=CANCELLED
  soft-cancel + OrderEvent(TASK_CANCELLED) 로 이력을 보존한다(row 유지).
* **arbitrary meta 금지**: manual create/update 는 client meta 를 저장하지 않는다(전송 시 400).
* **typed auto upsert same tx + unique auto key**: erp_automation 자동 task 는 typed ORM
  upsert(raw SQL 0)·caller tx·활성 (order_id, auto_key) 중복 0.
"""

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, OrderMutationReceipt, OrderTask, User
from foms.services.orders.erp_automation import apply_auto_tasks, ensure_auto_task

CMD_TASK_CREATE = "TASK_CREATE"
CMD_TASK_UPDATE = "TASK_UPDATE"
CMD_TASK_CANCEL = "TASK_CANCEL"


# --------------------------------------------------------------------------
# 픽스처 / 헬퍼
# --------------------------------------------------------------------------
@pytest.fixture
def policy_on(app):
    """이 테스트 동안만 AUTH-01 정책 가드를 강제 활성화하고 원복한다."""
    sentinel = object()
    prev = app.config.get("AUTH_POLICY_ENABLED", sentinel)
    app.config["AUTH_POLICY_ENABLED"] = True
    yield
    if prev is sentinel:
        app.config.pop("AUTH_POLICY_ENABLED", None)
    else:
        app.config["AUTH_POLICY_ENABLED"] = prev


def _login(client, *, username, role, team=None):
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
    uid = user.id
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["username"] = username
        sess["role"] = role
    return uid


def _mk_user(username, *, is_active=True):
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role="STAFF",
        team="DRAWING",
        name=f"{username}-name",
        is_active=is_active,
    )
    db_session.add(user)
    db_session.commit()
    return user.id


def _create_order(status="RECEIVED"):
    order = Order(
        received_date="2026-04-07",
        customer_name="Task 대상",
        phone="010-1234-5678",
        address="Seoul",
        product="Wardrobe",
        status=status,
        manager_name="Alice",
        is_erp_order=True,
        erp_stage_code=status,
        structured_data={"workflow": {"stage": status}},
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _fresh_order(oid):
    db_session.remove()
    return db_session.query(Order).filter_by(id=oid).first()


def _create_task(client, oid, **body):
    return client.post(f"/api/orders/{oid}/tasks", json=body)


# --------------------------------------------------------------------------
# parent scope: 다른 order_id 로 update/delete → 404, task 불변
# --------------------------------------------------------------------------
def test_task_parent_scope_cross_order_denied(client, app):
    """task 는 진짜 부모 Order 에만 종속 — 다른 order 로 update/delete 하면 404."""
    _login(client, username="cs-parent", role="STAFF", team="CS")
    order_a = _create_order()
    order_b = _create_order()

    resp = _create_task(client, order_a, title="A 팔로업")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    task_id = resp.get_json()["task_id"]

    # 다른 order(B) 경로로 PUT/DELETE → 404
    put = client.put(f"/api/orders/{order_b}/tasks/{task_id}", json={"status": "DONE"})
    assert put.status_code == 404, put.get_data(as_text=True)
    dele = client.delete(f"/api/orders/{order_b}/tasks/{task_id}")
    assert dele.status_code == 404, dele.get_data(as_text=True)

    db_session.remove()
    task = db_session.query(OrderTask).filter_by(id=task_id).first()
    assert task.order_id == order_a
    assert task.status == "OPEN"  # cross-order 시도로 바뀌지 않음


# --------------------------------------------------------------------------
# exact team enum: canonical 팀만 허용, 임의 문자열 400
# --------------------------------------------------------------------------
def test_task_create_rejects_arbitrary_team(client, app):
    """owner_team 은 canonical enum 만 — 임의 문자열은 400 · task 미생성."""
    _login(client, username="cs-team", role="STAFF", team="CS")
    oid = _create_order()

    resp = _create_task(client, oid, title="bad team", owner_team="HACKERS")
    assert resp.status_code == 400, resp.get_data(as_text=True)

    db_session.remove()
    assert db_session.query(OrderTask).filter_by(order_id=oid).count() == 0


def test_task_create_accepts_canonical_team_and_normalizes_measure(client, app):
    """canonical 팀 허용 + MEASURE→SALES 정규화 저장."""
    _login(client, username="cs-team2", role="STAFF", team="CS")
    oid = _create_order()

    ok = _create_task(client, oid, title="drawing 배정", owner_team="drawing")
    assert ok.status_code == 200, ok.get_data(as_text=True)

    measure = _create_task(client, oid, title="measure 배정", owner_team="MEASURE")
    assert measure.status_code == 200, measure.get_data(as_text=True)

    db_session.remove()
    teams = {t.title: t.owner_team for t in db_session.query(OrderTask).filter_by(order_id=oid).all()}
    assert teams["drawing 배정"] == "DRAWING"
    assert teams["measure 배정"] == "SALES"  # MEASURE 정규화


def test_task_create_rejects_inactive_owner_user(client, app):
    """owner_user_id 는 활성 User 만 — 비활성/부재는 400."""
    _login(client, username="cs-owner", role="STAFF", team="CS")
    oid = _create_order()
    inactive = _mk_user("inactive-owner", is_active=False)

    resp = _create_task(client, oid, title="dangling", owner_user_id=inactive)
    assert resp.status_code == 400, resp.get_data(as_text=True)

    missing = _create_task(client, oid, title="ghost", owner_user_id=999999)
    assert missing.status_code == 400, missing.get_data(as_text=True)

    db_session.remove()
    assert db_session.query(OrderTask).filter_by(order_id=oid).count() == 0


# --------------------------------------------------------------------------
# arbitrary meta 금지 · status 검증
# --------------------------------------------------------------------------
def test_task_create_rejects_arbitrary_meta(client, app):
    """manual task 는 client meta 를 받지 않는다 — meta 전송 시 400 · 미생성."""
    _login(client, username="cs-meta", role="STAFF", team="CS")
    oid = _create_order()

    resp = _create_task(client, oid, title="evil", meta={"auto_key": "SPOOF", "x": 1})
    assert resp.status_code == 400, resp.get_data(as_text=True)

    db_session.remove()
    assert db_session.query(OrderTask).filter_by(order_id=oid).count() == 0


def test_task_create_rejects_unknown_status(client, app):
    """status 는 OPEN/IN_PROGRESS/DONE 만 — 임의/CANCELLED 는 400."""
    _login(client, username="cs-status", role="STAFF", team="CS")
    oid = _create_order()

    bad = _create_task(client, oid, title="weird", status="WHATEVER")
    assert bad.status_code == 400, bad.get_data(as_text=True)

    # CANCELLED 는 cancel route 전용 — create 로는 불가
    cancelled = _create_task(client, oid, title="pre-cancel", status="CANCELLED")
    assert cancelled.status_code == 400, cancelled.get_data(as_text=True)


# --------------------------------------------------------------------------
# one-tx: 부모 version bump + receipt + OrderEvent + task.version
# --------------------------------------------------------------------------
def test_task_create_bumps_order_version_and_writes_receipt_event(client, app):
    """create 는 부모 mutation_version++ · receipt 1 · OrderEvent(TASK_CREATED) 1 · task.version=1."""
    _login(client, username="cs-onetx", role="STAFF", team="CS")
    oid = _create_order()
    before = _fresh_order(oid).mutation_version

    resp = _create_task(client, oid, title="one tx")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    task_id = resp.get_json()["task_id"]

    fresh = _fresh_order(oid)
    assert fresh.mutation_version == before + 1

    events = db_session.query(OrderEvent).filter_by(order_id=oid, event_type="TASK_CREATED").all()
    assert len(events) == 1
    assert db_session.query(OrderMutationReceipt).filter_by(policy_id=CMD_TASK_CREATE).count() == 1

    task = db_session.query(OrderTask).filter_by(id=task_id).first()
    assert task.version == 1
    assert task.task_uuid  # DB-global identity 발급
    assert task.provenance == "MANUAL"


def test_task_update_bumps_version_and_event(client, app):
    """update 는 부모 version++ · OrderEvent(TASK_UPDATED) · task.version 증가."""
    _login(client, username="cs-upd", role="STAFF", team="CS")
    oid = _create_order()
    task_id = _create_task(client, oid, title="v1").get_json()["task_id"]
    mid = _fresh_order(oid).mutation_version

    resp = client.put(f"/api/orders/{oid}/tasks/{task_id}", json={"title": "v2", "status": "IN_PROGRESS"})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    assert _fresh_order(oid).mutation_version == mid + 1
    task = db_session.query(OrderTask).filter_by(id=task_id).first()
    assert task.title == "v2" and task.status == "IN_PROGRESS"
    assert task.version == 2  # create=1 → update=2
    assert db_session.query(OrderEvent).filter_by(order_id=oid, event_type="TASK_UPDATED").count() == 1


# --------------------------------------------------------------------------
# cancel history / hard delete 금지
# --------------------------------------------------------------------------
def test_task_delete_is_soft_cancel_with_history(client, app):
    """DELETE 는 물리 삭제 0 — status=CANCELLED soft-cancel + OrderEvent(TASK_CANCELLED)."""
    _login(client, username="cs-cancel", role="STAFF", team="CS")
    oid = _create_order()
    task_id = _create_task(client, oid, title="to cancel").get_json()["task_id"]
    mid = _fresh_order(oid).mutation_version

    resp = client.delete(f"/api/orders/{oid}/tasks/{task_id}")
    assert resp.status_code == 200, resp.get_data(as_text=True)

    db_session.remove()
    task = db_session.query(OrderTask).filter_by(id=task_id).first()
    assert task is not None                      # hard delete 아님 — row 유지
    assert task.status == "CANCELLED"            # soft-cancel
    assert _fresh_order(oid).mutation_version == mid + 1
    assert db_session.query(OrderEvent).filter_by(order_id=oid, event_type="TASK_CANCELLED").count() == 1


# --------------------------------------------------------------------------
# idempotency: 같은 key create → task 1 · version 1회 bump
# --------------------------------------------------------------------------
def test_task_create_same_idempotency_key_creates_once(client, app):
    """같은 Idempotency-Key create 재요청은 replay — task 1 · version 1회 bump."""
    _login(client, username="cs-idem", role="STAFF", team="CS")
    oid = _create_order()
    before = _fresh_order(oid).mutation_version
    headers = {"Idempotency-Key": "22222222-2222-2222-2222-222222222222"}
    body = {"title": "한 번만"}

    r1 = client.post(f"/api/orders/{oid}/tasks", json=body, headers=headers)
    r2 = client.post(f"/api/orders/{oid}/tasks", json=body, headers=headers)
    assert r1.status_code == 200 and r2.status_code == 200, (r1.get_data(as_text=True), r2.get_data(as_text=True))

    db_session.remove()
    assert db_session.query(OrderTask).filter_by(order_id=oid).count() == 1
    assert _fresh_order(oid).mutation_version == before + 1


# --------------------------------------------------------------------------
# If-Match(부모 version) 낙관 잠금
# --------------------------------------------------------------------------
def test_task_create_stale_if_match_conflicts_no_change(client, app):
    """stale If-Match → 409 · task/version/event 완전 불변."""
    _login(client, username="cs-stale", role="STAFF", team="CS")
    oid = _create_order()
    before = _fresh_order(oid).mutation_version

    resp = client.post(
        f"/api/orders/{oid}/tasks",
        json={"title": "stale"},
        headers={"If-Match": str(before + 5)},
    )
    assert resp.status_code == 409, resp.get_data(as_text=True)

    db_session.remove()
    assert db_session.query(OrderTask).filter_by(order_id=oid).count() == 0
    assert _fresh_order(oid).mutation_version == before


# --------------------------------------------------------------------------
# actor 권한(AUTH-01) — any-STAFF 금지: CS/SALES/ADMIN/MANAGER 만
# --------------------------------------------------------------------------
@pytest.mark.parametrize("role,team", [
    ("STAFF", "CS"),
    ("STAFF", "SALES"),
    ("ADMIN", None),
    ("MANAGER", None),
])
def test_task_create_allows_eligible_actors(client, app, policy_on, role, team):
    """STAFF+CS/SALES · ADMIN · MANAGER 는 task 생성 200."""
    _login(client, username=f"ok-{role}-{team}", role=role, team=team)
    oid = _create_order()
    resp = _create_task(client, oid, title="allowed")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.headers.get("X-Auth-Policy") is None


@pytest.mark.parametrize("role,team", [
    ("VIEWER", None),
    ("STAFF", "DRAWING"),
    ("STAFF", "PRODUCTION"),
])
def test_task_create_denies_ineligible_actors(client, app, policy_on, role, team):
    """VIEWER·타팀 STAFF(any-STAFF 금지) 는 403 · task/event/receipt 0."""
    _login(client, username=f"no-{role}-{team}", role=role, team=team)
    oid = _create_order()
    resp = _create_task(client, oid, title="denied")
    assert resp.status_code == 403, resp.get_data(as_text=True)
    assert resp.headers.get("X-Auth-Policy") == "denied"

    db_session.remove()
    assert db_session.query(OrderTask).filter_by(order_id=oid).count() == 0
    assert db_session.query(OrderEvent).filter_by(order_id=oid).count() == 0
    assert db_session.query(OrderMutationReceipt).count() == 0


# --------------------------------------------------------------------------
# typed auto upsert same tx + unique auto key
# --------------------------------------------------------------------------
def test_auto_task_upsert_unique_key(client, app):
    """apply_auto_tasks 재적용 시 활성 (order_id, auto_key) 중복 0 (typed upsert)."""
    oid = _create_order()
    sd = {
        "flags": {"urgent": True, "urgent_reason": "hot"},
        "workflow": {"stage": "RECEIVED"},
        "assignments": {"owner_team": "CS"},
    }
    apply_auto_tasks(db_session, oid, sd)
    db_session.commit()
    apply_auto_tasks(db_session, oid, sd)  # 두 번째 적용
    db_session.commit()

    db_session.remove()
    urgent = [
        t for t in db_session.query(OrderTask).filter_by(order_id=oid).all()
        if (t.meta or {}).get("auto_key") == "AUTO_URGENT" and t.status in ("OPEN", "IN_PROGRESS")
    ]
    assert len(urgent) == 1                    # 중복 0
    assert urgent[0].provenance == "AUTO"
    assert urgent[0].task_uuid                  # identity 발급


def test_auto_task_upsert_shares_caller_tx(client, app):
    """auto upsert 는 내부 commit 하지 않는다 — caller rollback 이면 task 미저장(same tx)."""
    oid = _create_order()
    ensure_auto_task(
        db_session, oid, auto_key="AUTO_URGENT", title="긴급",
        owner_team="CS", due_date=None, meta={"auto_key": "AUTO_URGENT"},
    )
    db_session.rollback()  # caller 가 tx 를 무른다

    db_session.remove()
    assert db_session.query(OrderTask).filter_by(order_id=oid).count() == 0


def test_erp_automation_has_no_raw_sql():
    """erp_automation 은 raw SQL(text/execute) 을 쓰지 않는다(typed ORM upsert)."""
    import inspect
    from foms.services.orders import erp_automation

    src = inspect.getsource(erp_automation)
    assert "text(" not in src
    assert ".execute(" not in src
