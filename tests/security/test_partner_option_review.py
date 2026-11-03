"""협력사 옵션 3단계 — 도면팀 옵션 확인 · 협력사 도면 확인 때 확정(설계서 docs/specs/2026-11-03-partner-statement_SPEC.md §5.3 · §5.4).

도면 전달에 실린 ``partner_options`` 는 전달과 같은 트랜잭션에서 지금 값(CURRENT)만 바꾸고 원문(PARTNER)은 그대로 둔다.
협력사가 고른 것과 달라진 품목은 까닭이 없으면 전달 전체가 막힌다. 협력사 "이대로 만들어 주세요"는 "상담 후 정함" 품목을
고르게 하고(없으면 409), 지금 값을 확정본(CONFIRMED)으로 복사하며 감사 기록에 옵션 지문을 남긴다. 대조군: 옵션을 싣지 않은
전달은 지금 값을 건드리지 않는다 · 옵션 줄이 없는 주문(다른 회사)은 읽기 API 가 null 이다. 단가 · 이름은 가짜다.
"""
from __future__ import annotations

from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from foms.services.partners.item_options import diff_options
from models import Order, OrderItemOption, SecurityLog, User
from tests.security.partner_fixtures import _PAYLOAD, _client, _create, _to_confirm, _user, world  # noqa: F401
from tests.security.test_partner_item_options import PRICES, _item, priced  # noqa: F401 — 단가표 판 준비물 재사용


def _rows(oid, stage):
    db_session.expire_all()
    rows = db_session.query(OrderItemOption).filter_by(order_id=oid, stage=stage).order_by(OrderItemOption.id).all()
    return {r.item_uid: r for r in rows}


def _partner_order(app, w, items, drafter_id):
    resp = _create(app, w["partner_a"], {**_PAYLOAD, "items": items})
    assert resp.status_code == 200, resp.get_json()
    oid = resp.get_json()["data"]["order_id"]
    order = db_session.get(Order, oid)
    sd = dict(order.structured_data)
    sd["assignments"] = {**(sd.get("assignments") or {}), "drawing_assignee_user_ids": [drafter_id]}
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()
    return oid, [it["uid"] for it in sd["items"]]


def _transfer(client, oid, **extra):
    return client.post(f"/api/orders/{oid}/transfer-drawing",
                       json={"files": [{"key": f"orders/{oid}/drawing/final.pdf", "filename": "final.pdf"}], **extra})


def _drafter():
    return _user(role="STAFF", team="DRAWING", name="도면팀").id


def _as(app, user_id):
    return _client(app, db_session.get(User, user_id))


def test_staff_reads_options_and_partner_cannot(app, priced):
    drafter = _drafter()
    oid, uids = _partner_order(app, priced, [_item(lines=[{"key": "r4", "qty": 1, "memo": "우측"}])], drafter)
    data = _as(app, drafter).get(f"/api/orders/{oid}/partner-options").get_json()["data"]
    assert [(i["uid"], i["no"], i["title"], i["diff"]) for i in data["items"]] == [(uids[0], 1, "슬라이딩", [])]
    assert data["items"][0]["current"]["lines"][0] == {"key": "r4", "name": "슬라이딩 거울 도어", "qty": "1", "memo": "우측", "unit": "짝"}
    assert not any(price in repr(data) for price in PRICES)
    assert _client(app, db_session.get(User, priced["partner_a"])).get(f"/api/orders/{oid}/partner-options").status_code == 403
    other = _create(app, priced["partner_b"], {**_PAYLOAD, "items": [{"product_name": "붙박이장"}]}).get_json()["data"]["order_id"]
    assert _as(app, drafter).get(f"/api/orders/{other}/partner-options").get_json()["data"] is None  # 대조군


def test_transfer_needs_reason_for_changed_options_then_saves_current_only(app, priced):
    drafter = _drafter()
    oid, uids = _partner_order(app, priced, [_item(lines=[{"key": "r4", "qty": 1}]), _item("몰딩 여닫이", state="none")],
                               drafter)
    client = _as(app, drafter)
    changed = {uids[0]: {"lines": [{"key": "r4", "qty": 2}, {"key": "r5", "qty": 1, "memo": "왼쪽"}]},
               uids[1]: {"state": "none"}}
    refused = _transfer(client, oid, partner_options=changed)
    assert refused.status_code == 400 and "항목 1" in refused.get_json()["message"]
    db_session.expire_all()
    assert db_session.get(Order, oid).structured_data.get("drawing_status") != "TRANSFERRED"  # 전달 전체가 막힌다
    assert _rows(oid, "CURRENT")[uids[0]].lines[0]["qty"] == "1"
    changed[uids[0]]["reason"] = "가운데 통이 좁아 거울 도어 2짝 · EP 추가"
    ok = _transfer(client, oid, partner_options=changed)
    assert ok.status_code == 200, ok.get_json()
    current, partner = _rows(oid, "CURRENT")[uids[0]], _rows(oid, "PARTNER")[uids[0]]
    assert [(l["key"], l["qty"]) for l in current.lines] == [("r4", "2"), ("r5", "1")]
    assert [(c["name"], c["from"], c["to"], c["reason"]) for c in current.changes] == [
        ("슬라이딩 거울 도어", "1짝", "2짝", "가운데 통이 좁아 거울 도어 2짝 · EP 추가"),
        ("측면 마감판(EP)", None, "1개", "가운데 통이 좁아 거울 도어 2짝 · EP 추가")]
    assert [(l["key"], l["qty"]) for l in partner.lines] == [("r4", "1")]  # 원문은 그대로
    order = db_session.get(Order, oid)
    assert order.structured_data["drawing_status"] == "TRANSFERRED"
    assert order.structured_data["items"][0]["option_detail"] == "슬라이딩 거울 도어 2짝 · 측면 마감판(EP) 1개(왼쪽)"
    assert _rows(oid, "CURRENT")[uids[1]].changes == []  # 바꾸지 않은 품목은 까닭 없이 지나간다


def test_transfer_without_options_leaves_current_alone(app, priced):
    drafter = _drafter()
    oid, uids = _partner_order(app, priced, [_item(lines=[{"key": "r4", "qty": 1}])], drafter)
    assert _transfer(_as(app, drafter), oid).status_code == 200
    assert [(l["key"], l["qty"]) for l in _rows(oid, "CURRENT")[uids[0]].lines] == [("r4", "1")]


def test_approve_requires_later_items_and_confirms_with_fingerprint(app, priced):
    drafter = _drafter()
    oid, uids = _partner_order(app, priced, [_item(lines=[{"key": "r4", "qty": 1}]), _item("침대 붙박이장", state="later")],
                               drafter)
    _to_confirm(oid)
    partner = _client(app, db_session.get(User, priced["partner_a"]))
    page = partner.get(f"/partner/orders/{oid}").get_data(as_text=True)
    assert "data-pp-confirm-options" in page and "data-pp-optfield" in page and not any(p in page for p in PRICES)
    assert "저희 도면팀이 바꾼 옵션은" not in page  # 바뀐 품목이 없으면 노란 칸 안내도 없다(대조군)
    blocked = partner.post(f"/api/partner/orders/{oid}/approve-drawing", json={"idempotency_key": "k1"})
    assert blocked.status_code == 409 and "상담 후 정함" in blocked.get_json()["error"]
    assert _rows(oid, "CONFIRMED") == {}
    picked = {uids[1]: {"lines": [{"key": "r7", "qty": 1}]}}
    ok = partner.post(f"/api/partner/orders/{oid}/approve-drawing", json={"idempotency_key": "k2", "options": picked})
    assert ok.status_code == 200, ok.get_json()
    assert "push_note" in ok.get_json()["data"]  # 옵션을 고른 승인도 발주방 전송 결과를 돌려준다(화면이 알림으로 띄운다)
    confirmed = _rows(oid, "CONFIRMED")
    assert set(confirmed) == set(uids)
    assert [(l["key"], l["qty"]) for l in confirmed[uids[1]].lines] == [("r7", "1")]
    assert _rows(oid, "PARTNER")[uids[1]].state == "chosen"  # 협력사가 도면 확인 때 고른 것이 원문이 된다
    log = db_session.query(SecurityLog).filter_by(action="PARTNER_DRAWING_APPROVED", target_id=oid).one()
    assert len(log.detail["options_fingerprint"]) == 64
    assert db_session.get(Order, oid).structured_data["items"][1]["option_detail"] == "침대 프레임 Q 1개"


def test_drawing_tab_shows_changed_options_with_reason(app, priced):
    drafter = _drafter()
    oid, uids = _partner_order(app, priced, [_item(lines=[{"key": "r4", "qty": 1}])], drafter)
    assert _transfer(_as(app, drafter), oid, partner_options={
        uids[0]: {"lines": [{"key": "r4", "qty": 2}], "reason": "문 폭 때문에 2짝"}}).status_code == 200
    _to_confirm(oid)
    page = _client(app, db_session.get(User, priced["partner_a"])).get(f"/partner/orders/{oid}").get_data(as_text=True)
    assert "바뀜: 슬라이딩 거울 도어 1짝 → 2짝" in page and "바꾼 이유: 문 폭 때문에 2짝" in page
    assert "저희 도면팀이 바꾼 옵션은 노란 칸에 보입니다." in page
    assert "data-pp-optfield" not in page  # 고를 것(상담 후 정함)이 없으면 읽기만
    assert not any(price in page for price in PRICES)


def test_state_only_change_names_states_once():
    """"옵션 없음 → 상담 후 정함"처럼 상태만 바뀌면 이름 칸이 비어 화면에 "옵션"이 두 번 나오지 않는다."""
    none, later = {"state": "none", "lines": [], "customs": []}, {"state": "later", "lines": [], "customs": []}
    assert diff_options(none, later, {}) == [{"name": "", "from": "옵션 없음", "to": "상담 후 정함"}]
