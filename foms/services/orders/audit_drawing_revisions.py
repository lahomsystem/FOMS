"""flat 도면 이력 → UUID revision/request 매핑 audit/분류 (DRAWING-REVISION-BACKFILL-00, §5.2).

주문의 flat ``structured_data['drawing_transfer_history']``(TRANSFER/REQUEST_REVISION/
CONFIRM_RECEIPT 가 한 리스트에 시간순 append 됨)·``drawing_status``·
``blueprint.customer_confirmed`` 를 **read-only 로 분류**한다. 핵심 계약은 **자동 매핑 0** —
사람이 봐야 하는 주문은 절대 자동 backfill 하지 않는다:

* :func:`audit_drawing_revisions` 는 아무 것도 쓰지 않는다(순수 조회).
* **SAFE**: ``drawing_transfer_history`` 가 well-formed 이고, 열린(trailing) 수정요청이
  drawing_status 와 정합(``RETURNED`` ⟺ 열린 요청 정확히 1개, 그 외 ⟺ 열린 요청 0개)인
  주문 → TRANSFER 마다 revision, REQUEST_REVISION 마다 request 로 정확 매핑한다. 마지막
  TRANSFER=current revision, 마지막 CONFIRM_RECEIPT 시점 current revision=receipt,
  ``blueprint.customer_confirmed`` → receipt(없으면 current) revision=customer-confirm.
* **AMBIGUOUS**: history 구조 이상(:data:`MALFORMED`), drawing 활성인데 TRANSFER 없음
  (:data:`NO_TRANSFER`), drawing_status 와 열린 요청 불일치(:data:`STATUS_MISMATCH`),
  열린 요청 복수(:data:`DUPLICATE_OPEN`) → 수동 CSV 로 보낸다(자동 발급 금지).
* 도면 활동이 없는 주문(TRANSFER 0 + drawing_status 비활성)은 대상에서 제외한다.

**전이(개정 발급/전달) 활성화는 하류 STATE-DRAWING-01 소관** 이므로 이 audit 은 flat
history/status/attachment 를 **재작성/삭제하지 않고**(timestamp/file 추정으로 상태 활성 금지·
attachment 삭제 금지), 열린 요청이 여러 개일 때 어느 것이 current 인지 **자동 선택하지 않는다**.

**in-flight drawing current 100%**: :attr:`DrawingRevisionAudit.in_flight_ids`(drawing_status
가 활성 ``TRANSFERRED``/``RETURNED``/``CONFIRMED`` 인 주문)가 모두 SAFE(current revision 보유)
인지는 :meth:`DrawingRevisionAudit.covers_all_in_flight` 로 검사한다 — ambiguous in-flight
주문이 있으면 coverage < 100% 이고 enforcement 는 게이트된다
(:func:`backfill_drawing_revisions.can_enforce`).

ponytail: 형제 ``audit_production_runs`` / ``audit_as_cycles`` 와 동일한 lite 패턴 —
BACKFILL-ARTIFACT-00 의 암호화 run state machine(lease/checkpoint/OPS-APPROVAL)까지
끌어오지 않는다. revision(TRANSFER)·request(REQUEST_REVISION) 두 엔티티라 스냅샷 dataclass
가 2종일 뿐 분류 골격은 같다.
"""
from __future__ import annotations

import copy
import csv
import io
import json
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Tuple

# drawing_transfer_history 의 lifecycle action.
ACTION_TRANSFER = "TRANSFER"
ACTION_REQUEST = "REQUEST_REVISION"
ACTION_RECEIPT = "CONFIRM_RECEIPT"

# revision status(§2.2.1 drawing read-model target).
REV_TRANSFERRED = "TRANSFERRED"
REV_RETURNED = "RETURNED"
REV_CONFIRMED = "CONFIRMED"
REV_SUPERSEDED = "SUPERSEDED"

# request status.
REQ_OPEN = "OPEN"
REQ_RESOLVED = "RESOLVED"

# drawing_status 중 "current drawing 이 살아 있는" 활성 값(current revision 필요 = in-flight).
_ACTIVE_DRAWING_STATUS: FrozenSet[str] = frozenset(
    {REV_TRANSFERRED, REV_RETURNED, REV_CONFIRMED}
)

# ambiguous 사유 코드.
MALFORMED = "MALFORMED"              # drawing_transfer_history 구조 이상(list/dict 아님)
NO_TRANSFER = "NO_TRANSFER"          # drawing 활성인데 TRANSFER 이력 0 → revision 도출 불가
STATUS_MISMATCH = "STATUS_MISMATCH"  # drawing_status 와 열린 요청 상태 불일치
DUPLICATE_OPEN = "DUPLICATE_OPEN"    # 마지막 TRANSFER 뒤 열린 요청 복수


@dataclass(frozen=True)
class DrawingRevisionSnapshot:
    """revision 1개의 결정적 스냅샷(flat TRANSFER entry + receipt/customer 복제).

    Attributes:
        revision_no: 주문 내 TRANSFER 발생 순 1-based 순번.
        status: :data:`REV_TRANSFERRED` | :data:`REV_RETURNED` | :data:`REV_CONFIRMED`
            | :data:`REV_SUPERSEDED`.
        is_current: 현재 revision(마지막 TRANSFER) 여부(주문당 최대 1개).
        is_receipt: 수령 확인(마지막 CONFIRM_RECEIPT 시점 current) revision 여부(0/1).
        is_customer_confirmed: 고객 확인 revision 여부(0/1).
        transferred_at: 전달 시각 원문(없으면 None).
        transferred_by: 전달 담당명(없으면 None).
        note: 전달 메모(없으면 None).
        files: 전달 파일 스냅샷(원문 복제 — attachment 삭제/재작성 금지).
        receipt_confirmed_at: 수령 확인 시각 원문(없으면 None).
        receipt_confirmed_by: 수령 확인 담당명(없으면 None).
        customer_confirmed_at: 고객 확인 시각 원문(없으면 None).
        customer_confirmed_by: 고객 확인 담당명(없으면 None).
        legacy_seq: 발급 근거 drawing_transfer_history 인덱스(provenance·멱등 키).
    """

    revision_no: int
    status: str
    is_current: bool
    is_receipt: bool
    is_customer_confirmed: bool
    transferred_at: Optional[str]
    transferred_by: Optional[str]
    note: Optional[str]
    files: Tuple[Any, ...]
    receipt_confirmed_at: Optional[str]
    receipt_confirmed_by: Optional[str]
    customer_confirmed_at: Optional[str]
    customer_confirmed_by: Optional[str]
    legacy_seq: int


@dataclass(frozen=True)
class DrawingRequestSnapshot:
    """수정요청 1개의 결정적 스냅샷(flat REQUEST_REVISION entry 복제).

    Attributes:
        status: :data:`REQ_OPEN`(마지막 TRANSFER 뒤 미해소) | :data:`REQ_RESOLVED`(후속
            TRANSFER 로 해소된 과거 요청).
        is_open: 열린 요청 여부(주문당 최대 1개).
        target_revision_no: 요청 대상 revision(요청 시점 current) 의 순번(없으면 None).
        requested_at: 요청 시각 원문(없으면 None).
        requested_by: 요청 담당명(없으면 None).
        note: 요청 메모(없으면 None).
        files: 요청 참고 파일 스냅샷(원문 복제 — attachment 삭제 금지).
        target_drawing_keys: 요청 대상 도면 key 목록 스냅샷(없으면 빈 tuple).
        legacy_seq: 발급 근거 drawing_transfer_history 인덱스(provenance·멱등 키).
    """

    status: str
    is_open: bool
    target_revision_no: Optional[int]
    requested_at: Optional[str]
    requested_by: Optional[str]
    note: Optional[str]
    files: Tuple[Any, ...]
    target_drawing_keys: Tuple[Any, ...]
    legacy_seq: int


@dataclass(frozen=True)
class DrawingRevisionPlan:
    """SAFE 주문 1건의 결정적 backfill plan(revision 목록·request 목록).

    Attributes:
        order_id: 주문 id.
        revisions: 발급할 revision 목록(revision_no 오름차순, current 최대 1개).
        requests: 발급할 request 목록(legacy_seq 오름차순, open 최대 1개).
    """

    order_id: int
    revisions: Tuple[DrawingRevisionSnapshot, ...]
    requests: Tuple[DrawingRequestSnapshot, ...]

    def has_current(self) -> bool:
        """current revision 을 하나 가지고 있는가(coverage 판정)."""
        return any(r.is_current for r in self.revisions)


@dataclass(frozen=True)
class AmbiguousDrawing:
    """자동 매핑 불가한 주문 1건(수동 CSV 대상·read-only).

    Attributes:
        order_id: 주문 id.
        drawing_status: 발견 시점 flat ``drawing_status`` 값(참고).
        transfer_count: TRANSFER 이력 수.
        open_request_count: 마지막 TRANSFER 뒤 열린 REQUEST_REVISION 수.
        history: flat ``drawing_transfer_history`` 스냅샷(수동 검토용·원문 복제).
        reason: :data:`MALFORMED` | :data:`NO_TRANSFER` | :data:`STATUS_MISMATCH`
            | :data:`DUPLICATE_OPEN`.
    """

    order_id: int
    drawing_status: str
    transfer_count: int
    open_request_count: int
    history: Any
    reason: str


@dataclass(frozen=True)
class DrawingRevisionAudit:
    """분류 결과(read-only).

    Attributes:
        safe: SAFE 주문의 backfill plan 목록(order_id 오름차순).
        ambiguous: 자동 매핑 불가 주문 목록(수동 CSV 대상).
        in_flight_ids: drawing_status 가 활성(``TRANSFERRED``/``RETURNED``/``CONFIRMED``)인
            주문 id 집합(current revision coverage 기준).
    """

    safe: Tuple[DrawingRevisionPlan, ...]
    ambiguous: Tuple[AmbiguousDrawing, ...]
    in_flight_ids: FrozenSet[int]

    def covers_all_in_flight(self) -> bool:
        """모든 in-flight drawing 주문이 current revision 을 갖는 SAFE plan 인가(100% 매핑)."""
        covered = {p.order_id for p in self.safe if p.has_current()}
        return self.in_flight_ids <= covered


def _structured(order: Any) -> Dict[str, Any]:
    """order.structured_data 를 dict 로 안전 반환(없으면 빈 dict)."""
    sd = getattr(order, "structured_data", None)
    return sd if isinstance(sd, dict) else {}


def _drawing_status(sd: Dict[str, Any]) -> str:
    """flat ``drawing_status`` 를 대문자 trim 문자열로(부재 시 ``PENDING``)."""
    return str(sd.get("drawing_status") or "PENDING").strip().upper()


def _history_wellformed(history: Any) -> bool:
    """drawing_transfer_history 가 dict 리스트인가(malformed 판정).

    각 entry 는 dict 여야 한다. 알 수 없는 action 은 malformed 가 아니라 무시 대상이다
    (lifecycle action 만 추출). history 키 부재(None)는 malformed 아님(도면 활동 없음).
    """
    if not isinstance(history, list):
        return False
    return all(isinstance(e, dict) for e in history)


def _opt_str(value: Any) -> Optional[str]:
    """빈 값은 None, 그 외는 원문 문자열로(스냅샷 정규화)."""
    if value is None:
        return None
    text = str(value)
    return text if text != "" else None


def _entry_at(entry: Dict[str, Any]) -> Optional[str]:
    """entry 의 시각 원문. TRANSFER 는 ``transferred_at``, 그 외는 ``at``(둘 다 폴백)."""
    return _opt_str(entry.get("transferred_at") or entry.get("at"))


def _customer_confirm(sd: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[str]]:
    """``blueprint.customer_confirmed`` 여부와 confirmed_at/by 원문을 반환."""
    blueprint = sd.get("blueprint")
    if not isinstance(blueprint, dict) or not blueprint.get("customer_confirmed"):
        return False, None, None
    return True, _opt_str(blueprint.get("confirmed_at")), _opt_str(blueprint.get("confirmed_by"))


def classify_order(order: Any) -> Optional[object]:
    """한 주문을 SAFE plan / ambiguous / None(대상 제외)로 분류한다(read-only).

    Args:
        order: ``id``·``structured_data`` 속성을 가진 주문 row.

    Returns:
        :class:`DrawingRevisionPlan` (SAFE) | :class:`AmbiguousDrawing` (수동 CSV)
        | ``None`` (도면 활동 없음 — revision 미발급).
    """
    order_id = getattr(order, "id", None)
    sd = _structured(order)
    drawing_status = _drawing_status(sd)
    history_raw = sd.get("drawing_transfer_history")

    if history_raw is not None and not _history_wellformed(history_raw):
        return _ambiguous(order_id, drawing_status, 0, 0, history_raw, MALFORMED)

    events: List[Dict[str, Any]] = history_raw if isinstance(history_raw, list) else []
    # (history 인덱스, entry, action) — 시간순 유지(append-only, 취소는 pop 되어 사라짐).
    lifecycle = [
        (idx, e, str(e.get("action") or "").strip().upper())
        for idx, e in enumerate(events)
    ]
    transfers = [(idx, e) for idx, e, act in lifecycle if act == ACTION_TRANSFER]
    active = drawing_status in _ACTIVE_DRAWING_STATUS

    if not transfers:
        if active:
            # drawing 활성인데 전달 이력 없음 → revision 도출 불가(추정 금지) → 수동.
            return _ambiguous(order_id, drawing_status, 0, 0, history_raw, NO_TRANSFER)
        return None  # 도면 활동 없음 → 대상 아님.

    last_transfer_idx = transfers[-1][0]
    trailing_requests = [
        (idx, e) for idx, e, act in lifecycle
        if act == ACTION_REQUEST and idx > last_transfer_idx
    ]
    open_count = len(trailing_requests)
    is_returned = drawing_status == REV_RETURNED

    if open_count > 1:
        return _ambiguous(
            order_id, drawing_status, len(transfers), open_count, history_raw, DUPLICATE_OPEN
        )
    if is_returned and open_count == 0:
        # RETURNED(열린 요청 상태)인데 열린 요청 없음 → 요청 누락(missing open request).
        return _ambiguous(
            order_id, drawing_status, len(transfers), 0, history_raw, STATUS_MISMATCH
        )
    if (not is_returned) and open_count == 1:
        # 열린 요청이 있는데 drawing_status 는 RETURNED 아님 → 불일치.
        return _ambiguous(
            order_id, drawing_status, len(transfers), open_count, history_raw, STATUS_MISMATCH
        )

    return _build_plan(order_id, sd, lifecycle, drawing_status)


def _build_plan(
    order_id: int,
    sd: Dict[str, Any],
    lifecycle: List[Tuple[int, Dict[str, Any], str]],
    drawing_status: str,
) -> DrawingRevisionPlan:
    """SAFE 주문의 revision/request 스냅샷을 결정적으로 구성한다(flat 복제·mutation 0).

    Args:
        order_id: 주문 id.
        sd: structured_data dict.
        lifecycle: (history 인덱스, entry, action) 시간순 목록.
        drawing_status: flat drawing_status(대문자).

    Returns:
        :class:`DrawingRevisionPlan`.
    """
    # 1) TRANSFER → revision 골격(순번·스냅샷). current revision 추적.
    revisions: List[Dict[str, Any]] = []  # 가변 누적(뒤에서 status/flag 확정 후 frozen 화).
    seq_to_revno: Dict[int, int] = {}     # history 인덱스 → revision_no.
    current_revno = 0
    requests: List[DrawingRequestSnapshot] = []
    receipt_revno: Optional[int] = None
    receipt_at: Optional[str] = None
    receipt_by: Optional[str] = None

    for idx, entry, act in lifecycle:
        if act == ACTION_TRANSFER:
            current_revno += 1
            seq_to_revno[idx] = current_revno
            revisions.append({
                "revision_no": current_revno,
                "legacy_seq": idx,
                "transferred_at": _entry_at(entry),
                "transferred_by": _opt_str(entry.get("by_user_name")),
                "note": _opt_str(entry.get("note")),
                "files": tuple(copy.deepcopy(entry.get("files") or [])),
            })
        elif act == ACTION_REQUEST:
            # 요청 시점 current revision 을 대상으로(요청 발생 시 마지막 TRANSFER).
            target = current_revno if current_revno > 0 else None
            requests.append(DrawingRequestSnapshot(
                status=REQ_OPEN,   # 잠정 — 아래에서 마지막 것만 open 확정.
                is_open=False,
                target_revision_no=target,
                requested_at=_entry_at(entry),
                requested_by=_opt_str(entry.get("by_user_name")),
                note=_opt_str(entry.get("note")),
                files=tuple(copy.deepcopy(entry.get("files") or [])),
                target_drawing_keys=tuple(entry.get("target_drawing_keys") or []),
                legacy_seq=idx,
            ))
        elif act == ACTION_RECEIPT:
            # 수령 확인 시점 current revision = receipt(마지막 CONFIRM_RECEIPT 채택).
            receipt_revno = current_revno if current_revno > 0 else None
            receipt_at = _entry_at(entry)
            receipt_by = _opt_str(entry.get("by_user_name"))

    # 2) 열린 요청 확정: 마지막 TRANSFER 뒤 요청은 (분류상) 최대 1개이며 open.
    last_transfer_idx = max(
        (idx for idx, _e, act in lifecycle if act == ACTION_TRANSFER), default=-1
    )
    resolved_requests: List[DrawingRequestSnapshot] = []
    for req in requests:
        is_open = req.legacy_seq > last_transfer_idx
        resolved_requests.append(DrawingRequestSnapshot(
            status=REQ_OPEN if is_open else REQ_RESOLVED,
            is_open=is_open,
            target_revision_no=req.target_revision_no,
            requested_at=req.requested_at,
            requested_by=req.requested_by,
            note=req.note,
            files=req.files,
            target_drawing_keys=req.target_drawing_keys,
            legacy_seq=req.legacy_seq,
        ))
    has_open_request = any(r.is_open for r in resolved_requests)

    # 3) customer-confirm 대상: receipt revision(없으면 current revision).
    cust_confirmed, cust_at, cust_by = _customer_confirm(sd)
    customer_revno: Optional[int] = None
    if cust_confirmed and revisions:
        customer_revno = receipt_revno if receipt_revno is not None else current_revno

    # 4) revision status/flag 확정.
    final_revisions: List[DrawingRevisionSnapshot] = []
    for rev in revisions:
        revno = rev["revision_no"]
        is_current = revno == current_revno
        is_receipt = receipt_revno is not None and revno == receipt_revno
        is_customer = customer_revno is not None and revno == customer_revno
        if is_current:
            if has_open_request:
                status = REV_RETURNED
            elif is_receipt:
                status = REV_CONFIRMED
            else:
                status = REV_TRANSFERRED
        else:
            status = REV_SUPERSEDED
        final_revisions.append(DrawingRevisionSnapshot(
            revision_no=revno,
            status=status,
            is_current=is_current,
            is_receipt=is_receipt,
            is_customer_confirmed=is_customer,
            transferred_at=rev["transferred_at"],
            transferred_by=rev["transferred_by"],
            note=rev["note"],
            files=rev["files"],
            receipt_confirmed_at=receipt_at if is_receipt else None,
            receipt_confirmed_by=receipt_by if is_receipt else None,
            customer_confirmed_at=cust_at if is_customer else None,
            customer_confirmed_by=cust_by if is_customer else None,
            legacy_seq=rev["legacy_seq"],
        ))

    return DrawingRevisionPlan(
        order_id=order_id,
        revisions=tuple(final_revisions),
        requests=tuple(resolved_requests),
    )


def _ambiguous(
    order_id: Any,
    drawing_status: str,
    transfer_count: int,
    open_request_count: int,
    history: Any,
    reason: str,
) -> AmbiguousDrawing:
    """ambiguous 레코드 구성(history 는 원문 그대로 스냅샷 — 수동 검토용)."""
    return AmbiguousDrawing(
        order_id=order_id,
        drawing_status=drawing_status,
        transfer_count=transfer_count,
        open_request_count=open_request_count,
        history=copy.deepcopy(history) if isinstance(history, (list, dict)) else history,
        reason=reason,
    )


def iter_orders(session: Any, *, batch_size: int = 1000) -> Iterable[Any]:
    """모든 주문 row 를 스트리밍(read-only, 전수 coverage)."""
    from models import Order

    for order in session.query(Order).order_by(Order.id).yield_per(batch_size):
        yield order


def audit_drawing_revisions(session: Any, *, batch_size: int = 1000) -> DrawingRevisionAudit:
    """전체 주문을 분류해 SAFE plan·ambiguous·in-flight 집합을 만든다(mutation 0).

    Args:
        session: SQLAlchemy Session(read-only 로만 사용).
        batch_size: 스트리밍 yield_per 크기.

    Returns:
        :class:`DrawingRevisionAudit`.
    """
    safe: List[DrawingRevisionPlan] = []
    ambiguous: List[AmbiguousDrawing] = []
    in_flight: set[int] = set()
    for order in iter_orders(session, batch_size=batch_size):
        if _drawing_status(_structured(order)) in _ACTIVE_DRAWING_STATUS:
            in_flight.add(order.id)
        result = classify_order(order)
        if isinstance(result, DrawingRevisionPlan):
            safe.append(result)
        elif isinstance(result, AmbiguousDrawing):
            ambiguous.append(result)
    safe.sort(key=lambda p: p.order_id)
    ambiguous_sorted = tuple(sorted(ambiguous, key=lambda a: a.order_id))
    return DrawingRevisionAudit(tuple(safe), ambiguous_sorted, frozenset(in_flight))


def to_manual_csv(audit: DrawingRevisionAudit) -> str:
    """ambiguous 주문을 수동 매핑용 CSV 문자열로 내보낸다(header 포함).

    Args:
        audit: :func:`audit_drawing_revisions` 결과.

    Returns:
        ``order_id,drawing_status,transfer_count,open_request_count,legacy_history_json,
        decision,reason,approved_by_user_id`` CSV(ambiguous 행만·자동 매핑 0·target 공란).
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "order_id", "drawing_status", "transfer_count", "open_request_count",
        "legacy_history_json", "decision", "reason", "approved_by_user_id",
    ])
    for ref in audit.ambiguous:
        writer.writerow([
            ref.order_id,
            ref.drawing_status,
            ref.transfer_count,
            ref.open_request_count,
            json.dumps(ref.history, ensure_ascii=False, default=str),
            "MANUAL",      # decision: 사람이 결정(자동 발급 금지).
            ref.reason,
            "",            # approved_by_user_id: 승인 전.
        ])
    return buf.getvalue()


__all__ = [
    "ACTION_TRANSFER",
    "ACTION_REQUEST",
    "ACTION_RECEIPT",
    "REV_TRANSFERRED",
    "REV_RETURNED",
    "REV_CONFIRMED",
    "REV_SUPERSEDED",
    "REQ_OPEN",
    "REQ_RESOLVED",
    "MALFORMED",
    "NO_TRANSFER",
    "STATUS_MISMATCH",
    "DUPLICATE_OPEN",
    "DrawingRevisionSnapshot",
    "DrawingRequestSnapshot",
    "DrawingRevisionPlan",
    "AmbiguousDrawing",
    "DrawingRevisionAudit",
    "classify_order",
    "audit_drawing_revisions",
    "to_manual_csv",
]
