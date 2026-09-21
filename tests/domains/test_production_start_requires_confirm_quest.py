"""생산 시작의 CONFIRM 호환 경로는 승인 완료된 CONFIRM quest 를 요구한다(2026-09-20 F2, C5).

예전에는 ``_stage_quest_block`` 이 "quest 없음 = 게이트 안 함" 이라 CONFIRM 주문에 quest 가
없으면 승인 없이 제작을 시작할 수 있었다. 이제 ``require_quest=True`` 로 quest 없음도 409 다
(code 는 소비자 호환을 위해 ``QUEST_INCOMPLETE`` 그대로, 구분은 ``reason: QUEST_MISSING``).

운영에 'CONFIRM 인데 CONFIRM quest 없음' 이 1건 있다 — 화면 승인 버튼(합성 assignee quest)이
quest 를 만들고 CONFIRM→PRODUCTION 전이까지 하므로 막다른 길이 아님을 여기서 못박는다.
run-only(PRODUCTION) 경로와 ``production/complete`` 는 이 변경과 무관하다(대조군).
"""
from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, ProductionRun, User
from tests.support.quest_seed import confirm_quest_completed, confirm_quest_open


def _make_user(username: str, *, role: str = "STAFF", team: str = "PRODUCTION") -> User:
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team=team,
        name=f"{username} 이름",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user: User) -> None:
    _login_as(client, user.id, user.username, user.role)


def _login_as(client, user_id: int, username: str, role: str) -> None:
    """expire_all() 뒤에도 쓸 수 있게 ORM 객체 대신 값으로 로그인한다."""
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = username
        sess["role"] = role


def _make_order(stage_code: str, quests: list[dict] | None) -> Order:
    """ERP 주문 1건. ``quests`` 가 None 이면 structured_data 에 quests 키 자체를 넣지 않는다."""
    sd: dict = {"workflow": {"stage": stage_code}}
    if quests is not None:
        sd["quests"] = quests
    order = Order(
        received_date="2026-09-20",
        customer_name="컨펌 게이트 고객",
        phone="010-0000-0000",
        address="Seoul",
        product="붙박이장",
        status=stage_code,
        manager_name="Bob",
        is_erp_order=True,
        structured_data=sd,
        erp_stage_code=stage_code,
    )
    db_session.add(order)
    db_session.commit()
    return order


def _mint_run(order_id: int) -> ProductionRun:
    run = ProductionRun(order_id=order_id, status="IN_PROGRESS", steps=[], defects=[], is_current=True)
    db_session.add(run)
    db_session.commit()
    return run


def _start(client, order_id: int, body: dict | None = None):
    return client.post(f"/api/orders/{order_id}/production/start", json=body or {})


def _saved(order_id: int) -> Order:
    db_session.expire_all()
    return db_session.get(Order, order_id)


# --------------------------------------------------------------------------- #
# 1. CONFIRM 인데 quest 없음 → 409 QUEST_MISSING, 상태 불변
# --------------------------------------------------------------------------- #
def test_confirm_without_quest_is_rejected_with_quest_missing(client):
    """CONFIRM + quests 없음 → 409 QUEST_INCOMPLETE / reason QUEST_MISSING / missing_teams CS·SALES."""
    _login(client, _make_user("cq_missing"))
    order_id = _make_order("CONFIRM", None).id

    resp = _start(client, order_id)
    assert resp.status_code == 409, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["success"] is False
    assert body["code"] == "QUEST_INCOMPLETE"
    assert body["reason"] == "QUEST_MISSING"
    assert body["missing_teams"] == ["CS", "SALES"]
    assert body["message"] == "고객컨펌 승인이 먼저 필요합니다."  # 문구 SSOT = STAGE_LABELS["CONFIRM"]

    saved = _saved(order_id)
    assert saved.erp_stage_code == "CONFIRM"
    assert db_session.query(ProductionRun).filter_by(order_id=order_id).count() == 0


def test_confirm_with_empty_quest_list_is_also_missing(client):
    """quests 가 빈 리스트여도 quest 없음과 같다(409 QUEST_MISSING)."""
    _login(client, _make_user("cq_empty"))
    order_id = _make_order("CONFIRM", []).id

    resp = _start(client, order_id)
    assert resp.status_code == 409
    assert resp.get_json()["reason"] == "QUEST_MISSING"
    assert _saved(order_id).erp_stage_code == "CONFIRM"


# --------------------------------------------------------------------------- #
# 2. OPEN quest → 기존 409(reason 없음, missing ASSIGNEE)
# --------------------------------------------------------------------------- #
def test_confirm_with_open_quest_keeps_legacy_incomplete_shape(client):
    """CONFIRM + OPEN quest → 409 QUEST_INCOMPLETE, body 에 reason 키 없음, missing ['ASSIGNEE']."""
    _login(client, _make_user("cq_open"))
    order_id = _make_order("CONFIRM", [confirm_quest_open()]).id

    resp = _start(client, order_id)
    assert resp.status_code == 409, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["code"] == "QUEST_INCOMPLETE"
    assert "reason" not in body
    assert body["missing_teams"] == ["ASSIGNEE"]
    assert _saved(order_id).erp_stage_code == "CONFIRM"


# --------------------------------------------------------------------------- #
# 3·4. COMPLETED quest → 200 (코드 저장형·한글 저장형 둘 다)
# --------------------------------------------------------------------------- #
def test_confirm_with_completed_quest_starts_production(client):
    """CONFIRM + COMPLETED quest → 200, new_status PRODUCTION."""
    _login(client, _make_user("cq_done"))
    order_id = _make_order("CONFIRM", [confirm_quest_completed()]).id

    resp = _start(client, order_id)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["new_status"] == "PRODUCTION"
    assert _saved(order_id).erp_stage_code == "PRODUCTION"


def test_confirm_with_korean_stage_quest_is_matched_by_alias(client):
    """quest.stage 가 한글 저장형 '고객컨펌' 이어도 별칭으로 찾아 200."""
    _login(client, _make_user("cq_korean"))
    order_id = _make_order("CONFIRM", [confirm_quest_completed(stage="고객컨펌")]).id

    resp = _start(client, order_id)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _saved(order_id).erp_stage_code == "PRODUCTION"


# --------------------------------------------------------------------------- #
# 5·6. 대조군 — run-only 경로와 production/complete 는 quest 없어도 게이트 안 함
# --------------------------------------------------------------------------- #
def test_production_run_only_path_does_not_require_quest(client):
    """PRODUCTION(run 없음) + quests 없음 → start 200 run_started True(run-only 경로는 quest 무관)."""
    _login(client, _make_user("cq_runonly"))
    order_id = _make_order("PRODUCTION", None).id

    resp = _start(client, order_id)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["run_started"] is True
    assert _saved(order_id).erp_stage_code == "PRODUCTION"
    assert db_session.query(ProductionRun).filter_by(order_id=order_id, is_current=True).count() == 1


def test_production_complete_does_not_require_production_quest(client):
    """PRODUCTION + current run + quests 없음 → production/complete 200(complete 는 require_quest False)."""
    _login(client, _make_user("cq_complete"))
    order_id = _make_order("PRODUCTION", None).id
    _mint_run(order_id)

    resp = client.post(f"/api/orders/{order_id}/production/complete", json={})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _saved(order_id).erp_stage_code == "CONSTRUCTION"


# --------------------------------------------------------------------------- #
# 7. 운영 1건 재현 — quest 없는 CONFIRM 주문은 막다른 길이 아니다
# --------------------------------------------------------------------------- #
def test_missing_confirm_quest_is_recoverable_via_approve_button(client):
    """start 409 → SALES 담당 승인 `{}`(합성 quest) → CONFIRM→PRODUCTION 자동 전이 → start 200."""
    production_user = _make_user("cq_prod_recover")
    sales_user = _make_user("cq_sales_recover", team="SALES")
    production_login = (production_user.id, production_user.username, production_user.role)
    sales_login = (sales_user.id, sales_user.username, sales_user.role)
    order_id = _make_order("CONFIRM", None).id

    _login_as(client, *production_login)
    blocked = _start(client, order_id)
    assert blocked.status_code == 409 and blocked.get_json()["reason"] == "QUEST_MISSING"

    _login_as(client, *sales_login)
    approved = client.post(f"/api/orders/{order_id}/quest/approve", json={})
    assert approved.status_code == 200, approved.get_data(as_text=True)
    approved_body = approved.get_json()
    assert approved_body["success"] is True
    assert approved_body["auto_transitioned"] is True
    saved = _saved(order_id)
    assert saved.erp_stage_code == "PRODUCTION"
    # 승인 버튼이 합성 quest 를 저장했다(quest 없음 상태가 해소됨).
    stored = [q for q in saved.structured_data.get("quests", []) if q.get("stage") in ("CONFIRM", "고객컨펌")]
    assert stored and str(stored[0].get("status")).upper() == "COMPLETED"

    _login_as(client, *production_login)
    started = _start(client, order_id)
    assert started.status_code == 200, started.get_data(as_text=True)
    assert started.get_json()["run_started"] is True


# --------------------------------------------------------------------------- #
# 8. same-key replay — receipt 가 있으면 게이트를 다시 검사하지 않는다
# --------------------------------------------------------------------------- #
def test_same_key_replay_skips_quest_gate(client):
    """첫 요청 200 뒤 quest 를 지워도 같은 Idempotency-Key 재요청은 200 replay(게이트는 receipt 없을 때만)."""
    _login(client, _make_user("cq_replay"))
    order_id = _make_order("CONFIRM", [confirm_quest_completed()]).id
    headers = {"Idempotency-Key": "cq-replay-key-0001"}

    first = client.post(f"/api/orders/{order_id}/production/start", json={}, headers=headers)
    assert first.status_code == 200, first.get_data(as_text=True)

    # quest 를 지운다 — 게이트를 다시 탄다면 (stage 가 PRODUCTION + run 있음이라) 409 가 난다.
    saved = _saved(order_id)
    sd = dict(saved.structured_data)
    sd.pop("quests", None)
    saved.structured_data = sd
    db_session.commit()

    second = client.post(f"/api/orders/{order_id}/production/start", json={}, headers=headers)
    assert second.status_code == 200, second.get_data(as_text=True)
    assert db_session.query(ProductionRun).filter_by(order_id=order_id).count() == 1


# --------------------------------------------------------------------------- #
# 9. 관리자 강제 진행 — 승인이 없어도 사유를 적으면 뚫린다(ADMIN-OVERRIDE-01)
# --------------------------------------------------------------------------- #
def test_admin_override_punches_confirm_quest_gate(client):
    """ADMIN 이 admin_override 와 사유를 실으면 CONFIRM 승인 없이도 제작이 시작된다.

    평소 거부(위 1번)는 음성 대조군으로 그대로 남는다 — 그냥 클릭은 관리자도 막힌다.
    """
    _login(client, _make_user("cq_admin_punch", role="ADMIN"))
    order_id = _make_order("CONFIRM", None).id

    resp = _start(client, order_id, {"admin_override": True,
                                     "override_reason": "고객이 전화로 컨펌해 관리자가 진행"})

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _saved(order_id).erp_stage_code == "PRODUCTION"
    events = (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id,
                OrderEvent.event_type == "ADMIN_OVERRIDE_USED")
        .all()
    )
    assert len(events) == 1
    payload = events[0].payload
    assert payload["gates"] == ["QUEST_INCOMPLETE"]
    assert payload["route"] == "erp_orders_production.api_production_start"
    assert payload["from"] == "CONFIRM"
    assert payload["to"] == "PRODUCTION"
    assert payload["reason"] == "고객이 전화로 컨펌해 관리자가 진행"


def test_staff_admin_override_is_rejected_with_admin_only(client):
    """음성 대조군 — STAFF 가 admin_override 를 켜면 게이트 코드가 아니라 403 ADMIN_ONLY."""
    _login(client, _make_user("cq_staff_try"))
    order_id = _make_order("CONFIRM", None).id

    resp = _start(client, order_id, {"admin_override": True, "override_reason": "그냥"})

    assert resp.status_code == 403, resp.get_data(as_text=True)
    assert resp.get_json()["code"] == "ADMIN_ONLY"
    assert _saved(order_id).erp_stage_code == "CONFIRM"
