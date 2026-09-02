"""ERP history dashboard (canonical; SFC-B11B)."""

import time
from copy import deepcopy
from typing import Any

from flask import Blueprint, abort, make_response, redirect, render_template, request, g, url_for
from db import get_db
from models import Order
from foms.web.auth import login_required
from foms.services.orders.status_constants import STATUS
from foms.services.erp_order_flags import is_erp_order_record
from sqlalchemy import or_, cast, String

from foms.services.common.dashboard_cache import (
    KEY_VERSION,
    TTL_PANEL_ROWS,
    build_dashboard_cache_key,
    get_or_compute_dashboard_slice,
)
from foms.services.common.ept_b7_profile import apply_ept_b7_render_headers
from foms.services.common.erp_mine_filter import erp_mine_only_for_construction
from foms.services.common.erp_shell_http import apply_erp_shell_fragment_headers, wants_erp_shell_tab_body
from foms.services.common.fragment_revalidation import (
    RELEASE_ID,
    SHADOW_HEADER,
    SHADOW_RELEASE_HEADER,
    build_fragment_version_key,
    is_shadow_revalidation_enabled,
    record_shadow_observation,
)
from foms.services.erp_permissions import (
    build_mine_sql_filter,
    can_edit_erp,
    is_order_related_to_user,
)
from foms.services.history_read_model import (
    HISTORY_DASHBOARD_PAGE_SIZE,
    compute_history_page_blob,
    fetch_history_orders_by_ids,
)
from foms.services.request_utils import get_search_query_arg

erp_history_bp = Blueprint('erp_history', __name__, url_prefix='/erp/history')

_QUEUE_BLANK = ("", "-", None)

# --- HB-S2a 그림자 재검증 (동작 변경 0) ------------------------------------------
# 이 라우트가 실제로 읽는 요청 인자 전량. 미등재 인자가 오면 키 생성을 포기한다
# (새 필터가 키에 반영 안 되면 필터를 바꿔도 같은 키가 나와 낡은 본문이 재사용된다).
_HISTORY_ROUTE_ID = "erp_history_dashboard"
_HISTORY_KEY_ARGS = (
    "q", "search", "stage", "date_from", "date_to",
    "from_dashboard", "from_search", "page", "mine",
)
# 본문이 좌우되는 테이블. orders(목록) · order_attachments(build_product_items_for_orders)
# · order_schedule_dates(큐 카드 일정) · users(담당자 표시·mine 판정).
# 과다 포함의 대가는 재렌더 한 번, 과소 포함의 대가는 조용히 낡은 화면이다.
_HISTORY_KEY_TABLES = (
    "orders", "order_attachments", "order_schedule_dates", "users",
)


def _fill_queue_row_column_fallbacks(row: dict[str, Any], order: Order) -> dict[str, Any]:
    """Fill queue-card blanks from Order columns when structured_data has no parties/site.

    History search includes legacy rows whose name/phone/address live on columns only.
    Mobile queue rows otherwise read structured_data and would render '-'.

    Args:
        row: Dict from ``build_mobile_queue_order_row``.
        order: ORM (or display) order used to fill blanks.

    Returns:
        The same ``row`` dict, mutated in place.
    """
    if row.get("customer_name") in _QUEUE_BLANK and getattr(order, "customer_name", None):
        row["customer_name"] = order.customer_name
    if row.get("phone") in _QUEUE_BLANK and getattr(order, "phone", None):
        row["phone"] = order.phone
    if row.get("address") in _QUEUE_BLANK and getattr(order, "address", None):
        row["address"] = order.address
    if row.get("manager_name") in _QUEUE_BLANK and getattr(order, "manager_name", None):
        row["manager_name"] = order.manager_name
    return row


def _build_history_queue_rows(db, orders: list[Order], user) -> dict[int, dict[str, Any]]:
    """Build mobile v2 queue-card rows for history search (batch, no N+1).

    Args:
        db: SQLAlchemy session.
        orders: Page of Order rows already fetched for the history list.
        user: Current user (quest assignee / can-approve).

    Returns:
        Mapping of order id → queue-card view-model dict.
    """
    if not orders:
        return {}
    from foms.services.erp_mobile_order_display import (
        build_mobile_queue_batch_context,
        build_mobile_queue_order_row,
    )

    batch_ctx = build_mobile_queue_batch_context(db, orders)
    out: dict[int, dict[str, Any]] = {}
    for order in orders:
        row = build_mobile_queue_order_row(db, order, user, batch_ctx=batch_ctx)
        out[int(order.id)] = _fill_queue_row_column_fallbacks(row, order)
    return out


def _observe_fragment_version(response, user, mine_only: bool) -> None:
    """HB-S2a: 렌더 전 304 용 키가 정말 본문을 결정하는지 관측만 한다.

    응답을 바꾸지 않는다 — 진단 헤더 하나만 붙는다. 플래그가 꺼져 있거나(기본),
    셸 프래그먼트 요청이 아니거나, 키를 못 만들면(미등재 인자·Redis 없음) 아무 일도
    하지 않는다. mismatch 가 나면 그것이 "키에 빠진 축이 있다"는 증거이고,
    S2b(렌더 전 304)는 그 값이 0 이라는 관측 후에만 켠다.

    Args:
        response: 렌더가 끝난 Flask 응답.
        user: 현재 사용자.
        mine_only: 이 요청에 적용된 mine 필터 판정값.
    """
    if not is_shadow_revalidation_enabled() or not wants_erp_shell_tab_body(request):
        return
    key = build_fragment_version_key(
        route_id=_HISTORY_ROUTE_ID,
        req=request,
        user=user,
        tables=_HISTORY_KEY_TABLES,
        allowed_args=_HISTORY_KEY_ARGS,
        mine_only=mine_only,
    )
    if key is None:
        return
    response.headers[SHADOW_HEADER] = record_shadow_observation(
        key, response.get_data(), route_id=_HISTORY_ROUTE_ID
    )
    response.headers[SHADOW_RELEASE_HEADER] = RELEASE_ID


@erp_history_bp.route('/')
@login_required
def history_dashboard():
    """ERP 과거 이력 조회 화면 (Inquiry)"""
    db = get_db()
    user = getattr(g, "current_user", None)
    is_construction_team = bool(user and getattr(user, "team", None) == "CONSTRUCTION")
    
    # 1. 필수 필터 여부 확인 (무차별 Full Scan 방지)
    f_q = get_search_query_arg('q', 'search')
    f_stage = (request.args.get('stage') or '').strip()
    f_date_from = (request.args.get('date_from') or '').strip()
    f_date_to = (request.args.get('date_to') or '').strip()
    from_dashboard = (request.args.get('from_dashboard') or '') == '1'
    from_search = (request.args.get('from_search') or '') == '1'
    mine_only = erp_mine_only_for_construction(request, user)
    
    has_filter = bool(f_q or f_stage or f_date_from or f_date_to)
    auto_browse_mine = mine_only and not has_filter

    # soft-delete 제외한 활성 주문 전체 (레거시 + ERP Order).
    # ERP Order는 DB 컬럼이 초안 플레이스홀더('ERP Order', 000-…)인 채로 두고 실제 값이 structured_data에만
    # 있는 경우가 많음 → 목록 표시 시 apply_erp_display_fields로 동기화(메인 주문 목록과 동일).
    #
    # 스코프 = active_filter (전기간). 이력 화면은 "과거 이력 조회"가 목적이므로 운영 대시보드용
    # dashboard_active_filter(완료 후 60일 경과 주문 제외)를 쓰면 안 된다 — 8ffc9c4a(tail latency
    # 수정)에서 잘못 적용돼 오래 전 완료된 주문이 이력 검색에서만 사라지는 회귀가 있었다
    # (전체 주문 목록 listing.py는 active_filter라 거기선 검색됨). Full Scan은 has_filter 게이트가 막는다.
    _q = db.query(Order).filter(Order.active_filter())

    if mine_only and user:
        mine_conds = build_mine_sql_filter(user)
        if mine_conds:
            _q = _q.filter(or_(*mine_conds))
        else:
            _q = _q.filter(Order.id == -1)
    
    if f_q:
        search_term = f"%{f_q}%"
        _q = _q.filter(
            or_(
                Order.id.cast(String).ilike(search_term),  # perf-ok: bounded id search admin/cold path
                Order.customer_name.ilike(search_term),  # perf-ok: ix_orders_customer_name_trgm
                Order.phone.ilike(search_term),  # perf-ok: ix_orders_phone_trgm
                Order.address.ilike(search_term),  # perf-ok: ix_orders_address_trgm
                Order.manager_name.ilike(search_term),  # perf-ok: ix_orders_manager_name_trgm
                cast(Order.structured_data, String).ilike(search_term)  # perf-ok: ix_orders_structured_data_text_trgm
            )
        )
        
    if f_stage:
        # ERP: erp_stage_code / 레거시: status (값이 MEASURE·MEASURED 등으로 다를 수 있음)
        stage_or = [
            Order.erp_stage_code == f_stage,
            Order.status == f_stage,
        ]
        if f_stage == "MEASURE":
            stage_or.append(Order.status.in_(("MEASURE", "MEASURED", "REGIONAL_MEASURED")))
        _q = _q.filter(or_(*stage_or))
        
    if f_date_from:
        _q = _q.filter(Order.created_at >= f"{f_date_from} 00:00:00")
        
    if f_date_to:
        _q = _q.filter(Order.created_at <= f"{f_date_to} 23:59:59")
        
    page = request.args.get('page', 1, type=int)
    if page < 1:
        page = 1
    per_page = HISTORY_DASHBOARD_PAGE_SIZE

    total_orders = 0
    orders = []
    total_pages = 0

    if has_filter or auto_browse_mine:
        _page_fp = {
            "v": KEY_VERSION,
            "uid": user.id if user else None,
            "role": getattr(user, "role", None) if user else None,
            "team": getattr(user, "team", None) if user else None,
            "mine": bool(mine_only),
            "scope": "active_all",  # 60일 창 제거 — 옛 캐시 blob 무효화 겸 스코프 표식

            "q": f_q or "",
            "stage": f_stage or "",
            "from": f_date_from or "",
            "to": f_date_to or "",
            "page": page,
            "auto_browse": bool(auto_browse_mine),
        }
        _page_key = build_dashboard_cache_key("history", "page_rows", _page_fp)
        _page_blob = get_or_compute_dashboard_slice(
            _page_key,
            TTL_PANEL_ROWS,
            lambda: compute_history_page_blob(_q, page=page, per_page=per_page),
            page="history",
            slice_name="page_rows",
        )
        page = int(_page_blob["page"])
        total_pages = int(_page_blob["total_pages"])
        total_orders = int(_page_blob["total_orders"])
        order_ids = [int(x) for x in (_page_blob.get("order_ids") or [])]
        orders = fetch_history_orders_by_ids(_q, order_ids)
    else:
        total_pages = 0

    if mine_only and user:
        orders = [o for o in orders if is_order_related_to_user(o, user)]
    
    from foms.services.erp_display import _ensure_dict, _erp_get_stage, apply_erp_display_fields
    from foms.services.erp_product_items import build_product_items_for_orders

    enriched = []
    display_orders = []
    for o in orders:
        sd = _ensure_dict(o.structured_data)
        if is_erp_order_record(o):
            stage = _erp_get_stage(o, sd)
        else:
            stage = STATUS.get(o.status, o.status or "-")

        # ERP Order: Order 행 컬럼이 플레이스홀더인 경우 structured_data 기준으로 표시용 복제
        display_o = o
        if is_erp_order_record(o) and o.structured_data:
            display_o = deepcopy(o)
            apply_erp_display_fields(display_o)
        
        display_orders.append(display_o)

        # 완료일 = 시공일(structured schedule.construction.date) — 완료 대시보드
        # (_completion_sheet_context)와 동일 정의. 부재(레거시/미시공)면 None → 템플릿 '-'.
        completed_date = ((sd.get('schedule') or {}).get('construction') or {}).get('date') or None

        enriched.append({
            '_order': o,
            '_sd': sd,
            'stage': stage,
            'display_o': display_o,
            'completed_date': completed_date,
        })
    
    # N+1 방지를 위해 1번의 쿼리로 전체 표시 주문들의 첨부/제품 항목 매핑
    build_product_items_for_orders(db, display_orders)

    queue_rows = _build_history_queue_rows(db, orders, user)
    for item in enriched:
        item['queue_row'] = queue_rows.get(int(item['_order'].id))

    template_name = (
        'orders/partials/history_dashboard_fragment.html'
        if wants_erp_shell_tab_body(request)
        else 'orders/history_dashboard.html'
    )
    _t0 = time.perf_counter()
    response = make_response(
        render_template(
            template_name,
            orders=enriched,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
            total_orders=total_orders,
            has_filter=has_filter or auto_browse_mine,
            from_dashboard=from_dashboard,
            from_search=from_search,
            is_construction_team=is_construction_team,
            can_edit_erp=can_edit_erp(user),
            auto_browse_mine=auto_browse_mine,
            erp_mine_only=mine_only,
        )
    )
    apply_ept_b7_render_headers(
        response,
        route_id="erp_history_dashboard",
        render_ms=(time.perf_counter() - _t0) * 1000,
    )
    _observe_fragment_version(response, user, mine_only)
    apply_erp_shell_fragment_headers(response, request)
    if wants_erp_shell_tab_body(request):
        canonical_args = request.args.to_dict(flat=True)
        canonical_args.pop('view', None)
        response.headers['X-FOMS-Canonical-URL'] = url_for(
            'erp_history.history_dashboard',
            **canonical_args,
        )
    return response


@erp_history_bp.route('/tablet-sheet/<int:order_id>')
@login_required
def history_tablet_sheet(order_id: int):
    """태블릿 가로 이력 사이드 시트용 읽기전용 스냅샷 fragment (단건).

    이력 대시보드는 읽기전용(감사) 화면이므로, 행 탭 시 tablet-side-sheet.js 가 편집
    fragment(/api/foms/fragment/order/<id>/edit) 대신 이 읽기전용 스냅샷을 로드한다
    (본행 data-foms-sheet-url). 시트에는 편집 입력이 없고, 수정은 foot '원 주문 열기'로
    정본 주문 페이지에 점프한다. 신규 쿼리 경로/집계 없음 — 리스트와 동일 표시 파이프라인
    (apply_erp_display_fields + build_product_items_for_orders)을 단건 재사용한다.

    Args:
        order_id: 주문 PK.

    Returns:
        HTML fragment 응답(no-store, X-FOMS-Fragment). 최상위 문서 내비게이션(주소창/새 탭)은
        정본 edit 페이지로 302(비스타일 partial 노출 방지 — dashboard tablet-sheet 전례).
    """
    if request.headers.get("Sec-Fetch-Dest") == "document":
        return redirect(url_for('order_edit.edit_order', order_id=order_id, open='erp-order'))

    db = get_db()
    order = db.query(Order).filter(Order.id == order_id, Order.not_deleted_filter()).first()
    if order is None:
        abort(404)

    from foms.services.erp_display import (
        _ensure_dict,
        _erp_get_stage,
        apply_erp_display_fields,
        erp_deposit_amount_from_structured,
        erp_shipping_price_from_structured,
    )
    from foms.services.erp_product_items import build_product_items_for_orders
    from foms.services.estimate_service import (
        _balance_after_payments,
        _overpaid_after_payments,
    )

    sd = _ensure_dict(order.structured_data)
    if is_erp_order_record(order):
        stage = _erp_get_stage(order, sd)
    else:
        stage = STATUS.get(order.status, order.status or "-")

    # ERP Order: Order 행 컬럼이 플레이스홀더인 경우 structured_data 기준 표시용 복제(리스트 동일).
    display_o = order
    if is_erp_order_record(order) and order.structured_data:
        display_o = deepcopy(order)
        apply_erp_display_fields(display_o)
    build_product_items_for_orders(db, [display_o])

    # 완료일 = 시공일(schedule.construction.date) — 완료 대시보드와 동일 정의.
    completed_date = ((sd.get('schedule') or {}).get('construction') or {}).get('date') or None

    # 정산 요약(읽기전용). 잔금 = max(0, 출고가 − 예약금). 값 부재면 '—'.
    # 클램프 규칙의 정본은 서버 파생식(orders/structured_form_projection.recompute_totals)이고,
    # 그 식과 **같은 값**을 내는 _balance_after_payments 를 쓴다(표면별 새 식 금지).
    shipping_price = erp_shipping_price_from_structured(sd)
    deposit = erp_deposit_amount_from_structured(sd)
    balance = (
        None
        if shipping_price is None
        else _balance_after_payments(shipping_price, deposit or 0)
    )
    # 잔금은 0 에서 잘린다 — 넘친 금액은 그 클램프가 삼킨다. 돌려줄 돈이 있다는 사실이
    # 사라지지 않게 넘친 만큼만 따로 낸다(CEO L-1). 총액 미확정(0)은 과입금이 아니다.
    overpaid = (
        0
        if shipping_price is None
        else _overpaid_after_payments(shipping_price, deposit or 0)
    )

    def _krw(value):
        return "—" if value is None else f"{int(value):,}원"

    response = make_response(render_template(
        'orders/partials/history_tablet_sheet.html',
        o=order,
        d=display_o,
        stage=stage,
        completed_date=completed_date,
        shipping_price_display=_krw(shipping_price),
        deposit_display=_krw(deposit),
        balance_display=_krw(balance),
        overpaid_display=(_krw(overpaid) if overpaid else ""),
        has_settlement=(shipping_price is not None or deposit is not None),
    ))
    apply_erp_shell_fragment_headers(response, request)
    return response
