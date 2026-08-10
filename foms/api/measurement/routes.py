"""
HTTP routes for ERP 실측 API (`foms.api.measurement` package).
실측 대시보드 업데이트, 실측 동선 추천.
"""
import copy
import datetime
import hashlib
import json
import logging

logger = logging.getLogger(__name__)

from flask import Blueprint, g, request, jsonify
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from db import get_db
from models import Order, OrderEvent
from foms.web.auth import log_access, login_required, role_required
from foms.services.audit_message_display import describe_order_action, field_label
from foms.services.orders.audit_order_context import order_audit_context
import foms.api.measurement as measurement_api
from foms.services.erp_order_flags import is_erp_order_record
from foms.services.common.erp_mine_filter import erp_mine_only_from_request
from foms.services.erp_permissions import is_order_related_to_user
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.common.address_converter import FOMSAddressConverter
from foms.services.order_geocode import reset_order_geocode_on_address_change
from foms.services.order_geocode_outbox import enqueue_order_address_geocode
from foms.services.orders.revision import RevisionError, execute_order_mutation
from foms.services.measurement_dates import extract_all_measurement_dates
from foms.services.measurement_read_model import apply_measurement_dashboard_order_scope
from foms.services.measurement_route import build_measurement_route_payload
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
                'time': time_to_use,
                'is_regional': order.is_regional is True,
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
        count_regional = sum(1 for c in cases if c.get('is_regional'))
        count_metro = len(cases) - count_regional

        panel_dates.append({
            'date': date_str,
            'day_label': day_labels[current.weekday()],
            'count': len(cases),
            'count_regional': count_regional,
            'count_metro': count_metro,
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


#: 실측 대시보드에서 저장 가능한 typed projection 필드(generic field update 금지).
MEASUREMENT_UPDATE_FIELDS = frozenset({'manager', 'address', 'phone'})
MEASUREMENT_FIELD_EVENT = 'MEASUREMENT_FIELD_UPDATED'
MEASUREMENT_POLICY_ID = 'ERP_EDIT'


@erp_measurement_bp.route('/update/<int:order_id>', methods=['POST'])
@login_required
@measurement_api.erp_edit_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def api_erp_measurement_update(order_id):
    """실측 대시보드 필드 저장(manager/phone/address projection).

    generic field update 대신 **typed projection registry**(manager/phone/address)만
    허용하고, 저장은 REV-00 :func:`execute_order_mutation` 경유로 If-Match·version bump·
    receipt·OrderEvent 를 한 tx 에 원자화한다. 주소 변경 시 지오코드는 **SIDEFX outbox**
    (GEOCODE)로 예약한다 — postcommit 직접 지오코드/폴백은 하지 않는다.
    """
    db: Session = get_db()
    order = db.query(Order).filter(Order.id == order_id, Order.active_filter()).first()
    if not order:
        return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404
    if not is_erp_order_record(order):
        return jsonify({'success': False, 'message': 'ERP Order 주문만 수정할 수 있습니다.'}), 400

    payload = request.get_json(silent=True) or {}
    field = payload.get('field')
    if not field:
        return jsonify({'success': False, 'message': '필드명이 필요합니다.'}), 400
    if field not in MEASUREMENT_UPDATE_FIELDS:
        return jsonify({'success': False, 'message': f'지원하지 않는 필드: {field}'}), 400

    raw_value = payload.get('value', '')
    if isinstance(raw_value, dict):
        raw_value = raw_value.get('name', '')
    value = str(raw_value).strip()
    if field == 'manager':
        from foms.services.erp_display import clean_dict_like_name
        value = clean_dict_like_name(value)

    # optional If-Match(mutation_version) 낙관 잠금 — 형식 오류는 삼키지 않고 400.
    if_match_raw = (request.headers.get('If-Match') or '').strip().strip('"')
    expected_versions = None
    if if_match_raw:
        try:
            expected_versions = {order_id: int(if_match_raw)}
        except ValueError:
            return jsonify({'success': False, 'message': 'If-Match 형식이 올바르지 않습니다.'}), 400
    idempotency_key = (request.headers.get('Idempotency-Key') or '').strip() or None
    user_id = getattr(getattr(g, 'current_user', None), 'id', None)
    scope_hash = hashlib.sha256(f'{MEASUREMENT_POLICY_ID}:{order_id}'.encode()).hexdigest()
    request_hash = hashlib.sha256(
        json.dumps({'field': field, 'value': value}, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()

    def _mutate(sess: Session, orders):
        """row lock 아래에서 단일 typed 필드만 projection + event/geocode 예약(축 불변)."""
        o = orders[0]
        if field == 'address':
            # 주소·site·좌표 초기화(자체 flag_modified) → GEOCODE outbox 예약(no postcommit).
            reset_order_geocode_on_address_change(o, value)
            enqueue_order_address_geocode(sess, o, address=value, actor_user_id=user_id)
        else:
            sd = copy.deepcopy(o.structured_data or {})
            parties = sd.setdefault('parties', {})
            if field == 'manager':
                parties.setdefault('manager', {})['name'] = value
                o.manager_name = value
            else:  # phone
                parties.setdefault('customer', {})['phone'] = value
                o.phone = value
            o.structured_data = sd
            flag_modified(o, 'structured_data')
            sess.add(OrderEvent(
                order_id=o.id,
                event_type=MEASUREMENT_FIELD_EVENT,
                payload={'field': field},
                created_by_user_id=user_id,
            ))

        if isinstance(o.structured_data, dict):
            sync_erp_flat_columns(o, o.structured_data)
        o.structured_updated_at = datetime.datetime.now()
        return {o.id: [f'ORDER_DETAIL:{o.id}', 'ORDERS_INDEX', 'MEASUREMENT']}

    try:
        outcome = execute_order_mutation(
            db,
            actor_user_id=user_id,
            policy_id=MEASUREMENT_POLICY_ID,
            order_ids=[order_id],
            expected_versions=expected_versions,
            idempotency_key=idempotency_key,
            scope_hash=scope_hash,
            request_hash=request_hash,
            mutation=_mutate,
        )
        # 실측 typed 필드는 연락처·주소를 포함한다 — 값은 원장에 남기지 않고 "무엇을 고쳤는지"만
        # 남긴다(담당자만 예외: 사람 이름이라 PII 최소성 경계 안이다).
        audit_context = order_audit_context(order)
        log_access(
            describe_order_action(
                order_id=order_id, action="MEASUREMENT_UPDATED",
                note=field_label(field), **audit_context,
            ),
            user_id,
            auto_commit=False,
            action="MEASUREMENT_UPDATED", target_type="order", target_id=int(order_id),
            detail={"field": field,
                    **({"after": value} if field == "manager" else {}),
                    **audit_context},
        )
        db.commit()
    except RevisionError as rev:
        db.rollback()
        return jsonify({'success': False, 'message': str(rev), 'code': rev.error_code}), rev.status_code
    except Exception as e:  # noqa: BLE001 - 롤백 후 500
        db.rollback()
        logger.exception("[ERP_MEASUREMENT] 업데이트 오류: %s", e)
        return jsonify({'success': False, 'message': str(e)}), 500

    resp = jsonify({'success': True, 'mutation_receipt': outcome.read_receipt_id})
    for header, hvalue in outcome.headers.items():
        resp.headers[header] = hvalue
    return resp


@erp_measurement_bp.route('/route')
@login_required
def api_erp_measurement_route():
    """ERP 실측 동선 추천 (MVP).

    빌더는 `foms.services.measurement_route`(SSOT) — 실측 대시보드 뷰의
    서버 인라인(data-route-inline)과 동일 계보의 points 를 반환한다.
    '내 주문' 필터는 대시보드 뷰(foms.web.measurement.dashboard)와 동일 predicate,
    기본값(파라미터/쿠키 미설정)은 기존 동작 유지 — 필터 미적용.

    응답의 `route`는 예약 순서(측정 시각 오름차순) — 히어로/'다음 방문' SSOT.
    `optimized_route`/`optimized_total_distance_km`는 최근접 이웃으로 재배열한
    별도 동선(데스크톱 "경로 계획" 모달 전용, 근사 직선거리) — hero/next 판정에
    쓰지 말 것(ROUTE-01).
    """
    db = get_db()
    date_filter = request.args.get('date') or measurement_api.get_today_kst().strftime('%Y-%m-%d')
    manager_filter = (request.args.get('manager') or '').strip()
    limit = int(request.args.get('limit', 20))

    current_user = getattr(g, 'current_user', None)
    mine_filter_active = bool(erp_mine_only_from_request(request) and current_user)
    payload = build_measurement_route_payload(
        db,
        date_filter=date_filter,
        manager_filter=manager_filter,
        limit=limit,
        current_user=current_user,
        mine_active=mine_filter_active,
    )
    return jsonify({"success": True, **payload})


@erp_measurement_bp.route('/route-eta')
@login_required
def api_erp_measurement_route_eta():
    """현재 위치 → 대상 주문까지 카카오 실도로 거리·소요시간 (동선 스트립 캡션 장식용).

    파라미터
        order_id: 대상 주문 id (int, 필수)
        from_lat/from_lng: 현재 위치 좌표 (float, 필수)

    반환
        200 {success:true, data:{distance_km, duration_min}} — 카카오 성공
        200 {success:false, error} — 좌표 없음/카카오 실패 (장식 요소라 UX 차단 금지, 폴백)
        400 {success:false, error} — 파라미터 누락/범위 오류

    카카오 호출 실패는 logger.info로 남기되(에러 삼킴 금지) 200 폴백으로 응답한다.
    """
    order_id = request.args.get('order_id', type=int)
    from_lat = request.args.get('from_lat', type=float)
    from_lng = request.args.get('from_lng', type=float)
    if order_id is None or from_lat is None or from_lng is None:
        return jsonify({'success': False, 'error': '필수 파라미터 누락'}), 400
    if not (-90.0 <= from_lat <= 90.0) or not (-180.0 <= from_lng <= 180.0):
        return jsonify({'success': False, 'error': '좌표 범위 오류'}), 400

    db = get_db()
    order = db.query(Order).filter(Order.id == order_id).first()
    if order is None or order.lat is None or order.lng is None:
        return jsonify({'success': False, 'error': '대상 좌표 없음'})

    try:
        result = FOMSAddressConverter().calculate_route(
            from_lat, from_lng, float(order.lat), float(order.lng), timeout=5
        )
    except Exception as e:  # noqa: BLE001 — 장식용 폴백, 아래 logger.info로 기록
        logger.info('[ROUTE_ETA] 카카오 경로 계산 예외 order=%s: %s', order_id, e)
        return jsonify({'success': False, 'error': '경로 계산 실패'})

    if not result or result.get('status') != 'success':
        logger.info('[ROUTE_ETA] 카카오 응답 실패 order=%s: %s',
                    order_id, (result or {}).get('message'))
        return jsonify({'success': False, 'error': '경로 계산 실패'})

    return jsonify({
        'success': True,
        'data': {
            'distance_km': result.get('distance_km'),
            'duration_min': result.get('duration_min'),
        },
    })
