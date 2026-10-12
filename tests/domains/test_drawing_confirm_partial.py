"""도면 확정 때 일부 품목 취소 + 최종 생산 도면 고르기 (DRAWING-PARTIAL-CONFIRM).

설계: docs/specs/2026-10-12-drawing-confirm-partial-cancel_SPEC.md §3·§4·§7.
"""
from __future__ import annotations

import copy
from datetime import date

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.orders.drawing_confirm_partial import (
    PartialConfirmError,
    active_items,
    apply_partial_confirm,
    plan_partial_confirm,
    preserve_item_cancel_state,
)
from models import Order, OrderEvent, User

SALES = "영업부분"
UID_A = "aaaaaaaa-0000-4000-8000-000000000001"
UID_B = "bbbbbbbb-0000-4000-8000-000000000002"


def _sd_base(order_id=1):
    k1 = f"orders/{order_id}/drawing_wizard/exports/1.png"
    k2 = f"orders/{order_id}/drawing_wizard/exports/2.png"
    return {
        "items": [
            {"uid": UID_A, "product_name": "몰딩 여닫이장"},
            {"uid": UID_B, "product_name": "보테가 슬라이딩장"},
        ],
        "drawing_current_files": [
            {"key": k1, "filename": "1.png", "item_uids": [UID_A]},
            {"key": k2, "filename": "2.png", "item_uids": [UID_B]},
        ],
    }, k1, k2


# ── 서비스 ────────────────────────────────────────────────────────────────

def test_no_inputs_returns_none_for_legacy_confirm():
    sd, _, _ = _sd_base()
    assert plan_partial_confirm(sd, None, None) is None
    assert plan_partial_confirm(sd, None, []) is None


def test_cancel_item_auto_excludes_its_drawing():
    sd, k1, k2 = _sd_base()
    before = copy.deepcopy(sd)
    plan = plan_partial_confirm(sd, None, [{"uid": UID_B, "reason": "customer_change"}])
    assert sd == before  # 검증은 아무것도 안 바꾼다
    assert plan.final_keys == [k1]
    assert plan.excluded == [{"key": k2, "reason": "item_cancelled", "item_uids": [UID_B]}]

    summary = apply_partial_confirm(sd, plan, actor_user_id=7, at_iso="2026-10-12T15:40:00")
    assert [f["key"] for f in sd["drawing_current_files"]] == [k1]
    assert sd["drawing_excluded_files"][0]["key"] == k2
    assert sd["drawing_excluded_files"][0]["excluded_reason"] == "item_cancelled"
    assert sd["items"][1]["cancel"]["reason"] == "customer_change"
    assert sd["items"][1]["cancel"]["by_user_id"] == 7
    assert "cancel" not in sd["items"][0]
    assert sd["flags"]["estimate_needs_update"] is True
    assert summary["cancelled_item_uids"] == [UID_B]
    assert [it["uid"] for it in active_items(sd)] == [UID_A]


def test_select_final_drawings_without_cancel():
    sd, k1, k2 = _sd_base()
    plan = plan_partial_confirm(sd, [k2], None)
    assert plan.final_keys == [k2]
    assert plan.excluded[0]["reason"] == "not_selected"
    summary = apply_partial_confirm(sd, plan, actor_user_id=1, at_iso="t")
    assert summary["estimate_needs_update"] is False
    assert "flags" not in sd


@pytest.mark.parametrize("final, cancels, code", [
    (None, [{"uid": UID_A, "reason": "customer_change"}, {"uid": UID_B, "reason": "customer_change"}],
     "NO_ITEMS_LEFT"),
    ([], None, "NO_FINAL_DRAWING"),
    (["orders/9/other.png"], None, "UNKNOWN_DRAWING"),
    (None, [{"uid": "x" * 36, "reason": "customer_change"}], "UNKNOWN_ITEM"),
    (None, [{"uid": UID_B, "reason": "budget"}], "INVALID_CANCEL_REASON"),
    (None, [{"uid": UID_B, "reason": "other"}], "CANCEL_NOTE_REQUIRED"),
    ("K2_ONLY", [{"uid": UID_B, "reason": "customer_change"}], "CANCELLED_ITEM_DRAWING_SELECTED"),
])
def test_contract_violations(final, cancels, code):
    sd, k1, k2 = _sd_base()
    if final == "K2_ONLY":
        final = [k1, k2]
    with pytest.raises(PartialConfirmError) as exc:
        plan_partial_confirm(sd, final, cancels)
    assert exc.value.code == code


def test_other_reason_keeps_note():
    sd, _, _ = _sd_base()
    plan = plan_partial_confirm(sd, None, [{"uid": UID_B, "reason": "other", "note": "색상 고민"}])
    apply_partial_confirm(sd, plan, actor_user_id=1, at_iso="t")
    assert sd["items"][1]["cancel"]["note"] == "색상 고민"


def test_unlinked_drawing_stays_when_item_cancelled():
    """품목 연결이 없는 도면(공통/모름)은 품목 취소로 자동 제외되지 않는다."""
    sd, k1, k2 = _sd_base()
    for f in sd["drawing_current_files"]:
        f.pop("item_uids")
    plan = plan_partial_confirm(sd, None, [{"uid": UID_B, "reason": "customer_change"}])
    assert plan.final_keys == [k1, k2]


def test_form_save_preserve_restores_cancel_by_uid_and_flag():
    old, _, _ = _sd_base()
    old["items"][1]["cancel"] = {"reason": "customer_change", "source": "drawing_confirm"}
    old["flags"] = {"estimate_needs_update": True}
    # 폼은 순서를 바꿔 보내고, cancel 을 모르며, 위조 cancel 을 다른 품목에 붙여 보낸다
    new = {"items": [{"uid": UID_B, "product_name": "B"},
                     {"uid": UID_A, "product_name": "A", "cancel": {"reason": "other"}}],
           "flags": {"urgent": True}}
    assert preserve_item_cancel_state(old, new) == 1
    assert new["items"][0]["cancel"]["reason"] == "customer_change"
    assert "cancel" not in new["items"][1]
    assert new["flags"] == {"urgent": True, "estimate_needs_update": True}


# ── API ───────────────────────────────────────────────────────────────────

def _user(username):
    u = User(username=username, password=generate_password_hash("pw"), role="MANAGER", team="SALES",
             name=SALES, is_active=True)
    db_session.add(u)
    db_session.commit()
    return u


def _login(client, user):
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = user.id, user.username, user.role


def _order():
    order = Order(received_date=date.today().strftime("%Y-%m-%d"), customer_name="부분고객",
                  phone="010-8", address="부산", product="붙박이장", status="DRAWING",
                  manager_name=SALES, is_erp_order=True, erp_stage_code="DRAWING", structured_data={})
    db_session.add(order)
    db_session.commit()
    sd, k1, k2 = _sd_base(order.id)
    sd.update({
        "parties": {"customer": {"name": "부분고객"}, "manager": {"name": SALES}},
        "workflow": {"stage": "DRAWING"},
        "drawing_status": "TRANSFERRED",
        "drawing_transfer_history": [{"action": "TRANSFER", "at": "2026-10-12 01:00:00",
                                      "files": [{"key": k1}, {"key": k2}], "previous_current_files": []}],
    })
    order.structured_data = sd
    db_session.commit()
    return order.id, k1, k2


def _sd(oid):
    db_session.expire_all()
    return dict(db_session.get(Order, oid).structured_data or {})


def test_api_partial_confirm_cancels_item_and_excludes_drawing(client):
    _login(client, _user("part_a"))
    oid, k1, k2 = _order()
    res = client.post(f"/api/orders/{oid}/confirm-drawing-receipt", json={
        "customer_ok": True, "cancel_items": [{"uid": UID_B, "reason": "customer_change"}]})
    assert res.status_code == 200, res.get_json()
    sd = _sd(oid)
    assert sd["drawing_status"] == "CONFIRMED"
    assert [f["key"] for f in sd["drawing_current_files"]] == [k1]
    assert [f["key"] for f in sd["drawing_excluded_files"]] == [k2]
    assert sd["items"][1]["cancel"]["reason"] == "customer_change"
    receipt = [h for h in sd["drawing_transfer_history"] if h["action"] == "CONFIRM_RECEIPT"][-1]
    assert receipt["cancelled_item_uids"] == [UID_B]
    assert receipt["files_count"] == 1
    ev = db_session.query(OrderEvent).filter_by(order_id=oid, event_type="ITEM_CANCELLED_AT_CONFIRM").one()
    assert ev.payload["cancels"][0]["uid"] == UID_B


def test_api_rejects_and_changes_nothing(client):
    _login(client, _user("part_b"))
    oid, _, _ = _order()
    before = _sd(oid)
    res = client.post(f"/api/orders/{oid}/confirm-drawing-receipt", json={
        "cancel_items": [{"uid": UID_A, "reason": "customer_change"},
                         {"uid": UID_B, "reason": "customer_change"}]})
    assert res.status_code == 400
    assert res.get_json()["code"] == "NO_ITEMS_LEFT"
    assert _sd(oid) == before


def test_api_without_new_inputs_keeps_all_drawings(client):
    _login(client, _user("part_c"))
    oid, k1, k2 = _order()
    assert client.post(f"/api/orders/{oid}/confirm-drawing-receipt", json={}).status_code == 200
    sd = _sd(oid)
    assert [f["key"] for f in sd["drawing_current_files"]] == [k1, k2]
    assert "drawing_excluded_files" not in sd
    assert all("cancel" not in it for it in sd["items"])


def test_api_confirm_keeps_item_links_on_final_files(client):
    _login(client, _user("part_d"))
    oid, _, _ = _order()
    assert client.post(f"/api/orders/{oid}/confirm-drawing-receipt", json={}).status_code == 200
    assert [f.get("item_uids") for f in _sd(oid)["drawing_current_files"]] == [[UID_A], [UID_B]]


# ── 화면 ──────────────────────────────────────────────────────────────────

def test_ok_scope_view_shows_only_when_there_is_a_choice():
    from foms.services.orders.drawing_confirm_partial import build_ok_scope
    sd, k1, _ = _sd_base()
    view = build_ok_scope(sd)
    assert view["show"] is True
    assert [d["item_names"] for d in view["drawings"]] == [["몰딩 여닫이장"], ["보테가 슬라이딩장"]]
    assert [r["value"] for r in view["reasons"]] == ["customer_change", "other"]
    one = {"items": [{"product_name": "단품"}], "drawing_current_files": [{"key": k1}]}
    single = build_ok_scope(one)
    assert single["show"] is False
    assert single["items"][0]["uid"] == "idx:0"  # uid 없는 옛 품목은 위치 참조


def test_ok_scope_js_is_valid_and_follows_conventions():
    import re
    import shutil
    import subprocess
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / "static/js/foms/drawing-ok-scope.js"
    node = shutil.which("node")
    assert node
    proc = subprocess.run([node, "--check", str(path)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    text = path.read_text(encoding="utf-8")
    assert "innerHTML" not in text and 'style="' not in text and "jQuery" not in text
    assert re.search(r"if \(window\.__FOMS_[A-Z_]+_BOUND\) return;", text)
    assert len(text.splitlines()) <= 300


def test_ok_modal_renders_scope_box_with_json(client, monkeypatch):
    import json as _json
    from tests.support.drawing_tab_send_pc_helpers import _bar, _inject, _order as _pc_order, _page, make_people
    people = make_people()
    oid = _pc_order(people["drafter"]["id"], files=2)
    _inject(monkeypatch, {"bar": _bar("ok"), "can_approve_after_confirm": True, "round_text": "1차"})
    modal = _page(client, people["sales"], oid).select_one("#dwCustomerOkModal")
    assert "modal-lg" in modal.select_one(".modal-dialog")["class"]
    scope = modal.select_one("[data-ok-scope]")
    data = _json.loads(scope["data-ok-scope"])
    assert data["show"] is True and [d["no"] for d in data["drawings"]] == [1, 2]
    assert scope.select_one("[data-ok-items]") is not None and scope.select_one("[data-ok-sum]") is not None
    assert "style" not in str(scope)


def test_ok_modal_without_choice_keeps_old_shape(client, monkeypatch):
    from tests.support.drawing_tab_send_pc_helpers import _bar, _inject, _order as _pc_order, _page, make_people
    people = make_people()
    oid = _pc_order(people["drafter"]["id"], files=1)
    _inject(monkeypatch, {"bar": _bar("ok"), "round_text": "1차"})
    modal = _page(client, people["sales"], oid).select_one("#dwCustomerOkModal")
    assert modal.select_one("[data-ok-scope]") is None
    assert "modal-lg" not in modal.select_one(".modal-dialog")["class"]


# ── 3단계: 확정 뒤 화면 ───────────────────────────────────────────────────

def test_confirm_result_view_lists_cancelled_excluded_and_estimate():
    from foms.services.orders.drawing_confirm_partial import build_confirm_result_view, cancel_label
    sd, k1, k2 = _sd_base()
    plan = plan_partial_confirm(sd, None, [{"uid": UID_B, "reason": "other", "note": "색상"}])
    apply_partial_confirm(sd, plan, actor_user_id=1, at_iso="t")
    view = build_confirm_result_view(sd)
    assert view["show"] is True and view["estimate_needs_update"] is True
    assert view["cancelled"] == [{"name": "보테가 슬라이딩장", "label": "취소 · 기타(색상)"}]
    assert view["excluded"][0]["reason"] == "제품 취소"
    assert cancel_label(sd["items"][0]) == ""
    assert build_confirm_result_view(_sd_base()[0])["show"] is False


def test_workbench_renders_confirm_result(client, monkeypatch):
    from tests.support.drawing_tab_send_pc_helpers import _bar, _inject, _order as _pc_order, _page, make_people
    people = make_people()
    oid = _pc_order(people["drafter"]["id"], status="CONFIRMED")
    order = db_session.get(Order, oid)
    sd = dict(order.structured_data)
    sd["items"] = [{"uid": UID_A, "product_name": "여닫이장"},
                   {"uid": UID_B, "product_name": "슬라이딩장", "cancel": {"reason": "customer_change"}}]
    sd["drawing_excluded_files"] = [{"key": f"orders/{oid}/x.png", "filename": "슬라이딩.png",
                                     "excluded_reason": "item_cancelled"}]
    sd["flags"] = {"estimate_needs_update": True}
    order.structured_data = sd
    db_session.commit()
    _inject(monkeypatch, {"bar": _bar("send"), "round_text": "1차"})
    soup = _page(client, people["sales"], oid)
    box = soup.select_one("[data-confirm-result]")
    assert box is not None
    text = box.get_text(" ", strip=True)
    assert "슬라이딩장" in text and "취소 · 고객 변심" in text
    assert "제외된 도면 1장 보기" in text and box.select_one("[data-estimate-needs-update]") is not None
    assert "style=" not in str(box)


# ── 5단계: 마법사 시트 → 품목 연결 ────────────────────────────────────────

def _wizard_sd():
    sd, k1, k2 = _sd_base()
    for f, sid in zip(sd["drawing_current_files"], ("s1", "s2")):
        f.pop("item_uids")
        f["sheet_id"] = sid
    sd["drawing_wizard"] = {"sheets": [{"id": "s1", "product_index": 0}, {"id": "s2", "product_index": 1}]}
    return sd, k1, k2


def test_wizard_sheet_links_drawing_to_item_and_auto_excludes():
    from foms.services.orders.drawing_confirm_partial import build_ok_scope, file_item_uids
    sd, k1, k2 = _wizard_sd()
    assert file_item_uids(sd, sd["drawing_current_files"][1]) == [UID_B]
    plan = plan_partial_confirm(sd, None, [{"uid": UID_B, "reason": "customer_change"}])
    assert plan.final_keys == [k1] and plan.excluded[0]["reason"] == "item_cancelled"
    assert build_ok_scope(sd)["drawings"][1]["item_names"] == ["보테가 슬라이딩장"]


@pytest.mark.parametrize("sheets", [
    [{"id": "s2", "product_index": 9}],          # 범위 밖
    [{"id": "s2", "product_index": None}],       # 공통 시트
    [{"id": "s2", "product_index": True}],       # 형식 이상
    [],                                          # 시트 없음
])
def test_wizard_link_unknown_means_no_auto_exclude(sheets):
    from foms.services.orders.drawing_confirm_partial import file_item_uids
    sd, k1, k2 = _wizard_sd()
    sd["drawing_wizard"]["sheets"] = sheets
    assert file_item_uids(sd, sd["drawing_current_files"][1]) == []
    plan = plan_partial_confirm(sd, None, [{"uid": UID_B, "reason": "customer_change"}])
    assert plan.final_keys == [k1, k2]


# ── 6단계: 확정 뒤 품목 취소 ──────────────────────────────────────────────

def _confirmed_order():
    oid, k1, k2 = _order()
    order = db_session.get(Order, oid)
    sd = dict(order.structured_data)
    sd["drawing_status"] = "CONFIRMED"
    order.structured_data = sd
    db_session.commit()
    return oid, k1, k2


def test_after_confirm_cancel_marks_item_and_moves_its_drawing(client):
    _login(client, _user("after_a"))
    oid, k1, k2 = _confirmed_order()
    res = client.post(f"/api/orders/{oid}/items/{UID_B}/cancel", json={"reason": "customer_change"})
    assert res.status_code == 200, res.get_json()
    sd = _sd(oid)
    assert sd["items"][1]["cancel"]["source"] == "after_confirm"
    assert [f["key"] for f in sd["drawing_current_files"]] == [k1]
    assert sd["drawing_excluded_files"][0]["excluded_reason"] == "item_cancelled_after_confirm"
    assert sd["flags"]["estimate_needs_update"] is True
    assert db_session.query(OrderEvent).filter_by(order_id=oid, event_type="ITEM_CANCELLED_AFTER_CONFIRM").count() == 1


@pytest.mark.parametrize("prep, uid, body, code", [
    ("transferred", UID_B, {"reason": "customer_change"}, "NOT_CONFIRMED"),
    ("confirmed", "z" * 36, {"reason": "customer_change"}, "UNKNOWN_ITEM"),
    ("confirmed", UID_B, {"reason": "other"}, "CANCEL_NOTE_REQUIRED"),
    ("last_one", UID_B, {"reason": "customer_change"}, "NO_ITEMS_LEFT"),
])
def test_after_confirm_cancel_rejects_without_change(client, prep, uid, body, code):
    _login(client, _user(f"after_{code.lower()}"))
    oid, _, _ = _order() if prep == "transferred" else _confirmed_order()
    if prep == "last_one":
        order = db_session.get(Order, oid)
        sd = dict(order.structured_data)
        sd["items"] = [dict(sd["items"][0], cancel={"reason": "customer_change"}), sd["items"][1]]
        order.structured_data = sd
        db_session.commit()
    before = _sd(oid)
    res = client.post(f"/api/orders/{oid}/items/{uid}/cancel", json=body)
    assert res.status_code == 400 and res.get_json()["code"] == code
    assert _sd(oid) == before


def _confirmed_page(client, monkeypatch, items):
    from tests.support.drawing_tab_send_pc_helpers import _bar, _inject, _order as _pc_order, _page, make_people
    people = make_people()
    oid = _pc_order(people["drafter"]["id"], status="CONFIRMED")
    order = db_session.get(Order, oid)
    sd = dict(order.structured_data)
    sd["items"] = items
    order.structured_data = sd
    db_session.commit()
    _inject(monkeypatch, {"bar": _bar("send"), "round_text": "1차"})
    return _page(client, people["sales"], oid)


def test_after_confirm_cancel_button_and_modal_render(client, monkeypatch):
    soup = _confirmed_page(client, monkeypatch, [{"uid": UID_A, "product_name": "여닫이장"},
                                                 {"uid": UID_B, "product_name": "슬라이딩장"}])
    btns = soup.select("[data-item-cancel-uid]")
    assert [b["data-item-cancel-name"] for b in btns] == ["여닫이장", "슬라이딩장"]
    modal = soup.select_one("#dwItemCancelModal")
    assert modal is not None and modal["data-mutation-version"]
    assert modal.select_one("#dw-item-cancel-note")["maxlength"] == "200"


def test_after_confirm_cancel_hidden_for_last_item(client, monkeypatch):
    soup = _confirmed_page(client, monkeypatch, [{"uid": UID_A, "product_name": "여닫이장"}])
    assert soup.select("[data-item-cancel-uid]") == [] and soup.select_one("#dwItemCancelModal") is None



def test_legacy_items_without_uid_cancel_by_index_and_get_uid(client):
    """마법사로 만든 주문처럼 uid 가 없는 품목도 확정 창에서 취소된다 — 적용 순간 uid 발급."""
    _login(client, _user("legacy_a"))
    oid, k1, k2 = _order()
    order = db_session.get(Order, oid)
    sd = dict(order.structured_data)
    sd["items"] = [{"product_name": "여닫이장"}, {"product_name": "슬라이딩장"}]
    sd["drawing_current_files"] = [{"key": k1, "filename": "1.png"}, {"key": k2, "filename": "2.png"}]
    order.structured_data = sd
    db_session.commit()
    res = client.post(f"/api/orders/{oid}/confirm-drawing-receipt", json={
        "final_drawing_keys": [k1], "cancel_items": [{"uid": "idx:1", "reason": "customer_change"}]})
    assert res.status_code == 200, res.get_json()
    after = _sd(oid)
    assert "cancel" not in after["items"][0] and after["items"][1]["cancel"]["reason"] == "customer_change"
    new_uid = after["items"][1]["uid"]
    assert len(new_uid) == 36
    receipt = [h for h in after["drawing_transfer_history"] if h["action"] == "CONFIRM_RECEIPT"][-1]
    assert receipt["cancelled_item_uids"] == [new_uid]
