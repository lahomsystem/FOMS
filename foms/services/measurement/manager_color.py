"""실측 한눈 목록 담당자 색 칸(1~8) 배정 — 날마다·기기마다 같은 담당은 같은 색.

단순 이름 해시(crc32 % 8)는 담당 6명만 넣어도 두 명이 같은 칸에 걸린다(생일 문제 — 목업에서
실제로 겹쳤다). 그래서 **영업팀 명부 순서**로 칸을 준다:

- 명부 = 활성(``is_active``) 사용자 중 정규화 팀이 ``SALES`` 인 사람(``MEASURE`` 표기 포함 —
  :func:`foms.services.orders.order_mutation_policy.normalize_team` 과 같은 규칙), ``User.id`` 오름차순.
- 칸 = ``(명부 순위 % 8) + 1`` — 8명까지는 절대 안 겹친다. 새 담당은 id 가 커서 맨 뒤에 붙으므로
  기존 담당 색이 바뀌지 않는다.
- 키 = 묶음 키와 같은 ``trim → lower`` (``visit_check._manager_key``). 같은 이름이 둘이면 먼저(id 작은) 사람.
- 명부에 없는 이름(자유 입력 담당 등)은 crc32 예비 칸(고정 함수 — ``hash()`` 는 프로세스마다 바뀐다).
- 담당 없음(빈 키)은 0 = 규칙 없음(지금의 브랜드 띠 그대로).

DB 조회는 :func:`load_manager_color_slots` 한 번(요청당 1쿼리, 행 수와 무관)이다.
"""

from __future__ import annotations

import zlib
from typing import Any, Iterable, Mapping, Optional

from foms.persistence.main.models import User
from foms.services.orders.order_mutation_policy import normalize_team

#: 담당 색 칸 수 — CSS ``[data-mgr-color="1"]`` ~ ``"8"`` 과 같아야 한다.
MANAGER_COLOR_SLOT_COUNT = 8
#: 색을 주는 팀(정규화 뒤 값).
MANAGER_COLOR_TEAM = "SALES"


def manager_color_key(name: Any) -> str:
    """``visit_check._manager_key`` 와 같은 키: trim → lower, '-' 는 ''."""
    key = (name or "").strip().lower() if isinstance(name, str) else ""
    return "" if key == "-" else key


def build_manager_color_slots(users: Iterable[Any]) -> dict:
    """``(id, name, team)`` 행들 → ``{담당 키: 칸}``. 영업팀만, id 오름차순 순위로 칸을 준다."""
    roster = []
    for row in users or []:
        user_id, name, team = row[0], row[1], row[2]
        if normalize_team(team) != MANAGER_COLOR_TEAM:
            continue
        try:
            roster.append((int(user_id), name))
        except (TypeError, ValueError):
            continue
    roster.sort(key=lambda item: item[0])
    slots: dict = {}
    rank = 0
    for _, name in roster:
        key = manager_color_key(name)
        if not key or key in slots:
            continue
        slots[key] = (rank % MANAGER_COLOR_SLOT_COUNT) + 1
        rank += 1
    return slots


def manager_color_slot(key: Any, slots: Optional[Mapping] = None) -> int:
    """담당 키 → 칸(1~8). 빈 키는 0, 명부에 없으면 crc32 예비 칸."""
    key = manager_color_key(key)
    if not key:
        return 0
    slot = (slots or {}).get(key)
    if slot:
        return int(slot)
    return zlib.crc32(key.encode("utf-8")) % MANAGER_COLOR_SLOT_COUNT + 1


def load_manager_color_slots(db) -> dict:
    """활성 사용자 ``(id, name, team)`` 을 한 번 읽어 칸 표를 만든다(요청당 1쿼리)."""
    rows = (
        db.query(User.id, User.name, User.team)
        .filter(User.is_active.is_(True))
        .order_by(User.id.asc())
        .all()
    )
    return build_manager_color_slots(rows)


__all__ = [
    "MANAGER_COLOR_SLOT_COUNT",
    "MANAGER_COLOR_TEAM",
    "build_manager_color_slots",
    "load_manager_color_slots",
    "manager_color_key",
    "manager_color_slot",
]
