"""협력사 거래명세서 4단계 — 우리 CS 초안 · 발행 · 수정본 · 취소(설계서 docs/specs/2026-11-03-partner-statement_SPEC.md §3.3 · §5.5 · §8).

금액은 확정 옵션(CONFIRMED) × 그 날짜 단가표 판에서만 나온다. CS 는 커스텀 금액과 고친 단가(+ 이유)만 넣는다. 금액이 빈 줄이
남으면 발행이 막히고, 발행본은 잠겨(고치기 409) 단가표 새 판이 나와도 값이 그대로다. 수정본을 발행하면 옛 것은 VOID, 잔액은
옛 것을 빼고 다시 센다. 대조군: 영업팀 · 협력사는 403, CS 팀 · ADMIN 은 200. 단가 · 이름은 가짜다.
"""
from __future__ import annotations

from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from foms.services.partners.item_options import confirm_partner_options
from foms.services.partners.price_list import save_price_list
from foms.services.partners.statement_view import korean_amount
from models import Order, PartnerStatement, SecurityLog, User
from tests.security.partner_fixtures import _PAYLOAD, _client, _create, _user, world  # noqa: F401
from tests.security.test_partner_item_options import SHEET, _item, priced  # noqa: F401 — 단가표 판 준비물 재사용

API = "/api/partner-statements"


def _confirmed_order(app, w, items, *, date="2026-11-10"):
    resp = _create(app, w["partner_a"], {**_PAYLOAD, "items": items})
    assert resp.status_code == 200, resp.get_json()
    oid = resp.get_json()["data"]["order_id"]
    order = db_session.get(Order, oid)
    sd = dict(order.structured_data)
    sd["schedule"] = {**(sd.get("schedule") or {}), "construction": {"date": date}}
    order.structured_data = sd
    flag_modified(order, "structured_data")
    confirm_partner_options(db_session, order, {}, None)
    db_session.commit()
    return oid


def _cs(app):
    return _client(app, _user(team="CS", name="씨에스"))


def _draft(client, oid):
    resp = client.post(f"{API}/orders/{oid}/draft")
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["data"]


def _lines(data):
    return [(g["title"], [(l["name"], l["qty"], l["unit_price"], l["amount"], l["source"]) for l in g["lines"]])
            for g in data["groups"]]


def test_draft_amounts_custom_blocks_issue_then_issue_locks_and_numbers(app, priced):
    oid = _confirmed_order(app, priced, [_item(lines=[{"key": "r4", "qty": 1}], customs=[{"text": "선반 하나 더"}])])
    client = _cs(app)
    data = _draft(client, oid)
    # 가로 3,700 ÷ 300 = 12.33 → 12.3 자 × 98,765 = 1,214,809.5 → 1,214,810 (원 단위 반올림)
    assert _lines(data) == [("슬라이딩", [("슬라이딩", "12.3", 98765, 1214810, "auto"),
                                         ("슬라이딩 거울 도어", "1", 176543, 176543, "auto"),
                                         ("선반 하나 더", "1", None, None, "custom")])]
    assert data["complete"] is False
    blocked = client.post(f"{API}/{data['id']}/issue", json={"version": data["version"]})
    assert blocked.status_code == 409 and "금액이 빈 줄" in blocked.get_json()["error"]
    saved = client.post(f"{API}/{data['id']}/save", json={"version": data["version"],
                                                          "edits": [{"ref": "1-3", "amount": "50,000"}]}).get_json()["data"]
    assert saved["complete"] is True and saved["total"] == 1214810 + 176543 + 50000
    assert saved["supply"] + saved["vat"] == saved["total"] and saved["supply"] == round(saved["total"] / 1.1)
    stale = client.post(f"{API}/{data['id']}/save", json={"version": data["version"], "edits": []})
    assert stale.status_code == 409  # 화면이 본 version 이 낡으면 막는다
    issued = client.post(f"{API}/{data['id']}/issue", json={"version": saved["version"]}).get_json()["data"]
    assert issued["status"] == "ISSUED" and issued["doc_no"] == "HD-20261110-01" and issued["date"] == "2026-11-10"
    assert (issued["prev_balance"], issued["after_balance"]) == (0, saved["total"])
    locked = client.post(f"{API}/{data['id']}/save", json={"version": issued["version"], "edits": []})
    assert locked.status_code == 409 and "수정본" in locked.get_json()["error"]
    assert db_session.query(SecurityLog).filter_by(action="PARTNER_STATEMENT_ISSUED", target_id=data["id"]).count() == 1
    # 같은 날 둘째 명세서는 순번 02 · 앞 잔액을 이어받는다
    oid2 = _confirmed_order(app, priced, [_item(lines=[{"key": "r4", "qty": 2}])])
    d2 = _draft(client, oid2)
    i2 = client.post(f"{API}/{d2['id']}/issue", json={"version": d2["version"]}).get_json()["data"]
    assert i2["doc_no"] == "HD-20261110-02" and i2["prev_balance"] == saved["total"]


def test_price_edit_needs_reason_and_recalc_keeps_cs_values(app, priced):
    oid = _confirmed_order(app, priced, [_item(lines=[{"key": "r4", "qty": 1}], customs=[{"text": "선반"}])])
    client = _cs(app)
    data = _draft(client, oid)
    no_reason = client.post(f"{API}/{data['id']}/save", json={"version": data["version"],
                                                              "edits": [{"ref": "1-2", "unit_price": 150000}]})
    assert no_reason.status_code == 400 and "이유" in no_reason.get_json()["error"]
    saved = client.post(f"{API}/{data['id']}/save", json={"version": data["version"], "edits": [
        {"ref": "1-2", "unit_price": 150000, "reason": "협의 단가"}, {"ref": "1-3", "amount": 30000}]}).get_json()["data"]
    door = saved["groups"][0]["lines"][1]
    assert (door["source"], door["unit_price"], door["orig_unit_price"], door["amount"], door["reason"]) == (
        "edited", 150000, 176543, 150000, "협의 단가")
    again = client.post(f"{API}/{data['id']}/recalc", json={"version": saved["version"]}).get_json()["data"]
    assert _lines(again) == _lines(saved)  # 다시 계산해도 CS 가 넣은 값은 같은 줄에 남는다
    back = client.post(f"{API}/{data['id']}/save", json={"version": again["version"],
                                                         "edits": [{"ref": "1-2", "unit_price": 176543}]}).get_json()["data"]
    assert back["groups"][0]["lines"][1]["source"] == "auto" and "orig_unit_price" not in back["groups"][0]["lines"][1]


def test_issued_values_survive_new_price_list_and_revision_voids_old(app, priced):
    oid = _confirmed_order(app, priced, [_item(lines=[{"key": "r4", "qty": 1}])])
    client = _cs(app)
    data = _draft(client, oid)
    issued = client.post(f"{API}/{data['id']}/issue", json={"version": data["version"]}).get_json()["data"]
    cheaper = {**SHEET, "categories": [dict(c, rows=[dict(r, cells=[r["cells"][0], 1]) for r in c["rows"]])
                                       for c in SHEET["categories"]]}
    from foms.services.partners.price_list import active_price_list
    save_price_list(db_session, priced["org_a"], cheaper, label="12월판", effective_from="2026-11-01",
                    base_id=active_price_list(db_session, priced["org_a"]).id, user_id=None)
    db_session.commit()
    again = client.get(f"{API}/{data['id']}").get_json()["data"]
    assert _lines(again) == _lines(issued) and again["total"] == issued["total"]  # 발행본은 스냅샷
    assert client.post(f"{API}/{data['id']}/revise", json={"reason": " "}).status_code == 400
    rev = client.post(f"{API}/{data['id']}/revise", json={"reason": "거울 도어 1짝 빠짐"}).get_json()["data"]
    assert rev["status"] == "DRAFT" and rev["revision_of"] == data["id"] and _lines(rev) == _lines(issued)
    assert client.post(f"{API}/{rev['id']}/recalc", json={"version": rev["version"]}).status_code == 409
    assert client.post(f"{API}/{data['id']}/revise", json={"reason": "또"}).status_code == 409  # 초안은 하나
    done = client.post(f"{API}/{rev['id']}/issue", json={"version": rev["version"]}).get_json()["data"]
    db_session.expire_all()
    old = db_session.get(PartnerStatement, data["id"])
    assert old.status == "VOID" and old.reason == "거울 도어 1짝 빠짐"
    assert done["doc_no"] == "HD-20261110-02" and done["prev_balance"] == 0  # 옛 것은 잔액에서 빠진다
    voided = client.post(f"{API}/{rev['id']}/void", json={"reason": "주문 취소"}).get_json()["data"]
    assert voided["status"] == "VOID" and voided["reason"] == "주문 취소"


def test_only_cs_team_and_admin(app, priced):
    oid = _confirmed_order(app, priced, [_item(lines=[{"key": "r4", "qty": 1}])])
    sales = _client(app, db_session.get(User, priced["sales"]))
    partner = _client(app, db_session.get(User, priced["partner_a"]))
    assert sales.get(f"{API}/pending").status_code == 403
    assert sales.post(f"{API}/orders/{oid}/draft").status_code == 403
    assert partner.get(f"{API}/pending").status_code == 403
    assert partner.post(f"{API}/orders/{oid}/draft").status_code == 403
    assert sales.get("/erp/partner-statements").status_code == 403
    admin = _client(app, db_session.get(User, priced["admin"]))
    assert admin.get(f"{API}/pending").status_code == 200  # 대조군
    accounting = _client(app, _user(team="ACCOUNTING"))
    assert accounting.get(f"{API}/pending").status_code == 200  # 회계팀은 CS 권한을 잇는다
    assert _cs(app).get("/erp/partner-statements").status_code == 200


def test_pending_list_and_bulk_issue_only_complete(app, priced):
    ready = _confirmed_order(app, priced, [_item(lines=[{"key": "r4", "qty": 1}])])
    custom = _confirmed_order(app, priced, [_item(customs=[{"text": "특수 선반"}])], date="2026-11-30")
    client = _cs(app)
    rows = {r["order_id"]: r for r in client.get(f"{API}/pending").get_json()["data"]["rows"]}
    assert rows[ready]["complete"] is True and rows[custom]["complete"] is False and rows[custom]["custom_open"] == 1
    assert [r["order_id"] for r in client.get(f"{API}/pending").get_json()["data"]["rows"]] == [ready, custom]
    bulk = client.post(f"{API}/issue-complete").get_json()["data"]
    assert len(bulk["issued"]) == 1 and bulk["skipped"] == []
    left = [r["order_id"] for r in client.get(f"{API}/pending").get_json()["data"]["rows"]]
    assert left == [custom]
    issued = client.get(f"{API}/issued").get_json()["data"]["rows"]
    assert [(r["order_id"], r["status"]) for r in issued] == [(ready, "ISSUED")]


def test_cancelled_item_left_out(app, priced):
    oid = _confirmed_order(app, priced, [_item(lines=[{"key": "r4", "qty": 1}]), _item("침대 붙박이장", state="none")])
    order = db_session.get(Order, oid)
    sd = dict(order.structured_data)
    sd["items"] = [dict(sd["items"][0]), {**sd["items"][1], "cancel": {"at": "2026-11-03"}}]
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()
    data = _draft(_cs(app), oid)
    assert [g["title"] for g in data["groups"]] == ["슬라이딩"]


def test_profile_admin_only_prefix_and_print(app, priced):
    admin = _client(app, db_session.get(User, priced["admin"]))
    url = f"/api/admin/partners/{priced['org_a']}/statement-profile"
    got = admin.get(url).get_json()["data"]
    assert got["version"] == 0 and got["supplier"]["doc_prefix"] == "HD"
    body = {"version": 0, "supplier": {"name": "가짜공급", "doc_prefix": "ab", "accounts": "가짜은행 000-0\n둘째 111-1"},
            "receiver": {"ceo": "가나대표"}}
    saved = admin.post(url, json=body).get_json()["data"]
    assert saved["version"] == 1 and saved["supplier"]["doc_prefix"] == "AB" and saved["receiver"]["name"] == "가나가구"
    assert admin.post(url, json=body).status_code == 409  # 낡은 version
    assert _cs(app).post(url, json={**body, "version": 1}).status_code == 403
    oid = _confirmed_order(app, priced, [_item(lines=[{"key": "r4", "qty": 1}])])
    client = _cs(app)
    data = _draft(client, oid)
    issued = client.post(f"{API}/{data['id']}/issue", json={"version": data["version"]}).get_json()["data"]
    assert issued["doc_no"].startswith("AB-20261110-")
    page = client.get(f"/erp/partner-statements/{data['id']}/print").get_data(as_text=True)
    assert "가짜공급" in page and "가나대표" in page and "가짜은행 000-0" in page
    assert korean_amount(issued["total"]) in page and "공급받는자용" in page and "공급자용" in page


def test_korean_amount():
    assert korean_amount(0) == "영"
    assert korean_amount(1214810) == "일백이십일만사천팔백일십"
    assert korean_amount(100000000) == "일억"
    assert korean_amount(10000) == "일만"
    assert korean_amount(1001) == "일천일"
