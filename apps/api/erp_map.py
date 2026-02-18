"""
ERP 지도·주소·유저 API. (Phase 4-4)
erp.py에서 분리: map_data, erp users 목록, generate_map, update_address.
"""
import datetime

from flask import Blueprint, request, jsonify
from sqlalchemy import or_, and_, func, String

from db import get_db
from models import Order, User
from apps.auth import login_required
from apps.erp import erp_edit_required, _normalize_for_search
from foms_address_converter import FOMSAddressConverter
from foms_map_generator import FOMSMapGenerator
from sqlalchemy.orm.attributes import flag_modified

erp_map_bp = Blueprint('erp_map', __name__)


@erp_map_bp.route('/api/map_data')
@login_required
def api_map_data():
    """지도 표시용 주문 데이터 API"""
    try:
        date_filter = request.args.get('date')
        status_filter = request.args.get('status')
        limit = int(request.args.get('limit', 100))

        db = get_db()
        query = db.query(Order).filter(Order.status != 'DELETED')

        query = query.filter(
            Order.is_regional != True,
            ~Order.status.in_(['SELF_MEASUREMENT', 'SELF_MEASURED'])
        )

        if status_filter and status_filter != 'ALL':
            query = query.filter(Order.status == status_filter)

        if date_filter:
            try:
                filter_date = datetime.datetime.strptime(date_filter, '%Y-%m-%d').date()
                date_start = filter_date - datetime.timedelta(days=30)
                date_end = filter_date + datetime.timedelta(days=30)
            except Exception:
                date_start = None
                date_end = None

            date_conditions = [
                Order.measurement_date == date_filter,
                Order.received_date == date_filter,
                Order.scheduled_date == date_filter,
                Order.completion_date == date_filter,
                Order.as_received_date == date_filter,
                Order.as_completed_date == date_filter
            ]

            if date_start and date_end:
                date_start_str = date_start.strftime('%Y-%m-%d')
                date_end_str = date_end.strftime('%Y-%m-%d')
                date_conditions.append(
                    and_(
                        Order.is_erp_beta == True,
                        func.cast(Order.received_date, String) >= date_start_str,
                        func.cast(Order.received_date, String) <= date_end_str
                    )
                )
            else:
                date_conditions.append(Order.is_erp_beta == True)

            query = query.filter(or_(*date_conditions))

        orders = query.order_by(Order.id.desc()).limit(limit * 5).all()

        if date_filter:
            filtered_orders = []
            for order in orders:
                should_include = False
                if order.is_erp_beta and order.structured_data:
                    sd = order.structured_data
                    erp_measurement_date = (((sd.get('schedule') or {}).get('measurement') or {}).get('date'))
                    if erp_measurement_date and str(erp_measurement_date) == date_filter:
                        should_include = True
                    elif order.measurement_date and str(order.measurement_date) == date_filter:
                        should_include = True
                else:
                    if order.measurement_date and str(order.measurement_date) == date_filter:
                        should_include = True

                if should_include:
                    filtered_orders.append(order)
            orders = filtered_orders[:limit]

        converter = FOMSAddressConverter()
        map_data = []
        for order in orders:
            customer_name = order.customer_name
            phone = order.phone
            address_to_use = order.address
            product = order.product

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

            lat, lng, status = converter.convert_address(address_to_use)
            if lat is not None and lng is not None:
                map_data.append({
                    'id': order.id,
                    'customer_name': customer_name,
                    'phone': phone,
                    'address': address_to_use,
                    'product': product,
                    'status': order.status,
                    'received_date': order.received_date,
                    'latitude': lat,
                    'longitude': lng,
                    'conversion_status': status
                })

        return jsonify({
            'success': True,
            'data': map_data,
            'total_orders': len(orders),
            'converted_orders': len(map_data)
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
        manager_filter = (request.args.get('manager') or '').strip()
        search_query = (request.args.get('q') or request.args.get('search') or '').strip()
        title = request.args.get('title', '주문 위치 지도')

        db = get_db()
        query = db.query(Order).filter(Order.status != 'DELETED')

        query = query.filter(
            Order.is_regional != True,
            ~Order.status.in_(['SELF_MEASUREMENT', 'SELF_MEASURED'])
        )

        if status_filter and status_filter != 'ALL':
            query = query.filter(Order.status == status_filter)

        if date_filter:
            try:
                filter_date = datetime.datetime.strptime(date_filter, '%Y-%m-%d').date()
                date_start = filter_date - datetime.timedelta(days=30)
                date_end = filter_date + datetime.timedelta(days=30)
            except Exception:
                date_start = None
                date_end = None

            date_conditions = [
                Order.measurement_date == date_filter,
                Order.received_date == date_filter,
                Order.scheduled_date == date_filter,
                Order.completion_date == date_filter,
                Order.as_received_date == date_filter,
                Order.as_completed_date == date_filter
            ]

            if date_start and date_end:
                date_start_str = date_start.strftime('%Y-%m-%d')
                date_end_str = date_end.strftime('%Y-%m-%d')
                date_conditions.append(
                    and_(
                        Order.is_erp_beta == True,
                        func.cast(Order.received_date, String) >= date_start_str,
                        func.cast(Order.received_date, String) <= date_end_str
                    )
                )
            else:
                date_conditions.append(Order.is_erp_beta == True)

            query = query.filter(or_(*date_conditions))

        orders = query.order_by(Order.id.desc()).limit(500).all()

        if date_filter:
            filtered_orders = []
            for order in orders:
                should_include = False
                if order.is_erp_beta and order.structured_data:
                    sd = order.structured_data
                    erp_measurement_date = (((sd.get('schedule') or {}).get('measurement') or {}).get('date'))
                    if erp_measurement_date and str(erp_measurement_date) == date_filter:
                        should_include = True
                    elif order.measurement_date and str(order.measurement_date) == date_filter:
                        should_include = True
                else:
                    if order.measurement_date and str(order.measurement_date) == date_filter:
                        should_include = True

                if should_include:
                    filtered_orders.append(order)
            orders = filtered_orders[:100]

        converter = FOMSAddressConverter()
        map_data = []
        orders_list = []

        for order in orders:
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

            if manager_filter:
                manager_name_str = str(manager_name or '')
                if manager_filter.lower() not in manager_name_str.lower():
                    continue

            if search_query:
                search_lower = _normalize_for_search(search_query).lower()
                searchable_parts = [
                    address_to_use,
                    order.address,
                    customer_name,
                    product,
                    order.notes,
                    manager_name,
                ]
                if order.is_erp_beta and order.structured_data:
                    sd = order.structured_data
                    site = sd.get('site') or {}
                    searchable_parts.extend([
                        site.get('address_full'),
                        site.get('address_main'),
                        site.get('address_detail'),
                        site.get('address_note'),
                    ])
                searchable = _normalize_for_search(' '.join(
                    str(p).strip() for p in searchable_parts if p
                )).lower()
                if not searchable or search_lower not in searchable:
                    continue

            lat, lng, status = converter.convert_address(address_to_use)

            def format_date(date_value):
                if date_value is None:
                    return None
                if isinstance(date_value, str):
                    return date_value
                if hasattr(date_value, 'strftime'):
                    return date_value.strftime('%Y-%m-%d')
                return str(date_value)

            order_list_item = {
                'id': order.id,
                'customer_name': customer_name,
                'phone': phone,
                'address': address_to_use,
                'product': product,
                'status': order.status,
                'received_date': format_date(order.received_date),
                'measurement_date': format_date(measurement_date),
                'scheduled_date': format_date(scheduled_date),
                'completion_date': format_date(order.completion_date),
                'manager_name': manager_name,
                'notes': order.notes or '-',
                'geocode_failed': lat is None or lng is None,
                'conversion_status': status if (lat is None or lng is None) else 'success'
            }
            orders_list.append(order_list_item)

            if lat is not None and lng is not None:
                map_data.append({
                    'id': order.id,
                    'customer_name': customer_name,
                    'phone': phone,
                    'address': address_to_use,
                    'product': product,
                    'status': order.status,
                    'received_date': order.received_date,
                    'latitude': lat,
                    'longitude': lng
                })

        map_generator = FOMSMapGenerator()

        if map_data:
            folium_map = map_generator.create_map(map_data, title)
            if folium_map:
                map_html = folium_map._repr_html_()
            else:
                map_html = '<div class="error-message">지도를 생성할 수 없습니다.</div>'

            return jsonify({
                'success': True,
                'map_html': map_html,
                'total_orders': len(map_data),
                'orders': orders_list
            })

        empty_map = map_generator.create_empty_map(title)
        if empty_map:
            map_html = empty_map._repr_html_()
            return jsonify({
                'success': True,
                'map_html': map_html,
                'total_orders': 0,
                'orders': [],
                'message': f'{title}에 해당하는 주문이 없습니다.'
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
        converter = FOMSAddressConverter()
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
        converter = FOMSAddressConverter()
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
        converter = FOMSAddressConverter()
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
        converter = FOMSAddressConverter()
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

        if order.is_erp_beta and order.structured_data:
            sd = order.structured_data or {}
            if 'site' not in sd:
                sd['site'] = {}
            sd['site']['address_full'] = new_address
            sd['site']['address_main'] = new_address
            order.structured_data = sd
            flag_modified(order, 'structured_data')
        else:
            order.address = new_address

        db.commit()

        converter = FOMSAddressConverter()
        lat, lng, status = converter.convert_address(new_address)

        return jsonify({
            'success': True,
            'latitude': lat,
            'longitude': lng,
            'address': new_address,
            'conversion_status': status,
            'geocode_failed': lat is None or lng is None
        })

    except Exception as e:
        import traceback
        print(f"ERROR: update_address 에러 발생: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500
