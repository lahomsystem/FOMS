"""나눠 시공하는 주문의 방문 한 번 — 글 · 남은 날 판정 (제품마다 '시공 끝' 2단계).

설계: ``docs/specs/2026-11-21-item-construction-done_SPEC.md`` 4.2 · 5.3.

[오늘 시공 끝](부분 방문)은 그 방문 줄을 ``VISITED`` 로 닫고 ``workflow.history`` 에 한 줄을
남긴다. 그 줄의 note 는 반드시 :data:`PARTIAL_VISIT_NOTE_PREFIX` 로 시작한다 — 화면(상태 글)이
마지막 "시공 시작" 줄과 마지막 "부분 시공 끝" 줄의 순서로 방문이 열려 있는지 가른다.

순수 함수만 둔다(DB · 요청 문맥 없음).
"""
from __future__ import annotations

import datetime
from typing import Any, Iterable

from foms.services.feature_flags import is_item_construction_done_enabled
# 모듈째 가져와 부를 때 읽는다 — construction_dates 가 맨 끝에서 이 모듈을 가져오고(남은 시공 한 줄),
# item_construction_done 은 construction_dates 를 가져와서 이름을 바로 꺼내면 가져오는 순서에 따라 깨진다.
from foms.services.orders import construction_dates as _dates
from foms.services.orders import item_construction_done as _done

__all__ = [
    "PARTIAL_VISIT_NOTE_PREFIX",
    "VISITED_STATUS",
    "done_entries",
    "names_for_uids",
    "partial_visit_note",
    "remaining_entries",
    "remaining_dates_after",
    "split_flow_active",
    "split_production_start_allowed",
]

#: [오늘 시공 끝] history 줄 note 의 첫머리(화면 판정과 맞춘 약속 — 바꾸지 않는다).
PARTIAL_VISIT_NOTE_PREFIX = "부분 시공 끝"

#: 부분 방문으로 닫은 방문 줄(``OrderConstructionAttempt.status``) 값. DB 제약이 없는 새 값이다.
VISITED_STATUS = "VISITED"

#: 평면 칸 ``erp_stage_code`` 의 생산 단계 값(시공 라우트의 ``_CONSTRUCTION_STAGES`` 와 같은 꼴).
_PRODUCTION_STAGES = ("생산", "PRODUCTION")


def split_flow_active(structured_data: Any) -> bool:
    """스위치가 켜져 있고 나눠 시공하는 주문인가 — [시공 완료]가 "오늘 끝낸 제품"을 받는 조건."""
    return is_item_construction_done_enabled() and _done.is_split_order(structured_data)


def split_production_start_allowed(order: Any) -> bool:
    """생산 단계 주문이 [시공 시작]을 열 수 있나(N3) — 스위치 켜짐 · 나눠 시공 · 남은 제품 있음."""
    if getattr(order, "erp_stage_code", None) not in _PRODUCTION_STAGES:
        return False
    sd = getattr(order, "structured_data", None)
    return split_flow_active(sd) and bool(_done.remaining_lines(sd))


def names_for_uids(structured_data: Any, uids: Iterable[str]) -> list[str]:
    """uid 목록을 제품 이름으로(제품 배열 순서). 모르는 uid 는 뺀다."""
    wanted = {str(uid) for uid in uids}
    return [line.name for line in _done.item_lines(structured_data) if line.uid and line.uid in wanted]


def remaining_dates_after(structured_data: Any, after: datetime.date) -> list[str]:
    """남은 제품(취소 · '시공 끝' 제외)의 시공일 **전부** 가운데 ``after`` 보다 뒤인 날(정렬 · 중복 제거).

    마지막 날만 보면 한 제품에 날이 둘(11/10 · 11/17)일 때 앞날이 남은 시공에서 빠진다.
    """
    limit = after.isoformat()
    days = {day for line in _done.remaining_lines(structured_data) for day in line.dates}
    return sorted(day for day in days if day > limit)


def remaining_entries(structured_data: Any) -> list[dict[str, Any]]:
    """응답용 남은 제품 목록 — ``[{name, date}]``(제품 배열 순서)."""
    return [{"name": line.name, "date": line.last_date} for line in _done.remaining_lines(structured_data)]


def done_entries(structured_data: Any) -> list[dict[str, Any]]:
    """'시공 끝' 제품 목록 — ``[{uid, name, date, date_label}]``(제품 배열 순서)."""
    out = []
    for line in _done.item_lines(structured_data):
        if not line.is_done:
            continue
        day = str((line.done or {}).get("date") or "")
        try:
            label = _dates.short_date_label(day) if day else ""
        except ValueError:
            label = ""
        out.append({"uid": line.uid, "name": line.name, "date": day or None, "date_label": label})
    return out


def partial_visit_note(done_names: Iterable[str], structured_data_after: Any) -> str:
    """history 한 줄 — "부분 시공 끝 (화장대 · 베란다장) — 남은 시공 11/17".

    남은 날은 찍은 뒤 문서의 남은 제품 마지막 시공일(지난 날 포함, 정렬)이다. 남은 제품에 날짜가
    없으면 날짜 부분을 뺀다.
    """
    names = " · ".join(name for name in done_names if name)
    head = f"{PARTIAL_VISIT_NOTE_PREFIX} ({names})" if names else PARTIAL_VISIT_NOTE_PREFIX
    days = sorted({line.last_date for line in _done.remaining_lines(structured_data_after) if line.last_date})
    if not days:
        return head
    return f"{head} — 남은 시공 " + " · ".join(_dates.short_date_label(day) for day in days)
