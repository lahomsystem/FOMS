"""고객컨펌 승인 → 생산 단계 E2E (2026-09-17) — PC·모바일 동일 계약, 멱등, 이다은 재현.

* ``POST /api/orders/<id>/quest/approve`` 본문 ``{}`` 의 CONFIRM 최종 승인이 PRODUCTION 까지 옮긴다
  (``CUSTOMER_CONFIRMED`` 이벤트 1건, PRODUCTION quest 미생성, blueprint.customer_confirmed).
* 모바일이 보내는 헤더가 있어도 없어도 같은 엔드포인트·같은 계약이다.
* 같은 Idempotency-Key 재요청은 두 번 전이하지 않는다.
* DRAWING 은 여전히 409 COMMAND_REQUIRED.
* 이다은 재현: quest COMPLETED(한글 stage) + 단계 CONFIRM + run 0 → 표시 is_done, 보드 제작대기·승인됨,
  [제작 시작] 200 → PRODUCTION + run 1.
"""
from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.erp_quest_display import resolve_current_quest
from foms.services.production_dashboard_display import build_production_enriched_rows
from models import Order, OrderEvent, ProductionRun, User


def _make_user(username: str, *, role: str = "ADMIN", team: str = "SALES") -> User:
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
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _open_confirm_quest() -> dict:
    return {
        "stage": "CONFIRM",
        "title": "고객 컨펌",
        "description": "",
        "owner_team": "SALES",
        "owner_person": "",
        "status": "OPEN",
        "required_approvals": ["CS", "SALES"],
        "team_approvals": {},
        "approval_mode": "assignee",
        "assignee_approval": {
            "approved": False, "approved_by": None, "approved_by_name": None, "approved_at": None,
        },
        "created_at": "2026-09-16T00:00:00",
        "updated_at": "2026-09-16T00:00:00",
    }


def _create_order(*, stage: str, sd: dict) -> Order:
    order = Order(
        received_date="2026-09-16",
        customer_name="흐름 고객",
        phone="010-1234-5678",
        address="서울 테헤란로 123",
        product="붙박이장",
        status=stage,
        is_erp_order=True,
        structured_data=sd,
        erp_stage_code=stage,
    )
    db_session.add(order)
    db_session.commit()
    return order


def _confirm_order(*, quests: list[dict] | None = None) -> Order:
    return _create_order(
        stage="CONFIRM",
        sd={"workflow": {"stage": "CONFIRM"}, "quests": quests if quests is not None else [_open_confirm_quest()]},
    )


def _events(order_id: int, event_type: str) -> list[OrderEvent]:
    return (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id, OrderEvent.event_type == event_type)
        .all()
    )


def _assert_confirm_transitioned(order_id: int, body: dict) -> None:
    assert body["success"] is True
    assert body["all_approved"] is True
    assert body["missing_teams"] == []
    assert body["auto_transitioned"] is True
    assert body["next_stage"] == "생산"
    assert body["quest"]["status"] == "COMPLETED"

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    sd = saved.structured_data
    assert sd["workflow"]["stage"] == "PRODUCTION"
    assert saved.erp_stage_code == "PRODUCTION"
    assert sd["blueprint"]["customer_confirmed"] is True
    stages = [q.get("stage") for q in sd["quests"]]
    assert "PRODUCTION" not in stages and "생산" not in stages
    assert len(_events(order_id, "CUSTOMER_CONFIRMED")) == 1
    assert _events(order_id, "PRODUCTION_STARTED") == []
    # 승인만으로는 run 이 생기지 않는다 — 제작 시작이 run 을 발급한다.
    assert db_session.query(ProductionRun).filter(ProductionRun.order_id == order_id).count() == 0


# --------------------------------------------------------------------------- #
# 1. PC 승인 → PRODUCTION
# --------------------------------------------------------------------------- #
def test_pc_confirm_approval_moves_to_production(client):
    _login(client, _make_user("flow_pc"))
    order_id = _confirm_order().id

    resp = client.post(f"/api/orders/{order_id}/quest/approve", json={})
    assert resp.status_code == 200, resp.get_json()
    _assert_confirm_transitioned(order_id, resp.get_json())


# --------------------------------------------------------------------------- #
# 2. 모바일 헤더 유무와 무관 — 같은 엔드포인트, 같은 계약
# --------------------------------------------------------------------------- #
def test_mobile_headers_do_not_change_the_contract(client):
    """모바일 카드(erp-quest-approve.js)가 보내는 헤더로 한 번, 헤더 없이 한 번 — 응답 키·값이 같다."""
    _login(client, _make_user("flow_mobile"))
    mobile_id = _confirm_order().id
    plain_id = _confirm_order().id

    mobile = client.post(
        f"/api/orders/{mobile_id}/quest/approve",
        json={},
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile/15E148",
        },
    )
    plain = client.post(f"/api/orders/{plain_id}/quest/approve", json={})
    assert mobile.status_code == 200, mobile.get_json()
    assert plain.status_code == 200, plain.get_json()
    _assert_confirm_transitioned(mobile_id, mobile.get_json())
    _assert_confirm_transitioned(plain_id, plain.get_json())

    keys = ("success", "all_approved", "missing_teams", "auto_transitioned", "next_stage")
    assert {k: mobile.get_json()[k] for k in keys} == {k: plain.get_json()[k] for k in keys}


# --------------------------------------------------------------------------- #
# 3. 같은 Idempotency-Key 재요청 → 전이 1회
# --------------------------------------------------------------------------- #
def test_same_idempotency_key_transitions_once(client):
    _login(client, _make_user("flow_idem"))
    order_id = _confirm_order().id
    headers = {"Idempotency-Key": "confirm-approve-idem-1"}

    first = client.post(f"/api/orders/{order_id}/quest/approve", json={}, headers=headers)
    second = client.post(f"/api/orders/{order_id}/quest/approve", json={}, headers=headers)

    assert first.status_code == 200, first.get_json()
    assert first.get_json()["auto_transitioned"] is True
    # 전이 뒤 같은 버튼 재요청은 '이미 넘어감' 으로 거부된다 — PRODUCTION quest 를 만들지 않는다.
    assert second.status_code == 409, second.get_json()
    assert second.get_json()["code"] == "ALREADY_TRANSITIONED"
    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert [q["stage"] for q in saved.structured_data["quests"]] == ["CONFIRM"]
    assert saved.erp_stage_code == "PRODUCTION"
    assert len(_events(order_id, "CUSTOMER_CONFIRMED")) == 1


def test_stale_retap_without_key_does_not_mint_production_quest(client):
    """키 없는 연타(옛 화면)도 같은 이유로 409 — 제작 완료 게이트가 잠기지 않는다(CEO P1)."""
    _login(client, _make_user("flow_stale"))
    order_id = _confirm_order().id
    first = client.post(f"/api/orders/{order_id}/quest/approve", json={})
    second = client.post(f"/api/orders/{order_id}/quest/approve", json={})
    assert first.status_code == 200, first.get_json()
    assert second.status_code == 409, second.get_json()
    assert second.get_json()["code"] == "ALREADY_TRANSITIONED"
    db_session.expire_all()
    quests = db_session.get(Order, order_id).structured_data["quests"]
    assert all(q["stage"] != "생산" and q["stage"] != "PRODUCTION" for q in quests)
    done = client.post(f"/api/orders/{order_id}/production/start", json={})
    assert done.status_code == 200, done.get_json()


def test_team_mode_partial_approval_does_not_transition(client):
    """레거시 team 모드 CONFIRM quest: 한 팀 승인은 기록만, 두 팀째가 전이(음성 대조군)."""
    quest = {
        "stage": "CONFIRM", "title": "고객 컨펌", "status": "OPEN", "approval_mode": "team",
        "owner_team": "SALES", "required_approvals": ["CS", "SALES"], "team_approvals": {},
    }
    order_id = _confirm_order(quests=[quest]).id
    _login(client, _make_user("flow_team_cs", team="CS"))
    first = client.post(f"/api/orders/{order_id}/quest/approve", json={"team": "CS"})
    assert first.status_code == 200, first.get_json()
    body = first.get_json()
    assert body["all_approved"] is False
    assert body["missing_teams"] == ["SALES"]
    assert body["auto_transitioned"] is False
    db_session.expire_all()
    assert db_session.get(Order, order_id).erp_stage_code == "CONFIRM"
    assert _events(order_id, "CUSTOMER_CONFIRMED") == []

    _login(client, _make_user("flow_team_sales", team="SALES"))
    second = client.post(f"/api/orders/{order_id}/quest/approve", json={"team": "SALES"})
    assert second.status_code == 200, second.get_json()
    _assert_confirm_transitioned(order_id, second.get_json())
    assert len(_events(order_id, "CUSTOMER_CONFIRMED")) == 1

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "PRODUCTION"
    assert len(_events(order_id, "CUSTOMER_CONFIRMED")) == 1


# --------------------------------------------------------------------------- #
# 4. DRAWING 은 여전히 409
# --------------------------------------------------------------------------- #
def test_drawing_approval_still_command_required(client):
    _login(client, _make_user("flow_drawing", team="DRAWING"))
    quest = {**_open_confirm_quest(), "stage": "DRAWING", "title": "도면"}
    order_id = _create_order(stage="DRAWING", sd={"workflow": {"stage": "DRAWING"}, "quests": [quest]}).id

    resp = client.post(f"/api/orders/{order_id}/quest/approve", json={})
    assert resp.status_code == 409, resp.get_json()
    assert resp.get_json()["code"] == "COMMAND_REQUIRED"
    db_session.expire_all()
    assert db_session.get(Order, order_id).erp_stage_code == "DRAWING"


# --------------------------------------------------------------------------- #
# 5. 이다은 재현 — 계약 C9 dict 그대로
# --------------------------------------------------------------------------- #
def _lee_daeun_sd() -> dict:
    return {
        "workflow": {"stage": "CONFIRM", "history": [{"stage": "CONFIRM", "note": "도면 수령 확정"}]},
        "quests": [{
            "stage": "고객컨펌", "title": "고객 컨펌", "status": "COMPLETED", "approval_mode": "assignee",
            "required_approvals": ["CS", "SALES"], "team_approvals": {},
            "assignee_approval": {
                "approved": True, "approved_by": 12, "approved_by_name": "이다은담당",
                "approved_at": "2026-09-16T10:00:00",
            },
            "completed_at": "2026-09-16T10:00:00", "updated_at": "2026-09-16T10:00:00",
        }],
        "blueprint": {
            "customer_confirmed": True, "confirmed_at": "2026-09-16T10:00:00", "confirmed_by": "이다은담당",
        },
    }


def test_lee_daeun_reproduction_resolves_via_production_start(client):
    """제보 1(표시 '-')·제보 2(제작 시작 409)가 같은 데이터에서 함께 풀린다."""
    _login(client, _make_user("flow_daeun", team="PRODUCTION"))
    order = _create_order(stage="CONFIRM", sd=_lee_daeun_sd())
    order_id = order.id

    # 제보 1: ERP 대시보드 표시 — COMPLETED quest 를 버리지 않고 is_done 으로 보여 준다.
    shown = resolve_current_quest(order.structured_data, "고객컨펌", "CONFIRM")
    assert shown is not None and shown["is_done"] is True

    # 생산 보드: 단계 CONFIRM 이라 제작대기(호환) + 판정 SSOT 로 승인됨 → [제작 시작] 노출.
    rows = build_production_enriched_rows([order], {}, set())
    assert len(rows) == 1
    assert rows[0]["stage"] == "제작대기"
    assert rows[0]["is_sales_approved"] is True

    # 제보 2: 제작 시작이 quest 게이트를 통과한다.
    resp = client.post(f"/api/orders/{order_id}/production/start", json={})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["new_status"] == "PRODUCTION"

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "PRODUCTION"
    assert saved.structured_data["workflow"]["history"][-1]["note"] == "제작 시작"
    runs = db_session.query(ProductionRun).filter(ProductionRun.order_id == order_id).all()
    assert len(runs) == 1 and runs[0].status == "IN_PROGRESS" and runs[0].is_current is True
    assert build_production_enriched_rows([saved], {}, {saved.id})[0]["stage"] == "제작중"
