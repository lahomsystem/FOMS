"""FILE-LEGACY-AUDIT-00 — legacy attachment/key read-only 감사(순수 분류).

:class:`~models.OrderAttachment` row 를 order/purpose(category)/object key 로 **정확 분류**한다.
UPLOAD-01(:mod:`foms.services.files.upload_authz`)의 canonical key 규약
``orders/{order_id}/{whitelist}[/...]`` 을 SSOT 로 재사용해, legacy key 가 정규형과 어긋나는
정도를 분류한다. **아무 것도 쓰지 않는다**(DB write·파일 삭제·R2 접근 0). 추정 backfill·정정은
하류 FILE-LEGACY-BACKFILL-01 몫이며 이 모듈은 감사(분류)만 한다.

분류 2종:

* **exact**: (1) order 확정(``order_id`` 존재 + 그 order row 가 실재) (2) key 정규
  (``validate_upload_key`` 통과 — key 의 order segment 가 row.order_id 와 정확 일치·whitelist·
  안전 segment) (3) purpose 확정(``category`` 가 유효 첨부 category 이며 key 파생 category 와 일치).
* **ambiguous(quarantine)**: 위 중 하나라도 불충족 — order 불명(``order_id`` None)·orphan(참조
  order 부재)·비정규 key·purpose 추정 불가/불일치. 사유 코드를 붙여 별도 CSV 로 격리한다.

ponytail: key 파싱/정규화는 UPLOAD-01 ``validate_upload_key`` 를 그대로 쓴다(재구현 0). 이 모듈은
read-only 분류 라이브러리다 — 암호화 artifact/run state machine 을 끌어오지 않는다(순수 CSV).
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Any, Iterable, List, Optional, Set

from foms.api.files.common import normalize_attachment_category
from foms.services.files.upload_authz import validate_upload_key

# ambiguity 사유 코드.
ORDER_MISSING = "ORDER_MISSING"              # order_id 가 None(주문 미결합)
ORPHAN = "ORPHAN"                            # order_id 가 실재하지 않는 order 를 가리킴
NONCANONICAL_KEY = "NONCANONICAL_KEY"        # storage_key 가 canonical 규약과 어긋남
PURPOSE_UNRESOLVABLE = "PURPOSE_UNRESOLVABLE"  # category 가 유효 첨부 category 아님
PURPOSE_MISMATCH = "PURPOSE_MISMATCH"        # 선언 category != key 파생 category


@dataclass(frozen=True)
class ExactMapping:
    """정확히 분류된 legacy attachment(row → order → purpose → object key).

    Attributes:
        attachment_id: OrderAttachment.id.
        order_id: 확정된 대상 order id.
        purpose: 확정된 첨부 category(measurement/drawing/construction/as).
        object_key: canonical storage object key.
        thumbnail_key: 썸네일 object key(있으면). 정보용 — 분류 게이트에는 쓰지 않는다.
    """

    attachment_id: Any
    order_id: int
    purpose: str
    object_key: str
    thumbnail_key: Optional[str]


@dataclass(frozen=True)
class AmbiguousAttachment:
    """격리(quarantine) 대상 attachment — 사유 코드와 함께 수동 판단으로 넘긴다.

    Attributes:
        attachment_id: OrderAttachment.id.
        order_id: 선언된 order_id(None 가능).
        declared_category: row 의 원 category 값(정규화 전 원값).
        object_key: 원 storage_key.
        thumbnail_key: 원 thumbnail_key(있으면).
        reasons: 정렬된 사유 코드 목록(하나 이상).
    """

    attachment_id: Any
    order_id: Optional[int]
    declared_category: Optional[str]
    object_key: Optional[str]
    thumbnail_key: Optional[str]
    reasons: tuple[str, ...]


@dataclass
class LegacyAttachmentAudit:
    """legacy attachment 감사 결과(read-only 분류). exact / ambiguous 분리 보관."""

    exact: List[ExactMapping] = field(default_factory=list)
    ambiguous: List[AmbiguousAttachment] = field(default_factory=list)
    total: int = 0


def classify_attachments(
    attachments: Iterable[Any], known_order_ids: Set[int]
) -> LegacyAttachmentAudit:
    """attachment row 목록을 exact / ambiguous 로 분리 분류한다(아무 것도 쓰지 않음).

    Args:
        attachments: ``id``/``order_id``/``category``/``storage_key``/``thumbnail_key`` 를 가진
            OrderAttachment-like 목록.
        known_order_ids: 실재하는 order id 집합(orphan 판정용).

    Returns:
        LegacyAttachmentAudit — exact/ambiguous 분리 + total count.
    """
    result = LegacyAttachmentAudit()
    for att in attachments:
        result.total += 1
        classified = _classify_one(att, known_order_ids)
        if isinstance(classified, ExactMapping):
            result.exact.append(classified)
        else:
            result.ambiguous.append(classified)
    return result


def _classify_one(att: Any, known_order_ids: Set[int]):
    """단일 attachment → ExactMapping | AmbiguousAttachment."""
    order_id = getattr(att, "order_id", None)
    raw_category = getattr(att, "category", None)
    storage_key = getattr(att, "storage_key", None)
    thumbnail_key = getattr(att, "thumbnail_key", None)
    reasons: List[str] = []

    # (1) order 확정: order_id 존재 + 실재.
    if order_id is None:
        reasons.append(ORDER_MISSING)
    elif order_id not in known_order_ids:
        reasons.append(ORPHAN)

    # (2) key 정규: UPLOAD-01 canonical 규약(SSOT). order_id 없으면 order 대비 검증 불가 → 비정규.
    key_category: Optional[str] = None
    if order_id is not None and isinstance(storage_key, str):
        key_ok, key_category, _ = validate_upload_key(storage_key, order_id)
    else:
        key_ok = False
    if not key_ok:
        reasons.append(NONCANONICAL_KEY)

    # (3) purpose 확정: category 유효 + key 파생 category 와 일치.
    declared = normalize_attachment_category(raw_category)
    if declared is None:
        reasons.append(PURPOSE_UNRESOLVABLE)
    elif key_ok and key_category != declared:
        reasons.append(PURPOSE_MISMATCH)

    if reasons:
        return AmbiguousAttachment(
            attachment_id=getattr(att, "id", None),
            order_id=order_id,
            declared_category=raw_category,
            object_key=storage_key,
            thumbnail_key=thumbnail_key,
            reasons=tuple(sorted(reasons)),
        )
    return ExactMapping(
        attachment_id=getattr(att, "id", None),
        order_id=order_id,
        purpose=declared,
        object_key=storage_key,
        thumbnail_key=thumbnail_key,
    )


def audit_legacy_attachments(session: Any) -> LegacyAttachmentAudit:
    """DB session 에서 모든 OrderAttachment 를 읽어 분류한다(read-only: SELECT 만).

    Args:
        session: SQLAlchemy session. **읽기 전용** — commit/flush write 를 하지 않는다.

    Returns:
        LegacyAttachmentAudit.
    """
    from models import Order, OrderAttachment

    known_order_ids: Set[int] = {oid for (oid,) in session.query(Order.id).all()}
    attachments = session.query(OrderAttachment).all()
    return classify_attachments(attachments, known_order_ids)


def to_exact_csv(audit: LegacyAttachmentAudit) -> str:
    """exact mapping 을 CSV 로 내보낸다.

    헤더 ``attachment_id,order_id,purpose,object_key,thumbnail_key``(attachment_id 정렬).

    Returns:
        CSV 텍스트(마지막 개행 포함).
    """
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["attachment_id", "order_id", "purpose", "object_key", "thumbnail_key"])
    for row in sorted(audit.exact, key=lambda r: _sort_key(r.attachment_id)):
        writer.writerow(
            [row.attachment_id, row.order_id, row.purpose, row.object_key, row.thumbnail_key or ""]
        )
    return buf.getvalue()


def to_quarantine_csv(audit: LegacyAttachmentAudit) -> str:
    """ambiguous(quarantine) attachment 를 CSV 로 내보낸다.

    헤더 ``attachment_id,order_id,declared_category,object_key,thumbnail_key,reasons``
    (attachment_id 정렬, reasons 는 ``|`` 로 결합).

    Returns:
        CSV 텍스트(마지막 개행 포함).
    """
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(
        ["attachment_id", "order_id", "declared_category", "object_key", "thumbnail_key", "reasons"]
    )
    for row in sorted(audit.ambiguous, key=lambda r: _sort_key(r.attachment_id)):
        writer.writerow([
            row.attachment_id,
            "" if row.order_id is None else row.order_id,
            "" if row.declared_category is None else row.declared_category,
            "" if row.object_key is None else row.object_key,
            row.thumbnail_key or "",
            "|".join(row.reasons),
        ])
    return buf.getvalue()


def _sort_key(attachment_id: Any) -> tuple[int, Any]:
    """None-safe 정렬 키(None 은 뒤로)."""
    return (1, "") if attachment_id is None else (0, attachment_id)
