"""수령 확정의 고객 OK 기록 + 확정 → 고객 컨펌 두 요청 흐름(설계서 2026-09-29 §4.2 · §3.6 · §7.1 S1).

* ``confirm-drawing-receipt`` 본문의 선택 키 ``customer_ok``·``customer_ok_via``·``customer_ok_note``
  가 마지막 ``CONFIRM_RECEIPT`` 이력 항목에 ``customer_ok`` 로 붙는다. 값이 이상하면 버리고
  확정은 진행한다(설명용 값으로 확정을 막지 않는다). 라우트 파일은 한 줄도 늘지 않는다.
* 도면 탭의 [고객 OK · 확정]은 확정 → ``quest/approve`` 를 차례로 부른다. 새 흐름이
  C21 게이트(도면 CONFIRMED 아니면 409)를 그대로 타고, 컨펌 가능 예측
  ``can_approve_after_confirm`` 이 승인 라우트와 **같은 quest 고르기**를 쓴다.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date

import pytest
from flask import template_rendered
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.orders.drawing_customer_send_view import can_approve_after_confirm
from models import Order, User

SALES = "영업확정"


def _user(username, *, role="MANAGER", team="SALES", name=SALES):
    u = User(username=username, password=generate_password_hash("pw"), role=role, team=team,
             name=name, is_active=True)
    db_session.add(u)
    db_session.commit()
    return u


def _login(client, user):
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = user.id, user.username, user.role


def _confirm_quest(*, status="OPEN", mode="assignee", required=("CS", "SALES"), created="2026-09-16T00:00:00",
                   completed=None):
    q = {
        "stage": "CONFIRM", "title": "고객 컨펌", "description": "", "owner_team": "SALES",
        "owner_person": "", "status": status, "required_approvals": list(required),
        "team_approvals": {}, "approval_mode": mode,
        "assignee_approval": {"approved": False, "approved_by": None, "approved_by_name": None,
                              "approved_at": None},
        "created_at": created, "updated_at": created,
    }
    if completed:
        q["completed_at"] = completed
    return q


def _order(*, stage="DRAWING", drawing_status="TRANSFERRED", quests=None, extra_history=()):
    order = Order(received_date=date.today().strftime("%Y-%m-%d"), customer_name="확정고객",
                  phone="010-7", address="서울", product="붙박이장", status=stage,
                  manager_name=SALES, is_erp_order=True, erp_stage_code=stage, structured_data={})
    db_session.add(order)
    db_session.commit()
    v1 = f"orders/{order.id}/drawing_wizard/exports/v1.png"
    order.structured_data = {
        "parties": {"customer": {"name": "확정고객", "phone": "010-2473-6730"}, "manager": {"name": SALES}},
        "workflow": {"stage": stage},
        "drawing_status": drawing_status,
        "drawing_current_files": [{"key": v1, "filename": "v1.png"}],
        "drawing_transfer_history": [
            {"action": "TRANSFER", "at": "2026-09-29 01:00:00", "files": [{"key": v1}],
             "previous_current_files": []},
            *extra_history,
        ],
        "quests": list(quests) if quests is not None else [_confirm_quest()],
    }
    db_session.commit()
    return order.id


def _sd(oid):
    db_session.expire_all()
    return dict(db_session.get(Order, oid).structured_data or {})


def _last_receipt(sd):
    return [h for h in sd["drawing_transfer_history"] if h.get("action") == "CONFIRM_RECEIPT"][-1]


def _confirm(client, oid, **body):
    return client.post(f"/api/orders/{oid}/confirm-drawing-receipt", json=body)


def _approve(client, oid, key="k-1"):
    return client.post(f"/api/orders/{oid}/quest/approve", json={"idempotency_key": key})


# ── ① ~ ③ 기록 ───────────────────────────────────────────────────────────────
def test_customer_ok_fields_attach_to_last_confirm_receipt(client):
    _login(client, _user("ok_a"))
    oid = _order()
    res = _confirm(client, oid, customer_ok=True, customer_ok_via="kakao", customer_ok_note="이대로 좋대요")
    assert res.status_code == 200, res.get_json()
    entry = _last_receipt(_sd(oid))
    assert entry["customer_ok"] == {"confirmed_by_customer": True, "via": "kakao", "note": "이대로 좋대요"}


def test_empty_body_keeps_today_entry(client):
    _login(client, _user("ok_b"))
    oid = _order()
    assert _confirm(client, oid).status_code == 200
    assert "customer_ok" not in _last_receipt(_sd(oid))


def test_bad_values_are_dropped_and_confirm_proceeds(client):
    _login(client, _user("ok_c"))
    oid = _order()
    res = _confirm(client, oid, customer_ok=False, customer_ok_via="fax", customer_ok_note="가" * 250)
    assert res.status_code == 200, res.get_json()
    sd = _sd(oid)
    assert sd["drawing_status"] == "CONFIRMED"
    ok = _last_receipt(sd)["customer_ok"]
    assert ok["confirmed_by_customer"] is False
    assert ok["via"] is None
    assert ok["note"] == "가" * 200


def test_non_string_note_is_dropped(client):
    _login(client, _user("ok_c2"))
    oid = _order()
    assert _confirm(client, oid, customer_ok=True, customer_ok_note={"x": 1}).status_code == 200
    ok = _last_receipt(_sd(oid))["customer_ok"]
    assert ok["note"] == "" and ok["via"] is None and ok["confirmed_by_customer"] is True


# ── ④ 확정 → 컨펌 → 생산 ─────────────────────────────────────────────────────
def test_confirm_then_approve_moves_to_production(client):
    _login(client, _user("ok_d"))
    oid = _order()
    res = _confirm(client, oid, customer_ok=True)
    assert res.status_code == 200
    assert res.get_json()["new_stage"] == "CONFIRM"
    res2 = _approve(client, oid)
    assert res2.status_code == 200, res2.get_json()
    body = res2.get_json()
    assert body["success"] is True and body["auto_transitioned"] is True
    assert _sd(oid)["workflow"]["stage"] == "PRODUCTION"


# ── ⑤ C21 고정 ───────────────────────────────────────────────────────────────
def test_c21_approve_on_returned_confirm_order_is_409(client):
    _login(client, _user("ok_e"))
    oid = _order(stage="CONFIRM", drawing_status="RETURNED")
    res = _approve(client, oid)
    assert res.status_code == 409
    assert _sd(oid)["workflow"]["stage"] == "CONFIRM"


# ── ⑥ 컨펌 권한 없는 사용자 ─────────────────────────────────────────────────
def test_user_without_approve_right_confirms_but_approve_is_403(client):
    # 주문 담당 영업이라 확정은 되지만, 이 주문의 고객 컨펌 quest 는 생산팀 승인으로 넓혀 저장돼
    # 있어(정책보다 넓은 저장값은 존중된다) 영업은 승인 팀이 아니다.
    user = _user("ok_f", role="STAFF", team="SALES")
    _login(client, user)
    oid = _order(quests=[_confirm_quest(mode="team", required=("PRODUCTION",))])
    assert _confirm(client, oid, customer_ok=True).status_code == 200
    res = _approve(client, oid)
    assert res.status_code == 403
    sd = _sd(oid)
    assert sd["workflow"]["stage"] == "CONFIRM" and sd["drawing_status"] == "CONFIRMED"


# ── ⑦ 확정 뒤 재수정의 재확정 ────────────────────────────────────────────────
def test_reconfirm_after_production_cannot_predict_approve():
    user = _user("ok_g")
    oid = _order(stage="PRODUCTION", drawing_status="TRANSFERRED")
    order = db_session.get(Order, oid)
    assert can_approve_after_confirm(user, order, order.structured_data) is False


def test_predict_true_on_drawing_and_confirm_stage():
    user = _user("ok_g2")
    for stage in ("DRAWING", "CONFIRM", "고객컨펌"):
        oid = _order(stage=stage)
        order = db_session.get(Order, oid)
        assert can_approve_after_confirm(user, order, order.structured_data) is True, stage


def test_predict_false_for_production_team_user():
    user = _user("ok_g3", role="STAFF", team="PRODUCTION")
    oid = _order()
    order = db_session.get(Order, oid)
    assert can_approve_after_confirm(user, order, order.structured_data) is False


# ── ⑧ 확정만 → 바에 approve_confirm → 승인 → 생산 ──────────────────────────
@contextmanager
def _captured(app):
    recorded = []

    def record(sender, template, context, **extra):
        recorded.append(context)

    template_rendered.connect(record, app)
    try:
        yield recorded
    finally:
        template_rendered.disconnect(record, app)


def _bar_keys(app, client, oid):
    with _captured(app) as contexts:
        res = client.get(f"/erp/drawing-workbench/{oid}")
    assert res.status_code == 200
    cs = next(c for c in contexts if "customer_send" in c)["customer_send"]
    return [b["key"] for b in cs["bar"]], cs


def test_confirm_only_then_bar_approve_confirm_then_production(app, client):
    _login(client, _user("ok_h"))
    oid = _order()
    assert _confirm(client, oid, customer_ok=True).status_code == 200
    keys, cs = _bar_keys(app, client, oid)
    assert "approve_confirm" in keys and "production" not in keys
    assert cs["can_approve_after_confirm"] is True
    assert _approve(client, oid).status_code == 200
    assert _sd(oid)["workflow"]["stage"] == "PRODUCTION"
    keys_after, _ = _bar_keys(app, client, oid)
    assert "approve_confirm" not in keys_after and "production" in keys_after


def test_confirm_only_without_right_shows_production_link(app, client):
    user = _user("ok_h2", role="STAFF", team="SALES")
    _login(client, user)
    oid = _order(quests=[_confirm_quest(mode="team", required=("PRODUCTION",))])
    assert _confirm(client, oid).status_code == 200
    keys, cs = _bar_keys(app, client, oid)
    assert "approve_confirm" not in keys
    assert cs["can_approve_after_confirm"] is False


# ── ⑨ 옛 팀 모드 quest ──────────────────────────────────────────────────────
def test_old_team_mode_quest_success_but_not_all_approved(client):
    _login(client, _user("ok_i"))
    oid = _order(quests=[_confirm_quest(mode="team", required=("CS", "SALES"))])
    assert _confirm(client, oid).status_code == 200
    res = _approve(client, oid)
    assert res.status_code == 200, res.get_json()
    body = res.get_json()
    assert body["success"] is True and body["all_approved"] is False
    assert body["missing_teams"]
    assert _sd(oid)["workflow"]["stage"] == "CONFIRM"


# ── ⑩ 같은 승인 두 번 ───────────────────────────────────────────────────────
def test_second_approve_is_already_transitioned(client):
    _login(client, _user("ok_j"))
    oid = _order()
    assert _confirm(client, oid).status_code == 200
    assert _approve(client, oid, key="k-a").status_code == 200
    res = _approve(client, oid, key="k-b")
    assert res.status_code == 409
    assert res.get_json()["code"] == "ALREADY_TRANSITIONED"


# ── ⑪ 예측과 승인 라우트가 같은 quest 를 고른다(모집단 안 대조군) ──────────
def test_prediction_picks_same_quest_as_approve_route(client):
    """같은 단계 quest 둘 — 완료된 것(SALES 가 승인 팀)과 열린 것(PRODUCTION 팀 모드).

    승인 라우트는 열린 quest 를 고르므로 SALES 사용자는 403 이다. 예측이 완료 quest 를
    골랐다면 True(= 버튼이 보이고 누르면 403)가 된다.
    """
    user = _user("ok_k")
    done = _confirm_quest(status="COMPLETED", required=("SALES",), created="2026-09-10T00:00:00",
                          completed="2026-09-11T00:00:00")
    open_q = _confirm_quest(mode="team", required=("PRODUCTION",), created="2026-09-20T00:00:00")
    oid = _order(stage="CONFIRM", drawing_status="CONFIRMED", quests=[done, open_q])
    order = db_session.get(Order, oid)
    assert can_approve_after_confirm(user, order, order.structured_data) is False
    _login(client, user)
    assert _approve(client, oid).status_code == 403
    # 대조군: 열린 quest 가 SALES 승인이면 예측도 True, 라우트도 200.
    open_sales = _confirm_quest(mode="assignee", required=("SALES",), created="2026-09-20T00:00:00")
    oid2 = _order(stage="CONFIRM", drawing_status="CONFIRMED", quests=[done, open_sales])
    order2 = db_session.get(Order, oid2)
    assert can_approve_after_confirm(user, order2, order2.structured_data) is True
    assert _approve(client, oid2, key="k-2").status_code == 200
