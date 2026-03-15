"""
ERP 지도·주소·유저 API. (Phase 4-4)
erp.py에서 분리: map_data, erp users 목록, generate_map, update_address.
"""
import copy
import datetime
import os
import threading


from flask import Blueprint, request, jsonify, render_template
from sqlalchemy import or_, and_

from db import get_db
from models import Order, User
from apps.auth import login_required
from services.erp_permissions import erp_edit_required
from apps.erp import _normalize_for_search
from foms_address_converter import FOMSAddressConverter
from foms_map_generator import FOMSMapGenerator
from services.jobs.queue import enqueue_geocode_order_address
from services.order_geocode import reset_order_geocode_on_address_change
from services.map_snapshot import build_measurement_map_query, build_measurement_snapshot

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

    # 자가실측·지방실측 제외(진짜 실측 필요한 것만)
    if dashboard == 'measurement':
        query = query.filter(
            or_(
                and_(
                    Order.is_regional != True,
                    ~Order.status.in_(['SELF_MEASUREMENT', 'SELF_MEASURED'])
                ),
                Order.is_self_measurement == True
            )
        )
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
        query = query.distinct()

    orders = query.order_by(Order.id.desc()).limit(limit).all()

    if dashboard == 'measurement':
        from services.erp_display import self_measurement_four_checks_done
        orders = [o for o in orders if not self_measurement_four_checks_done(o)]

    return orders


def _extract_map_order_display(order):
    customer_name = order.customer_name
    phone = order.phone
    address_to_use = order.address
    product = order.product
    measurement_date = order.measurement_date
    scheduled_date = order.scheduled_date
    manager_name = order.manager_name or '-'

    if order.is_erp_beta and order.structured_data:
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

        erp_scheduled_date = (((sd.get('schedule') or {}).get('construction') or {}).get('date'))
        if erp_scheduled_date:
            scheduled_date = erp_scheduled_date

        erp_manager_name = ((sd.get('parties') or {}).get('manager') or {}).get('name')
        if erp_manager_name:
            manager_name = erp_manager_name

    return {
        'customer_name': customer_name,
        'phone': phone,
        'address': address_to_use,
        'product': product,
        'measurement_date': measurement_date,
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
    if order.is_erp_beta and order.structured_data:
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
    from services.geocode_helpers import extract_address_from_order

    map_data = []
    orders_list = []
    skipped_no_coords = 0
    to_geocode = []

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
            geocode_failed = False
            geocode_status = 'success'
        else:
            geocode_failed = True
            skipped_no_coords += 1
            address_for_geocode = extract_address_from_order(order)
            if (
                enqueue_missing
                and address_for_geocode
                and address_for_geocode.strip()
                and address_for_geocode.strip() != '-'
                and not stored_geocode_status
            ):
                geocode_status = 'pending'
                to_geocode.append(order)
            else:
                geocode_status = stored_geocode_status or 'failed'

        orders_list.append({
            'id': order.id,
            'customer_name': display['customer_name'],
            'phone': display['phone'],
            'address': display['address'],
            'product': display['product'],
            'status': order.status,
            'received_date': _format_map_date(order.received_date),
            'measurement_date': _format_map_date(display['measurement_date']),
            'scheduled_date': _format_map_date(display['scheduled_date']),
            'completion_date': _format_map_date(order.completion_date),
            'manager_name': display['manager_name'],
            'notes': order.notes or '-',
            'geocode_failed': geocode_failed,
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
    """지도 보기 페이지"""
    return render_template('map_view.html')


@erp_map_bp.route('/api/map_data')
@login_required
def api_map_data():
    """지도 표시용 주문 데이터 API"""
    try:
        date_filter = request.args.get('date')
        status_filter = request.args.get('status')
        dashboard = request.args.get('dashboard')
        manager_filter = (request.args.get('manager') or '').strip()
        search_query = (request.args.get('q') or request.args.get('search') or '').strip()
        limit = _resolve_map_limit(
            request.args.get('limit'),
            default_limit=500 if dashboard == 'measurement' else 200
        )
        scan_limit = _MAP_SCAN_MAX_LIMIT if date_filter else min(_MAP_SCAN_MAX_LIMIT, max(limit, limit * 3))

        # measurement 모드: map_snapshot 사용, 전체 주문 반환 (2026-03-15)
        if dashboard == 'measurement' and date_filter:
            db = get_db()
            query = build_measurement_map_query(
                db, date_filter, search_query, manager_filter, dashboard, limit
            )
            orders = query.all()
            from services.erp_display import self_measurement_four_checks_done
            orders = [o for o in orders if not self_measurement_four_checks_done(o)]
            snapshot = build_measurement_snapshot(orders, manager_filter)
            return jsonify({
                'success': True,
                'orders': snapshot['orders'],
                'markers': snapshot['markers'],
                'summary': snapshot['summary'],
                'data': snapshot['markers'],
            })

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
            enqueue_missing=False,
            result_limit=limit,
        )

        return jsonify({
            'success': True,
            'data': payload['map_data'],
            'orders': payload['orders'],
            'total_orders': len(payload['orders']),
            'converted_orders': len(payload['map_data']),
            'skipped_no_coords': payload['skipped_no_coords'],
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
        date_filter = request.args.get('date')
        status_filter = request.args.get('status')
        dashboard = request.args.get('dashboard')
        manager_filter = (request.args.get('manager') or '').strip()
        search_query = (request.args.get('q') or request.args.get('search') or '').strip()
        title = request.args.get('title', '주문 위치 지도')
        limit = _resolve_map_limit(
            request.args.get('limit'),
            default_limit=500 if dashboard == 'measurement' else 200
        )
        scan_limit = _MAP_SCAN_MAX_LIMIT if date_filter else min(_MAP_SCAN_MAX_LIMIT, max(limit, limit * 3))

        # measurement 모드: shared query builder 사용 (2026-03-15)
        if dashboard == 'measurement' and date_filter:
            db = get_db()
            query = build_measurement_map_query(
                db, date_filter, search_query, manager_filter, dashboard, limit
            )
            orders = query.all()
            from services.erp_display import self_measurement_four_checks_done
            orders = [o for o in orders if not self_measurement_four_checks_done(o)]

            to_geocode = []
            from services.geocode_helpers import extract_address_from_order
            for order in orders:
                lat = getattr(order, 'lat', None)
                lng = getattr(order, 'lng', None)
                if lat is None or lng is None:
                    addr = extract_address_from_order(order)
                    if addr and addr.strip() and addr.strip() != '-':
                        if getattr(order, 'geocode_status', None) != 'pending':
                            order.geocode_status = 'pending'
                            to_geocode.append((order, addr.strip()))
            for order, _ in to_geocode:
                enqueue_geocode_order_address(order.id)
            if to_geocode:
                db.commit()

            snapshot = build_measurement_snapshot(orders, manager_filter)
            map_generator = FOMSMapGenerator()
            map_data = snapshot['markers']
            orders_list = snapshot['orders']

            if map_data:
                folium_map = map_generator.create_map(map_data, title)
                map_html = folium_map._repr_html_() if folium_map else '<div class="error-message">지도를 생성할 수 없습니다.</div>'
                return jsonify({
                    'success': True,
                    'map_html': map_html,
                    'total_orders': len(orders_list),
                    'orders': orders_list,
                    'snapshot': snapshot,
                })
            empty_map = map_generator.create_empty_map(title)
            map_html = empty_map._repr_html_() if empty_map else ''
            return jsonify({
                'success': True,
                'map_html': map_html,
                'total_orders': len(orders_list),
                'orders': orders_list,
                'snapshot': snapshot,
                'message': f'{title} 지도에 표시할 마커가 없습니다. 우측 목록에서 주소 오류를 확인하세요.' if orders_list else f'{title}에 해당하는 주문이 없습니다.'
            })

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

        queued_orders = []
        used_sync_fallback = False
        for order in payload['to_geocode']:
            queued = enqueue_geocode_order_address(order.id)
            if queued:
                order.geocode_status = 'pending'
                queued_orders.append(order)
            else:
                from services.jobs.tasks import geocode_order_address
                try:
                    geocode_order_address(order.id)
                    used_sync_fallback = True
                except Exception as e:
                    print(f"Fallback geocode error: {e}")
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
                result_limit=limit,
            )

        map_generator = FOMSMapGenerator()

        if payload['map_data']:
            folium_map = map_generator.create_map(payload['map_data'], title)
            if folium_map:
                map_html = folium_map._repr_html_()
            else:
                map_html = '<div class="error-message">지도를 생성할 수 없습니다.</div>'

            return jsonify({
                'success': True,
                'map_html': map_html,
                'total_orders': len(payload['orders']),
                'converted_orders': len(payload['map_data']),
                'skipped_no_coords': payload['skipped_no_coords'],
                'orders': payload['orders'],
            })

        empty_map = map_generator.create_empty_map(title)
        if empty_map:
            map_html = empty_map._repr_html_()
            return jsonify({
                'success': True,
                'map_html': map_html,
                'total_orders': len(payload['orders']),
                'converted_orders': 0,
                'skipped_no_coords': payload['skipped_no_coords'],
                'orders': payload['orders'],
                'message': f'{title} 지도에 표시할 마커가 없습니다. 우측 목록에서 주소 오류를 확인하세요.' if payload['orders'] else f'{title}에 해당하는 주문이 없습니다.'
            })

        return jsonify({'success': False, 'error': '지도를 생성할 수 없습니다.'})

    except Exception as e:
        import traceback
        print(f"ERROR: generate_map 에러 발생: {e}")
        print(traceback.format_exc())
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
    """주소 학습 데이터 추가 API"""
    try:
        data = request.get_json()
        original_address = data.get('original_address')
        corrected_address = data.get('corrected_address')
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        if not all([original_address, corrected_address, latitude, longitude]):
            return jsonify({'success': False, 'error': '모든 필드가 필요합니다.'}), 400
        converter = _get_address_converter()
        converter.add_learning_data(original_address, corrected_address, latitude, longitude)
        return jsonify({'success': True, 'message': '학습 데이터가 추가되었습니다.'})
    except Exception as e:
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


@erp_map_bp.route('/api/orders/<int:order_id>/update_address', methods=['POST'])
@login_required
@erp_edit_required
def api_update_order_address(order_id):
    """주문 주소를 수정하고 재-지오코딩"""
    try:
        data = request.get_json()
        new_address = (data.get('address') or '').strip()

        if not new_address:
            return jsonify({'success': False, 'message': '주소를 입력해주세요.'}), 400

        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()

        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        reset_order_geocode_on_address_change(order, new_address)
        db.commit()

        queued = enqueue_geocode_order_address(order_id)
        if not queued:
            # RQ worker 미사용(개발환경 등) 시 즉각 동기처리(Fallback)
            from services.jobs.tasks import geocode_order_address
            try:
                geocode_order_address(order_id)
            except Exception as e:
                print(f"Fallback geocode error: {e}")

            # geocode_order_address가 db_session.remove() 호출로 세션을 정리하므로
            # refresh 대신 재조회로 최신 lat/lng 반영 (Root Cause Fix)
            order = db.query(Order).filter(Order.id == order_id).first()
            return jsonify({
                'success': True,
                'address': new_address,
                'conversion_status': order.geocode_status or 'failed',
                'latitude': order.lat,
                'longitude': order.lng,
                'geocode_queued': False,
            })

        # queue 경로: 항상 동일한 응답 계약 (2026-03-15)
        return jsonify({
            'success': True,
            'address': new_address,
            'conversion_status': 'pending',
            'latitude': None,
            'longitude': None,
            'geocode_queued': True,
        })

    except Exception as e:
        import traceback
        print(f"ERROR: update_address 에러 발생: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500
