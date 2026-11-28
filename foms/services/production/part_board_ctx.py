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

from sqlalchemy import or_, select

from foms.services.datetime_kst import get_today_kst
from foms.services.orders.drawing_factory import sheet_factory
from foms.services.orders.drawing_fix import blocked
from foms.services.orders.drawing_fix_requests import board_request_options
from foms.services.production import mark_crew as mc
from foms.services.production.drawing_notes_read import board_notes
from foms.services.production.factory_scope import board_factory, scene_on
from foms.services.production.order_card import is_order_entry, row_files
from foms.services.production.part_access import VIEW_PART, own_parts, writable_parts
from foms.services.production.part_card_state import hand_cell, order_block
from foms.services.production.part_constants import MARK_STATE_NEED, PRODUCTION_PART_KEYS
from foms.services.production.part_mark_notes import actor_name
from models import ProductionPartMark

MarkIndex = dict[tuple[int, str, str], Any]
SheetIndex = dict[tuple[int, str], list[Any]]


def fetch_part_marks(db: Any, order_ids: Iterable[int], *, touched: Iterable[int] = (),
                     since: Optional[datetime.datetime] = None) -> list[Any]:
    """그날들 생산 주문의 표시 줄 전부 — 쿼리 한 번(주문이 없으면 0번).

    Args:
        db: 세션.
        order_ids: 주문 id 들.
        touched: 같은 한 번에 더 읽을 주문 id 들 — 그 가운데 ``since`` 뒤 손댄 줄이 하나라도 있는 주문만, 그 주문 줄 전부(하위 질의 —
            '내 공정' 탭이 제작 완료로 넘어간 주문의 오늘 끝낸 장을 보는 데 쓴다, 2026-11-28 "제작 완료돼도 남김"). ``since`` 가 없으면 무시.
        since: 손댄 때 아래 끝(UTC naive — ``updated_at`` 과 견준다).

    Returns:
        ``ProductionPartMark`` 줄 목록(네 파트 모두 — 다른 파트 한 줄에 쓴다).
    """
    ids = sorted({int(i) for i in order_ids})
    late = sorted({int(i) for i in touched} - set(ids)) if since is not None else []
    if not ids and not late:
        return []
    found = [ProductionPartMark.order_id.in_(ids)] if ids else []
    if late:  # 같은 문장 하나 — 손댄 줄이 있는 주문 id 를 하위 질의로 고른다(쿼리 수 그대로)
        recent = select(ProductionPartMark.order_id).where(ProductionPartMark.order_id.in_(late),
                                                           ProductionPartMark.updated_at >= since)
        found.append(ProductionPartMark.order_id.in_(recent))
    return db.query(ProductionPartMark).filter(or_(*found)).all()


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
        rows: 카드를 만들 첫 화면 행(생산 단계 주문 — '내 공정'은 오늘 손댄 제작 완료 주문도, ``my_steps.finished_rows``).
        mode: 보기 모드(:func:`~foms.services.production.part_access.part_view_mode`).
        part: 볼 파트 key.
        marks: 이미 읽은 그 주문들 표시 줄(넘기면 다시 읽지 않는다 — 쿼리 0).
        today: KST 오늘(시험용, 없으면 지금).
        factory: 관리자가 고른 공장(``?factory=``) — 그 밖 사람은 계정 공장.
        scene_rows: 2공장 그림을 켤지 볼 행(없으면 ``rows``).

    Returns:
        :func:`~foms.services.production.part_board.build_card` 맥락 dict + ``slots``(장 · 파트 자리 사전 — :func:`index_marks`).
    """
    # 카드 장 = 확정 도면, 0장인 생산 단계 줄은 주문 카드 한 장(@order — 2026-11-28 흐름 §3-5). 펜 기록 · 바뀐 도면 짝은 진짜 도면만.
    files = {int(row["id"]): row_files(row) for row in rows}
    drawn = {oid: [e for e in entries if not is_order_entry(e)] for oid, entries in files.items()}
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
        "by_sheet": by_sheet, "current_keys": {oid: {e["key"] for e in entries} for oid, entries in drawn.items()},
        "blocks": {int(row["id"]): order_block(row) for row in rows},  # 주문 통째(보류 · 도면 고치는 중)
        "fix": {int(row["id"]): blocked(row.get("structured_data") or {}) for row in rows},  # 도면별 막힘(2026-11-25 §3-3, 쿼리 0)
        "notes": board_notes(db, drawn),  # 펜 기록 머리(스위치 켬만 +1 — 꺼짐 None · 쿼리 0, 2026-11-28 §8 '쿼리')
        "req": board_request_options(user, rows),  # [도면 수정 요청] 창 고르기(2026-11-25 §2-4 · N3 — 생산 단계 주문, 쿼리 0)
        "hands": {int(row["id"]): {p: hand_cell(row.get("structured_data") or {}, order_marks.get(int(row["id"]), []), p)
                                   for p in PRODUCTION_PART_KEYS} for row in rows},
        "slots": by_slot,
    }


def for_part(ctx: dict[str, Any], user: Any, part: str) -> dict[str, Any]:
    """같은 맥락을 다른 파트로 — ``part`` · ``writable`` 만 바꾼 얕은 사본(여러 파트를 섞는 '내 공정' · 파트 넷을 도는 '작업 중')."""
    return {**ctx, "part": part, "writable": part in writable_parts(user)}


def card_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """'내 공정' · '작업 중' · 탭 숫자가 카드를 세는 줄 — 화면의 생산 단계 주문 전부(날짜와 무관 · 행 순서 그대로)."""
    return [row for row in rows if row.get("home_view") == "prod"]


def factory_files(row: dict[str, Any], files: list[dict[str, Any]], *, factory: int, scene: bool) -> list[tuple[int, dict[str, Any]]]:
    """그 줄 확정 도면 가운데 보는 공장 장 ``[(장 번호 1부터, 항목)]`` — 판(:func:`~part_board.build_pane_board`)과 같은 공장 판정.

    남의 공장 장은 날짜 탭에서만 판 뒤 묶음(누름 없음)으로 보이고 '내 공정' · '작업 중' · 탭 숫자에는 안 든다.
    """
    sd = row.get("structured_data") or {}
    return [(index + 1, entry) for index, entry in enumerate(files)
            if (sheet_factory(sd, entry) if scene else factory) == factory]


def held_counts(rows: Iterable[dict[str, Any]], marks: Iterable[Any], user: Any, *, factory: int, scene: bool) -> dict[str, int]:
    """위 탭 숫자(쿼리 0) — ``mine`` = 내 몫이 작업 중인 장(내가 쓸 수 있는 파트 — 판 카드 ``mine_row`` 와 같은 판정),
    ``crew`` = 아직인 몫이 한 사람이라도 있는 작업 중 장(파트 넷 합). 장 = 확정 도면 한 장 × 파트, 보는 공장 장만.

    Args:
        rows: 첫 화면 행 전부(생산 단계 줄만 센다).
        marks: 그 주문들 표시 줄(화면 생산 주문 전체를 한 번 읽은 것).
        user: 보는 사람.
        factory · scene: 보는 공장 · 2공장 그림 켬(:func:`board_ctx` 와 같은 값).

    Returns:
        ``{"mine": n, "crew": n}``.
    """
    slots = {(int(m.order_id), str(m.drawing_key), str(m.part)): m for m in marks}
    uid = getattr(user, "id", None)
    mine_parts = set(writable_parts(user))
    mine = crew = 0
    for row in card_rows(rows):
        oid = int(row["id"])
        files = row_files(row)  # 도면 0장 생산 줄 = 주문 카드 한 장(@order)
        for _no, entry in factory_files(row, files, factory=factory, scene=scene):
            for part in PRODUCTION_PART_KEYS:
                mark = slots.get((oid, str(entry["key"]), part))
                if mark is None or str(mark.state or "") != MARK_STATE_NEED:
                    continue
                people = mc.crew_of(mark)
                crew += any(not mc.is_done(m) for m in people)
                mine += part in mine_parts and mc.share_of(people, uid) == mc.SHARE_HELD
    return {"mine": mine, "crew": crew}


__all__ = ["MarkIndex", "SheetIndex", "board_ctx", "card_rows", "factory_files", "fetch_part_marks", "for_part", "held_counts",
           "index_marks", "order_marks_of"]
