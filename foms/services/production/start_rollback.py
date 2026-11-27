"""도면이 연 제작 시작 되돌리기 — 도면 [시작 취소] · [기본 취소] · [완료 취소] 뒤 저절로 제작 대기로(사장님 2026-11-27).

결정(글자 그대로): "그 주문에 잡혀 있거나 완료된 도면이 하나도 없게 되면, 도면으로 걸렸던 제작 시작도 같이 취소됩니다. '남은 공정' 숫자가
줄고 주문은 '제작 대기'로 돌아갑니다. 작업 시트에서 [제작 시작]을 일부러 누른 주문, 보류 중이거나 불량 기록이 있는 주문은 건드리지
않습니다." — 2026-11-23 설계서 §4-8 · §19 넷째("실수로 맡았다 취소해도 제작 중 그대로")를 뒤집는다.

부르는 곳은 도면 한 장 쓰기(``part_mark_write.mark_one``)뿐이다. 표시 줄이 미정이 되는 쓰기(시작 취소 · 대신 빼기 · 기본 취소 · 바로 완료한
도면의 완료 취소) 뒤에만 :func:`plan_start_rollback` 을 부르고, 되돌릴 것이 있으면 그 쓰기의 주문 쓰기 한 번
(``apply_order_changes`` 의 ``execute_order_mutation`` — 공정 칸 동기화와 같은 콜백 · 버전 +1 한 번)에서 :meth:`StartRollback.apply`
가 회차를 닫는다. 주문 행은 ``mark_one`` 이 처음부터 잠갔다(제작 시작과 같은 잠금) — 그사이 남이 다른 도면을 잡았으면 그 줄이 읽혀
되돌리지 않는다.

되돌리는 조건(모두 참일 때만 — 하나라도 아니면 지금처럼 회차 그대로):

1. 이번 쓰기 뒤 그 주문 **네 파트 표시 줄이 모두 미정**(옛 판 key 줄 포함 — :func:`cards_used` 가 빈 집합).
2. 보류 중 아님 · 수정 제작 중 아님 · 공장 완료 표지 없음.
3. 이번 쓰기 뒤 공정 칸 넷이 모두 꺼짐(이번 쓰기가 끌 칸까지 반영 — 손으로 켠 칸이 하나라도 남으면 되돌리지 않는다).
4. 지금 회차가 있고, 그 회차를 연 것이 **도면**(가장 최근 ``PRODUCTION_STARTED`` 의 ``via == 'part_marks'`` 이고 그 이벤트가 이 회차가
   열린 때보다 앞서지 않음). 작업 시트 [제작 시작] · 옛 회차(이벤트 없음) · 완료 취소가 새로 연 회차는 건드리지 않는다.
5. 그 회차가 열린 뒤 불량 기록 없음(때를 못 읽는 기록은 있는 것으로 본다).

1 ~ 3 은 쿼리 0(읽은 줄 · 잠근 주문). 4 · 5 는 1 ~ 3 을 통과한 취소 길에서만 읽기 2(회차 · 마지막 시작 이벤트) — 시작 · 완료 길은 0.

되돌리기 = 회차 닫기(``_supersede_production_run`` — [제작 시작 취소] API 와 같은 함수) + 단계 기록 "제작 시작 취소 (도면 작업 시작 취소)"
+ 이벤트 ``PRODUCTION_CANCELLED``(``via:'part_marks'``) + 감사 한 줄. 단계는 생산 그대로. [제작 시작 취소] API 가 같이 하는 보류 해제 ·
수정 제작 표지 끄기 · 공장 완료 표지 지우기는 하지 않는다(조건 2 가 이미 걸렀다). 알림 · '바뀐 것' 줄은 만들지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional

from foms.services.production import mark_crew
from foms.services.production.factory_marks import done_table
from foms.services.production.order_write_helpers import (
    _current_production_run,
    _hold_active,
    _is_rework_completion,
    _supersede_production_run,
)
from foms.services.production.part_constants import MARK_STATE_NONE
from foms.services.production.part_progress import cards_used
from foms.services.production.part_steps_sync import plan_part_step_changes
from foms.services.production.start_run import (
    CARD_CANCEL_NOTE,
    PRODUCTION_CANCEL_POLICY_ID,
    STARTED_EVENT,
    VIA_PART_MARKS,
    cancelled_event_values,
    card_cancel_audit_values,
    record_start_in_sd,
)
from foms.services.production.steps import step_done_map
from models import OrderEvent

#: 표시 감사 글 꼬리 — 첫 카드가 제작을 시작했을 때 / 표시가 모두 미정이 돼 그 시작을 되돌렸을 때(짝).
START_AUDIT_TAIL = " · 제작 시작"
ROLLBACK_AUDIT_TAIL = " · 제작 시작 취소"


@dataclass(frozen=True)
class StartRollback:
    """되돌릴 회차 하나 — 잠금 아래에서 판정을 마친 것(:func:`plan_start_rollback`)."""

    run: Any
    #: 주문 쓰기 영수증의 정책 id([제작 시작 취소] 단추와 같다).
    policy_id: str = PRODUCTION_CANCEL_POLICY_ID

    def apply(self, order: Any, sd: dict[str, Any], user: Any, events: list[dict[str, Any]],
              audits: list[dict[str, Any]]) -> None:
        """회차를 닫고 주문 쪽을 쓴다(``execute_order_mutation`` 콜백 안 — 버전은 그 콜백이 한 번 올린다).

        Args:
            order: 잠근 주문.
            sd: 호출자가 deepcopy · 공정 칸까지 고친 structured_data(여기서 주문에 다시 넣는다).
            user: 누른 사람.
            events: 이번 쓰기의 이벤트 줄 모음(``PRODUCTION_CANCELLED`` 한 줄을 더한다 — INSERT 는 호출자가 표마다 한 번).
            audits: 이번 쓰기의 감사 줄 모음(한 줄을 더한다).
        """
        run_id = _supersede_production_run(self.run)
        record_start_in_sd(order, sd, user, note=CARD_CANCEL_NOTE)  # 단계 기록 · 재대입 · flag_modified · 납작 칸(단계는 생산 그대로)
        events.append(cancelled_event_values(order.id, getattr(user, "id", None), run_id=run_id, via=VIA_PART_MARKS))
        audits.append(card_cancel_audit_values(order, user))


def _steps_off_after(sd: Any, marks: list[Any], parts: Iterable[str], cleared: Iterable[str]) -> bool:
    """이번 쓰기가 맞출 칸까지 반영해 공정 칸 넷이 모두 꺼지는지(쿼리 0 — 주문 쓰기와 같은 계획 함수)."""
    after = step_done_map(sd)
    after.update({change.key: change.done for change in plan_part_step_changes(sd, marks, parts, cleared)})
    return not any(after.values())


def _opened_by_cards(db: Any, order_id: int, run: Any) -> bool:
    """그 회차를 연 것이 도면인지 — 가장 최근 ``PRODUCTION_STARTED`` 가 도면 길이고 이 회차가 열린 때보다 앞서지 않음(쿼리 1)."""
    last = (db.query(OrderEvent.payload, OrderEvent.created_at)
            .filter(OrderEvent.order_id == int(order_id), OrderEvent.event_type == STARTED_EVENT)
            .order_by(OrderEvent.id.desc()).first())
    if last is None or run.started_at is None or last.created_at is None:
        return False
    payload = last.payload if isinstance(last.payload, dict) else {}
    return payload.get("via") == VIA_PART_MARKS and last.created_at >= run.started_at


def _defect_in_run(sd: Any, run: Any) -> bool:
    """그 회차가 열린 뒤 불량 기록이 있는지(쿼리 0). 때를 못 읽는 기록은 있는 것으로 본다(건드리지 않는 쪽)."""
    production = sd.get("production") if isinstance(sd, dict) else None
    defects = production.get("defects") if isinstance(production, dict) else None
    for defect in defects if isinstance(defects, list) else []:
        at = mark_crew.from_iso(defect.get("at")) if isinstance(defect, dict) else None
        if at is None or at >= run.started_at:
            return True
    return False


def plan_start_rollback(db: Any, order: Any, marks: list[Any], parts: Iterable[str],
                        cleared: Iterable[str] = (), *, target: str = MARK_STATE_NONE) -> Optional[StartRollback]:
    """표시 줄이 미정이 된 쓰기 뒤 — 도면이 연 제작 시작을 되돌릴지(모듈 머리말 조건 1 ~ 5). 쓰지는 않는다.

    Args:
        db: 세션(같은 tx — 주문 행은 이미 잠겨 있다).
        order: 잠근 주문(생산 단계임은 ``mark_one`` 이 이미 봤다).
        marks: 이번 쓰기를 반영한 그 주문 표시 줄 모습(네 파트 · 옛 판 key 포함).
        parts: 이번 쓰기가 공정 칸을 맞출 파트(누른 파트).
        cleared: 이번 쓰기로 완료 줄이 미정이 된 파트(``part_steps_after`` 와 같다).
        target: 이번 쓰기가 만든 줄 상태 — 미정이 아니면(시작 · 완료 · 기본) 아무것도 읽지 않고 None(쿼리 0).

    Returns:
        되돌릴 것(:class:`StartRollback`) 또는 None(지금처럼 회차 그대로).
    """
    if target != MARK_STATE_NONE:
        return None
    sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    if cards_used(marks) or _hold_active(sd)[0] or _is_rework_completion(sd) or done_table(sd):
        return None
    if not _steps_off_after(sd, marks, parts, cleared):
        return None
    run = _current_production_run(db, order.id)
    if run is None or not _opened_by_cards(db, order.id, run) or _defect_in_run(sd, run):
        return None
    return StartRollback(run)


def run_tail(started: Any, closing: Any) -> str:
    """표시 감사 글의 회차 꼬리 — 제작 시작 " · 제작 시작" / 되돌림 " · 제작 시작 취소" / 둘 다 아니면 빈 글."""
    return START_AUDIT_TAIL if started else ROLLBACK_AUDIT_TAIL if closing else ""


__all__ = ["ROLLBACK_AUDIT_TAIL", "START_AUDIT_TAIL", "StartRollback", "plan_start_rollback", "run_tail"]
