"""협력사 명세서 — 확정한 옵션 고치기(설계서 docs/specs/2026-11-11-partner-confirmed-option-fix_SPEC.md §5).

협력사가 옵션을 틀리게 고르고 도면을 확정해도, 우리 CS 가 명세서 초안에서 확정 옵션을 지우기 · 수 바꾸기 · 더하기로 고치면
확정본(CURRENT · CONFIRMED)이 바뀌고 명세서가 다시 센다. 협력사 원문(PARTNER)은 그대로다(대조군). 바뀐 품목은 이유가 꼭
있어야 하고 그 이유가 협력사 화면 · 명세서 근거 칸에 보인다. 수정본은 발행본과 같은 단가표 판으로 센다. 단가 · 이름은 가짜다.
"""
from __future__ import annotations

from db import db_session
from foms.services.partners.price_list import active_price_list, save_price_list
from models import Order, PartnerStatement, SecurityLog, User
from tests.security.partner_fixtures import _client, _user, world  # noqa: F401
from tests.security.test_partner_item_options import SHEET, _item, _rows, priced  # noqa: F401
from tests.security.test_partner_option_review import _as, _drafter, _partner_order, _to_confirm, _transfer
from tests.security.test_partner_statements import API, _confirmed_order, _cs, _draft

BASE = 1214810  # 가로 3,700 → 12.3 자 × 98,765
DOOR = 176543   # 슬라이딩 거울 도어 1짝
LIGHT = 43210   # 라인 조명 1m


def _amounts(data):
    return [[(l["key"], l["qty"], l["amount"]) for l in g["lines"]] for g in data["groups"]]


def _fix(client, data, uid, reason="도면 기준", **options):
    return client.post(f"{API}/{data['id']}/options",
                       json={"version": data["version"], "items": {uid: {**options, "reason": reason}}})


def test_cs_removes_changes_and_adds_options_statement_recounts_partner_original_kept(app, priced):
    oid = _confirmed_order(app, priced, [_item(lines=[{"key": "r4", "qty": 1}])])
    client = _cs(app)
    data = _draft(client, oid)
    assert _amounts(data) == [[("r2", "12.3", BASE), ("r4", "1", DOOR)]]
    view = client.get(f"{API}/{data['id']}/options").get_json()["data"]
    uid = view["items"][0]["uid"]
    assert view["editable"] is True and view["items"][0]["current"]["lines"][0]["unit"] == "짝"
    assert not any(str(price) in repr(view) for price in (BASE, DOOR, LIGHT))  # 고르기 목록에 금액은 없다

    no_reason = _fix(client, data, uid, reason=" ", lines=[{"key": "r4", "qty": 2}])
    assert no_reason.status_code == 400 and "이유" in no_reason.get_json()["error"]
    later = _fix(client, data, uid, state="later")
    assert later.status_code == 400 and "상담 후 정함" in later.get_json()["error"]
    same = _fix(client, data, uid, lines=[{"key": "r4", "qty": 1}])
    assert same.status_code == 400 and "바뀐 옵션이 없습니다" in same.get_json()["error"]

    fixed = _fix(client, data, uid, reason="문 폭 때문에 2짝", lines=[{"key": "r4", "qty": 2}, {"key": "r8", "qty": 3}])
    assert fixed.status_code == 200, fixed.get_json()
    out = fixed.get_json()["data"]
    assert _amounts(out) == [[("r2", "12.3", BASE), ("r4", "2", DOOR * 2), ("r8", "3", LIGHT * 3)]]
    assert out["total"] == BASE + DOOR * 2 + LIGHT * 3 and out["version"] == data["version"] + 1
    assert out["groups"][0]["lines"][1]["basis"] == "바꾼 옵션 · 문 폭 때문에 2짝"
    stale = _fix(client, data, uid, lines=[{"key": "r4", "qty": 1}])
    assert stale.status_code == 409  # 화면이 본 version 이 낡으면 막는다

    rows = {stage: _rows(oid, stage)[0] for stage in ("PARTNER", "CURRENT", "CONFIRMED")}
    assert [(l["key"], l["qty"]) for l in rows["PARTNER"].lines] == [("r4", "1")]  # 원문은 그대로(대조군)
    for stage in ("CURRENT", "CONFIRMED"):
        assert [(l["key"], l["qty"]) for l in rows[stage].lines] == [("r4", "2"), ("r8", "3")]
        assert {c["reason"] for c in rows[stage].changes} == {"문 폭 때문에 2짝"}
    assert db_session.get(Order, oid).structured_data["items"][0]["option_detail"].startswith("슬라이딩 거울 도어 2짝")
    log = db_session.query(SecurityLog).filter_by(action="PARTNER_OPTIONS_CORRECTED", target_id=data["id"]).one()
    assert log.detail["items"][0]["reason"] == "문 폭 때문에 2짝" and log.detail["before"] != log.detail["after"]

    # 지우기: 거울 도어를 빼면 그 줄이 사라지고, 앞서 적힌 라인 조명 이유는 그대로 남는다
    gone = _fix(client, out, uid, reason="거울 도어 없음", lines=[{"key": "r8", "qty": 3}]).get_json()["data"]
    assert _amounts(gone) == [[("r2", "12.3", BASE), ("r8", "3", LIGHT * 3)]]
    confirmed = _rows(oid, "CONFIRMED")[0]
    assert {(c["name"][:6], c["reason"]) for c in confirmed.changes} == {
        ("슬라이딩 거", "거울 도어 없음"), ("라인 조명 ", "문 폭 때문에 2짝")}



def test_partner_sees_fixed_options_with_reasons_after_confirm(app, priced):
    # 실제 흐름: 도면 전달 → 협력사 "이대로 만들어 주세요"(확정 · 생산) → CS 가 명세서에서 고침 → 협력사 도면 탭에 이유가 보인다.
    drafter = _drafter()
    oid, uids = _partner_order(app, priced, [_item(lines=[{"key": "r4", "qty": 1}])], drafter)
    assert _transfer(_as(app, drafter), oid).status_code == 200
    _to_confirm(oid)
    partner = _client(app, db_session.get(User, priced["partner_a"]))
    assert partner.post(f"/api/partner/orders/{oid}/approve-drawing", json={"idempotency_key": "k1"}).status_code == 200
    before = partner.get(f"/partner/orders/{oid}").get_data(as_text=True)
    assert "data-pp-confirm-options" in before and "저희가 바꾼 옵션은" not in before  # 안 고쳤으면 노란 칸 없음(대조군)
    client = _cs(app)
    data = _draft(client, oid)
    assert _fix(client, data, uids[0], reason="도면엔 거울 도어 없음", state="none").status_code == 200
    page = partner.get(f"/partner/orders/{oid}").get_data(as_text=True)
    assert "바뀜: 슬라이딩 거울 도어 1짝 → 없음 · 이유: 도면엔 거울 도어 없음" in page
    assert '거래명세서 "금액 문의"로 알려 주세요' in page and "data-pp-optfield" not in page
    assert not any(str(price) in page for price in (BASE, DOOR))


def test_cs_price_edit_survives_option_fix(app, priced):
    oid = _confirmed_order(app, priced, [_item(lines=[{"key": "r4", "qty": 1}])])
    client = _cs(app)
    data = _draft(client, oid)
    saved = client.post(f"{API}/{data['id']}/save", json={"version": data["version"], "edits": [
        {"ref": "1-1", "unit_price": 90000, "reason": "협의 단가"}]}).get_json()["data"]
    uid = client.get(f"{API}/{data['id']}/options").get_json()["data"]["items"][0]["uid"]
    out = _fix(client, saved, uid, lines=[{"key": "r4", "qty": 1}, {"key": "r8", "qty": 1}]).get_json()["data"]
    base = out["groups"][0]["lines"][0]
    assert (base["source"], base["unit_price"], base["reason"]) == ("edited", 90000, "협의 단가")
    assert out["total"] == base["amount"] + DOOR + LIGHT


def test_revision_fix_uses_issued_price_list_and_issued_is_locked(app, priced):
    oid = _confirmed_order(app, priced, [_item(lines=[{"key": "r4", "qty": 1}])])
    client = _cs(app)
    data = _draft(client, oid)
    issued = client.post(f"{API}/{data['id']}/issue", json={"version": data["version"]}).get_json()["data"]
    uid = client.get(f"{API}/{data['id']}/options").get_json()["data"]["items"][0]["uid"]
    locked = _fix(client, issued, uid, lines=[{"key": "r4", "qty": 2}])
    assert locked.status_code == 409 and "수정본" in locked.get_json()["error"]
    cheaper = {**SHEET, "categories": [dict(c, rows=[dict(r, cells=[r["cells"][0], 1]) for r in c["rows"]])
                                       for c in SHEET["categories"]]}
    save_price_list(db_session, priced["org_a"], cheaper, label="12월판", effective_from="2026-11-01",
                    base_id=active_price_list(db_session, priced["org_a"]).id, user_id=None)
    db_session.commit()
    rev = client.post(f"{API}/{data['id']}/revise", json={"reason": "거울 도어 2짝"}).get_json()["data"]
    out = _fix(client, rev, uid, reason="도면은 2짝", lines=[{"key": "r4", "qty": 2}]).get_json()["data"]
    assert _amounts(out) == [[("r2", "12.3", BASE), ("r4", "2", DOOR * 2)]]  # 발행본과 같은 판(새 판 1원이 아님)
    assert out["date"] == issued["date"] and out["revision_of"] == data["id"]
    done = client.post(f"{API}/{rev['id']}/issue", json={"version": out["version"]}).get_json()["data"]
    db_session.expire_all()
    assert done["total"] == BASE + DOOR * 2 and db_session.get(PartnerStatement, data["id"]).status == "VOID"


def test_only_statement_staff_can_fix_options(app, priced):
    oid = _confirmed_order(app, priced, [_item(lines=[{"key": "r4", "qty": 1}])])
    data = _draft(_cs(app), oid)
    uid = _rows(oid, "CONFIRMED")[0].item_uid
    sales = _client(app, _user(team="SALES", name="영업"))
    partner = _client(app, db_session.get(User, priced["partner_a"]))
    for client in (sales, partner):
        assert client.get(f"{API}/{data['id']}/options").status_code in (403, 404)
        assert _fix(client, data, uid, lines=[{"key": "r4", "qty": 2}]).status_code in (403, 404)
    assert [(l["key"], l["qty"]) for l in _rows(oid, "CONFIRMED")[0].lines] == [("r4", "1")]
    assert _fix(_cs(app), data, uid, lines=[{"key": "r4", "qty": 2}]).status_code == 200  # CS 는 된다(음성 대조군)
