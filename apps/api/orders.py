
from flask import Blueprint, jsonify, request, session, current_app
from apps.auth import login_required, role_required, log_access
from db import get_db
from models import Order
from constants import STATUS
from sqlalchemy import or_, and_, func
from sqlalchemy.orm.attributes import flag_modified
import traceback
import json
import datetime
from foms_address_converter import FOMSAddressConverter

orders_bp = Blueprint('orders', __name__, url_prefix='/api')


def ensure_path(parent, key):
    if key not in parent or not isinstance(parent.get(key), dict):
        parent[key] = {}
    return parent[key]


def _get_order_schedule_date(order):
    """출고/시공일 결정 (AS 대시보드·nearby 검색과 동일 로직). AS는 scheduled_date, as_received_date, as_completed_date. Beta는 structured_data schedule.construction.date 또는 scheduled_date."""
    if not order:
        return None
    status = getattr(order, 'status', None)
    if status in ('AS_RECEIVED', 'AS_COMPLETED'):
        v = getattr(order, 'scheduled_date', None)
        if v and str(v).strip():
            return str(v).strip()
        v = getattr(order, 'as_received_date', None)
        if v and str(v).strip():
            return str(v).strip()
        v = getattr(order, 'as_completed_date', None)
        if v and str(v).strip():
            return str(v).strip()
    sd = getattr(order, 'structured_data', None)
    if getattr(order, 'is_erp_beta', False) and isinstance(sd, dict):
        cons = (sd.get('schedule') or {}).get('construction') or {}
        cons_date = cons.get('date')
        if cons_date:
            return str(cons_date)
    v = getattr(order, 'shipping_scheduled_date', None)
    if v and str(v).strip():
        return str(v).strip()
    v = getattr(order, 'scheduled_date', None)
    if v and str(v).strip():
        return str(v).strip()
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


@orders_bp.route('/orders/nearby')
@login_required
def api_orders_nearby():
    """AS 대시보드용: 주소 기반 가까운 출고/시공 일정 찾기"""
    target_address = request.args.get('address', '').strip()
    if not target_address:
        return jsonify({'success': False, 'message': '주소가 필요합니다.'}), 400

    # 기준일: 오늘 (또는 파라미터)
    ref_date = request.args.get('date', datetime.datetime.now().strftime('%Y-%m-%d'))
    
    db = get_db()
    
    # 1. 대상 주문 조회 (오늘 이후 출고/시공 예정인 건).
    # - AS: scheduled_date, as_received_date, as_completed_date
    # - 일반/레거시: shipping_scheduled_date, scheduled_date
    # - ERP Beta: 시공일이 structured_data.schedule.construction.date 에만 있는 경우 포함
    candidates = db.query(Order).filter(
        Order.status != 'DELETED',
        or_(
            Order.shipping_scheduled_date >= ref_date,
            Order.scheduled_date >= ref_date,
            Order.as_received_date >= ref_date,
            Order.as_completed_date >= ref_date,
            and_(Order.is_erp_beta == True, Order.structured_data != None),
        )
    ).order_by(Order.id.desc()).limit(2500).all()

    # 2. 주소 유사도 점수 계산 (표시용 주소·실제 시공일 사용)
    target_tokens = set(target_address.split())
    scored_orders = []
    for order in candidates:
        order_addr = _get_order_display_address(order)
        if not order_addr:
            continue
        d_date = _get_order_schedule_date(order)
        if not d_date or d_date < ref_date:
            continue

        order_tokens = set(order_addr.split())
        score = len(target_tokens.intersection(order_tokens))
        if score > 0:
            _shipping = getattr(order, 'shipping_scheduled_date', None)
            _status = getattr(order, 'status', None) or ''
            scored_orders.append({
                'id': order.id,
                'customer_name': _get_order_display_customer_name(order),
                'address': order_addr,
                'date': d_date,
                'type': '상차' if _shipping else '시공',
                'status': STATUS.get(_status, _status),
                'score': score
            })

    # 3. 정렬: 점수 높은 순 -> 날짜 빠른 순
    scored_orders.sort(key=lambda x: (-x['score'], x['date']))
    
    # 4. 카카오 API를 활용한 실 거리 계산 (점진적 반경 확장)
    try:
        converter = FOMSAddressConverter()
        
        # 1. 기준 주소 분석
        start_lat, start_lng, _, target_region = converter.analyze_address(target_address)
        
        target_sido = ''
        target_sigungu = ''
        if target_region:
            target_sido = target_region.get('region_1depth_name', '')
            target_sigungu = target_region.get('region_2depth_name', '')
        
        # 2. 후보군 우선순위 분류
        # Group 1: 같은 시군구 (최우선)
        # Group 2: 같은 시도
        # Group 3: 인접 시도 (수도권 등)
        # Group 4: 나머지 (텍스트 유사도 기반)
        
        group1 = []
        group2 = []
        group3 = []
        group4 = []
        
        # 수도권 정의
        sudo_kwon = ['서울', '경기', '인천']
        is_target_sudo = any(x in target_sido for x in sudo_kwon)
        
        for order in candidates:
            order_addr = _get_order_display_address(order)
            if not order_addr:
                continue
            d_date = _get_order_schedule_date(order)
            if not d_date or d_date < ref_date:
                continue

            target_tokens = set(target_address.split())
            order_tokens = set(order_addr.split())
            score = len(target_tokens.intersection(order_tokens))

            _shipping = getattr(order, 'shipping_scheduled_date', None)
            _status = getattr(order, 'status', None) or ''
            item = {
                'id': order.id,
                'customer_name': _get_order_display_customer_name(order),
                'address': order_addr,
                'date': d_date,
                'type': '상차' if _shipping else '시공',
                'status': STATUS.get(_status, _status),
                'score': score
            }

            if target_sigungu and target_sigungu in order_addr:
                group1.append(item)
            elif target_sido and target_sido in order_addr:
                group2.append(item)
            elif is_target_sudo and any(x in order_addr for x in sudo_kwon):
                group3.append(item)
            else:
                if score > 0: # 최소한 단어 하나는 겹쳐야 함
                    group4.append(item)
        
        # 3. 후보군 병합 (최대 15개)
        # 각 그룹 내에서는 날짜 빠른 순 정렬
        group1.sort(key=lambda x: x['date'] or '9999-99-99')
        group2.sort(key=lambda x: x['date'] or '9999-99-99')
        group3.sort(key=lambda x: x['date'] or '9999-99-99')
        group4.sort(key=lambda x: (-x['score'], x['date'] or '9999-99-99'))
        
        final_candidates = (group1 + group2 + group3 + group4)[:15]
        
        if start_lat and start_lng and final_candidates:
            # 상위 후보에 대해 거리 계산 수행
            final_results = []
            
            for item in final_candidates:
                # 목적지 주소 좌표 변환
                end_lat, end_lng, _, _ = converter.analyze_address(item['address'])
                
                if end_lat and end_lng:
                    # 경로 계산 (거리/시간)
                    route_info = converter.calculate_route(start_lat, start_lng, end_lat, end_lng)
                    
                    if route_info.get('status') == 'success':
                        item['distance_km'] = route_info['distance_km']
                        item['duration_min'] = route_info['duration_min']
                        item['toll'] = route_info['toll']
                        item['geo_status'] = 'success'
                        
                        # 텍스트 매칭 점수는 참고용으로 남겨두고, 거리 정보를 우선 표시
                        item['score_text'] = f"{item['distance_km']}km ({item['duration_min']}분)"
                    else:
                        item['geo_status'] = 'route_failed'
                        item['score_text'] = f"경로 계산 실패 (텍스트 점수: {item['score']})"
                else:
                    item['geo_status'] = 'geocode_failed'
                    item['score_text'] = f"좌표 변환 실패 (텍스트 점수: {item['score']})"
                
                final_results.append(item)
            
            # 5. 재정렬: 거리 계산 성공한 항목 우선, 그 중 소요 시간 짧은 순
            # geo_status가 success인 것 우선, 그 다음 duration_min 오름차순
            final_results.sort(key=lambda x: (0 if x.get('geo_status') == 'success' else 1, x.get('duration_min', 9999)))
            
            return jsonify({
                'success': True,
                'results': final_results[:5],
                'count': len(final_results)
            })
            
    except Exception as e:
        print(f"[NEARBY] 거리 계산 오류: {e}")
        import traceback
        traceback.print_exc()
        # 오류 발생 시 기존 텍스트 매칭 결과 반환 (fallback)

    # Top 5 반환 (거리 계산 실패 또는 예외 발생 시)
    return jsonify({
        'success': True,
        'results': scored_orders[:5],
        'count': len(scored_orders)
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
    query = db.query(Order).filter(Order.status != 'DELETED')

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
        query = query.filter(
            or_(
                Order.received_date.between(start_date_only, end_date_only),
                Order.measurement_date.between(start_date_only, end_date_only)
            )
        )

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

        _status = getattr(order, 'status', None) or ''
        status_time_map = {
            'RECEIVED': getattr(order, 'received_time', None), 'MEASURED': measurement_time,
            'SCHEDULED': None, 'SHIPPED_PENDING': None, 'COMPLETED': None,
            'AS_RECEIVED': None, 'AS_COMPLETED': None
        }
        time_str = status_time_map.get(_status)

        if _status == 'MEASURED' and measurement_time in ['종일', '오전', '오후']:
            start_datetime = start_date_val
            all_day = True
        elif time_str:
            start_datetime = f"{start_date_val}T{time_str}:00"
            all_day = False
        else:
            start_datetime = start_date_val
            all_day = True

        color = status_colors.get(_status, '#3788d8')
        title = f"{customer_name} | {phone} | {product}"

        events.append({
            'id': order.id,
            'title': title,
            'start': start_datetime,
            'allDay': all_day,
            'backgroundColor': color,
            'borderColor': color,
            'extendedProps': {
                'customer_name': customer_name, 'phone': phone, 'address': address,
                'product': product, 'options': getattr(order, 'options', None), 'notes': getattr(order, 'notes', None),
                'status': _status, 'received_date': getattr(order, 'received_date', None),
                'received_time': getattr(order, 'received_time', None),
                'measurement_date': measurement_date, 'measurement_time': measurement_time,
                'completion_date': getattr(order, 'completion_date', None), 'scheduled_date': scheduled_date,
                'as_received_date': getattr(order, 'as_received_date', None), 'as_completed_date': getattr(order, 'as_completed_date', None),
                'manager_name': getattr(order, 'manager_name', None)
            }
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
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def update_order_field():
    """주문 필드 업데이트 (수도권 및 지방 대시보드용)"""
    db = get_db()
    data = request.get_json()
    
    order_id = data.get('order_id')
    # 두 가지 파라미터명 지원: field/value (수도권), field_name/new_value (지방)
    field = data.get('field') or data.get('field_name')
    value = data.get('value') or data.get('new_value')

    order = db.query(Order).filter_by(id=order_id).first()

    if not order:
        return jsonify({'success': False, 'message': '유효하지 않은 주문입니다.'}), 404

    # 업데이트 가능한 필드인지 확인 (보안 목적)
    allowed_fields = [
        'manager_name', 'scheduled_date', 'status',  # 기존 필드들
        'shipping_scheduled_date', 'completion_date',  # 지방 대시보드 날짜 필드들
        'measurement_completed', 'regional_sales_order_upload',  # 지방 체크박스 필드들
        'regional_blueprint_sent', 'regional_order_upload',
        'regional_cargo_sent', 'regional_construction_info_sent',
        'as_received_date', 'as_completed_date',  # AS 관련 날짜 필드들
        'as_visit_date', 'as_content', # AS 방문일 및 내용 (직접 입력용)
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
        elif field == 'as_content':
            # as_content는 모델 필드가 아니므로 건너뜀 (아래 structured_data 로직에서 처리)
            pass
        else:
            setattr(order, field, value)

        # ERP Beta 주문이거나 structured_data 연동이 필요한 필드(as_content 등)인 경우
        _is_beta = getattr(order, 'is_erp_beta', False)
        if _is_beta or field == 'as_content' or field == 'as_visit_date':
            # structured_data가 None이면 빈 딕셔너리로 초기화 (JSONB 필드 대응)
            sd = getattr(order, 'structured_data', None)
            if sd is None:
                setattr(order, 'structured_data', {})
                sd = {}
            elif not isinstance(sd, dict):
                sd = {}

            if field == 'manager_name':
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
        
        # 상태 변경 시 특별한 로깅
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
        
        # 상태 업데이트
        old_status_val: str = getattr(order, 'status', None) or ''
        order.status = new_status
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
