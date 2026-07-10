"""ERP 메인 대시보드 (ERP-SLIM-4; canonical, SFC-B11B). /erp/dashboard."""
import datetime
import os
import time
from flask import Blueprint, flash, make_response, redirect, render_template, request, g, url_for
from db import get_db
from models import Order
from foms.web.auth import login_required
from sqlalchemy import text
from foms.services.erp_permissions import can_edit_erp
from foms.services.erp_policy import (
    STAGE_NAME_TO_CODE,
    STAGE_LABELS,
    recommend_owner_team,
)
from foms.services.erp_display import (
    _ensure_dict,
    _erp_get_stage,
    _erp_alerts,
    _erp_has_media,
    get_today_kst,
)
from foms.services.erp_mobile_order_display import (
    batch_resolve_queue_attachment_preview_items,
)
from foms.services.erp_order_deeplink import resolve_edit_return_back_endpoint
from foms.services.orders.status_constants import BULK_ACTION_STATUS
from foms.services.orders.dashboard_filters import parse_orders_dashboard_filters
from foms.services.orders.dashboard_dto import build_orders_row_dtos
from foms.services.orders.dashboard_read_model import (
    build_orders_dashboard_queries,
    compute_orders_summary_slice,
    compute_orders_attachment_assignee_maps,
)
from foms.services.feature_flags import (
    env_bool,
    env_bool_or_mobile_v2,
    is_mobile_v2_shell,
    resolve_shell_variant_cached,
)
from foms.services.foms_split_view import build_split_master_cards, default_split_side_items
from foms.services.orders.dashboard_control_tower import (
    build_mobile_control_tower,
    build_field_ops_for_day,
    build_risk_frame,
    risk_row_cta_meta,
)
from foms.services.common.dashboard_cache import (
    TTL_ATTACHMENT_COUNT_MAP,
    TTL_SUMMARY_COUNTS,
    build_dashboard_cache_key,
    get_or_compute_dashboard_slice,
)
from foms.services.common.erp_shell_http import (
    apply_erp_shell_fragment_headers,
    wants_erp_shell_tab_body,
)
from foms.services.common.ept_b7_profile import apply_ept_b7_render_headers
from foms.services.common.erp_mine_filter import erp_tower_mine_from_request


erp_dashboard_bp = Blueprint('erp_dashboard', __name__, url_prefix='/erp')


def _dashboard_search_history_redirect_blocked(f_team: str, f_urgent: str, f_has_alert: str, f_alert_type: str) -> bool:
    """Return True when a search is scoped by operations-only filters."""
    return any(
        (
            request.args.get('mine') == '1',
            bool(f_team),
            f_urgent == '1',
            f_has_alert == '1',
            bool(f_alert_type),
        )
    )


def _redirect_to_history_for_dashboard_search(f_q: str):
    target_args = {"q": f_q, "from_dashboard": "1"}
    if wants_erp_shell_tab_body(request):
        target_args["view"] = "fragment"
    flash("ERP 대시보드에서 결과가 없어 과거 이력 검색으로 이동했습니다.", "info")
    return redirect(url_for("erp_history.history_dashboard", **target_args))


def _orders_user_visibility_fingerprint(current_user, is_admin: bool) -> dict:
    """대시보드 _q_stats / mine / 팀 가시성에 쓰이는 사용자 식별자."""
    if not current_user:
        return {"user_id": None, "role": None, "username": None, "name": None, "is_admin": bool(is_admin)}
    return {
        "user_id": getattr(current_user, "id", None),
        "role": getattr(current_user, "role", None),
        "username": getattr(current_user, "username", None),
        "name": getattr(current_user, "name", None),
        "is_admin": bool(is_admin),
    }


def _channel_desk_url() -> str:
    """채널톡 데스크 딥링크. 모바일에서 앱 설치 시 universal link로 채널톡 앱이 열린다.

    기본은 하우드(haud) 채널 데스크. 운영은 CHANNEL_DESK_URL로 특정 채널/대화로
    정밀 지정 가능.
    """
    return (os.environ.get('CHANNEL_DESK_URL') or '').strip() or 'https://desk.channel.io/haud'


@erp_dashboard_bp.route('/dashboard')
@login_required
def erp_dashboard():
    """ERP 프로세스 대시보드(MVP)"""
    db = get_db()
    is_admin = False
    current_user = getattr(g, 'current_user', None)
    if current_user and current_user.role == 'ADMIN':
        is_admin = True
    can_edit_erp_flag = can_edit_erp(current_user)

    # Batch 2a: request.args 파싱/정규화는 parse_orders_dashboard_filters로 분리(동작 보존).
    # 값·검증 규칙(MEASURED→MEASURE, sort 화이트리스트, date ISO, risk 키, focus_order int)은
    # dashboard_filters.py에 1:1로 이전. 아래는 다운스트림 호환을 위한 로컬 바인딩.
    _filters = parse_orders_dashboard_filters(request)
    f_stage = _filters.stage
    f_urgent = _filters.urgent
    f_has_alert = _filters.has_alert
    f_alert_type = _filters.alert_type
    f_q = _filters.q
    effective_stage = _filters.effective_stage
    f_team = _filters.team
    f_sort = _filters.sort
    f_today = _filters.today
    f_tower_mine = _filters.tower_mine
    f_mine = _filters.mine
    f_date = _filters.date
    f_field = _filters.field
    f_risk = _filters.risk
    focus_order_id = _filters.focus_order_id

    # Batch 2a-2: SQL 필터·정렬·_q_stats 분기 빌드는 build_orders_dashboard_queries로 분리(동작 보존).
    # count/pagination/cache/DTO는 아래에서 라우트가 계속 담당.
    # today_iso는 다운스트림(payload date 등) 호환을 위해 반환값으로 받는다.
    _q, _q_stats, today_date, today_iso = build_orders_dashboard_queries(
        db, current_user, is_admin, _filters
    )

    # Phase D: DB 레벨 페이지네이션
    page = request.args.get('page', 1, type=int)
    if page < 1: page = 1
    per_page = 50

    # f_has_alert, f_alert_type 등의 메모리 필터가 완벽하지 않으므로 (SQL 후보군),
    # count는 SQL count를 그대로 사용 (약간의 오차 허용)
    total_orders = _q.count()
    total_pages = (total_orders + per_page - 1) // per_page

    # 위험 착지 프레임(카테고리·결함·CTA·뒤로=레이더). total_orders=len(risk_ids)=카드=칩 (SSOT).
    risk_frame = build_risk_frame(
        f_risk, total_orders, back_href=url_for('erp_dashboard.erp_dashboard')
    ) if f_risk else None

    if (
        f_q
        and page == 1
        and total_orders == 0
        and not focus_order_id
        and request.args.get('from_history') != '1'
        and request.args.get('from_dashboard') != '1'
        and not _dashboard_search_history_redirect_blocked(f_team, f_urgent, f_has_alert, f_alert_type)
    ):
        return _redirect_to_history_for_dashboard_search(f_q)

    orders = _q.offset((page - 1) * per_page).limit(per_page).all()

    # 검색 카드 딥링크: 단건이 60일 창/페이지/술어와 무관하게 항상 페이지에 포함되도록 강제 주입.
    if focus_order_id and focus_order_id not in {o.id for o in orders}:
        focus_o = (
            db.query(Order)
            .filter(Order.id == focus_order_id, Order.active_filter(), Order.is_erp_order.is_(True))
            .first()
        )
        if focus_o is not None:
            orders = [focus_o] + orders

    TEAM_LABELS = {
        'CS': '라홈팀',
        'SALES': '영업팀',
        'MEASURE': '실측팀',
        'DRAWING': '도면팀',
        'PRODUCTION': '생산팀',
        'CONSTRUCTION': '시공팀',
    }

    # AS 파이프라인: 'AS처리' 클릭 시 AS접수·AS처리 표시 ('AS완료'는 '완료' 타일로 이동)
    AS_STAGE_GROUP = ('AS접수', 'AS처리')

    # 페이징된 50건에 대해서만 파이썬 필터(CS 오버라이드 및 정확한 alert 체크) 수행
    # 단, DB 페이지네이션을 썼으므로 필터링 후 50건이 안 될 수 있음.
    filtered = []
    for o in orders:
        sd = _ensure_dict(o.structured_data)
        stage = _erp_get_stage(o, sd)
        alerts = _erp_alerts(o, sd, 0)

        # 검색 카드 딥링크 단건은 alert/team 필터와 무관하게 항상 통과시킨다.
        is_focus_row = bool(focus_order_id and o.id == focus_order_id)

        if f_has_alert == '1' and not is_focus_row:
            if not (alerts.get('urgent') or alerts.get('drawing_overdue') or alerts.get('measurement_d4') or alerts.get('construction_d3') or alerts.get('production_d2')):
                continue
        if f_alert_type and not is_focus_row:
            if f_alert_type == 'urgent' and not alerts.get('urgent'):
                continue
            elif f_alert_type == 'measurement_d4' and not alerts.get('measurement_d4'):
                continue
            elif f_alert_type == 'construction_d3' and not alerts.get('construction_d3'):
                continue
            elif f_alert_type == 'production_d2' and not alerts.get('production_d2'):
                continue
            elif f_alert_type == 'drawing_overdue' and not alerts.get('drawing_overdue'):
                continue

        # --- C: f_team 인메모리 2차 확인 (CS 오버라이드 보완) ---
        if f_team and not is_admin and not is_focus_row:
            stage_code = STAGE_NAME_TO_CODE.get(stage, stage)
            if stage_code in ('MEASURE', 'CONFIRM'):
                orderer_name = (((sd or {}).get("parties") or {}).get("orderer") or {}).get("name") or ""
                is_lahom = "라홈" in orderer_name.strip()
                if is_lahom:
                    if f_team not in ('CS', 'MEASURE'):
                        continue
                else:
                    if f_team not in ('SALES', 'MEASURE'):
                        continue

        filtered.append({
            '_order': o,
            '_sd': sd,
            'stage': stage,
            'alerts': alerts,
        })

    if f_risk:
        # P1 트리아지: 페이지 내 표시도 마감/정체 오름차순으로 고정(SQL 정렬과 일치).
        def _risk_triage_key(item: dict):
            o = item['_order']
            if f_risk in ('construction_unready', 'balance_due'):
                return (str(o.erp_construction_date or '9999-99-99'), -o.id)
            if f_risk == 'measure_unassigned':
                return (str(o.erp_measurement_date or '9999-99-99'), -o.id)
            if f_risk == 'drawing_stalled':
                return ((o.erp_stage_updated_at or datetime.datetime.max).isoformat(), -o.id)
            return (str(o.id),)

        filtered.sort(key=_risk_triage_key)
    elif f_sort == 'schedule':
        def _schedule_sort_key(item: dict) -> str:
            schedule = (item.get('_sd') or {}).get('schedule') or {}
            md = (schedule.get('measurement') or {}).get('date') or '9999-99-99'
            cd = (schedule.get('construction') or {}).get('date') or '9999-99-99'
            return min(str(md), str(cd))

        filtered.sort(key=_schedule_sort_key)
    elif f_sort == 'amount':
        def _amount_sort_key(item: dict) -> int:
            sd = item.get('_sd') or {}
            total = 0
            for it in sd.get('items') or []:
                if not isinstance(it, dict):
                    continue
                raw = it.get('price') or it.get('amount') or 0
                try:
                    total += int(str(raw).replace(',', '').strip() or 0)
                except (TypeError, ValueError):
                    continue
            return total

        filtered.sort(key=_amount_sort_key, reverse=True)
    else:
        filtered.sort(key=lambda item: item['_order'].id, reverse=True)

    # --- A-0. kpis / step_stats 집계 (limit 무관하게 _q_stats에서 산출) ---
    _summary_fp = {
        "v": 4,
        "user": _orders_user_visibility_fingerprint(current_user, is_admin),
        "filters": {
            "mine": '1' if f_mine else '',
            "q": f_q,
            "team": f_team,
            "today": f_today,
        },
    }
    _summary_key = build_dashboard_cache_key("orders", "summary_counts", _summary_fp)

    # Batch 2a-3: summary 집계 compute는 compute_orders_summary_slice(read-model)로 분리(동작 보존).
    # cache 키(_summary_key)·fingerprint·get_or_compute는 라우트가 유지 → cache hit/miss 불변.
    _summary_blob = get_or_compute_dashboard_slice(
        _summary_key,
        TTL_SUMMARY_COUNTS,
        lambda: compute_orders_summary_slice(_q_stats),
        page="orders",
        slice_name="summary_counts",
    )
    kpis = _summary_blob["kpis"]
    process_steps = _summary_blob["process_steps"]

    page_slice = filtered

    # 표시용 50건: Order 객체 참조로 full enrichment
    page_orders = [item['_order'] for item in page_slice]
    page_sds = {item['_order'].id: item['_sd'] for item in page_slice}

    _att_fp = {
        "v": 1,
        "user": _orders_user_visibility_fingerprint(current_user, is_admin),
        "filters": {
            "stage": f_stage,
            "urgent": f_urgent,
            "has_alert": f_has_alert,
            "alert_type": f_alert_type,
            "q": f_q,
            "team": f_team,
            "mine": '1' if f_mine else '',
        },
        "page": page,
        "order_ids": [o.id for o in page_orders],
    }
    _att_key = build_dashboard_cache_key("orders", "attachment_assignee_maps", _att_fp)

    # Batch 2a-4: attachment/assignee maps compute는 compute_orders_attachment_assignee_maps(read-model)로 분리(동작 보존).
    # cache 키(_att_key)·fingerprint(_att_fp)·get_or_compute는 라우트가 유지 → cache hit/miss 불변.
    _maps_blob = get_or_compute_dashboard_slice(
        _att_key,
        TTL_ATTACHMENT_COUNT_MAP,
        lambda: compute_orders_attachment_assignee_maps(db, page_orders, page_sds),
        page="orders",
        slice_name="attachment_assignee_maps",
    )
    att_counts = {int(k): int(v) for k, v in (_maps_blob.get("att_counts") or {}).items()}
    user_map = {int(k): str(v) for k, v in (_maps_blob.get("user_map") or {}).items()}

    # Full enrichment: 50건만 (quest_payload, assignee_names, can_modify_domain 등 표시 필드)
    # Batch 2: 표시용 row DTO 조립은 build_orders_row_dtos(dashboard_dto)로 분리(동작 보존, 캐시 아님).
    enriched = build_orders_row_dtos(page_orders, page_sds, att_counts, user_map, current_user)

    paginated_orders = enriched

    # P1: 위험 착지 행별 단일 지배 CTA. tel→고객 전화, edit→담당배정 필드 포커스,
    # channel→채널톡 데스크 앱(담당자 연락), detail→상세 폴백.
    if f_risk:
        _cta_meta = risk_row_cta_meta(f_risk)
        if _cta_meta:
            _kind = _cta_meta['kind']
            _desk_url = _channel_desk_url() if _kind == 'channel' else None
            for row in paginated_orders:
                _external = False
                if _kind == 'tel':
                    _digits = ''.join(ch for ch in str(row.get('phone') or '') if ch.isdigit())
                    _href = ('tel:' + _digits) if _digits else url_for('erp_dashboard.erp_order_mobile_detail', order_id=row['id'])
                elif _kind == 'edit':
                    _href = url_for('order_edit.edit_order', order_id=row['id'], open='erp-order', focus='assignee')
                elif _kind == 'channel':
                    _href = _desk_url
                    _external = True
                else:
                    _href = url_for('erp_dashboard.erp_order_mobile_detail', order_id=row['id'])
                row['risk_cta'] = {
                    'label': _cta_meta['label'], 'icon': _cta_meta['icon'],
                    'tone': _cta_meta['tone'], 'href': _href, 'external': _external,
                }

    _preview_items = batch_resolve_queue_attachment_preview_items(
        db, [int(r["id"]) for r in paginated_orders if r.get("id")]
    )
    for row in paginated_orders:
        oid = int(row["id"])
        items = _preview_items.get(oid, [])
        row["attachment_preview_items"] = items
        row["attachment_preview_urls"] = [item["view"] for item in items if item.get("view")]

    # 상세 payload는 서버 fragment에 선적재하지 않는다(과거 50행분 detail_payload preload가
    # fragment 크기의 최대 덩어리였음). 패널을 처음 열 때 클라이언트가
    # /api/orders/<id>/detail-payload 로 lazy fetch한다(erp_orders_structured.
    # api_get_order_detail_payload → build_order_detail_payload_map 단건 재사용).
    template_name = (
        'orders/partials/dashboard_main.html'
        if wants_erp_shell_tab_body(request)
        else 'orders/dashboard.html'
    )
    _t0 = time.perf_counter()
    uid = current_user.id if current_user else None
    mobile_v2 = is_mobile_v2_shell(resolve_shell_variant_cached(uid))
    split_enabled = mobile_v2 and env_bool_or_mobile_v2(
        "FOMS_TABLET_SPLIT_VIEW_ENABLED",
        mobile_v2_active=mobile_v2,
    )

    # 모바일 홈 = 오퍼레이션 컨트롤 타워. 드릴(검색/필터/단계/내것/뷰=큐)이 없을 때만 타워,
    # 드릴이 걸리면 기존 작업 큐로 전환한다. (단계 타일·위험 카드가 큐로 연결됨)
    _has_drill = any((
        f_q, effective_stage, f_urgent == '1', f_has_alert == '1', f_alert_type,
        f_team, request.args.get('mine') == '1', f_today == '1', bool(f_date), bool(f_risk),
        request.args.get('view') == 'queue',
        request.args.get('focus_order'),
    ))
    # mobile_chunk(무한스크롤 조각 요청)은 큐 전용 → 타워 페이로드 계산을 건너뛴다.
    _is_chunk = request.args.get('mobile_chunk') == '1'
    tower_mode = bool(mobile_v2 and not _has_drill and not _is_chunk)
    control_tower = None
    if tower_mode:
        _tower_fp = {
            "v": 2,
            "user": _orders_user_visibility_fingerprint(current_user, is_admin),
            "date": today_iso,
            "mine": f_tower_mine,
        }
        _tower_key = build_dashboard_cache_key("orders", "mobile_control_tower", _tower_fp)
        control_tower = get_or_compute_dashboard_slice(
            _tower_key,
            TTL_SUMMARY_COUNTS,
            lambda: build_mobile_control_tower(
                db, current_user, today=get_today_kst(), mine_only=f_tower_mine
            ),
            page="orders",
            slice_name="mobile_control_tower",
        )

    _mobile_ctx = {
        "orders": paginated_orders,
        "filters": {
            'stage': effective_stage,
            'urgent': f_urgent,
            'has_alert': f_has_alert,
            'alert_type': f_alert_type,
            'q': f_q,
            'team': f_team,
            'mine': '1' if f_mine else '',
            'sort': f_sort,
            'today': f_today,
            'date': f_date,
            'field': f_field,
            'risk': f_risk,
        },
        "kpis": kpis,
        "process_steps": process_steps,
        "page": page,
        "total_pages": total_pages,
        "total_orders": total_orders,
        "can_edit_erp": can_edit_erp_flag,
        "current_user": current_user,
    }

    if mobile_v2 and request.args.get('mobile_chunk') == '1':
        _chunk = render_template(
            'orders/partials/dashboard_mobile_v2_chunk.html',
            **_mobile_ctx,
        )
        response = make_response(_chunk)
        apply_erp_shell_fragment_headers(response, request)
        return response

    _mytasks_href = (
        url_for('erp_dashboard.erp_dashboard')
        if f_tower_mine
        else url_for('erp_dashboard.erp_dashboard', tower_mine='1')
    )
    _body = render_template(
        template_name,
        erp_dashboard_fragment=wants_erp_shell_tab_body(request),
        orders=paginated_orders,
        kpis=kpis,
        process_steps=process_steps,
        tower_mode=tower_mode,
        control_tower=control_tower,
        tower_mine_active=f_tower_mine,
        mobile_shell_show_mytasks=tower_mode,
        mobile_shell_mytasks_active=f_tower_mine,
        mobile_shell_mytasks_href=_mytasks_href,
        risk_frame=risk_frame,
        filters={
            'stage': effective_stage,
            'urgent': f_urgent,
            'has_alert': f_has_alert,
            'alert_type': f_alert_type,
            'q': f_q,
            'team': f_team,
            'mine': '1' if f_mine else '',
            'sort': f_sort,
            'today': f_today,
            'date': f_date,
            'field': f_field,
            'risk': f_risk,
        },
        team_labels=TEAM_LABELS,
        stage_labels=STAGE_LABELS,
        is_admin=is_admin,
        can_edit_erp=can_edit_erp_flag,
        status_choices=list(BULK_ACTION_STATUS.items()) + [('DELETED', '삭제(휴지통)')],
        page=page,
        total_pages=total_pages,
        total_orders=total_orders,
        foms_split_enabled=split_enabled,
        master_cards=build_split_master_cards(
            paginated_orders,
            active_order_id=int(request.args.get('order') or 0) or None,
        ) if split_enabled else [],
        side_items=default_split_side_items() if split_enabled else [],
    )
    _render_ms = (time.perf_counter() - _t0) * 1000.0
    response = make_response(_body)
    apply_erp_shell_fragment_headers(response, request)
    apply_ept_b7_render_headers(response, route_id="erp_dashboard", render_ms=_render_ms)
    return response


@erp_dashboard_bp.route('/dashboard/')
@login_required
def erp_dashboard_trailing_slash():
    """Normalize mobile/browser-saved trailing-slash dashboard URLs."""
    return redirect(url_for('erp_dashboard.erp_dashboard', **request.args))


@erp_dashboard_bp.route('/dashboard/field-ops')
@login_required
def erp_dashboard_field_ops():
    """모바일 홈 '현장 일정' 인라인 swap — 특정 날짜·타입 현장 목록(JSON+HTML).

    주간 타일 클릭(날짜 변경)과 실측/시공 탭(타입 필터)이 공유하는 단일 소스.
    """
    db = get_db()
    current_user = getattr(g, 'current_user', None)
    field_type = (request.args.get('field') or 'all').strip()
    if field_type not in ('all', 'measure', 'construction', 'as'):
        field_type = 'all'
    mine_only = erp_tower_mine_from_request(request)

    date_iso = (request.args.get('date') or '').strip()
    try:
        datetime.date.fromisoformat(date_iso)
    except ValueError:
        date_iso = get_today_kst().isoformat()

    payload = build_field_ops_for_day(
        db, current_user, date_iso, field_type=field_type, mine_only=mine_only
    )
    list_html = render_template(
        'orders/partials/dashboard_mobile_tower_field_list.html',
        rows=payload['rows'],
    )
    queue_args = {'date': date_iso, 'view': 'queue'}
    if field_type in ('measure', 'construction', 'as'):
        queue_args['field'] = field_type
    return {
        'success': True,
        'data': {
            'html': list_html,
            'count': payload['count'],
            'measure_count': payload['measure_count'],
            'construction_count': payload['construction_count'],
            'as_count': payload['as_count'],
            'label': payload['label'],
            'iso': date_iso,
            'queue_href': url_for('erp_dashboard.erp_dashboard', **queue_args),
        },
    }


@erp_dashboard_bp.route('/orders/<int:order_id>/mobile')
@login_required
def erp_order_mobile_detail(order_id: int):
    """P1 mockup: 모바일 주문 상세 (/erp/orders/<id>/mobile)."""
    db = get_db()
    order = (
        db.query(Order)
        .filter(Order.id == order_id, Order.is_erp_order.is_(True), Order.not_deleted_filter())
        .first()
    )
    if not order:
        flash('주문을 찾을 수 없습니다.', 'warning')
        return redirect(url_for('erp_dashboard.erp_dashboard'))

    from foms.services.erp_mobile_order_display import (
        build_mobile_queue_batch_context,
        build_mobile_queue_order_row,
    )

    current_user = getattr(g, 'current_user', None)
    # 단건이라도 batch_ctx 없이는 ~5쿼리(첨부/미리보기/타임라인/담당자 단건조회) —
    # shipment/measurement/fragment.py 와 동일 배치 패턴.
    _batch_ctx = build_mobile_queue_batch_context(db, [order])
    order_row = build_mobile_queue_order_row(db, order, current_user, batch_ctx=_batch_ctx)
    can_edit_erp_flag = can_edit_erp(current_user)
    return_to = (request.args.get('return_to') or '').strip()
    back_endpoint = resolve_edit_return_back_endpoint(return_to)

    return render_template(
        'orders/mobile_order_detail.html',
        order=order_row,
        can_edit_erp=can_edit_erp_flag,
        erp_sub_nav_active='dashboard',
        mobile_shell_title='주문 상세',
        mobile_shell_show_back=True,
        mobile_shell_back_href=url_for(back_endpoint),
    )
