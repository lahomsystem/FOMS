"""생산팀 첫 화면 — 전체 주문 한 줄(설계서 §12, 2026-11-09 D10·D12).

``dashboard.py`` 와 같은 Blueprint(``erp_production_page``)에 라우트만 더한다(파일 500줄 래칫).
``foms/web/production/__init__.py`` 가 이 모듈을 import 해야 라우트가 붙는다.
"""

from __future__ import annotations

import datetime

import time

from flask import abort, g, make_response, render_template, request

from db import get_db
from models import Order
from foms.api.production.orders import _PRODUCTION_DEFECT_REASONS
from foms.services.common.ept_b7_profile import apply_ept_b7_render_headers
from foms.services.common.erp_shell_http import apply_erp_shell_fragment_headers, wants_erp_shell_tab_body
from foms.services.datetime_kst import get_today_kst
from foms.services.feature_flags import (
    is_mobile_v2_shell,
    resolve_shell_variant_cached,
    wants_coarse_pointer_surfaces,
)
from foms.services.production.home_access import can_view_production_home
from foms.services.production.part_access import VIEW_ADMIN, VIEW_PART, VIEW_READONLY, part_view_mode
from foms.services.production.part_board import build_part_board, part_sync_cursor
from foms.services.production.part_constants import PART_CUT
from foms.services.production_change_alerts import collect_production_tombstones
from foms.services.production_sheet_view import build_production_sheet_view
from foms.services.production_home_days import production_home_days
from foms.services.production_home_read_model import (
    build_production_home,
    production_home_counts,
    production_home_groups,
    production_home_inbox,
    production_home_step_queues,
)

_HOME_TABS = ('date', 'steps', 'changes', 'all', 'parts')
#: 날짜 한 장 조각(``?view=day&day=``) — 날을 누르면 JS 가 그 장만 받아 끼운다(설계서 §15.6 '날 고르기', 11-14).
#: 셸 조각(``view=fragment`` + 셸 머리글, 탭 몸통 전체)과 다른 값이라 둘이 섞이지 않는다.
DAY_VIEW = 'day'
#: 날짜 한 장 조각 응답 머리글 — 받은 장의 열쇠(JS 가 고른 날과 같은지 본다).
DAY_PANE_HEADER = 'X-FOMS-HOME-DAY'
from foms.web.auth import login_required
from foms.web.production.dashboard import erp_production_page_bp

_KST = datetime.timezone(datetime.timedelta(hours=9))


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
    """파트 화면 템플릿 값 — 판(없으면 None) · '도면 카드' 탭 · '내 공정' 숨김 · 위 줄 제목 · JS 설정.

    판은 파트 계정의 날짜 탭(태블릿) 또는 관리자 · 읽기 전용의 '도면 카드' 탭에서만 만든다(표시 줄 읽기 쿼리 +1).
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
        'parts_tab': surface and mode in (VIEW_ADMIN, VIEW_READONLY),
        'hide_steps_tab': mode == VIEW_PART,
        'part_title': (board['part_label'], name) if board is not None and mode == VIEW_PART else None,
    }


def selected_day_pane(days: dict) -> dict:
    """고른 날(주소 ``day=`` 또는 자동으로 고른 날)의 장 하나. ``production_home_days`` 의 ``selected`` 는 늘 장 열쇠다."""
    return next((p for p in days['panes'] if p['key'] == days['selected']), days['panes'][0])


def _require_home_user():
    """생산 홈·전체 화면 시트를 볼 수 있는 사람(관리자·CS·영업·생산, 협력사 제외). 아니면 403."""
    user = getattr(g, 'current_user', None)
    # 규칙은 한 곳(home_access) — 태블릿 레일의 생산 단추 주소도 같은 답을 쓴다(D19).
    if not can_view_production_home(user):
        abort(403)
    return user


@erp_production_page_bp.route('/production/home')
@login_required
def erp_production_home():
    """생산팀 첫 화면 — 탭 날짜(2주 띠 + 그날, D18 11-10) · 내 공정 · 바뀐 것 · 전체 주문(찾기). 설계서 §12 · D10·D12.

    볼 수 있는 사람 = 공정 체크를 할 수 있는 사람과 같다(관리자·CS·영업·생산, ``_PRODUCTION_STEPS_EDIT_TEAMS``
    와 같은 답). 협력사 계정은 없다. 금액은 뷰 모델에 싣지 않는다(D7).

    생산 파트(설계서 §15.6, P15-5): 파트 계정 + 태블릿이면 날짜 탭의 장에 도면 카드 판을 더 그리고(지금 장은
    태블릿 가로에서만 숨김), 관리자 · 읽기 전용 직원은 태블릿에서 '도면 카드' 탭(``?tab=parts&part=``)으로 본다.
    파트 계정은 '내 공정' 탭이 없다(D50, 기기 무관).

    날짜 · 도면 카드 탭은 고른 날 장 하나만 그린다(11-14, 예전 D5 는 15장을 다 보냈다). 띠 숫자는 모든 날을 센다.
    응답은 셋 — 전체 페이지 · 셸 조각(``view=fragment`` + 셸 머리글, 레일 · 아래 메뉴) · 날짜 한 장 조각
    (``view=day&day=``, 날을 누를 때 JS 가 받는다, 머리글 :data:`DAY_PANE_HEADER`). 셋 다 같은 자료 경로다.
    """
    db = get_db()
    user = _require_home_user()
    mode = part_view_mode(user)
    surface = _tablet_part_surface(user)
    tab = _resolve_home_tab(request.args.get('tab') or 'date', mode, surface)
    day_view = request.args.get('view') == DAY_VIEW and tab in ('date', 'parts')
    rows, stats = build_production_home(db, user)
    today = get_today_kst()
    now_kst = datetime.datetime.now(_KST)
    past_hidden = stats['past_hidden']
    # 띠 숫자는 모든 날을 같은 행에서 센다(쿼리 없음). 그리는 장은 고른 날 하나뿐 — 나머지 날은 누를 때 조각으로(11-14).
    days = (production_home_days(rows, today, request.args.get('day'), past_hidden=past_hidden)
            if tab in ('date', 'parts') else None)
    pane = selected_day_pane(days) if days is not None else None
    screen = _part_screen(db, user, tab, mode, surface, {'panes': [pane]} if pane is not None else None)
    _t0 = time.perf_counter()
    if day_view:
        response = make_response(render_template('production/partials/home_day_pane.html', tab=tab, d=pane, **screen))
        response.headers[DAY_PANE_HEADER] = pane['key']
        response.headers['Cache-Control'] = 'no-store'
        apply_ept_b7_render_headers(response, route_id='erp_production_home_day',
                                    render_ms=(time.perf_counter() - _t0) * 1000)
        return response
    # 네 탭은 같은 행 집합에서 파생 — 쿼리는 묘비(취소 주문) 하나만 더한다. 묘비는 모든 탭에서 세어
    # "바뀐 것" 탭 숫자 = 받은함 장 수가 되게 한다(R2, 11-10).
    tombstones = collect_production_tombstones(db, user, False)
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
        inbox=production_home_inbox(rows, tombstones) if tab == 'changes' else [],
        queues=production_home_step_queues(rows) if tab == 'steps' else None,
        today_label=f"{today.month}월 {today.day}일 ({'월화수목금토일'[today.weekday()]})",
        loaded_at_hm=now_kst.strftime('%H:%M'),
        loaded_at_iso=now_kst.isoformat(timespec='seconds'),
    ))
    apply_ept_b7_render_headers(response, route_id='erp_production_home', render_ms=(time.perf_counter() - _t0) * 1000)
    apply_erp_shell_fragment_headers(response, request)
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
    return render_template(
        'production/sheet.html',
        order=sheet,
        is_admin=bool(user and user.role == 'ADMIN'),
        defect_reasons=_PRODUCTION_DEFECT_REASONS,
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
