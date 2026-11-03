"""협력사 입금 장부 5단계 — 기록 · 지우기 · 잔액 · 입금 대기 · 월 장부 받기(설계서 docs/specs/2026-11-03-partner-statement_SPEC.md §3.4 · §5.7 · §8).

잔액 = 발행 명세서 합 − 지우지 않은 입금 합이고, 다음 명세서의 전일 잔액에 그대로 들어간다. 명세서를 고른 입금은 그 명세서에,
고르지 않은 입금은 오래된 명세서부터 채워 "입금 대기"를 정한다. 지우기는 이유가 꼭 있어야 하고 줄은 남는다. 대조군: 영업팀 ·
협력사는 기록 403, CS 는 200. 다른 회사 명세서에는 입금을 맞출 수 없다. 단가 · 이름은 가짜다.
"""
from __future__ import annotations

from db import db_session
from foms.services.partners.payments import allocate, unpaid_order_ids
from models import PartnerPayment, SecurityLog, User
from tests.security.partner_fixtures import _PAYLOAD, _client, _create, _user, world  # noqa: F401
from tests.security.test_partner_item_options import _item, priced  # noqa: F401
from tests.security.test_partner_statement_portal import _issued, _partner
from tests.security.test_partner_statements import API, _cs, _draft, _confirmed_order

PAY = "/api/partner-payments"


def test_record_void_balance_and_next_prev_balance(app, priced):
    cs = _cs(app)
    _o1, first = _issued(app, priced, cs)
    org = priced["org_a"]
    got = cs.get(f"{PAY}?org_id={org}").get_json()["data"]
    assert got["balance"] == first["total"] and [s["id"] for s in got["statements"]] == [first["id"]]
    assert cs.post(PAY, json={"org_id": org, "paid_on": "2026-11-11", "amount": "0"}).status_code == 400
    assert cs.post(PAY, json={"org_id": org, "paid_on": "", "amount": "1000"}).status_code == 400
    paid = cs.post(PAY, json={"org_id": org, "paid_on": "2026-11-11", "amount": "100,000", "memo": "가나가구 입금"}).get_json()["data"]
    assert paid["balance"] == first["total"] - 100000 and paid["payments"][0]["amount"] == 100000
    oid2 = _confirmed_order(app, priced, [_item(lines=[{"key": "r4", "qty": 2}])])
    d2 = _draft(cs, oid2)
    second = cs.post(f"{API}/{d2['id']}/issue", json={"version": d2["version"]}).get_json()["data"]
    assert second["prev_balance"] == first["total"] - 100000  # 입금이 잔액에서 빠진다
    pid = paid["payments"][0]["id"]
    assert cs.post(f"{PAY}/{pid}/void", json={"reason": " "}).status_code == 400
    voided = cs.post(f"{PAY}/{pid}/void", json={"reason": "금액 잘못 넣음"}).get_json()["data"]
    assert voided["balance"] == first["total"] + second["total"] and voided["payments"][0]["voided"] is True
    assert cs.post(f"{PAY}/{pid}/void", json={"reason": "또"}).status_code == 409
    assert db_session.query(SecurityLog).filter(SecurityLog.action.in_(
        ("PARTNER_PAYMENT_RECORDED", "PARTNER_PAYMENT_VOIDED"))).count() == 2


def test_only_cs_and_own_org_statement(app, priced):
    cs = _cs(app)
    _o1, first = _issued(app, priced, cs)
    body = {"org_id": priced["org_b"], "paid_on": "2026-11-11", "amount": 1000, "statement_id": first["id"]}
    assert cs.post(PAY, json=body).status_code == 400  # 다른 회사 명세서에는 맞출 수 없다
    sales = _client(app, db_session.get(User, priced["sales"]))
    assert sales.post(PAY, json={**body, "org_id": priced["org_a"]}).status_code == 403
    assert sales.get(f"{PAY}/export.csv?org_id={priced['org_a']}").status_code == 403
    assert _partner(app, priced).post(PAY, json={**body, "org_id": priced["org_a"]}).status_code == 403
    ok = cs.post(PAY, json={**body, "org_id": priced["org_a"]})
    assert ok.status_code == 200  # 대조군
    assert db_session.query(PartnerPayment).one().statement_id == first["id"]


def test_allocation_matched_then_oldest_first_and_unpaid_badge(app, priced):
    cs = _cs(app)
    o1, first = _issued(app, priced, cs, date="2026-11-05")
    o2, second = _issued(app, priced, cs, date="2026-11-10", qty=2)
    org = priced["org_a"]
    assert unpaid_order_ids(db_session, [o1, o2]) == {o1, o2}
    cs.post(PAY, json={"org_id": org, "paid_on": "2026-11-11", "amount": second["total"], "statement_id": second["id"]})
    cs.post(PAY, json={"org_id": org, "paid_on": "2026-11-12", "amount": first["total"] - 1})
    db_session.expire_all()
    assert allocate(db_session, org) == {first["id"]: first["total"] - 1, second["id"]: second["total"]}
    assert unpaid_order_ids(db_session, [o1, o2]) == {o1}
    cs.post(PAY, json={"org_id": org, "paid_on": "2026-11-12", "amount": 1})
    db_session.expire_all()
    assert unpaid_order_ids(db_session, [o1, o2]) == set()


def test_partner_ledger_shows_payments_carry_and_csv(app, priced):
    cs = _cs(app)
    _o1, october = _issued(app, priced, cs, date="2026-10-20")
    _o2, november = _issued(app, priced, cs, date="2026-11-10")
    org = priced["org_a"]
    cs.post(PAY, json={"org_id": org, "paid_on": "2026-10-25", "amount": 50000})
    cs.post(PAY, json={"org_id": org, "paid_on": "2026-11-12", "amount": 70000, "memo": "11월 입금"})
    mine = _partner(app, priced)
    page = mine.get("/partner/statements?month=2026-11").get_data(as_text=True)
    assert f"{october['total'] - 50000:,}원" in page  # 이월 = 지난달 발행 − 지난달 입금
    assert "− 70,000원" in page and "11월 입금" in page and "입금 대기" in page
    assert f"{october['total'] + november['total'] - 120000:,}원" in page  # 지금 잔액
    csv_resp = mine.get("/partner/statements/export.csv?month=2026-11")
    text = csv_resp.get_data().decode("utf-8")
    assert csv_resp.status_code == 200 and text.startswith("﻿일자,") and "\r\n" in text
    assert f"{october['total'] - 50000}" in text and ",70000," in text and november["doc_no"] in text
    staff_csv = cs.get(f"{PAY}/export.csv?org_id={org}&month=2026-11").get_data().decode("utf-8")
    assert staff_csv == text
    assert _partner(app, priced, "partner_b").get("/partner/statements/export.csv?month=2026-11").get_data().decode(
        "utf-8").count("\r\n") == 3  # 다른 회사는 머리 · 이월 · 합계만
