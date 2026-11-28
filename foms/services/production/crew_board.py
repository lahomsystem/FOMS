"""'작업 중' 탭(``?tab=crew``) 읽기 모델 — 반장 · 관리자 · 읽기 전용이 태블릿 가로에서 "누가 무엇을 담았는지" 본다(설계서
2026-11-28-production-my-steps-flow §3-6 · 사장님 답 7 · 13 · 18 · 30 · 32).

* 파트 칩: ``전체`` · 재단 · 엣지 · 조립 · 검수(주소 ``?part=`` — 모르는 값 · 없음 = 전체).
* 사람 묶음: 그 파트에서 자기 몫이 작업 중인 장을 가진 사람마다 한 묶음(파트 순서 안에서 이름순). 같이 작업하는 장은 아직인 사람
  **모두의** 묶음에 같은 카드가 선다(답 32). 자기 몫을 끝낸 사람("1/2 완료")의 묶음에는 안 선다.
* 미정(맨 아래): 파트마다 아무도 안 고른 장 수(``counts`` — 손 체크 · 기본 · 완료는 밖, 막힌 장 · 검수 전 장은 셈). 파트를 고르면 그
  파트 미정 카드(시공일 순 · 200장 캡), ``전체`` 면 카드 없이 숫자만(``cards`` None).
* 카드 = :func:`~foms.services.production.part_board.build_card` 그 dict(보는 사람 = 반장 · 관리자 · 읽기 전용 꼴) + ``part`` ·
  ``part_label`` · ``day_key``. 사람 묶음 카드도 200장 캡(``hidden``). 남의 공장 장(2공장)은 안 든다(판과 같은 공장 판정).

쿼리 0 — 표시 줄 · 판 맥락은 부르는 쪽(:mod:`foms.web.production.home_flow`)이 만들어 넘긴다.
"""

from __future__ import annotations

import datetime
from typing import Any, Callable, Optional

from foms.services.production import mark_crew as mc
from foms.services.production import part_board as pb
from foms.services.production.my_steps import strip_key
from foms.services.production.part_board_ctx import factory_files, for_part
from foms.services.production.part_constants import (
    MARK_STATE_NEED,
    MARK_STATE_NONE,
    PRODUCTION_PART_KEYS,
    PRODUCTION_PART_LABELS,
)
from foms.services.production.ship_dates import row_due

#: 파트 칩 '전체' 열쇠 · 글.
CREW_ALL = "all"
CREW_ALL_LABEL = "전체"


def crew_part(requested: Any) -> str:
    """주소 ``?part=`` → 고른 파트 key 또는 ``all``(모르는 값 · 없음)."""
    text = str(requested or "").strip().lower()
    return text if text in PRODUCTION_PART_KEYS else CREW_ALL


def _due_order(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """시공일 순(판정 기준 출고일 빠른 순 · 출고일 없음 맨 뒤 · 같은 날은 주문 번호 순)."""
    def key(row: dict[str, Any]) -> tuple[int, datetime.date, int]:
        day = row_due(row)
        return (0, day, int(row["id"])) if day else (1, datetime.date.min, int(row["id"]))
    return sorted(rows, key=key)


def _card(row: dict[str, Any], entry: dict[str, Any], position: tuple[int, int, int], ctx: dict[str, Any], part: str,
          today: datetime.date) -> dict[str, Any]:
    card = pb.build_card(row, entry, position, ctx["slots"], ctx)
    card.update(part=part, part_label=PRODUCTION_PART_LABELS[part], day_key=strip_key(row, today))
    return card


def build_crew(user: Any, rows: list[dict[str, Any]], ctx: dict[str, Any], *, part: Any, today: datetime.date,
               href: Callable[[str], str], cap: Optional[int] = None) -> dict[str, Any]:
    """'작업 중' 탭 재료.

    Args:
        user: 보는 사람(반장 · 관리자 · 읽기 전용).
        rows: 카드를 만들 줄(:func:`~foms.services.production.part_board_ctx.card_rows`).
        ctx: 그 줄로 만든 판 맥락(:func:`~foms.services.production.part_board_ctx.board_ctx`).
        part: 주소 ``?part=``(:func:`crew_part` 로 읽는다).
        today: KST 오늘.
        href: 파트 칩 주소 만들기(파트 key 또는 ``all`` → 주소).
        cap: 카드 상한(없으면 판과 같은 :data:`~part_board.PART_BOARD_CARD_CAP`).

    Returns:
        ``{part, parts: [{key, label, href}], people: [{name, part, part_label, cards}], hidden,
        none: {counts: {파트: n}, cards: [카드] 또는 None, hidden}}`` — ``hidden`` = 캡에 밀린 사람 묶음 카드(서로 다른 장) 수.
    """
    cap = pb.PART_BOARD_CARD_CAP if cap is None else cap
    picked = crew_part(part)
    shown_parts = PRODUCTION_PART_KEYS if picked == CREW_ALL else (picked,)
    part_ctx = {p: for_part(ctx, user, p) for p in PRODUCTION_PART_KEYS}
    slots, hands = ctx["slots"], ctx["hands"]
    people: dict[tuple[int, str, int], dict[str, Any]] = {}
    none_counts = {p: 0 for p in PRODUCTION_PART_KEYS}
    none_slots: list[tuple[dict[str, Any], dict[str, Any], tuple[int, int, int]]] = []
    built = hidden = 0
    for pos, row in enumerate(_due_order(rows)):
        oid = int(row["id"])
        files = ctx["files"].get(oid) or []
        for no, entry in factory_files(row, files, factory=ctx["factory"], scene=ctx["scene"]):
            for p_index, p in enumerate(PRODUCTION_PART_KEYS):
                mark = slots.get((oid, str(entry["key"]), p))
                state = str(getattr(mark, "state", None) or MARK_STATE_NONE)
                if state == MARK_STATE_NONE and not (hands.get(oid) or {}).get(p):
                    none_counts[p] += 1
                    if p == picked:
                        none_slots.append((row, entry, (pos, no, len(files))))
                    continue
                left = [m for m in mc.crew_of(mark) if not mc.is_done(m)] if state == MARK_STATE_NEED else []
                if not left or p not in shown_parts:
                    continue
                if built >= cap:
                    hidden += 1
                    continue
                built += 1
                card = _card(row, entry, (pos, no, len(files)), part_ctx[p], p, today)
                for member in left:  # 같이 작업 = 아직인 사람마다 같은 카드(답 32)
                    name = str(member.get("name") or "").strip()
                    uid = member.get("uid")
                    group = people.setdefault((p_index, name, uid if isinstance(uid, int) else -1),
                                              {"name": name, "part": p, "part_label": PRODUCTION_PART_LABELS[p], "cards": []})
                    group["cards"].append(card)
    none_cards = None
    if picked != CREW_ALL:
        none_cards = [_card(row, entry, position, part_ctx[picked], picked, today) for row, entry, position in none_slots[:cap]]
    parts = [{"key": CREW_ALL, "label": CREW_ALL_LABEL, "href": href(CREW_ALL)}]
    parts += [{"key": p, "label": PRODUCTION_PART_LABELS[p], "href": href(p)} for p in PRODUCTION_PART_KEYS]
    return {
        "part": picked, "parts": parts,
        "people": [people[key] for key in sorted(people)],  # 파트 순서 → 이름순(같은 이름은 사람 id 순 — 따로 묶는다)
        "hidden": hidden,
        "none": {"counts": none_counts, "cards": none_cards,
                 "hidden": max(0, len(none_slots) - cap) if picked != CREW_ALL else 0},
    }


__all__ = ["CREW_ALL", "build_crew", "crew_part"]
