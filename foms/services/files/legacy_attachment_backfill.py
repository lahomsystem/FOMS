"""FILE-LEGACY-BACKFILL-01 — audited legacy attachment ownership backfill.

FILE-LEGACY-AUDIT-00(:mod:`foms.services.files.legacy_attachment_audit`)이 분류한 legacy
:class:`~models.OrderAttachment` 의 **ownership(order/purpose/canonical key)** 을 적용한다.
audit 이 ``exact`` 로 분류한 **safe row 만** 정규화하고, ``ambiguous`` 는 **절대 자동 매핑하지
않는다** — 사람이 CSV 에 resolved (order/purpose/key) + **reason 을 직접 적은 경우에만** 적용한다.

핵심 계약(SSOT §5.2 FILE-LEGACY-BACKFILL-01):

* **safe-only**: audit ``exact`` row 는 order 확정·key 정규(``validate_upload_key`` 통과)이므로
  order_id/storage_key 는 이미 canonical 이다. 정규화 대상은 **category(purpose) 컬럼**뿐이며
  (legacy casing/whitespace → canonical), audit 이 확정한 ``purpose`` 로 맞춘다.
* **ambiguous 자동 매핑 0**: ambiguous row 는 이 도구가 절대 쓰지 않는다. 오직
  :func:`apply_manual_mappings` 를 통해 사람이 reason 과 함께 결정한 매핑만, 그것도 대상이
  ambiguous 집합에 있고 공급값이 스스로 canonical 일 때만 적용한다.
* **dry-run 기본**: ``apply=False`` 면 아무 것도 쓰지 않고 계획만 센다. 쓰기는 ``apply=True``
  (approval gate)에서만.
* **coverage 100%**: 모든 audited row 는 safe-applied(exact→canonical) 또는
  ambiguous-quarantined(reason 보유) 로 계정된다. :func:`verify_coverage` 로 증명.
* **idempotent·resume**: 값이 다른 row 만 UPDATE 하므로 재실행은 0 row 를 건드리고, 부분 적용
  후 재실행은 남은 row 만 이어서 정규화한다(자원 idempotency).

ponytail: 형제 ``backfill_order_item_identities.py`` 와 동일 **lite 패턴** — 이 backfill 은
비파괴(category casing 정규화 + 사람이 검토한 repair)이므로 암호화 run state machine
(``runs.py`` lease/checkpoint/OPS-APPROVAL)을 끌어오지 않는다. **무마이그레이션**: 기존
OrderAttachment 컬럼(order_id/category/storage_key/thumbnail_key)만 채운다.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from foms.api.files.common import ATTACHMENT_CATEGORIES, normalize_attachment_category
from foms.services.common.table_version_counter import mark_tables_dirty
from foms.services.files.legacy_attachment_audit import (
    LegacyAttachmentAudit,
    audit_legacy_attachments,
)
from foms.services.files.upload_authz import validate_upload_key
from models import Order, OrderAttachment

#: 사람이 채우는 수동 매핑 CSV 헤더(ambiguous repair 용). reason 은 필수.
MANUAL_CSV_HEADER = (
    "attachment_id",
    "order_id",
    "purpose",
    "object_key",
    "thumbnail_key",
    "reason",
)

# 수동 매핑 거부 사유 코드.
NOT_AMBIGUOUS = "NOT_AMBIGUOUS"          # 대상이 audit ambiguous 집합에 없음(exact/미존재 clobber 차단)
ORDER_MISSING = "ORDER_MISSING"          # 공급 order_id 가 실재하지 않음
PURPOSE_INVALID = "PURPOSE_INVALID"      # 공급 purpose 가 유효 category 아님
NONCANONICAL_KEY = "NONCANONICAL_KEY"    # 공급 key 가 공급 order 기준 canonical 아님
PURPOSE_MISMATCH = "PURPOSE_MISMATCH"    # 공급 key 파생 category != 공급 purpose

# in_() 파라미터 폭발을 막는 청크 크기.
# ponytail: 단순 상수. 정규화는 자원 idempotent 라 청크 경계에서 재개해도 안전(재실행=남은 row만).
_CHUNK = 5000


@dataclass(frozen=True)
class SafeBackfillResult:
    """safe(exact) backfill 결과.

    Attributes:
        total_safe: audit 가 exact 로 분류한 row 수.
        category_normalized: category 가 canonical purpose 로 바뀐(또는 dry-run 시 바뀔) row 수.
        already_canonical: 이미 canonical 이라 손대지 않은 safe row 수.
        ambiguous_skipped: 손대지 않은 ambiguous row 수(자동 매핑 0 증거).
        applied: True=실제 쓰기, False=dry-run(무쓰기).
    """

    total_safe: int
    category_normalized: int
    already_canonical: int
    ambiguous_skipped: int
    applied: bool


@dataclass(frozen=True)
class ManualMapping:
    """사람이 결정한 ambiguous repair 1건(reason 필수).

    Attributes:
        attachment_id: 대상 OrderAttachment.id(ambiguous 여야 함).
        order_id: resolved 대상 order id.
        purpose: resolved 첨부 category(measurement/drawing/construction/as).
        object_key: resolved canonical storage key.
        thumbnail_key: resolved 썸네일 key(없으면 None).
        reason: 사람이 적은 결정 사유(빈 값 금지 — approval 증거).
    """

    attachment_id: int
    order_id: int
    purpose: str
    object_key: str
    thumbnail_key: Optional[str]
    reason: str


@dataclass(frozen=True)
class RejectedMapping:
    """검증 실패로 적용하지 않은 수동 매핑 1건."""

    attachment_id: Any
    reason_code: str


@dataclass(frozen=True)
class ManualResult:
    """수동 매핑 적용 결과.

    Attributes:
        applied: 적용한(또는 dry-run 시 적용될) 유효 매핑 수.
        rejected: 검증 실패로 건너뛴 매핑 목록(사유 코드 포함).
        apply: True=실제 쓰기, False=dry-run.
    """

    applied: int
    rejected: List[RejectedMapping] = field(default_factory=list)
    apply: bool = False


@dataclass(frozen=True)
class CoverageReport:
    """coverage 검증 결과(safe-applied + ambiguous-quarantined = 100%).

    Attributes:
        total: 전체 audited row 수.
        exact: 현재 exact(safe) 분류 row 수.
        ambiguous: 현재 ambiguous(quarantine) 분류 row 수.
        pending_normalization: 아직 category 가 canonical 이 아닌 exact row 수(0 이어야 완료).
        coverage_complete: pending_normalization==0 이고 exact+ambiguous==total 이면 True.
    """

    total: int
    exact: int
    ambiguous: int
    pending_normalization: int
    coverage_complete: bool


def _chunks(items: List[Any], size: int = _CHUNK) -> Iterable[List[Any]]:
    """리스트를 size 단위로 쪼갠다(in_() 파라미터 폭발 방지)."""
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _safe_groups(audit: LegacyAttachmentAudit) -> Dict[str, List[int]]:
    """exact row 를 purpose 별 attachment_id 목록으로 묶는다(id None 은 제외)."""
    groups: Dict[str, List[int]] = {}
    for row in audit.exact:
        if row.attachment_id is None:
            continue
        groups.setdefault(row.purpose, []).append(row.attachment_id)
    return groups


def _count_pending(session: Session, groups: Dict[str, List[int]]) -> int:
    """category 가 아직 canonical purpose 와 다른 exact row 수(정규화 대상)."""
    pending = 0
    for purpose, ids in groups.items():
        for chunk in _chunks(ids):
            pending += (
                session.query(OrderAttachment.id)
                .filter(
                    OrderAttachment.id.in_(chunk),
                    OrderAttachment.category != purpose,
                )
                .count()
            )
    return pending


def apply_safe_backfill(
    session: Session,
    audit: Optional[LegacyAttachmentAudit] = None,
    *,
    apply: bool = False,
) -> SafeBackfillResult:
    """exact(safe) row 의 category 를 canonical purpose 로 정규화한다(dry-run 기본·멱등).

    exact row 는 order/key 가 이미 canonical 이므로 order_id/storage_key 는 손대지 않는다(no-op).
    유일한 정규화 대상은 category 컬럼(legacy casing/whitespace → canonical purpose)이다.
    ``category != purpose`` 인 row 만 UPDATE 하므로 재실행은 0 row(멱등), 부분 적용 후 재실행은
    남은 row 만 이어서 처리한다(자원 idempotency = resume). **ambiguous 는 절대 손대지 않는다.**
    커밋은 호출자 몫.

    Args:
        session: DB 세션.
        audit: 미리 계산한 audit(없으면 :func:`audit_legacy_attachments` 호출). 부분 배치는
            exact 부분집합만 담은 audit 를 넘겨 resume 한다.
        apply: False(기본)=dry-run(무쓰기, 계획만 카운트). True=실제 UPDATE(approval gate).

    Returns:
        :class:`SafeBackfillResult`.
    """
    if audit is None:
        audit = audit_legacy_attachments(session)
    groups = _safe_groups(audit)
    total_safe = sum(len(ids) for ids in groups.values())

    if not apply:
        pending = _count_pending(session, groups)
        return SafeBackfillResult(
            total_safe=total_safe,
            category_normalized=pending,
            already_canonical=total_safe - pending,
            ambiguous_skipped=len(audit.ambiguous),
            applied=False,
        )

    normalized = 0
    for purpose, ids in groups.items():
        for chunk in _chunks(ids):
            normalized += (
                session.query(OrderAttachment)
                .filter(
                    OrderAttachment.id.in_(chunk),
                    OrderAttachment.category != purpose,
                )
                .update({OrderAttachment.category: purpose}, synchronize_session=False)
            )
    # HB-S1: query-level update() 는 세션 훅이 못 본다 — 커밋 시점 카운터 증가 대상 등재.
    if normalized:
        mark_tables_dirty(session, "order_attachments")
    session.flush()
    return SafeBackfillResult(
        total_safe=total_safe,
        category_normalized=normalized,
        already_canonical=total_safe - normalized,
        ambiguous_skipped=len(audit.ambiguous),
        applied=True,
    )


class ManualMappingError(ValueError):
    """수동 CSV 구조/필수값(특히 reason) 위반 — 파싱 단계에서 거부."""


def parse_manual_mappings(csv_text: str) -> List[ManualMapping]:
    """수동 매핑 CSV 를 파싱한다. **reason 빈 값은 파싱 거부**(사람 결정 필수).

    헤더는 :data:`MANUAL_CSV_HEADER` 를 요구한다. attachment_id/order_id 는 정수,
    purpose/object_key/reason 은 비어 있으면 안 된다. thumbnail_key 는 비어 있으면 None.

    Args:
        csv_text: CSV 텍스트(헤더 포함).

    Returns:
        :class:`ManualMapping` 목록.

    Raises:
        ManualMappingError: 헤더 불일치, 정수 파싱 실패, 필수값(특히 reason) 누락.
    """
    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames is None or tuple(reader.fieldnames) != MANUAL_CSV_HEADER:
        raise ManualMappingError(
            f"CSV header must be {MANUAL_CSV_HEADER}, got {reader.fieldnames}."
        )
    mappings: List[ManualMapping] = []
    for lineno, row in enumerate(reader, start=2):
        reason = (row.get("reason") or "").strip()
        if not reason:
            raise ManualMappingError(f"line {lineno}: reason is required (manual decision).")
        purpose = (row.get("purpose") or "").strip()
        object_key = (row.get("object_key") or "").strip()
        if not purpose or not object_key:
            raise ManualMappingError(f"line {lineno}: purpose and object_key are required.")
        try:
            attachment_id = int((row.get("attachment_id") or "").strip())
            order_id = int((row.get("order_id") or "").strip())
        except (TypeError, ValueError):
            raise ManualMappingError(f"line {lineno}: attachment_id/order_id must be integers.")
        thumb = (row.get("thumbnail_key") or "").strip()
        mappings.append(
            ManualMapping(
                attachment_id=attachment_id,
                order_id=order_id,
                purpose=purpose,
                object_key=object_key,
                thumbnail_key=thumb or None,
                reason=reason,
            )
        )
    return mappings


def _validate_manual(
    mapping: ManualMapping, ambiguous_ids: Set[Any], known_order_ids: Set[int]
) -> Optional[str]:
    """수동 매핑 1건 검증. 통과면 None, 실패면 사유 코드.

    대상이 ambiguous 집합에 있어야 하고(exact/미존재 clobber 차단), 공급 order/purpose/key 가
    **스스로 canonical** 이어야 한다(사람 typo 로 비정규값을 쓰지 않도록 trust-boundary 검증).
    """
    if mapping.attachment_id not in ambiguous_ids:
        return NOT_AMBIGUOUS
    if mapping.order_id not in known_order_ids:
        return ORDER_MISSING
    if normalize_attachment_category(mapping.purpose) not in ATTACHMENT_CATEGORIES:
        return PURPOSE_INVALID
    key_ok, key_category, _ = validate_upload_key(mapping.object_key, mapping.order_id)
    if not key_ok:
        return NONCANONICAL_KEY
    if key_category != mapping.purpose:
        return PURPOSE_MISMATCH
    return None


def apply_manual_mappings(
    session: Session,
    mappings: Iterable[ManualMapping],
    audit: Optional[LegacyAttachmentAudit] = None,
    *,
    apply: bool = False,
) -> ManualResult:
    """사람이 결정한 매핑만 ambiguous row 에 적용한다(dry-run 기본·검증·멱등).

    대상이 audit ambiguous 집합에 있고 공급 (order/purpose/key) 가 스스로 canonical 인 매핑만
    order_id/category/storage_key/thumbnail_key ownership 을 채운다. 그 외(exact 대상·미존재·
    비정규 공급값)는 적용하지 않고 :class:`RejectedMapping` 으로 보고한다(자동 매핑 0). 커밋은
    호출자 몫.

    Args:
        session: DB 세션.
        mappings: :func:`parse_manual_mappings` 산출 매핑들.
        audit: 미리 계산한 audit(없으면 내부 계산) — ambiguous 집합 판정용.
        apply: False(기본)=dry-run(무쓰기). True=실제 UPDATE.

    Returns:
        :class:`ManualResult`.
    """
    if audit is None:
        audit = audit_legacy_attachments(session)
    ambiguous_ids: Set[Any] = {a.attachment_id for a in audit.ambiguous}
    known_order_ids: Set[int] = {oid for (oid,) in session.query(Order.id).all()}

    applied = 0
    rejected: List[RejectedMapping] = []
    for mapping in mappings:
        code = _validate_manual(mapping, ambiguous_ids, known_order_ids)
        if code is not None:
            rejected.append(RejectedMapping(attachment_id=mapping.attachment_id, reason_code=code))
            continue
        applied += 1
        if apply:
            # HB-S1: query-level update() 는 세션 훅이 못 본다 — 커밋 시점 카운터 증가 대상 등재.
            mark_tables_dirty(session, "order_attachments")
            session.query(OrderAttachment).filter(OrderAttachment.id == mapping.attachment_id).update(
                {
                    OrderAttachment.order_id: mapping.order_id,
                    OrderAttachment.category: mapping.purpose,
                    OrderAttachment.storage_key: mapping.object_key,
                    OrderAttachment.thumbnail_key: mapping.thumbnail_key,
                },
                synchronize_session=False,
            )
    if apply:
        session.flush()
    return ManualResult(applied=applied, rejected=rejected, apply=apply)


def verify_coverage(
    session: Session, audit: Optional[LegacyAttachmentAudit] = None
) -> CoverageReport:
    """coverage 100% 를 검증한다(safe row 전부 canonical + ambiguous 전부 quarantined).

    fresh 재감사로 현재 상태를 본다. 모든 exact row 의 category 가 canonical(pending 0)이고
    exact+ambiguous==total 이면 ``coverage_complete=True``. ambiguous 가 남아 있어도
    (reason 을 가진 채) quarantined 로 계정되므로 coverage 는 완료로 본다.

    Args:
        session: DB 세션.
        audit: 미리 계산한 audit(없으면 fresh 재감사).

    Returns:
        :class:`CoverageReport`.
    """
    if audit is None:
        audit = audit_legacy_attachments(session)
    pending = _count_pending(session, _safe_groups(audit))
    exact = len(audit.exact)
    ambiguous = len(audit.ambiguous)
    accounted = (exact + ambiguous) == audit.total
    return CoverageReport(
        total=audit.total,
        exact=exact,
        ambiguous=ambiguous,
        pending_normalization=pending,
        coverage_complete=(pending == 0 and accounted),
    )
