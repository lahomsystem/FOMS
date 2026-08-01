"""FILE-LEGACY-BACKFILL-01 PostgreSQL 계약 테스트 (PGTEST-00 lane).

FILE-LEGACY-AUDIT-00 이 분류한 legacy :class:`~models.OrderAttachment` 의 ownership backfill
(:mod:`foms.services.files.legacy_attachment_backfill`)을 실 PostgreSQL 로 검증한다:

* **dry-run 기본**: approval(apply=True) 없이는 아무 것도 쓰지 않는다.
* **safe-only**: exact row 의 category 만 canonical purpose 로 정규화하고, order/key 는 이미
  canonical 이라 손대지 않는다.
* **ambiguous 자동 매핑 0**: ambiguous row 는 safe backfill 이 절대 건드리지 않고, 오직 사람이
  reason 을 적은 CSV 매핑을 통해서만, 그것도 공급값이 스스로 canonical 일 때만 적용된다.
* **coverage 100%**: safe-applied(exact→canonical) + ambiguous-quarantined = 전 row 계정.
* **idempotent·resume**: 재실행 0 row, 부분 적용 후 재실행은 남은 row 만.

``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가 skip(conftest). 커밋 파일에 비밀번호 0
(dev DSN 은 env). audit(FILE-LEGACY-AUDIT-00)·models·마이그레이션 무변경 — 기존 컬럼만 채운다.
"""
from __future__ import annotations

import pytest

from foms.services.files.legacy_attachment_audit import (
    LegacyAttachmentAudit,
    audit_legacy_attachments,
)
from foms.services.files.legacy_attachment_backfill import (
    NONCANONICAL_KEY,
    NOT_AMBIGUOUS,
    ManualMapping,
    ManualMappingError,
    MANUAL_CSV_HEADER,
    apply_manual_mappings,
    apply_safe_backfill,
    parse_manual_mappings,
    verify_coverage,
)
from models import Order, OrderAttachment


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _order(session) -> Order:
    """ERP 주문 1건 생성."""
    o = Order(
        received_date="2026-07-24", customer_name="홍길동", phone="010-0000-0000",
        address="서울", product="침대", is_erp_order=True, structured_data={"items": []},
    )
    session.add(o)
    session.flush()
    return o


def _attach(session, order, *, category, storage_key, thumbnail_key=None) -> OrderAttachment:
    a = OrderAttachment(
        order_id=order.id, filename="f.jpg", file_type="image", category=category,
        file_size=1, storage_key=storage_key, thumbnail_key=thumbnail_key,
    )
    session.add(a)
    session.flush()
    return a


def _canon_key(order, sub="measurement", name="a.jpg") -> str:
    return f"orders/{order.id}/{sub}/{name}"


# --------------------------------------------------------------------------- #
# dry-run 기본 (approval gate)
# --------------------------------------------------------------------------- #
def test_safe_dry_run_writes_nothing(pg_session):
    """apply 없이(dry-run) safe backfill 은 DB 를 쓰지 않고 계획만 센다."""
    order = _order(pg_session)
    a = _attach(pg_session, order, category="Measurement", storage_key=_canon_key(order))

    result = apply_safe_backfill(pg_session)  # apply=False 기본
    pg_session.expire_all()

    assert result.applied is False
    assert result.total_safe == 1
    assert result.category_normalized == 1        # 정규화될 예정(그러나 미적용)
    # DB 는 불변: 여전히 legacy casing.
    assert pg_session.get(OrderAttachment, a.id).category == "Measurement"


# --------------------------------------------------------------------------- #
# safe-only 적용 + ambiguous 자동 매핑 0
# --------------------------------------------------------------------------- #
def test_apply_normalizes_safe_only(pg_session):
    """apply=True 는 exact category 만 정규화하고 ambiguous 는 byte-불변(자동 매핑 0)."""
    order = _order(pg_session)
    safe = _attach(pg_session, order, category="DRAWING", storage_key=_canon_key(order, "drawing", "p.pdf"))
    canon = _attach(pg_session, order, category="measurement", storage_key=_canon_key(order))
    # ambiguous: 비정규 key(4 segment 미만).
    amb = _attach(pg_session, order, category="measurement", storage_key="legacy/uploads/x.jpg")

    result = apply_safe_backfill(pg_session, apply=True)
    pg_session.expire_all()

    assert result.applied is True
    assert result.total_safe == 2                 # safe, canon
    assert result.category_normalized == 1        # DRAWING → drawing
    assert result.already_canonical == 1          # measurement 는 이미 canonical
    assert result.ambiguous_skipped == 1

    assert pg_session.get(OrderAttachment, safe.id).category == "drawing"     # 정규화됨
    assert pg_session.get(OrderAttachment, canon.id).category == "measurement"
    # ambiguous row: category·key 모두 불변(자동 매핑 0).
    amb_row = pg_session.get(OrderAttachment, amb.id)
    assert amb_row.category == "measurement"
    assert amb_row.storage_key == "legacy/uploads/x.jpg"


def test_safe_apply_does_not_touch_order_or_key(pg_session):
    """exact row 의 order_id/storage_key 는 이미 canonical 이라 정규화가 손대지 않는다."""
    order = _order(pg_session)
    a = _attach(pg_session, order, category="AS", storage_key=_canon_key(order, "as", "r.jpg"))
    original_key = a.storage_key

    apply_safe_backfill(pg_session, apply=True)
    pg_session.expire_all()
    row = pg_session.get(OrderAttachment, a.id)
    assert row.category == "as"                    # 정규화만
    assert row.order_id == order.id                # 불변
    assert row.storage_key == original_key         # 불변


# --------------------------------------------------------------------------- #
# idempotent · resume
# --------------------------------------------------------------------------- #
def test_safe_backfill_idempotent(pg_session):
    """재실행 시 이미 canonical 인 row 는 다시 쓰지 않는다(0 row)."""
    order = _order(pg_session)
    _attach(pg_session, order, category="Drawing", storage_key=_canon_key(order, "drawing", "p.jpg"))

    first = apply_safe_backfill(pg_session, apply=True)
    assert first.category_normalized == 1
    pg_session.expire_all()

    second = apply_safe_backfill(pg_session, apply=True)
    assert second.category_normalized == 0         # 멱등: 남은 정규화 대상 0


def test_safe_backfill_resume_partial(pg_session):
    """부분 audit 로 일부만 적용 후, 전체 재실행이 남은 row 만 정규화한다(자원 idempotency)."""
    order = _order(pg_session)
    a0 = _attach(pg_session, order, category="Measurement", storage_key=_canon_key(order, "measurement", "0.jpg"))
    a1 = _attach(pg_session, order, category="Measurement", storage_key=_canon_key(order, "measurement", "1.jpg"))

    # 첫 배치가 a0 만 처리(부분 진행)했다고 가정: exact 부분집합만 담은 audit 를 넘긴다.
    full = audit_legacy_attachments(pg_session)
    partial_exact = [m for m in full.exact if m.attachment_id == a0.id]
    partial = LegacyAttachmentAudit(exact=partial_exact, ambiguous=[], total=len(partial_exact))
    apply_safe_backfill(pg_session, audit=partial, apply=True)
    pg_session.expire_all()
    assert pg_session.get(OrderAttachment, a0.id).category == "measurement"   # 처리됨
    assert pg_session.get(OrderAttachment, a1.id).category == "Measurement"   # 아직

    # 전체 재실행 → 남은 a1 만.
    result = apply_safe_backfill(pg_session, apply=True)
    pg_session.expire_all()
    assert result.category_normalized == 1
    assert pg_session.get(OrderAttachment, a1.id).category == "measurement"


# --------------------------------------------------------------------------- #
# 수동 CSV: reason 필수 · ambiguous 만 · 공급값 canonical 검증
# --------------------------------------------------------------------------- #
def test_manual_csv_requires_reason():
    """reason 빈 값의 수동 매핑 CSV 는 파싱 단계에서 거부된다(사람 결정 필수)."""
    header = ",".join(MANUAL_CSV_HEADER)
    csv_text = header + "\n1,5,measurement,orders/5/measurement/x.jpg,,\n"  # reason 비어 있음
    with pytest.raises(ManualMappingError):
        parse_manual_mappings(csv_text)


def test_manual_mapping_applies_only_via_reason(pg_session):
    """ambiguous row 는 사람이 reason 을 적은 CSV 매핑으로만, dry-run 없이 apply 시에만 복구된다."""
    order = _order(pg_session)
    amb = _attach(pg_session, order, category="measurement", storage_key="legacy/uploads/x.jpg")

    # 사람이 legacy 경로를 canonical 로 매핑(reason 포함).
    header = ",".join(MANUAL_CSV_HEADER)
    canon = _canon_key(order, "measurement", "x.jpg")
    csv_text = f"{header}\n{amb.id},{order.id},measurement,{canon},,verified from legacy path\n"
    mappings = parse_manual_mappings(csv_text)

    # dry-run: 아무 것도 쓰지 않는다.
    dry = apply_manual_mappings(pg_session, mappings)
    pg_session.expire_all()
    assert dry.apply is False and dry.applied == 1
    assert pg_session.get(OrderAttachment, amb.id).storage_key == "legacy/uploads/x.jpg"

    # apply: ambiguous 가 복구되어 재감사 시 exact 로 분류.
    done = apply_manual_mappings(pg_session, mappings, apply=True)
    pg_session.expire_all()
    assert done.apply is True and done.applied == 1 and done.rejected == []
    assert pg_session.get(OrderAttachment, amb.id).storage_key == canon
    reaudit = audit_legacy_attachments(pg_session)
    assert amb.id in {m.attachment_id for m in reaudit.exact}
    assert amb.id not in {a.attachment_id for a in reaudit.ambiguous}


def test_manual_rejects_non_ambiguous_target(pg_session):
    """exact row(또는 미존재) 를 겨냥한 수동 매핑은 적용되지 않는다(clobber 차단)."""
    order = _order(pg_session)
    exact = _attach(pg_session, order, category="Measurement", storage_key=_canon_key(order))

    # exact id 를 겨냥 — 공급값이 canonical 이어도 대상이 ambiguous 가 아니므로 거부.
    mapping = ManualMapping(
        attachment_id=exact.id, order_id=order.id, purpose="measurement",
        object_key=_canon_key(order), thumbnail_key=None, reason="mistaken target",
    )
    result = apply_manual_mappings(pg_session, [mapping], apply=True)
    pg_session.expire_all()
    assert result.applied == 0
    assert [r.reason_code for r in result.rejected] == [NOT_AMBIGUOUS]


def test_manual_rejects_noncanonical_supply(pg_session):
    """사람이 비정규 key 를 공급하면 거부한다(typo 로 비정규값 쓰기 차단)."""
    order = _order(pg_session)
    amb = _attach(pg_session, order, category="measurement", storage_key="legacy/uploads/x.jpg")

    mapping = ManualMapping(
        attachment_id=amb.id, order_id=order.id, purpose="measurement",
        object_key="still/legacy/x.jpg", thumbnail_key=None, reason="bad supply",
    )
    result = apply_manual_mappings(pg_session, [mapping], apply=True)
    pg_session.expire_all()
    assert result.applied == 0
    assert [r.reason_code for r in result.rejected] == [NONCANONICAL_KEY]
    assert pg_session.get(OrderAttachment, amb.id).storage_key == "legacy/uploads/x.jpg"


# --------------------------------------------------------------------------- #
# coverage 100% (safe-applied + ambiguous-quarantined)
# --------------------------------------------------------------------------- #
def test_coverage_100_percent(pg_session):
    """safe 정규화 + 수동 복구 후 모든 row 가 계정된다(quarantined ambiguous 포함)."""
    order = _order(pg_session)
    _attach(pg_session, order, category="Measurement", storage_key=_canon_key(order, "measurement", "1.jpg"))   # safe 정규화
    _attach(pg_session, order, category="drawing", storage_key=_canon_key(order, "drawing", "2.pdf"))           # 이미 canonical
    repairable = _attach(pg_session, order, category="measurement", storage_key="legacy/3.jpg")                  # ambiguous→복구
    # ambiguous(purpose mismatch): key 는 drawing, category 는 measurement → quarantine 유지.
    _attach(pg_session, order, category="measurement", storage_key=_canon_key(order, "drawing", "4.jpg"))

    apply_safe_backfill(pg_session, apply=True)
    pg_session.expire_all()

    canon = _canon_key(order, "measurement", "3.jpg")
    mapping = ManualMapping(
        attachment_id=repairable.id, order_id=order.id, purpose="measurement",
        object_key=canon, thumbnail_key=None, reason="legacy path resolved",
    )
    apply_manual_mappings(pg_session, [mapping], apply=True)
    pg_session.expire_all()

    report = verify_coverage(pg_session)
    assert report.total == 4
    assert report.pending_normalization == 0       # 모든 safe row canonical
    assert report.exact == 3                        # 정규화 + 이미-canon + 복구
    assert report.ambiguous == 1                    # purpose-mismatch quarantine
    assert report.exact + report.ambiguous == report.total
    assert report.coverage_complete is True         # quarantined 도 계정 → 100%
