
from flask import Blueprint, jsonify, request, session, current_app
from apps.auth import login_required, role_required, log_access, get_user_by_id
from db import get_db
from services.erp_permissions import can_edit_erp
from models import Order, OrderEvent
from constants import STATUS, BULK_ACTION_STATUS
from sqlalchemy import or_, and_, func
from sqlalchemy.orm.attributes import flag_modified
import datetime
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from foms_address_converter import FOMSAddressConverter
from services.jobs.queue import enqueue_geocode_order_address

orders_bp = Blueprint('orders', __name__, url_prefix='/api')


def ensure_path(parent, key):
    if key not in parent or not isinstance(parent.get(key), dict):
        parent[key] = {}
    return parent[key]


def _schedule_date_has_on_or_after(d_date_str, ref_date):
    """시공일 문자열(단일 또는 CSV)에 ref_date 당일 또는 이후 날짜가 하나라도 있으면 True."""
    if not d_date_str or not ref_date:
        return False
    parts = [p.strip() for p in str(d_date_str).split(',') if p and p.strip()]
    return any(p >= ref_date for p in parts)


def _get_order_schedule_date(order, ref_date: str | None = None):
    """출고/시공 예정일 반환.

    ref_date 지정 시 그 날짜 이후(당일 포함)의 가장 빠른 날짜를 반환한다.
    AS 주문(AS_RECEIVED/AS_COMPLETED): scheduled_date(실제 시공 예정일)만 사용.
    ERP Beta 주문: structured_data.schedule.construction.date 우선.
    일반 주문: shipping_scheduled_date → scheduled_date 순.
    최종 fallback: OrderScheduleDate 관계 (construction/shipping kind).
    """
    if not order:
        return None

    def _valid(d):
        """날짜 문자열이 유효하고 ref_date 이후인지 확인."""
        s = str(d).strip() if d else ''
        return s if s and (not ref_date or s >= ref_date) else None

    status = getattr(order, 'status', None)
    if status in ('AS_RECEIVED', 'AS_COMPLETED'):
        return _valid(getattr(order, 'scheduled_date', None))

    sd = getattr(order, 'structured_data', None)
    if getattr(order, 'is_erp_beta', False) and isinstance(sd, dict):
        cons_date = ((sd.get('schedule') or {}).get('construction') or {}).get('date')
        if d := _valid(cons_date):
            return d

    for attr in ('shipping_scheduled_date', 'scheduled_date'):
        if d := _valid(getattr(order, attr, None)):
            return d

    # 최종 fallback: OrderScheduleDate 관계 (ref_date 이후 가장 빠른 날짜)
    sched_dates = getattr(order, 'schedule_dates', None)
    if sched_dates:
        dates = sorted([
            sd.date for sd in sched_dates
            if sd.kind in ('construction', 'shipping') and _valid(sd.date)
        ])
        if dates:
            return dates[0]
    return None


def _get_order_display_address(order):
    """표시용 주소 (structured_data site 우선, 없으면 order.address)."""
    if not order:
        return ''
    sd = getattr(order, 'structured_data', None)
    if isinstance(sd, dict):
        site = (sd.get('site') or {})
        address_full = site.get('address_full')
        address_main = site.get('address_main')
        address_detail = site.get('address_detail')
        if address_full:
            return str(address_full).strip()
        if address_main:
            detail = (address_detail or '').strip()
            return f"{address_main.strip()} {detail}".strip() if detail else address_main.strip()
    addr = getattr(order, 'address', None)
    return (addr or '').strip()


def _get_order_display_customer_name(order):
    """표시용 고객명 (structured_data parties.customer.name 우선, 없으면 order.customer_name)."""
    if not order:
        return ''
    sd = getattr(order, 'structured_data', None)
    if isinstance(sd, dict):
        name = ((sd.get('parties') or {}).get('customer') or {}).get('name')
        if name and str(name).strip():
            return str(name).strip()
    cn = getattr(order, 'customer_name', None)
    return (cn or '').strip()


_SEARCH_RADII_KM = [1.0, 3.0, 5.0, 10.0, 20.0, 30.0]
_MAX_RESULTS = 5
_GEOCODE_WORKERS = 10


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """두 좌표 간 Haversine 직선거리(km) 반환."""
    R = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = math.sin(d_lat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lng / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def _build_candidate_item(order, ref_date: str | None = None) -> dict:
    """주문 ORM 객체를 nearby 결과 아이템 dict로 변환."""
    order_addr = _get_order_display_address(order)
    d_date = _get_order_schedule_date(order, ref_date)
    _shipping = getattr(order, 'shipping_scheduled_date', None)
    _status = getattr(order, 'status', None) or ''
    return {
        'id': order.id,
        'customer_name': _get_order_display_customer_name(order),
        'address': order_addr,
        'date': d_date,
        'type': '상차' if _shipping else '시공',
        'status': STATUS.get(_status, _status),
    }


@orders_bp.route('/orders/nearby')
@login_required
def api_orders_nearby():
    """AS 대시보드용: 주소 기반 가까운 출고/시공 일정 찾기.

    카카오 Geocoding API로 좌표를 변환한 뒤, 직선거리 기반 점진적 반경
    (1 → 3 → 5 → 10 → 20 → 30 km)으로 후보를 수집하고 상위 5건을 반환합니다.
    30km에서도 미달 시 거리 무관 가장 가까운 순 Top 5 반환.
    카카오 API 장애 시 텍스트 유사도 기반 fallback을 사용합니다.
    """
    target_address = request.args.get('address', '').strip()
    if not target_address:
        return jsonify({'success': False, 'error': '주소가 필요합니다.'}), 400

    exclude_id = request.args.get('exclude_id', type=int)
    # KST(Asia/Seoul) 기준 오늘 날짜 사용 — Railway 서버는 UTC이므로 반드시 명시
    try:
        from zoneinfo import ZoneInfo
        _kst_today = datetime.datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y-%m-%d')
    except Exception:
        _kst_today = (datetime.datetime.utcnow() + datetime.timedelta(hours=9)).strftime('%Y-%m-%d')
    ref_date = request.args.get('date', _kst_today)

    db = get_db()

    from sqlalchemy.orm import load_only, selectinload
    from models import OrderScheduleDate

    # 1. 오늘 이후 실제 시공/출고 예정일이 있는 주문만 조회 (전국 대상 — 지역 사전 필터 없음)
    # 지역 사전 필터를 걸면 인접 시/도 주문을 놓치므로, 날짜 필터만 적용 후
    # Haversine 거리 계산으로 가장 가까운 Top5를 순수하게 찾는다.
    query = (
        db.query(Order)
        .options(
            load_only(
                Order.id, Order.address, Order.status, Order.shipping_scheduled_date,
                Order.scheduled_date, Order.is_erp_beta, Order.structured_data, Order.customer_name
            ),
            selectinload(Order.schedule_dates),
        )
        .outerjoin(OrderScheduleDate, Order.id == OrderScheduleDate.order_id)
        .filter(
            Order.status != 'DELETED',
            or_(
                Order.shipping_scheduled_date >= ref_date,
                Order.scheduled_date >= ref_date,
                and_(
                    OrderScheduleDate.id.isnot(None),
                    OrderScheduleDate.date >= ref_date,
                ),
                # ERP Beta: 시공일이 structured_data.schedule.construction.date 에만 있는 경우
                and_(
                    Order.is_erp_beta == True,
                    func.jsonb_extract_path_text(
                        Order.structured_data, 'schedule', 'construction', 'date'
                    ) >= ref_date,
                ),
            ),
        )
        .distinct()
    )

    if exclude_id:
        query = query.filter(Order.id != exclude_id)

    candidates = query.order_by(Order.id.desc()).limit(2500).all()

    # 2. 날짜 유효성 재검증 + 아이템 변환
    valid_items = []
    for order in candidates:
        order_addr = _get_order_display_address(order)
        if not order_addr:
            continue
        d_date = _get_order_schedule_date(order, ref_date)
        if not d_date:
            continue
        valid_items.append(_build_candidate_item(order, ref_date))

    # 3. 카카오 API: 좌표 기반 점진적 반경 검색
    try:
        converter = FOMSAddressConverter()
        start_lat, start_lng, _, _ = converter.analyze_address(target_address)

        if not start_lat or not start_lng:
            raise ValueError("기준 주소 좌표 변환 실패")

        # 3-1. 전체 후보 좌표 병렬 변환
        def geocode_item(item: dict):
            lat, lng, _, _ = converter.analyze_address(item['address'])
            return item, lat, lng

        geo_results: list[tuple[dict, float | None, float | None]] = []
        with ThreadPoolExecutor(max_workers=min(_GEOCODE_WORKERS, len(valid_items) or 1)) as ex:
            futures = {ex.submit(geocode_item, item): item for item in valid_items}
            for fut in as_completed(futures):
                try:
                    geo_results.append(fut.result())
                except Exception as geo_err:
                    current_app.logger.warning("[NEARBY] 좌표 변환 실패: %s", geo_err)
                    geo_results.append((futures[fut], None, None))

        # 직선거리 계산 (좌표 성공한 것만)
        with_distance = []
        for item, lat, lng in geo_results:
            if lat and lng:
                item['_dist_km'] = _haversine_km(start_lat, start_lng, lat, lng)
                item['_lat'] = lat
                item['_lng'] = lng
                with_distance.append(item)

        # 3-2. 전체 후보를 날짜 1순위 → 거리 2순위로 정렬 후 Top 5 선택
        # 반경으로 먼저 자르면 날짜가 빠른 주문이 반경 밖에 있을 때 누락되므로
        # 반경 정보는 UI 표시용으로만 사용한다.
        final_candidates = sorted(
            with_distance,
            key=lambda x: (x.get('date') or '9999-99-99', x['_dist_km'])
        )[:_MAX_RESULTS]

        # UI 표시용 반경: 선택된 5건 중 가장 먼 거리
        used_radius = max((c['_dist_km'] for c in final_candidates), default=_SEARCH_RADII_KM[-1])

        # 3-4. 최종 5건에만 카카오 경로(실소요시간) 계산
        def route_item(item: dict):
            route_info = converter.calculate_route(start_lat, start_lng, item['_lat'], item['_lng'])
            if route_info.get('status') == 'success':
                item['distance_km'] = route_info['distance_km']
                item['duration_min'] = route_info['duration_min']
                item['score_text'] = f"{route_info['distance_km']}km ({route_info['duration_min']}분)"
            else:
                item['score_text'] = f"약 {item['_dist_km']:.1f}km"
            # 내부 좌표 필드 제거 (응답 불필요)
            item.pop('_dist_km', None)
            item.pop('_lat', None)
            item.pop('_lng', None)
            return item

        final_results = []
        with ThreadPoolExecutor(max_workers=min(_MAX_RESULTS, len(final_candidates) or 1)) as ex_r:
            route_futures = [ex_r.submit(route_item, item) for item in final_candidates]
            for fut in as_completed(route_futures):
                try:
                    final_results.append(fut.result())
                except Exception as route_err:
                    current_app.logger.warning("[NEARBY] 경로 계산 실패: %s", route_err)

        # 경로 계산 후 시공일 오름차순 재정렬 (동일 날짜 시 소요시간 보조)
        final_results.sort(key=lambda x: (x.get('date') or '9999-99-99', x.get('duration_min', 9999)))

        return jsonify({
            'success': True,
            'results': final_results,
            'count': len(final_results),
            'search_radius_km': used_radius,
        })

    except Exception as e:
        current_app.logger.warning("[NEARBY] 카카오 API 오류, fallback 사용: %s", e, exc_info=True)

    # Fallback: 텍스트 유사도 기반 상위 5건
    target_tokens = set(target_address.split())
    for item in valid_items:
        order_tokens = set(item['address'].split())
        item['_score'] = len(target_tokens & order_tokens)
        item['score_text'] = ''
    valid_items.sort(key=lambda x: (-x.get('_score', 0), x.get('date') or '9999-99-99'))
    fallback_results = valid_items[:_MAX_RESULTS]
    for item in fallback_results:
        item.pop('_score', None)

    return jsonify({
        'success': True,
        'results': fallback_results,
        'count': len(fallback_results),
        'search_radius_km': None,
    })


@orders_bp.route('/orders')
@login_required
def api_orders():
    """캘린더/FullCalendar용 주문 이벤트 목록 API"""
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    status_filter = request.args.get('status', None)
    limit_raw = request.args.get('limit', '2000')

    db = get_db()
    
    # 캘린더 응답 최소화를 위해 아주 무거운 필드(원문, 지도 좌표계 등)는 제외
    # selectinload(Order.schedule_dates)를 추가해 속도 향상(필요시)
    from sqlalchemy.orm import defer
    from models import OrderScheduleDate
    
    query = db.query(Order).filter(Order.status != 'DELETED').options(
        defer(Order.raw_order_text),
        defer(Order.regional_memo),
        defer(Order.address_hash),
        defer(Order.lat),
        defer(Order.lng),
        defer(Order.geocode_status),
        defer(Order.options), # options와 notes는 일단 그대로 두었음 (UI 클릭 모달에서 필요)
    )

    if status_filter and status_filter in STATUS:
        if status_filter == 'RECEIVED':
            query = query.filter(Order.status.in_(['RECEIVED', 'ON_HOLD']))
        else:
            query = query.filter(Order.status == status_filter)

    if start_date and end_date:
        if 'T' in str(start_date):
            start_date_only = str(start_date).split('T')[0]
            end_date_only = str(end_date).split('T')[0]
        else:
            start_date_only, end_date_only = start_date, end_date
            
        # 정확한 날짜 범위 검색을 위해 OrderScheduleDate 테이블과 JOIN
        query = query.outerjoin(OrderScheduleDate, Order.id == OrderScheduleDate.order_id)
        query = query.filter(
            or_(
                # 기본 주문 테이블의 날짜 (between)
                Order.received_date.between(start_date_only, end_date_only),
                Order.as_received_date.between(start_date_only, end_date_only),
                Order.as_completed_date.between(start_date_only, end_date_only),
                Order.completion_date.between(start_date_only, end_date_only),
                # OrderScheduleDate를 통한 측정일/시공일 검색 (between)
                and_(
                    OrderScheduleDate.id.isnot(None),
                    OrderScheduleDate.date.between(start_date_only, end_date_only)
                )
            )
        )
        # 중복 제거
        query = query.distinct()

    try:
        limit = int(limit_raw)
    except (TypeError, ValueError):
        limit = 2000
    limit = max(100, min(limit, 5000))

    orders = query.order_by(Order.id.desc()).limit(limit).all()

    status_colors = {
        'RECEIVED': '#3788d8', 'MEASURED': '#f39c12', 'SCHEDULED': '#e74c3c',
        'SHIPPED_PENDING': '#ff6b35', 'COMPLETED': '#2ecc71',
        'AS_RECEIVED': '#9b59b6', 'AS_COMPLETED': '#1abc9c'
    }

    events = []
    for order in orders:
        customer_name = getattr(order, 'customer_name', None) or ''
        phone = getattr(order, 'phone', None) or ''
        address = getattr(order, 'address', None) or ''
        product = getattr(order, 'product', None) or ''
        measurement_date = getattr(order, 'measurement_date', None)
        measurement_time = getattr(order, 'measurement_time', None)
        scheduled_date = getattr(order, 'scheduled_date', None)

        sd = getattr(order, 'structured_data', None)
        if getattr(order, 'is_erp_beta', False) and isinstance(sd, dict):
            erp_customer_name = ((sd.get('parties') or {}).get('customer') or {}).get('name')
            if erp_customer_name:
                customer_name = erp_customer_name
            erp_phone = ((sd.get('parties') or {}).get('customer') or {}).get('phone')
            if erp_phone:
                phone = erp_phone
            erp_address = ((sd.get('site') or {}).get('address_full') or (sd.get('site') or {}).get('address_main'))
            if erp_address:
                address = erp_address
            items = sd.get('items') or []
            if items:
                first_item = items[0]
                product_name = first_item.get('product_name') or first_item.get('name')
                if product_name:
                    product = f"{product_name} 외 {len(items) - 1}개" if len(items) > 1 else product_name
            erp_measurement_date = (((sd.get('schedule') or {}).get('measurement') or {}).get('date'))
            if erp_measurement_date:
                measurement_date = erp_measurement_date
            erp_measurement_time = (((sd.get('schedule') or {}).get('measurement') or {}).get('time'))
            if erp_measurement_time:
                measurement_time = erp_measurement_time
            erp_scheduled_date = (((sd.get('schedule') or {}).get('construction') or {}).get('date'))
            if erp_scheduled_date:
                scheduled_date = erp_scheduled_date

        _is_beta = getattr(order, 'is_erp_beta', False)
        if _is_beta and measurement_date:
            start_date_val = measurement_date
        else:
            _status = getattr(order, 'status', None) or ''
            status_date_map = {
                'RECEIVED': getattr(order, 'received_date', None), 'MEASURED': measurement_date,
                'SCHEDULED': scheduled_date, 'SHIPPED_PENDING': scheduled_date,
                'COMPLETED': getattr(order, 'completion_date', None),
                'AS_RECEIVED': getattr(order, 'as_received_date', None), 'AS_COMPLETED': getattr(order, 'as_completed_date', None)
            }
            start_date_val = status_date_map.get(_status)

        if not start_date_val:
            continue

        start_dates_list = [s.strip() for s in str(start_date_val).split(',') if s.strip() and len(s.strip()) == 10]
        if not start_dates_list:
            start_dates_list = [str(start_date_val).strip()] if str(start_date_val).strip() else []

        _status = getattr(order, 'status', None) or ''
        status_time_map = {
            'RECEIVED': getattr(order, 'received_time', None), 'MEASURED': measurement_time,
            'SCHEDULED': None, 'SHIPPED_PENDING': None, 'COMPLETED': None,
            'AS_RECEIVED': None, 'AS_COMPLETED': None
        }
        time_str = status_time_map.get(_status)

        color = status_colors.get(_status, '#3788d8')
        title = f"{customer_name} | {phone} | {product}"
        ext = {
            'customer_name': customer_name, 'phone': phone, 'address': address,
            'product': product, 'options': getattr(order, 'options', None), 'notes': getattr(order, 'notes', None),
            'status': _status, 'received_date': getattr(order, 'received_date', None),
            'received_time': getattr(order, 'received_time', None),
            'measurement_date': measurement_date, 'measurement_time': measurement_time,
            'completion_date': getattr(order, 'completion_date', None), 'scheduled_date': scheduled_date,
            'as_received_date': getattr(order, 'as_received_date', None), 'as_completed_date': getattr(order, 'as_completed_date', None),
            'manager_name': getattr(order, 'manager_name', None)
        }

        for idx, one_date in enumerate(start_dates_list):
            if _status == 'MEASURED' and measurement_time in ['종일', '오전', '오후']:
                start_datetime = one_date
                all_day = True
            elif time_str:
                start_datetime = f"{one_date}T{time_str}:00"
                all_day = False
            else:
                start_datetime = one_date
                all_day = True
            events.append({
                'id': f"{order.id}-{idx}-{one_date}" if len(start_dates_list) > 1 else order.id,
                'title': title,
                'start': start_datetime,
                'allDay': all_day,
                'backgroundColor': color,
                'borderColor': color,
                'extendedProps': ext
            })

    return jsonify(events)


@orders_bp.route('/update_regional_status', methods=['POST'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def update_regional_status():
    """지방 주문 및 자가실측 체크리스트 상태 업데이트"""
    db = get_db()
    data = request.get_json()
    
    order_id = data.get('order_id')
    field = data.get('field')
    value = data.get('value')

    order = db.query(Order).filter_by(id=order_id).first()

    _regional = getattr(order, 'is_regional', False)
    _self_meas = getattr(order, 'is_self_measurement', False)
    if not order or (not _regional and not _self_meas):
        return jsonify({'success': False, 'message': '유효하지 않은 주문입니다.'}), 404

    # 업데이트 가능한 필드인지 확인 (보안 목적)
    allowed_fields = [
        'measurement_completed',
        'regional_sales_order_upload',
        'regional_blueprint_sent',
        'regional_order_upload',
        'regional_cargo_sent',
        'regional_construction_info_sent'
    ]
    if field not in allowed_fields:
        return jsonify({'success': False, 'message': '허용되지 않은 필드입니다.'}), 400

    try:
        setattr(order, field, value)
        db.commit()
        order_type = "자가실측" if _self_meas else "지방 주문"
        log_access(f"{order_type} #{order.id}의 '{field}' 상태를 '{value}'(으)로 변경", session['user_id'])
        return jsonify({'success': True, 'message': '상태가 업데이트되었습니다.'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': f'오류 발생: {str(e)}'}), 500

@orders_bp.route('/update_regional_memo', methods=['POST'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def update_regional_memo():
    """지방 주문 메모 업데이트"""
    db = get_db()
    data = request.get_json()
    
    order_id = data.get('order_id')
    memo = data.get('memo', '')

    order = db.query(Order).filter_by(id=order_id).first()

    _regional = getattr(order, 'is_regional', False)
    _self_meas = getattr(order, 'is_self_measurement', False)
    if not order or (not _regional and not _self_meas):
        return jsonify({'success': False, 'message': '유효하지 않은 주문입니다.'}), 404

    try:
        order.regional_memo = memo
        db.commit()
        order_type = "자가실측" if _self_meas else "지방 주문"
        log_access(f"{order_type} #{order.id}의 메모를 업데이트", session['user_id'])
        return jsonify({'success': True, 'message': '메모가 저장되었습니다.'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': f'오류 발생: {str(e)}'}), 500

@orders_bp.route('/update_order_field', methods=['POST'])
@login_required
def update_order_field():
    """주문 필드 업데이트 (수도권 및 지방 대시보드용). 실측일/시공일은 can_edit_erp 권한으로도 허용."""
    db = get_db()
    data = request.get_json()
    
    order_id = data.get('order_id')
    # 두 가지 파라미터명 지원: field/value (수도권), field_name/new_value (지방)
    field = data.get('field') or data.get('field_name')
    value = data.get('value') or data.get('new_value')

    order = db.query(Order).filter_by(id=order_id).first()

    if not order:
        return jsonify({'success': False, 'message': '유효하지 않은 주문입니다.'}), 404

    # 권한: 실측일/시공일은 can_edit_erp, 그 외는 ADMIN/MANAGER/STAFF
    user = get_user_by_id(session.get('user_id')) if session.get('user_id') else None
    if not user:
        return jsonify({'success': False, 'message': '로그인이 필요합니다.'}), 401
    _date_fields = ('measurement_date', 'scheduled_date')
    if field in _date_fields:
        if not can_edit_erp(user):
            return jsonify({'success': False, 'message': '실측일/시공일 수정 권한이 없습니다. (영업, 라홈, 하우드, CS팀만 가능)'}), 403
    else:
        if user.role not in ('ADMIN', 'MANAGER', 'STAFF'):
            return jsonify({'success': False, 'message': '이 작업을 수행할 권한이 없습니다.'}), 403

    # 업데이트 가능한 필드인지 확인 (보안 목적)
    allowed_fields = [
        'manager_name', 'scheduled_date', 'status',  # 기존 필드들
        'shipping_scheduled_date', 'completion_date',  # 지방 대시보드 날짜 필드들
        'measurement_completed', 'regional_sales_order_upload',  # 지방 체크박스 필드들
        'regional_blueprint_sent', 'regional_order_upload',
        'regional_cargo_sent', 'regional_construction_info_sent',
        'as_received_date', 'as_completed_date',  # AS 관련 날짜 필드들
        'as_visit_date', 'as_content', 'as_pending',  # AS 방문일·내용·미결 플래그
        'measurement_date',  # 실측일 필드
        'regional_memo',  # 메모 필드 허용 (수납장 대시보드 등)
        'is_cabinet', 'cabinet_status',  # 수납장 관련
        'shipping_fee'  # 배송비 필드 (수납장 대시보드용)
    ]
    if field not in allowed_fields:
        return jsonify({'success': False, 'message': f'허용되지 않은 필드입니다: {field}'}), 400

    try:
        old_value = getattr(order, field, None)
        if field == 'as_visit_date':
            order.scheduled_date = value
        elif field == 'as_content' or field == 'as_pending':
            # as_content, as_pending는 모델 필드가 아니므로 건너뜀 (structured_data에서 처리)
            pass
        else:
            setattr(order, field, value)

        # AS 완료일 입력 시 ERP 프로세스 AS 처리 카테고리 > 완료로 처리 (기존/Beta 동일), 미결 해제
        if field == 'as_completed_date' and value:
            setattr(order, 'status', 'AS_COMPLETED')
            if getattr(order, 'is_erp_beta', False):
                sd = getattr(order, 'structured_data', None) or {}
                if isinstance(sd, dict):
                    wf = sd.get('workflow') or {}
                    wf = dict(wf)
                    wf['stage'] = 'AS_COMPLETED'
                    wf['stage_updated_at'] = datetime.datetime.now().isoformat()
                    sd['workflow'] = wf
                    setattr(order, 'structured_data', sd)
                    flag_modified(order, 'structured_data')
            sd = getattr(order, 'structured_data', None) or {}
            if isinstance(sd, dict):
                shipment = sd.get('shipment')
                if isinstance(shipment, dict) and shipment.get('as_pending'):
                    shipment['as_pending'] = False
                    setattr(order, 'structured_data', sd)
                    flag_modified(order, 'structured_data')

        # ERP Beta 주문이거나 structured_data 연동이 필요한 필드(as_content, as_pending 등)인 경우
        _is_beta = getattr(order, 'is_erp_beta', False)
        if _is_beta or field == 'as_content' or field == 'as_visit_date' or field == 'as_pending':
            # structured_data가 None이면 빈 딕셔너리로 초기화 (JSONB 필드 대응)
            sd = getattr(order, 'structured_data', None)
            if sd is None:
                setattr(order, 'structured_data', {})
                sd = {}
            elif not isinstance(sd, dict):
                sd = {}

            if field == 'as_pending':
                shipment = ensure_path(sd, 'shipment')
                shipment['as_pending'] = str(value).lower() in ('1', 'true', 'yes')
                setattr(order, 'structured_data', sd)
                flag_modified(order, 'structured_data')
            elif field == 'manager_name':
                parties = ensure_path(sd, 'parties')
                manager = ensure_path(parties, 'manager')
                manager['name'] = value
                flag_modified(order, 'structured_data')
            elif field == 'measurement_date':
                schedule = ensure_path(sd, 'schedule')
                measurement = ensure_path(schedule, 'measurement')
                measurement['date'] = value
                flag_modified(order, 'structured_data')
            elif field == 'scheduled_date':
                schedule = ensure_path(sd, 'schedule')
                construction = ensure_path(schedule, 'construction')
                construction['date'] = value
                flag_modified(order, 'structured_data')
            elif field == 'customer_name':
                parties = ensure_path(sd, 'parties')
                customer = ensure_path(parties, 'customer')
                customer['name'] = value
                flag_modified(order, 'structured_data')
            elif field == 'phone':
                parties = ensure_path(sd, 'parties')
                customer = ensure_path(parties, 'customer')
                customer['phone'] = value
                flag_modified(order, 'structured_data')
            elif field == 'address':
                site = ensure_path(sd, 'site')
                site['address_full'] = value
                flag_modified(order, 'structured_data')
            elif field == 'as_visit_date':
                # as_visit_date는 scheduled_date 필드와 동기화
                schedule = ensure_path(sd, 'schedule')
                construction = ensure_path(schedule, 'construction')
                construction['date'] = value
                order.scheduled_date = value
                flag_modified(order, 'structured_data')
            elif field == 'as_content':
                # as_content는 structured_data.shipment.as_content에 저장
                shipment = ensure_path(sd, 'shipment')
                shipment['as_content'] = value
                flag_modified(order, 'structured_data')

        db.commit()

        if field == 'address':
            enqueue_geocode_order_address(order_id)
        
        # 상태 변경 시 특별한 로깅 (AS 접수로 바꿀 때도 scheduled_date/as_visit_date 자동 입력하지 않음)
        if field == 'status':
            log_access(f"자가실측 주문 #{order.id} 상태 변경: '{old_value}' → '{value}'", session['user_id'])
        else:
            log_access(f"주문 #{order.id}의 '{field}' 필드를 '{value}'(으)로 변경", session['user_id'])
        
        return jsonify({'success': True, 'message': '정보가 업데이트되었습니다.'})
    except Exception as e:
        db.rollback()
        current_app.logger.error(f"주문 #{order_id} 필드 업데이트 실패: {str(e)}")
        return jsonify({'success': False, 'message': f'오류 발생: {str(e)}'}), 500

@orders_bp.route('/update_order_status', methods=['POST'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def update_order_status():
    """수도권 대시보드에서 주문 상태 직접 변경"""
    db = get_db()  # Define outside try block for proper error handling
    try:
        data = request.get_json()
        order_id = data.get('order_id')
        new_status = data.get('status')
        
        if not order_id or not new_status:
            return jsonify({'success': False, 'message': '필수 파라미터가 누락되었습니다.'}), 400
        
        # 유효한 상태인지 확인
        if new_status not in STATUS:
            return jsonify({'success': False, 'message': '유효하지 않은 상태입니다.'}), 400
        
        order = db.query(Order).filter(Order.id == order_id).first()
        
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404
        
        old_status_val: str = getattr(order, 'status', None) or ''
        order.status = new_status

        # AS 접수 상태로 변경 시 접수일이 없으면 오늘 날짜 자동 설정
        if new_status == 'AS_RECEIVED' and not getattr(order, 'as_received_date', None):
            setattr(order, 'as_received_date', datetime.date.today().strftime('%Y-%m-%d'))

        db.commit()
        
        # 로그 기록
        user_id = session.get('user_id')
        old_status_name = STATUS.get(old_status_val, old_status_val)
        new_status_name = STATUS.get(new_status, new_status)
        log_access(f"주문 #{order_id} 상태 변경: {old_status_name} → {new_status_name}", user_id)
        
        return jsonify({
            'success': True,
            'old_status': old_status_val,
            'new_status': new_status,
            'status_display': STATUS.get(new_status, new_status)
        })
        
    except Exception as e:
        db.rollback()
        current_app.logger.error(f"주문 상태 업데이트 실패: {str(e)}")
        return jsonify({'success': False, 'message': f'오류 발생: {str(e)}'}), 500


@orders_bp.route('/bulk_update_order_status', methods=['POST'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def bulk_update_order_status():
    """작업 큐에서 다중 선택한 주문의 상태를 한 번에 변경. ERP Beta는 structured_data.workflow.stage 동기화."""
    try:
        data = request.get_json()
        order_ids = data.get('order_ids')
        new_status = (data.get('status') or '').strip()

        if not order_ids or not isinstance(order_ids, list):
            return jsonify({'success': False, 'message': 'order_ids(배열)가 필요합니다.'}), 400
        if not new_status:
            return jsonify({'success': False, 'message': 'status가 필요합니다.'}), 400
        is_delete = new_status == 'DELETED'
        if not is_delete and new_status not in BULK_ACTION_STATUS:
            return jsonify({'success': False, 'message': '유효한 status가 필요합니다.'}), 400

        db = get_db()
        user_id = session.get('user_id')
        updated = 0
        deleted_at_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        valid_ids = []
        for oid in order_ids:
            try:
                valid_ids.append(int(oid))
            except (TypeError, ValueError):
                continue
                
        if not valid_ids:
            return jsonify({'success': False, 'message': '유효한 주문 ID가 없습니다.'}), 400

        orders = db.query(Order).filter(Order.id.in_(valid_ids)).all()
        
        for order in orders:
            old_status_val = getattr(order, 'status', None) or ''
            if is_delete:
                setattr(order, 'status', 'DELETED')
                setattr(order, 'original_status', old_status_val or 'RECEIVED')
                setattr(order, 'deleted_at', deleted_at_str)
                log_access(f"주문 #{order.id} 휴지통 이동 (bulk): {old_status_val} → DELETED", user_id)
                updated += 1
                continue
            setattr(order, 'status', new_status)
            # AS 접수 상태로 변경 시 접수일이 없으면 오늘 날짜 자동 설정
            if new_status == 'AS_RECEIVED' and not getattr(order, 'as_received_date', None):
                today_str = datetime.datetime.now().strftime('%Y-%m-%d')
                setattr(order, 'as_received_date', today_str)
            sd_raw = getattr(order, 'structured_data', None)
            if getattr(order, 'is_erp_beta', False) and sd_raw:
                from models import OrderEvent  # Assuming this exists based on context
                sd = sd_raw
                if not isinstance(sd, dict):
                    continue
                wf = sd.get('workflow') or {}
                old_stage = (wf.get('stage') or '').strip()
                if new_status in STATUS:
                    wf = dict(wf)
                    wf['stage'] = new_status
                    wf['stage_updated_at'] = datetime.datetime.now().isoformat()
                    sd['workflow'] = wf
                    setattr(order, 'structured_data', sd)
                    flag_modified(order, 'structured_data')
                db.add(OrderEvent(
                    order_id=order.id,
                    event_type='STAGE_CHANGED',
                    payload={'from': old_stage, 'to': new_status, 'manual': True, 'bulk': True},
                    created_by_user_id=user_id
                ))
            log_access(f"주문 #{order.id} 상태 변경: {old_status_val} → {new_status}", user_id)
            updated += 1
        db.commit()
        return jsonify({
            'success': True,
            'updated': updated,
            'new_status': new_status,
            'status_display': STATUS.get(new_status, new_status)
        })
    except Exception as e:
        db = get_db()
        if db:
            db.rollback()
        current_app.logger.error(f"bulk_update_order_status 실패: {str(e)}")
        return jsonify({'success': False, 'message': f'오류 발생: {str(e)}'}), 500
