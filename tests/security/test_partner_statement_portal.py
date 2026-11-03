"""협력사 거래명세서 4단계 — 협력사 쪽 월 장부 · 보기 · 확인했어요 · 금액 문의(설계서 docs/specs/2026-11-03-partner-statement_SPEC.md §5.6 · §6 · §8).

협력사는 자기 회사의 발행 · 취소 명세서만 본다: 초안 · 다른 회사 명세서는 404(자기 것은 200 — 음성 대조군). 처음 열면 "열어 봄",
"확인했어요"는 한 번만 남고 취소본은 409. 문의는 고른 줄과 함께 남고 우리 CS 답이 협력사 화면에 보인다. 월 장부 이월은 지난달 발행
합이다. 단가 · 이름은 가짜다.
"""
from __future__ import annotations

from db import db_session
from models import PartnerStatement, SecurityLog, User
from tests.security.partner_fixtures import _PAYLOAD, _client, _create, _user, world  # noqa: F401
from tests.security.test_partner_item_options import _item, priced  # noqa: F401
from tests.security.test_partner_statements import API, _confirmed_order, _cs, _draft


def _issued(app, w, client, *, date="2026-11-10", qty=1):
    oid = _confirmed_order(app, w, [_item(lines=[{"key": "r4", "qty": qty}])], date=date)
    data = _draft(client, oid)
    issued = client.post(f"{API}/{data['id']}/issue", json={"version": data["version"]}).get_json()["data"]
    return oid, issued


def _partner(app, w, key="partner_a"):
    return _client(app, db_session.get(User, w[key]))


def test_partner_sees_only_own_issued_statements(app, priced):
    cs = _cs(app)
    oid, issued = _issued(app, priced, cs)
    draft_oid = _confirmed_order(app, priced, [_item(lines=[{"key": "r4", "qty": 3}])])
    draft = _draft(cs, draft_oid)
    mine = _partner(app, priced)
    page = mine.get(f"/partner/statements/{issued['id']}")
    assert page.status_code == 200 and issued["doc_no"] in page.get_data(as_text=True)  # 대조군
    assert mine.get(f"/partner/statements/{draft['id']}").status_code == 404  # 초안은 안 보인다
    assert _partner(app, priced, "partner_b").get(f"/partner/statements/{issued['id']}").status_code == 404
    assert _partner(app, priced, "partner_b").post(f"/api/partner/statements/{issued['id']}/ack").status_code == 404
    ledger = mine.get("/partner/statements?month=2026-11").get_data(as_text=True)
    assert issued["doc_no"] in ledger and "새 명세서" in ledger
    db_session.expire_all()
    assert db_session.get(PartnerStatement, issued["id"]).partner_viewed_at is not None
    detail = mine.get(f"/partner/orders/{oid}").get_data(as_text=True)
    assert 'data-pp-tab="statements"' in detail
    assert 'data-pp-tab="statements"' not in mine.get(f"/partner/orders/{draft_oid}").get_data(as_text=True)
    printed = mine.get(f"/partner/statements/{issued['id']}/print").get_data(as_text=True)
    assert "data:image/svg+xml" in printed and "공급받는자용" in printed and "공급자용" in printed
    assert cs.get("/partner/statements").status_code in (302, 403)  # 우리 직원은 협력사 화면이 아니다


def test_ack_once_and_void_refused(app, priced):
    cs = _cs(app)
    _oid, issued = _issued(app, priced, cs)
    mine = _partner(app, priced)
    assert mine.post(f"/api/partner/statements/{issued['id']}/ack").status_code == 200
    assert mine.post(f"/api/partner/statements/{issued['id']}/ack").status_code == 200
    assert db_session.query(SecurityLog).filter_by(action="PARTNER_STATEMENT_ACKED", target_id=issued["id"]).count() == 1
    assert "확인함" in mine.get("/partner/statements?month=2026-11").get_data(as_text=True)
    cs.post(f"{API}/{issued['id']}/void", json={"reason": "주문 취소"})
    _oid2, other = _issued(app, priced, cs)
    cs.post(f"{API}/{other['id']}/void", json={"reason": "다시 낼 것"})
    refused = mine.post(f"/api/partner/statements/{other['id']}/ack")
    assert refused.status_code == 409
    assert "다시 낼 것" in mine.get("/partner/statements?month=2026-11").get_data(as_text=True)


def test_question_with_line_and_cs_answer(app, priced):
    cs = _cs(app)
    _oid, issued = _issued(app, priced, cs)
    mine = _partner(app, priced)
    url = f"/api/partner/statements/{issued['id']}/questions"
    assert mine.post(url, json={"line_ref": "9-9", "text": "이거 뭐죠"}).status_code == 400
    assert mine.post(url, json={"line_ref": "1-2", "text": "  "}).status_code == 400
    asked = mine.post(url, json={"line_ref": "1-2", "text": "거울 도어 1짝 맞나요?"}).get_json()["data"]["questions"]
    assert [(q["line"], q["text"], q["answer"]) for q in asked] == [("1. 슬라이딩 · 슬라이딩 거울 도어", "거울 도어 1짝 맞나요?", "")]
    rows = cs.get(f"{API}/issued").get_json()["data"]["rows"]
    assert rows[0]["open_questions"] == 1
    qid = asked[0]["id"]
    answered = cs.post(f"{API}/{issued['id']}/questions/{qid}/answer", json={"text": "네, 1짝입니다."}).get_json()["data"]
    assert answered["questions"][0]["answer"] == "네, 1짝입니다."
    assert _client(app, db_session.get(User, priced["sales"])).post(
        f"{API}/{issued['id']}/questions/{qid}/answer", json={"text": "x"}).status_code == 403
    assert "답: 네, 1짝입니다." in mine.get(f"/partner/statements/{issued['id']}").get_data(as_text=True)


def test_ledger_carry_from_previous_month(app, priced):
    cs = _cs(app)
    _o1, october = _issued(app, priced, cs, date="2026-10-20")
    _o2, november = _issued(app, priced, cs, date="2026-11-10", qty=2)
    mine = _partner(app, priced)
    page = mine.get("/partner/statements?month=2026-11").get_data(as_text=True)
    assert f"{october['total']:,}원" in page and f"{november['total']:,}원" in page
    assert f"{october['total'] + november['total']:,}원" in page  # 지금 잔액
    assert october["doc_no"] not in page  # 지난달 명세서는 이월로만
    assert october["doc_no"] in mine.get("/partner/statements?month=2026-10").get_data(as_text=True)


def test_final_drawings_show_as_thumbnails(app, priced):
    from sqlalchemy.orm.attributes import flag_modified
    from models import Order

    cs = _cs(app)
    oid = _confirmed_order(app, priced, [_item(lines=[{"key": "r4", "qty": 1}])])
    order = db_session.get(Order, oid)
    sd = dict(order.structured_data)
    sd["drawing_current_files"] = [{"key": f"orders/{oid}/drawing/final.png", "filename": "final.png"},
                                   {"key": f"orders/{oid}/drawing/final.pdf", "filename": "final.pdf"}]
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()
    data = _draft(cs, oid)
    assert [(d["name"], d["is_image"]) for d in data["drawings"]] == [("1번 · final.png", True), ("2번 · final.pdf", False)]
    issued = cs.post(f"{API}/{data['id']}/issue", json={"version": data["version"]}).get_json()["data"]
    page = _partner(app, priced).get(f"/partner/statements/{issued['id']}").get_data(as_text=True)
    assert 'class="pp-sv__thumb"' in page and 'alt="1번 · final.png"' in page and "2번 · final.pdf" in page
