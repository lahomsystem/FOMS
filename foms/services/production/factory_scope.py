"""2공장 생산 쪽 한 곳 규칙 — 공장 문 · 보는 공장 · 2공장 그림 켬 · 남의 공장 카드 글(설계서 2026-11-23 §4-6 · §4-13 · §5 · C6 · C9).

**순수 계산 · 쿼리 0** — 장의 공장은 주문 JSON(:mod:`foms.services.orders.drawing_factory`), 계정 공장은 이미 읽은 사용자 행
(:mod:`foms.services.production.part_access`)에서 읽는다. 권한 판정은 ``part_access`` 한 곳(:func:`can_write_sheet` ·
:func:`writable_factories`)만 부른다 — 역할 · 팀을 여기서 따로 견주지 않는다.

* **공장 문**(§4-6 · C6): 쓰기 API 는 남의 공장 장을 403 ``OTHER_FACTORY`` 로 막는다(관리자는 두 공장). 내가 작업하는 장의
  시작 취소는 된다(§4-6 '되는 것' — 시작한 뒤 장이 옮겨진 옛 담당, 같이 작업하는 사람 중 하나여도 — multi-holder §7-2).
  공정 칸(주문에 값 하나)은 지금 장이 **모두** 남의 공장인 주문만 같은 403 으로 막는다(:func:`order_factory_gate` — 비평 C02). 섞인 주문은
  지금 규칙 그대로(반장 한 번에 두 공장 장 — 2026-11-25 D1 검토 판결 A), 장 0장 주문도 그대로.
* **보는 공장**: 도면 판 = 관리자는 판 머리에서 고른 공장(주소 ``factory=``, 처음 = 계정 값 또는 1공장 — §19 열한째), 그 밖은
  계정 공장(비면 1공장). 날짜 줄의 묶음(남의 공장 줄 · 내 공장 완료)은 한 공장 계정(파트 계정 · 반장)에게만 — 관리자 · 보기만
  하는 직원 · PC 는 두 공장을 합쳐 본다(§19 열한째 · PC 는 감독용).
* **2공장 그림 켬**(§3): 그날 읽은 행 중 2공장 장이 하나라도 있거나 보는 공장이 2공장일 때만. 꺼지면 모든 2공장 그림이 없고
  화면이 지금과 같다.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from foms.services.orders.drawing_factory import has_second_factory, present_factories, sheet_factory
from foms.services.production import mark_crew as mc
from foms.services.production.factory_constants import DEFAULT_FACTORY, FACTORIES, FACTORY_2, factory_label, normalize_factory
from foms.services.production.part_access import VIEW_ADMIN, VIEW_SUB, can_write_sheet, part_view_mode, user_factory, writable_factories
from foms.services.production.part_constants import PRODUCTION_PART_LABELS, basic_word
from foms.services.production.part_mark_gates import Gate
from foms.services.production.part_mark_rules import ACTION_RELEASE

OTHER_FACTORY = "OTHER_FACTORY"


def other_factory_note(factory: Any) -> str:
    """남의 공장 카드를 누르면 뜨는 글(§9) — "2공장에서 작업하는 도면이에요."."""
    return f"{factory_label(factory)}에서 작업하는 도면이에요."


def other_factory_message(factory: Any) -> str:
    """쓰기 API 거절 글(403 ``OTHER_FACTORY``) — 카드 글 + 다시 받기 안내(늦은 화면은 옮겨진 장을 아직 내 것으로 그린다)."""
    return f"{other_factory_note(factory)} [다시 받기]를 눌러 주세요."


def factory_gate(user: Any, sd: Any, entry: dict[str, Any], *, action: str, row: Any = None) -> Optional[Gate]:
    """남의 공장 장 쓰기를 막는다(§4-6 · C6) — 관리자는 두 공장, 파트 계정 · 반장은 자기 공장만.

    Args:
        user: 누른 사람(이미 읽은 행).
        sd: 잠근 주문의 ``structured_data``.
        entry: 누른 장(확정 도면 항목 — ``sheet_id`` · ``key``).
        action: 누름.
        row: 그 장 · 그 파트 표시 줄(없으면 None) — 내가 작업하는 사람 목록에 있는 장의 시작 취소는 막지 않는다.

    Returns:
        막히면 403 :class:`Gate`(``factory`` = 장의 공장), 아니면 None.
    """
    factory = sheet_factory(sd, entry)
    if can_write_sheet(user, factory):
        return None
    me = getattr(user, "id", None)
    if action == ACTION_RELEASE and row is not None and mc.find(mc.crew_of(row), me) is not None:
        return None
    return Gate(403, OTHER_FACTORY, other_factory_message(factory), {"factory": factory})


def order_factory_gate(user: Any, sd: Any) -> Optional[Gate]:
    """공정 칸 쓰기(켜기 · 끄기 · 반장 손 체크 · 통째 작업 풀어 쓰기)의 공장 문(비평 C02) — 지금 장이 모두 남의 공장이면 403.

    글 · 코드는 도면 칸의 남의 공장 거절(:func:`factory_gate`)과 같다. 섞인 주문(내 공장 장이 하나라도 있음) · 장 0장은 None(지금 규칙).

    Returns:
        막히면 403 :class:`Gate`(``factory`` = 첫 공장), 아니면 None.
    """
    present = present_factories(sd)
    if not present or any(can_write_sheet(user, f) for f in present):
        return None
    return Gate(403, OTHER_FACTORY, other_factory_message(present[0]), {"factory": present[0]})


def order_elsewhere(user: Any, sd: Any) -> Optional[dict[str, str]]:
    """'내 공정' 줄 · 판의 [<공정> 완료] 자리 막힘(:func:`order_factory_gate` 와 같은 판정) — 칩 "2공장 작업" · 누르면 뜨는 글."""
    gate = order_factory_gate(user, sd)
    if gate is None:
        return None
    factory = gate.extra["factory"]
    return {"kind": "elsewhere", "text": elsewhere_chip(factory), "why": other_factory_note(factory), "code": OTHER_FACTORY}


def steps_factory_note(user: Any, sd: Any) -> Optional[str]:
    """반장이 장이 모두 남의 공장인 주문의 공정 칸을 볼 때 읽기 전용 까닭(카드 글 "2공장에서 작업하는 도면이에요.") — 아니면 None.

    공정 API 403(:func:`order_factory_gate`)과 같은 판정 — 작업 시트 공정 칸이 본다(누른 뒤 거절 대신 누르기 전에).
    관리자는 두 공장이라 늘 None, 파트 계정 · 파트도 반장도 아닌 생산팀은 공정 칸 잠금(``steps_lock``)이 먼저다.
    """
    if part_view_mode(user) != VIEW_SUB:
        return None
    gate = order_factory_gate(user, sd)
    return other_factory_note(gate.extra["factory"]) if gate is not None else None


def elsewhere_chip(factory: Any) -> str:
    """남의 공장 칩 글 — "2공장 작업"(도면 카드 · '내 공정' 같은 글)."""
    return f"{factory_label(factory)} 작업"


def board_factory(user: Any, requested: Any = None) -> int:
    """도면 판을 볼 공장 — 관리자는 고른 공장(모르는 값 · 없음 = 계정 값 또는 1), 그 밖은 계정 공장(비면 1)."""
    if part_view_mode(user) == VIEW_ADMIN:
        try:
            picked = normalize_factory(requested)
        except ValueError:
            picked = None
        if picked is not None:
            return picked
    return user_factory(user)


def home_factory(user: Any) -> Optional[int]:
    """날짜 줄을 공장으로 묶어 볼 사람의 공장 — 한 공장만 쓰는 계정(파트 계정 · 반장)이면 그 공장, 그 밖은 None(두 공장 합침)."""
    mine = writable_factories(user)
    return mine[0] if len(mine) == 1 else None


def scene_on(sds: Iterable[Any], viewer: Optional[int]) -> bool:
    """2공장 그림을 켤지(§3) — 보는 공장이 2공장이거나 읽은 주문 중 2공장 장이 하나라도 있으면."""
    return viewer == FACTORY_2 or any(has_second_factory(sd) for sd in sds)


def other_factories(viewer: int) -> tuple[int, ...]:
    """보는 공장이 아닌 공장들(화면 순서)."""
    return tuple(f for f in FACTORIES if f != (viewer if viewer in FACTORIES else DEFAULT_FACTORY))


def elsewhere_head(factory: int, count: int) -> str:
    """남의 공장 카드 묶음 머리 — "2공장 작업 4장"."""
    return f"{factory_label(factory)} 작업 {count}장"


def elsewhere_line(part: str, state: str, *, picked: Optional[str], done: Optional[str],
                   hand: Optional[dict[str, Any]] = None) -> str:
    """남의 공장 카드의 글 한 줄(색 칸 없이, §4-13) — "최가은 작업 중" · "엣지 완료 · 최가은" · "기본 · 김재단"(조립 "조립 없음 · 최조립") · "미정".

    Args:
        part: 보는 파트.
        state: 카드 상태(none · need · basic · done · hand).
        picked: 작업하는 사람 이름 줄("이시영 · 김재단 외 1" — multi-holder Q20). done: 완료한 사람 이름 줄.
        hand: 손 체크 칸(:func:`~foms.services.production.part_card_state.hand_cell`).
    """
    if state == "hand" and hand:
        return str(hand["text"])
    if state == "need":
        return f"{picked} 작업 중" if picked else "작업 중"
    if state in ("done", "basic"):
        head = f"{PRODUCTION_PART_LABELS[part]} 완료" if state == "done" else basic_word(part)
        return f"{head} · {done}" if done else head
    return "미정"


def elsewhere_info(card: dict[str, Any], part: str, factory: int, row: Any = None) -> dict[str, str]:
    """카드 한 장의 남의 공장 칸 — 칩 "2공장"(글 "박엣지 작업 중" 과 겹말이 안 되게, 생산 비평 C29) · 글 한 줄 · 누르면 뜨는 글.

    Args:
        card: 카드 자료(``state`` · 한 명짜리 이름 칸 · ``hand``).
        part: 보는 파트. factory: 그 장의 공장.
        row: 그 장 · 그 파트 표시 줄(주면 이름을 작업하는 사람 목록에서 — "이시영 · 김재단 작업 중", 안 주면 카드의 한 명짜리 칸).
    """
    crew = mc.crew_of(row) if row is not None else []
    picked = mc.name_line(mc.names(crew)) or card.get("picked_by_name")
    done = mc.name_line(mc.done_names(crew)) or card.get("done_by_name")
    return {"factory": str(factory), "chip": factory_label(factory),
            "text": elsewhere_line(part, card["state"], picked=picked, done=done, hand=card.get("hand")),
            "why": other_factory_note(factory)}


__all__ = ["OTHER_FACTORY", "board_factory", "elsewhere_chip", "elsewhere_head", "elsewhere_info", "elsewhere_line", "factory_gate",
           "home_factory", "order_elsewhere", "order_factory_gate", "other_factories", "other_factory_message", "other_factory_note",
           "scene_on", "steps_factory_note"]
