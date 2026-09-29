"""도면 탭 고객 보내기 S1a — 회차 함수 하나 + 빈 화면값 뼈대(설계서 2026-09-29 §4.3 · §4.5).

회차 규칙(사용자 결정 Q2):
    round = 전달이 없으면 0, 있으면 1 + 마지막 TRANSFER 앞의 REQUEST_REVISION 수.
    수정요청 없이 더 올린 전달(APPEND·REPLACE)은 같은 회차의 "추가 전달"이다.
    수정요청 취소는 REQUEST_REVISION 을 이력에서 빼므로(REVISION_CANCELLED 로 보존) 자동으로 안 센다.
    전달 취소는 최신 TRANSFER 를 이력에서 빼기만 하므로 앞 전달의 round_at 으로 돌아간다.

빈 화면값:
    S2·S3 템플릿이 ``customer_send.*`` 를 읽는다. Jinja 기본 Undefined 는 없는 변수의 속성을
    읽는 순간 오류이므로, 상세 ctx 에 모든 키를 빈 값으로 채운 ``customer_send`` 가 늘 있어야 한다.

음성 대조:
    모듈이 없을 때 이 파일 전체가 ImportError(수집 실패)로 빨강인 것을 확인했다.
    회차 규칙의 모집단 안 대조군 — "전달 2번" 두 주문 중 수정요청이 사이에 있는 쪽만 2차다.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date

from flask import template_rendered
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.orders.drawing_customer_send import (
    BAR_ITEM_FIELDS,
    BAR_KEYS,
    CUSTOMER_SEND_KEYS,
    RoundInfo,
    drawing_round_info,
    empty_customer_send_view,
)
from models import Order, User


def _t(at: str, mode: str = "REPLACE") -> dict:
    return {"action": "TRANSFER", "transferred_at": at, "at": at, "transfer_mode": mode, "files": []}


def _r(at: str) -> dict:
    return {"action": "REQUEST_REVISION", "at": at, "note": "고쳐 주세요"}


def _sd(*history: dict) -> dict:
    return {"drawing_transfer_history": list(history)}


# ── 회차 함수 ────────────────────────────────────────────────────────────────
def test_no_transfer_is_round_zero():
    info = drawing_round_info(_sd())
    assert isinstance(info, RoundInfo)
    assert info.round == 0
    assert info.round_at == ""
    assert info.transfer_count == 0
    assert info.is_append is False
    assert info.revisions_before == 0


def test_none_and_broken_history_are_round_zero():
    assert drawing_round_info(None).round == 0
    assert drawing_round_info({}).round == 0
    assert drawing_round_info({"drawing_transfer_history": "x"}).round == 0
    assert drawing_round_info({"drawing_transfer_history": [None, 3, "a"]}).round == 0


def test_revision_before_any_transfer_does_not_make_round():
    info = drawing_round_info(_sd(_r("2026-09-01T01:00:00Z")))
    assert info.round == 0
    assert info.revisions_before == 0


def test_one_transfer_is_round_one():
    info = drawing_round_info(_sd(_t("2026-09-01T02:00:00Z")))
    assert info.round == 1
    assert info.round_at == "2026-09-01T02:00:00Z"
    assert info.transfer_count == 1
    assert info.is_append is False


def test_two_transfers_without_revision_stay_round_one_as_append():
    info = drawing_round_info(_sd(_t("2026-09-01T02:00:00Z"), _t("2026-09-01T03:00:00Z", "APPEND")))
    assert info.round == 1
    assert info.transfer_count == 2
    assert info.is_append is True
    assert info.round_at == "2026-09-01T03:00:00Z"


def test_transfer_revision_transfer_is_round_two():
    info = drawing_round_info(
        _sd(_t("2026-09-01T02:00:00Z"), _r("2026-09-01T02:30:00Z"), _t("2026-09-01T03:00:00Z"))
    )
    assert info.round == 2
    assert info.revisions_before == 1
    assert info.is_append is False
    assert info.round_at == "2026-09-01T03:00:00Z"


def test_append_after_revision_round_stays_and_is_append():
    info = drawing_round_info(_sd(
        _t("2026-09-01T02:00:00Z"), _r("2026-09-01T02:30:00Z"),
        _t("2026-09-01T03:00:00Z"), _t("2026-09-01T04:00:00Z", "APPEND"),
    ))
    assert info.round == 2
    assert info.transfer_count == 3
    assert info.is_append is True


def test_revision_after_last_transfer_does_not_count_yet():
    # 도면팀이 고치는 중(RETURNED) — 아직 새 전달이 없으니 회차는 그대로다.
    info = drawing_round_info(_sd(_t("2026-09-01T02:00:00Z"), _r("2026-09-01T02:30:00Z")))
    assert info.round == 1
    assert info.revisions_before == 0


def test_cancelled_revision_is_not_counted():
    # 수정요청 취소 = REQUEST_REVISION 을 빼고 끝에 REVISION_CANCELLED 로 통째 보존.
    cancelled = {"action": "REVISION_CANCELLED", "at": "2026-09-01T02:40:00Z",
                 "request": _r("2026-09-01T02:30:00Z")}
    info = drawing_round_info(_sd(_t("2026-09-01T02:00:00Z"), cancelled, _t("2026-09-01T03:00:00Z", "APPEND")))
    assert info.round == 1
    assert info.revisions_before == 0
    assert info.is_append is True


def test_transfer_cancel_returns_to_previous_round_at():
    # 전달 취소 = 최신 TRANSFER 를 이력에서 빼기만 한다(erp_orders_drawing.py history.pop).
    history = [_t("2026-09-01T02:00:00Z"), _r("2026-09-01T02:30:00Z"), _t("2026-09-01T03:00:00Z")]
    assert drawing_round_info(_sd(*history)).round == 2
    history.pop()
    info = drawing_round_info(_sd(*history))
    assert info.round == 1
    assert info.round_at == "2026-09-01T02:00:00Z"


def test_round_at_falls_back_to_at():
    info = drawing_round_info(_sd({"action": "TRANSFER", "at": "2026-09-02T00:00:00Z"}))
    assert info.round_at == "2026-09-02T00:00:00Z"


def test_control_same_transfer_count_different_round():
    # 모집단 안 대조군: 전달 수(2)가 같아도 수정요청이 사이에 있어야만 2차다.
    a = drawing_round_info(_sd(_t("2026-09-01T02:00:00Z"), _t("2026-09-01T03:00:00Z")))
    b = drawing_round_info(_sd(_t("2026-09-01T02:00:00Z"), _r("2026-09-01T02:10:00Z"), _t("2026-09-01T03:00:00Z")))
    assert a.transfer_count == b.transfer_count == 2
    assert (a.round, b.round) == (1, 2)


# ── 빈 화면값 ────────────────────────────────────────────────────────────────
def test_empty_view_has_every_contract_key():
    view = empty_customer_send_view()
    assert set(view) == set(CUSTOMER_SEND_KEYS)
    # 설계서 §4.5 약속 + Q5 추가 키가 빠지지 않았는지(이름이 바뀌면 S2·S3 템플릿이 조용히 비게 된다).
    for key in (
        "round", "round_text", "round_at", "is_append", "arrived_at_text", "arrival_label",
        "can_send", "has_phone", "phone_masked", "sent_this_round", "sent_text", "link_only_text",
        "failed_text", "views", "last_viewed_text", "status_line", "turn_hint", "steps", "prev_summary",
        "doc_label_drawing", "doc_label_bundle", "bundle_both_template", "can_customer_ok",
        "can_approve_after_confirm", "bar", "cancel_warning_text_pc", "cancel_warning_text_mobile",
        "can_change_phone", "can_save_phone", "edit_revision", "sent_earlier_text", "last_attempt_state",
    ):
        assert key in view, key


def test_empty_view_values_hide_new_buttons():
    view = empty_customer_send_view()
    assert view["bar"] == []
    assert view["steps"] == []
    assert view["edit_revision"] == {}
    assert view["round"] == 0 and view["round_text"] == "" and view["views"] == 0
    for key in ("can_send", "has_phone", "sent_this_round", "bundle_both_template",
                "can_customer_ok", "can_approve_after_confirm", "can_change_phone", "can_save_phone",
                "is_append"):
        assert view[key] is False, key
    for key in ("sent_text", "link_only_text", "failed_text", "status_line", "turn_hint",
                "cancel_warning_text_pc", "cancel_warning_text_mobile", "phone_masked",
                "sent_earlier_text", "last_attempt_state"):
        assert view[key] == "", key
    # 스위치 꺼짐 = 지금 고정 표 이름(share.py _SMS_KIND_LABEL).
    assert view["doc_label_drawing"] == "도면"
    assert view["doc_label_bundle"] == "도면·계약서"


def test_empty_view_is_fresh_each_call():
    a = empty_customer_send_view()
    a["bar"].append({"key": "send"})
    a["edit_revision"]["note"] = "x"
    b = empty_customer_send_view()
    assert b["bar"] == [] and b["edit_revision"] == {}


def test_bar_contract_names():
    assert BAR_KEYS == (
        "send", "resend", "rev_customer", "rev_sales", "ok", "ok_no_customer", "rev_post",
        "approve_confirm", "production", "cancel_revision", "edit_revision", "urgent_call",
    )
    assert BAR_ITEM_FIELDS == ("key", "label", "tone", "slot")


# ── 상세 ctx 배선 ────────────────────────────────────────────────────────────
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


def _seed_transferred_order() -> tuple[int, User]:
    u = User(username="s1a_sales", password=generate_password_hash("pw"), role="ADMIN", team=None,
             name="S1A관리자", is_active=True)
    db_session.add(u)
    o = Order(
        received_date=date.today().strftime("%Y-%m-%d"), customer_name="S1A고객", phone="010-2929-2929",
        address="Seoul", product="붙박이장", status="DRAWING", manager_name="영업S1A", is_erp_order=True,
        erp_stage_code="DRAWING",
        structured_data={
            "parties": {"customer": {"name": "S1A고객"}, "manager": {"name": "영업S1A"}},
            "workflow": {"stage": "DRAWING"}, "drawing_status": "TRANSFERRED",
            "drawing_current_files": [{"key": "orders/0/drawings/a.png", "filename": "a.png"}],
            "drawing_transfer_history": [_t("2026-09-01T02:00:00Z")],
        },
    )
    db_session.add(o)
    db_session.commit()
    return o.id, u


def test_detail_ctx_carries_empty_customer_send(app, client):
    oid, u = _seed_transferred_order()
    with client.session_transaction() as s:
        s["user_id"], s["username"], s["role"] = u.id, u.username, u.role
    with _captured(app) as contexts:
        res = client.get(f"/erp/drawing-workbench/{oid}")
    assert res.status_code == 200
    detail = [c for c in contexts if "customer_send" in c]
    assert detail, "상세 ctx 에 customer_send 가 없다"
    cs = detail[0]["customer_send"]
    assert set(cs) == set(CUSTOMER_SEND_KEYS)
    assert cs["round"] == 1
    assert cs["round_text"] == "1차"
    assert cs["round_at"] == "2026-09-01T02:00:00Z"
    # S1 이 채운 버튼 목록 — 관리자는 영업 쪽이면서 도면 쪽(긴급 호출)이다.
    assert [b["key"] for b in cs["bar"]] == ["rev_sales", "send", "ok_no_customer", "urgent_call"]
