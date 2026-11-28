"""생산팀 첫 화면 — 전체 주문 한 줄(설계서 §12, 2026-11-09 D10·D12).

``blueprint.py`` 의 Blueprint(``erp_production_page``)에 라우트만 더한다(파일 500줄 래칫).
``foms/web/production/__init__.py`` 가 이 모듈을 import 해야 라우트가 붙는다.
"""

from __future__ import annotations

import datetime
import re
import time

from flask import abort, g, jsonify, make_response, render_template, request

from db import get_db
from models import Order
from foms.api.production.orders import _PRODUCTION_DEFECT_REASONS
from foms.services.common.ept_b7_profile import apply_ept_b7_render_headers
from foms.services.common.partner_order_filter import partner_filter_value
from foms.services.common.erp_shell_http import apply_erp_shell_fragment_headers, wants_erp_shell_tab_body
from foms.services.datetime_kst import get_today_kst
from foms.services.feature_flags import wants_wide_only_surfaces, wants_wide_viewport_surfaces
from foms.services.production.factory_constants import factory_label
from foms.services.production.factory_home import attach_factory_rows, attach_factory_stage
from foms.services.production.factory_scope import home_factory, scene_on
from foms.services.orders.order_mutation_policy import user_can_read_order
from foms.services.production.home_access import can_view_production_home
from foms.services.production.home_step_panel import (
    attach_step_blocks,
    attach_step_confirm,
    attach_step_panels,
    parse_step_order,
    step_confirm_ids,
    step_panel_for,
)
from foms.services.production.part_access import VIEW_PART, VIEW_SUB, part_account_parts, part_view_mode, user_factory
from foms.services.production.part_board import build_part_board, part_sync_cursor
from foms.services.production.drawing_notes_read import pen_config
from foms.services.production.part_constants import PART_CUT, production_parts_label
from foms.services.production.part_marks_query import marks_by_order
from foms.services.production.part_screen import morning_chip
from foms.services.production.pc_view import attach_pc_inbox, attach_pc_rows, pc_due, production_screen_flags
from foms.services.production.ship_dates import ship_fields
from foms.services.production.sync_blocks import DONE_BLOCK
from foms.services.production_change_alerts import collect_production_tombstones
from foms.services.production_home_changes import (
    DONE_ALL_VALUE,
    production_home_attach_change_by,
    production_home_changes_view,
)
from foms.services.production_sheet_view import build_production_sheet_view
from foms.services.production_home_days import production_home_days
from foms.services.production_home_read_model import (
    build_production_home,
    production_home_counts,
    production_home_groups,
    production_home_mine_only,
    production_home_step_queues,
)

#: 날짜 한 장 조각(``?view=day&day=``) — 날을 누르면 JS 가 그 장만 받아 끼운다(설계서 §15.6 '날 고르기', 11-14).
#: 셸 조각(``view=fragment`` + 셸 머리글, 탭 몸통 전체)과 다른 값이라 둘이 섞이지 않는다.
DAY_VIEW = 'day'
#: 날짜 한 장 조각 응답 머리글 — 받은 장의 열쇠(JS 가 고른 날과 같은지 본다).
DAY_PANE_HEADER = 'X-FOMS-HOME-DAY'
#: '내 공정' 판 하나 조각(``?tab=steps&view=panel&step=&order=``) — 줄을 누르면 JS 가 그 판만 받아 끼운다(2026-11-22,
#: 날짜 한 장과 같은 꼴). 응답 머리글 = 받은 판의 주문 번호(JS 가 누른 줄과 같은지 본다).
PANEL_VIEW = 'panel'
PANEL_HEADER = 'X-FOMS-HOME-PANEL'
#: 위 탭 숫자만(``?view=counts`` — JSON ``{making, changed}``) — 도면 카드 쓰기가 주문 칸을 바꾼 뒤 한 번 받는다(2026-11-27
#: 사장님 "작업 시작하면 내 공정에 바로 반영"). 화면과 같은 행 · 같은 묘비로 세고 템플릿을 그리지 않는다.
COUNTS_VIEW = 'counts'
from foms.web.auth import login_required
from foms.web.production.blueprint import erp_production_page_bp
from foms.web.production.home_flow import (FLOW_TABS, PARTS_TAB_MODES, counts_view_flow, flow_counts, flow_door, flow_tab,
                                           flow_view, resolve_home_tab, screen_marks, tablet_part_surface, wide_marks)

_KST = datetime.timezone(datetime.timedelta(hours=9))
#: 셸 조각 ETag 에서 뺄 값 — 파트 판의 첫 받아 오기 기준 시각(그릴 때마다 바뀐다, home_parts_overlays.html).
#: 받은 시각('방금 받음')은 본문에 두지 않는다 — 셸이 받거나 304 로 확인한 때를 #main-content 에 적고 JS 가 읽는다(11-22).
#: PC [고치기] 단추의 서버 시각(``data-foms-prod-edit-now`` · 초 단위, home_pc_tools.html)도 뺀다(11-23) — 쓰기 팀 PC 가 늘 200 이라
#: 운영 올림 perf-gate 의 조건부 304 확인이 초 경계에 따라 떨어졌다. 본문 값은 그대로 둔다: foms-production-edit.js 가 단추마다
#: 처음 본 때부터 흐른 시간을 더하므로, 304 로 옛 단추가 남아도 켠 시각이 맞는다.
_ETAG_VOLATILE = re.compile(rb' data-(?:pp-since|foms-prod-edit-now)="[^"]*"')


def _part_screen(db, user, tab: str, mode: str, surface: bool, days, *, marks=None, today=None, full: bool = False,
                 door=None) -> dict:
    """파트 화면 템플릿 값 — 판(없으면 None) · [도면 카드로 보기] · '내 공정' 숨김 · 위 줄 제목 · JS 설정 · 아침 칩.

    판은 파트 계정의 날짜 탭(태블릿) 또는 관리자 · 대신 · 읽기 전용의 '도면 카드' 화면(?tab=parts)에서만 만든다(표시 줄 읽기 쿼리 +1 —
    날짜 탭은 칸 아래 이름이 읽은 줄 ``marks`` 를 다시 써 0).
    ``days`` 는 그릴 장만 담은 묶음(``{'panes': [고른 장], 'all_rows': 행}``) — 다른 날 판은 그 날을 누를 때 조각으로 만든다(11-14).
    아침 칩(설계서 2026-11-23 §4-9)은 파트 계정의 전체 페이지(``full``)에서만 — 쿼리 1, 날 조각에는 없다. 여러 파트 계정은
    내 파트 전부를 센다(같은 쿼리 한 번, §4-12). '내 공정' · '작업 중' 탭(문 안만, 2026-11-28 흐름)은 판 머리 + 재료(home_flow).
    """
    board, extra = None, {'my_steps': None, 'crew': None}
    # 30초 받아 오기(P15-7)의 첫 since = 그리는 서버 시각(기기 시계 아님). 표시 줄을 읽기 **전**에 잡는다.
    since = part_sync_cursor()
    if tab in FLOW_TABS:
        board, extra = flow_tab(db, user, tab, days['all_rows'], marks, today or get_today_kst())
    elif days['panes'] and surface and ((tab == 'date' and mode == VIEW_PART) or tab == 'parts'):
        board = build_part_board(db, user, days, part=request.args.get('part'), marks=marks, today=today,
                                 factory=request.args.get('factory'))
    name = getattr(user, 'name', None) or getattr(user, 'username', '') or ''
    config = None
    chip = None
    if board is not None:
        config = {
            'mode': board['mode'], 'part': board['part'], 'label': board['part_label'], 'writable': board['writable'],
            'verb': '자름' if board['part'] == PART_CUT else board['part_label'], 'me': name,
            'basic': board['basic'],  # 재단 '기본' · 조립 '조립 없음' 글 한 벌(없는 파트는 None — JS 는 글을 여기서만 읽는다)
            'me_id': getattr(user, 'id', None),
            # 서버 KST 오늘 — 받아 오기로 고친 카드의 "어제부터" 판정(기기 시계 대신, 설계서 2026-11-23 §4-9)
            'today': (today or get_today_kst()).isoformat(),
            # 제작 완료 성공 응답 때 그 주문 카드에 그릴 칸(받아 오기의 '생산 단계 아님' 칸과 같은 값 — 비평 C09)
            'done_block': DONE_BLOCK,
            **pen_config(user),  # 펜 기록 {on, can_write, first} — 스위치 꺼짐이면 키 없음(설정 그대로, 2026-11-28 약속 2)
            **({'flow': flow_view(door)} if door else {}),  # 새 흐름 {tab, mine_href} — 문 밖(PC · 폰)은 키 없음(2026-11-28 약속 1)
        }
        if full and mode == VIEW_PART and tab == 'date':
            chip = morning_chip(db, user, tuple(p['key'] for p in board['parts']), full_rows_of(days),
                                today or get_today_kst())
    return {
        'part_board': board,
        'part_config': config,
        'part_since': since if board is not None else None,
        'part_morning': chip,
        # 날짜 장 제목 옆 [도면 카드로 보기](11-21 사용자 ② — '도면 카드' 탭을 뺀 자리). 문은 예전 탭과 같고(관리자 · 대신 · 읽기 전용 +
        # 터치 기기), 화면 긴 변이 992 미만인 폰(``foms_scr``)은 가로로 돌려도 카드를 못 보니 뺀다. 주소(?tab=parts)는 그대로 열린다.
        'parts_link': surface and mode in PARTS_TAB_MODES and wants_wide_only_surfaces(),
        'hide_steps_tab': mode == VIEW_PART,
        'part_title': _home_title(mode, user, board, name) if surface else None,
        'nav_part': _nav_part(mode, user, board),
        'flow': flow_view(door), **extra,  # 탭 줄 · '내 공정' my_steps · '작업 중' crew(다른 탭은 None)
    }


def _nav_part(mode: str, user, board) -> str | None:
    """여러 파트 계정이 고른 파트 — 위 탭 [날짜] · [바뀐 것] · [찾기] · [다시 받기]가 주소에 싣는다(2026-11-23 §4-12).

    '바뀐 것' · '찾기'에 갔다 [날짜]로 돌아와도 고른 파트가 남게 한다. 판이 있으면 판이 고른 파트, 없으면(다른 탭 · PC · 폰) 주소
    ``part`` 가 내 파트일 때만. 파트 하나 · 파트 없는 계정 · 관리자 · 읽기 전용은 None — 지금 주소 그대로.
    """
    if mode != VIEW_PART:
        return None
    if board is not None:
        return board['part'] if board.get('pick') else None
    mine = part_account_parts(user)
    asked = str(request.args.get('part') or '').strip().lower()
    return asked if len(mine) > 1 and asked in mine else None


def _home_title(mode: str, user, board, name: str):
    """위 줄 큰 제목 (역할, 이름) — 파트 계정 "엣지 박엣지" · 반장 "반장 박반장", 어느 탭이든(사장님 2026-11-26). 그 밖은 None("생산")."""
    if mode == VIEW_PART:
        role = _title_parts(board) if board is not None else production_parts_label(part_account_parts(user))
        return (role, name) if role else None
    return ('반장', name) if mode == VIEW_SUB else None


def _title_parts(board: dict) -> str:
    """위 줄 큰 제목의 파트 이름 — 파트 하나면 그 이름(지금 그대로), 여럿이면 "재단 · 엣지"(2026-11-23 §8-1 여러 파트)."""
    if board.get('pick'):
        return production_parts_label([p['key'] for p in board['parts']]) or board['part_label']
    return board['part_label']


def full_rows_of(days) -> list:
    """아침 칩이 세는 줄 — 전체 행(``days['all_rows']``, 없으면 그릴 장의 만들 것)."""
    if days.get('all_rows') is not None:
        return days['all_rows']
    return [row for pane in days.get('panes') or [] for row in pane.get('make_rows') or []]


def _factory_scene(user, rows: list, pc_view: bool) -> dict:
    """2공장 그림(설계서 2026-11-23 §4-13 · §4-14 · §8-2) — 켜지면 행에 공장 칸을 달고 묶을 공장 · 위 줄 공장 글을 돌려준다.

    한 공장 계정(파트 계정 · 반장)의 태블릿 · 폰만 날짜 줄을 공장으로 묶는다(남의 공장 줄 · 내 공장 완료). 관리자 · 보기만 하는
    직원 · PC(감독용)는 두 공장을 합쳐 본다. 2공장 장이 하나도 없고 보는 공장이 1공장이면 아무것도 안 단다(지금 화면 그대로).
    """
    group = None if pc_view else home_factory(user)
    viewer = group or user_factory(user)
    if not scene_on((r.get('structured_data') or {} for r in rows), viewer):
        return {'group': None, 'label': None, 'on': False}
    attach_factory_rows(rows, viewer=viewer, group=group)
    return {'group': group, 'label': factory_label(group) if group else None, 'on': True}


def _step_panel_screen(tab: str, surface: bool, queues: dict | None) -> dict:
    """'내 공정' 탭 오른쪽 판(설계서 2026-11-21-production-my-steps-panel §3-1 · §3-6) 템플릿 값.

    문 = 도면 카드와 같은 기기 문(모바일 v2 셸 + 터치) + 넓은 창. 문 밖(PC 마우스 · 폰 · 세로 쿠키)은 판을 아예 그리지 않는다 —
    지금 화면 그대로. 터치인데 창이 좁아(세로) 뺐으면 생략 표식을 남겨 가로로 돌리면 화면을 다시 받는다 — 화면 긴 변이
    992 미만인 폰(``foms_scr``)은 가로로 돌려도 못 보므로 표식도 없다(폰 출력은 지금과 같다).
    판 자료는 이미 읽은 행에서(쿼리 0). 주소 ``order=`` 는 판이 있을 때만 읽는다(고른 줄 · 첫 탭).
    """
    door = tab == 'steps' and surface and queues is not None
    panel = door and wants_wide_viewport_surfaces()
    order = parse_step_order(request.args.get('order')) if panel else None
    pinned = attach_step_panels(queues, order) if panel else None
    return {
        'step_panel': panel,
        'step_panel_omitted': door and not panel and wants_wide_only_surfaces(),
        'step_pin': pinned,
        'step_order': order if pinned else None,
        'defect_reasons': _PRODUCTION_DEFECT_REASONS,
    }


def _attach_step_confirm(db, queues: dict | None, flags: dict, user) -> None:
    """'내 공정' 도면 있는 줄의 [<공정> 끝] 자리 막힘 — [끝]을 그리는 사람(``can_check_steps``)만, 도면 있는 막히지 않은 줄의 표시 줄을
    한 번에 읽어(+1, 그런 줄이 없으면 0) [끝] 대신 "재단 0/1 · 1장 미완료"(공정 API 409 와 같은 판정)를 단다. 옛 확인 창 자료
    (``step_confirm``)는 2026-11-27 지웠다 — 그 줄은 늘 이 막힘이 먼저였다.

    같은 표시 줄로 "남은 장이 고치는 도면뿐"인 줄은 [끝] 자리에 "도면 2 고치는 중"(2026-11-25 D1 검토 판결 D). [끝]이 없는 사람도 같은
    줄을 보도록, 도면별로 막힌 장이 있는 줄이 있을 때만 그 줄들의 표시 줄을 읽는다(그런 줄이 없으면 0 — 지금 쿼리 그대로).
    [끝]을 그리는 사람에게는 먼저 장이 모두 남의 공장인 줄을 "2공장 작업"으로 막는다(비평 C02 — 공정 API 와 같은 공장 문, 쿼리 0).
    """
    if queues is None:
        return
    confirm = bool(flags.get('can_check_steps'))
    if confirm:
        attach_step_blocks(queues, user)
    ids = step_confirm_ids(queues, fix_only=not confirm)
    if ids:
        attach_step_confirm(queues, marks_by_order(db, ids), confirm=confirm)


def _step_panel_response(db, tab: str, surface: bool, rows: list, flags: dict, user):
    """'내 공정' 판 하나 조각(``view=panel``) — 문 · 권한은 한 화면을 다 그릴 때와 같다(읽기만, 새 쓰기 길 없음).

    문 = 판이 있는 화면(``_step_panel_screen`` 과 같은 '내 공정' 탭 + 터치 v2 + 넓은 창). 파트 계정은 탭이 날짜로 돌아가(D50)
    여기 못 온다. 쓰기 단추는 같은 ``flags['can_act']``. 판 자료는 같은 행 · 같은 공정 줄에서(``step_panel_for``) — 줄이
    그 사이 다른 공정으로 옮겨 갔거나 문 밖이면 404(JS 가 '다시 받기' 글을 보인다).
    """
    door = tab == 'steps' and surface and wants_wide_viewport_surfaces()
    order = parse_step_order(request.args.get('order')) if door else None
    queues = production_home_step_queues(rows) if door else None
    _attach_step_confirm(db, queues, flags, user)  # [끝] 확인 창 자료(+1, 판 하나 조각도 다 그릴 때와 같은 단추)
    panel = step_panel_for(queues, request.args.get('step') or '', order) if door else None
    if panel is None:
        abort(404)
    _t0 = time.perf_counter()
    response = make_response(render_template('production/partials/home_step_panel.html', p=panel,
                                             q={'selected_id': panel['id']}, defect_reasons=_PRODUCTION_DEFECT_REASONS,
                                             **flags))
    response.headers[PANEL_HEADER] = str(panel['id'])
    response.headers['Cache-Control'] = 'no-store'
    apply_ept_b7_render_headers(response, route_id='erp_production_home_panel', render_ms=(time.perf_counter() - _t0) * 1000)
    return response


def _counts_response(db, user, rows: list, partner_org: str, door=None):
    """위 탭 숫자만(``view=counts``) — 화면의 '남은 공정 N' · '바뀐 것 N'과 같은 함수(``production_home_counts``) · 같은 묘비 읽기.

    도면 카드 쓰기(첫 카드 = 제작 시작 · 공정 칸 켜짐/꺼짐 · 제작 완료) 뒤 foms-production-parts-fresh.js 가 한 번 받는다 —
    쓰기 응답에 읽기를 얹지 않으려고 따로 받는다. 받아 두지 않는다(no-store).
    """
    # 켜진 프리랜서는 묘비도 내 주문만(행 들머리와 같은 판정) — 안 그러면 '바뀐 것' 숫자에 남의 취소 주문 수가 샌다.
    tombstones = collect_production_tombstones(db, user, production_home_mine_only(user), partner_org)
    counts = production_home_counts(rows, len(tombstones))
    response = jsonify({'success': True, 'error': None, 'data': {'counts': {  # 태블릿 문 안은 mine · crew 도(같은 키 — 표시 줄 +1)
        'making': counts['making'], 'changed': counts['changed'], **counts_view_flow(db, user, rows, door)}}})
    response.headers['Cache-Control'] = 'private, no-store'
    return response


def _sheet_drawing_link(user) -> dict | None:
    """작업 시트 공정 보기 줄을 누르면 갈 도면 화면(사장님 2026-11-27 "도면이 주, 작업 시트는 보기") — 도면 판이 있는 기기(태블릿 v2 터치 +
    긴 변 992 이상, 날짜 장 [도면 카드로 보기]와 같은 문)만. 관리자 · 반장 · 읽기 전용 = '도면 카드' 화면(``?tab=parts&part=&order=`` — '남은
    공정' 판 막힘 칸과 같은 주소), 파트 계정 = 날짜 탭 판(``?part=&order=``, 내 파트 줄만). 그 밖(PC · 폰 · 파트도 반장도 아닌 생산팀)은 None
    — 줄은 글만(PC 는 줄을 누르면 지금 도면 목록 창)."""
    if not (tablet_part_surface(user) and wants_wide_only_surfaces()):
        return None
    mode = part_view_mode(user)
    if mode in PARTS_TAB_MODES:
        return {'tab': 'parts', 'parts': None}
    return {'tab': None, 'parts': list(part_account_parts(user))} if mode == VIEW_PART else None


def selected_day_pane(days: dict) -> dict:
    """고른 날(주소 ``day=`` 또는 자동으로 고른 날)의 장 하나. ``production_home_days`` 의 ``selected`` 는 늘 장 열쇠다."""
    return next((p for p in days['panes'] if p['key'] == days['selected']), days['panes'][0])


def _require_home_user():
    """생산 홈·전체 화면 시트를 볼 수 있는 사람(관리자 · CS · 영업 · 생산 · 도면 · 시공 · 출고, 협력사 제외). 아니면 403."""
    user = getattr(g, 'current_user', None)
    # 규칙은 한 곳(home_access) — 태블릿 레일의 생산 단추 주소도 같은 답을 쓴다(D19).
    if not can_view_production_home(user):
        abort(403)
    return user


def _home_order_or_404(db, order_id: int, user) -> Order:
    """작업 시트 · 인쇄가 여는 주문 하나 — 살아 있는 ERP 주문이고 이 사람이 읽을 수 있는 주문(``user_can_read_order``)만.

    회사 직원은 모든 주문을 읽으므로 지금과 같다. 켜진 프리랜서는 자기 주문(연결 표 · 내가 만든 초안)만 — 남의 주문은 없는
    주문과 같은 404 다(있는지 알리지 않는다, 2026-11-27 옛 생산 보드 없애기 §3-2). 프리랜서 문지기가 주소 번호를 먼저 보고, 여기가 둘째 겹.
    """
    order = (
        db.query(Order)
        .filter(Order.id == order_id, Order.active_filter(), Order.is_erp_order.is_(True))
        .first()
    )
    if order is None or not user_can_read_order(user, order):
        abort(404)
    return order


@erp_production_page_bp.route('/production/home')
@login_required
def erp_production_home():
    """생산팀 첫 화면 — 탭 날짜(2주 띠 + 그날, D18 11-10) · 내 공정 · 바뀐 것 · 전체 주문(찾기). 설계서 §12 · D10·D12.

    볼 수 있는 사람 = ``home_access.can_view_production_home``(관리자 · CS · 영업 · 생산 · 도면 · 시공 · 출고), 쓰는 사람은
    더 좁다(관리자 · 생산팀, ``write_access.can_write_production``). 협력사 계정은 없다. 금액은 뷰 모델에 싣지 않는다(D7).
    켜진 프리랜서는 자기 주문만 본다 — 행(``build_production_home``)과 묘비 두 들머리가 ``production_home_mine_only`` 를 같이 쓴다.

    생산 파트(설계서 §15.6, P15-5): 파트 계정 + 태블릿이면 날짜 탭의 장에 도면 카드 판을 더 그리고(지금 장은
    태블릿 가로에서만 숨김), 관리자 · 대신 · 읽기 전용 직원은 태블릿에서 날짜 장 제목 옆 [도면 카드로 보기](``?tab=parts&part=&day=``, 11-21 위 탭에서 뺐다)로 본다.
    파트 계정은 '내 공정' 탭이 없다(D50, 기기 무관).

    날짜 · 도면 카드 탭은 고른 날 장 하나만 그린다(11-14, 예전 D5 는 15장을 다 보냈다). 띠 숫자는 모든 날을 센다.
    응답은 셋 — 전체 페이지 · 셸 조각(``view=fragment`` + 셸 머리글, 레일 · 아래 메뉴) · 날짜 한 장 조각
    (``view=day&day=``, 날을 누를 때 JS 가 받는다, 머리글 :data:`DAY_PANE_HEADER`). 셋 다 같은 자료 경로다.
    '내 공정' 판 하나 조각(``view=panel&step=&order=``, 줄을 누를 때, 머리글 :data:`PANEL_HEADER`)도 같은 행에서 만든다.
    """
    db = get_db()
    user = _require_home_user()
    mode = part_view_mode(user)
    surface = tablet_part_surface(user)
    door = flow_door(mode, surface)  # '내 공정' · '작업 중' 탭 문(태블릿, 2026-11-28 흐름) — PC · 폰은 None
    tab = resolve_home_tab(request.args.get('tab') or 'date', mode, surface, door)
    day_view = request.args.get('view') == DAY_VIEW and tab in ('date', 'parts')
    # 기기 · 권한 판정 한 곳(PC 보기 전용 · [고치기] · 쓰기 단추, 설계서 2026-11-21-production-pc-viewer §4 · §5 · §7)
    flags = production_screen_flags(user, request)
    # 협력사 거르기(헤더 메뉴 · 쿠키)를 보드와 같이 먹는다(설계서 2026-11-21-production-pc-viewer §9-11).
    partner_org = partner_filter_value(request)
    rows, stats = build_production_home(db, user, partner_org=partner_org)
    if request.args.get('view') == COUNTS_VIEW:
        return _counts_response(db, user, rows, partner_org, door)  # 위 탭 숫자만(도면 카드 쓰기 뒤 parts-fresh.js) — 그리기 없음
    today = get_today_kst()
    if flags['pc_view']:
        attach_pc_rows(rows, today)  # PC 줄 값(시공일 칸 · 누가 · 언제 · 늦음) — 이미 읽은 행에서, 쿼리 0
    if request.args.get('view') == PANEL_VIEW:
        return _step_panel_response(db, tab, surface, rows, flags, user)  # '내 공정' 판 하나(누른 줄) — 행 읽기 뒤 [끝] 확인 창 자료만 +1
    scene = _factory_scene(user, rows, flags['pc_view'])  # 2공장 칸(켜졌을 때만) — 날짜 묶기 전에 단다
    past_hidden = stats['past_hidden']
    # 띠 숫자는 모든 날을 같은 행에서 센다(쿼리 없음). 그리는 장은 고른 날 하나뿐 — 나머지 날은 누를 때 조각으로(11-14).
    # 주소 order= (옛 focus_order=)는 그 주문의 날 장을 고르고 줄에 테두리를 친다(바로가기 · 알림 · 검색, §9-10).
    days = (production_home_days(rows, today, request.args.get('day'), past_hidden=past_hidden,
                                 focus_order=parse_step_order(request.args.get('order') or request.args.get('focus_order')))
            if tab in ('date', 'parts') else None)
    pane = selected_day_pane(days) if days is not None else None
    wide = wide_marks(tab, door, day_view)  # 문 안 전체 페이지 = 같은 한 번을 화면 생산 주문 전체로(탭 숫자 · 새 탭 재료)
    marks = screen_marks(db, tab, pane, rows, flags['pc_view'], today, wide=wide)
    if scene['group'] is not None and marks is not None and tab == 'date':  # "2공장 제작 완료만 남음"(§4-4) — 읽은 표시 줄로, 쿼리 0
        attach_factory_stage(pane.get('make_rows') or [], marks, scene['group'])
    screen = _part_screen(db, user, tab, mode, surface, {'panes': [pane] if pane is not None else [], 'all_rows': rows},
                          marks=marks, today=today, full=not day_view, door=door)
    _t0 = time.perf_counter()
    if day_view:
        pane_tpl = 'production/partials/home_pc_day_pane.html' if flags['pc_view'] else 'production/partials/home_day_pane.html'
        response = make_response(render_template(pane_tpl, tab=tab, d=pane, **screen, **flags))
        response.headers[DAY_PANE_HEADER] = pane['key']
        response.headers['Cache-Control'] = 'no-store'
        apply_ept_b7_render_headers(response, route_id='erp_production_home_day',
                                    render_ms=(time.perf_counter() - _t0) * 1000)
        return response
    # 네 탭은 같은 행 집합에서 파생 — 쿼리는 묘비(취소 주문) 하나만 더한다. 묘비는 모든 탭에서 세어
    # "바뀐 것" 탭 숫자 = 받은함 장 수가 되게 한다(R2, 11-10).
    tombstones = collect_production_tombstones(db, user, production_home_mine_only(user), partner_org)
    # 바뀐 것 탭의 '누가 · 언제' · 확인한 것 · 더 보기(11-21)와 찾기 탭 바뀐 줄의 '누가 · 언제'는 사람 이름 읽기 1회를 더한다
    # (그 두 탭만, 읽을 사람이 없으면 0회). 날짜 · 내 공정 탭 쿼리는 그대로다.
    changes = (production_home_changes_view(db, user, rows, tombstones,
                                            show_all_done=request.args.get('done') == DONE_ALL_VALUE)
               if tab == 'changes' else None)
    if flags['pc_view']:
        attach_pc_inbox(changes, rows)
    if tab == 'all':
        production_home_attach_change_by(db, rows)
    queues = production_home_step_queues(rows, today) if tab == 'steps' else None
    _attach_step_confirm(db, queues, flags, user)  # '내 공정' [끝] 확인 창 자료(도면 있는 줄만 묻는다, 2026-11-25)
    # 셸 조각(레일 · 아래 메뉴에서 온 view=fragment): 몸통 + 이 화면 CSS · 스크립트(다른 탭 조각과 같은 꼴, 11-14).
    template_name = ('production/partials/home_fragment.html' if wants_erp_shell_tab_body(request)
                     else 'production/home.html')
    response = make_response(render_template(
        template_name,
        tab=tab,
        rows=rows,
        total=stats['total'],
        groups=production_home_groups(rows, today, past_hidden=past_hidden) if tab == 'all' else [],
        days=days,
        pane=pane,
        **screen,
        counts={**production_home_counts(rows, len(tombstones)), **flow_counts(user, rows, marks, door, wide)},
        changes=changes,
        queues=queues,
        **_step_panel_screen(tab, surface, queues),
        **flags,
        today_label=f"{today.month}월 {today.day}일 ({'월화수목금토일'[today.weekday()]})",
        factory_now=scene['label'],
        factory_scene=scene['on'],  # 공장 칩 CSS 를 실을지(home_styles.html)
    ))
    apply_ept_b7_render_headers(response, route_id='erp_production_home', render_ms=(time.perf_counter() - _t0) * 1000)
    apply_erp_shell_fragment_headers(response, request, etag_ignore=_ETAG_VOLATILE)
    return response


@erp_production_page_bp.route('/production/sheet/<int:order_id>')
@login_required
def erp_production_sheet_page(order_id: int):
    """전체 화면 작업 시트(설계서 §12.2, 안 2) — 도면 6할 + 고객·만들 것·공정·불량·단추.

    뷰 모델(``build_production_sheet_view``)에 전체 화면 키를 더한다(``full=True``).
    단추는 ``data-tablet-sheet-action`` 계약(tablet-domain-sheets.js, 이 페이지는 기기 무관).
    """
    db = get_db()
    user = _require_home_user()
    order = _home_order_or_404(db, order_id, user)
    sheet = build_production_sheet_view(db, order, user, full=True, notes=True)  # 도면 장마다 펜 기록(켬만 +1)
    flags = production_screen_flags(user, request)
    # PC 머리 시공일 = 첫 화면 ① 칸과 같은 글(M/D (요일) · D-n · 외 n · 상차/희망일 표, 설계서 §6-3 규칙 1 · 사장님 2026-11-25
    # "출고 일정 = 제작 일정" — 같은 출고 칸 ship_fields). 태블릿 · 폰은 지금 글 그대로.
    today = get_today_kst()
    due = (pc_due({'construction_date': order.erp_construction_date, 'structured_data': order.structured_data or {},
                   **ship_fields(order, today)}, today) if flags['pc_view'] else None)
    return render_template(
        'production/sheet.html',
        order=sheet,
        is_admin=bool(user and user.role == 'ADMIN'),
        defect_reasons=_PRODUCTION_DEFECT_REASONS,
        pc_sheet_due=due,
        sheet_dw_link=_sheet_drawing_link(user) if sheet.get('step_lines') else None,
        **flags,
    )


@erp_production_page_bp.route('/production/print/<int:order_id>')
@login_required
def erp_production_print_sheet(order_id: int):
    """작업지시서 인쇄(F8, D8): 단독 HTML — 머리(주문·고객·연락처·주소·발주사·일정·시공팀), 규격 표(취소 품목 제외),
    특이사항, 공정 빈 칸 4, 최종 도면 장마다 1쪽. 새 탭에서 열어 [인쇄]. 금액 없음(D7). 전례 ``erp_order_label``.
    """
    db = get_db()
    user = _require_home_user()
    order = _home_order_or_404(db, order_id, user)
    sheet = build_production_sheet_view(db, order, user, full=True)
    now_kst = datetime.datetime.now(_KST)
    return render_template(
        'production/print_sheet.html',
        order=sheet,
        printed_at=f"{now_kst.month}/{now_kst.day} {now_kst.hour:02d}:{now_kst.minute:02d}",
        printed_by=(getattr(user, 'name', None) or getattr(user, 'username', '') or ''),
    )
