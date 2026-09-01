"""
ERP 지도·주소·유저 API. (Phase 4-4)
erp.py에서 분리: map_data, erp users 목록, generate_map, update_address.
"""
import datetime
import hashlib
import json
import os
import threading


from flask import Blueprint, request, jsonify, render_template, current_app, g
from sqlalchemy import or_, and_
from sqlalchemy.orm import Session

from db import get_db
from models import Order, User
from foms.web.auth import log_access, login_required
from foms.services.audit_message_display import describe_action, describe_order_action
from foms.services.orders.audit_order_context import order_audit_context
from foms.services.erp_permissions import erp_edit_required
from foms.services.erp_display import _normalize_for_search
from foms.services.common.address_converter import FOMSAddressConverter
from foms.services.common.geocode_config import KAKAO_JS_API_KEY
from foms.services.common.map_generator import FOMSMapGenerator
from foms.services.datetime_kst import now_utc_naive
from foms.services.geocode_retry import canonicalize_status, should_retry_geocode
from foms.services.jobs.queue import enqueue_geocode_order_address
from foms.services.order_geocode import reset_order_geocode_on_address_change
from foms.services.order_geocode_outbox import enqueue_order_address_geocode
from foms.services.orders.revision import RevisionError, execute_order_mutation
from foms.services.address_learning_requests import (
    AddressLearningError,
    AddressLearningRateLimited,
    record_address_learning_request,
)
from foms.services.erp_display import normalize_manager_name
from foms.services.measurement_read_model import apply_measurement_dashboard_order_scope
erp_map_bp = Blueprint('erp_map', __name__)
_converter_instance = None
_converter_lock = threading.Lock()
_MAP_MAX_LIMIT_DEFAULT = 500  # measurement 실측일 limit 잘림 완화 (#2662 등, 2026-03-15)


def _read_int_env(name, default_value, min_value):
    try:
        value = int(os.environ.get(name, str(default_value)) or default_value)
    except (TypeError, ValueError):
        value = default_value
    return max(min_value, value)


_MAP_SCAN_MAX_LIMIT = _read_int_env('ERP_MAP_SCAN_MAX_LIMIT', 800, 200)


def _resolve_map_limit(raw_limit, default_limit=100):
    max_limit = _read_int_env('ERP_MAP_MAX_LIMIT', _MAP_MAX_LIMIT_DEFAULT, 50)
    try:
        value = int(raw_limit) if raw_limit is not None else int(default_limit)
    except (TypeError, ValueError):
        value = int(default_limit)
    if value <= 0:
        value = int(default_limit)
    return min(value, max_limit)


def _get_address_converter():
    global _converter_instance
    if _converter_instance is None:
        with _converter_lock:
            if _converter_instance is None:
                _converter_instance = FOMSAddressConverter()
    return _converter_instance


def _normalize_map_status_filter(raw_status):
    status = (raw_status or '').strip().upper()
    if not status:
        return ''
    legacy_aliases = {
        'MEASURED': 'MEASURE',
    }
    return legacy_aliases.get(status, status)


def _format_map_date(date_value):
    if date_value is None:
        return None
    if isinstance(date_value, str):
        return date_value
    if hasattr(date_value, 'strftime'):
        return date_value.strftime('%Y-%m-%d')
    return str(date_value)


def _query_map_orders(db, *, date_filter=None, status_filter=None, dashboard=None, limit=100):
    query = db.query(Order).filter(Order.active_filter())

    # 자가실측 상태는 플래그 있는 주문만 포함. 지방주문(is_regional)도 실측 대시보드에 표시.
    if dashboard == 'measurement':
        query = apply_measurement_dashboard_order_scope(query)
    else:
        query = query.filter(
            Order.is_regional != True,
            ~Order.status.in_(['SELF_MEASUREMENT', 'SELF_MEASURED'])
        )

    normalized_status = _normalize_map_status_filter(status_filter)
    if dashboard == 'measurement':
        # 실측 대시보드 지도는 항상 실측 상태만 보여준다.
        normalized_status = 'MEASURE'
    if normalized_status and normalized_status != 'ALL':
        if normalized_status == 'MEASURE':
            query = query.filter(Order.status.in_(['MEASURE', 'MEASURED']))
        else:
            query = query.filter(Order.status == normalized_status)

    from models import OrderScheduleDate
    if date_filter:
        query = query.join(OrderScheduleDate, Order.id == OrderScheduleDate.order_id)
        if dashboard == 'measurement':
            query = query.filter(
                OrderScheduleDate.kind == 'measurement',
                OrderScheduleDate.date == date_filter
            )
        else:
            query = query.filter(
                or_(
                    OrderScheduleDate.date == date_filter,
                    Order.received_date == date_filter,
                    Order.as_received_date == date_filter,
                    Order.as_completed_date == date_filter
                )
            )
        query = query.distinct(Order.id)

    orders = query.order_by(Order.id.desc()).limit(limit).all()

    if dashboard == 'measurement':
        from foms.services.erp_display import self_measurement_four_checks_done
        orders = [o for o in orders if not self_measurement_four_checks_done(o)]

    return orders


def _extract_map_order_display(order):
    customer_name = order.customer_name
    phone = order.phone
    address_to_use = order.address
    product = order.product
    measurement_date = order.measurement_date
    measurement_time = order.measurement_time
    scheduled_date = order.scheduled_date
    manager_name = order.manager_name or '-'

    if order.is_erp_order and order.structured_data:
        sd = order.structured_data
        erp_customer_name = ((sd.get('parties') or {}).get('customer') or {}).get('name')
        if erp_customer_name:
            customer_name = erp_customer_name

        erp_phone = ((sd.get('parties') or {}).get('customer') or {}).get('phone')
        if erp_phone:
            phone = erp_phone

        erp_address_full = (sd.get('site') or {}).get('address_full')
        erp_address_main = (sd.get('site') or {}).get('address_main')
        erp_address_detail = (sd.get('site') or {}).get('address_detail')

        if erp_address_full and erp_address_full.strip() and erp_address_full != '-':
            address_to_use = erp_address_full.strip()
        elif erp_address_main and erp_address_main.strip():
            if erp_address_detail and erp_address_detail.strip() and erp_address_detail != '-':
                address_to_use = f"{erp_address_main.strip()} {erp_address_detail.strip()}"
            else:
                address_to_use = erp_address_main.strip()

        items = sd.get('items') or []
        if items and len(items) > 0:
            first_item = items[0]
            product_name = first_item.get('product_name') or first_item.get('name')
            if product_name:
                if len(items) > 1:
                    product = f"{product_name} 외 {len(items) - 1}개"
                else:
                    product = product_name

        erp_measurement_date = (((sd.get('schedule') or {}).get('measurement') or {}).get('date'))
        if erp_measurement_date:
            measurement_date = erp_measurement_date

        erp_measurement_time = (((sd.get('schedule') or {}).get('measurement') or {}).get('time'))
        if erp_measurement_time:
            measurement_time = erp_measurement_time

        erp_scheduled_date = (((sd.get('schedule') or {}).get('construction') or {}).get('date'))
        if erp_scheduled_date:
            scheduled_date = erp_scheduled_date

        erp_manager_name = normalize_manager_name(
            (sd.get('parties') or {}).get('manager'),
            manager_name,
        )
        if erp_manager_name:
            manager_name = erp_manager_name

    return {
        'customer_name': customer_name,
        'phone': phone,
        'address': address_to_use,
        'product': product,
        'measurement_date': measurement_date,
        'measurement_time': measurement_time,
        'scheduled_date': scheduled_date,
        'manager_name': manager_name,
    }


def _order_matches_map_filters(order, display, *, manager_filter='', search_query=''):
    if manager_filter:
        manager_name_str = str(display['manager_name'] or '')
        if manager_filter.lower() not in manager_name_str.lower():
            return False

    if not search_query:
        return True

    search_lower = _normalize_for_search(search_query).lower()
    searchable_parts = [
        str(order.id),
        display['address'],
        order.address,
        display['customer_name'],
        display['product'],
        order.notes,
        display['manager_name'],
    ]
    if order.is_erp_order and order.structured_data:
        site = (order.structured_data.get('site') or {})
        searchable_parts.extend([
            site.get('address_full'),
            site.get('address_main'),
            site.get('address_detail'),
            site.get('address_note'),
        ])

    searchable = _normalize_for_search(' '.join(
        str(p).strip() for p in searchable_parts if p
    )).lower()
    return bool(searchable and search_lower in searchable)


def _build_map_payload(orders, *, manager_filter='', search_query='', enqueue_missing=False, result_limit=None):
    from foms.services.geocode_helpers import extract_address_from_order

    map_data = []
    orders_list = []
    skipped_no_coords = 0
    to_geocode = []
    # 재큐 백오프 기준 시각(naive UTC — geocoded_at 저장 규약과 같은 축).
    geocode_now = now_utc_naive()

    for order in orders:
        display = _extract_map_order_display(order)
        if not _order_matches_map_filters(
            order,
            display,
            manager_filter=manager_filter,
            search_query=search_query,
        ):
            continue
        if result_limit and len(orders_list) >= result_limit:
            break

        lat = getattr(order, 'lat', None)
        lng = getattr(order, 'lng', None)
        stored_geocode_status = getattr(order, 'geocode_status', None)
        has_coords = lat is not None and lng is not None

        # lat/lng를 단일 진실 소스로 사용 (stored_geocode_status와 불일치 시 좌표 우선)
        if has_coords:
            geocode_status = 'success'
        else:
            skipped_no_coords += 1
            address_for_geocode = extract_address_from_order(order)
            # 재시도 판정은 foms.services.geocode_retry SSOT. 예전에는
            # ``not stored_geocode_status`` 라 한 번이라도 실패한 주문을 **영구 제외**했고,
            # 그래서 일시적 네트워크 사고로 failed 가 된 건이 영원히 좌표를 못 받았다.
            if (
                enqueue_missing
                and address_for_geocode
                and address_for_geocode.strip()
                and address_for_geocode.strip() != '-'
                and should_retry_geocode(order, now=geocode_now)
            ):
                geocode_status = 'pending'
                to_geocode.append(order)
            else:
                # address_error 는 화면이 아는 3상태(success/pending/failed)로 접어 내보낸다.
                geocode_status = canonicalize_status(stored_geocode_status) or 'failed'

        orders_list.append({
            'id': order.id,
            'customer_name': display['customer_name'],
            'phone': display['phone'],
            'address': display['address'],
            'product': display['product'],
            'status': order.status,
            'received_date': _format_map_date(order.received_date),
            'measurement_date': _format_map_date(display['measurement_date']),
            'measurement_time': display.get('measurement_time'),
            'scheduled_date': _format_map_date(display['scheduled_date']),
            'completion_date': _format_map_date(order.completion_date),
            'manager_name': display['manager_name'],
            'notes': order.notes or '-',
            'conversion_status': geocode_status,
        })

        if lat is not None and lng is not None:
            map_data.append({
                'id': order.id,
                'customer_name': display['customer_name'],
                'phone': display['phone'],
                'address': display['address'],
                'product': display['product'],
                'status': order.status,
                'received_date': _format_map_date(order.received_date),
                'measurement_time': display.get('measurement_time'),
                'latitude': float(lat),
                'longitude': float(lng),
                'conversion_status': geocode_status,
            })

    return {
        'map_data': map_data,
        'orders': orders_list,
        'skipped_no_coords': skipped_no_coords,
        'to_geocode': to_geocode,
    }


@erp_map_bp.route('/map_view')
@login_required
def map_view():
    """지도 보기 페이지.

    EPT-B5: standalone full document — this route does not call
    ``apply_erp_shell_fragment_headers``; shell tab fetch / FRAGMENT_READY does not
    target ``/map_view``.
    """
    # 카카오 지도 클라이언트 렌더용 JS 키(SSOT: geocode_config) — 템플릿 data 속성 주입.
    return render_template('measurement/map_view.html', kakao_js_key=KAKAO_JS_API_KEY)


def _normalize_map_date(value):
    """날짜를 YYYY-MM-DD로 정규화. 빈/잘못된 값은 None."""
    if value is None:
        return None
    s = (value or '').strip()
    if not s:
        return None
    if len(s) >= 10 and s[4] == '-' and s[7] == '-':
        try:
            datetime.datetime.strptime(s[:10], '%Y-%m-%d')
            return s[:10]
        except ValueError:
            pass
    return None


def _resolve_pending_geocodes(
    db,
    payload,
    *,
    date_filter,
    status_filter,
    dashboard,
    scan_limit,
    manager_filter,
    search_query,
    result_limit,
):
    """payload['to_geocode'] 주문을 RQ 큐에 넣고(불가 시 동기 폴백), 폴백 시 payload 재조립.

    `/api/generate_map`(folium)과 `/api/map_data?enqueue=1`(카카오 클라 렌더)이
    동일 지오코딩 트리거 계보를 쓰도록 추출한 공용 헬퍼(동작 보존).

    Args:
        db: SQLAlchemy 세션.
        payload: `_build_map_payload(..., enqueue_missing=True)` 결과.
        나머지: 동기 폴백 발생 시 재조회에 필요한 원 쿼리 파라미터.

    Returns:
        갱신된 payload dict (폴백 미발생 시 입력 그대로).
    """
    queued_orders = []
    used_sync_fallback = False
    for order in payload['to_geocode']:
        queued = enqueue_geocode_order_address(order.id)
        if queued:
            order.geocode_status = 'pending'
            # 시도 표식 — 이게 없으면 pending 의 나이가 갱신되지 않아 백오프가 지난 건이
            # 지도를 열 때마다 다시 큐에 들어간다(재큐가 failed 까지 넓어져 생긴 요구).
            order.geocoded_at = now_utc_naive()
            queued_orders.append(order)
        else:
            from foms.services.jobs.tasks import geocode_order_address
            try:
                geocode_order_address(order.id)
                used_sync_fallback = True
            except Exception as e:
                current_app.logger.warning(
                    "map geocode fallback failed for order_id=%s: %s",
                    order.id,
                    e,
                    exc_info=True,
                )
    if queued_orders:
        db.commit()
    if used_sync_fallback:
        db.expire_all()
        orders = _query_map_orders(
            db,
            date_filter=date_filter,
            status_filter=status_filter,
            dashboard=dashboard,
            limit=scan_limit,
        )
        payload = _build_map_payload(
            orders,
            manager_filter=manager_filter,
            search_query=search_query,
            enqueue_missing=False,
            result_limit=result_limit,
        )
    return payload


@erp_map_bp.route('/api/map_data')
@login_required
def api_map_data():
    """지도 표시용 주문 데이터 API.

    `enqueue=1`이면 좌표 없는 주문의 지오코딩을 트리거한다(카카오 클라이언트
    렌더의 최초 로드용 — `/api/generate_map`과 동일 계보, 폴링 호출은 미지정).
    """
    try:
        date_filter = _normalize_map_date(request.args.get('date'))
        status_filter = request.args.get('status')
        dashboard = request.args.get('dashboard')
        manager_filter = (request.args.get('manager') or '').strip()
        search_query = (request.args.get('q') or request.args.get('search') or '').strip()
        enqueue = (request.args.get('enqueue') or '').strip() == '1'
        limit = _resolve_map_limit(
            request.args.get('limit'),
            default_limit=500 if dashboard in ('measurement', 'as') else 200
        )

        # as 모드: AS 탭 미완료 SSOT 쿼리, 날짜 무관 전체 (2026-08-05)
        if dashboard == 'as':
            from foms.api.cs.as_map import as_map_data_response
            return as_map_data_response(
                search_query=search_query,
                manager_filter=manager_filter,
                bucket=(request.args.get('bucket') or '').strip(),
                limit=limit,
                enqueue=enqueue,
                avail_days=(request.args.get('avail_days') or '').strip(),
                avail_time=(request.args.get('avail_time') or '').strip(),
            )

        # measurement 모드: map_snapshot 사용, 전체 주문 반환 (2026-03-15)
        if dashboard == 'measurement' and date_filter:
            from foms.api.measurement.map import measurement_map_data_response
            mine = (request.args.get('mine') or '').strip() == '1'
            return measurement_map_data_response(
                date_filter=date_filter,
                search_query=search_query,
                manager_filter=manager_filter,
                dashboard=dashboard,
                limit=limit,
                mine=mine,
                current_user=getattr(g, 'current_user', None),
                enqueue=enqueue,
            )

        scan_limit = _MAP_SCAN_MAX_LIMIT if date_filter else min(_MAP_SCAN_MAX_LIMIT, max(limit, limit * 3))
        db = get_db()
        orders = _query_map_orders(
            db,
            date_filter=date_filter,
            status_filter=status_filter,
            dashboard=dashboard,
            limit=scan_limit,
        )
        payload = _build_map_payload(
            orders,
            manager_filter=manager_filter,
            search_query=search_query,
            enqueue_missing=enqueue,
            result_limit=limit,
        )
        if enqueue:
            payload = _resolve_pending_geocodes(
                db,
                payload,
                date_filter=date_filter,
                status_filter=status_filter,
                dashboard=dashboard,
                scan_limit=scan_limit,
                manager_filter=manager_filter,
                search_query=search_query,
                result_limit=limit,
            )

        map_data_list = payload.get('map_data', [])
        orders_list = payload.get('orders', [])

        return jsonify({
            'success': True,
            'data': map_data_list,
            'orders': orders_list,
            'total_orders': len(orders_list),
            'converted_orders': len(map_data_list),
            'skipped_no_coords': payload.get('skipped_no_coords', 0),
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@erp_map_bp.route('/erp/api/users', methods=['GET'])
@login_required
def api_erp_users_list():
    """ERP 사용자 목록 반환 (팀 필터링 가능)"""
    team_filter = request.args.get('team')
    query = get_db().query(User).filter(User.is_active == True)

    if team_filter:
        query = query.filter(User.team == team_filter)

    users = query.all()
    return jsonify({
        'success': True,
        'users': [{'id': u.id, 'name': u.name, 'team': u.team} for u in users]
    })


@erp_map_bp.route('/api/generate_map')
@login_required
def api_generate_map():
    """지도 HTML 생성 API"""
    try:
        date_filter = _normalize_map_date(request.args.get('date'))
        status_filter = request.args.get('status')
        dashboard = request.args.get('dashboard')
        manager_filter = (request.args.get('manager') or '').strip()
        search_query = (request.args.get('q') or request.args.get('search') or '').strip()
        title = request.args.get('title', '주문 위치 지도')
        limit = _resolve_map_limit(
            request.args.get('limit'),
            default_limit=500 if dashboard in ('measurement', 'as') else 200
        )
        scan_limit = _MAP_SCAN_MAX_LIMIT if date_filter else min(_MAP_SCAN_MAX_LIMIT, max(limit, limit * 3))

        # as 모드: folium 폴백도 동일 SSOT 쿼리 파리티 (2026-08-05)
        if dashboard == 'as':
            from foms.api.cs.as_map import AS_MAP_DEFAULT_TITLE, as_generate_map_response
            return as_generate_map_response(
                search_query=search_query,
                manager_filter=manager_filter,
                bucket=(request.args.get('bucket') or '').strip(),
                limit=limit,
                title=request.args.get('title') or AS_MAP_DEFAULT_TITLE,
                avail_days=(request.args.get('avail_days') or '').strip(),
                avail_time=(request.args.get('avail_time') or '').strip(),
            )

        # measurement 모드: shared query builder 사용 (2026-03-15)
        if dashboard == 'measurement' and date_filter:
            from foms.api.measurement.map import measurement_generate_map_response
            mine = (request.args.get('mine') or '').strip() == '1'
            return measurement_generate_map_response(
                date_filter=date_filter,
                search_query=search_query,
                manager_filter=manager_filter,
                dashboard=dashboard,
                limit=limit,
                title=title,
                mine=mine,
                current_user=getattr(g, 'current_user', None),
            )

        db = get_db()
        orders = _query_map_orders(
            db,
            date_filter=date_filter,
            status_filter=status_filter,
            dashboard=dashboard,
            limit=scan_limit,
        )
        payload = _build_map_payload(
            orders,
            manager_filter=manager_filter,
            search_query=search_query,
            enqueue_missing=True,
            result_limit=limit,
        )

        payload = _resolve_pending_geocodes(
            db,
            payload,
            date_filter=date_filter,
            status_filter=status_filter,
            dashboard=dashboard,
            scan_limit=scan_limit,
            manager_filter=manager_filter,
            search_query=search_query,
            result_limit=limit,
        )

        map_generator = FOMSMapGenerator()

        map_data_list = payload.get('map_data', [])
        orders_list = payload.get('orders', [])
        skipped_no_coords = payload.get('skipped_no_coords', 0)

        if map_data_list:
            folium_map = map_generator.create_map(map_data_list, title)
            if folium_map:
                map_html = folium_map._repr_html_()
            else:
                map_html = '<div class="error-message">지도를 생성할 수 없습니다.</div>'

            return jsonify({
                'success': True,
                'map_html': map_html,
                'total_orders': len(orders_list),
                'converted_orders': len(map_data_list),
                'skipped_no_coords': skipped_no_coords,
                'orders': orders_list,
            })

        empty_map = map_generator.create_empty_map(title)
        if empty_map:
            map_html = empty_map._repr_html_()
            return jsonify({
                'success': True,
                'map_html': map_html,
                'total_orders': len(orders_list),
                'converted_orders': 0,
                'skipped_no_coords': skipped_no_coords,
                'orders': orders_list,
                'message': f'{title} 지도에 표시할 마커가 없습니다. 우측 목록에서 주소 오류를 확인하세요.' if orders_list else f'{title}에 해당하는 주문이 없습니다.'
            })

        return jsonify({'success': False, 'error': '지도를 생성할 수 없습니다.'})

    except Exception as e:
        current_app.logger.error("generate_map error: %s", e, exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@erp_map_bp.route('/api/calculate_route')
@login_required
def api_calculate_route():
    """두 지점 간 경로 계산 API"""
    try:
        start_lat = request.args.get('start_lat', type=float)
        start_lng = request.args.get('start_lng', type=float)
        end_lat = request.args.get('end_lat', type=float)
        end_lng = request.args.get('end_lng', type=float)
        if not all([start_lat, start_lng, end_lat, end_lng]):
            return jsonify({'success': False, 'error': '출발지와 도착지 좌표가 모두 필요합니다.'}), 400
        converter = _get_address_converter()
        route_result = converter.calculate_route(start_lat, start_lng, end_lat, end_lng)
        if route_result['status'] == 'success':
            return jsonify({'success': True, 'data': route_result})
        return jsonify({'success': False, 'error': route_result['message']}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': f'경로 계산 중 오류: {str(e)}'}), 500


@erp_map_bp.route('/api/address_suggestions')
@login_required
def api_address_suggestions():
    """주소 교정 제안 API"""
    try:
        address = request.args.get('address')
        if not address:
            return jsonify({'success': False, 'error': '주소가 필요합니다.'}), 400
        converter = _get_address_converter()
        suggestions = converter.get_address_suggestions(address)
        return jsonify({'success': True, 'suggestions': suggestions})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@erp_map_bp.route('/api/add_address_learning', methods=['POST'])
@login_required
def api_add_address_learning():
    """주소 학습 데이터 추가 API — audit child + rate limit(무제한 all-STAFF 쓰기 거부).

    구 in-memory ``add_learning_data`` 무제한 쓰기를 대체한다: 교정을 durable child 행
    (:class:`~models.AddressLearningRequest`, 누가/언제 audit)으로 기록하고, 사용자별 rate
    창 상한을 강제하며, 실제 학습 적용은 ADDRESS_LEARNING outbox side-effect 로 예약한다.
    """
    db: Session = get_db()
    try:
        data = request.get_json() or {}
        original_address = data.get('original_address')
        corrected_address = data.get('corrected_address')
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        if not all([original_address, corrected_address, latitude, longitude]):
            return jsonify({'success': False, 'error': '모든 필드가 필요합니다.'}), 400

        user_id = getattr(getattr(g, 'current_user', None), 'id', None)
        try:
            record_address_learning_request(
                db,
                original_address=original_address,
                corrected_address=corrected_address,
                lat=latitude,
                lng=longitude,
                requested_by_user_id=user_id,
            )
            # 주소 원문은 남기지 않는다(고객 주소 = PII) — 학습 요청이 있었다는 사실만.
            log_access(
                describe_action("ADDRESS_LEARNING_ADDED", target_label="주소 학습"),
                user_id,
                auto_commit=False,
                action="ADDRESS_LEARNING_ADDED", target_type="address_learning",
                target_id=None, detail={"has_correction": True},
            )
            db.commit()
        except AddressLearningRateLimited as exc:
            db.rollback()
            return jsonify({'success': False, 'error': str(exc)}), 429
        except AddressLearningError as exc:
            db.rollback()
            return jsonify({'success': False, 'error': str(exc)}), 400

        # 학습 사전 캐시 무효화(교정이 이후 지오코드에 반영되도록). 적용 자체는 worker 몫.
        _get_address_converter().clear_geocode_cache()
        return jsonify({'success': True, 'message': '학습 데이터가 추가되었습니다.'})
    except Exception as e:
        db.rollback()
        current_app.logger.error("add_address_learning error: %s", e, exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@erp_map_bp.route('/api/validate_address')
@login_required
def api_validate_address():
    """주소 유효성 검증 API"""
    try:
        address = request.args.get('address')
        if not address:
            return jsonify({'success': False, 'error': '주소가 필요합니다.'}), 400
        converter = _get_address_converter()
        validation = converter.validate_address(address)
        return jsonify({'success': True, 'validation': validation})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


#: 주소 수정 mutation 의 receipt idempotency scope 식별자(auth 는 erp_edit_required 담당).
UPDATE_ADDRESS_POLICY_ID = 'ERP_EDIT'


@erp_map_bp.route('/api/orders/<int:order_id>/update_address', methods=['POST'])
@login_required
@erp_edit_required
def api_update_order_address(order_id):
    """주문 주소를 수정하고 재-지오코딩을 SIDEFX outbox 로 예약한다.

    저장은 REV-00 :func:`execute_order_mutation` 경유(If-Match·version bump·receipt·
    ADDRESS_CHANGED event 한 tx). 지오코드는 GEOCODE outbox 이벤트로 예약하며 **postcommit
    직접 지오코드/폴백은 하지 않는다**(worker 비동기 처리). 좌표는 항상 pending 으로 응답한다.
    """
    db: Session = get_db()
    try:
        data = request.get_json() or {}
        new_address = (data.get('address') or '').strip()
        if not new_address:
            return jsonify({'success': False, 'message': '주소를 입력해주세요.'}), 400

        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        if_match_raw = (request.headers.get('If-Match') or '').strip().strip('"')
        expected_versions = None
        if if_match_raw:
            try:
                expected_versions = {order_id: int(if_match_raw)}
            except ValueError:
                return jsonify({'success': False, 'message': 'If-Match 형식이 올바르지 않습니다.'}), 400
        idempotency_key = (request.headers.get('Idempotency-Key') or '').strip() or None
        user_id = getattr(getattr(g, 'current_user', None), 'id', None)
        scope_hash = hashlib.sha256(f'{UPDATE_ADDRESS_POLICY_ID}:{order_id}'.encode()).hexdigest()
        request_hash = hashlib.sha256(
            json.dumps({'address': new_address}, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()

        def _mutate(sess: Session, orders):
            """row lock 아래에서 주소·site·좌표 초기화 + GEOCODE outbox 예약(no postcommit)."""
            o = orders[0]
            reset_order_geocode_on_address_change(o, new_address)
            enqueue_order_address_geocode(sess, o, address=new_address, actor_user_id=user_id)
            return {o.id: [f'ORDER_DETAIL:{o.id}', 'ORDERS_INDEX', 'MEASUREMENT']}

        try:
            outcome = execute_order_mutation(
                db,
                actor_user_id=user_id,
                policy_id=UPDATE_ADDRESS_POLICY_ID,
                order_ids=[order_id],
                expected_versions=expected_versions,
                idempotency_key=idempotency_key,
                scope_hash=scope_hash,
                request_hash=request_hash,
                mutation=_mutate,
            )
            # 주소 값 자체는 원장에 남기지 않는다(PII) — "주소를 고쳤다"는 사실만 남긴다.
            address_context = order_audit_context(order)
            log_access(
                describe_order_action(order_id=order_id, action="ORDER_ADDRESS_UPDATED",
                                      **address_context),
                user_id,
                auto_commit=False,
                action="ORDER_ADDRESS_UPDATED", target_type="order", target_id=int(order_id),
                detail=address_context,
            )
            db.commit()
        except RevisionError as rev:
            db.rollback()
            return jsonify({'success': False, 'message': str(rev), 'code': rev.error_code}), rev.status_code

        resp = jsonify({
            'success': True,
            'address': new_address,
            'conversion_status': 'pending',
            'latitude': None,
            'longitude': None,
            'geocode_queued': True,
            'mutation_receipt': outcome.read_receipt_id,
        })
        for header, hvalue in outcome.headers.items():
            resp.headers[header] = hvalue
        return resp

    except Exception as e:
        db.rollback()
        current_app.logger.error(
            "update_address error for order_id=%s: %s",
            order_id,
            e,
            exc_info=True,
        )
        return jsonify({'success': False, 'message': str(e)}), 500
