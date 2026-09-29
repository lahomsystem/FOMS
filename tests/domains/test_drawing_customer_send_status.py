"""영업 → 고객 상태 읽기 모델(설계서 2026-09-29 §4.4 · §4.5). 버튼 목록은 ``test_drawing_customer_send_bar.py``.

발송은 실제 공유 라우트(발급·알림톡·회사 문자·회수)로 만들고(발송 이벤트 표지가 라우트가
박은 그대로다), 전달 취소는 라우트가 하는 일(최신 TRANSFER 를 이력에서 빼기)을 sd 에 그대로
한다. 화면값은 도면 작업실 상세 라우트의 ctx 에서 읽는다.
"""
from __future__ import annotations

import copy
import datetime
from contextlib import contextmanager

import pytest
from flask import template_rendered
from sqlalchemy import event as sa_event
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services import kakao_alimtalk as ka
from foms.services.orders.drawing_customer_send_view import (
    build_customer_send_view,
    can_approve_after_confirm,
)
from models import Order, OrderEvent, OrderShareToken, User

SALES = "영업상태"
_ENV_KEYS = ('SOLAPI_PF_ID_LAHOM', 'SOLAPI_PF_ID_HAUD',
             'SOLAPI_TEMPLATE_SHARE_ID_LAHOM', 'SOLAPI_TEMPLATE_SHARE_ID_HAUD',
             'SOLAPI_TEMPLATE_SHARE_BOTH_ID_LAHOM', 'SOLAPI_TEMPLATE_SHARE_BOTH_ID_HAUD',
             'SOLAPI_SENDER_PHONE_LAHOM', 'SOLAPI_SENDER_PHONE_HAUD',
             'SOLAPI_SENDER_FALLBACK_LAHOM', 'SOLAPI_SENDER_FALLBACK_HAUD',
             'SOLAPI_SENDER_PHONE')
R1_AT = "2026-09-20 01:00:00"
R2_AT = "2026-09-22 01:00:00"


def _user(username, *, role="MANAGER", team="SALES", name=SALES):
    u = User(username=username, password=generate_password_hash("pw"), role=role, team=team,
             name=name, is_active=True)
    db_session.add(u)
    db_session.commit()
    return u


def _login(client, user):
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = user.id, user.username, user.role


def _transfer(at, key):
    return {"action": "TRANSFER", "at": at, "transferred_at": at, "files": [{"key": key}],
            "previous_current_files": []}


def _order(*, history=None, drawing_status="TRANSFERRED", stage="DRAWING", files=1, assignees=None):
    order = Order(received_date="2026-09-19", customer_name="상태고객", phone="010-2473-6730",
                  address="서울", product="붙박이장", status=stage, manager_name=SALES,
                  is_erp_order=True, erp_stage_code=stage, structured_data={})
    db_session.add(order)
    db_session.commit()
    keys = [f"orders/{order.id}/drawing_wizard/exports/v{i + 1}.png" for i in range(files)]
    sd = {
        "parties": {"customer": {"name": "상태고객", "phone": "010-2473-6730"}, "manager": {"name": SALES}},
        "items": [{"product_name": "붙박이장", "quantity": 1, "price": 1000}],
        "workflow": {"stage": stage},
        "drawing_status": drawing_status,
        "drawing_current_files": [{"key": k, "filename": k.rsplit("/", 1)[-1]} for k in keys],
        "drawing_transfer_history": history if history is not None else [_transfer(R1_AT, keys[0] if keys else "x")],
    }
    if assignees:
        sd["assignments"] = {"drawing_assignee_user_ids": list(assignees)}
    order.structured_data = sd
    db_session.commit()
    return order.id


def _mutate_sd(oid, fn):
    db_session.expire_all()
    order = db_session.get(Order, oid)
    sd = copy.deepcopy(order.structured_data)
    fn(sd)
    order.structured_data = sd
    db_session.commit()


def _pop_last_transfer(sd):
    hist = sd["drawing_transfer_history"]
    idx = max(i for i, h in enumerate(hist) if h.get("action") == "TRANSFER")
    hist.pop(idx)


@pytest.fixture
def ata(monkeypatch):
    state = {"calls": [], "raise": None}

    def _fake(**kwargs):
        state["calls"].append(kwargs)
        if state["raise"] is not None:
            raise state["raise"]
        return "ATA-1"

    monkeypatch.setattr(ka, "_solapi_send", _fake)
    monkeypatch.setattr(ka, "_solapi_send_text", lambda **k: "SMS-1")
    for name in _ENV_KEYS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SOLAPI_PF_ID_HAUD", "PF-HAUD")
    monkeypatch.setenv("SOLAPI_TEMPLATE_SHARE_ID_HAUD", "TPL-HAUD")
    monkeypatch.setenv("SOLAPI_SENDER_PHONE_HAUD", "15660703")
    return state


def _create(client, oid, kind="drawing"):
    res = client.post(f"/api/share/create/{oid}", json={"kind": kind})
    assert res.status_code == 200, res.get_json()
    return res.get_json()["data"]


def _send(client, oid, *, kind="drawing", channel="alimtalk", body=None):
    data = _create(client, oid, kind)
    path = "send-alimtalk" if channel == "alimtalk" else "send-sms"
    res = client.post(f"/api/share/{path}/{data['share_id']}",
                      json={"token": data["token"], "source_screen": "drawing_tab", **(body or {})})
    return data, res


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


def _ctx(app, client, oid):
    with _captured(app) as contexts:
        res = client.get(f"/erp/drawing-workbench/{oid}")
    assert res.status_code == 200
    return next(c for c in contexts if "customer_send" in c)


def _cs(app, client, oid):
    return _ctx(app, client, oid)["customer_send"]


def _events(oid):
    db_session.expire_all()
    return (db_session.query(OrderEvent)
            .filter(OrderEvent.order_id == oid, OrderEvent.event_type.in_(("SHARE_ALIMTALK", "SHARE_SMS")))
            .order_by(OrderEvent.id).all())


# ── 발송 없음 · 성공 ────────────────────────────────────────────────────────
def test_nothing_sent(app, client):
    _login(client, _user("st_a"))
    oid = _order()
    cs = _cs(app, client, oid)
    assert cs["sent_this_round"] is False
    assert cs["status_line"] == "영업 → 고객 · 1차 아직 안 보냄"
    assert cs["link_only_text"] == "" and cs["failed_text"] == "" and cs["sent_text"] == ""
    assert cs["cancel_warning_text_pc"] == "" and cs["cancel_warning_text_mobile"] == ""
    assert cs["has_phone"] is True and cs["phone_masked"] == "010****6730"
    assert cs["can_send"] is True
    assert cs["arrival_label"] == "1차 도착"
    assert [s["state"] for s in cs["steps"]][:2] == ["done", "now"]


def test_alimtalk_success_this_round(app, client, ata):
    _login(client, _user("st_b"))
    oid = _order()
    _, res = _send(client, oid)
    assert res.status_code == 200 and res.get_json()["data"]["sent"] is True
    cs = _cs(app, client, oid)
    assert cs["sent_this_round"] is True
    assert "알림톡으로 보냈" in cs["sent_text"]
    assert cs["status_line"].startswith("영업 → 고객 · 1차 보냄 ")
    assert "알림톡" in cs["status_line"]
    assert cs["link_only_text"] == ""  # 발송에 쓰인 링크는 '링크만 만듦' 이 아니다
    assert cs["cancel_warning_text_pc"] and cs["cancel_warning_text_mobile"]
    assert "긴급 호출" not in cs["cancel_warning_text_pc"]
    assert "긴급 호출" in cs["cancel_warning_text_mobile"]
    assert "1차" in cs["cancel_warning_text_pc"]
    assert [s["state"] for s in cs["steps"]][:3] == ["done", "done", "now"]


def test_company_sms_success_this_round(app, client, ata):
    _login(client, _user("st_b2"))
    oid = _order()
    _, res = _send(client, oid, channel="sms")
    assert res.status_code == 200, res.get_json()
    cs = _cs(app, client, oid)
    assert cs["sent_this_round"] is True and "회사 문자" in cs["status_line"]


# ── 회차 경계: 보냄 → 전달 취소 ─────────────────────────────────────────────
def _two_round_history(oid):
    k = f"orders/{oid}/drawing_wizard/exports/v1.png"
    return [_transfer(R1_AT, k), {"action": "REQUEST_REVISION", "at": "2026-09-21 01:00:00"},
            _transfer(R2_AT, k)]


def test_sent_then_cancel_transfer_is_not_sent_for_previous_round(app, client, ata):
    """2차에 보냄 → 2차 전달 취소 → 1차는 보낸 적 없음(표지 비교).

    음성 대조: 같은 주문에서 이벤트의 표지를 떼면 시각 비교로 떨어져 '보냄'이 된다 — 이
    테스트가 초록인 이유가 표지라는 것을 같은 모집단 안에서 보인다.
    """
    _login(client, _user("st_c"))
    oid = _order(history=[])
    _mutate_sd(oid, lambda sd: sd.update(drawing_transfer_history=_two_round_history(oid)))
    _send(client, oid)
    assert _cs(app, client, oid)["sent_this_round"] is True
    _mutate_sd(oid, _pop_last_transfer)
    cs = _cs(app, client, oid)
    assert cs["round"] == 1
    assert cs["sent_this_round"] is False
    assert cs["cancel_warning_text_pc"] == ""
    # 음성 대조 — 표지 떼기
    for ev in _events(oid):
        payload = dict(ev.payload)
        payload.pop("round_at", None)
        payload.pop("round", None)
        ev.payload = payload
    db_session.commit()
    assert _cs(app, client, oid)["sent_this_round"] is True


def test_previous_round_send_counts_again_after_cancel(app, client, ata):
    _login(client, _user("st_d"))
    oid = _order()  # 1차 전달만
    _send(client, oid)  # 1차 표지로 보냄
    k = f"orders/{oid}/drawing_wizard/exports/v1.png"
    _mutate_sd(oid, lambda sd: sd["drawing_transfer_history"].extend(
        [{"action": "REQUEST_REVISION", "at": "2026-09-21 01:00:00"}, _transfer(R2_AT, k)]))
    cs2 = _cs(app, client, oid)
    assert cs2["round"] == 2 and cs2["sent_this_round"] is False
    _mutate_sd(oid, _pop_last_transfer)
    assert _cs(app, client, oid)["sent_this_round"] is True


def test_legacy_untagged_event_uses_time_compare(app, client):
    _login(client, _user("st_e"))
    oid = _order()
    before = OrderEvent(order_id=oid, event_type="SHARE_ALIMTALK",
                        payload={"share_id": 999001, "kind": "drawing", "status": "sent"},
                        created_at=datetime.datetime(2026, 9, 19, 0, 0, 0))
    db_session.add(before)
    db_session.commit()
    assert _cs(app, client, oid)["sent_this_round"] is False  # 전달 전 발송
    after = OrderEvent(order_id=oid, event_type="SHARE_ALIMTALK",
                       payload={"share_id": 999002, "kind": "drawing", "status": "sent"},
                       created_at=datetime.datetime(2026, 9, 20, 2, 0, 0))
    db_session.add(after)
    db_session.commit()
    assert _cs(app, client, oid)["sent_this_round"] is True


# ── 실패 · network · 보내는 중 ──────────────────────────────────────────────
def test_vendor_failure_shows_failed_text(app, client, ata):
    _login(client, _user("st_f"))
    oid = _order()
    ata["raise"] = ValueError("invalid receiver phone")
    _, res = _send(client, oid)
    assert res.status_code == 200 and res.get_json()["data"]["sent"] is False
    cs = _cs(app, client, oid)
    assert cs["sent_this_round"] is False
    assert "알림톡 실패" in cs["failed_text"]
    assert "실패" in cs["status_line"]


def test_network_failure_is_unsure(app, client, ata):
    _login(client, _user("st_g"))
    oid = _order()
    ata["raise"] = TimeoutError("timed out")
    _send(client, oid)
    cs = _cs(app, client, oid)
    assert "결과 확인 안 됨" in cs["failed_text"]


def test_in_flight_event_is_unknown(app, client, ata):
    _login(client, _user("st_h"))
    oid = _order()
    _send(client, oid)
    ev = _events(oid)[-1]
    ev.payload = {**ev.payload, "status": "in_flight"}
    db_session.commit()
    cs = _cs(app, client, oid)
    assert cs["sent_this_round"] is False
    assert "결과 모름" in cs["failed_text"]


# ── 종류 · 통합 템플릿 짝 링크 ──────────────────────────────────────────────
def test_estimate_ignored_bundle_counts(app, client, ata):
    _login(client, _user("st_i"))
    oid = _order()
    _send(client, oid, kind="estimate")
    assert _cs(app, client, oid)["sent_this_round"] is False
    _send(client, oid, kind="bundle")
    assert _cs(app, client, oid)["sent_this_round"] is True


def test_both_template_pair_link_not_link_only_and_views_count(app, client, ata, monkeypatch):
    monkeypatch.setenv("SOLAPI_TEMPLATE_SHARE_BOTH_ID_HAUD", "TPL-BOTH")
    _login(client, _user("st_j"))
    oid = _order()
    _, res = _send(client, oid, kind="bundle")
    assert res.status_code == 200, res.get_json()
    ev = _events(oid)[-1]
    pair_id = ev.payload["drawing_share_id"]
    assert ev.payload.get("estimate_share_id")
    pair = db_session.get(OrderShareToken, pair_id)
    assert pair.created_by_user_id is None
    pair.view_count = 2
    pair.last_viewed_at = datetime.datetime.utcnow()
    db_session.commit()
    cs = _cs(app, client, oid)
    assert cs["link_only_text"] == ""
    assert cs["views"] == 2
    assert "링크 열림 2번" in cs["status_line"]
    assert cs["bundle_both_template"] is True


def test_legacy_bundle_event_pairs_drawing_link_within_ten_seconds(app, client):
    _login(client, _user("st_k"))
    oid = _order()
    t0 = datetime.datetime(2026, 9, 20, 3, 0, 0)
    bundle = OrderShareToken(order_id=oid, kind="bundle", token_hash="h-bundle-k", created_by_user_id=None,
                             expires_at=t0 + datetime.timedelta(days=30), created_at=t0)
    near = OrderShareToken(order_id=oid, kind="drawing", token_hash="h-near-k", created_by_user_id=None,
                           expires_at=t0 + datetime.timedelta(days=30), created_at=t0 + datetime.timedelta(seconds=5),
                           view_count=3, last_viewed_at=t0 + datetime.timedelta(hours=1))
    far = OrderShareToken(order_id=oid, kind="drawing", token_hash="h-far-k", created_by_user_id=None,
                          expires_at=t0 + datetime.timedelta(days=30), created_at=t0 + datetime.timedelta(seconds=60),
                          view_count=7)
    db_session.add_all([bundle, near, far])
    db_session.flush()
    db_session.add(OrderEvent(order_id=oid, event_type="SHARE_ALIMTALK",
                              payload={"share_id": bundle.id, "kind": "bundle", "status": "sent"},
                              created_at=t0))
    db_session.commit()
    cs = _cs(app, client, oid)
    assert cs["sent_this_round"] is True
    assert cs["views"] == 3  # 짝(±10초) 링크만 센다
    assert cs["link_only_text"] == ""


# ── 링크만 만듦 · 회수 ───────────────────────────────────────────────────────
def test_create_then_503_then_revoke_leaves_no_link_only(app, client, monkeypatch):
    for name in _ENV_KEYS:
        monkeypatch.delenv(name, raising=False)
    _login(client, _user("st_l"))
    oid = _order()
    data = _create(client, oid)
    res = client.post(f"/api/share/send-alimtalk/{data['share_id']}", json={"token": data["token"]})
    assert res.status_code == 503
    assert client.post(f"/api/share/revoke/{data['share_id']}").status_code == 200
    cs = _cs(app, client, oid)
    assert cs["link_only_text"] == ""
    assert cs["sent_this_round"] is False


def test_link_only_when_staff_created_link_without_send(app, client):
    _login(client, _user("st_m"))
    oid = _order()
    _create(client, oid)
    cs = _cs(app, client, oid)
    assert "링크를 만들었어요(직접 보낸 경우 보냈는지는 기록되지 않아요)" in cs["link_only_text"]
    assert cs["sent_this_round"] is False
    assert "링크만" in cs["status_line"]


def test_link_created_before_round_is_not_link_only(app, client):
    _login(client, _user("st_m2"))
    oid = _order()
    _create(client, oid)
    k = f"orders/{oid}/drawing_wizard/exports/v1.png"
    later = (datetime.datetime.utcnow() + datetime.timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    _mutate_sd(oid, lambda sd: sd["drawing_transfer_history"].extend(
        [{"action": "REQUEST_REVISION", "at": later}, _transfer(later, k)]))
    assert _cs(app, client, oid)["link_only_text"] == ""


# ── 이벤트 표지 ─────────────────────────────────────────────────────────────
def test_event_payload_tags(client, ata, monkeypatch):
    monkeypatch.setenv("SOLAPI_TEMPLATE_SHARE_BOTH_ID_HAUD", "TPL-BOTH")
    _login(client, _user("st_n"))
    oid = _order()
    _send(client, oid, kind="bundle")
    ev = _events(oid)[-1]
    assert ev.payload["round_at"] == R1_AT
    assert ev.payload["round"] == 1
    assert ev.payload["source_screen"] == "drawing_tab"
    assert ev.payload["drawing_share_id"] and ev.payload["estimate_share_id"]
    # 목록 밖 화면 값은 키를 넣지 않는다.
    data = _create(client, oid)
    client.post(f"/api/share/send-sms/{data['share_id']}", json={"token": data["token"], "source_screen": "x"})
    ev2 = _events(oid)[-1]
    assert ev2.event_type == "SHARE_SMS"
    assert "source_screen" not in ev2.payload
    assert ev2.payload["round_at"] == R1_AT


# ── 컨펌 권한 예측(팀별) ─────────────────────────────────────────────────────
@pytest.mark.parametrize("role,team,expected", [
    ("ADMIN", None, True), ("STAFF", "SALES", True), ("STAFF", "CS", True), ("STAFF", "DRAWING", False),
])
def test_approve_prediction_by_team(role, team, expected):
    user = _user(f"st_o_{role}_{team}", role=role, team=team)
    oid = _order()
    order = db_session.get(Order, oid)
    order.structured_data = {**order.structured_data, "quests": [{
        "stage": "CONFIRM", "status": "OPEN", "required_approvals": ["CS", "SALES"],
        "approval_mode": "assignee", "team_approvals": {}, "created_at": "2026-09-16T00:00:00",
    }]}
    db_session.commit()
    assert can_approve_after_confirm(user, order, order.structured_data) is expected


# ── 조회 수 ─────────────────────────────────────────────────────────────────
def test_read_model_uses_two_queries(app, client, ata):
    user = _user("st_p")
    uid = user.id
    _login(client, user)
    oid = _order()
    _send(client, oid)
    db_session.expire_all()
    order = db_session.get(Order, oid)
    user = db_session.get(User, uid)
    sd = copy.deepcopy(order.structured_data)
    statements = []

    def _count(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    engine = db_session.get_bind()
    sa_event.listen(engine, "before_cursor_execute", _count)
    try:
        with app.test_request_context():
            build_customer_send_view(
                db_session, order, sd, user, drawing_status="TRANSFERRED", sales_side=True,
                can_confirm_receipt=True, can_cancel_revision=True, is_admin=False,
                is_drawing_participant=False, drawing_mobile_buttons=0,
            )
    finally:
        sa_event.remove(engine, "before_cursor_execute", _count)
    assert len(statements) == 2, statements
