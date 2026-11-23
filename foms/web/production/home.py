"""생산팀 첫 화면 — 전체 주문 한 줄(설계서 §12, 2026-11-09 D10·D12).

``dashboard.py`` 와 같은 Blueprint(``erp_production_page``)에 라우트만 더한다(파일 500줄 래칫).
``foms/web/production/__init__.py`` 가 이 모듈을 import 해야 라우트가 붙는다.
"""

from __future__ import annotations

import datetime
import re
import time

from flask import abort, g, make_response, render_template, request

from db import get_db
from models import Order
from foms.api.production.orders import _PRODUCTION_DEFECT_REASONS
from foms.services.common.ept_b7_profile import apply_ept_b7_render_headers
from foms.services.common.partner_order_filter import partner_filter_value
from foms.services.common.erp_shell_http import apply_erp_shell_fragment_headers, wants_erp_shell_tab_body
from foms.services.datetime_kst import get_today_kst
from foms.services.feature_flags import (
    is_mobile_v2_shell,
    resolve_shell_variant_cached,
    wants_coarse_pointer_surfaces,
    wants_wide_only_surfaces,
    wants_wide_viewport_surfaces,
)
from foms.services.production.home_access import can_view_production_home
from foms.services.production.home_step_panel import attach_step_panels, parse_step_order, step_panel_for
from foms.services.production.part_access import VIEW_ADMIN, VIEW_PART, VIEW_READONLY, part_view_mode
from foms.services.production.part_board import build_part_board, part_sync_cursor
from foms.services.production.part_constants import PART_CUT
from foms.services.production.pc_view import attach_pc_inbox, attach_pc_rows, pc_due, production_screen_flags
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
    production_home_step_queues,
)

_HOME_TABS = ('date', 'steps', 'changes', 'all', 'parts')
#: 날짜 한 장 조각(``?view=day&day=``) — 날을 누르면 JS 가 그 장만 받아 끼운다(설계서 §15.6 '날 고르기', 11-14).
#: 셸 조각(``view=fragment`` + 셸 머리글, 탭 몸통 전체)과 다른 값이라 둘이 섞이지 않는다.
DAY_VIEW = 'day'
#: 날짜 한 장 조각 응답 머리글 — 받은 장의 열쇠(JS 가 고른 날과 같은지 본다).
DAY_PANE_HEADER = 'X-FOMS-HOME-DAY'
#: '내 공정' 판 하나 조각(``?tab=steps&view=panel&step=&order=``) — 줄을 누르면 JS 가 그 판만 받아 끼운다(2026-11-22,
#: 날짜 한 장과 같은 꼴). 응답 머리글 = 받은 판의 주문 번호(JS 가 누른 줄과 같은지 본다).
PANEL_VIEW = 'panel'
PANEL_HEADER = 'X-FOMS-HOME-PANEL'
from foms.web.auth import login_required
from foms.web.production.dashboard import erp_production_page_bp

_KST = datetime.timezone(datetime.timedelta(hours=9))
#: 셸 조각 ETag 에서 뺄 값 — 파트 판의 첫 받아 오기 기준 시각(그릴 때마다 바뀐다, home_parts_overlays.html).
#: 받은 시각('방금 받음')은 본문에 두지 않는다 — 셸이 받거나 304 로 확인한 때를 #main-content 에 적고 JS 가 읽는다(11-22).
_ETAG_VOLATILE = re.compile(rb' data-pp-since="[^"]*"')


def _tablet_part_surface(user) -> bool:
    """도면 카드 화면의 기기 문(설계서 §15.6 '문') — 모바일 v2 셸 + 터치 기기.

    마우스 기기(``foms_ptr=fine``)는 카드를 아예 그리지 않는다(시공 3분할 선례). 보이기는 태블릿 가로 미디어쿼리(parts.css).
    """
    uid = getattr(user, 'id', None)
    return is_mobile_v2_shell(resolve_shell_variant_cached(uid)) and wants_coarse_pointer_surfaces()


def _resolve_home_tab(raw, mode: str, surface: bool) -> str:
    """주소의 탭 → 그릴 탭. 파트 계정의 '내 공정'(D50)과 문 밖의 '도면 카드'(D55)는 날짜로 돌린다."""
    tab = raw if raw in _HOME_TABS else 'date'
    if tab == 'steps' and mode == VIEW_PART:
        return 'date'
    if tab == 'parts' and not (surface and mode in (VIEW_ADMIN, VIEW_READONLY)):
        return 'date'
    return tab


def _part_screen(db, user, tab: str, mode: str, surface: bool, days) -> dict:
    """파트 화면 템플릿 값 — 판(없으면 None) · [도면 카드로 보기] · '내 공정' 숨김 · 위 줄 제목 · JS 설정.

    판은 파트 계정의 날짜 탭(태블릿) 또는 관리자 · 읽기 전용의 '도면 카드' 화면(?tab=parts)에서만 만든다(표시 줄 읽기 쿼리 +1).
    ``days`` 는 그릴 장만 담은 묶음(``{'panes': [고른 장]}``) — 다른 날 판은 그 날을 누를 때 조각으로 만든다(11-14).
    """
    board = None
    # 30초 받아 오기(P15-7)의 첫 since = 그리는 서버 시각(기기 시계 아님). 표시 줄을 읽기 **전**에 잡는다.
    since = part_sync_cursor()
    if days is not None and surface and ((tab == 'date' and mode == VIEW_PART) or tab == 'parts'):
        board = build_part_board(db, user, days, part=request.args.get('part'))
    name = getattr(user, 'name', None) or getattr(user, 'username', '') or ''
    config = None
    if board is not None:
        config = {
            'mode': board['mode'], 'part': board['part'], 'label': board['part_label'], 'writable': board['writable'],
            'verb': '자름' if board['part'] == PART_CUT else board['part_label'], 'me': name,
            'me_id': getattr(user, 'id', None),
        }
    return {
        'part_board': board,
        'part_config': config,
        'part_since': since if board is not None else None,
        # 날짜 장 제목 옆 [도면 카드로 보기](11-21 사용자 ② — '도면 카드' 탭을 뺀 자리). 문은 예전 탭과 같고(관리자 · 읽기 전용 +
        # 터치 기기), 화면 긴 변이 992 미만인 폰(``foms_scr``)은 가로로 돌려도 카드를 못 보니 뺀다. 주소(?tab=parts)는 그대로 열린다.
        'parts_link': surface and mode in (VIEW_ADMIN, VIEW_READONLY) and wants_wide_only_surfaces(),
        'hide_steps_tab': mode == VIEW_PART,
        'part_title': (board['part_label'], name) if board is not None and mode == VIEW_PART else None,
    }


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


def _step_panel_response(tab: str, surface: bool, rows: list, flags: dict):
    """'내 공정' 판 하나 조각(``view=panel``) — 문 · 권한은 한 화면을 다 그릴 때와 같다(읽기만, 새 쓰기 길 없음).

    문 = 판이 있는 화면(``_step_panel_screen`` 과 같은 '내 공정' 탭 + 터치 v2 + 넓은 창). 파트 계정은 탭이 날짜로 돌아가(D50)
    여기 못 온다. 쓰기 단추는 같은 ``flags['can_act']``. 판 자료는 같은 행 · 같은 공정 줄에서(``step_panel_for``) — 줄이
    그 사이 다른 공정으로 옮겨 갔거나 문 밖이면 404(JS 가 '다시 받기' 글을 보인다).
    """
    door = tab == 'steps' and surface and wants_wide_viewport_surfaces()
    order = parse_step_order(request.args.get('order')) if door else None
    panel = step_panel_for(production_home_step_queues(rows), request.args.get('step') or '', order) if door else None
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


@erp_production_page_bp.route('/production/home')
@login_required
def erp_production_home():
    """생산팀 첫 화면 — 탭 날짜(2주 띠 + 그날, D18 11-10) · 내 공정 · 바뀐 것 · 전체 주문(찾기). 설계서 §12 · D10·D12.

    볼 수 있는 사람 = ``home_access.can_view_production_home``(관리자 · CS · 영업 · 생산 · 도면 · 시공 · 출고), 쓰는 사람은
    더 좁다(관리자 · 생산팀, ``write_access.can_write_production``). 협력사 계정은 없다. 금액은 뷰 모델에 싣지 않는다(D7).

    생산 파트(설계서 §15.6, P15-5): 파트 계정 + 태블릿이면 날짜 탭의 장에 도면 카드 판을 더 그리고(지금 장은
    태블릿 가로에서만 숨김), 관리자 · 읽기 전용 직원은 태블릿에서 날짜 장 제목 옆 [도면 카드로 보기](``?tab=parts&part=&day=``, 11-21 위 탭에서 뺐다)로 본다.
    파트 계정은 '내 공정' 탭이 없다(D50, 기기 무관).

    날짜 · 도면 카드 탭은 고른 날 장 하나만 그린다(11-14, 예전 D5 는 15장을 다 보냈다). 띠 숫자는 모든 날을 센다.
    응답은 셋 — 전체 페이지 · 셸 조각(``view=fragment`` + 셸 머리글, 레일 · 아래 메뉴) · 날짜 한 장 조각
    (``view=day&day=``, 날을 누를 때 JS 가 받는다, 머리글 :data:`DAY_PANE_HEADER`). 셋 다 같은 자료 경로다.
    '내 공정' 판 하나 조각(``view=panel&step=&order=``, 줄을 누를 때, 머리글 :data:`PANEL_HEADER`)도 같은 행에서 만든다.
    """
    db = get_db()
    user = _require_home_user()
    mode = part_view_mode(user)
    surface = _tablet_part_surface(user)
    tab = _resolve_home_tab(request.args.get('tab') or 'date', mode, surface)
    day_view = request.args.get('view') == DAY_VIEW and tab in ('date', 'parts')
    # 기기 · 권한 판정 한 곳(PC 보기 전용 · [고치기] · 쓰기 단추, 설계서 2026-11-21-production-pc-viewer §4 · §5 · §7)
    flags = production_screen_flags(user, request)
    # 협력사 거르기(헤더 메뉴 · 쿠키)를 보드와 같이 먹는다(설계서 2026-11-21-production-pc-viewer §9-11).
    partner_org = partner_filter_value(request)
    rows, stats = build_production_home(db, user, partner_org=partner_org)
    today = get_today_kst()
    if flags['pc_view']:
        attach_pc_rows(rows, today)  # PC 줄 값(시공일 칸 · 누가 · 언제 · 늦음) — 이미 읽은 행에서, 쿼리 0
    if request.args.get('view') == PANEL_VIEW:
        return _step_panel_response(tab, surface, rows, flags)  # '내 공정' 판 하나(누른 줄) — 행 읽기 뒤 쿼리 0
    past_hidden = stats['past_hidden']
    # 띠 숫자는 모든 날을 같은 행에서 센다(쿼리 없음). 그리는 장은 고른 날 하나뿐 — 나머지 날은 누를 때 조각으로(11-14).
    # 주소 order= (옛 focus_order=)는 그 주문의 날 장을 고르고 줄에 테두리를 친다(바로가기 · 알림 · 검색, §9-10).
    days = (production_home_days(rows, today, request.args.get('day'), past_hidden=past_hidden,
                                 focus_order=parse_step_order(request.args.get('order') or request.args.get('focus_order')))
            if tab in ('date', 'parts') else None)
    pane = selected_day_pane(days) if days is not None else None
    screen = _part_screen(db, user, tab, mode, surface, {'panes': [pane]} if pane is not None else None)
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
    tombstones = collect_production_tombstones(db, user, False, partner_org)
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
        counts=production_home_counts(rows, len(tombstones)),
        changes=changes,
        queues=queues,
        **_step_panel_screen(tab, surface, queues),
        **flags,
        today_label=f"{today.month}월 {today.day}일 ({'월화수목금토일'[today.weekday()]})",
    ))
    apply_ept_b7_render_headers(response, route_id='erp_production_home', render_ms=(time.perf_counter() - _t0) * 1000)
    apply_erp_shell_fragment_headers(response, request, etag_ignore=_ETAG_VOLATILE)
    return response


@erp_production_page_bp.route('/production/sheet/<int:order_id>')
@login_required
def erp_production_sheet_page(order_id: int):
    """전체 화면 작업 시트(설계서 §12.2, 안 2) — 도면 6할 + 고객·만들 것·공정·불량·단추.

    옆 시트(``erp_production_tablet_sheet``)와 같은 뷰 모델에 전체 화면 키를 더한다(``full=True``).
    단추는 옆 시트와 같은 ``data-tablet-sheet-action`` 계약(tablet-domain-sheets.js, 이 페이지는 기기 무관).
    """
    db = get_db()
    user = _require_home_user()
    order = (
        db.query(Order)
        .filter(Order.id == order_id, Order.active_filter(), Order.is_erp_order.is_(True))
        .first()
    )
    if order is None:
        abort(404)
    sheet = build_production_sheet_view(db, order, user, full=True)
    flags = production_screen_flags(user, request)
    # PC 머리 시공일 = 첫 화면 ① 칸과 같은 글(M/D (요일) · D-n · 외 n, 설계서 §6-3 규칙 1). 태블릿 · 폰은 지금 글 그대로.
    due = (pc_due({'construction_date': order.erp_construction_date, 'structured_data': order.structured_data or {}},
                  get_today_kst()) if flags['pc_view'] else None)
    return render_template(
        'production/sheet.html',
        order=sheet,
        is_admin=bool(user and user.role == 'ADMIN'),
        defect_reasons=_PRODUCTION_DEFECT_REASONS,
        pc_sheet_due=due,
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
    order = (
        db.query(Order)
        .filter(Order.id == order_id, Order.active_filter(), Order.is_erp_order.is_(True))
        .first()
    )
    if order is None:
        abort(404)
    sheet = build_production_sheet_view(db, order, user, full=True)
    now_kst = datetime.datetime.now(_KST)
    return render_template(
        'production/print_sheet.html',
        order=sheet,
        printed_at=f"{now_kst.month}/{now_kst.day} {now_kst.hour:02d}:{now_kst.minute:02d}",
        printed_by=(getattr(user, 'name', None) or getattr(user, 'username', '') or ''),
    )
