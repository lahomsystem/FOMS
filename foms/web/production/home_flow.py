"""생산 첫 화면 새 흐름 — 탭 판정 · 표시 줄 읽기 · '내 공정' · '작업 중' 템플릿 값 · 위 탭 숫자(설계서
2026-11-28-production-my-steps-flow §3-1 · §3-4 · §3-6 · §5, 사장님 답 28 "스위치 없이 한 번에" · 30 "탭을 따로 둠").

``home.py`` 는 부르기만 한다(파일 500줄 래칫). 문(태블릿 도면 카드 기기 문 + 폰 아님):

* 파트 계정 = ``날짜`` · ``내 공정 N``(``tab=mine``) · ``바뀐 것`` · ``찾기``.
* 반장 · 관리자 · 읽기 전용 = ``날짜`` · ``작업 중 N``(``tab=crew``) · ``남은 공정 N``(``tab=steps`` 그대로) · ``바뀐 것`` · ``찾기``.
* PC(마우스) · 폰 = 지금 그대로 — 문 밖에서 ``mine`` · ``crew`` 를 열면 날짜로 돌린다(지금 ``parts`` 와 같은 꼴), 판 설정 ``flow`` ·
  탭 숫자 ``counts.mine`` · ``counts.crew`` 키도 없다.

쿼리: 새 쿼리 없음 — 문 안 전체 페이지의 날짜 · '도면 카드' · '내 공정' · '작업 중' 탭은 이미 하던 표시 줄 읽기 **한 번**을 화면 생산
주문 전체로 넓혀(``order_id IN``) 탭 숫자 · 새 탭 재료를 같이 만든다. 날 조각(``view=day``)은 그 날 장만 읽는다(지금 그대로).
'남은 공정' · '바뀐 것' · '찾기' 탭은 표시 줄을 안 읽으므로 숫자가 None 이다(쿼리를 더하지 않는다 — 화면이 ``?view=counts`` 로 받는다).
"""

from __future__ import annotations

import datetime
from typing import Any, Optional

from flask import request, url_for

from foms.services.feature_flags import (
    is_mobile_v2_shell,
    resolve_shell_variant_cached,
    wants_coarse_pointer_surfaces,
    wants_wide_only_surfaces,
)
from foms.services.production.crew_board import CREW_ALL, build_crew, crew_part
from foms.services.production.factory_scope import board_factory, scene_on
from foms.services.production.my_steps import build_my_steps
from foms.services.production.part_access import VIEW_ADMIN, VIEW_PART, VIEW_READONLY, VIEW_SUB
from foms.services.production.part_board import board_head, resolve_board_part
from foms.services.production.part_board_ctx import board_ctx, card_rows, fetch_part_marks, held_counts
from foms.services.production.part_screen import drawn_order_ids, read_screen_marks
from foms.services.production_home_days import production_home_days

FLOW_MINE = 'mine'
FLOW_CREW = 'crew'
FLOW_TABS = (FLOW_MINE, FLOW_CREW)
HOME_TABS = ('date', 'steps', 'changes', 'all', 'parts', FLOW_MINE, FLOW_CREW)
#: '도면 카드' 화면(?tab=parts) · '작업 중' 탭을 여는 보기 모드 — 관리자 · 대신(반장, 2026-11-23 §4-12 · 승인 때 고친 것 5) ·
#: 읽기 전용(D55). 파트 계정은 날짜 탭에서 바로 카드를 본다(D50).
PARTS_TAB_MODES = (VIEW_ADMIN, VIEW_SUB, VIEW_READONLY)
#: 위 탭 숫자를 같은 표시 줄 한 번으로 세는 탭(문 안 전체 페이지만).
COUNTED_TABS = ('date', 'parts', FLOW_MINE, FLOW_CREW)
_HOME_ENDPOINT = 'erp_production_page.erp_production_home'


def tablet_part_surface(user: Any) -> bool:
    """도면 카드 화면의 기기 문(설계서 §15.6 '문') — 모바일 v2 셸 + 터치 기기.

    마우스 기기(``foms_ptr=fine``)는 카드를 아예 그리지 않는다(시공 3분할 선례). 보이기는 태블릿 가로 미디어쿼리(parts.css).
    """
    uid = getattr(user, 'id', None)
    return is_mobile_v2_shell(resolve_shell_variant_cached(uid)) and wants_coarse_pointer_surfaces()


def flow_door(mode: str, surface: bool) -> Optional[str]:
    """새 탭 문 — 도면 카드 기기 문 + 긴 변 992 이상(폰 아님, ``foms_scr`` — [도면 카드로 보기]와 같은 문). 파트 계정 = ``mine``,
    반장 · 관리자 · 읽기 전용 = ``crew``, 그 밖(PC · 폰 · 볼 수 없는 사람) = None."""
    if not (surface and wants_wide_only_surfaces()):
        return None
    if mode == VIEW_PART:
        return FLOW_MINE
    return FLOW_CREW if mode in PARTS_TAB_MODES else None


def resolve_home_tab(raw: Any, mode: str, surface: bool, door: Optional[str]) -> str:
    """주소의 탭 → 그릴 탭. 파트 계정의 '남은 공정'(D50) · 문 밖의 '도면 카드'(D55) · 문 밖 · 남의 새 탭은 날짜로 돌린다."""
    tab = raw if raw in HOME_TABS else 'date'
    if tab == 'steps' and mode == VIEW_PART:
        return 'date'
    if tab == 'parts' and not (surface and mode in PARTS_TAB_MODES):
        return 'date'
    if tab in FLOW_TABS and tab != door:
        return 'date'
    return tab


def wide_marks(tab: str, door: Optional[str], day_view: bool) -> bool:
    """표시 줄 읽기를 화면 생산 주문 전체로 넓힐지 — 문 안 · 전체 페이지 · 숫자를 세는 탭."""
    return door is not None and not day_view and tab in COUNTED_TABS


def screen_marks(db: Any, tab: str, pane: Optional[dict[str, Any]], rows: list[dict[str, Any]], pc_view: bool,
                 today: datetime.date, *, wide: bool) -> Optional[list[Any]]:
    """칸 아래 이름(설계서 2026-11-23 §4-10)을 달 줄의 표시 줄을 한 번 읽는다 — 날짜 탭 고른 장 · PC 찾기 탭 생산 줄.

    ``wide``(:func:`wide_marks`)면 같은 한 번을 화면 생산 주문 전체로 넓혀 돌려준다(이름은 고른 장 줄에만 단다) — 날짜 · '도면 카드' 판,
    '내 공정' · '작업 중' 재료, 위 탭 숫자가 같은 줄을 쓴다. 넓히지 않은 '도면 카드' 탭(날 조각)은 판이 그 장 줄을 읽게 None.
    """
    flow = card_rows(rows) if wide else []
    if tab == 'date' and pane is not None:  # 남의 공장 줄(2공장 묶음)도 같은 한 번에 — 판이 그 카드 글을 같은 줄로 그린다
        return read_screen_marks(db, [*(pane.get('make_rows') or []), *(pane.get('elsewhere_rows') or [])], today, more=flow)
    if tab == 'all' and pc_view:
        read_screen_marks(db, rows, today)
    return fetch_part_marks(db, drawn_order_ids(flow)) if wide else None


def flow_view(door: Optional[str]) -> Optional[dict[str, str]]:
    """판 설정 · 탭 줄의 ``flow`` — ``{tab: 'mine' 또는 'crew', mine_href: 그 탭 주소}``(문 밖은 None — 판 설정에 키 없음)."""
    if door is None:
        return None
    return {'tab': door, 'mine_href': url_for(_HOME_ENDPOINT, tab=door)}


def flow_counts(user: Any, rows: list[dict[str, Any]], marks: Optional[list[Any]], door: Optional[str],
                counted: bool) -> dict[str, Optional[int]]:
    """위 탭 숫자 ``{mine, crew}`` — 문 밖은 빈 dict(키 없음), 표시 줄을 안 읽은 탭은 None(:func:`wide_marks` 거짓)."""
    if door is None:
        return {}
    if not counted:
        return {'mine': None, 'crew': None}
    factory = board_factory(user, request.args.get('factory'))
    scene = scene_on((r.get('structured_data') or {} for r in rows), factory)
    return held_counts(rows, marks or [], user, factory=factory, scene=scene)


def counts_view_flow(db: Any, user: Any, rows: list[dict[str, Any]], door: Optional[str]) -> dict[str, Optional[int]]:
    """숫자만 받는 길(``?view=counts``)의 ``mine`` · ``crew`` — 문 안이면 화면 생산 주문 표시 줄 한 번(+1), 문 밖은 키 없음."""
    if door is None:
        return {}
    return flow_counts(user, rows, fetch_part_marks(db, drawn_order_ids(card_rows(rows))), door, True)


def flow_tab(db: Any, user: Any, tab: str, rows: list[dict[str, Any]], marks: Optional[list[Any]],
             today: datetime.date) -> tuple[Optional[dict[str, Any]], dict[str, Any]]:
    """'내 공정' · '작업 중' 탭 — (판 머리, 템플릿 값 ``{my_steps, crew}``). 판 머리(:func:`~part_board.board_head`)는 확인 창 · 판 설정 ·
    스크립트를 싣는 데 쓴다(날짜 판과 같은 카드 · 같은 스크립트). 카드 맥락은 화면 생산 주문 전체(펜 기록 머리 = 스위치 켬만 +1)."""
    asked = request.args.get('part')
    picked = asked if tab == FLOW_MINE else (None if crew_part(asked) == CREW_ALL else crew_part(asked))
    mode, part = resolve_board_part(user, picked)
    if part is None:
        return None, {'my_steps': None, 'crew': None}
    cards = card_rows(rows)
    ctx = board_ctx(db, user, cards, mode=mode, part=part, marks=marks, today=today, factory=request.args.get('factory'),
                    scene_rows=rows)
    head = board_head(user, mode, part, ctx)
    if tab == FLOW_MINE:
        strip = production_home_days(rows, today)['strip']
        return head, {'my_steps': build_my_steps(user, cards, ctx, strip, today=today), 'crew': None}

    def href(key: str) -> str:
        return url_for(_HOME_ENDPOINT, tab=FLOW_CREW, part=None if key == CREW_ALL else key, factory=head['url_factory'])

    crew = build_crew(user, cards, ctx, part=asked, today=today, href=href)
    # 2공장 그림이 켜진 관리자의 공장 고르기(도면 카드 화면과 같은 꼴) — 주소는 여기서 한 번 짓는다(템플릿은 주소를 안 짓는다)
    picked_part = None if crew['part'] == CREW_ALL else crew['part']
    crew['factories'] = [{'key': f, 'href': url_for(_HOME_ENDPOINT, tab=FLOW_CREW, part=picked_part, factory=f)}
                         for f in (1, 2)] if head['factory_pick'] else []
    return head, {'my_steps': None, 'crew': crew}


__all__ = ['COUNTED_TABS', 'FLOW_CREW', 'FLOW_MINE', 'FLOW_TABS', 'HOME_TABS', 'PARTS_TAB_MODES', 'counts_view_flow', 'flow_counts',
           'flow_door', 'flow_tab', 'flow_view', 'resolve_home_tab', 'screen_marks', 'tablet_part_surface', 'wide_marks']
