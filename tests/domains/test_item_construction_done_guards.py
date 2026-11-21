"""제품마다 '시공 끝' — 교차 검수 고침(E1-1 ~ E1-8)의 문 · 다시 보내기 · 생산 단계 [시공 불가].

설계: ``docs/specs/2026-11-21-item-construction-done_SPEC.md`` 4.2 · 5.3. 준비물은
``test_item_construction_done_api`` 의 것을 그대로 쓴다.
"""

from __future__ import annotations

import copy
import datetime

from sqlalchemy import update

import foms.api.construction.visit_fail as visit_fail
from db import db_session
from foms.services.auth.freelancer_order_rights import OWN_ORDER_ENDPOINTS
from foms.services.orders.item_construction_done import DONE_KEY
from foms.services.orders.state_axes import read_main_stage
from models import Order, OrderAttachment, OrderConstructionAttempt, OrderEvent, SecurityLog
from tests.domains.test_item_construction_done_api import (  # noqa: F401 - visit_history 는 준비물
    FIRST_DAY, UID_A, UID_B, UID_C, _TODAY, _attempts, _events, _fresh, _login, _make_order, _seed_evidence,
    _set_stage, _start, visit_history,
)
from tests.security.test_freelancer_own_order_rights import _client, _freelancer, _link, _order

_KEY_A = {"Idempotency-Key": "5a1f7a52-2b1e-4b1f-9d1c-1a2b3c4d5e6f"}
_KEY_B = {"Idempotency-Key": "6b2e8b63-3c2f-4c2e-8e2d-2b3c4d5e6f70"}


def _post_complete(client, oid, refs, headers=None, **extra):
    body = {"done_item_uids": refs, **extra}
    return client.post(f"/api/orders/{oid}/construction/complete", json=body, headers=headers or {})


def _attachment(order_id: int, name: str) -> int:
    att = OrderAttachment(order_id=order_id, filename=name, file_type="image", category="construction",
                          file_size=10, storage_key=f"orders/{order_id}/{name}")
    db_session.add(att)
    db_session.commit()
    return att.id


def _evidence(client, oid, kind, att_id):
    return client.post(f"/api/orders/{oid}/construction/evidence", json={"kind": kind, "attachment_id": att_id})


# --------------------------------------------------------------------------- #
# E1-3 · E1-8 같은 키 다시 보내기 = 처음 몸 그대로
# --------------------------------------------------------------------------- #
def test_final_complete_replay_returns_the_first_body(client, monkeypatch, visit_history):
    import foms.api.construction.item_done as item_done

    calls: list = []
    monkeypatch.setattr(item_done, "notify_partner_construction_done", lambda db, order: calls.append(order.id))
    _login(client)
    oid = _make_order("PRODUCTION")
    assert _start(client, oid).status_code == 200
    _seed_evidence(oid)
    assert _post_complete(client, oid, [UID_A, UID_B], visit_date=FIRST_DAY).status_code == 200
    _set_stage(oid, "CONSTRUCTION")
    assert _start(client, oid).status_code == 200
    _seed_evidence(oid, after=(9101, 9102), signature=9103)

    first = _post_complete(client, oid, [UID_C], _KEY_A)
    assert first.status_code == 200 and first.get_json()["data"]["done_item_uids"] == [UID_C]
    version = _fresh(oid).mutation_version
    again = _post_complete(client, oid, [UID_C], _KEY_A)
    assert again.status_code == 200
    assert again.get_json() == first.get_json()
    assert _fresh(oid).mutation_version == version
    assert _events(oid, "CONSTRUCTION_COMPLETED") == 1 and calls == [oid]


def test_partial_visit_replay_returns_the_first_body(client):
    _login(client)
    oid = _make_order("CONSTRUCTION")
    assert _start(client, oid).status_code == 200
    _seed_evidence(oid)
    first = _post_complete(client, oid, [UID_A], _KEY_B)
    assert first.status_code == 200
    data = first.get_json()["data"]
    assert data["attempt_id"] and data["done_item_uids"] == [UID_A]
    again = _post_complete(client, oid, [UID_A], _KEY_B)
    assert again.status_code == 200 and again.get_json() == first.get_json()
    assert _events(oid, "CONSTRUCTION_VISIT_DONE") == 1


# --------------------------------------------------------------------------- #
# E1-6 낡은 목록 · E1-7 시공한 날 범위
# --------------------------------------------------------------------------- #
def test_stale_or_unknown_ref_is_409_and_changes_nothing(client, visit_history):
    _login(client)
    oid = _make_order("CONSTRUCTION")
    assert _start(client, oid).status_code == 200
    _seed_evidence(oid)
    assert _post_complete(client, oid, [UID_A]).status_code == 200  # 키 없이 한 번 끝냄
    assert _start(client, oid).status_code == 200
    _seed_evidence(oid)
    for refs in ([UID_A], [UID_B, "no-such-ref"], ["idx:0"]):  # 이미 끝난 것 · 모르는 것 · 이름표가 붙은 옛 자리
        resp = _post_complete(client, oid, refs)
        assert resp.status_code == 409, refs
        body = resp.get_json()
        assert body["code"] == "VISIT_ITEMS_STALE" and body["error"] == "목록이 바뀌었어요. 다시 열어 골라 주세요"
    assert set(_fresh(oid).structured_data[DONE_KEY]) == {UID_A}
    assert [a.status for a in _attempts(oid)] == ["VISITED", "IN_PROGRESS"]


def test_visit_date_must_be_within_the_last_14_days(client):
    _login(client)
    day = lambda n: (_TODAY + datetime.timedelta(days=n)).isoformat()  # noqa: E731
    for bad in (day(1), day(-14), "2026/11/05", "어제"):
        oid = _make_order("CONSTRUCTION")
        _seed_evidence(oid)
        resp = _post_complete(client, oid, [UID_A], visit_date=bad)
        assert resp.status_code == 400, bad
        assert resp.get_json()["code"] == "VISIT_DATE_OUT_OF_RANGE"
        assert DONE_KEY not in _fresh(oid).structured_data
    for good, expected in ((day(-13), day(-13)), (day(0), day(0)), ("", day(0))):
        oid = _make_order("CONSTRUCTION")
        _seed_evidence(oid)
        assert _post_complete(client, oid, [UID_A], visit_date=good).status_code == 200, good
        assert _fresh(oid).structured_data[DONE_KEY][UID_A]["date"] == expected


# --------------------------------------------------------------------------- #
# E1-5 지난 방문 사진은 이번 방문 증빙이 아니다
# --------------------------------------------------------------------------- #
def test_previous_visit_photo_is_rejected_for_split_order(client, visit_history):
    _login(client)
    oid = _make_order("CONSTRUCTION")
    assert _start(client, oid).status_code == 200
    a1, a2, sig = (_attachment(oid, n) for n in ("after1.jpg", "after2.jpg", "signature_1.png"))
    for kind, att in (("after", a1), ("after", a2), ("signature", sig)):
        assert _evidence(client, oid, kind, att).status_code == 200
    assert _post_complete(client, oid, [UID_A]).status_code == 200
    assert _start(client, oid).status_code == 200

    for kind, att in (("after", a1), ("signature", sig)):
        resp = _evidence(client, oid, kind, att)
        assert resp.status_code == 400 and resp.get_json()["error"] == "이전 방문 사진이에요"
    assert _evidence(client, oid, "after", _attachment(oid, "after3.jpg")).status_code == 200
    assert a1 not in _fresh(oid).structured_data["construction"]["evidence"]["after"]


def test_previous_photo_rule_skips_non_split_order(client):
    """제품 칸 날짜가 없는 주문(대조군)은 지금과 같다 — 지난 재작업 사진도 다시 걸 수 있다."""
    _login(client)
    oid = _make_order("CONSTRUCTION", items=[{"uid": UID_A, "product_name": "화장대"}])
    att = _attachment(oid, "old.jpg")
    db_session.add(OrderConstructionAttempt(order_id=oid, status="REWORKED", is_current=False,
                                            evidence={"before": [], "after": [att]}))
    db_session.commit()
    assert _evidence(client, oid, "after", att).status_code == 200


# --------------------------------------------------------------------------- #
# E1-2 생산 단계 방문의 [시공 불가] = 방문만 닫음
# --------------------------------------------------------------------------- #
def test_production_visit_fail_closes_only_the_visit(client, visit_history):
    _login(client)
    oid = _make_order("PRODUCTION")
    assert _start(client, oid).status_code == 200
    _seed_evidence(oid)
    new_day = (_TODAY + datetime.timedelta(days=3)).isoformat()
    body = {"reason": "product_defect", "detail": "문짝 흠집", "reschedule_date": new_day}
    key = {"Idempotency-Key": "7c3f9c74-4d3a-4d3f-8f3e-3c4d5e6f7081"}

    resp = client.post(f"/api/orders/{oid}/construction/fail", json=body, headers=key)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    payload = resp.get_json()
    assert payload["new_status"] == "PRODUCTION" and payload["data"]["mode"] == "visit"

    order = _fresh(oid)
    sd = order.structured_data
    assert read_main_stage(order) == "PRODUCTION" and order.erp_stage_code == "PRODUCTION"
    assert order.status == "PRODUCTION" and "rework_reason" not in sd["workflow"]
    assert sd["construction"]["evidence"] == {"before": [], "after": []}
    attempt = _attempts(oid)[0]
    assert attempt.status == "REWORKED" and attempt.is_current is False
    assert attempt.evidence["after"] == [9001, 9002] and attempt.fail_reason == "product_defect"
    fail = sd["construction_fail_history"]
    assert len(fail) == 1 and fail[0]["previous_stage"] == "PRODUCTION"
    assert sd["workflow"]["history"][-1]["note"].startswith("시공 불가 (단계 그대로)")
    assert sd["schedule"]["construction"]["rescheduled"] is True
    assert new_day in sd["schedule"]["construction"]["date"]  # 지금 다시 잡기 길 그대로
    event = db_session.query(OrderEvent).filter_by(order_id=oid, event_type="CONSTRUCTION_REWORKED").one()
    assert event.payload["visit_only"] is True
    assert db_session.query(SecurityLog).filter_by(action="CONSTRUCTION_REWORK_REQUESTED", target_id=oid).count() == 1

    again = client.post(f"/api/orders/{oid}/construction/fail", json=body, headers=key)
    assert again.status_code == 200 and again.get_json() == payload
    assert len(_fresh(oid).structured_data["construction_fail_history"]) == 1
    assert _start(client, oid).status_code == 200
    assert [a.status for a in _attempts(oid)] == ["REWORKED", "IN_PROGRESS"]


def test_fail_keeps_todays_paths_outside_production_split_visit(client, monkeypatch):
    _login(client)
    # 시공 단계 나눠 시공 주문은 지금처럼 사유별 단계로 되돌린다.
    oid = _make_order("CONSTRUCTION")
    resp = client.post(f"/api/orders/{oid}/construction/fail", json={"reason": "product_defect"})
    assert resp.status_code == 200 and resp.get_json()["new_status"] == "PRODUCTION"
    assert read_main_stage(_fresh(oid)) == "PRODUCTION"

    # 스위치를 끄면 생산 단계 열린 방문도 지금처럼 막힌다(단계 충돌).
    monkeypatch.setenv("FOMS_ITEM_CONSTRUCTION_DONE_ENABLED", "0")
    oid = _make_order("PRODUCTION")
    db_session.add(OrderConstructionAttempt(order_id=oid, status="IN_PROGRESS", is_current=True,
                                            evidence={"before": [], "after": []}))
    db_session.commit()
    resp = client.post(f"/api/orders/{oid}/construction/fail", json={"reason": "site_issue"})
    assert resp.status_code == 409 and resp.get_json()["code"] == "INVALID_STAGE"
    assert _attempts(oid)[0].status == "IN_PROGRESS"


# --------------------------------------------------------------------------- #
# E1-1 프리랜서 — 내 주문의 "오늘 끝낸 제품" 목록만
# --------------------------------------------------------------------------- #
def test_freelancer_reads_visit_items_of_own_order_only(app):
    assert "erp_orders_construction.api_construction_visit_items" in OWN_ORDER_ENDPOINTS
    assert "orders.api_order_item_construction_done_undo" not in OWN_ORDER_ENDPOINTS
    fl = _freelancer()
    own = _order(fl.match_name)
    _link(own, fl)
    other = _order("남의담당")
    browser = _client(app, fl)
    assert browser.get(f"/api/orders/{own}/construction/visit-items").status_code == 200
    assert browser.get(f"/api/orders/{other}/construction/visit-items").status_code == 404


# --------------------------------------------------------------------------- #
# 최종 검수 F-B2 · F-B4 · F-B5 — 잠근 뒤 판정 · 스위치 꺼짐
# --------------------------------------------------------------------------- #
def test_evidence_register_writes_on_top_of_the_latest_row(client):
    """[증빙 등록]은 잠근 최신 행 위에 쓴다 — 다른 창이 막 커밋한 시공 끝 표시 · history 를 지우지 않는다(F-B2)."""
    _login(client)
    oid = _make_order("CONSTRUCTION")
    att = _attachment(oid, "after1.jpg")
    db_session.remove()
    stale = db_session.query(Order).filter_by(id=oid).first()  # 낡은 값이 identity map 에 남는다
    newer = copy.deepcopy(stale.structured_data)
    newer[DONE_KEY] = {UID_A: {"date": FIRST_DAY, "source": "visit"}}
    newer["workflow"]["history"] = [{"stage": "CONSTRUCTION", "note": "부분 시공 끝 (화장대)"}]
    db_session.execute(update(Order).where(Order.id == oid).values(structured_data=newer)
                       .execution_options(synchronize_session=False))
    assert DONE_KEY not in stale.structured_data

    assert _evidence(client, oid, "after", att).status_code == 200
    sd = _fresh(oid).structured_data
    assert set(sd[DONE_KEY]) == {UID_A}
    assert sd["workflow"]["history"][-1]["note"] == "부분 시공 끝 (화장대)"
    assert sd["construction"]["evidence"]["after"] == [att]


def test_visit_fail_rechecks_under_lock_and_writes_nothing_when_closed(client, monkeypatch):
    """잠그기 전엔 열린 방문으로 보였어도 잠근 뒤 아니면 409 — 그사이 닫힘 · 단계 바뀜(F-B4)."""
    monkeypatch.setattr(visit_fail, "production_visit_fail_applies", lambda *a, **k: True)
    _login(client)
    closed = _make_order("PRODUCTION")  # 열린 방문 줄이 없다
    moved = _make_order("CONSTRUCTION")  # 단계가 시공으로 넘어갔다
    db_session.add(OrderConstructionAttempt(order_id=moved, status="IN_PROGRESS", is_current=True,
                                            evidence={"before": [], "after": []}))
    db_session.commit()
    for oid in (closed, moved):
        resp = client.post(f"/api/orders/{oid}/construction/fail", json={"reason": "site_issue"})
        assert resp.status_code == 409, oid
        assert resp.get_json()["code"] == "VISIT_NOT_OPEN"
        assert "construction_fail_history" not in _fresh(oid).structured_data
        assert _events(oid, "CONSTRUCTION_REWORKED") == 0
    assert _attempts(moved)[0].status == "IN_PROGRESS"


def test_undo_is_404_when_flag_off(client, monkeypatch):
    """스위치가 꺼지면 되돌리기 문도 없다(F-B5) — 표시는 그대로."""
    monkeypatch.setenv("FOMS_ITEM_CONSTRUCTION_DONE_ENABLED", "0")
    _login(client, team="CS")
    oid = _make_order("CONSTRUCTION", extra={DONE_KEY: {UID_A: {"date": FIRST_DAY, "source": "visit"}}})
    resp = client.post(f"/api/orders/{oid}/items/{UID_A}/construction-done/undo", json={"reason": "잘못 눌렀어요"})
    assert resp.status_code == 404 and resp.get_json()["code"] == "FEATURE_OFF"
    assert set(_fresh(oid).structured_data[DONE_KEY]) == {UID_A}
