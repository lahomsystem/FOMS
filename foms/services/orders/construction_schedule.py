"""시공일 · 시공시간 한 번 쓰기 — 출고 화면 협력사 희망 판과 출고팀 주문 화면 시공일 칸이 같이 쓴다.

설계서 ``docs/specs/2026-11-04-shipment-partner-request-board_SPEC.md`` §2.3 · §2.3-b.

정본은 ``structured_data.schedule.construction.{date, time}`` 이다. 일정 줄 · ``CONSTRUCTION_DATE_CHANGED`` 이벤트 ·
대시보드 캐시 · 협력사 "시공일 안내" 푸시는 전역 before_flush 훅(``order_date_sync``)이 맡으므로 여기서 부르지
않는다. 여기서 하는 일은 대시보드 칸 쓰기(``foms/api/orders/field_update.py`` ``scheduled_date``)와 같은 순서다:
도면팀 · 생산팀 알림(apply) → 변경 원장. 감사 · 커밋 · 알림 finalize 는 부르는 라우트가 한다.
"""
from __future__ import annotations

import copy
import datetime
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from foms.services.datetime_kst import format_datetime_kst, get_today_kst, now_utc_naive
from foms.services.error_logging import log_handled_exception
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.feature_flags import is_item_construction_done_enabled
from foms.services.notifications.drawing_order_change import (
    apply_drawing_order_change_alert,
    finalize_drawing_order_change_alert,
)
from foms.services.notifications.production_change import (
    apply_production_change_alert,
    finalize_production_change_alert,
)
from foms.services.orders.change_reason import is_reason_required
from foms.services.orders.construction_dates import all_construction_dates, pick_nearest_date, split_date_text
from foms.services.orders.drawing_confirm_partial import is_item_cancelled
from foms.services.orders.item_construction_done import is_split_order, remaining_lines
from foms.services.orders.order_field_change_writer import record_field_changes
from foms.services.orders.state_axes import read_main_stage
from foms.services.orders.structured_diff import diff_structured
from foms.services.partners.schedule_request import REQUEST_CLOSED_STAGES, clean_date, request_open
from foms.services.production_change_alerts import _date_to_md

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
    #: 옮긴 날(``YYYY-MM-DD``) — 스위치가 켜져 날 하나만 옮겼을 때만. 꺼져 있거나 옮길 날이 없었으면 빈 글.
    from_date: str = ""


def _construction(sd: dict[str, Any]) -> dict[str, Any]:
    schedule = sd.get("schedule") if isinstance(sd.get("schedule"), dict) else {}
    construction = schedule.get("construction") if isinstance(schedule.get("construction"), dict) else {}
    return construction


#: 날짜 여럿을 한 칸에 적을 때의 이음 글 — 주문 칸 "2026-11-05, 2026-11-17" 과 같다.
DATE_JOIN = ", "

#: 고른 날이 주문 시공일에 없을 때(화면이 오래됐거나 다른 사람이 먼저 옮겼다).
FROM_DATE_MISSING_MESSAGE = "옮길 날을 다시 골라 주세요."


def _remaining_days(sd: Any) -> list[str]:
    """나눠 시공하는 주문의 남은 제품('시공 끝' 기록 없음) 날들(정렬). 나눠 시공이 아니거나 남은 날이 없으면 빈 목록."""
    if not isinstance(sd, dict) or not is_split_order(sd):
        return []
    return sorted({day for line in remaining_lines(sd) for day in line.dates if day})


def _text_order_days(sd: Any) -> list[str]:
    """주문 칸 글에 적힌 차례 그대로의 날들(정렬하지 않는다 · 못 읽는 토큰은 건너뛴다)."""
    raw = _construction(sd if isinstance(sd, dict) else {}).get("date")
    if raw is None or isinstance(raw, (dict, list, tuple, set, bool, int, float)):
        return []
    out: list[str] = []
    for token in str(raw).split(","):
        days = split_date_text(token)
        if days:
            out.append(days[0])
    return out


def first_order_date(sd: Any) -> str:
    """주문 칸(``schedule.construction.date``) 글에 **처음 적힌** 시공일(``YYYY-MM-DD``, 정렬하지 않는다). 없으면 빈 글.

    평면 칸 ``erp_construction_date``(``erp_display._normalize_date_to_yyyymmdd`` — 글 앞 날)와 같은 기준이라
    대시보드 칸 · 판에 보이는 첫 날과 같다. 나눠 시공하는 주문이면 남은 제품 날 가운데 글에 처음 적힌 날을 먼저
    고른다('시공 끝' 제품의 날은 옮기지 않는다). 남은 날이 없을 때만 위 규칙.
    """
    text_days = _text_order_days(sd)
    remaining = _remaining_days(sd)
    if remaining:
        for day in text_days:
            if day in remaining:
                return day
        return remaining[0]
    return text_days[0] if text_days else ""


def nearest_order_date(sd: Any, today: Any = None) -> str:
    """주문 칸 시공일 가운데 오늘 이후 가장 가까운 날(모두 지났으면 마지막 날). 주문 칸이 비면 제품 칸까지 본다."""
    sd = sd if isinstance(sd, dict) else {}
    days = split_date_text(_construction(sd).get("date")) or all_construction_dates(sd)
    picked = pick_nearest_date(days, today or get_today_kst())
    return picked.isoformat() if picked else ""


def visit_order_date(sd: Any, visit_day: datetime.date) -> str:
    """그 방문의 시공일 — 방문 날 이하에서 가장 늦은 주문 시공일, 없으면 그 뒤 가장 가까운 날. 날이 없으면 빈 글.

    나눠 시공하는 주문이면 남은 제품 날들 가운데에서 같은 규칙으로 먼저 고른다('시공 끝' 제품의 날은 옮기지 않는다).
    """
    days = _remaining_days(sd) or split_date_text(_construction(sd if isinstance(sd, dict) else {}).get("date"))
    limit = visit_day.isoformat()
    before = [day for day in days if day <= limit]
    if before:
        return before[-1]
    return days[0] if days else ""


def one_day_move_applies(sd: Any) -> bool:
    """날 하나만 옮기기를 할 주문인가 — 스위치 켜짐 · 주문 칸에 시공일 있음 · 나눠 시공하는 주문(``is_split_order``).

    이틀 연속처럼 제품 칸 날짜가 없는 주문은 나눠 시공이 아니라 지금처럼 주문 칸을 통째로 바꾼다.
    주문 칸이 비어 있으면 제품 칸은 건드리지 않고 지금처럼 쓴다.
    """
    sd = sd if isinstance(sd, dict) else {}
    return (is_item_construction_done_enabled() and bool(split_date_text(_construction(sd).get("date")))
            and is_split_order(sd))


def sync_items_for_whole_write(sd: dict[str, Any], new_value: Any) -> bool:
    """주문 칸을 통째로 쓰기 **전에** 부른다 — 나눠 시공이 아닌 주문이면 날이 적힌 제품 칸도 같은 값으로 쓴다.

    나눠 시공이 아니면 모든 제품의 마지막 날이 같아 일정이 같다. 주문 칸만 새 날이 되고 날이 적힌 제품 칸이 옛 날에
    머물면, 날을 물려받는 다른 제품과 마지막 날이 갈려 ``is_split_order`` 가 참이 된다(거짓 나눠 시공 — 보통 주문인데
    완료 창이 "오늘 끝낸 제품"을 요구한다). 취소 안 됐고 ``construction_date`` 가 비지 않은 제품만 쓴다. 비우는
    쓰기(되돌리기)면 제품 칸도 비운다. 주문 칸이 비어 있어도 같다. 스위치가 꺼졌거나 쓰기 직전 이미 나눠 시공인
    주문이면 손대지 않는다.

    :returns: 제품 칸을 고쳤는가.
    """
    if not is_item_construction_done_enabled() or not isinstance(sd, dict):
        return False
    if is_split_order(sd):  # 쓰기 직전 이미 나눠 시공인 주문은 제품 칸 그대로(주문 칸이 비어 있어도)
        return False
    text = str(new_value if new_value is not None else "")
    changed = False
    for item in sd.get("items") or []:
        if not isinstance(item, dict) or is_item_cancelled(item):
            continue
        if str(item.get("construction_date") or "").strip() and item.get("construction_date") != text:
            item["construction_date"] = text
            changed = True
    return changed


def _replace_day(days: list[str], from_day: str, to_day: str) -> str:
    """날 목록에서 ``from_day`` 를 ``to_day`` 로 바꾼 글(중복 제거 · 정렬). ``to_day`` 가 비면 그 날만 뺀다."""
    moved = {to_day if day == from_day else day for day in days}
    moved.discard("")
    return DATE_JOIN.join(sorted(moved))


def _date_lists(sd: dict[str, Any]) -> tuple:
    """주문 칸 · 제품 칸마다 읽은 날 목록 — 옮기기 전후가 같은지 견준다(표기만 다른 것은 같다)."""
    items = [item for item in (sd.get("items") or []) if isinstance(item, dict)]
    return (tuple(split_date_text(_construction(sd).get("date"))),
            tuple(tuple(split_date_text(item.get("construction_date"))) for item in items))


def move_construction_date(sd: dict[str, Any], *, from_date: Any, to_date: str, today: Any = None) -> str:
    """'어느 날을 어느 날로' — 이미 복사한 ``sd`` 의 시공일 하나만 옮긴다(제자리 수정 · 순수 함수, 설계서 8절 N8).

    * 주문 칸이 비었거나 나눠 시공하는 주문(``is_split_order``)이 아니면 지금처럼 주문 칸을 ``to_date`` 로 통째로
      바꾸고 제품 칸은 두며 빈 글을 돌려준다.
    * 나눠 시공하는 주문: 주문 칸 날짜 목록에서 ``from_date`` 하나만 ``to_date`` 로 바꾸고, 그 날이 적힌 제품 칸
      ``items[].construction_date`` 도 같이 바꾼다. 다른 날은 그대로(중복 제거 · 정렬 · ``", "`` 로 잇는다).
    * ``from_date`` 가 비고 ``to_date`` 가 이미 날 목록에 있으면 날은 그대로 둔다(시간만 바꾸기).
      ``from_date`` 만 비면 오늘 이후 가장 가까운 날(:func:`nearest_order_date`).
    * 옮기기 전후 날 목록이 같으면 원래 글로 되돌린다 — 바뀜 기록 · 알림이 생기지 않는다(빈 글을 돌려준다).

    :raises ScheduleInputError: ``from_date`` 가 이 주문의 시공일이 아닐 때.
    :returns: 옮긴 날(``YYYY-MM-DD``). 통째로 바꿨거나 날이 그대로면 빈 글.
    """
    if not isinstance(sd.get("schedule"), dict):
        sd["schedule"] = {}
    if not isinstance(sd["schedule"].get("construction"), dict):
        sd["schedule"]["construction"] = {}
    construction = sd["schedule"]["construction"]
    order_days = split_date_text(construction.get("date"))
    if not order_days or not is_split_order(sd):
        sync_items_for_whole_write(sd, to_date)
        construction["date"] = to_date
        return ""
    known = set(all_construction_dates(sd)) | set(order_days)
    if str(from_date or "").strip():
        from_day = clean_date(from_date)
        if not from_day or from_day not in known:
            raise ScheduleInputError(FROM_DATE_MISSING_MESSAGE)
    elif to_date in known:
        return ""
    else:
        from_day = nearest_order_date(sd, today)
    before = _date_lists(sd)
    items = [item for item in (sd.get("items") or []) if isinstance(item, dict)]
    original_order = construction.get("date")
    original_items = [(item, "construction_date" in item, item.get("construction_date")) for item in items]
    if from_day in order_days:
        construction["date"] = _replace_day(order_days, from_day, to_date)
    for item in items:
        item_days = split_date_text(item.get("construction_date"))
        if from_day in item_days:
            item["construction_date"] = _replace_day(item_days, from_day, to_date)
    if _date_lists(sd) == before:
        construction["date"] = original_order
        for item, had_key, text in original_items:
            if had_key:
                item["construction_date"] = text
        return ""
    return from_day


def move_preview_day(sd: Any, current: str) -> str:
    """AI 미리보기 '시공 날짜' 앞 칸 — 나눠 시공하는 주문이면 실행기가 옮길 날(오늘 이후 가장 가까운 날), 아니면 그대로."""
    return (nearest_order_date(sd) or current) if one_day_move_applies(sd) else current


def move_landed(current_text: str, date: str) -> bool:
    """AI 실행 끝남 확인 — 주문 칸이 새 날과 같다. 스위치가 켜져 있으면 새 날이 날 목록에 있으면 된다(다른 날이 남는다)."""
    if current_text == date:
        return True
    return bool(date) and is_item_construction_done_enabled() and date in split_date_text(current_text)


def move_first_date_for_field(sd: dict[str, Any], value: Any) -> str | None:
    """대시보드 시공일 칸(``field_update`` ``scheduled_date``) — 칸에 보이는 첫 날 하나만 ``value`` 로 옮긴다.

    날 하나만 옮기기를 할 주문이 아니거나(:func:`one_day_move_applies`) ``value`` 가 날 하나가 아니면
    (빈 값 · 여러 날 · 못 읽는 글) 주문 칸은 고치지 않고 ``None`` — 부르는 쪽이 지금처럼 통째로 쓴다(나눠 시공이
    아닌 주문이면 날이 적힌 제품 칸은 여기서 같은 값으로 맞춘다 — :func:`sync_items_for_whole_write`).
    옮겼으면 옮긴 날(날이 그대로면 빈 글).
    """
    if not one_day_move_applies(sd):
        sync_items_for_whole_write(sd, value)
        return None
    days = split_date_text(value)
    if len(days) != 1:
        return None
    return move_construction_date(sd, from_date=first_order_date(sd), to_date=days[0])


def reschedule_text_after_fail(sd: dict[str, Any], reschedule_date: Any, visit_started_at: Any = None) -> Any:
    """[시공 불가] → 다시 잡기 — 주문 칸에 쓸 시공일 값(이미 복사한 ``sd`` 의 제품 칸도 같이 옮긴다).

    날 하나만 옮기기를 할 주문이 아니거나(:func:`one_day_move_applies`) 새 날이 ``YYYY-MM-DD`` 가 아니면 지금처럼
    받은 값을 그대로 돌려준다(아무것도 안 고친다). 그러면 그 방문의 시공일(:func:`visit_order_date` — 방문 줄
    ``started_at`` 의 한국 날짜 이하에서 가장 늦은 날, 없으면 그 뒤 가장 가까운 날) 하나만 새 날로 옮긴 글.
    """
    to_day = clean_date(reschedule_date)
    if not to_day or not one_day_move_applies(sd):
        sync_items_for_whole_write(sd, reschedule_date)  # 통째로 쓸 때 날이 적힌 제품 칸도 같이(나눠 시공 아님)
        return reschedule_date
    visit_text = format_datetime_kst(visit_started_at, "%Y-%m-%d") if visit_started_at else None
    visit_day = datetime.date.fromisoformat(visit_text) if visit_text else get_today_kst()
    move_construction_date(sd, from_date=visit_order_date(sd, visit_day), to_date=to_day)
    return sd["schedule"]["construction"].get("date") or to_day


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
    from_date: Any = None,
) -> ScheduleWrite:
    """잠근 주문에 시공일 · 시공시간을 쓴다(커밋 없음). 값 검사는 :func:`validate_schedule_input` 를 먼저 지난 값.

    :param keep_existing_time: 참이면 시공시간이 이미 있을 때 그대로 둔다(협력사 희망 판 — 처음 정하기만).
    :param from_date: 옮길 날(``YYYY-MM-DD``). 스위치가 켜져 있고 나눠 시공하는 주문이면(:func:`one_day_move_applies`)
        그 날 하나만 ``date`` 로 옮긴다(:func:`move_construction_date`, 비면 오늘 이후 가장 가까운 날 — 새 날이 이미
        날 목록에 있으면 날은 그대로 · 시간만). 아니면 무시하고 지금처럼 주문 칸을 ``date`` 로 통째로 바꾼다.
        ``date`` 가 비면(되돌리기) 늘 통째로 비운다.
    :raises ScheduleInputError: 스위치가 켜져 있고 ``from_date`` 가 이 주문의 시공일이 아닐 때.
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
    moved_from = ""
    to_day = date
    if date and one_day_move_applies(old_sd):  # 비우기(협력사 판 [되돌리기])는 늘 통째로
        moved_from = move_construction_date(sd, from_date=from_date, to_date=date)
        date = str(schedule["construction"].get("date") or "")
    else:
        sync_items_for_whole_write(sd, date)  # 스위치 켜짐 · 나눠 시공 아님 → 날이 적힌 제품 칸도 같은 값(되돌리기면 비움)
        schedule["construction"]["date"] = date
    schedule["construction"]["time"] = new_time

    actor_id = getattr(user, "id", None)
    actor_name = getattr(user, "name", None) or "SYSTEM"
    notifications: list[tuple[str, Any, bool]] = []
    try:
        notif, created = apply_drawing_order_change_alert(
            db, order, old_sd, sd, actor_user_id=actor_id, actor_name=actor_name,
            old_notes=getattr(order, "notes", None), new_notes=getattr(order, "notes", None),
            old_is_regional=getattr(order, "is_regional", None), new_is_regional=getattr(order, "is_regional", None),
            old_construction_type=getattr(order, "construction_type", None),
            new_construction_type=getattr(order, "construction_type", None),
        )
        notifications.append(("drawing", notif, created))
    except Exception:  # noqa: BLE001 — 도면팀 알림 실패가 시공일 저장을 막으면 안 된다(field_update 와 같다)
        log_handled_exception("construction schedule drawing alert")
    if before_date != date or (moved_from and moved_from != to_day):
        if moved_from:  # 날 하나만 옮겼다 — 알림 글도 "어느 날 → 어느 날"
            change_text = f"{_date_to_md(moved_from)} → {_date_to_md(to_day or None)}"
        else:
            change_text = f"{_date_to_md(before_date or None)} → {_date_to_md(date or None)}"
        try:
            notif, created = apply_production_change_alert(
                db, order, "construction_date", change_text,
                actor_user_id=actor_id, actor_name=actor_name,
            )
            notifications.append(("production", notif, created))
        except Exception:  # noqa: BLE001 — 생산팀 알림 실패도 저장을 막지 않는다
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
        notifications=notifications, from_date=moved_from,
    )


def finalize_schedule_notifications(db, result: ScheduleWrite) -> None:
    """커밋 뒤 — 도면팀 · 생산팀 알림 푸시 · 배지(field_update 의 finalize 와 같다)."""
    for kind, notif, created in result.notifications:
        try:
            if kind == "drawing":
                finalize_drawing_order_change_alert(db, notif, created_new=created)
            else:
                finalize_production_change_alert(db, notif, created_new=created)
        except Exception:  # noqa: BLE001 — 커밋은 끝났다, 알림 마무리 실패는 기록만
            log_handled_exception("construction schedule notify finalize")


class ScheduleConflict(RuntimeError):
    """다른 사람이 먼저 정했거나 더는 정할 수 없는 주문(409)."""


def confirm_partner_request(db, order: Any, user: Any, *, date: Any, time: Any) -> ScheduleWrite:
    """출고 화면 협력사 희망 판 [확정] — 잠근 협력사 주문의 첫 시공일(설계서 §2.3).

    부르는 쪽이 ``lock_order_row`` 로 잠그고 협력사 주문인지 본다. 이미 시공일이 있거나 시공이 시작된
    단계면 :class:`ScheduleConflict`. 시공시간이 이미 있으면 그대로 둔다(바꾸면 사유 대상이 된다).
    """
    clean, text = validate_schedule_input(date, time)
    sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    if str(getattr(order, "erp_construction_date", "") or "").strip() or not request_open(sd, order.erp_stage_code or ""):
        raise ScheduleConflict("다른 사람이 먼저 시공일을 정했어요.")
    # 판에 보이는 첫 날 — 확정 대기 주문은 보통 비어 있어 옮길 날 없이 지금처럼 쓴다(설계서 8절).
    return write_construction_schedule(db, order, user, date=clean, time=text, keep_existing_time=True,
                                       from_date=first_order_date(sd))


def revert_to_partner_request(db, order: Any, user: Any) -> ScheduleWrite:
    """출고 화면 '최근 정한 기록' [되돌리기] — 잠근 협력사 주문의 시공일 · 시공시간을 지워 확정 대기로 돌린다.

    협력사 희망 시공일(``partner_intake.requested_construction``)은 그대로라 판에 다시 뜬다. 시공일이 이미 없거나
    시공이 시작된 단계면 :class:`ScheduleConflict`. 협력사 "시공일 취소" 알림은 전역 훅(``notify_listeners``)이 한다.
    """
    sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    if not _construction(sd).get("date") or not str(getattr(order, "erp_construction_date", "") or "").strip():
        raise ScheduleConflict("이미 확정 대기예요.")
    if (order.erp_stage_code or "").upper() in REQUEST_CLOSED_STAGES:
        raise ScheduleConflict("시공이 시작된 주문은 되돌릴 수 없어요.")
    # 확정 대기로 돌리므로 주문 칸을 통째로 비운다(날 하나 옮기기 · 스위치와 상관없음).
    return write_construction_schedule(db, order, user, date="", time="")
