"""
ERP 생산 대시보드 페이지 (ERP-SLIM-9) — canonical page owner.

erp.py에서 분리: /erp/production/dashboard
"""
from __future__ import annotations

import datetime
import logging
import time
from typing import Any

from flask import Blueprint, abort, make_response, render_template, request, g

from db import get_db
from models import Order, ProductionRun
from foms.web.auth import login_required

from foms.services.datetime_kst import get_today_kst
from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.erp_template_filters import (
    eval_spec_width_mm,
    item_spec_w300_value,
)

from foms.services.production_dashboard_filters import parse_production_dashboard_filters
from foms.services.production_read_model import (
    apply_production_dashboard_sort,
    build_production_orders_query,
    production_stage_bucket_expr,
    compute_production_summary_blob,
    fetch_production_current_run_ids,
    paginate_production_rows,
    production_attachment_slice_key,
    production_attachment_slice_value,
    production_summary_slice_key,
    PRODUCTION_DASHBOARD_PAGE_SIZE,
    PRODUCTION_KANBAN_MAX_ROWS,
)
from foms.services.common.fragment_prerender import observe_shadow, shadow_requested
from foms.services.production_fragment_version import ROUTE_ID as FRAGVER_ROUTE_ID, compute_production_key
from foms.services.production_dashboard_display import (
    build_production_enriched_rows,
    build_production_process_steps,
    _production_quest_sales_state,
    _production_stage_label_from_stage,
)
from foms.services.common.dashboard_cache import (
    TTL_ATTACHMENT_COUNT_MAP,
    TTL_SUMMARY_COUNTS,
    get_or_compute_dashboard_slice,
)
from foms.services.common.ept_b7_profile import apply_ept_b7_render_headers
from foms.services.production_dashboard_display import (
    build_production_enriched_rows,
    build_production_process_steps,
)
from foms.services.production_change_alerts import (
    collect_production_change_alerts,
    collect_production_tombstones,
)
from foms.services.production_drawing_gate_display import attach_production_drawing_gate
from foms.services.erp_permissions import (
    can_edit_erp,
    is_order_related_to_user,
)
from foms.services.orders.order_mutation_policy import team_has_capability
from foms.services.feature_flags import (
    is_mobile_v2_shell, resolve_shell_variant_cached, wants_coarse_pointer_surfaces,
)
from foms.services.erp_policy import STAGE_LABELS
from foms.services.orders.team_labels import TEAM_LABELS
# namespace surface 계약(pin): 라우트 본문 미사용이어도 erp_display 재export 유지
from foms.services.erp_display import (
    _ensure_dict,
    _erp_get_stage,
    _erp_has_media,
    _erp_alerts,
    _normalize_date_to_yyyymmdd,
)
from foms.services.common.erp_shell_http import apply_erp_shell_fragment_headers, wants_erp_shell_tab_body


erp_production_page_bp = Blueprint(
    'erp_production_page', __name__, url_prefix='/erp'
)

logger = logging.getLogger(__name__)


@erp_production_page_bp.route('/production/dashboard')
@login_required
def erp_production_dashboard():
    """생산 대시보드"""
    _t_view = time.perf_counter()
    db = get_db()
    user = getattr(g, 'current_user', None)
    is_admin = user and user.role == 'ADMIN'

    _pf = parse_production_dashboard_filters(request)
    f_stage = _pf.stage
    f_q = _pf.q
    erp_mine_only = _pf.erp_mine_only

    # 단계 필터/버킷은 build_production_orders_query·production_stage_bucket_expr가
    # flat 컬럼 Order.erp_stage_code(index=True)를 직접 참조한다(JSONB path cast 제거).
    _q = build_production_orders_query(db, user, f_stage, f_q, erp_mine_only)
    # 칸반은 dashboard_body.html 의 `erp_mobile_v2_enabled and coarse_pointer_surfaces` 일 때만
    # 그린다. 안 그리는 요청(마우스 PC·옛 셸, 하트비트 포함)은 전량(최대 300행)을 건너뛰고 페이지
    # 행만 읽는다. 칸반 값(kanban_*·changed_count·tombstones·tablet_prod_kpis)은 그 칸반만 읽는다.
    kanban_wanted = is_mobile_v2_shell(resolve_shell_variant_cached(
        user.id if user else None)) and wants_coarse_pointer_surfaces(request)
    # 렌더 전 304 1단계(그림자): 뒤에서 도는 재검증에서만 키를 렌더 **전**에 만든다. 응답은 그대로이고,
    # 키 단계가 읽은 조각 값은 렌더가 넘겨받는다(다시 읽지 않는다). 켜는 법은 fragment_prerender 참조.
    _shadow = shadow_requested(request, FRAGVER_ROUTE_ID)
    _fv, _fv_abandon = compute_production_key(db, request, user, _pf, kanban_wanted) if _shadow else (None, "")
    _reuse = _fv.reuse if _fv else {}
    _summary_blob = _reuse["summary"] if "summary" in _reuse else get_or_compute_dashboard_slice(
        production_summary_slice_key(user, f_stage, f_q, erp_mine_only),
        TTL_SUMMARY_COUNTS,
        lambda: compute_production_summary_blob(_q),
        page="production",
        slice_name="summary_counts",
    )
    step_stats = _summary_blob["step_stats"]
    kpis = _summary_blob["kpis"]
    total_orders = int(_summary_blob["total_orders"])
    # 시공일 빠른 순(기본) 또는 실측일/시공일 헤더 정렬 — PC 리스트에도 동일 적용(의도됨).
    _q = apply_production_dashboard_sort(_q, _pf.sort, _pf.sort_dir)

    # 태블릿 칸반은 페이지 윈도가 아니라 정렬된 전량(캡 PRODUCTION_KANBAN_MAX_ROWS)을 렌더한다.
    # R1 시공일 정렬 도입 후 시공일 변경으로 rank>page_size 가 된 카드가 page1 윈도에서
    # 사라지는 회귀(스테이징 실증)를 막는다. PC 리스트(orders)는 기존 페이지네이션 유지.
    page = _pf.page or 1
    if page < 1:
        page = 1
    per_page = PRODUCTION_DASHBOARD_PAGE_SIZE
    total_pages = (total_orders + per_page - 1) // per_page
    offset = (page - 1) * per_page

    kanban_rows = _q.limit(PRODUCTION_KANBAN_MAX_ROWS).all() if kanban_wanted else []
    kanban_capped = kanban_wanted and total_orders > PRODUCTION_KANBAN_MAX_ROWS
    if not kanban_wanted:
        _, _, page_rows = paginate_production_rows(_q, _pf.page, total_orders)
    elif kanban_capped:
        # silent 축소 금지 — 캡 발동을 로그로 남긴다.
        logger.warning(
            "[production] 칸반 캡 발동: total=%s > cap=%s — 정렬 상위 %s건만 렌더",
            total_orders, PRODUCTION_KANBAN_MAX_ROWS, PRODUCTION_KANBAN_MAX_ROWS,
        )
        # 캡 밖 페이지도 정확히 착지해야 하므로 page rows 는 별도 조회(기존 방식).
        _, _, page_rows = paginate_production_rows(_q, _pf.page, total_orders)
    else:
        # page rows 는 전량 셋의 슬라이스 — 이중 조회/이중 enrichment 회피.
        page_rows = kanban_rows[offset:offset + per_page]

    # 검색 카드 딥링크(?focus_order=)는 단계 버킷·페이지네이션과 무관하게 착지해야 한다(PC 리스트).
    # orders/construction/measurement 대시보드와 동일한 deep-link SSOT.
    focus_order_id = _pf.focus_order_id
    if focus_order_id and focus_order_id not in {o.id for o in page_rows}:
        focus_order = (
            db.query(Order)
            .filter(Order.id == focus_order_id, Order.active_filter(), Order.is_erp_order.is_(True))
            .first()
        )
        if focus_order is not None and (
            not erp_mine_only
            or is_order_related_to_user(focus_order, user)
        ):
            page_rows = [focus_order] + page_rows

    # 칸반(전량) ∪ page(캡 밖·비생산 focus 포함)을 한 번만 enrich·조회한다(N+1·이중 enrichment 금지).
    _kanban_ids = {o.id for o in kanban_rows}
    _all_rows = kanban_rows + [o for o in page_rows if o.id not in _kanban_ids]

    _att_key = production_attachment_slice_key(user, f_stage, f_q, erp_mine_only, [o.id for o in _all_rows])
    _att_blob = _reuse["att"] if _reuse.get("att_key") == _att_key else get_or_compute_dashboard_slice(
        _att_key,
        TTL_ATTACHMENT_COUNT_MAP,
        lambda: production_attachment_slice_value(db, _all_rows),
        page="production",
        slice_name="attachment_counts",
    )
    att_counts = {int(k): int(v) for k, v in (_att_blob or {}).items()}

    # 버킷 = 단계 + current run: PRODUCTION 행을 제작대기/제작중으로 가르는 run id 집합
    # (쿼리 1회, 캐시하지 않는다 — 제작 시작/취소 직후 보드가 즉시 맞아야 한다).
    _run_ids = fetch_production_current_run_ids(db, _all_rows)
    # 변경 감지·지방 뱃지·자수는 칸반이 소비하는 전량 셋 기준(모달·칩 카운트가 보드와 일치).
    _enriched_all = build_production_enriched_rows(_all_rows, att_counts, _run_ids)
    _orders_by_id = {o.id: o for o in _all_rows}
    _alerts_by_id = collect_production_change_alerts(db, _all_rows, user.id if user else None)
    for _r in _enriched_all:
        # 태블릿 칸반 카드 총 자수(W/300): 사이드 시트와 동일 SSOT(_prod_sheet_total_units) 재사용.
        _card_sd = _r.get("structured_data") or {}
        _card_items = _card_sd.get("items")
        _r["units_display"] = _prod_sheet_total_units(
            _card_items if isinstance(_card_items, list) else []
        )
        _r["is_regional"] = bool(getattr(_orders_by_id.get(_r["id"]), "is_regional", False))
        _rc = _alerts_by_id.get(_r["id"]) or {"alerts": [], "history": []}
        _r["change_alerts"] = _rc["alerts"]        # 미확인(시끄러운 스트립)
        _r["has_changes"] = bool(_rc["alerts"])
        _r["change_history"] = _rc["history"]      # 진입 이후 전체(확인 후에도 남는 상설 이력)
        _r["has_change_history"] = bool(_rc["history"])
    # 도면 수정 중 배지·[제작 시작] 막힘(Q2, 2a-2) — 제작 시작 라우트와 같은 판정 함수.
    attach_production_drawing_gate(db, _enriched_all, _orders_by_id)
    _by_eid = {_r["id"]: _r for _r in _enriched_all}

    kanban_enriched = [_by_eid[o.id] for o in kanban_rows if o.id in _by_eid]
    enriched = [_by_eid[o.id] for o in page_rows if o.id in _by_eid]  # PC 리스트(페이지 윈도)

    # 첨부 preview 배치는 page rows(PC 리스트)에만 — 칸반 카드는 previews 미사용(attachments_count만),
    # 전량(최대 300) preview 해소는 낭비.
    from foms.services.erp_mobile_order_display import batch_resolve_queue_attachment_preview_items
    _queue_preview_items = batch_resolve_queue_attachment_preview_items(
        db, [r["id"] for r in enriched]
    )
    for _r in enriched:
        items = _queue_preview_items.get(_r["id"], [])
        _r["attachment_preview_items"] = items
        _r["attachment_previews"] = [item["view"] for item in items if item.get("view")]

    # 취소 묘비와 변경 카운트는 칸반(보드 전체) 기준 — 모달·칩 카운트가 보드와 일치(칸반 없으면 생략).
    tombstones = collect_production_tombstones(db, user, erp_mine_only) if kanban_wanted else []
    changed_count = sum(1 for _r in kanban_enriched if _r.get("has_changes")) + len(tombstones)
    process_steps = build_production_process_steps(step_stats)
    # 태블릿 칸반 상단 KPI 4종: 칸반이 소비하는 전량 셋 기준(신규 쿼리 없음).
    tablet_prod_kpis = _compute_tablet_prod_kpis(kanban_enriched) if kanban_wanted else {}
    # detail_payload eager 조립 제거: 템플릿 preload가 lazy fetch(/api/orders/<id>/
    # detail-payload)로 전환되어 이 서버측 계산은 미사용이었다(매 요청 N행 낭비).

    # C-D1: 생산 되돌리기 버튼(수정 제작·제작 취소·완료 취소)은 서버 술어와 같은 조건에서만
    # 그린다 — foms/api/production/orders.py 의 _PRODUCTION_STEPS_EDIT_TEAMS 와 같은 답이다.
    can_act_production = bool(user) and (
        user.role == 'ADMIN'
        or team_has_capability(getattr(user, 'team', None), ('CS', 'SALES', 'PRODUCTION'))
    )
    template_name = (
        'production/partials/dashboard_fragment.html'
        if wants_erp_shell_tab_body(request)
        else 'production/dashboard.html'
    )
    _t0 = time.perf_counter()
    response = make_response(
        render_template(
            template_name,
            orders=enriched,
            kanban_orders=kanban_enriched,
            kanban_capped=kanban_capped,
            kpis=kpis,
            process_steps=process_steps,
            step_stats=step_stats,
            filters={'stage': f_stage, 'q': f_q, 'sort': _pf.sort, 'dir': _pf.sort_dir},
            team_labels=TEAM_LABELS,
            stage_labels=STAGE_LABELS,
            is_admin=is_admin,
            can_edit_erp=can_edit_erp(user),
            can_act_production=can_act_production,
            erp_mine_only=erp_mine_only,
            page=page,
            per_page=PRODUCTION_DASHBOARD_PAGE_SIZE,
            total_pages=total_pages,
            total_orders=total_orders,
            tablet_prod_kpis=tablet_prod_kpis,
            tombstones=tombstones,
            changed_count=changed_count,
        )
    )
    apply_ept_b7_render_headers(
        response,
        route_id="erp_production_dashboard",
        render_ms=(time.perf_counter() - _t0) * 1000,
    )
    apply_erp_shell_fragment_headers(response, request)
    if _shadow:
        observe_shadow(
            route_id=FRAGVER_ROUTE_ID, req=request, response=response, user_id=user.id if user else None,
            result=_fv, view_ms=(time.perf_counter() - _t_view) * 1000, abandon=_fv_abandon,
            recheck=lambda: compute_production_key(db, request, user, _pf, kanban_wanted)[0],
        )
    return response


def _compute_tablet_prod_kpis(orders: list[dict[str, Any]]) -> dict[str, Any]:
    """태블릿 생산 칸반 상단 KPI 4종을 현재 페이지 ``orders``에서 파생한다.

    신규 DB 쿼리 없이 이미 enriched 된 행 dict만 소비한다(칸반이 렌더하는 동일 목록).
    이번 주(월~일, KST)는 시공(상차)일이 이번 주에 드는 주문의 항목 W/300 합.
    주 구간 판정은 이미 계산된 ``construction_dday``(=시공일−오늘)의 오프셋 범위로 한다.

    Args:
        orders: ``build_production_enriched_rows`` 결과 행 dict 리스트.

    Returns:
        {today_line, today_load, delayed, hold, week_units}. week_units는 소수 1자리 문자열.
    """
    today = get_today_kst()
    week_start = -today.weekday()      # 이번 주 월요일까지의 dday 오프셋
    week_end = 6 - today.weekday()     # 이번 주 일요일까지의 dday 오프셋
    today_line = today_load = delayed = hold = 0
    week_total = 0.0
    for row in orders:
        if row.get('stage') == '제작중':
            today_line += 1
        if row.get('hold_active'):
            hold += 1
        dday = row.get('construction_dday')
        if dday == 0:
            today_load += 1
        if dday is not None and dday < 0:
            delayed += 1
        if dday is not None and week_start <= dday <= week_end:
            sd = row.get('structured_data') or {}
            items = sd.get('items')
            for item in items if isinstance(items, list) else []:
                week_total += item_spec_w300_value(item)
    return {
        'today_line': today_line,
        'today_load': today_load,
        'delayed': delayed,
        'hold': hold,
        'week_units': f"{week_total:.1f}",
    }


_PROD_SHEET_IMG_EXT = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp')


def _prod_item_total_w_mm(item: dict[str, Any]) -> float:
    """항목의 총 가로 폭(mm). spec_rows 있으면 각 행 W 합, 없으면 spec_width/spec 평가.

    ``item_spec_w300_value``와 동일 규칙(÷300 이전의 원 폭값).
    """
    if not isinstance(item, dict):
        return 0.0
    spec_rows = item.get('spec_rows')
    if spec_rows and isinstance(spec_rows, list):
        total = 0.0
        for row in spec_rows:
            if isinstance(row, dict):
                total += eval_spec_width_mm(row.get('spec_width') or row.get('w') or '')
        return total
    return eval_spec_width_mm(item.get('spec_width') or item.get('spec') or '')


def _prod_sheet_spec_rows_view(items: list[Any]) -> list[dict[str, Any]]:
    """규격 미니테이블 행: {label(품목), w(가로 mm 표시), qty(수량)}."""
    view: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        w_mm = _prod_item_total_w_mm(item)
        view.append({
            'label': item.get('product_name') or item.get('name') or '품목',
            'w': ('%g' % w_mm) if w_mm else '-',
            'qty': item.get('quantity') or item.get('qty') or 1,
        })
    return view


def _prod_sheet_total_units(items: list[Any]) -> str:
    """총 자수(모든 항목 W/300 합)을 소수 1자리 문자열로."""
    total = 0.0
    for item in items:
        total += item_spec_w300_value(item)
    return f"{total:.1f}"


def _prod_sheet_load_md(value: Any) -> str:
    """시공(상차) 예정일 → 'M/D'. 미정/파싱 실패 시 '-'."""
    norm = _normalize_date_to_yyyymmdd(value)
    if not norm:
        return '-'
    try:
        d = datetime.datetime.strptime(norm, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return '-'
    return f"{d.month}/{d.day}"


def _prod_sheet_drawing_thumb(sd: dict[str, Any]) -> dict[str, str] | None:
    """도면 전달본 썸네일: resolve_final_drawing_files(수령 확정과 같은 함수)의 첫 이미지.

    전달 API 가 계산해 둔 현재 도면 목록(``drawing_current_files``, view_url/download_url
    same-origin)을 쓴다 — 수령 확정본과 같은 답이다. 이미지 파일을 우선 정렬해 <img> 렌더가
    가능한 항목을 앞세운다.
    """
    files = resolve_final_drawing_files(sd)
    ordered = sorted(
        files,
        key=lambda f: 0 if (f.get('filename') or '').lower().endswith(_PROD_SHEET_IMG_EXT) else 1,
    )
    for f in ordered:
        view = (f.get('view_url') or '').strip()
        if not view:
            continue
        return {
            'thumb': view,
            'view': view,
            'download': (f.get('download_url') or view).strip(),
            'label': f.get('filename') or '도면 전달본',
        }
    return None


@erp_production_page_bp.route('/production/tablet-sheet/<int:order_id>')
@login_required
def erp_production_tablet_sheet(order_id: int):
    """태블릿 가로 생산 칸반 카드 → 우측 사이드 시트 body fragment(읽기 요약 + 액션).

    공용 tablet-side-sheet.js의 ``data-foms-sheet-url`` 계약으로 로드된다. 단일 주문
    1회 로드만 수행하고 도면 전달본은 structured_data(전달 이력)에서 파생하므로 추가
    쿼리·N+1이 없다. 액션 버튼 배선은 tablet-domain-sheets.js(document 위임) 소관.
    """
    db = get_db()
    order = (
        db.query(Order)
        .filter(Order.id == order_id, Order.active_filter(), Order.is_erp_order.is_(True))
        .first()
    )
    if order is None:
        abort(404)
    user = getattr(g, 'current_user', None)
    sd = _ensure_dict(order.structured_data)
    items = sd.get('items')
    if not isinstance(items, list):
        items = []
    construction_date = (((sd.get('schedule') or {}).get('construction') or {}).get('date'))
    notes_raw = sd.get('notes')
    _prod = sd.get('production') if isinstance(sd.get('production'), dict) else {}
    _hold = _prod.get('hold') if isinstance(_prod.get('hold'), dict) else {}
    _rework = _prod.get('rework') if isinstance(_prod.get('rework'), dict) else {}
    # 전이 버튼 조건 렌더용 stage/승인 상태(read-model 버킷 매핑·row 규약과 동일 헬퍼 재사용).
    # 버킷 = 단계 + current run(단건 조회 1회).
    has_run = (
        db.query(ProductionRun.id)
        .filter(ProductionRun.order_id == order.id, ProductionRun.is_current.is_(True))
        .first()
        is not None
    )
    stage_label = _production_stage_label_from_stage(order.erp_stage_code, has_run) or '기타'
    is_sales_approved = _production_quest_sales_state(sd, stage_label, order.erp_stage_code)[0]
    sheet = {
        'id': order.id,
        'customer_name': (((sd.get('parties') or {}).get('customer') or {}).get('name')) or '-',
        'load_md': _prod_sheet_load_md(construction_date),
        'total_units_display': _prod_sheet_total_units(items),
        'spec_rows_view': _prod_sheet_spec_rows_view(items),
        'notes_text': notes_raw.strip() if isinstance(notes_raw, str) else '',
        'drawing_thumb': _prod_sheet_drawing_thumb(sd),
        'hold_active': bool(_hold.get('active')),
        'hold_reason': (_hold.get('reason') or '').strip() if isinstance(_hold.get('reason'), str) else '',
        'rework_active': bool(_rework.get('active')),
        'rework_reason': (_rework.get('reason') or '').strip() if isinstance(_rework.get('reason'), str) else '',
        'rework_count': int(_rework.get('count') or 0),
        # 완료 이력(E-d): 시트 무채 이력 섹션이 '보류 이력 N건' 을 파생. 해제된 보류 기록 리스트.
        'hold_history': _prod.get('hold_history') if isinstance(_prod.get('hold_history'), list) else [],
        'stage': stage_label,
        'is_sales_approved': bool(is_sales_approved),
    }
    attach_production_drawing_gate(db, [sheet], {order.id: order})
    _sc = collect_production_change_alerts(db, [order], user.id if user else None).get(order.id) or {"alerts": [], "history": []}
    sheet['change_alerts'] = _sc['alerts']
    sheet['has_changes'] = bool(_sc['alerts'])
    sheet['change_history'] = _sc['history']
    sheet['has_change_history'] = bool(_sc['history'])
    return render_template('production/partials/tablet_sheet.html', order=sheet,
                           is_admin=bool(user and user.role == 'ADMIN'))
