"""ERP AS 대시보드 (ERP-SLIM-8; canonical, SFC-B11B). /erp/as."""
import time
from flask import Blueprint, abort, make_response, render_template, request, redirect, url_for, g
from db import get_db
from models import Order
from foms.web.auth import login_required
from sqlalchemy import or_, cast, String, case
import datetime

from foms.services.erp_display import _normalize_for_search
from foms.services.common.erp_mine_filter import erp_mine_only_from_request
from foms.services.erp_permissions import build_mine_sql_filter, can_edit_erp
from foms.services.erp_display import _ensure_dict, apply_erp_display_fields_to_orders, get_today_kst
from foms.services.as_content_safety import sanitize_as_content_html
from foms.services.as_dashboard_display import apply_as_dashboard_row_display_fields
from foms.services.feature_flags import is_mobile_v2_shell, resolve_shell_variant_cached
from foms.services.common.erp_shell_http import (
    apply_erp_shell_fragment_headers,
    wants_erp_shell_tab_body,
)
from foms.services.common.ept_b7_profile import apply_ept_b7_render_headers, phase
from foms.services.common.geocode_config import KAKAO_JS_API_KEY
from foms.services.as_dashboard_filters import parse_as_dashboard_filters
from foms.services.as_dashboard_helpers import (
    _combined_as_content_expr,
    _display_address_expr,
    _display_customer_name_expr,
    _display_manager_name_expr,
    _display_phone_expr,
    _erp_as_completed_condition,
    _sql_compact,
)
from foms.services.as_dashboard_read_model import (
    build_as_tab_count_context,
    build_as_tab_query_conditions,
)
from foms.services.attachment_sort import attachment_sort_key
from foms.services.orders.as_round_chart import build_as_round_chart_view


erp_as_page_bp = Blueprint('erp_as_page', __name__, url_prefix='/erp')


def _as_attachments_by_log_id(db, order_id: int) -> dict:
    """AS 첨부를 as_log 항목 id 로 묶어 돌려준다 (AS-FRESH-01 T4).

    회차 차트가 기록 줄마다 썸네일을 그리려면 항목별 첨부가 필요한데, 항목마다 조회하면
    N+1 이다. 주문 단위 **1쿼리**로 읽어 메모리에서 묶는다(hot path 규칙).
    결합되지 않은 첨부(as_log_id NULL, T1 이전 업로드)는 기존 첨부 모달 소관이라 제외한다.

    Args:
        db: 세션. order_id: 대상 주문 PK.

    Returns:
        ``{as_log_id: [{id, filename, is_image, view_url, thumb_url}, ...]}``.
    """
    from foms.api.files.routes import build_file_view_url
    from models import OrderAttachment

    rows = (
        db.query(OrderAttachment)
        .filter(
            OrderAttachment.order_id == order_id,
            OrderAttachment.category == 'as',
            OrderAttachment.as_log_id.isnot(None),
        )
        .all()
    )
    rows.sort(key=attachment_sort_key)
    grouped: dict = {}
    for att in rows:
        if not att.storage_key:
            continue
        grouped.setdefault(str(att.as_log_id), []).append({
            'id': att.id,
            'filename': att.filename or 'file',
            'is_image': (att.file_type or 'image') == 'image',
            'view_url': build_file_view_url(att.storage_key),
            'thumb_url': build_file_view_url(att.thumbnail_key or att.storage_key),
        })
    return grouped


def _compact_search_text(value):
    """검색 비교용 문자열 정규화 (NFC + 공백 제거 + 소문자)."""
    normalized = _normalize_for_search(value)
    if not normalized:
        return ''
    return ''.join(normalized.split()).lower()


def _is_sales_delivery_search(compact_q):
    """영업/택배 전용 검색어인지 판별."""
    return (compact_q or '').replace('/', '') == '영업택배'


def _order_is_sales_delivery(order):
    """주문이 영업/택배 탭 소속인지 판별."""
    sd = _ensure_dict(getattr(order, 'structured_data', None))
    shipment = sd.get('shipment') or {}
    return shipment.get('sales_delivery') is True


def _erp_order_search_filter(query, q, *, dialect_name='', use_postgres_regex=False):
    """고객명·전화·주소·내용 전체 검색 (공백 무시 + AS 내용 포함)."""
    compact_q = _compact_search_text(q)
    if not compact_q:
        return query
    term = f'%{compact_q}%'
    as_content = _combined_as_content_expr(
        dialect_name=dialect_name,
        use_postgres_regex=use_postgres_regex,
    )
    customer_name = _display_customer_name_expr(dialect_name=dialect_name)
    manager_name = _display_manager_name_expr(dialect_name=dialect_name)
    phone = _display_phone_expr(dialect_name=dialect_name)
    address = _display_address_expr(dialect_name=dialect_name)
    # perf-ok 근거(아래 8개 분기 공통, T12 실측):
    #   이 OR 는 **어떤 trgm 인덱스도 타지 않는다**. `_sql_compact` 가 씌우는
    #   `lower(regexp_replace(..))` 는 표현식 인덱스(`ix_orders_*_trgm`)와 형태가 달라
    #   매칭되지 않고(EXPLAIN: `enable_seqscan=off` 강제에서도 Seq Scan), 분기 하나만
    #   비인덱서블이어도 BitmapOr 자체가 성립하지 않는다. 과거 각 줄에 붙어 있던
    #   `ix_orders_*_trgm` 인용은 사실이 아니어서 제거했다(플랜을 오독하게 만든다).
    #   유지 근거는 인덱스가 아니라 **경로 성격**이다 — 검색어를 입력했을 때만 도는
    #   콜드 경로이고 모집단도 AS 상태 부분집합이다. 인덱스로 접으려면 8개 분기를
    #   합친 정규화 생성 컬럼(+trgm/tsvector)이 필요하며, 그건 별도 perf task 소관이다.
    return query.filter(
        or_(
            _sql_compact(cast(Order.id, String), use_postgres_regex=use_postgres_regex).ilike(term),  # perf-ok
            _sql_compact(customer_name, use_postgres_regex=use_postgres_regex).ilike(term),  # perf-ok
            _sql_compact(manager_name, use_postgres_regex=use_postgres_regex).ilike(term),  # perf-ok
            _sql_compact(phone, use_postgres_regex=use_postgres_regex).ilike(term),  # perf-ok
            _sql_compact(address, use_postgres_regex=use_postgres_regex).ilike(term),  # perf-ok
            _sql_compact(Order.product, use_postgres_regex=use_postgres_regex).ilike(term),  # perf-ok
            _sql_compact(Order.notes, use_postgres_regex=use_postgres_regex).ilike(term),  # perf-ok
            _sql_compact(as_content, use_postgres_regex=use_postgres_regex).ilike(term),  # perf-ok
        )
    )


def _erp_as_tab_for_order(order):
    """주문이 기본적으로 속해야 하는 AS 상태 탭 계산."""
    if order.status == 'AS_COMPLETED' and order.as_completed_date not in (None, ''):
        return 'completed'
    if _order_is_sales_delivery(order):
        return 'sales_delivery'
    return 'incomplete'


@erp_as_page_bp.route('/as/card-detail/<int:order_id>')
@login_required
def erp_as_card_detail(order_id: int):
    """AS 모바일 카드 상세(시공자 + AS 타임라인) lazy 렌더 파셜 (D1c).

    닫힌 <details>가 열릴 때 as-dashboard.js가 fetch하는 경량 endpoint.
    PC 확장 fragment와 동일한 매크로(render_as_timeline·시공자)를 단건 렌더하므로
    quick-add·영업/전달 토글 배선 계약이 두 표면에서 동일하다.

    Args:
        order_id: 대상 주문 PK.

    Returns:
        카드 상세 파셜 HTML(text/html). AS 상태가 아니거나 없으면 404.
    """
    db = get_db()
    order = (
        db.query(Order)
        .filter(Order.active_filter())
        .filter(Order.status.in_(['AS', 'AS_RECEIVED', 'AS_COMPLETED']))
        .filter(Order.id == order_id)
        .first()
    )
    if order is None:
        abort(404)
    # 대시보드와 동일한 표시필드 보강(시공자·AS 내용 HTML·영업택배). 썸네일은 상세에 없어 게이트 off.
    apply_as_dashboard_row_display_fields([order], db, mobile_v2_active=False)
    # T15c: 상세 타임라인 표면은 ver7 회차 차트로 교체 — 단건 lazy 라우트에서만 조립한다
    # (목록 hot path 는 기존 as_timeline_view 셀 요약 그대로).
    order.as_round_chart_view = build_as_round_chart_view(
        order.structured_data,
        attachments_by_log_id=_as_attachments_by_log_id(db, order.id),
    )
    current_user = getattr(g, 'current_user', None)
    return render_template(
        'cs/partials/as_card_detail_partial.html',
        r=order,
        can_edit_erp=can_edit_erp(current_user),
    )


@erp_as_page_bp.route('/as/timeline/<int:order_id>')
@login_required
def erp_as_timeline(order_id: int):
    """AS 확장용 회차 차트 fragment lazy 렌더(모바일 card-detail 패턴 복제).

    ``?readonly=1`` 이면 편집 권한과 무관하게 읽기 전용으로 렌더한다 — 지도 카드
    인라인 확장(T15d)은 열람 표면이라 quick-add·판정·수정 버튼을 내지 않는다
    (쓰기 자체는 API 권한이 소유하므로 이 파라미터는 보안 경계가 아니라 UI 계약).

    Args:
        order_id: 대상 주문 PK.

    Returns:
        회차 차트 파셜 HTML(text/html). AS 상태가 아니거나 없으면 404.
    """
    db = get_db()
    order = (
        db.query(Order)
        .filter(Order.active_filter())
        .filter(Order.status.in_(['AS', 'AS_RECEIVED', 'AS_COMPLETED']))
        .filter(Order.id == order_id)
        .first()
    )
    if order is None:
        abort(404)
    apply_as_dashboard_row_display_fields([order], db, mobile_v2_active=False)
    # T15c: PC 확장 표면 = ver7 회차 차트. 구 '더보기'(?full=1)는 표면과 함께 퇴역 —
    # 차트는 회차별 전량을 내되 회차당 상한(_ROUND_ENTRY_LIMIT)이 fragment 폭증을 막는다.
    order.as_round_chart_view = build_as_round_chart_view(
        order.structured_data,
        attachments_by_log_id=_as_attachments_by_log_id(db, order.id),
    )
    current_user = getattr(g, 'current_user', None)
    readonly = request.args.get('readonly') == '1'
    return render_template(
        'cs/partials/as_timeline_partial.html',
        r=order,
        can_edit_erp=False if readonly else can_edit_erp(current_user),
    )


@erp_as_page_bp.route('/as')
@login_required
def erp_as_dashboard():
    """ERP Order - AS 대시보드 (MVP: AS 상태 주문 리스트)"""
    db = get_db()
    # Batch 5: 상단 request.args 파싱·tab 화이트리스트는 parse_as_dashboard_filters로 분리(동작 보존).
    _af = parse_as_dashboard_filters(request)
    status_filter = _af.status_filter
    search_q = _af.search_q
    selected_date = _af.selected_date
    open_map = _af.open_map
    tab = _af.tab
    billing_filter = _af.billing

    if open_map:
        # AS 전용 지도(dashboard=as): 미완료 전체(날짜 무관) — 현재 버킷만 전달
        from foms.services.as_dashboard_read_model import AS_INCOMPLETE_BUCKET_KEYS
        map_kwargs = {'dashboard': 'as'}
        bucket_val = (request.args.get('bucket') or '').strip()
        if bucket_val in AS_INCOMPLETE_BUCKET_KEYS:
            map_kwargs['bucket'] = bucket_val
        return redirect(url_for('erp_map.map_view', **map_kwargs))

    bind = db.get_bind() if hasattr(db, 'get_bind') else None
    dialect_name = ((bind.dialect.name or '') if bind and bind.dialect else '').lower()
    use_postgres = dialect_name == 'postgresql'
    customer_name_expr = _display_customer_name_expr(dialect_name=dialect_name)

    base_query = db.query(Order).filter(Order.active_filter())
    base_query = base_query.filter(Order.status.in_(['AS', 'AS_RECEIVED', 'AS_COMPLETED']))

    if status_filter:
        base_query = base_query.filter(Order.status == status_filter)

    current_user = getattr(g, 'current_user', None)
    erp_mine_only = erp_mine_only_from_request(request)
    if erp_mine_only and current_user:
        conds = build_mine_sql_filter(current_user)
        if conds:
            base_query = base_query.filter(or_(*conds))
        else:
            base_query = base_query.filter(Order.id == -1)

    compact_q = _compact_search_text(search_q)
    focus_order_id = request.args.get('focus_order', type=int)
    if compact_q and focus_order_id is None and _is_sales_delivery_search(compact_q):
        return redirect(url_for(
            'erp_as_page.erp_as_dashboard',
            tab='sales_delivery',
            status='',
            q='',
            sort_dir=(request.args.get('sort_dir') or 'desc').strip().lower(),
            mine='1' if erp_mine_only else '',
        ))
    if compact_q and focus_order_id is None:
        # 이름 검색 단건은 "정확한 고객명 일치 1건"이면서 "전체 검색 결과도 1건"일 때만 자동 이동
        filtered_preview_rows = _erp_order_search_filter(
            base_query,
            search_q,
            dialect_name=dialect_name,
            use_postgres_regex=use_postgres,
        ).order_by(Order.id.desc()).limit(2).all()
        name_match_rows = base_query.filter(
            _sql_compact(customer_name_expr, use_postgres_regex=use_postgres) == compact_q
        ).order_by(Order.id.desc()).limit(2).all()
        if (
            len(name_match_rows) == 1
            and len(filtered_preview_rows) == 1
            and int(name_match_rows[0].id) == int(filtered_preview_rows[0].id)  # type: ignore[arg-type]
        ):
            only_order = name_match_rows[0]
            target_tab = _erp_as_tab_for_order(only_order)
            return redirect(url_for(
                'erp_as_page.erp_as_dashboard',
                tab=target_tab,
                status=only_order.status or '',
                billing=billing_filter,
                q=search_q,
                sort_dir=(request.args.get('sort_dir') or 'desc').strip().lower(),
                mine='1' if erp_mine_only else '',
                focus_order=only_order.id,
            ))

    if focus_order_id:
        focus_row = base_query.filter(Order.id == focus_order_id).first()
        if focus_row:
            target_tab = _erp_as_tab_for_order(focus_row)
            if tab != target_tab:
                return redirect(url_for(
                    'erp_as_page.erp_as_dashboard',
                    tab=target_tab,
                    status=status_filter,
                    billing=billing_filter,
                    q=search_q,
                    sort_dir=(request.args.get('sort_dir') or 'desc').strip().lower(),
                    mine='1' if erp_mine_only else '',
                    focus_order=focus_order_id,
                ))
        filtered_base_query = base_query.filter(Order.id == focus_order_id)
    elif compact_q:
        filtered_base_query = _erp_order_search_filter(
            base_query,
            search_q,
            dialect_name=dialect_name,
            use_postgres_regex=use_postgres,
        )
    else:
        filtered_base_query = base_query

    as_tab_conditions = build_as_tab_query_conditions(dialect_name=dialect_name)
    as_pending_true = as_tab_conditions["as_pending_true"]
    as_visit_date_present = as_tab_conditions["as_visit_date_present"]
    incomplete_non_sales_condition = as_tab_conditions["incomplete_non_sales_condition"]
    sales_delivery_condition = as_tab_conditions["sales_delivery_condition"]
    paid_unconfirmed_condition = as_tab_conditions["paid_unconfirmed_condition"]
    billing_filters = as_tab_conditions["billing_filters"]

    # 비용 필터(탭 무관)는 카운트 계산 전에 적용한다. status 필터와 같은 위치 계약이라
    # 탭 카운트·버킷 요약·헤더 건수·페이지 수가 목록과 항상 같은 모집단을 본다.
    if billing_filter in billing_filters:
        filtered_base_query = filtered_base_query.filter(billing_filters[billing_filter])

    with phase("tab_counts"):
        as_count_context = build_as_tab_count_context(
            filtered_base_query,
            tab=tab,
            bucket=request.args.get('bucket'),
            incomplete_non_sales_condition=incomplete_non_sales_condition,
            sales_delivery_condition=sales_delivery_condition,
            as_pending_true=as_pending_true,
            as_visit_date_present=as_visit_date_present,
            paid_unconfirmed_condition=paid_unconfirmed_condition,
        )
    incomplete_buckets = as_count_context["incomplete_buckets"]
    as_bucket = as_count_context["as_bucket"]
    as_tab_counts = as_count_context["as_tab_counts"]
    as_incomplete_summary = as_count_context["as_incomplete_summary"]

    # 하단 탭: 완료 안된 건 vs 완료 된 건 vs 전체
    query = filtered_base_query
    if tab == 'completed':
        query = query.filter(_erp_as_completed_condition())
    elif tab == 'sales_delivery':
        query = query.filter(sales_delivery_condition)
    else:
        # 완료 안된 건(X): AS 미완료 중 영업/택배로 분류되지 않은 주문만 표시
        query = query.filter(incomplete_non_sales_condition)
        if as_bucket:
            # stats 칩에서 고른 버킷(방문확정/미결/미정)으로 추가 좁힘
            query = query.filter(incomplete_buckets[as_bucket])

    sort_dir = (request.args.get('sort_dir') or 'desc').strip().lower()
    if sort_dir != 'asc':
        sort_dir = 'desc'
    # 날짜 컬럼 헤더 정렬. 기본은 기존과 같은 AS 접수일이고, 방문일/완료일 헤더를 누르면
    # 그 컬럼으로 갈아탄다. 방문일은 컬럼이 없고 schedule.as_visit.date(JSONB)가 SSOT다
    # (표시 셀 r.as_visit_date와 같은 경로 — 표시값과 정렬 기준이 갈리지 않게).
    sort_key = (request.args.get('sort_key') or 'received').strip().lower()
    if sort_key not in ('received', 'visit', 'completed'):
        sort_key = 'received'
    order_col = {
        'received': Order.as_received_date,
        'completed': Order.as_completed_date,
        'visit': Order.structured_data[('schedule', 'as_visit', 'date')].as_string(),
    }[sort_key]
    total_orders = int(as_tab_counts.get(tab, 0))
    if as_bucket:
        # 버킷 필터 시 헤더 건수·페이지 수도 좁혀진 결과 기준으로
        total_orders = int(as_incomplete_summary.get(as_bucket, 0))
    sort_clauses = []
    if focus_order_id:
        sort_clauses.append(case((Order.id == focus_order_id, 0), else_=1))
    # 날짜 미정은 방향과 무관하게 항상 뒤로 — 방문일/완료일은 빈 값이 흔해서 오름차순에
    # 빈 행부터 깔리면 1페이지가 통째로 무의미해진다(다른 대시보드 정렬과 같은 규약).
    blank_last = case((order_col.is_(None), 1), ((order_col == ''), 1), else_=0)
    sort_clauses.append(blank_last.asc())
    if sort_dir == 'desc':
        sort_clauses.extend([order_col.desc().nullslast(), Order.id.desc()])
    else:
        sort_clauses.extend([order_col.asc().nullslast(), Order.id.desc()])
    query = query.order_by(*sort_clauses)

    # Pagination
    page = request.args.get('page', 1, type=int)
    if page < 1:
        page = 1
    per_page = 100
    total_pages = (total_orders + per_page - 1) // per_page
    if total_pages and page > total_pages:
        page = total_pages

    with phase("list_query"):
        rows = query.offset((page - 1) * per_page).limit(per_page).all()

    mobile_v2_active = is_mobile_v2_shell(
        resolve_shell_variant_cached(current_user.id if current_user else None)
    )
    # Batch 5: rows 표시 필드 보강은 apply_as_dashboard_row_display_fields(display 모듈)로 분리(동작 보존, 캐시 아님).
    # T4: 반환값 = 렌더된 행 중 기준 일정 드리프트(ref_moved/both_moved) 배너 요약
    # (count + 점프 칩 + 초과 건수). 같은 행 루프에서 모으므로 추가 쿼리·재평가 없음.
    with phase("row_display"):
        drift_banner = apply_as_dashboard_row_display_fields(rows, db, mobile_v2_active=mobile_v2_active)
    # 시공자가 아닌 사용자만 AS 카테고리 사진 조회 가능 (관리자 등)
    can_view_as_photos = not (current_user and (current_user.team or '').strip() == 'CONSTRUCTION')

    template_name = (
        'cs/partials/as_dashboard_fragment.html'
        if wants_erp_shell_tab_body(request)
        else 'cs/as_dashboard.html'
    )
    _t0 = time.perf_counter()
    _body = render_template(
        template_name,
        status_filter=status_filter,
        search_q=search_q,
        selected_date=selected_date,
        rows=rows,
        can_edit_erp=can_edit_erp(current_user),
        erp_mine_only=erp_mine_only,
        can_view_as_photos=can_view_as_photos,
        sort_dir=sort_dir,
        sort_key=sort_key,
        as_tab=tab,
        as_tab_counts=as_tab_counts,
        as_incomplete_summary=as_incomplete_summary,
        as_bucket=as_bucket,
        billing_filter=billing_filter,
        compact_search_q=compact_q,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        total_orders=total_orders,
        # 일정찾기 지도 모달(카카오) 전용 — layout_head 의 지도 origin preconnect 게이트도 겸한다.
        kakao_js_key=KAKAO_JS_API_KEY,
        drift_banner=drift_banner,
    )
    _render_ms = (time.perf_counter() - _t0) * 1000.0
    response = make_response(_body)
    apply_erp_shell_fragment_headers(response, request)
    apply_ept_b7_render_headers(response, route_id="erp_as_dashboard", render_ms=_render_ms)
    return response
