"""도면 탭 버튼 목록 ``customer_send.bar``(설계서 2026-09-29 §3.0 + 사용자 결정 Q5 ①③).

PC 결정 바와 모바일 하단 바가 같이 순회하는 서버 판정 목록. 상태별 키 순서, 도면팀 PC 긴급 호출
``urgent_call``, 요청 고치기 ``edit_revision``(반영 체크 전만), 모바일 넘침 ``slot`` 을 본다.
주문 시드·발송·화면값 읽기 도우미는 상태 읽기 모델 테스트와 같은 것을 쓴다.
"""
from __future__ import annotations

from foms.services.orders.drawing_customer_send import BAR_ITEM_FIELDS, BAR_KEYS
from foms.services.orders.drawing_customer_send_bar import build_customer_send_bar
from tests.domains.test_drawing_customer_send_status import (  # noqa: F401 — ata 는 fixture
    R1_AT,
    _cs,
    _login,
    _mutate_sd,
    _order,
    _send,
    _transfer,
    _user,
    ata,
)


# ── 버튼 목록(§3.0 + Q5) ─────────────────────────────────────────────────────
def _keys(cs):
    return [b["key"] for b in cs["bar"]]


def _assert_bar_shape(cs):
    for item in cs["bar"]:
        assert tuple(item) == BAR_ITEM_FIELDS, item
        assert item["key"] in BAR_KEYS
        assert item["slot"] in ("main", "more")
        assert item["label"]


def test_bar_transferred_unsent(app, client):
    _login(client, _user("bar_a"))
    oid = _order()
    cs = _cs(app, client, oid)
    assert _keys(cs) == ["rev_sales", "send", "ok_no_customer"]
    assert all(b["slot"] == "main" for b in cs["bar"])
    _assert_bar_shape(cs)


def test_bar_transferred_sent(app, client, ata):
    _login(client, _user("bar_b"))
    oid = _order()
    _send(client, oid)
    cs = _cs(app, client, oid)
    assert _keys(cs) == ["resend", "rev_customer", "ok"]
    _assert_bar_shape(cs)


def test_bar_no_files_no_send(app, client):
    _login(client, _user("bar_c"))
    oid = _order(files=0, history=[_transfer(R1_AT, "x")])
    cs = _cs(app, client, oid)
    assert "send" not in _keys(cs) and cs["can_send"] is False


def test_bar_returned_edit_then_checked(app, client):
    _login(client, _user("bar_d"))
    oid = _order(drawing_status="RETURNED")
    _mutate_sd(oid, lambda sd: sd["drawing_transfer_history"].append(
        {"action": "REQUEST_REVISION", "at": "2026-09-21 01:00:00", "by_user_id": 1, "note": "폭 줄여 주세요",
         "source": "customer", "received_via": "kakao", "files": []}))
    cs = _cs(app, client, oid)
    assert _keys(cs) == ["edit_revision", "cancel_revision"]
    assert cs["edit_revision"]["note"] == "폭 줄여 주세요"
    assert cs["edit_revision"]["source"] == "customer"
    assert cs["edit_revision"]["received_via"] == "kakao"
    assert "send" not in _keys(cs)

    def _check(sd):
        sd["drawing_transfer_history"][-1]["review_check"] = {"checked": True}
    _mutate_sd(oid, _check)
    cs2 = _cs(app, client, oid)
    assert _keys(cs2) == ["cancel_revision"]
    assert cs2["edit_revision"] == {}


def test_bar_confirmed_confirm_stage(app, client):
    _login(client, _user("bar_e"))
    oid = _order(drawing_status="CONFIRMED", stage="CONFIRM")
    _mutate_sd(oid, lambda sd: sd.update(quests=[{
        "stage": "CONFIRM", "status": "OPEN", "required_approvals": ["CS", "SALES"],
        "approval_mode": "assignee", "team_approvals": {}, "created_at": "2026-09-16T00:00:00"}]))
    assert _keys(_cs(app, client, oid)) == ["rev_post", "send", "approve_confirm"]


def test_bar_confirmed_other_stage(app, client):
    _login(client, _user("bar_f"))
    oid = _order(drawing_status="CONFIRMED", stage="PRODUCTION")
    assert _keys(_cs(app, client, oid)) == ["rev_post", "send", "production"]


def test_bar_drawing_team_gets_only_urgent_call(app, client):
    _login(client, _user("bar_g", role="STAFF", team="DRAWING", name="도면팀원"))
    oid = _order()
    cs = _cs(app, client, oid)
    assert _keys(cs) == ["urgent_call"]
    assert cs["status_line"] == "영업 → 고객 · 1차 아직 안 보냄"
    assert cs["turn_hint"] == ""


def test_bar_admin_drawing_assignee_overflows_to_more(app, client):
    admin = _user("bar_h", role="ADMIN", team=None, name="관리자")
    _login(client, admin)
    oid = _order(assignees=[admin.id])
    cs = _cs(app, client, oid)
    keys = _keys(cs)
    assert keys[:3] == ["rev_sales", "send", "ok_no_customer"] and keys[-1] == "urgent_call"
    slots = {b["key"]: b["slot"] for b in cs["bar"]}
    # 도면 쪽 버튼 둘(전달·전달 취소)이 바에 있어 영업 쪽은 주 버튼 하나만 바에 남는다.
    assert slots["send"] == "main"
    assert slots["rev_sales"] == "more" and slots["ok_no_customer"] == "more"


def test_bar_pure_function_primary_first_in_slots():
    bar = build_customer_send_bar(
        drawing_status="TRANSFERRED", sales_side=True, can_send=True, sent_this_round=True,
        can_confirm_receipt=True, can_cancel_revision=True, can_edit_revision=False,
        can_approve_after_confirm=False, stage_code="DRAWING", show_urgent_call=False,
        drawing_mobile_buttons=1,
    )
    assert [b["key"] for b in bar] == ["resend", "rev_customer", "ok"]
    slots = {b["key"]: b["slot"] for b in bar}
    assert slots["ok"] == "main" and slots["resend"] == "main" and slots["rev_customer"] == "more"
