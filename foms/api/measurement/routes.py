"""
HTTP routes for ERP 실측 API (`foms.api.measurement` package).
실측 대시보드 업데이트, 실측 동선 추천.
"""
import copy
import datetime
import logging
import math

logger = logging.getLogger(__name__)

from flask import Blueprint, g, request, jsonify
from sqlalchemy import or_, and_, cast, String
from sqlalchemy.orm.attributes import flag_modified

from db import get_db
from models import Order
from foms.web.auth import login_required, role_required
import foms.api.measurement as measurement_api
from foms.services.erp_order_flags import is_erp_order_record
from foms.services.common.erp_mine_filter import erp_mine_only_from_request
from foms.services.erp_permissions import is_order_related_to_user
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.common.address_converter import FOMSAddressConverter
from foms.services.order_geocode import reset_order_geocode_on_address_change
from foms.services.measurement_dates import extract_all_measurement_dates
from foms.services.measurement_read_model import apply_measurement_dashboard_order_scope
from foms.services.common.business_calendar import get_holidays_kr


def normalize_address_for_sort(address):
    if not address or not str(address).strip():
        return ""
    addr = str(address).strip()
    replacements = {
        "서울특별시": "서울", "서울시": "서울",
        "경기도": "경기",
        "인천광역시": "인천", "인천시": "인천",
        "부산광역시": "부산", "부산시": "부산",
        "대구광역시": "대구", "대구시": "대구",
        "대전광역시": "대전", "대전시": "대전",
        "광주광역시": "광주", "광주시": "광주",
        "울산광역시": "울산", "울산시": "울산",
        "제주특별자치도": "제주", "제주시": "제주",
        "세종특별자치시": "세종", "세종시": "세종",
        "강원특별자치도": "강원", "강원도": "강원",
        "충청북도": "충북", "충청남도": "충남",
        "전라북도": "전북", "전라남도": "전남",
        "경상북도": "경북", "경상남도": "경남"
    }
    parts = addr.split(' ', 2)
    if parts and parts[0] in replacements:
        parts[0] = replacements[parts[0]]
    return " ".join(parts)

erp_measurement_bp = Blueprint(
    'erp_measurement',
    __name__,
    url_prefix='/api/erp/measurement',
)


@erp_measurement_bp.route('/summary')
@login_required
def api_erp_measurement_summary():
    """
    ERP Beta 실측 일정 미러링 패널용: 오늘~향후 14일 날짜별 실측 건수 JSON.
    Legacy summary contract를 유지하기 위해 `active_filter()` 기반 주문 집합과
    multi-source 실측일 추출(`extract_all_measurement_dates`)을 그대로 사용한다.
    화면 본문의 recent-only `dashboard_active_filter(days=60)`와는 범위가 다를 수 있다.
    """
    db = get_db()
    today_kst = measurement_api.get_today_kst()
    range_start = today_kst
    range_end = today_kst + datetime.timedelta(days=14)

    base_query = db.query(Order).filter(Order.active_filter())
    base_query = apply_measurement_dashboard_order_scope(base_query)

    current_user = getattr(g, 'current_user', None)
    mine_filter_active = erp_mine_only_from_request(request) and current_user

    from sqlalchemy.orm import selectinload
    panel_orders = base_query.options(selectinload(Order.schedule_dates)).order_by(Order.id.desc()).limit(1500).all()
    if mine_filter_active:
        panel_orders = [
            o for o in panel_orders
            if is_order_related_to_user(o, current_user)
        ]

    years = {range_start.year, range_end.year}
    holiday_dates = set()
    for y in years:
        holiday_dates |= get_holidays_kr(y)

    measurement_info = {}
    for order in panel_orders:
        if measurement_api.self_measurement_four_checks_done(order):
            continue
        all_dates = extract_all_measurement_dates(order)

        # ERP Beta 주소 및 고객명 추출
        address_to_use = order.address
        customer_name = order.customer_name
        time_to_use = order.measurement_time or ''

        if order.is_erp_order and order.structured_data:
            sd = order.structured_data
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

            erp_customer_name = ((sd.get('parties') or {}).get('customer') or {}).get('name')
            if erp_customer_name:
                customer_name = erp_customer_name

            erp_time = ((sd.get('schedule') or {}).get('measurement') or {}).get('time')
            if erp_time:
                time_to_use = erp_time

        for date_value in all_dates:
            try:
                d = datetime.datetime.strptime(date_value, '%Y-%m-%d').date()
            except Exception:
                continue
            if d < range_start or d > range_end:
                continue
            key = d.strftime('%Y-%m-%d')
            if key not in measurement_info:
                measurement_info[key] = []

            measurement_info[key].append({
                'id': order.id,
                'customer_name': customer_name or '이름없음',
                'address': address_to_use or '-',
                'time': time_to_use
            })

    day_labels = ['월', '화', '수', '목', '금', '토', '일']
    today_str = today_kst.strftime('%Y-%m-%d')
    panel_dates = []
    current = range_start
    while current <= range_end:
        date_str = current.strftime('%Y-%m-%d')
        is_weekend = current.weekday() >= 5
        is_holiday = date_str in holiday_dates
        cases = measurement_info.get(date_str, [])
        # 가까운 주소 끼리 정렬(시, 군, 구) 후 시간순 정렬
        cases.sort(key=lambda x: (normalize_address_for_sort(x.get('address')), str(x.get('time') or '')))

        panel_dates.append({
            'date': date_str,
            'day_label': day_labels[current.weekday()],
            'count': len(cases),
            'cases': cases,
            'is_weekend': is_weekend,
            'is_holiday': is_holiday,
            'is_today': date_str == today_str,
        })
        current += datetime.timedelta(days=1)

    return jsonify({
        'success': True,
        'panel_dates': panel_dates,
    })


@erp_measurement_bp.route('/update/<int:order_id>', methods=['POST'])
@login_required
@measurement_api.erp_edit_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def api_erp_measurement_update(order_id):
    """실측 대시보드 업데이트"""
    try:
        db = get_db()
        order = db.query(Order).filter(Order.id == order_id, Order.active_filter()).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        if not is_erp_order_record(order):
            return jsonify({'success': False, 'message': 'ERP Order 주문만 수정할 수 있습니다.'}), 400

        payload = request.get_json(silent=True) or {}
        field = payload.get('field')
        raw_value = payload.get('value', '')
        if isinstance(raw_value, dict):
            raw_value = raw_value.get('name', '')
        value = str(raw_value).strip()
        if field == 'manager':
            from foms.services.erp_display import clean_dict_like_name
            value = clean_dict_like_name(value)

        if not field:
            return jsonify({'success': False, 'message': '필드명이 필요합니다.'}), 400

        structured_data = copy.deepcopy(order.structured_data or {})

        if field == 'manager':
            if 'parties' not in structured_data:
                structured_data['parties'] = {}
            if 'manager' not in structured_data['parties']:
                structured_data['parties']['manager'] = {}
            structured_data['parties']['manager']['name'] = value
            order.manager_name = value

        elif field == 'address':
            reset_order_geocode_on_address_change(order, value)

        elif field == 'phone':
            if 'parties' not in structured_data:
                structured_data['parties'] = {}
            if 'customer' not in structured_data['parties']:
                structured_data['parties']['customer'] = {}
            structured_data['parties']['customer']['phone'] = value
            order.phone = value

        else:
            return jsonify({'success': False, 'message': f'지원하지 않는 필드: {field}'}), 400

        if field != 'address':
            order.structured_data = structured_data
            flag_modified(order, 'structured_data')

        if isinstance(order.structured_data, dict):
            sync_erp_flat_columns(order, order.structured_data)

        order.structured_updated_at = datetime.datetime.now()

        db.commit()

        if field == 'address':
            queued = measurement_api.enqueue_geocode_order_address(order_id)
            if not queued:
                from foms.services.jobs.tasks import geocode_order_address
                geocode_order_address(order_id)

        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        logger.exception("[ERP_MEASUREMENT] 업데이트 오류: %s", e)
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_measurement_bp.route('/route')
@login_required
def api_erp_measurement_route():
    """ERP 실측 동선 추천 (MVP)"""
    db = get_db()
    date_filter = request.args.get('date') or measurement_api.get_today_kst().strftime('%Y-%m-%d')
    manager_filter = (request.args.get('manager') or '').strip()
    limit = int(request.args.get('limit', 20))
    limit = max(1, min(limit, 30))

    query = db.query(Order).filter(Order.active_filter())

    if date_filter:
        from models import OrderScheduleDate
        query = query.join(OrderScheduleDate, Order.id == OrderScheduleDate.order_id)
        query = query.filter(
            OrderScheduleDate.kind == 'measurement',
            OrderScheduleDate.date == date_filter
        ).distinct()

    if manager_filter:
        query = query.filter(Order.manager_name.ilike(f'%{manager_filter}%'))  # perf-ok: ix_orders_manager_name_trgm

    ordered_query = query.order_by(
        Order.measurement_time.asc().nullslast(),
        Order.id.asc(),
    )
    if date_filter:
        candidate_orders = ordered_query.all()
        orders = [
            order
            for order in candidate_orders
            if date_filter in extract_all_measurement_dates(order)
        ][:limit]
    else:
        orders = ordered_query.limit(limit).all()

    converter = FOMSAddressConverter()
    points = []
    for o in orders:
        address_to_use = o.address
        customer_name = o.customer_name
        phone = o.phone
        manager_name = o.manager_name

        if o.is_erp_order and o.structured_data:
            sd = o.structured_data
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

            erp_customer_name = ((sd.get('parties') or {}).get('customer') or {}).get('name')
            if erp_customer_name:
                customer_name = erp_customer_name

            erp_phone = ((sd.get('parties') or {}).get('customer') or {}).get('phone')
            if erp_phone:
                phone = erp_phone

            erp_manager_name = ((sd.get('parties') or {}).get('manager') or {}).get('name')
            if erp_manager_name:
                manager_name = erp_manager_name

        lat, lng, status = converter.convert_address(address_to_use)
        if lat is None or lng is None:
            continue
        points.append({
            "id": o.id,
            "customer_name": customer_name,
            "phone": phone,
            "address": address_to_use,
            "measurement_time": o.measurement_time,
            "manager_name": manager_name,
            "status": o.status,
            "lat": float(lat),
            "lng": float(lng),
            "geo_status": status
        })

    if len(points) <= 1:
        return jsonify({
            "success": True,
            "date": date_filter,
            "manager": manager_filter,
            "total_points": len(points),
            "route": points,
            "total_distance_km": 0
        })

    def haversine_km(a, b):
        R = 6371.0
        lat1 = math.radians(a["lat"])
        lon1 = math.radians(a["lng"])
        lat2 = math.radians(b["lat"])
        lon2 = math.radians(b["lng"])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        return 2 * R * math.asin(math.sqrt(h))

    remaining = points[:]
    route = [remaining.pop(0)]
    total_km = 0.0

    while remaining:
        last = route[-1]
        best_i = 0
        best_d = float("inf")
        for i, cand in enumerate(remaining):
            d = haversine_km(last, cand)
            if d < best_d:
                best_d = d
                best_i = i
        next_pt = remaining.pop(best_i)
        total_km += best_d
        route.append(next_pt)

    km_h = 0.0
    for i in range(len(route) - 1):
        a = route[i]
        b = route[i + 1]
        d_h = haversine_km(a, b)
        km_h += d_h

    return jsonify({
        "success": True,
        "date": date_filter,
        "manager": manager_filter,
        "total_points": len(points),
        "route": route,
        "total_distance_km": round(km_h, 2)
    })
