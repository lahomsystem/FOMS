"""safe legacy 결합 backfill + enforcement 게이트 (ITEM-ID-00, §5.2).

:func:`audit_item_identities` 가 ``safe`` 로 분류한 ``(order_id, item_index)`` 슬롯에만
UUID identity 를 발급하고(멱등), 그 슬롯의 첨부/일정 ``item_id`` 를 채운다. **ambiguous 는
절대 손대지 않는다** — 자동 매핑 0 계약이다. 발급/링크는 in-range 슬롯에 한정되므로
out-of-range/음수 인덱스 행은 backfill 후에도 ``item_id IS NULL`` 로 남아 수동 CSV 매핑
대상이 된다.

:func:`can_enforce_not_null` 은 NOT NULL enforcement(별도 마이그레이션)를 걸 수 있는지 판정한다:
ambiguous 가 0건이고 **모든** 아이템-스코프 첨부/일정이 ``item_id`` 를 가질 때만 True. 그
전에는 enforcement 를 걸지 않는다(expand 단계 유지).

ponytail: 형제 ``assignment_backfill.py`` / ``state_axes_audit.py`` 와 동일 lite 패턴 —
암호화 run state machine(``runs.py``)을 끌어오지 않는다(index→UUID 발급엔 과함). 대량/재개
가 필요해지면 그때 ``runs.py`` 로 감싼다.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from foms.services.orders.audit_order_item_identities import (
    ItemIdentityAudit,
    audit_item_identities,
)
from foms.services.orders.item_identity import (
    get_or_create_identity,
    resolve_active_item_id,
)
from models import OrderAttachment, OrderScheduleDate


@dataclass(frozen=True)
class BackfillResult:
    """backfill 적용 결과 요약.

    Attributes:
        identities_minted: 새로 발급된 UUID identity 수(기존 활성은 재사용, 미포함).
        attachments_linked: ``item_id`` 를 새로 채운 첨부 수.
        schedule_dates_linked: ``item_id`` 를 새로 채운 일정 수.
        ambiguous_skipped: 손대지 않은 ambiguous 결합 수(자동 매핑 0 증거).
    """

    identities_minted: int
    attachments_linked: int
    schedule_dates_linked: int
    ambiguous_skipped: int


def apply_safe_backfill(
    session: Session, audit: ItemIdentityAudit | None = None
) -> BackfillResult:
    """safe 슬롯에만 UUID 를 발급하고 첨부/일정 item_id 를 채운다(ambiguous 무접근·멱등).

    이미 ``item_id`` 가 채워진 행은 다시 건드리지 않는다(재실행 멱등). 커밋은 호출자 몫이며,
    커밋 cadence(배치 크기)도 호출자가 정한다 — runs.py 의 lease/checkpoint 를 안 쓰는 대신
    이 **자원 idempotency**(NULL 행만 링크 + registry partial-unique)가 resume 을 보장한다:
    한 배치가 부분 실패로 롤백되면, 다음 재실행이 아직 NULL 인 행만 이어서 링크하고 이미 발급된
    UUID 는 재발급하지 않는다.

    Args:
        session: DB 세션.
        audit: 미리 계산한 audit(없으면 내부에서 :func:`audit_item_identities` 호출).

    Returns:
        :class:`BackfillResult`.
    """
    if audit is None:
        audit = audit_item_identities(session)

    minted = 0
    att_linked = 0
    sch_linked = 0
    for order_id, item_index in sorted(audit.safe):
        # 발급 전에 활성 identity 유무를 확인해 minted 를 신규 발급만 카운트(재실행 멱등).
        pre_existing = resolve_active_item_id(session, order_id, item_index)
        identity = get_or_create_identity(session, order_id, item_index)
        if pre_existing is None:
            minted += 1

        att_linked += (
            session.query(OrderAttachment)
            .filter(
                OrderAttachment.order_id == order_id,
                OrderAttachment.item_index == item_index,
                OrderAttachment.item_id.is_(None),
            )
            .update({OrderAttachment.item_id: identity.id}, synchronize_session=False)
        )
        sch_linked += (
            session.query(OrderScheduleDate)
            .filter(
                OrderScheduleDate.order_id == order_id,
                OrderScheduleDate.item_index == item_index,
                OrderScheduleDate.item_id.is_(None),
            )
            .update({OrderScheduleDate.item_id: identity.id}, synchronize_session=False)
        )

    session.flush()
    return BackfillResult(
        identities_minted=minted,
        attachments_linked=att_linked,
        schedule_dates_linked=sch_linked,
        ambiguous_skipped=len(audit.ambiguous),
    )


def can_enforce_not_null(session: Session) -> bool:
    """NOT NULL enforcement 를 걸 수 있는지 판정한다(ambiguous 0건 AND 전 행 item_id 보유).

    아이템-스코프(``item_index IS NOT NULL``) 첨부/일정 중 ``item_id`` 가 비어 있는 행이
    하나라도 있거나, ambiguous 결합이 하나라도 있으면 False.

    Args:
        session: DB 세션.

    Returns:
        enforcement 적용 가능하면 True.
    """
    audit = audit_item_identities(session)
    if audit.ambiguous:
        return False
    missing_att = (
        session.query(OrderAttachment)
        .filter(
            OrderAttachment.item_index.isnot(None),
            OrderAttachment.item_id.is_(None),
        )
        .count()
    )
    if missing_att:
        return False
    missing_sch = (
        session.query(OrderScheduleDate)
        .filter(
            OrderScheduleDate.item_index.isnot(None),
            OrderScheduleDate.item_id.is_(None),
        )
        .count()
    )
    return missing_sch == 0
