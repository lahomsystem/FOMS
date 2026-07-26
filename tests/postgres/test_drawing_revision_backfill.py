"""DRAWING-REVISION-BACKFILL-00 PostgreSQL 계약 테스트 (PGTEST-00 lane).

도면 개정 UUID registry(:class:`~models.DrawingRevision` /
:class:`~models.DrawingRevisionRequest`)와 flat→revision/request 매핑 backfill 을 실
PostgreSQL 로 검증한다:

* flat ``drawing_transfer_history``(TRANSFER/REQUEST_REVISION/CONFIRM_RECEIPT)·
  ``blueprint.customer_confirmed`` → revision/request safe map(유실 0·flat/attachment 잔존).
* current/request/receipt/customer 포인터 정확(각 0/1)·missing/duplicate open request 0.
* ambiguous(malformed·no-transfer·status↔요청 불일치·중복 열림)는 자동 매핑 0 → 수동 CSV.
* in-flight drawing current **100% 매핑**(coverage)·backfill 멱등·resume·enforcement 게이트.
* UUID DB-global unique·order binding·current/receipt/customer/open partial-unique·legacy 멱등.
* **timestamp/file 추정으로 상태 활성 금지·attachment 삭제 0**(flat structured_data 무변경).

``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가 skip(conftest). 커밋 파일에 비밀번호 0
(dev DSN 은 env). 이 packet 은 아직 route/전이에 배선되지 않았다(경계 — 개정 발급/전달
활성화는 하류 STATE-DRAWING-01) — 이 테스트가 하류가 의존할 계약을 정본으로 고정한다.
"""
from __future__ import annotations

import copy
import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from foms.services.orders.audit_drawing_revisions import (
    DUPLICATE_OPEN,
    MALFORMED,
    NO_TRANSFER,
    STATUS_MISMATCH,
    AmbiguousDrawing,
    DrawingRevisionAudit,
    DrawingRevisionPlan,
    audit_drawing_revisions,
    classify_order,
    to_manual_csv,
)
from foms.services.orders.backfill_drawing_revisions import (
    apply_safe_backfill,
    can_enforce,
)
from models import DrawingRevision, DrawingRevisionRequest, Order, OrderAttachment


# --------------------------------------------------------------------------- #
# helpers — flat drawing 이력 구성
# --------------------------------------------------------------------------- #
def _files(*keys):
    """전달/요청 파일 스냅샷(key + name)."""
    return [{"key": k, "name": k.split("/")[-1]} for k in keys]


def _transfer(seq, files, note="전달"):
    """TRANSFER entry(도면 전달) — transferred_at 사용."""
    return {
        "action": "TRANSFER",
        "transferred_at": f"2026-07-2{seq} 01:00:00",
        "by_user_id": 10,
        "by_user_name": "도면기사",
        "note": note,
        "files": files,
        "files_count": len(files),
    }


def _request(seq, keys=None, files=None, note="수정요청"):
    """REQUEST_REVISION entry(수정 요청) — at 사용."""
    return {
        "action": "REQUEST_REVISION",
        "at": f"2026-07-2{seq} 02:00:00",
        "by_user_id": 20,
        "by_user_name": "영업담당",
        "note": note,
        "files": files or [],
        "target_drawing_keys": keys,
    }


def _receipt(seq, files=None):
    """CONFIRM_RECEIPT entry(수령 확인) — at 사용."""
    return {
        "action": "CONFIRM_RECEIPT",
        "at": f"2026-07-2{seq} 03:00:00",
        "by_user_id": 20,
        "by_user_name": "영업담당",
        "note": "도면 수령 확인",
        "files": files or [],
        "files_count": len(files or []),
    }


def _sd(drawing_status, history, *, customer_confirmed=False, confirmed_by="영업담당"):
    """drawing_status + drawing_transfer_history(+선택 blueprint.customer_confirmed)."""
    sd = {
        "workflow": {"stage": "DRAWING", "history": []},
        "drawing_status": drawing_status,
        "drawing_transfer_history": history,
    }
    if customer_confirmed:
        sd["blueprint"] = {
            "customer_confirmed": True,
            "confirmed_at": "2026-07-25 09:00:00",
            "confirmed_by": confirmed_by,
        }
    return sd


def _order(session, drawing_status, history, **kw) -> Order:
    """ERP 주문 1건 생성(structured_data = flat drawing 이력)."""
    o = Order(
        received_date="2026-07-24", customer_name="홍길동", phone="010-0000-0000",
        address="서울", product="가구", is_erp_order=True, status="DRAWING",
        structured_data=_sd(drawing_status, history, **kw),
    )
    session.add(o)
    session.flush()
    return o


def _attach(session, order_id, key, category="drawing") -> OrderAttachment:
    """도면 attachment 1건(삭제 금지 증명용)."""
    row = OrderAttachment(
        order_id=order_id, filename=key.split("/")[-1], file_type="image",
        category=category, storage_key=key, file_size=1,
    )
    session.add(row)
    session.flush()
    return row


# --------------------------------------------------------------------------- #
# 분류: SAFE (safe map — revision/request/receipt/customer)
# --------------------------------------------------------------------------- #
def test_single_transfer_is_safe_current_transferred(pg_session):
    """단일 TRANSFER·drawing_status TRANSFERRED → current revision 1개(TRANSFERRED)·요청 0."""
    order = _order(pg_session, "TRANSFERRED", [_transfer(1, _files("d/o1_r1.pdf"))])
    plan = classify_order(order)
    assert isinstance(plan, DrawingRevisionPlan)
    assert len(plan.revisions) == 1 and plan.requests == ()
    r = plan.revisions[0]
    assert r.revision_no == 1 and r.status == "TRANSFERRED"
    assert r.is_current and not r.is_receipt and not r.is_customer_confirmed
    assert r.transferred_at == "2026-07-21 01:00:00" and r.transferred_by == "도면기사"
    assert r.files == ({"key": "d/o1_r1.pdf", "name": "o1_r1.pdf"},)
    assert plan.has_current() is True


def test_transfer_request_is_safe_returned_open(pg_session):
    """TRANSFER + 수정요청·RETURNED → current revision RETURNED + 열린 요청 1(대상 rev1)."""
    order = _order(pg_session, "RETURNED", [
        _transfer(1, _files("d/r1.pdf")),
        _request(2, keys=["d/r1.pdf"], files=_files("d/ref.pdf")),
    ])
    plan = classify_order(order)
    assert isinstance(plan, DrawingRevisionPlan)
    assert plan.revisions[0].status == "RETURNED" and plan.revisions[0].is_current
    assert len(plan.requests) == 1
    req = plan.requests[0]
    assert req.status == "OPEN" and req.is_open is True
    assert req.target_revision_no == 1
    assert req.target_drawing_keys == ("d/r1.pdf",)
    assert req.files == ({"key": "d/ref.pdf", "name": "ref.pdf"},)


def test_transfer_receipt_is_safe_confirmed(pg_session):
    """TRANSFER + CONFIRM_RECEIPT·CONFIRMED → current revision CONFIRMED + receipt 플래그."""
    order = _order(pg_session, "CONFIRMED", [
        _transfer(1, _files("d/r1.pdf")),
        _receipt(2, files=_files("d/r1.pdf")),
    ])
    plan = classify_order(order)
    r = plan.revisions[0]
    assert r.status == "CONFIRMED" and r.is_current and r.is_receipt
    assert r.receipt_confirmed_at == "2026-07-22 03:00:00" and r.receipt_confirmed_by == "영업담당"
    assert not r.is_customer_confirmed


def test_customer_confirm_marks_receipt_revision(pg_session):
    """blueprint.customer_confirmed → receipt revision 이 customer-confirm 으로 표시된다."""
    order = _order(pg_session, "CONFIRMED", [
        _transfer(1, _files("d/r1.pdf")),
        _receipt(2),
    ], customer_confirmed=True)
    r = classify_order(order).revisions[0]
    assert r.is_customer_confirmed is True
    assert r.customer_confirmed_at == "2026-07-25 09:00:00"
    assert r.customer_confirmed_by == "영업담당"


def test_multi_transfer_supersedes_older(pg_session):
    """TRANSFER 2회 → 이전 revision SUPERSEDED, 마지막이 current."""
    order = _order(pg_session, "TRANSFERRED", [
        _transfer(1, _files("d/r1.pdf")),
        _transfer(2, _files("d/r2.pdf")),
    ])
    plan = classify_order(order)
    assert [r.revision_no for r in plan.revisions] == [1, 2]
    assert [r.status for r in plan.revisions] == ["SUPERSEDED", "TRANSFERRED"]
    assert [r.is_current for r in plan.revisions] == [False, True]
    assert sum(r.is_current for r in plan.revisions) == 1  # current 0/1


def test_full_cycle_request_resolved_by_retransfer(pg_session):
    """T1·수령·수정요청·T2(재전달) → rev1 receipt+SUPERSEDED, rev2 current, 요청 RESOLVED(대상 rev1)."""
    order = _order(pg_session, "TRANSFERRED", [
        _transfer(1, _files("d/r1.pdf")),
        _receipt(2),
        _request(3, keys=["d/r1.pdf"]),
        _transfer(4, _files("d/r2.pdf")),
    ])
    plan = classify_order(order)
    rev1, rev2 = plan.revisions
    assert rev1.revision_no == 1 and rev1.status == "SUPERSEDED" and rev1.is_receipt
    assert not rev1.is_current
    assert rev2.revision_no == 2 and rev2.status == "TRANSFERRED" and rev2.is_current
    assert not rev2.is_receipt
    assert len(plan.requests) == 1
    req = plan.requests[0]
    assert req.status == "RESOLVED" and req.is_open is False
    assert req.target_revision_no == 1  # 요청 시점 current 는 rev1


# --------------------------------------------------------------------------- #
# 분류: AMBIGUOUS (missing/duplicate open request·no-transfer·malformed)
# --------------------------------------------------------------------------- #
def test_returned_without_open_request_is_mismatch(pg_session):
    """RETURNED 인데 마지막 전달 뒤 열린 요청 0 → STATUS_MISMATCH(요청 누락)."""
    order = _order(pg_session, "RETURNED", [_transfer(1, _files("d/r1.pdf"))])
    amb = classify_order(order)
    assert isinstance(amb, AmbiguousDrawing) and amb.reason == STATUS_MISMATCH


def test_nonreturned_with_open_request_is_mismatch(pg_session):
    """열린 요청이 있는데 drawing_status 가 RETURNED 아님 → STATUS_MISMATCH."""
    order = _order(pg_session, "CONFIRMED", [
        _transfer(1, _files("d/r1.pdf")), _request(2),
    ])
    amb = classify_order(order)
    assert isinstance(amb, AmbiguousDrawing) and amb.reason == STATUS_MISMATCH


def test_duplicate_open_request_is_ambiguous(pg_session):
    """마지막 전달 뒤 열린 요청 복수 → 자동 선택 금지 → DUPLICATE_OPEN."""
    order = _order(pg_session, "RETURNED", [
        _transfer(1, _files("d/r1.pdf")), _request(2), _request(3),
    ])
    amb = classify_order(order)
    assert isinstance(amb, AmbiguousDrawing) and amb.reason == DUPLICATE_OPEN
    assert amb.open_request_count == 2


def test_active_without_transfer_is_ambiguous(pg_session):
    """drawing 활성(TRANSFERRED)인데 TRANSFER 이력 0 → NO_TRANSFER(추정 금지)."""
    order = _order(pg_session, "TRANSFERRED", [])
    amb = classify_order(order)
    assert isinstance(amb, AmbiguousDrawing) and amb.reason == NO_TRANSFER


def test_malformed_history_is_ambiguous(pg_session):
    """drawing_transfer_history 가 리스트 아님/entry 가 dict 아님 → MALFORMED."""
    bad_type = _order(pg_session, "TRANSFERRED", {"oops": 1})
    assert classify_order(bad_type).reason == MALFORMED
    bad_entry = _order(pg_session, "TRANSFERRED", ["not-a-dict"])
    assert classify_order(bad_entry).reason == MALFORMED


def test_no_drawing_activity_excluded(pg_session):
    """도면 활동 없음(TRANSFER 0 + drawing_status 비활성) → 대상 제외(None)."""
    pending = _order(pg_session, "PENDING", [])
    assert classify_order(pending) is None
    order = _order(pg_session, "RECEIVED", [])
    order.structured_data = {"workflow": {"stage": "RECEIVED"}}  # drawing 키 없음
    pg_session.flush()
    assert classify_order(order) is None


# --------------------------------------------------------------------------- #
# backfill: SAFE 만 발급 + flat/attachment 보존 + 자동 매핑 0
# --------------------------------------------------------------------------- #
def test_backfill_mints_and_preserves_flat_and_attachments(pg_session):
    """SAFE 주문에 revision/request 발급, flat structured_data·attachment 는 무변경(보존)."""
    order = _order(pg_session, "TRANSFERRED", [
        _transfer(1, _files("d/r1.pdf")),
        _receipt(2),
        _request(3),
        _transfer(4, _files("d/r2.pdf")),
    ], customer_confirmed=True)
    _attach(pg_session, order.id, "d/r1.pdf")
    _attach(pg_session, order.id, "d/r2.pdf")
    before = copy.deepcopy(order.structured_data)

    result = apply_safe_backfill(pg_session)
    pg_session.expire_all()

    assert result.revisions_minted == 2 and result.requests_minted == 1
    assert result.ambiguous_skipped == 0

    revs = (
        pg_session.query(DrawingRevision)
        .filter_by(order_id=order.id).order_by(DrawingRevision.revision_no).all()
    )
    assert [r.status for r in revs] == ["SUPERSEDED", "TRANSFERRED"]
    assert all(uuid.UUID(r.id) for r in revs)

    # flat structured_data 는 byte-identical 로 남는다(삭제/재작성·상태 활성 추정 0).
    reloaded = pg_session.get(Order, order.id).structured_data
    assert reloaded == before
    # attachment 는 한 건도 삭제되지 않는다.
    assert pg_session.query(OrderAttachment).filter_by(order_id=order.id).count() == 2


def test_pointers_current_receipt_customer_request(pg_session):
    """full cycle → current/receipt/customer/open 포인터가 각각 정확히 1개, 링크 정합."""
    order = _order(pg_session, "RETURNED", [
        _transfer(1, _files("d/r1.pdf")),
        _receipt(2),
        _request(3, keys=["d/r1.pdf"]),
    ], customer_confirmed=True)
    apply_safe_backfill(pg_session)
    pg_session.expire_all()

    q = pg_session.query(DrawingRevision).filter_by(order_id=order.id)
    current = q.filter_by(is_current=True).one()
    receipt = q.filter_by(is_receipt=True).one()
    customer = q.filter_by(is_customer_confirmed=True).one()
    assert current.revision_no == receipt.revision_no == customer.revision_no == 1
    assert current.status == "RETURNED"  # 열린 요청이 있는 current

    req = pg_session.query(DrawingRevisionRequest).filter_by(order_id=order.id, is_open=True).one()
    assert req.revision_id == current.id  # 열린 요청은 current revision 을 가리킨다


def test_backfill_skips_ambiguous_no_auto_map(pg_session):
    """ambiguous 주문은 revision/request 를 발급하지 않는다(자동 매핑 0)."""
    _order(pg_session, "RETURNED", [_transfer(1, _files("d/r1.pdf"))])   # STATUS_MISMATCH
    _order(pg_session, "TRANSFERRED", [])                                # NO_TRANSFER

    result = apply_safe_backfill(pg_session)
    pg_session.expire_all()

    assert result.revisions_minted == 0 and result.requests_minted == 0
    assert result.ambiguous_skipped == 2
    assert pg_session.query(DrawingRevision).count() == 0
    assert pg_session.query(DrawingRevisionRequest).count() == 0


def test_manual_csv_lists_ambiguous_only(pg_session):
    """ambiguous 는 CSV 로 내보내진다(decision=MANUAL·approved 공란·자동 매핑 0)."""
    order = _order(pg_session, "RETURNED", [
        _transfer(1, _files("d/r1.pdf")), _request(2), _request(3),
    ])
    csv_text = to_manual_csv(audit_drawing_revisions(pg_session))
    assert ("order_id,drawing_status,transfer_count,open_request_count,"
            "legacy_history_json,decision,reason,approved_by_user_id") in csv_text
    assert f"{order.id}," in csv_text
    assert f",MANUAL,{DUPLICATE_OPEN}," in csv_text


# --------------------------------------------------------------------------- #
# missing/duplicate open request 0 (backfill 후 불변식)
# --------------------------------------------------------------------------- #
def test_open_request_invariant_after_backfill(pg_session):
    """SAFE 발급 후: RETURNED 주문은 열린 요청 정확히 1개, 그 외 0개(missing/duplicate 0)."""
    returned = _order(pg_session, "RETURNED", [_transfer(1, _files("d/a.pdf")), _request(2)])
    confirmed = _order(pg_session, "CONFIRMED", [_transfer(1, _files("d/b.pdf")), _receipt(2)])
    apply_safe_backfill(pg_session)
    pg_session.expire_all()

    assert pg_session.query(DrawingRevisionRequest).filter_by(
        order_id=returned.id, is_open=True).count() == 1
    assert pg_session.query(DrawingRevisionRequest).filter_by(
        order_id=confirmed.id, is_open=True).count() == 0


# --------------------------------------------------------------------------- #
# in-flight drawing current 100% 매핑 (coverage)
# --------------------------------------------------------------------------- #
def test_in_flight_maps_to_current_100pct(pg_session):
    """모든 in-flight drawing 주문이 current revision 으로 100% 매핑된다."""
    ids = [
        _order(pg_session, "TRANSFERRED", [_transfer(1, _files(f"d/{i}.pdf"))]).id
        for i in range(3)
    ]
    audit = audit_drawing_revisions(pg_session)
    assert audit.in_flight_ids == set(ids)
    assert audit.covers_all_in_flight() is True

    apply_safe_backfill(pg_session, audit=audit)
    pg_session.expire_all()
    for oid in ids:
        cur = pg_session.query(DrawingRevision).filter_by(order_id=oid, is_current=True).one()
        assert cur.status == "TRANSFERRED"


def test_coverage_incomplete_when_in_flight_ambiguous(pg_session):
    """in-flight 인데 ambiguous(RETURNED 요청 누락)면 coverage < 100%."""
    _order(pg_session, "TRANSFERRED", [_transfer(1, _files("d/ok.pdf"))])   # safe in-flight
    _order(pg_session, "RETURNED", [_transfer(1, _files("d/bad.pdf"))])     # ambiguous in-flight
    audit = audit_drawing_revisions(pg_session)
    assert len(audit.in_flight_ids) == 2
    assert audit.covers_all_in_flight() is False


# --------------------------------------------------------------------------- #
# 멱등 / resume
# --------------------------------------------------------------------------- #
def test_backfill_is_idempotent(pg_session):
    """재실행 시 이미 발급된 (order_id, legacy_seq) revision/request 는 다시 발급하지 않는다."""
    _order(pg_session, "RETURNED", [_transfer(1, _files("d/r1.pdf")), _request(2)])
    first = apply_safe_backfill(pg_session)
    assert first.revisions_minted == 1 and first.requests_minted == 1

    pg_session.expire_all()
    second = apply_safe_backfill(pg_session)
    assert second.revisions_minted == 0 and second.requests_minted == 0
    assert second.already_present == 2
    assert pg_session.query(DrawingRevision).count() == 1
    assert pg_session.query(DrawingRevisionRequest).count() == 1


def test_backfill_resumes_after_partial_orders(pg_session):
    """부분 적용(한 주문만) 후 재실행이 남은 주문을 이어서 발급한다(중복 0)."""
    o1 = _order(pg_session, "TRANSFERRED", [_transfer(1, _files("d/a.pdf"))])
    o2 = _order(pg_session, "TRANSFERRED", [_transfer(1, _files("d/b.pdf"))])

    plan1 = classify_order(pg_session.get(Order, o1.id))
    partial = DrawingRevisionAudit(safe=(plan1,), ambiguous=(), in_flight_ids=frozenset({o1.id}))
    apply_safe_backfill(pg_session, audit=partial)
    pg_session.expire_all()
    assert pg_session.query(DrawingRevision).filter_by(order_id=o1.id).count() == 1
    assert pg_session.query(DrawingRevision).filter_by(order_id=o2.id).count() == 0

    result = apply_safe_backfill(pg_session)
    pg_session.expire_all()
    assert result.revisions_minted == 1        # o2 만 신규
    assert result.already_present == 1          # o1 revision 은 이미 있음
    assert pg_session.query(DrawingRevision).filter_by(order_id=o2.id).count() == 1


def test_resume_relinks_request_to_existing_revision(pg_session):
    """revision 은 있고 request 만 없는 상태에서 재실행 시 기존 revision UUID 로 링크된다."""
    order = _order(pg_session, "RETURNED", [_transfer(1, _files("d/r1.pdf")), _request(2)])
    apply_safe_backfill(pg_session)
    pg_session.expire_all()
    rev = pg_session.query(DrawingRevision).filter_by(order_id=order.id).one()

    # request row 만 지워 "revision 존재·request 미발급" 부분상태를 만든다.
    pg_session.query(DrawingRevisionRequest).filter_by(order_id=order.id).delete()
    pg_session.flush()

    result = apply_safe_backfill(pg_session)
    pg_session.expire_all()
    assert result.revisions_minted == 0 and result.requests_minted == 1
    req = pg_session.query(DrawingRevisionRequest).filter_by(order_id=order.id).one()
    assert req.revision_id == rev.id  # 재실행이 기존 revision 을 정확히 링크


# --------------------------------------------------------------------------- #
# enforcement 게이트
# --------------------------------------------------------------------------- #
def test_enforcement_gate_blocks_with_ambiguous(pg_session):
    """ambiguous 가 있으면 enforcement 게이트가 닫힌다."""
    _order(pg_session, "TRANSFERRED", [_transfer(1, _files("d/a.pdf"))])
    _order(pg_session, "RETURNED", [_transfer(1, _files("d/b.pdf"))])   # ambiguous
    apply_safe_backfill(pg_session)
    pg_session.expire_all()
    assert can_enforce(pg_session) is False


def test_enforcement_gate_allows_when_clean(pg_session):
    """ambiguous 0 + 모든 in-flight current 100% 면 enforcement 가능."""
    _order(pg_session, "TRANSFERRED", [_transfer(1, _files("d/a.pdf"))])
    _order(pg_session, "PENDING", [])   # 도면 활동 없음: in-flight 아님
    apply_safe_backfill(pg_session)
    pg_session.expire_all()
    assert can_enforce(pg_session) is True


def test_enforcement_gate_blocks_before_backfill(pg_session):
    """in-flight 주문이 있는데 revision 미발급이면(backfill 전) 게이트가 닫힌다."""
    _order(pg_session, "TRANSFERRED", [_transfer(1, _files("d/a.pdf"))])
    assert can_enforce(pg_session) is False


# --------------------------------------------------------------------------- #
# DB 제약: partial-unique 포인터 · legacy 멱등 · UUID unique
# --------------------------------------------------------------------------- #
def _insert_rev(session, order_id, revno, *, is_current=False, is_receipt=False,
                is_customer_confirmed=False, legacy_seq=None, status="SUPERSEDED"):
    """raw insert 한 건(제약 직격용)."""
    session.execute(DrawingRevision.__table__.insert().values(
        id=str(uuid.uuid4()), order_id=order_id, status=status, revision_no=revno,
        is_current=is_current, is_receipt=is_receipt,
        is_customer_confirmed=is_customer_confirmed, legacy_seq=legacy_seq,
    ))


def test_current_revision_partial_unique(pg_session):
    """한 주문 current revision 최대 1개 — 2번째 current 는 거부, 이력은 허용."""
    order = _order(pg_session, "TRANSFERRED", [_transfer(1, _files("d/r1.pdf"))])
    apply_safe_backfill(pg_session)
    pg_session.expire_all()
    with pytest.raises(IntegrityError):
        with pg_session.begin_nested():
            _insert_rev(pg_session, order.id, 99, is_current=True, status="TRANSFERRED")
    with pg_session.begin_nested():
        _insert_rev(pg_session, order.id, 98, is_current=False)  # 이력은 허용
    assert pg_session.query(DrawingRevision).filter_by(order_id=order.id).count() == 2


def test_receipt_and_customer_partial_unique(pg_session):
    """한 주문 receipt/customer revision 은 각각 최대 1개(partial unique)."""
    order = _order(pg_session, "CONFIRMED", [_transfer(1, _files("d/r1.pdf")), _receipt(2)],
                   customer_confirmed=True)
    apply_safe_backfill(pg_session)
    pg_session.expire_all()
    with pytest.raises(IntegrityError):
        with pg_session.begin_nested():
            _insert_rev(pg_session, order.id, 90, is_receipt=True)
    with pytest.raises(IntegrityError):
        with pg_session.begin_nested():
            _insert_rev(pg_session, order.id, 91, is_customer_confirmed=True)


def test_open_request_partial_unique(pg_session):
    """한 주문 열린 요청 최대 1개 — 2번째 open request 는 거부(duplicate open 0 강제)."""
    order = _order(pg_session, "RETURNED", [_transfer(1, _files("d/r1.pdf")), _request(2)])
    apply_safe_backfill(pg_session)
    pg_session.expire_all()
    with pytest.raises(IntegrityError):
        with pg_session.begin_nested():
            pg_session.execute(DrawingRevisionRequest.__table__.insert().values(
                id=str(uuid.uuid4()), order_id=order.id, status="OPEN",
                is_open=True, legacy_seq=99,
            ))


def test_legacy_seq_partial_unique(pg_session):
    """한 주문의 한 legacy_seq 에 revision 은 최대 1개(중복 발급 방지·backfill 멱등)."""
    order = _order(pg_session, "TRANSFERRED", [_transfer(1, _files("d/r1.pdf"))])
    apply_safe_backfill(pg_session)
    pg_session.expire_all()
    with pytest.raises(IntegrityError):
        with pg_session.begin_nested():
            _insert_rev(pg_session, order.id, 5, legacy_seq=0)  # 같은 (order_id, legacy_seq=0)


def test_uuid_pk_global_unique(pg_session):
    """같은 UUID 재삽입은 PK 위반(DB-global unique)."""
    order = _order(pg_session, "TRANSFERRED", [_transfer(1, _files("d/r1.pdf"))])
    apply_safe_backfill(pg_session)
    pg_session.expire_all()
    existing = pg_session.query(DrawingRevision).filter_by(order_id=order.id).one()
    with pytest.raises(IntegrityError):
        with pg_session.begin_nested():
            pg_session.execute(DrawingRevision.__table__.insert().values(
                id=existing.id, order_id=order.id, status="SUPERSEDED", revision_no=2,
            ))
