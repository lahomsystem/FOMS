"""실측 방문 체크("실측만 완료") 판정 — API 와 대시보드가 같이 쓰는 한 곳 (MEASUREMENT-VISIT-01).

저장 위치는 ``Order.structured_data['measurement_visits']`` 이다(서버 소유 — 폼이 렌더·전송하지
않는다). 모양::

    {"2026-09-23": {"at": "2026-09-23T14:05:11+09:00", "by_user_id": 12, "by_name": "최진호"}}

이 체크는 카드의 "실측 완료" 버튼(``measurement_completed`` · 도면 넘김)과 **다른 개념**이다.
여기 함수들은 DB 를 만지지 않는 순수 함수다.
"""

from __future__ import annotations

import datetime
import re
from typing import Any, Optional

from foms.services.measurement.manager_color import (
    MANAGER_COLOR_SLOT_COUNT,
    manager_color_key,
    manager_color_slot,
)
from foms.services.measurement_time import measurement_glance_time_key

MEASUREMENT_VISITS_KEY = "measurement_visits"
#: 날짜 키 상한 — 넘으면 가장 오래된 날짜부터 지운다(무한 증가 방지).
MEASUREMENT_VISITS_CAP = 20

#: 담당자 이름이 없을 때 묶음 머리에 보이는 이름.
UNASSIGNED_MANAGER_LABEL = "담당 미정"

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def normalize_visit_date(raw: Any) -> Optional[str]:
    """엄격한 ISO 날짜('YYYY-MM-DD')면 그 문자열, 아니면 None."""
    if not isinstance(raw, str) or not _ISO_DATE_RE.match(raw):
        return None
    try:
        datetime.date.fromisoformat(raw)
    except ValueError:
        return None
    return raw


def _visits_of(sd: Any) -> Optional[dict]:
    if not isinstance(sd, dict):
        return None
    visits = sd.get(MEASUREMENT_VISITS_KEY)
    return visits if isinstance(visits, dict) else None


def visit_entry(sd: Any, date_iso: Optional[str]) -> Optional[dict]:
    """그 날짜의 체크 기록(dict). 없거나 모양이 틀리면 None."""
    if not date_iso:
        return None
    visits = _visits_of(sd)
    if visits is None:
        return None
    entry = visits.get(date_iso)
    return entry if isinstance(entry, dict) else None


def is_visit_marked(sd: Any, date_iso: Optional[str]) -> bool:
    """그 날짜에 실측 방문 체크가 되어 있는가."""
    return visit_entry(sd, date_iso) is not None


def apply_visit_mark(
    sd: dict,
    date_iso: str,
    done: bool,
    *,
    at_iso: str,
    by_user_id: Any,
    by_name: str,
) -> bool:
    """이미 deepcopy 된 ``sd`` 를 직접 고친다. 바뀌었으면 True.

    - done=True: 그 날짜 기록이 없을 때만 ``{at, by_user_id, by_name}`` 를 넣는다.
    - done=False: 있을 때만 그 날짜 키를 지운다.
    - 날짜 키가 상한을 넘으면 ISO 문자열 정렬로 오래된 것부터 지운다.
    - 기존 값이 dict 가 아니면 ``{}`` 로 바꾼다(모양 복구도 변경으로 친다).
    """
    raw = sd.get(MEASUREMENT_VISITS_KEY)
    changed = False
    if isinstance(raw, dict):
        visits = dict(raw)
    else:
        visits = {}
        if MEASUREMENT_VISITS_KEY in sd:
            changed = True

    has_entry = isinstance(visits.get(date_iso), dict)
    if done:
        if not has_entry:
            visits[date_iso] = {"at": at_iso, "by_user_id": by_user_id, "by_name": by_name}
            changed = True
    elif date_iso in visits:
        del visits[date_iso]
        changed = True

    if len(visits) > MEASUREMENT_VISITS_CAP:
        # 방금 체크한 날짜는 지우지 않는다(옛 날짜를 뒤늦게 체크해도 남아야 한다).
        evictable = sorted((k for k in visits if not (done and k == date_iso)), key=str)
        for old_key in evictable[: len(visits) - MEASUREMENT_VISITS_CAP]:
            del visits[old_key]
        changed = True

    if changed:
        sd[MEASUREMENT_VISITS_KEY] = visits
    return changed


def _manager_key(name: Any) -> str:
    """PC 이미지 저장의 ``normalizeExportManagerKey`` 와 같다: trim → lower, '-' 는 ''."""
    return manager_color_key(name)


def _manager_label(name: Any) -> str:
    text = name.strip() if isinstance(name, str) else ""
    return text if text and text != "-" else UNASSIGNED_MANAGER_LABEL


def _phone_present(phone: Any) -> bool:
    text = phone.strip() if isinstance(phone, str) else ""
    return bool(text) and text != "-"


def _row_visit_time(row: Any) -> Any:
    """템플릿 시간 칩(``_t``)과 같은 원천: ``structured_data.schedule.measurement.time``."""
    sd = row.get("structured_data") if isinstance(row, dict) else None
    schedule = sd.get("schedule") if isinstance(sd, dict) else None
    measurement = schedule.get("measurement") if isinstance(schedule, dict) else None
    return measurement.get("time") if isinstance(measurement, dict) else None


def build_measurement_glance_groups(rows: list, color_slots: Optional[dict] = None) -> list:
    """행 순서 그대로 같은 담당자의 **연속 구간**을 묶고, 묶음 안 행만 방문 시각 이른 순으로 정렬한다.

    묶음 자체의 순서·경계는 입력(PC 표) 순서 그대로다. 묶음 안 정렬 키는
    ``measurement_glance_time_key`` (숫자 시각 → '오전' → '오후' → 종일 → 미상, 같은 키는 원래 순서).
    방문 시각은 **전날 17시에 확정한 계획값**이다 — 당일 바뀌어도 ERP 에 들어오지 않으므로
    이 정렬은 계획의 표시 순서일 뿐 실제 방문 순서를 보장하지 않는다.

    원소: ``{key, manager_name, manager_phone, rows, done, total, color_slot, order_no}``.
    ``manager_phone`` 은 묶음 안에서 처음 나온 비어 있지 않은 값(번호 정규화는 템플릿이 한다).
    ``done`` 은 ``measurement_visit_done`` 수.

    ``color_slot`` 은 담당 색 칸(1~8, 담당 없음 0 — :mod:`foms.services.measurement.manager_color`,
    ``color_slots`` 는 :func:`~foms.services.measurement.manager_color.load_manager_color_slots` 결과).
    ``order_no`` 는 오늘 목록에서 그 담당이 처음 나온 순서(1, 2, 3 …, 담당 없음 0) — 탭과 띠의
    번호 칸(색이 안 갈리는 사람을 위한 두 번째 단서). 같은 담당이 두 묶음으로 갈려도 같은 번호다.
    """
    groups: list = []
    for row in rows or []:
        key = _manager_key(row.get("manager_name"))
        if not groups or groups[-1]["key"] != key:
            groups.append({
                "key": key,
                "manager_name": _manager_label(row.get("manager_name")),
                "manager_phone": row.get("manager_phone"),
                "rows": [],
                "done": 0,
                "total": 0,
            })
        grp = groups[-1]
        # 첫 행에 번호가 없어도 묶음 안 다른 행의 번호로 전화 링크를 살린다(같은 담당자).
        if not _phone_present(grp["manager_phone"]) and _phone_present(row.get("manager_phone")):
            grp["manager_phone"] = row.get("manager_phone")
        grp["rows"].append(row)
        grp["total"] += 1
        if row.get("measurement_visit_done"):
            grp["done"] += 1
    order_by_key: dict = {}
    # 영업팀 명부 담당은 고정 칸. 명부 밖 이름(외주 등)은 그날 비어 있는 칸을 받는다 — 해시 예비 칸은
    # 명부 담당과 같은 색이 될 수 있었다(화면 확인에서 실제로 겹침).
    slot_by_key: dict = {}
    for grp in groups:
        if grp["key"] and color_slots and grp["key"] in color_slots:
            slot_by_key[grp["key"]] = manager_color_slot(grp["key"], color_slots)
    for grp in groups:
        key = grp["key"]
        if key and key not in slot_by_key:
            used = set(slot_by_key.values())
            free = [s for s in range(1, MANAGER_COLOR_SLOT_COUNT + 1) if s not in used]
            slot_by_key[key] = free[0] if free else manager_color_slot(key, color_slots)
    for grp in groups:
        grp["color_slot"] = slot_by_key.get(grp["key"], 0)
        if grp["key"] and grp["key"] not in order_by_key:
            order_by_key[grp["key"]] = len(order_by_key) + 1
        grp["order_no"] = order_by_key.get(grp["key"], 0)
        # sorted 는 안정 정렬 — 같은 시각 키는 PC 표 순서를 지킨다.
        grp["rows"] = sorted(grp["rows"], key=lambda r: measurement_glance_time_key(_row_visit_time(r)))
    return groups


__all__ = [
    "MEASUREMENT_VISITS_CAP",
    "MEASUREMENT_VISITS_KEY",
    "UNASSIGNED_MANAGER_LABEL",
    "apply_visit_mark",
    "build_measurement_glance_groups",
    "is_visit_marked",
    "normalize_visit_date",
    "visit_entry",
]
