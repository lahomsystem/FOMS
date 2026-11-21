"""제품마다 '시공 끝' 표시 판정 (한 주문 여러 시공일 2단계).

설계: ``docs/specs/2026-11-21-item-construction-done_SPEC.md``.

주문 하나에 제품이 여럿이고 제품마다 마지막 시공일이 다르면 "나눠 시공하는 주문"이다. 시공팀이
첫 방문 날 [시공 완료] 창에서 "오늘 끝낸 제품"을 고르면 그 제품에만 '시공 끝' 기록이 붙고,
주문은 단계에 그대로 남는다. 남은 제품이 있으면 CS · 완료로 넘어가지 않는다(문지기).

기록은 서버만 쓰는 칸 하나다::

    structured_data["item_construction_done"] = {
        "<제품 uid>": {"date": "YYYY-MM-DD", "at": iso, "by_user_id": int | None,
                       "by_name": str, "source": "visit" | "admin_override",
                       "attempt_id": int | None},
    }

순수 함수만 둔다(DB · 요청 문맥 없음). 스위치(``is_item_construction_done_enabled``)는 부르는 쪽이
본다 — 여기 판정은 자료만 읽는다. 지난 주문 일괄 완료 도구처럼 스위치와 상관없이 자료로 막아야
하는 곳이 있기 때문이다.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from foms.services.orders.construction_dates import short_date_label, split_date_text
from foms.services.orders.drawing_confirm_partial import is_item_cancelled, item_ref
from foms.services.orders.structured_item_uid import ITEM_UID_KEY, item_uid_of

__all__ = [
    "DONE_KEY",
    "SOURCE_ADMIN_OVERRIDE",
    "SOURCE_VISIT",
    "ItemLine",
    "apply_done_marks",
    "blocked_message",
    "done_map",
    "has_done_marks",
    "is_partial_open",
    "is_split_order",
    "item_lines",
    "order_construction_dates",
    "remaining_lines",
    "remaining_summary",
    "remove_done_mark",
    "visit_candidates",
]

#: 서버 전용 최상위 칸 — 폼 저장 보호 목록(``_OPERATIONAL_TOP_LEVEL_KEYS``)에 올린다.
DONE_KEY = "item_construction_done"

SOURCE_VISIT = "visit"
SOURCE_ADMIN_OVERRIDE = "admin_override"

_NAME_KEYS = ("product_name", "name", "product")


@dataclass(frozen=True)
class ItemLine:
    """취소 안 된 제품 한 줄의 판정 결과."""

    ref: str                    # uid, 없으면 ``idx:<배열 위치>``
    uid: Optional[str]
    index: int                  # ``items`` 배열 위치(취소 제품 포함 기준)
    name: str
    dates: tuple[str, ...]      # 제품 칸 날짜, 비면 주문 날짜를 물려받은 값
    last_date: Optional[str]    # 위 날짜 가운데 가장 늦은 날
    done: Optional[dict]        # '시공 끝' 기록, 없으면 None

    @property
    def is_done(self) -> bool:
        return self.done is not None


def _sd(structured_data: Any) -> dict:
    return structured_data if isinstance(structured_data, dict) else {}


def _raw_items(sd: dict) -> list:
    items = sd.get("items")
    return items if isinstance(items, list) else []


def order_construction_dates(structured_data: Any) -> list[str]:
    """주문 칸(``schedule.construction.date``)의 시공일 목록."""
    schedule = _sd(structured_data).get("schedule")
    construction = schedule.get("construction") if isinstance(schedule, dict) else None
    if not isinstance(construction, dict):
        return []
    return split_date_text(construction.get("date"))


def done_map(structured_data: Any) -> dict[str, dict]:
    """'시공 끝' 기록 전부(uid → 기록). 형식이 아니면 빈 dict."""
    raw = _sd(structured_data).get(DONE_KEY)
    if not isinstance(raw, dict):
        return {}
    return {str(k): v for k, v in raw.items() if isinstance(v, dict)}


def _item_name(item: dict, index: int) -> str:
    for key in _NAME_KEYS:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return f"제품 {index + 1}"


def item_lines(structured_data: Any) -> list[ItemLine]:
    """취소 안 된 제품마다 한 줄(배열 순서). 제품 칸 날짜가 비면 주문 날짜를 물려받는다.

    물려받는 규칙은 출고 · 태블릿의 "그날 제품" 고르기(``visible_items_for_dates``)와 같다.
    """
    sd = _sd(structured_data)
    raw = _raw_items(sd)
    order_dates = order_construction_dates(sd)
    marks = done_map(sd)
    lines: list[ItemLine] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict) or is_item_cancelled(item):
            continue
        uid = item_uid_of(item)
        dates = tuple(split_date_text(item.get("construction_date")) or order_dates)
        lines.append(ItemLine(
            ref=item_ref(raw, index),
            uid=uid,
            index=index,
            name=_item_name(item, index),
            dates=dates,
            last_date=dates[-1] if dates else None,
            done=marks.get(uid) if uid else None,
        ))
    return lines


def has_done_marks(structured_data: Any) -> bool:
    """취소 안 된 제품 가운데 '시공 끝' 기록이 하나라도 있나."""
    return any(line.is_done for line in item_lines(structured_data))


def is_split_order(structured_data: Any) -> bool:
    """나눠 시공하는 주문인가 — 제품들의 마지막 시공일이 두 가지 이상, 또는 이미 '시공 끝' 제품이 있다.

    제품 칸 날짜가 없는 주문(이틀 연속 시공 포함)은 모든 제품이 주문 날짜를 물려받아 마지막 날이
    같으므로 나눠 시공이 아니다 — 단추 · 동작이 지금과 같다.
    """
    lines = item_lines(structured_data)
    if any(line.is_done for line in lines):
        return True
    return len({line.last_date for line in lines if line.last_date}) >= 2


def remaining_lines(structured_data: Any) -> list[ItemLine]:
    """취소 안 됐고 '시공 끝' 기록이 없는 제품."""
    return [line for line in item_lines(structured_data) if not line.is_done]


def is_partial_open(structured_data: Any) -> bool:
    """부분 시공 중 — '시공 끝' 제품이 있고 남은 제품도 있다. 문지기는 이 판정으로 막는다."""
    lines = item_lines(structured_data)
    return any(line.is_done for line in lines) and any(not line.is_done for line in lines)


def remaining_summary(structured_data: Any) -> str:
    """남은 제품 한 줄 — "11/17 부엌가구 · 화장대". 남은 제품이 없으면 빈 글."""
    parts = []
    for line in remaining_lines(structured_data):
        label = short_date_label(line.last_date) if line.last_date else ""
        parts.append(f"{label} {line.name}".strip())
    return " · ".join(parts)


def blocked_message(structured_data: Any) -> str:
    """문지기 오류 글 — "11/17 부엌가구 시공이 남아 있어요"."""
    summary = remaining_summary(structured_data)
    return f"{summary} 시공이 남아 있어요" if summary else "남은 제품 시공이 있어요"


def visit_candidates(structured_data: Any, day_iso: str) -> list[dict[str, Any]]:
    """[시공 완료] 창의 "오늘 끝낸 제품" 목록 — 남은 제품 전부, 마지막 시공일이 그날 이전이면 미리 체크."""
    out = []
    for line in remaining_lines(structured_data):
        out.append({
            "ref": line.ref,
            "name": line.name,
            "last_date": line.last_date,
            "last_label": short_date_label(line.last_date) if line.last_date else "",
            "precheck": line.last_date is None or line.last_date <= day_iso,
        })
    return out


def apply_done_marks(
    structured_data: dict,
    refs: Iterable[str],
    *,
    day_iso: str,
    at_iso: str,
    user_id: Optional[int],
    user_name: str,
    source: str = SOURCE_VISIT,
    attempt_id: Optional[int] = None,
) -> list[str]:
    """고른 제품에 '시공 끝'을 찍는다(제자리 수정 — 부르는 쪽이 deepcopy 한 사본을 넘긴다).

    ``refs`` 는 uid 또는 ``idx:<위치>``. 이름표가 없는 옛 제품은 이때 uid 를 새로 단다(확정 뒤 제품
    취소와 같은 방식). 모르는 참조 · 취소 제품 · 이미 끝난 제품은 건너뛴다. 찍은 uid 목록을 돌려준다.
    """
    wanted = {str(r).strip() for r in refs if isinstance(r, str) and str(r).strip()}
    raw = _raw_items(structured_data)
    marks = dict(done_map(structured_data))
    marked: list[str] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict) or is_item_cancelled(item):
            continue
        ref = item_ref(raw, index)
        if ref not in wanted:
            continue
        uid = item_uid_of(item)
        if uid is None:
            uid = str(uuid.uuid4())
            item[ITEM_UID_KEY] = uid
        if uid in marks:
            continue
        marks[uid] = {
            "date": day_iso, "at": at_iso, "by_user_id": user_id, "by_name": user_name,
            "source": source, "attempt_id": attempt_id,
        }
        marked.append(uid)
    if marked:
        structured_data[DONE_KEY] = marks
    return marked


def remove_done_mark(structured_data: dict, uid: str) -> Optional[dict]:
    """'시공 끝' 기록 하나를 지운다(제자리 수정). 지운 기록, 없었으면 None."""
    marks = dict(done_map(structured_data))
    record = marks.pop(str(uid), None)
    if record is None:
        return None
    if marks:
        structured_data[DONE_KEY] = marks
    else:
        structured_data.pop(DONE_KEY, None)
    return record
