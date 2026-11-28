"""도면 카드 판 맥락(``ctx``) 만들기 — :func:`foms.services.production.part_board.build_part_board` 밖으로 옮겼다(파일 500줄 래칫 ·
설계서 2026-11-28-production-my-steps-flow §6-3).

판(날짜 탭 · '도면 카드' 화면) · '내 공정' · '작업 중'(:mod:`~foms.services.production.my_steps` ·
:mod:`~foms.services.production.crew_board`)이 같은 맥락으로 같은 카드(:func:`~foms.services.production.part_board.build_card`)를
만든다. 쿼리는 표시 줄 읽기 한 번(넘긴 ``marks`` 가 있으면 0) + 펜 기록 머리(스위치 켬만 +1)뿐이다. 맥락에서 파트에 매인 칸은
``part`` · ``writable`` 둘이다 — 파트를 바꿔 같은 맥락을 다시 쓰려면 :func:`for_part`.

이 모듈은 ``part_board`` 를 import 하지 않는다(거꾸로만 — 순환 금지).
"""

from __future__ import annotations

import datetime
from typing import Any, Iterable, Optional

from foms.services.datetime_kst import get_today_kst
from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.orders.drawing_fix import blocked
from foms.services.orders.drawing_fix_requests import board_request_options
from foms.services.production.drawing_notes_read import board_notes
from foms.services.production.factory_scope import board_factory, scene_on
from foms.services.production.part_access import VIEW_PART, own_parts, writable_parts
from foms.services.production.part_card_state import hand_cell, order_block
from foms.services.production.part_constants import PRODUCTION_PART_KEYS
from foms.services.production.part_mark_notes import actor_name
from models import ProductionPartMark

MarkIndex = dict[tuple[int, str, str], Any]
SheetIndex = dict[tuple[int, str], list[Any]]


def fetch_part_marks(db: Any, order_ids: Iterable[int]) -> list[Any]:
    """그날들 생산 주문의 표시 줄 전부 — 쿼리 한 번(주문이 없으면 0번).

    Args:
        db: 세션.
        order_ids: 주문 id 들.

    Returns:
        ``ProductionPartMark`` 줄 목록(네 파트 모두 — 다른 파트 한 줄에 쓴다).
    """
    ids = sorted({int(i) for i in order_ids})
    if not ids:
        return []
    return db.query(ProductionPartMark).filter(ProductionPartMark.order_id.in_(ids)).all()


def index_marks(marks: Iterable[Any]) -> tuple[MarkIndex, SheetIndex]:
    """표시 줄 → (장 · 파트 자리 사전, 시트 신원 사전).

    Returns:
        ``({(order_id, key, part): 줄}, {(order_id, sheet_id): [줄…]})`` — 둘째는 시트 신원이 있는 줄 + 모든 줄을 ``file:<key>``
        자리에도(파일 도면 이어받기 짝 — 설계서 2026-11-25 §3-5, 시트 id 에는 ``:`` 가 없어 겹치지 않는다).
    """
    by_slot: MarkIndex = {}
    by_sheet: SheetIndex = {}
    for row in marks:
        by_slot[(int(row.order_id), str(row.drawing_key), str(row.part))] = row
        by_sheet.setdefault((int(row.order_id), f"file:{row.drawing_key}"), []).append(row)
        if row.sheet_id:
            by_sheet.setdefault((int(row.order_id), str(row.sheet_id)), []).append(row)
    return by_slot, by_sheet


def order_marks_of(marks: Iterable[Any]) -> dict[int, list[Any]]:
    """표시 줄 → 주문마다 줄 목록."""
    out: dict[int, list[Any]] = {}
    for row in marks:
        out.setdefault(int(row.order_id), []).append(row)
    return out


def board_ctx(db: Any, user: Any, rows: list[dict[str, Any]], *, mode: str, part: str, marks: Optional[list[Any]] = None,
              today: Optional[datetime.date] = None, factory: Any = None,
              scene_rows: Optional[Iterable[dict[str, Any]]] = None) -> dict[str, Any]:
    """판 맥락 — 카드를 만들 줄(``rows``)의 확정 도면 · 표시 줄 사전 · 손 체크 · 막힘 · 펜 기록 · 고치기 요청 고르기.

    Args:
        db: 세션.
        user: 보는 사람.
        rows: 카드를 만들 첫 화면 행(생산 단계 주문).
        mode: 보기 모드(:func:`~foms.services.production.part_access.part_view_mode`).
        part: 볼 파트 key.
        marks: 이미 읽은 그 주문들 표시 줄(넘기면 다시 읽지 않는다 — 쿼리 0).
        today: KST 오늘(시험용, 없으면 지금).
        factory: 관리자가 고른 공장(``?factory=``) — 그 밖 사람은 계정 공장.
        scene_rows: 2공장 그림을 켤지 볼 행(없으면 ``rows``).

    Returns:
        :func:`~foms.services.production.part_board.build_card` 맥락 dict + ``slots``(장 · 파트 자리 사전 — :func:`index_marks`).
    """
    files = {int(row["id"]): resolve_final_drawing_files(row.get("structured_data") or {}) for row in rows}
    if marks is None:
        marks = fetch_part_marks(db, (oid for oid, entries in files.items() if entries))
    by_slot, by_sheet = index_marks(marks)
    order_marks = order_marks_of(marks)
    factory = board_factory(user, factory)
    scene = scene_on((r.get("structured_data") or {} for r in (rows if scene_rows is None else scene_rows)), factory)
    return {
        "part": part, "mine": mode == VIEW_PART, "writable": part in writable_parts(user), "user_id": getattr(user, "id", None),
        "viewer_name": actor_name(user), "factory": factory, "scene": scene,
        "own_parts": own_parts(user),
        "files": files, "today": today or get_today_kst(), "order_marks": order_marks,
        "by_sheet": by_sheet, "current_keys": {oid: {e["key"] for e in entries} for oid, entries in files.items()},
        "blocks": {int(row["id"]): order_block(row) for row in rows},  # 주문 통째(보류 · 도면 고치는 중)
        "fix": {int(row["id"]): blocked(row.get("structured_data") or {}) for row in rows},  # 도면별 막힘(2026-11-25 §3-3, 쿼리 0)
        "notes": board_notes(db, files),  # 펜 기록 머리(스위치 켬만 +1 — 꺼짐 None · 쿼리 0, 2026-11-28 §8 '쿼리')
        "req": board_request_options(user, rows),  # [도면 수정 요청] 창 고르기(2026-11-25 §2-4 · N3 — 생산 단계 주문, 쿼리 0)
        "hands": {int(row["id"]): {p: hand_cell(row.get("structured_data") or {}, order_marks.get(int(row["id"]), []), p)
                                   for p in PRODUCTION_PART_KEYS} for row in rows},
        "slots": by_slot,
    }


def for_part(ctx: dict[str, Any], user: Any, part: str) -> dict[str, Any]:
    """같은 맥락을 다른 파트로 — ``part`` · ``writable`` 만 바꾼 얕은 사본(여러 파트를 섞는 '내 공정' · 파트 넷을 도는 '작업 중')."""
    return {**ctx, "part": part, "writable": part in writable_parts(user)}


__all__ = ["MarkIndex", "SheetIndex", "board_ctx", "fetch_part_marks", "for_part", "index_marks", "order_marks_of"]
