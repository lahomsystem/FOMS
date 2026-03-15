"""
ERP 실측 API. (Phase 4-3)
erp.py에서 분리: 실측 대시보드 업데이트, 실측 동선 추천.
"""
import copy
import datetime
import math

from flask import Blueprint, request, jsonify, session
from sqlalchemy import or_, and_, cast, String
from sqlalchemy.orm.attributes import flag_modified

from db import get_db
from models import Order
from apps.auth import login_required, role_required, get_user_by_id
from services.erp_permissions import erp_edit_required
from services.erp_display import get_today_kst, self_measurement_four_checks_done
from services.erp_shipment_settings import is_order_mine_for_user
from foms_address_converter import FOMSAddressConverter
from services.jobs.queue import enqueue_geocode_order_address
from services.order_geocode import reset_order_geocode_on_address_change

# 실측 패널 집계용: erp_measurement_dashboard 로직 재사용
from apps.erp_measurement_dashboard import extract_all_measurement_dates, _load_holidays_for_year

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
    대시보드와 건수 일치를 위해 base_query + mine 필터 동일 적용.
    """
    db = get_db()
    today_kst = get_today_kst()
    range_start = today_kst
    range_end = today_kst + datetime.timedelta(days=14)

    base_query = db.query(Order).filter(Order.active_filter())
    base_query = base_query.filter(
        or_(
            and_(
                Order.is_regional != True,
                ~Order.status.in_(['SELF_MEASUREMENT', 'SELF_MEASURED'])
            ),
            Order.is_self_measurement == True
        )
    )

    current_user = get_user_by_id(session.get('user_id')) if session.get('user_id') else None
    mine_filter_active = request.args.get('mine') == '1' and current_user

    from sqlalchemy.orm import selectinload
    panel_orders = base_query.options(selectinload(Order.schedule_dates)).order_by(Order.id.desc()).limit(1500).all()
    if mine_filter_active:
        panel_orders = [o for o in panel_orders if is_order_mine_for_user(o, current_user)]

    years = {range_start.year, range_end.year}
    holiday_dates = set()
    for y in years:
        holiday_dates |= _load_holidays_for_year(y)

    measurement_counts = {}
    for order in panel_orders:
        if self_measurement_four_checks_done(order):
            continue
        all_dates = extract_all_measurement_dates(order)
        for date_value in all_dates:
            try:
                d = datetime.datetime.strptime(date_value, '%Y-%m-%d').date()
            except Exception:
                continue
            if d < range_start or d > range_end:
                continue
            key = d.strftime('%Y-%m-%d')
            measurement_counts[key] = measurement_counts.get(key, 0) + 1

    day_labels = ['월', '화', '수', '목', '금', '토', '일']
    today_str = today_kst.strftime('%Y-%m-%d')
    panel_dates = []
    current = range_start
    while current <= range_end:
        date_str = current.strftime('%Y-%m-%d')
        is_weekend = current.weekday() >= 5
        is_holiday = date_str in holiday_dates
        panel_dates.append({
            'date': date_str,
            'day_label': day_labels[current.weekday()],
            'count': measurement_counts.get(date_str, 0),
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
@erp_edit_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def api_erp_measurement_update(order_id):
    """실측 대시보드 업데이트"""
    try:
        db = get_db()
        order = db.query(Order).filter(Order.id == order_id, Order.active_filter()).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        if not order.is_erp_beta:
            return jsonify({'success': False, 'message': 'ERP Beta 주문만 수정할 수 있습니다.'}), 400

        payload = request.get_json(silent=True) or {}
        field = payload.get('field')
        value = payload.get('value', '').strip()

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
        order.structured_updated_at = datetime.datetime.now()
        if field != 'address':
            flag_modified(order, 'structured_data')

        db.commit()

        if field == 'address':
            queued = enqueue_geocode_order_address(order_id)
            if not queued:
                from services.jobs.tasks import geocode_order_address
                geocode_order_address(order_id)

        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        import traceback
        print(f"[ERP_MEASUREMENT] 업데이트 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_measurement_bp.route('/route')
@login_required
def api_erp_measurement_route():
    """ERP 실측 동선 추천 (MVP)"""
    db = get_db()
    date_filter = request.args.get('date') or get_today_kst().strftime('%Y-%m-%d')
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
        query = query.filter(Order.manager_name.ilike(f'%{manager_filter}%'))

    orders = query.order_by(Order.measurement_time.asc().nullslast(), Order.id.asc()).limit(limit).all()

    converter = FOMSAddressConverter()
    points = []
    for o in orders:
        address_to_use = o.address
        customer_name = o.customer_name
        phone = o.phone

        if o.is_erp_beta and o.structured_data:
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

        lat, lng, status = converter.convert_address(address_to_use)
        if lat is None or lng is None:
            continue
        points.append({
            "id": o.id,
            "customer_name": customer_name,
            "phone": phone,
            "address": address_to_use,
            "measurement_time": o.measurement_time,
            "manager_name": o.manager_name,
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
