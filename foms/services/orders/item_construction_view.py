"""제품마다 '시공 끝' — 화면 쪽 판정(한 주문 여러 시공일 2단계, 설계서 6절).

설계: ``docs/specs/2026-11-21-item-construction-done_SPEC.md`` 6절 · 결정 N2 · N3 · N9.

자료 판정은 ``item_construction_done``(순수 함수)이 하고, 여기서는 그 결과를 화면 글 · 줄 표시로 바꾼다.
스위치(``is_item_construction_done_enabled``)가 꺼져 있거나 나눠 시공하는 주문이 아니면 모든 함수가
"바꿀 것 없음"(None · 빈 값 · 그대로)을 돌려준다 — 화면이 지금과 같다.

방문이 열려 있는지는 ``workflow.history`` 로 가른다: 마지막 "시공 시작" 줄 뒤에 "부분 시공 끝 …" 줄
(``PARTIAL_VISIT_NOTE_PREFIX`` — [오늘 시공 끝] 때 서버가 남긴다, 설계서 4.2 ③)이 있으면 방문은 닫혔다.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Query

from foms.services.datetime_kst import get_today_kst
from foms.services.feature_flags import is_item_construction_done_enabled
from foms.services.orders.construction_dates import short_date_label
from foms.services.orders.item_construction_done import (
    DONE_KEY,
    done_map,
    is_partial_open,
    is_split_order,
    item_lines,
    remaining_lines,
)
from foms.services.orders.order_mutation_policy import team_has_capability

__all__ = [
    "PARTIAL_VISIT_NOTE_PREFIX",
    "SPLIT_PRODUCTION_NOTE",
    "SPLIT_PRODUCTION_STAGE_TEXT",
    "annotate_split_rows",
    "done_item_uids",
    "order_item_done_view",
    "partial_board_label",
    "partial_visit_closed",
    "production_split_listed",
    "split_production_candidate_ids",
    "visit_open",
]

#: [오늘 시공 끝] 때 서버(E1)가 ``workflow.history`` 에 남기는 줄의 머리말(설계서 4.2 ③).
PARTIAL_VISIT_NOTE_PREFIX = "부분 시공 끝"
_START_NOTE = "시공 시작"
PRODUCTION_STAGE_CODES = ("PRODUCTION", "생산")
_UNDO_STAGE_CODES = PRODUCTION_STAGE_CODES + ("CONSTRUCTION", "시공", "CONSTRUCTING")
SPLIT_PRODUCTION_STAGE_TEXT = "생산 · 부분 시공"
SPLIT_PRODUCTION_NOTE = "생산 중 — 먼저 시공하는 제품만 기록해요"


def _sd(structured_data: Any) -> dict:
    return structured_data if isinstance(structured_data, dict) else {}


def _label(day: Any) -> str:
    try:
        return short_date_label(str(day)[:10])
    except (TypeError, ValueError):
        return ""


def _last_note_indexes(sd: dict) -> tuple[int, int]:
    """(마지막 "시공 시작" 줄 위치, 마지막 "부분 시공 끝" 줄 위치). 없으면 -1."""
    workflow = sd.get("workflow")
    history = workflow.get("history") if isinstance(workflow, dict) else None
    start = partial = -1
    for index, entry in enumerate(history if isinstance(history, list) else []):
        if not isinstance(entry, dict):
            continue
        note = str(entry.get("note") or "").strip()
        if note == _START_NOTE:
            start = index
        elif note.startswith(PARTIAL_VISIT_NOTE_PREFIX):
            partial = index
    return start, partial


def partial_visit_closed(structured_data: Any) -> bool:
    """마지막 "시공 시작" 뒤에 [오늘 시공 끝] 줄이 있다 — 그 방문은 닫혔고 다음 방문은 [시공 시작]부터다.

    스위치가 꺼져 있으면 늘 False(지금과 같다). [오늘 시공 끝] 줄이 하나도 없는 주문은 False.
    """
    start, partial = _last_note_indexes(_sd(structured_data))
    return partial > start and is_item_construction_done_enabled()


def visit_open(structured_data: Any) -> bool:
    """"시공 시작" 줄이 있고, 그 뒤에 [오늘 시공 끝] 줄이 없다."""
    start, partial = _last_note_indexes(_sd(structured_data))
    return start >= 0 and start > partial


def _remaining_dates_text(sd: dict) -> str:
    days = sorted({line.last_date for line in remaining_lines(sd) if line.last_date})
    return " · ".join(label for label in (_label(d) for d in days) if label)


def partial_board_label(structured_data: Any) -> Optional[str]:
    """상태 글 — 방문이 열려 있지 않고 부분 시공 중이면 "부분 시공 · 남은 11/17". 아니면 None(지금 글 그대로)."""
    sd = _sd(structured_data)
    if not is_item_construction_done_enabled() or not is_partial_open(sd) or visit_open(sd):
        return None
    dates = _remaining_dates_text(sd)
    return f"부분 시공 · 남은 {dates}" if dates else "부분 시공"


def done_item_uids(structured_data: Any) -> set[str]:
    """'시공 끝' 기록이 있는 (취소 안 된) 제품 uid. 스위치가 꺼져 있으면 빈 집합."""
    if not is_item_construction_done_enabled():
        return set()
    return {line.uid for line in item_lines(structured_data) if line.is_done and line.uid}


def _is_production(order: Any) -> bool:
    return str(getattr(order, "erp_stage_code", "") or "").strip().upper() in PRODUCTION_STAGE_CODES


def production_split_listed(order: Any, structured_data: Any, today_iso: Optional[str] = None) -> bool:
    """PC · 폰 시공 목록에 생산 단계 주문을 넣을지 — 나눠 시공 · 남은 제품 있음 · 남은 제품 시공일이 오늘 이후."""
    if not _is_production(order) or not is_item_construction_done_enabled():
        return False
    sd = _sd(structured_data)
    if not is_split_order(sd):
        return False
    today = today_iso or get_today_kst().isoformat()
    return any(line.last_date and line.last_date >= today for line in remaining_lines(sd))


def split_production_candidate_ids(base_query: Query, today_iso: Optional[str] = None) -> list[int]:
    """시공 목록에 더할 생산 단계 주문 번호(쿼리 1번). 스위치가 꺼져 있으면 쿼리 없이 빈 목록.

    SQL 로 먼저 좁힌다: 생산 단계 + 시공일 줄(``order_schedule_dates``)이 두 날 이상이고 가장 늦은 날이 오늘 이후
    (나눠 시공하는 주문은 제품마다 마지막 날이 달라 시공일이 늘 둘 이상이다). 그 뒤 실은 줄(제품 · 일정 · 기록 칸만)에
    ``production_split_listed`` 를 건다 — 목록 쪽 수 세기 · 쪽 나누기가 그대로 맞는다.
    """
    if not is_item_construction_done_enabled():
        return []
    from models import Order, OrderScheduleDate  # 순환 import 피함(모델 → 서비스)

    today = today_iso or get_today_kst().isoformat()
    multi_day = (
        select(OrderScheduleDate.order_id)
        .where(OrderScheduleDate.kind == "construction")
        .group_by(OrderScheduleDate.order_id)
        .having(func.count(func.distinct(OrderScheduleDate.date)) >= 2, func.max(OrderScheduleDate.date) >= today)
    )
    sd_json = Order.structured_data
    rows = (
        base_query.order_by(None)
        .filter(Order.erp_stage_code.in_(PRODUCTION_STAGE_CODES), Order.id.in_(multi_day))
        .with_entities(Order.id, Order.erp_stage_code, sd_json["items"].label("items"),
                       sd_json["schedule"].label("schedule"), sd_json[DONE_KEY].label("done"))
        .all()
    )
    out = []
    for row in rows:
        sd = {"items": row.items, "schedule": row.schedule, DONE_KEY: row.done}
        if production_split_listed(row, sd, today):
            out.append(int(row.id))
    return out


def annotate_split_rows(rows: list[dict], *, visit_date: Optional[str] = None) -> None:
    """시공 목록 · 태블릿 줄 DTO 에 나눠 시공 표시를 단다(나눠 시공하는 주문 줄만 — 그 밖 줄은 손대지 않는다).

    * 생산 단계 줄(``stage == '생산중'``)에 남은 제품이 있으면 시공 단계처럼 단추가 그려지게 ``stage`` 를
      '시공중'(방문 열림) · '시공대기'(닫힘)로 바꾸고, 글은 ``stage_text`` "생산 · 부분 시공", 상세 한 줄
      ``split_production_note``. 생산 안내(``tablet_note``)는 뺀다(같은 말 한 번).
    * 시공 단계 줄은 상태 글만 ``partial_board_label`` 로(방문이 닫힌 부분 시공 중).
    * 완료 창이 "오늘 끝낸 제품"을 고를 날 ``visit_date``(없으면 오늘)를 줄에 싣는다.
    """
    if not rows or not is_item_construction_done_enabled():
        return
    day = visit_date or get_today_kst().isoformat()
    for row in rows:
        sd = _sd(row.get("structured_data"))
        if not is_split_order(sd):
            continue
        row["item_done_visit_date"] = day
        if row.get("stage") == "생산중":
            if not remaining_lines(sd):
                continue
            # 화면 줄 DTO 의 표시 단계(단추를 고르는 열쇠)일 뿐 — 주문 단계(workflow.stage)는 그대로다(결정 N3).
            row.update({"stage": "시공중" if visit_open(sd) else "시공대기",
                        "stage_text": SPLIT_PRODUCTION_STAGE_TEXT, "split_production_note": SPLIT_PRODUCTION_NOTE})
            row.pop("tablet_note", None)
            continue
        label = partial_board_label(sd) if row.get("stage") in ("시공대기", "시공중") else None
        if label:
            row["stage_text"] = label


def user_may_undo_item_done(user: Any) -> bool:
    """[되돌리기]를 그릴 사람 — 관리자 · 매니저, 또는 CS 능력 팀(회계팀 별칭 포함) 직원. 조회 전용은 아니다."""
    if user is None:
        return False
    role = str(getattr(user, "role", "") or "").upper()
    if role in ("ADMIN", "MANAGER"):
        return True
    return role == "STAFF" and team_has_capability(getattr(user, "team", None), ("CS",))


def order_item_done_view(order: Any, user: Any = None) -> Optional[dict]:
    """주문 화면 제품 줄 표시 — ``{'order_id', 'records': [{uid, name, label}], 'can_undo'}``. 표시할 것이 없으면 None.

    스위치 꺼짐 · 나눠 시공 아님 · '시공 끝' 기록 없음이면 None(화면이 지금과 같다). [되돌리기]는
    관리자 · 매니저 · CS 이고 주문이 생산 · 시공 단계일 때만(결정 N9 — 서버도 같은 조건으로 막는다).
    """
    if order is None or not is_item_construction_done_enabled():
        return None
    sd = _sd(getattr(order, "structured_data", None))
    if not done_map(sd) or not is_split_order(sd):
        return None
    records = []
    for line in item_lines(sd):
        if not line.is_done or not line.uid:
            continue
        label = _label((line.done or {}).get("date"))
        records.append({"uid": line.uid, "name": line.name, "label": f"{label} 시공 끝" if label else "시공 끝"})
    if not records:
        return None
    stage = str(getattr(order, "erp_stage_code", "") or "").strip().upper()
    return {"order_id": int(order.id), "records": records,
            "can_undo": stage in _UNDO_STAGE_CODES and user_may_undo_item_done(user)}
