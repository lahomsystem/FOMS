"""
ERP 실측 API. (Phase 4-3)
erp.py에서 분리: 실측 대시보드 업데이트, 실측 동선 추천.
"""
import datetime
import math

from flask import Blueprint, request, jsonify
from sqlalchemy import or_
from sqlalchemy.orm.attributes import flag_modified

from db import get_db
from models import Order
from apps.auth import login_required, role_required
from apps.erp import erp_edit_required
from foms_address_converter import FOMSAddressConverter

erp_measurement_bp = Blueprint(
    'erp_measurement',
    __name__,
    url_prefix='/api/erp/measurement',
)


@erp_measurement_bp.route('/update/<int:order_id>', methods=['POST'])
@login_required
@erp_edit_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def api_erp_measurement_update(order_id):
    """실측 대시보드 업데이트"""
    try:
        db = get_db()
        order = db.query(Order).filter(Order.id == order_id, Order.status != 'DELETED').first()
        if not order:
            return jsonify({'success': False, 'error': '주문을 찾을 수 없습니다.'}), 404

        if not order.is_erp_beta:
            return jsonify({'success': False, 'error': 'ERP Beta 주문만 수정할 수 있습니다.'}), 400

        payload = request.get_json(silent=True) or {}
        field = payload.get('field')
        value = payload.get('value', '').strip()

        if not field:
            return jsonify({'success': False, 'error': '필드명이 필요합니다.'}), 400

        structured_data = order.structured_data or {}

        if field == 'manager':
            if 'parties' not in structured_data:
                structured_data['parties'] = {}
            if 'manager' not in structured_data['parties']:
                structured_data['parties']['manager'] = {}
            structured_data['parties']['manager']['name'] = value
            order.manager_name = value

        elif field == 'address':
            if 'site' not in structured_data:
                structured_data['site'] = {}
            structured_data['site']['address_full'] = value
            parts = value.split(' ', 1)
            if len(parts) >= 2:
                structured_data['site']['address_main'] = parts[0]
                structured_data['site']['address_detail'] = parts[1]
            else:
                structured_data['site']['address_main'] = value
                structured_data['site']['address_detail'] = ''
            order.address = value

        elif field == 'phone':
            if 'parties' not in structured_data:
                structured_data['parties'] = {}
            if 'customer' not in structured_data['parties']:
                structured_data['parties']['customer'] = {}
            structured_data['parties']['customer']['phone'] = value
            order.phone = value

        else:
            return jsonify({'success': False, 'error': f'지원하지 않는 필드: {field}'}), 400

        order.structured_data = structured_data
        order.structured_updated_at = datetime.datetime.now()

        flag_modified(order, 'structured_data')

        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        import traceback
        print(f"[ERP_MEASUREMENT] 업데이트 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500


@erp_measurement_bp.route('/route')
@login_required
def api_erp_measurement_route():
    """ERP 실측 동선 추천 (MVP)"""
    db = get_db()
    date_filter = request.args.get('date') or datetime.datetime.now().strftime('%Y-%m-%d')
    manager_filter = (request.args.get('manager') or '').strip()
    limit = int(request.args.get('limit', 20))
    limit = max(1, min(limit, 30))

    query = db.query(Order).filter(Order.status != 'DELETED')

    if date_filter:
        date_conditions = [Order.measurement_date == date_filter]
        query = query.filter(or_(*date_conditions))

    if manager_filter:
        query = query.filter(Order.manager_name.ilike(f'%{manager_filter}%'))

    all_orders = query.order_by(Order.measurement_time.asc().nullslast(), Order.id.asc()).limit(limit * 2).all()

    orders = []
    for order in all_orders:
        if date_filter:
            if order.is_erp_beta and order.structured_data:
                sd = order.structured_data
                erp_measurement_date = (((sd.get('schedule') or {}).get('measurement') or {}).get('date'))
                if (erp_measurement_date and str(erp_measurement_date) == date_filter) or \
                   (order.measurement_date and str(order.measurement_date) == date_filter):
                    orders.append(order)
            else:
                if order.measurement_date and str(order.measurement_date) == date_filter:
                    orders.append(order)
        else:
            orders.append(order)

    orders = orders[:limit]

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
