"""legacy 위치-인덱스 결합 audit/분류 (ITEM-ID-00, §5.2 line 562).

첨부(:class:`~models.OrderAttachment`)·일정(:class:`~models.OrderScheduleDate`)의 기존
``item_index`` 를 안정 UUID identity 에 매핑하기 전에 **read-only 로 분류**한다. 핵심 계약은
**자동 매핑 0**:

* :func:`audit_item_identities` 는 아무 것도 쓰지 않는다(순수 조회). ``item_index`` 가 주문의
  ``structured_data['items']`` 범위 안(``0 <= idx < item_count``)이면 ``safe`` (backfill 로
  UUID 발급 가능), 범위 밖/음수면 ``ambiguous`` (수동 CSV 검토 대상)로 나눈다.
* ``item_index is None`` (공통 첨부/일정)은 아이템 스코프가 아니므로 대상에서 제외한다
  (item_id 를 발급하지 않고 공통으로 남긴다 — schedule 을 common 으로 이동하는 것이 아니라
  애초에 아이템에 결합되지 않은 행이다).
* :func:`to_manual_csv` 는 ambiguous 를 수동 매핑용 CSV 로 내보낸다.

ponytail: 이 audit 은 index→UUID 분류라 형제 backfill(``assignment_backfill.py`` ·
``state_axes_audit.py``)과 동일한 lite 패턴을 쓴다 — BACKFILL-ARTIFACT-00 의 암호화 run
state machine(lease/checkpoint/OPS-APPROVAL)까지 끌어오지 않는다. 그 무거운 파이프라인은
대량 PII resume backfill 용이고, in-range 인덱스에 UUID 를 발급하는 이 결합엔 과하다.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, List, Tuple

from sqlalchemy.orm import Session

from models import Order, OrderAttachment, OrderScheduleDate

# ambiguous 사유 코드.
OUT_OF_RANGE = "OUT_OF_RANGE"      # item_index >= item_count (아이템 삭제/미파싱 포함)
NEGATIVE_INDEX = "NEGATIVE_INDEX"  # item_index < 0 (유효 슬롯 아님)


@dataclass(frozen=True)
class AmbiguousItemRef:
    """자동 매핑 불가한 legacy 결합 1건(수동 CSV 대상·read-only).

    Attributes:
        order_id: 주문 id.
        item_index: 문제된 위치 인덱스.
        ref_kind: ``'attachment'`` | ``'schedule'``.
        ref_id: 해당 행 PK.
        reason: :data:`OUT_OF_RANGE` | :data:`NEGATIVE_INDEX`.
        item_count: 발견 시점 주문의 아이템 수(수동 검토 참고).
    """

    order_id: int
    item_index: int
    ref_kind: str
    ref_id: int
    reason: str
    item_count: int


@dataclass(frozen=True)
class ItemIdentityAudit:
    """분류 결과(read-only).

    Attributes:
        safe: backfill 로 UUID 발급 가능한 ``(order_id, item_index)`` 슬롯 집합.
        ambiguous: 자동 매핑 불가 결합 목록(수동 CSV 대상).
    """

    safe: FrozenSet[Tuple[int, int]]
    ambiguous: Tuple[AmbiguousItemRef, ...]


def _item_count(order: Any) -> int:
    """주문의 ``structured_data['items']`` 길이(없거나 형식 이상이면 0)."""
    sd = getattr(order, "structured_data", None)
    if not isinstance(sd, dict):
        return 0
    items = sd.get("items")
    return len(items) if isinstance(items, list) else 0


def audit_item_identities(session: Session) -> ItemIdentityAudit:
    """아이템-스코프 첨부/일정의 위치 인덱스를 safe/ambiguous 로 분류한다(쓰기 0).

    Args:
        session: DB 세션.

    Returns:
        :class:`ItemIdentityAudit` — safe 슬롯 집합 + ambiguous 결합 목록.
    """
    refs: List[Tuple[str, int, int, int]] = []  # (ref_kind, order_id, item_index, ref_id)
    for order_id, item_index, ref_id in (
        session.query(
            OrderAttachment.order_id, OrderAttachment.item_index, OrderAttachment.id
        )
        .filter(OrderAttachment.item_index.isnot(None))
        .all()
    ):
        refs.append(("attachment", order_id, item_index, ref_id))
    for order_id, item_index, ref_id in (
        session.query(
            OrderScheduleDate.order_id, OrderScheduleDate.item_index, OrderScheduleDate.id
        )
        .filter(OrderScheduleDate.item_index.isnot(None))
        .all()
    ):
        refs.append(("schedule", order_id, item_index, ref_id))

    # 주문별 아이템 수를 한 번씩만 계산(같은 주문의 여러 결합이 공유).
    counts: Dict[int, int] = {}
    for _kind, order_id, _idx, _rid in refs:
        if order_id not in counts:
            order = session.get(Order, order_id)
            counts[order_id] = _item_count(order) if order is not None else 0

    safe: set[Tuple[int, int]] = set()
    ambiguous: List[AmbiguousItemRef] = []
    for ref_kind, order_id, item_index, ref_id in refs:
        count = counts.get(order_id, 0)
        if item_index < 0:
            ambiguous.append(
                AmbiguousItemRef(order_id, item_index, ref_kind, ref_id, NEGATIVE_INDEX, count)
            )
        elif item_index < count:
            safe.add((order_id, item_index))
        else:
            ambiguous.append(
                AmbiguousItemRef(order_id, item_index, ref_kind, ref_id, OUT_OF_RANGE, count)
            )
    return ItemIdentityAudit(frozenset(safe), tuple(ambiguous))


def to_manual_csv(audit: ItemIdentityAudit) -> str:
    """ambiguous 결합을 수동 매핑용 CSV 문자열로 내보낸다(header 포함).

    Args:
        audit: :func:`audit_item_identities` 결과.

    Returns:
        ``order_id,item_index,ref_kind,ref_id,reason,item_count`` CSV 문자열.
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["order_id", "item_index", "ref_kind", "ref_id", "reason", "item_count"])
    for ref in sorted(
        audit.ambiguous, key=lambda r: (r.order_id, r.ref_kind, r.ref_id)
    ):
        writer.writerow(
            [ref.order_id, ref.item_index, ref.ref_kind, ref.ref_id, ref.reason, ref.item_count]
        )
    return buf.getvalue()
