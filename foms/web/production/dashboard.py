"""
ERP 생산 대시보드 페이지 (ERP-SLIM-9) — canonical page owner.

erp.py에서 분리: /erp/production/dashboard
"""
from __future__ import annotations

import datetime
import time
from typing import Any

from flask import Blueprint, abort, make_response, render_template, request, g

from db import get_db
from models import Order
from foms.web.auth import login_required

from foms.services.datetime_kst import get_today_kst
from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.erp_template_filters import (
    eval_spec_width_mm,
    item_spec_w300_value,
)

from foms.services.production_dashboard_filters import parse_production_dashboard_filters
from foms.services.production_read_model import (
    build_production_orders_query,
    production_stage_bucket_expr,
    compute_production_summary_blob,
    fetch_production_attachment_counts,
    paginate_production_rows,
    PRODUCTION_DASHBOARD_PAGE_SIZE,
)
from foms.services.production_dashboard_display import (
    build_production_enriched_rows,
    build_production_process_steps,
)
from foms.services.common.dashboard_cache import (
    KEY_VERSION,
    TTL_ATTACHMENT_COUNT_MAP,
    TTL_SUMMARY_COUNTS,
    build_dashboard_cache_key,
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
from foms.services.erp_permissions import (
    can_edit_erp,
    is_order_related_to_user,
)
from foms.services.erp_policy import STAGE_LABELS
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


TEAM_LABELS = {
    'CS': '라홈팀',
    'SALES': '영업팀',
    'MEASURE': '실측팀',
    'DRAWING': '도면팀',
    'PRODUCTION': '생산팀',
    'CONSTRUCTION': '시공팀',
}


@erp_production_page_bp.route('/production/dashboard')
@login_required
def erp_production_dashboard():
    """생산 대시보드"""
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

    _summary_fp = {
        "v": KEY_VERSION,
        "uid": user.id if user else None,
        "role": getattr(user, "role", None) if user else None,
        "mine": bool(erp_mine_only),
        "stage": f_stage or "",
        "q": f_q or "",
    }
    _summary_key = build_dashboard_cache_key("production", "summary_counts", _summary_fp)
    _summary_blob = get_or_compute_dashboard_slice(
        _summary_key,
        TTL_SUMMARY_COUNTS,
        lambda: compute_production_summary_blob(_q),
        page="production",
        slice_name="summary_counts",
    )
    step_stats = _summary_blob["step_stats"]
    kpis = _summary_blob["kpis"]
    total_orders = int(_summary_blob["total_orders"])
    # 시공일 빠른 순 정렬(YYYY-MM-DD String(10) 사전순=시간순, index 있음). 미정(NULL)은
    # 뒤로, 동률/미정은 created_at 최신 순. PC 리스트에도 동일 적용(의도됨).
    _q = _q.order_by(
        Order.erp_construction_date.asc().nulls_last(),
        Order.created_at.desc(),
    )

    page, total_pages, page_rows = paginate_production_rows(
        _q, _pf.page, total_orders
    )

    # 검색 카드 딥링크(?focus_order=)는 단계 버킷·페이지네이션과 무관하게 착지해야 한다.
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

    _att_fp = {
        "v": KEY_VERSION,
        "uid": user.id if user else None,
        "mine": bool(erp_mine_only),
        "stage": f_stage or "",
        "q": f_q or "",
        "page": page,
        "ids": sorted(o.id for o in page_rows),
    }
    _att_key = build_dashboard_cache_key("production", "attachment_counts", _att_fp)

    def _compute_att() -> dict[str, int]:
        raw = fetch_production_attachment_counts(db, page_rows)
        return {str(k): int(v) for k, v in raw.items()}

    _att_blob = get_or_compute_dashboard_slice(
        _att_key,
        TTL_ATTACHMENT_COUNT_MAP,
        _compute_att,
        page="production",
        slice_name="attachment_counts",
    )
    att_counts = {int(k): int(v) for k, v in (_att_blob or {}).items()}
    enriched = build_production_enriched_rows(page_rows, att_counts)
    # 모바일 v2 큐 카드 썸네일: 페이지 주문 첨부 미리보기 URL 일괄 해소
    from foms.services.erp_mobile_order_display import batch_resolve_queue_attachment_preview_items
    _queue_preview_items = batch_resolve_queue_attachment_preview_items(
        db, [r["id"] for r in enriched]
    )
    # 변경 감지(시공일 변경·도면 재전달/수정요청): 배치 1쿼리(N+1 금지). 지방 뱃지는 이미
    # 로드된 page_rows 의 flat 컬럼에서 파생.
    _orders_by_id = {o.id: o for o in page_rows}
    _alerts_by_id = collect_production_change_alerts(db, page_rows, user.id if user else None)
    for _r in enriched:
        items = _queue_preview_items.get(_r["id"], [])
        _r["attachment_preview_items"] = items
        _r["attachment_previews"] = [item["view"] for item in items if item.get("view")]
        # 태블릿 칸반 카드 총 자수(W/300): 사이드 시트와 동일 SSOT(_prod_sheet_total_units)를
        # 재사용 — 신규 쿼리 없이 이미 로드된 structured_data.items 에서만 파생(카드 표시용).
        _card_sd = _r.get("structured_data") or {}
        _card_items = _card_sd.get("items")
        _r["units_display"] = _prod_sheet_total_units(
            _card_items if isinstance(_card_items, list) else []
        )
        _r["is_regional"] = bool(getattr(_orders_by_id.get(_r["id"]), "is_regional", False))
        _r["change_alerts"] = _alerts_by_id.get(_r["id"], [])
        _r["has_changes"] = bool(_r["change_alerts"])
    # 취소 묘비(최근 14일, 생산 파이프라인, 미확인)와 변경 카운트(변경 행 수 + 묘비 수).
    tombstones = collect_production_tombstones(db, user, erp_mine_only)
    changed_count = sum(1 for _r in enriched if _r.get("has_changes")) + len(tombstones)
    process_steps = build_production_process_steps(step_stats)
    # 태블릿 칸반 상단 KPI 4종: 칸반이 소비하는 동일 `enriched` 행에서만 파생(신규 쿼리 없음).
    tablet_prod_kpis = _compute_tablet_prod_kpis(enriched)
    # detail_payload eager 조립 제거: 템플릿 preload가 lazy fetch(/api/orders/<id>/
    # detail-payload)로 전환되어 이 서버측 계산은 미사용이었다(매 요청 N행 낭비).

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
            kpis=kpis,
            process_steps=process_steps,
            step_stats=step_stats,
            filters={'stage': f_stage, 'q': f_q},
            team_labels=TEAM_LABELS,
            stage_labels=STAGE_LABELS,
            is_admin=is_admin,
            can_edit_erp=can_edit_erp(user),
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
    return response


def _compute_tablet_prod_kpis(orders: list[dict[str, Any]]) -> dict[str, Any]:
    """태블릿 생산 칸반 상단 KPI 4종을 현재 페이지 ``orders``에서 파생한다.

    신규 DB 쿼리 없이 이미 enriched 된 행 dict만 소비한다(칸반이 렌더하는 동일 목록).
    이번 주(월~일, KST)는 시공(상차)일이 이번 주에 드는 주문의 항목 W/300 합.
    주 구간 판정은 이미 계산된 ``construction_dday``(=시공일−오늘)의 오프셋 범위로 한다.

    Args:
        orders: ``build_production_enriched_rows`` 결과 행 dict 리스트.

    Returns:
        {today_line, today_load, delayed, week_units}. week_units는 소수 1자리 문자열.
    """
    today = get_today_kst()
    week_start = -today.weekday()      # 이번 주 월요일까지의 dday 오프셋
    week_end = 6 - today.weekday()     # 이번 주 일요일까지의 dday 오프셋
    today_line = today_load = delayed = 0
    week_total = 0.0
    for row in orders:
        if row.get('stage') == '제작중':
            today_line += 1
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
    """도면 전달본 썸네일: resolve_final_drawing_files(전달 SSOT)의 첫 이미지.

    전달 이력을 정본으로 재구성한 최종 도면 파일(view_url/download_url same-origin)을
    쓴다. 이미지 파일을 우선 정렬해 <img> 렌더가 가능한 항목을 앞세운다.
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
    }
    _sheet_alerts = collect_production_change_alerts(db, [order], user.id if user else None).get(order.id, [])
    sheet['change_alerts'] = _sheet_alerts
    sheet['has_changes'] = bool(_sheet_alerts)
    return render_template('production/partials/tablet_sheet.html', order=sheet)
