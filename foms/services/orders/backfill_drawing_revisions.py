"""SAFE 주문에 UUID revision/request 발급 + enforcement 게이트 (DRAWING-REVISION-BACKFILL-00, §5.2).

:func:`~foms.services.orders.audit_drawing_revisions.audit_drawing_revisions` 가 ``SAFE`` 로
분류한 주문에만 UUID :class:`~models.DrawingRevision`(TRANSFER 마다)·
:class:`~models.DrawingRevisionRequest`(REQUEST_REVISION 마다)를 발급하고, flat
``drawing_transfer_history`` entry 의 전달·수령확인(receipt)·고객확인(customer-confirm)·요청
스냅샷을 registry 컬럼으로 **복제**한다. flat ``structured_data`` 와 attachment 는 **절대
삭제/재작성하지 않는다**(timestamp/file 추정으로 상태 활성 금지·attachment 삭제 금지 — 전이
활성화는 하류 STATE-DRAWING-01 소관). ambiguous 주문은 손대지 않는다(자동 매핑 0).

멱등/resume: 이미 발급된 revision/request(같은 ``order_id`` + ``legacy_seq``)는 다시 발급하지
않는다(부분 실패 후 재실행이 아직 없는 것만 이어서 발급). ``uq_drawing_revision_legacy`` /
``uq_drawing_request_legacy`` partial-unique 가 DB 레벨에서도 중복 발급을 막고,
``uq_drawing_revision_current`` / ``_receipt`` / ``_customer`` / ``uq_drawing_request_open``
이 주문당 각 포인터를 1개로 강제한다 — 이 **자원 idempotency** 가 resume 을 보장한다.

:func:`can_enforce` 는 전이(STATE-DRAWING-01)를 켤 수 있는지 판정한다: ambiguous 0건이고
**모든** in-flight drawing 주문이 current revision 을 가질 때만 True(§ "in-flight drawing
current 100%"). 그 전에는 command flag 를 켜지 않는다.

ponytail: 형제 ``backfill_production_runs`` / ``backfill_as_cycles`` 와 동일 lite 패턴 —
암호화 run state machine(``runs.py``)을 끌어오지 않는다. revision→request 링크(soft
``revision_id``)만 registry 발급 시 해소한다.
"""
from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional

from foms.services.orders.audit_drawing_revisions import (
    DrawingRevisionAudit,
    audit_drawing_revisions,
)


@dataclass(frozen=True)
class BackfillResult:
    """backfill 적용 결과 요약.

    Attributes:
        revisions_minted: 새로 발급된 revision 수.
        requests_minted: 새로 발급된 request 수.
        already_present: 이미 발급돼 건너뛴 revision+request 수(재실행 멱등 증거).
        ambiguous_skipped: 손대지 않은 ambiguous 주문 수(자동 매핑 0 증거).
    """

    revisions_minted: int
    requests_minted: int
    already_present: int
    ambiguous_skipped: int


def _parse_dt(raw: Optional[str]) -> Optional[datetime.datetime]:
    """legacy 시각 문자열(ISO 'T' 또는 공백 구분)을 naive datetime 으로(파싱 불가 시 None)."""
    if not raw:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None
    return parsed.replace(tzinfo=None) if parsed.tzinfo is not None else parsed


def _existing_revno_map(session, order_id: int) -> Dict[int, str]:
    """주문의 이미 발급된 revision 을 {revision_no: id} 로 반환(resume 링크 해소용)."""
    from models import DrawingRevision

    rows = (
        session.query(DrawingRevision.revision_no, DrawingRevision.id)
        .filter(DrawingRevision.order_id == order_id)
        .all()
    )
    return {revno: rid for revno, rid in rows}


def _revision_exists(session, order_id: int, legacy_seq: int) -> bool:
    """주문의 해당 legacy transfer entry revision 이 이미 발급됐는가(멱등 판정)."""
    from models import DrawingRevision

    return (
        session.query(DrawingRevision.id)
        .filter(
            DrawingRevision.order_id == order_id,
            DrawingRevision.legacy_seq == legacy_seq,
        )
        .first()
        is not None
    )


def _request_exists(session, order_id: int, legacy_seq: int) -> bool:
    """주문의 해당 legacy request entry request 가 이미 발급됐는가(멱등 판정)."""
    from models import DrawingRevisionRequest

    return (
        session.query(DrawingRevisionRequest.id)
        .filter(
            DrawingRevisionRequest.order_id == order_id,
            DrawingRevisionRequest.legacy_seq == legacy_seq,
        )
        .first()
        is not None
    )


def apply_safe_backfill(
    session, audit: Optional[DrawingRevisionAudit] = None
) -> BackfillResult:
    """SAFE 주문에만 revision/request 를 발급한다(ambiguous 무접근·멱등·flat/attachment 보존).

    이미 발급된 (order_id, legacy_seq) revision/request 는 건너뛴다(재실행 멱등). flat
    structured_data 와 attachment 는 읽기만 하고 수정/삭제하지 않는다 — 전달/수령/고객/요청
    스냅샷은 registry 컬럼에 **복제**된다. 커밋은 호출자 몫이다.

    Args:
        session: DB 세션.
        audit: 미리 계산한 audit(없으면 내부에서 :func:`audit_drawing_revisions` 호출).

    Returns:
        :class:`BackfillResult`.
    """
    from models import DrawingRevision, DrawingRevisionRequest

    if audit is None:
        audit = audit_drawing_revisions(session)

    rev_minted = 0
    req_minted = 0
    already = 0
    new_revs: List[DrawingRevision] = []
    new_reqs: List[DrawingRevisionRequest] = []

    for plan in audit.safe:
        # revno → id: 기존 발급분(resume) + 이번에 발급할 신규분(요청 링크 해소용).
        revno_to_id: Dict[int, str] = _existing_revno_map(session, plan.order_id)

        for rev in plan.revisions:
            if _revision_exists(session, plan.order_id, rev.legacy_seq):
                already += 1
                continue
            rid = str(uuid.uuid4())
            revno_to_id[rev.revision_no] = rid
            new_revs.append(DrawingRevision(
                id=rid,
                order_id=plan.order_id,
                status=rev.status,
                revision_no=rev.revision_no,
                transferred_at=_parse_dt(rev.transferred_at),
                transferred_by=rev.transferred_by,
                note=rev.note,
                files=list(rev.files),
                receipt_confirmed_at=_parse_dt(rev.receipt_confirmed_at),
                receipt_confirmed_by=rev.receipt_confirmed_by,
                customer_confirmed_at=_parse_dt(rev.customer_confirmed_at),
                customer_confirmed_by=rev.customer_confirmed_by,
                is_current=rev.is_current,
                is_receipt=rev.is_receipt,
                is_customer_confirmed=rev.is_customer_confirmed,
                legacy_seq=rev.legacy_seq,
            ))
            rev_minted += 1

        for req in plan.requests:
            if _request_exists(session, plan.order_id, req.legacy_seq):
                already += 1
                continue
            target_id = (
                revno_to_id.get(req.target_revision_no)
                if req.target_revision_no is not None else None
            )
            new_reqs.append(DrawingRevisionRequest(
                id=str(uuid.uuid4()),
                order_id=plan.order_id,
                revision_id=target_id,
                status=req.status,
                requested_at=_parse_dt(req.requested_at),
                requested_by=req.requested_by,
                note=req.note,
                files=list(req.files),
                target_drawing_keys=list(req.target_drawing_keys),
                is_open=req.is_open,
                legacy_seq=req.legacy_seq,
            ))
            req_minted += 1

    session.add_all(new_revs)
    session.add_all(new_reqs)
    session.flush()
    return BackfillResult(
        revisions_minted=rev_minted,
        requests_minted=req_minted,
        already_present=already,
        ambiguous_skipped=len(audit.ambiguous),
    )


def can_enforce(session) -> bool:
    """전이(STATE-DRAWING-01) 활성화 게이트: ambiguous 0 AND in-flight current 100%.

    ambiguous 주문이 하나라도 있거나, drawing_status 가 활성(``TRANSFERRED``/``RETURNED``/
    ``CONFIRMED``)인 주문 중 current revision(``is_current``)이 없는 주문이 하나라도 있으면 False.

    Args:
        session: DB 세션.

    Returns:
        enforcement 적용 가능하면 True.
    """
    from models import DrawingRevision

    audit = audit_drawing_revisions(session)
    if audit.ambiguous:
        return False
    for order_id in audit.in_flight_ids:
        current = (
            session.query(DrawingRevision.id)
            .filter(
                DrawingRevision.order_id == order_id,
                DrawingRevision.is_current.is_(True),
            )
            .first()
        )
        if current is None:
            return False
    return True


__all__ = [
    "BackfillResult",
    "apply_safe_backfill",
    "can_enforce",
]
