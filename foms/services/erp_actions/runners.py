"""ERP 할 일 실행기 — services 만으로 도는 것(설계서 2026-11-14-foms-graft 3.3 · 3.4 · 3.11 ``SERVICE_RUNNERS``).

실행기는 승인 ②걸음이다(:func:`.lifecycle.approve` 가 권한 · 줄 잠금 전 검사를 끝내고 ``executing`` 을 커밋한 뒤 부른다).
**감싼 길과 같은 차례**를 탄다: 줄 잠금 → 검사(:func:`.preview.check` 를 잠금 아래에서 다시) → 쓰기(감싼 서비스 함수) →
감사 줄(감싼 길과 같은 ``action`` · 같은 칸 + ``source = 'erp_action:<제안 번호>'``) → 커밋 → 알림 마무리. 감싼 기능의 커밋
방식을 바꾸지 않는다(알림톡 ``send_alimtalk`` 은 제 세션에서 스스로 커밋한다).

- 막힘(감싼 기능이 거절 — 주문이 바뀌지 않음)은 :meth:`RunOutcome.blocked` 로 돌려준다. 제안은 다시 ``open`` 이 된다.
- 감싼 기능이 예외를 내면 그대로 올린다 — 생명주기가 되감고 흔적(:func:`.preview.ran`)으로 실행 · 실패를 가른다.
- 감사 줄은 ``foms.web.auth.log_access`` 대신 ``SecurityLog`` 를 같은 트랜잭션에 직접 싣는다(층 방향 — 본보기
  ``foms/api/orders/measurement_visit.py``).
- 실행기 표는 이름 → 함수 한 곳(:data:`SERVICE_RUNNERS`). api 층 기능을 부르는 실행기는 ``foms/api/erp_action_runners.py``
  의 ``RUNNERS`` 에 더한다.
- 시험에서 바깥으로 나가는 것(알림톡 · 푸시)은 모두 가짜로 바꿔 끼운다 — 이 모듈은 알림톡을 :mod:`kakao_alimtalk` 모듈 속성으로
  부른다(바꿔 끼우기 한 곳).
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional

from foms.services import kakao_alimtalk
from foms.services.audit_message_display import describe_field_change, describe_order_action
from foms.services.audit_writer import normalize_security_detail
from foms.services.auth.partner_scope import is_partner_order
from foms.services.common.dashboard_cache import invalidate_all_dashboard_slice_caches
from foms.services.erp_actions import preview
from foms.services.erp_actions.registry import message as failure_message
from foms.services.error_logging import log_handled_exception
from foms.services.orders.as_cycle_service import ASCycleError, schedule_as_cycle
from foms.services.orders.as_log import append_system_log
from foms.services.orders.audit_order_context import order_audit_context
from foms.services.orders.change_reason import attach_reason
from foms.services.orders.construction_note import (
    NoteInputError,
    NoteWrite,
    add_construction_note,
    finalize_note_notifications,
    note_lines,
)
from foms.services.orders.construction_schedule import (
    ScheduleConflict,
    ScheduleInputError,
    ScheduleWrite,
    confirm_partner_request,
    finalize_schedule_notifications,
    validate_schedule_input,
    write_construction_schedule,
)
from foms.services.orders.revision import RevisionError, lock_order_row
from foms.services.shipment_as_recommendation_cache import invalidate_shipment_as_recommendation_cache
from models import Order, SecurityLog

logger = logging.getLogger(__name__)

__all__ = [
    "OUTCOME_BLOCKED", "OUTCOME_EXECUTED", "OUTCOME_FAILED", "RunOutcome", "RunRequest", "Runner", "SERVICE_RUNNERS",
    "run_add_construction_note", "run_move_construction", "run_schedule_as_visit", "run_schedule_construction",
    "run_send_measure_alimtalk",
]

OUTCOME_EXECUTED, OUTCOME_BLOCKED, OUTCOME_FAILED = "executed", "blocked", "failed"


@dataclass(frozen=True)
class RunRequest:
    """실행 한 번의 재료 — 제안 번호 · 할 일 · 주문 · 넣을 값(꼴 검사를 지난 것) · 승인한 사람 · 사유."""

    proposal_id: int
    action: str
    order_id: int
    params: Mapping[str, Any]
    actor: Any
    reason_code: Optional[str] = None
    reason_note: Optional[str] = None
    now: Optional[datetime.datetime] = None

    @property
    def source(self) -> str:
        """감사 줄 · 주문 기록의 출처 표식 ``erp_action:<제안 번호>``."""
        return f"erp_action:{int(self.proposal_id)}"

    @property
    def actor_id(self) -> Optional[int]:
        """승인한 사람 번호."""
        value = getattr(self.actor, "id", None)
        return int(value) if value is not None else None

    def idempotency_key(self) -> str:
        """REV-00 영수증 열쇠 — 제안 번호 + 넣을 값 지문(같은 제안 · 같은 값의 다시 실행은 두 번 쓰지 않는다)."""
        blob = json.dumps(dict(self.params), sort_keys=True, ensure_ascii=False, default=str)
        return f"erp-action-{int(self.proposal_id)}-{hashlib.sha256(blob.encode('utf-8')).hexdigest()[:12]}"


@dataclass(frozen=True)
class RunOutcome:
    """실행 결과 — ``status``(executed · blocked · failed) · 코드 · 화면 말(코드가 정한 말) · 결과(코드 · 수 · 번호만)."""

    status: str
    code: str
    message: str
    result: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def executed(cls, message: str, **result: Any) -> "RunOutcome":
        """실행됨."""
        return cls(OUTCOME_EXECUTED, "OK", message, dict(result))

    @classmethod
    def blocked(cls, message: str, code: str = "ACTION_PRECONDITION", **result: Any) -> "RunOutcome":
        """감싼 기능이 거절함 — 주문은 바뀌지 않았다."""
        return cls(OUTCOME_BLOCKED, code, message, dict(result))

    @classmethod
    def failed(cls, code: str = "ACTION_FAILED", **result: Any) -> "RunOutcome":
        """실행하려 했으나 이루지 못함(바깥 보내기 실패 등)."""
        return cls(OUTCOME_FAILED, code, failure_message(code), dict(result))


Runner = Callable[[Any, RunRequest], RunOutcome]


def _locked_checked(session: Any, req: RunRequest) -> tuple[Optional[Any], Optional[RunOutcome]]:
    """줄 잠금 → 잠금 아래에서 막는 조건 다시 보기. 막히면 (None, 막힘 결과) — 되감은 뒤."""
    order = lock_order_row(session, req.order_id)
    problem = preview.check(req.action, order, req.params)
    if problem:
        session.rollback()
        return None, RunOutcome.blocked(problem)
    return order, None


def _add_audit(session: Any, req: RunRequest, order: Any, *, action: str, message: str, detail: dict) -> None:
    """감싼 길과 같은 감사 줄을 본 트랜잭션에 싣는다(출처 표식 ``source`` 를 더한다)."""
    session.add(SecurityLog(
        user_id=req.actor_id, message=message, action=action, target_type="order", target_id=int(order.id),
        detail=normalize_security_detail({**detail, "source": req.source}),
    ))


# ── 시공 잡기 · 방문 옮기기(시공) ─────────────────────────────────────────
def _attach_reason(session: Any, order: Any, result: ScheduleWrite, req: RunRequest) -> bool:
    """사유를 물을 변경이고 승인 창에서 사유를 받았으면 지금 사유 원장에 남긴다(같은 트랜잭션)."""
    if not (result.reason_required and req.reason_code):
        return False
    session.flush()  # 원장 줄을 같은 변경 묶음으로 찾으려면(autoflush 꺼진 세션) 먼저 내보낸다
    role = str(getattr(req.actor, "role", "") or "").strip().upper()
    attach_reason(session, order_id=int(order.id), change_set_id=result.change_set_id, code=req.reason_code,
                  note=req.reason_note, actor_user_id=req.actor_id, is_admin=role == "ADMIN")
    return True


def _audit_schedule(session: Any, order: Any, result: ScheduleWrite, req: RunRequest) -> None:
    """시공일 쓰기 감사 — 출고 화면 · 주문 화면 길(``ORDER_FIELD_UPDATED`` · ``scheduled_date``)과 같은 칸."""
    context = order_audit_context(order)
    message = describe_field_change(order_id=order.id, field="scheduled_date", before=result.before_date,
                                    after=result.date, has_before=True, **context)
    _add_audit(session, req, order, action="ORDER_FIELD_UPDATED", message=message, detail={
        "field": "scheduled_date", "before": result.before_date, "after": result.date, "time": result.time,
        "change_set": result.change_set_id, "change_count": result.change_count, **context})


def _write_schedule(session: Any, order: Any, req: RunRequest, *, first: bool) -> ScheduleWrite:
    """협력사 주문의 첫 시공일은 희망 확정 길, 그 밖은 시공일 쓰기 길(값 검사 먼저)."""
    if first and is_partner_order(order):
        return confirm_partner_request(session, order, req.actor, date=req.params.get("date"),
                                       time=req.params.get("time", ""))
    day, time = validate_schedule_input(req.params.get("date"), req.params.get("time"))
    return write_construction_schedule(session, order, req.actor, date=day, time=time)


def _run_schedule(session: Any, req: RunRequest, *, first: bool) -> RunOutcome:
    """시공일 쓰기 실행 — 잠금 → 검사 → 쓰기 → 사유 → 감사 → 커밋 → 도면팀 · 생산팀 알림 마무리."""
    order, stop = _locked_checked(session, req)
    if stop is not None:
        return stop
    try:
        result = _write_schedule(session, order, req, first=first)
        attached = _attach_reason(session, order, result, req)
        _audit_schedule(session, order, result, req)
        session.commit()
    except (ScheduleInputError, ScheduleConflict) as exc:
        session.rollback()
        return RunOutcome.blocked(str(exc))
    finalize_schedule_notifications(session, result)
    return RunOutcome.executed(
        "시공일을 정했어요." if first else "시공일을 옮겼어요.", change_set=result.change_set_id,
        change_count=result.change_count, before_date=result.before_date, date=result.date, time=result.time,
        reason_required=result.reason_required, reason_attached=attached)


def run_schedule_construction(session: Any, req: RunRequest) -> RunOutcome:
    """시공 잡기(시공일이 빈 주문) — 협력사 주문은 ``confirm_partner_request``."""
    return _run_schedule(session, req, first=True)


def run_move_construction(session: Any, req: RunRequest) -> RunOutcome:
    """방문 옮기기(시공일이 이미 있는 주문) — 사유가 필요한 변경이면 승인 창 사유를 원장에."""
    return _run_schedule(session, req, first=False)


# ── 방문 옮기기(AS) ──────────────────────────────────────────────────────
def _sha(value: Any) -> str:
    blob = value if isinstance(value, str) else json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _invalidate_as_caches() -> None:
    """AS 일정 커밋 뒤 대시보드 · AS 추천 캐시 비우기(AS 방문일 길과 같은 두 가지 — 실패는 기록만)."""
    try:
        invalidate_all_dashboard_slice_caches()
    except Exception:  # noqa: BLE001 — 캐시 비우기 실패가 저장 결과를 바꾸지 않는다
        log_handled_exception("erp action as dashboard cache")
    try:
        invalidate_shipment_as_recommendation_cache(reason="erp_action_as_schedule")
    except Exception:  # noqa: BLE001 — 위와 같다
        log_handled_exception("erp action as recommendation cache")


def run_schedule_as_visit(session: Any, req: RunRequest) -> RunOutcome:
    """방문 옮기기(AS) — AS 방문일 길(``schedule_as_cycle`` · 타임라인 한 줄 · ``AS_SCHEDULED`` 감사)과 같은 차례."""
    order = session.get(Order, req.order_id)
    problem = preview.check(req.action, order, req.params)
    if problem:
        session.rollback()
        return RunOutcome.blocked(problem)
    day = str(req.params.get("date"))
    try:
        schedule_as_cycle(
            session, order_id=int(order.id), actor_user_id=req.actor_id, visit_date=day, visit_time=None,
            cycle_id=None, scope_hash=_sha(f"AS_SCHEDULE:{int(order.id)}"),
            request_hash=_sha({"visit_date": day, "visit_time": "", "source": req.source}),
            idempotency_key=req.idempotency_key(),
            sd_hook=lambda sd: append_system_log(sd, text=f"방문일 확정: {day}"), legacy_bridge=True)
    except ASCycleError as exc:
        session.rollback()
        return RunOutcome.blocked(str(exc))
    except (ValueError, RevisionError):
        session.rollback()
        return RunOutcome.blocked(failure_message("ACTION_PRECONDITION"))
    context = order_audit_context(order)
    _add_audit(session, req, order, action="AS_SCHEDULED", detail={"visit_date": day, **context},
               message=describe_order_action(order_id=order.id, action="AS_SCHEDULED", note=day, **context))
    session.commit()
    _invalidate_as_caches()
    return RunOutcome.executed("AS 방문일을 정했어요.", visit_date=day)


# ── 알림톡 보내기(실측 예약) ─────────────────────────────────────────────
def run_send_measure_alimtalk(session: Any, req: RunRequest) -> RunOutcome:
    """실측 예약 알림톡 — 손으로 보내기 길(설정 확인 → 활성 주문 → ``send_alimtalk`` → 감사)과 같은 차례.

    중복 막기 열쇠는 ``alimtalk:measure:<주문>:action:<제안 번호>`` — 같은 제안을 다시 실행해도 이미 나간 안내는 다시 보내지
    않는다(``send_alimtalk`` 의 이력 판정). 보내기는 알림톡 모듈이 제 세션에서 커밋한다.
    """
    if not kakao_alimtalk.is_configured():
        return RunOutcome.blocked("알림톡 설정이 없어 보낼 수 없어요.")
    order = session.query(Order).filter(Order.id == req.order_id, Order.active_filter()).first()
    problem = preview.check(req.action, order, req.params)
    if problem:
        session.rollback()
        return RunOutcome.blocked(problem)
    sent_result = kakao_alimtalk.send_alimtalk(
        int(order.id), manual_by=req.actor_id, dedupe_key=preview.alimtalk_action_key(order.id, req.proposal_id))
    session.expire(order)  # 보내기는 다른 세션에서 이력을 커밋했다 — 이 세션의 사본은 낡았다
    sent, error = bool(sent_result.get("sent")), sent_result.get("error")
    context = order_audit_context(order)
    _add_audit(session, req, order, action="ALIMTALK_MANUAL_SENT",
               detail={"sent": sent, "error": error, "template": "measure", **context},
               message=describe_order_action(order_id=order.id, action="ALIMTALK_MANUAL_SENT",
                                             note=None if sent else f"실패: {error}", **context))
    session.commit()
    if sent:
        return RunOutcome.executed("실측 예약 알림톡을 보냈어요.", sent=True)
    return RunOutcome.failed(sent=False, error=error)


# ── 시공 메모 더하기 ─────────────────────────────────────────────────────
def _audit_note(session: Any, order: Any, result: NoteWrite, req: RunRequest) -> None:
    """시공 메모 감사 — 칸 고치기 감사(``ORDER_FIELD_UPDATED``)와 같은 꼴. 메모 글은 싣지 않고 줄 수만."""
    after_lines = len(note_lines(order.structured_data))
    context = order_audit_context(order)
    message = describe_field_change(order_id=order.id, field="construction_note", before=f"{result.before_lines}줄",
                                    after=f"{after_lines}줄", has_before=True, **context)
    _add_audit(session, req, order, action="ORDER_FIELD_UPDATED", message=message, detail={
        "field": "construction_note", "before_lines": result.before_lines, "after_lines": after_lines,
        "change_set": result.change_set_id, "change_count": result.change_count, **context})


def run_add_construction_note(session: Any, req: RunRequest) -> RunOutcome:
    """시공 메모 한 줄 더하기 — 잠금 → 검사 → 쓰기(REV-00 · 판 번호 올림) → 감사 → 커밋 → 도면팀 알림 마무리."""
    order, stop = _locked_checked(session, req)
    if stop is not None:
        return stop
    try:
        result = add_construction_note(session, order, req.actor, line=req.params.get("note"))
        _audit_note(session, order, result, req)
        session.commit()
    except NoteInputError as exc:
        session.rollback()
        return RunOutcome.blocked(str(exc))
    finalize_note_notifications(session, result)
    return RunOutcome.executed("시공 메모를 더했어요.", change_set=result.change_set_id,
                               change_count=result.change_count)


#: 실행기 표 — services 만으로 도는 것(채널톡 작은 창도 이 표를 쓴다). api 층 실행기는 ``foms/api/erp_action_runners.py``.
SERVICE_RUNNERS: dict[str, Runner] = {
    "schedule_construction": run_schedule_construction,
    "move_construction": run_move_construction,
    "schedule_as_visit": run_schedule_as_visit,
    "send_measure_alimtalk": run_send_measure_alimtalk,
    "add_construction_note": run_add_construction_note,
}
