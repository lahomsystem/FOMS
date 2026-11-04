"""시공일 · 시공시간 한 번 쓰기 — 출고 화면 협력사 희망 판과 출고팀 주문 화면 시공일 칸이 같이 쓴다.

설계서 ``docs/specs/2026-11-04-shipment-partner-request-board_SPEC.md`` §2.3 · §2.3-b.

정본은 ``structured_data.schedule.construction.{date, time}`` 이다. 일정 줄 · ``CONSTRUCTION_DATE_CHANGED`` 이벤트 ·
대시보드 캐시 · 협력사 "시공일 안내" 푸시는 전역 before_flush 훅(``order_date_sync``)이 맡으므로 여기서 부르지
않는다. 여기서 하는 일은 대시보드 칸 쓰기(``foms/api/orders/field_update.py`` ``scheduled_date``)와 같은 순서다:
도면팀 · 생산팀 알림(apply) → 변경 원장. 감사 · 커밋 · 알림 finalize 는 부르는 라우트가 한다.
"""
from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.orders.change_reason import is_reason_required
from foms.services.orders.order_field_change_writer import record_field_changes
from foms.services.orders.state_axes import read_main_stage
from foms.services.orders.structured_diff import diff_structured
from foms.services.partners.schedule_request import clean_date

#: 판 · 주문 화면에서 고르는 시공시간(주문 화면의 '직접 입력'은 CS · 영업 폼 저장으로만).
TIME_CHOICES = ("", "오전", "오후", "종일")


class ScheduleInputError(ValueError):
    """날짜 · 시간 값이 틀렸다(400)."""


@dataclass
class ScheduleWrite:
    """쓰기 결과 — 라우트가 감사 · 커밋 · finalize 에 쓴다."""

    before_date: str
    before_time: str
    date: str
    time: str
    change_set_id: str
    change_count: int
    reason_required: bool
    notifications: list[tuple[str, Any, bool]] = field(default_factory=list)


def _construction(sd: dict[str, Any]) -> dict[str, Any]:
    schedule = sd.get("schedule") if isinstance(sd.get("schedule"), dict) else {}
    construction = schedule.get("construction") if isinstance(schedule.get("construction"), dict) else {}
    return construction


def validate_schedule_input(date: Any, time: Any) -> tuple[str, str]:
    """날짜는 'YYYY-MM-DD' 이고 오늘 이후, 시간은 :data:`TIME_CHOICES` 중 하나."""
    clean = clean_date(date)
    if not clean:
        raise ScheduleInputError("시공일을 골라 주세요.")
    if clean < get_today_kst().isoformat():
        raise ScheduleInputError("지난 날짜예요.")
    text = str(time if time is not None else "").strip()
    if text not in TIME_CHOICES:
        raise ScheduleInputError("시간은 오전 · 오후 · 종일 중에서 골라 주세요.")
    return clean, text


def write_construction_schedule(
    db,
    order: Any,
    user: Any,
    *,
    date: str,
    time: str,
    keep_existing_time: bool = False,
) -> ScheduleWrite:
    """잠근 주문에 시공일 · 시공시간을 쓴다(커밋 없음). 값 검사는 :func:`validate_schedule_input` 를 먼저 지난 값.

    :param keep_existing_time: 참이면 시공시간이 이미 있을 때 그대로 둔다(협력사 희망 판 — 처음 정하기만).
    """
    old_sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    old_cons = _construction(old_sd)
    before_date = str(old_cons.get("date") or "").strip()
    before_time = str(old_cons.get("time") or "").strip()
    new_time = before_time if (keep_existing_time and before_time) else time

    sd = copy.deepcopy(old_sd)
    if not isinstance(sd.get("schedule"), dict):
        sd["schedule"] = {}
    schedule = sd["schedule"]
    if not isinstance(schedule.get("construction"), dict):
        schedule["construction"] = {}
    schedule["construction"]["date"] = date
    schedule["construction"]["time"] = new_time

    actor_id = getattr(user, "id", None)
    actor_name = getattr(user, "name", None) or "SYSTEM"
    notifications: list[tuple[str, Any, bool]] = []
    try:
        from foms.services.notifications.drawing_order_change import apply_drawing_order_change_alert

        notif, created = apply_drawing_order_change_alert(
            db, order, old_sd, sd, actor_user_id=actor_id, actor_name=actor_name,
            old_notes=getattr(order, "notes", None), new_notes=getattr(order, "notes", None),
            old_is_regional=getattr(order, "is_regional", None), new_is_regional=getattr(order, "is_regional", None),
            old_construction_type=getattr(order, "construction_type", None),
            new_construction_type=getattr(order, "construction_type", None),
        )
        notifications.append(("drawing", notif, created))
    except Exception:  # noqa: BLE001 — 도면팀 알림 실패가 시공일 저장을 막으면 안 된다(field_update 와 같다)
        from foms.services.error_logging import log_handled_exception

        log_handled_exception("construction schedule drawing alert")
    if before_date != date:
        try:
            from foms.services.notifications.production_change import apply_production_change_alert
            from foms.services.production_change_alerts import _date_to_md

            notif, created = apply_production_change_alert(
                db, order, "construction_date", f"{_date_to_md(before_date or None)} → {_date_to_md(date)}",
                actor_user_id=actor_id, actor_name=actor_name,
            )
            notifications.append(("production", notif, created))
        except Exception:  # noqa: BLE001 — 생산팀 알림 실패도 저장을 막지 않는다
            from foms.services.error_logging import log_handled_exception

            log_handled_exception("construction schedule production alert")

    order.structured_data = sd
    flag_modified(order, "structured_data")
    sync_erp_flat_columns(order, sd)
    order.structured_updated_at = now_utc_naive()

    changes = diff_structured(old_sd, sd, max_changes=-1).changes
    change_set_id = str(uuid.uuid4())
    count = record_field_changes(db, changes, order_id=int(order.id), actor_user_id=actor_id,
                                 change_set_id=change_set_id)
    return ScheduleWrite(
        before_date=before_date, before_time=before_time, date=date, time=new_time,
        change_set_id=change_set_id, change_count=count,
        reason_required=is_reason_required(changes, stage=read_main_stage(order)),
        notifications=notifications,
    )


def finalize_schedule_notifications(db, result: ScheduleWrite) -> None:
    """커밋 뒤 — 도면팀 · 생산팀 알림 푸시 · 배지(field_update 의 finalize 와 같다)."""
    for kind, notif, created in result.notifications:
        try:
            if kind == "drawing":
                from foms.services.notifications.drawing_order_change import finalize_drawing_order_change_alert

                finalize_drawing_order_change_alert(db, notif, created_new=created)
            else:
                from foms.services.notifications.production_change import finalize_production_change_alert

                finalize_production_change_alert(db, notif, created_new=created)
        except Exception:  # noqa: BLE001 — 커밋은 끝났다, 알림 마무리 실패는 기록만
            from foms.services.error_logging import log_handled_exception

            log_handled_exception("construction schedule notify finalize")


class ScheduleConflict(RuntimeError):
    """다른 사람이 먼저 정했거나 더는 정할 수 없는 주문(409)."""


def confirm_partner_request(db, order: Any, user: Any, *, date: Any, time: Any) -> ScheduleWrite:
    """출고 화면 협력사 희망 판 [확정] — 잠근 협력사 주문의 첫 시공일(설계서 §2.3).

    부르는 쪽이 ``lock_order_row`` 로 잠그고 협력사 주문인지 본다. 이미 시공일이 있거나 시공이 시작된
    단계면 :class:`ScheduleConflict`. 시공시간이 이미 있으면 그대로 둔다(바꾸면 사유 대상이 된다).
    """
    from foms.services.partners.schedule_request import request_open

    clean, text = validate_schedule_input(date, time)
    sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    if str(getattr(order, "erp_construction_date", "") or "").strip() or not request_open(sd, order.erp_stage_code or ""):
        raise ScheduleConflict("다른 사람이 먼저 시공일을 정했어요.")
    return write_construction_schedule(db, order, user, date=clean, time=text, keep_existing_time=True)
