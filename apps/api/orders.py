from flask import Blueprint, jsonify, request, session, current_app
from apps.auth import login_required, role_required, log_access, get_user_by_id
from services.erp_sync_columns import sync_erp_flat_columns
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
from services.erp_display import get_today_kst
from services.as_content_safety import (
    load_structured_data_dict_or_raise,
    sanitize_as_content_html,
)

orders_bp = Blueprint('orders', __name__, url_prefix='/api')


def ensure_path(parent, key):
    if key not in parent or not isinstance(parent.get(key), dict):
        parent[key] = {}
    return parent[key]


def _coerce_bool_value(value):
    """JSON/폼 기반 boolean 값을 일관되게 해석."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in ('1', 'true', 'yes', 'y', 'on')


def _load_order_structured_data_for_update(order):
    """주문 structured_data를 무손실로 로드. 안전하지 않으면 저장 중단."""
    try:
        return load_structured_data_dict_or_raise(getattr(order, 'structured_data', None))
    except ValueError as exc:
        raise ValueError(
            f'structured_data를 안전하게 불러올 수 없어 저장을 중단했습니다: {exc}'
        ) from exc


def _build_order_update_response(order, field, fallback_value, structured_data=None):
    """프론트 동기화용 저장 결과 페이로드."""
    sd = structured_data if isinstance(structured_data, dict) else None
    shipment = (sd.get('shipment') or {}) if sd else {}
    schedule = (sd.get('schedule') or {}) if sd else {}
    as_visit = (schedule.get('as_visit') or {}) if isinstance(schedule, dict) else {}

    if field in ('as_content', 'as_content_2'):
        normalized_value = shipment.get(field) or ''
    elif field == 'as_pending':
        normalized_value = shipment.get('as_pending') is True
    elif field == 'as_blueprint':
        normalized_value = shipment.get('as_blueprint') is True
    elif field == 'sales_delivery':
        normalized_value = shipment.get('sales_delivery') is True
    elif field == 'as_visit_date':
        normalized_value = as_visit.get('date') or ''
    else:
        normalized_value = getattr(order, field, fallback_value)

    status = getattr(order, 'status', None)
    return {
        'success': True,
        'message': '정보가 업데이트되었습니다.',
        'normalized_value': normalized_value if normalized_value is not None else '',
        'status': status,
        'status_label': STATUS.get(status, status),
        'as_completed_date': getattr(order, 'as_completed_date', None) or '',
        'as_visit_date': getattr(order, 'as_visit_date', None) or '',
        'as_pending': shipment.get('as_pending') is True,
        'as_blueprint': shipment.get('as_blueprint') is True,
        'sales_delivery': shipment.get('sales_delivery') is True,
    }


def _schedule_date_has_on_or_after(d_date_str, ref_date):
    """시공일 문자열(단일 또는 CSV)에 ref_date 당일 또는 이후 날짜가 하나라도 있으면 True."""
    if not d_date_str or not ref_date:
        return False
    parts = [p.strip() for p in str(d_date_str).split(',') if p and p.strip()]
    return any(p >= ref_date for p in parts)


def _get_order_schedule_date(order, ref_date: str | None = None):
    """시공일 반환 (가까운 일정 찾기 전용).

    기준: #erp-construction-date 필드 = structured_data.schedule.construction.date.
    ref_date 이후(당일 포함) 중 가장 빠른 날짜를 반환한다.
    • ERP Beta 주문: structured_data.schedule.construction.date 우선
    • 일반 주문: scheduled_date → OrderScheduleDate(construction kind) 순
    • shipping_scheduled_date(상차/출고일)는 사용하지 않음 — 시공일과 별개 개념
    """
    if not order:
        return None

    def _valid(d):
        """날짜 문자열이 유효하고 ref_date 이후인지 확인."""
        s = str(d).strip() if d else ''
        return s if s and (not ref_date or s >= ref_date) else None

    sd = getattr(order, 'structured_data', None)
    if getattr(order, 'is_erp_beta', False) and isinstance(sd, dict):
        cons_date = ((sd.get('schedule') or {}).get('construction') or {}).get('date')
        if d := _valid(cons_date):
            return d

    if d := _valid(getattr(order, 'scheduled_date', None)):
        return d

    # 최종 fallback: OrderScheduleDate 관계 — construction kind만
    sched_dates = getattr(order, 'schedule_dates', None)
    if sched_dates:
        dates = sorted([
            row.date for row in sched_dates
            if row.kind == 'construction' and _valid(row.date)
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


_SEARCH_RADII_KM = [1.0, 3.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0]
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
    """주문 ORM 객체를 nearby 결과 아이템 dict로 변환 (시공일 기준)."""
    order_addr = _get_order_display_address(order)
    d_date = _get_order_schedule_date(order, ref_date)
    item = {
        'id': order.id,
        'customer_name': _get_order_display_customer_name(order),
        'address': order_addr,
        'date': d_date,
        'type': '시공',
        # status 필드 제거 — UI에 상태 표시 불필요
    }
    # DB에 이미 지오코딩된 좌표가 있으면 캐시 — live API 호출 생략용
    db_lat = getattr(order, 'lat', None)
    db_lng = getattr(order, 'lng', None)
    db_geocode_status = getattr(order, 'geocode_status', None)
    if db_lat and db_lng and db_geocode_status == 'success':
        item['_db_lat'] = float(db_lat)
        item['_db_lng'] = float(db_lng)
    return item


@orders_bp.route('/orders/nearby')
@login_required
def api_orders_nearby():
    """AS 대시보드용: 주소 기반 가까운 출고/시공 일정 찾기.

    카카오 Geocoding API로 좌표를 변환한 뒤, 직선거리 기반 점진적 반경
    (1 → 3 → 5 → 10 → 15 → 20 → 25 → 30 km)으로 후보를 수집하고 상위 5건을 반환합니다.
    고유 날짜 5건이 모이는 최소 반경에서 중단; 30km에서도 미달 시 거리 무관 Top 5 반환.
    카카오 API 장애 시 텍스트 유사도 기반 fallback을 사용합니다.
    """
    target_address = request.args.get('address', '').strip()
    if not target_address:
        return jsonify({'success': False, 'message': '주소가 필요합니다.', 'error': '주소가 필요합니다.'}), 400

    exclude_id = request.args.get('exclude_id', type=int)
    # KST(Asia/Seoul) 기준 내일 날짜 사용 — 오늘은 제외, 내일부터 집계
    # Railway 서버는 UTC이므로 반드시 ZoneInfo로 KST 명시
    try:
        from zoneinfo import ZoneInfo
        _kst_tomorrow = (datetime.datetime.now(ZoneInfo('Asia/Seoul')) + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    except Exception:
        _kst_tomorrow = (datetime.datetime.utcnow() + datetime.timedelta(hours=9, days=1)).strftime('%Y-%m-%d')
    ref_date = request.args.get('date', _kst_tomorrow)

    db = get_db()

    from sqlalchemy.orm import load_only, selectinload
    from models import OrderScheduleDate

    # 1. 내일 이후 시공 예정일이 있는 주문만 조회 (AS 상태 제외, 전국 대상)
    # ─ AS_RECEIVED·AS_COMPLETED만 제외 (scheduled_date가 AS방문일로 오염됨)
    # ─ 화이트리스트 대신 블랙리스트: 실제 DB 상태가 CONSTRUCTION·MEASURE 등
    #   다양하므로 AS 상태만 명시적으로 exclude하는 것이 안전.
    # ─ 지역 사전 필터를 걸면 인접 시/도 주문을 놓치므로, 날짜+상태 필터만 적용 후
    #   Haversine 거리 계산으로 가장 가까운 Top5를 순수하게 찾는다.
    _AS_STATUSES = ('AS_RECEIVED', 'AS_COMPLETED', 'DELETED')
    query = (
        db.query(Order)
        .options(
            load_only(
                Order.id, Order.address, Order.status, Order.shipping_scheduled_date,
                Order.scheduled_date, Order.is_erp_beta, Order.structured_data, Order.customer_name,
                Order.lat, Order.lng, Order.geocode_status,  # DB 저장 좌표 — live geocoding 절약
            ),
            selectinload(Order.schedule_dates),
        )
        .outerjoin(
            OrderScheduleDate,
            and_(Order.id == OrderScheduleDate.order_id,
                 OrderScheduleDate.kind == 'construction'),
        )
        .filter(
            # AS 상태만 제외 (scheduled_date가 AS방문일로 오염) — 나머지 전부 허용
            ~Order.status.in_(_AS_STATUSES),
            or_(
                # 시공 예정일: 일반 주문 scheduled_date
                Order.scheduled_date >= ref_date,
                # OrderScheduleDate construction kind
                and_(
                    OrderScheduleDate.id.isnot(None),
                    OrderScheduleDate.date >= ref_date,
                ),
                # ERP Beta: #erp-construction-date = structured_data.schedule.construction.date
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

    # 3. 좌표 결정 우선순위:
    #   1) 프론트에서 넘긴 lat/lng 파라미터 (DB 저장값)
    #   2) exclude_id 주문의 DB lat/lng 직접 조회 (AS 접수 전 geocoding 좌표)
    #   3) Kakao API live geocoding (fallback)
    _req_lat = request.args.get('lat', type=float)
    _req_lng = request.args.get('lng', type=float)

    # exclude_id 주문 DB 좌표 조회 — Kakao API 없이 target 좌표 확보
    if not (_req_lat and _req_lng) and exclude_id:
        _src_order = db.query(Order).options(
            load_only(Order.id, Order.lat, Order.lng, Order.geocode_status)
        ).filter(Order.id == exclude_id).first()
        if _src_order and _src_order.lat and _src_order.lng:
            _req_lat, _req_lng = float(_src_order.lat), float(_src_order.lng)

    try:
        converter = FOMSAddressConverter()

        if _req_lat and _req_lng:
            start_lat, start_lng = _req_lat, _req_lng
        else:
            start_lat, start_lng, _, _ = converter.analyze_address(target_address)

        if not start_lat or not start_lng:
            raise ValueError("기준 주소 좌표 변환 실패")

        # 3-1. 전체 후보 좌표 병렬 변환
        # DB에 geocode_status='success' 좌표가 저장된 경우 live API 호출 생략
        def geocode_item(item: dict):
            if item.get('_db_lat') and item.get('_db_lng'):
                return item, item['_db_lat'], item['_db_lng']
            addr = item['address']
            lat, lng, _, _ = converter.analyze_address(addr)
            # 지방 광역시도 없는 주소(예: "남양주시 화도읍 ...") 는 Kakao 실패 가능
            # → "경기 " 접두 재시도 (이미 "경기"로 시작하면 건너뜀)
            if not lat and not addr.startswith(('서울', '경기', '인천', '부산', '대구', '광주', '대전', '울산', '세종', '강원', '충북', '충남', '전북', '전남', '경북', '경남', '제주')):
                lat, lng, _, _ = converter.analyze_address(f"경기 {addr}")
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

        # 3-2. 30km 이내 전체 pool에서 탭별 독립 Top5 계산
        # ─ 날짜 dedup 제거: 같은 날짜여도 각 주문 독립 평가
        #   (dedup 시 같은 날 더 가까운 주문이 먼저 선택되어 실제 가까운 주문이 탈락하는 버그 수정)
        _MAX_KM = _SEARCH_RADII_KM[-1]  # 30km
        within_max = [it for it in with_distance if it['_dist_km'] <= _MAX_KM]
        pool = within_max if within_max else with_distance
        used_radius = _MAX_KM

        # 1. 거리순 Top5: 직선거리 오름차순 → 날짜 오름차순 (dedup 없음)
        by_distance = sorted(pool,
                             key=lambda x: (x['_dist_km'], x.get('date') or '9999-99-99'))[:_MAX_RESULTS]

        # 2. 날짜순 Top5: 날짜별 dedup (각 날짜에서 가장 가까운 1건 대표) → 날짜 오름차순
        # ─ 이유: dedup 없으면 가장 빠른 날짜(내일 등)가 Top5를 독점해 선택 폭이 없어짐
        # ─ 날짜별 1건씩 대표 선택 → 최대 5가지 서로 다른 날짜 선택지 제공
        def _dedup_by_date(items: list[dict]) -> list[dict]:
            """날짜별 가장 가까운 1건만 남긴 뒤 날짜 오름차순 정렬."""
            by_date_dist = sorted(items, key=lambda x: (x.get('date') or '9999-99-99', x['_dist_km']))
            seen: set[str] = set()
            result = []
            for it in by_date_dist:
                d = it.get('date') or ''
                if d and d not in seen:
                    seen.add(d)
                    result.append(it)
            return result

        by_date = _dedup_by_date(pool)[:_MAX_RESULTS]

        # 3. 복합 Top5: 거리·날짜 각 0~1 정규화 후 0.5:0.5 합산
        try:
            _ref_obj = datetime.date.fromisoformat(ref_date)
        except Exception:
            _ref_obj = datetime.date.today()

        if pool:
            _max_dist = max(it['_dist_km'] for it in pool) or 1.0

            def _safe_days(it: dict) -> float:
                try:
                    return max(0, (datetime.date.fromisoformat(it['date']) - _ref_obj).days)
                except (ValueError, TypeError, KeyError):
                    return None  # 무효 날짜는 정규화에서 제외

            _day_vals_raw = [_safe_days(it) for it in pool]
            # 이상치(None) 제외 후 max 계산 — None이면 복합 점수에서 날짜 기여 0으로 처리
            valid_days = [v for v in _day_vals_raw if v is not None]
            _max_days = max(valid_days) if valid_days else 1.0

            def _norm_days(v) -> float:
                return (v / _max_days) if (v is not None and _max_days > 0) else 1.0  # 무효 날짜: 최하 점수

            _scored = sorted(
                zip(pool, _day_vals_raw),
                key=lambda t: 0.5 * (t[0]['_dist_km'] / _max_dist) + 0.5 * _norm_days(t[1])
            )
            by_combined = [it for it, _ in _scored[:_MAX_RESULTS]]
        else:
            by_distance = by_date = by_combined = []


        # 3-3. 3개 리스트 합집합에 대해서만 route 계산 (중복 제거, 최대 ~15건)
        def route_item(item: dict):
            route_info = converter.calculate_route(start_lat, start_lng, item['_lat'], item['_lng'])
            if route_info.get('status') == 'success':
                item['distance_km'] = route_info['distance_km']
                item['duration_min'] = route_info['duration_min']
                item['score_text'] = f"{route_info['distance_km']}km ({route_info['duration_min']}분)"
            else:
                item['score_text'] = f"약 {item['_dist_km']:.1f}km"
            item['dist_km'] = round(item['_dist_km'], 2)
            item.pop('_dist_km', None)
            item['lat'] = item.pop('_lat', None)
            item['lng'] = item.pop('_lng', None)
            return item

        _seen_route: set[int] = set()
        route_targets: list[dict] = []
        for it in by_distance + by_date + by_combined:
            if it['id'] not in _seen_route:
                _seen_route.add(it['id'])
                route_targets.append(it)

        with ThreadPoolExecutor(max_workers=min(len(route_targets) or 1, 15)) as ex_r:
            route_futures = [ex_r.submit(route_item, it) for it in route_targets]
            for fut in as_completed(route_futures):
                try:
                    fut.result()
                except Exception as route_err:
                    current_app.logger.warning("[NEARBY] 경로 계산 실패: %s", route_err)

        # route_item이 in-place 수정이므로 리스트 그대로 사용
        # dist_km 없는 아이템(route 실패) 제외
        def _routed(lst: list[dict]) -> list[dict]:
            return [it for it in lst if 'dist_km' in it]

        return jsonify({
            'success': True,
            'by_distance': _routed(by_distance),
            'by_date':     _routed(by_date),
            'by_combined': _routed(by_combined),
            'search_radius_km': used_radius,
            'ref_lat': start_lat,
            'ref_lng': start_lng,
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
        'by_distance': fallback_results,
        'by_date':     sorted(fallback_results, key=lambda x: x.get('date') or '9999-99-99'),
        'by_combined': fallback_results,
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
    
    query = db.query(Order).filter(Order.active_filter()).options(
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
    data = request.get_json() or {}
    
    order_id = data.get('order_id')
    # 두 가지 파라미터명 지원: field/value (수도권), field_name/new_value (지방)
    field = data['field'] if 'field' in data else data.get('field_name')
    value = data['value'] if 'value' in data else data.get('new_value')

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
        'as_visit_date', 'as_content', 'as_content_2', 'as_pending', 'as_blueprint', 'sales_delivery',  # AS 방문일·내용(1/2)·미결·영업/전달
        'measurement_date',  # 실측일 필드
        'regional_memo',  # 메모 필드 허용 (수납장 대시보드 등)
        'is_cabinet', 'cabinet_status',  # 수납장 관련
        'shipping_fee'  # 배송비 필드 (수납장 대시보드용)
    ]
    if field not in allowed_fields:
        return jsonify({'success': False, 'message': f'허용되지 않은 필드입니다: {field}'}), 400

    try:
        if field in ('as_content', 'as_content_2'):
            value = sanitize_as_content_html(value)

        _is_beta = getattr(order, 'is_erp_beta', False)
        structured_sync_fields = {
            'manager_name', 'measurement_date', 'scheduled_date',
            'customer_name', 'phone', 'address',
            'as_visit_date', 'as_content', 'as_content_2', 'as_pending', 'as_blueprint', 'sales_delivery',
        }
        structured_data = None
        structured_changed = False
        if field == 'as_completed_date' or _is_beta or field in structured_sync_fields:
            structured_data = _load_order_structured_data_for_update(order)

        old_value = getattr(order, field, None)
        if field == 'as_visit_date':
            pass
        elif field in ('as_content', 'as_content_2', 'as_pending', 'as_blueprint', 'sales_delivery'):
            # structured_data 전용 필드는 모델 컬럼 건너뜀
            pass
        else:
            setattr(order, field, value)

        # AS 완료일 입력 시 ERP 프로세스 AS 처리 카테고리 > 완료로 처리 (기존/Beta 동일), 미결 해제
        if field == 'as_completed_date':
            shipment = ensure_path(structured_data, 'shipment') if isinstance(structured_data, dict) else {}
            if value:
                setattr(order, 'status', 'AS_COMPLETED')
                if _is_beta and isinstance(structured_data, dict):
                    wf = ensure_path(structured_data, 'workflow')
                    wf['stage'] = 'AS_COMPLETED'
                    wf['stage_updated_at'] = datetime.datetime.now().isoformat()
                    structured_changed = True
                if shipment.get('as_pending'):
                    shipment['as_pending'] = False
                    structured_changed = True
            else:
                setattr(order, 'status', 'AS_RECEIVED')
                if _is_beta and isinstance(structured_data, dict):
                    wf = ensure_path(structured_data, 'workflow')
                    wf['stage'] = 'AS_RECEIVED'
                    wf['stage_updated_at'] = datetime.datetime.now().isoformat()
                    structured_changed = True

        # ERP Beta 주문이거나 structured_data 연동이 필요한 필드(as_content, as_pending 등)인 경우
        if _is_beta or field in ('as_content', 'as_content_2', 'as_visit_date', 'as_pending', 'as_blueprint', 'sales_delivery'):
            if field == 'as_pending':
                shipment = ensure_path(structured_data, 'shipment')
                shipment['as_pending'] = _coerce_bool_value(value)
                structured_changed = True
            elif field == 'as_blueprint':
                shipment = ensure_path(structured_data, 'shipment')
                shipment['as_blueprint'] = _coerce_bool_value(value)
                structured_changed = True
            elif field == 'sales_delivery':
                shipment = ensure_path(structured_data, 'shipment')
                shipment['sales_delivery'] = _coerce_bool_value(value)
                structured_changed = True
            elif field == 'manager_name':
                from services.erp_display import clean_dict_like_name
                clean_val = clean_dict_like_name(value)
                order.manager_name = clean_val
                parties = ensure_path(structured_data, 'parties')
                manager = ensure_path(parties, 'manager')
                manager['name'] = clean_val
                structured_changed = True
            elif field == 'measurement_date':
                schedule = ensure_path(structured_data, 'schedule')
                measurement = ensure_path(schedule, 'measurement')
                measurement['date'] = value
                structured_changed = True
            elif field == 'scheduled_date':
                schedule = ensure_path(structured_data, 'schedule')
                construction = ensure_path(schedule, 'construction')
                construction['date'] = value
                structured_changed = True
            elif field == 'customer_name':
                parties = ensure_path(structured_data, 'parties')
                customer = ensure_path(parties, 'customer')
                customer['name'] = value
                structured_changed = True
            elif field == 'phone':
                parties = ensure_path(structured_data, 'parties')
                customer = ensure_path(parties, 'customer')
                customer['phone'] = value
                structured_changed = True
            elif field == 'address':
                site = ensure_path(structured_data, 'site')
                site['address_full'] = value
                structured_changed = True
            elif field == 'as_visit_date':
                schedule = ensure_path(structured_data, 'schedule')
                as_visit = ensure_path(schedule, 'as_visit')
                as_visit['date'] = value
                structured_changed = True
            elif field in ('as_content', 'as_content_2'):
                # as_content(1/2)는 structured_data.shipment에 저장
                shipment = ensure_path(structured_data, 'shipment')
                shipment[field] = value
                structured_changed = True

        if structured_changed and isinstance(structured_data, dict):
            setattr(order, 'structured_data', structured_data)
            flag_modified(order, 'structured_data')
            sync_erp_flat_columns(order, structured_data)

        # 로그를 commit 전에 세션에 추가 → 단일 트랜잭션으로 처리 (이중 커밋 제거)
        if field == 'status':
            log_access(f"자가실측 주문 #{order.id} 상태 변경: '{old_value}' → '{value}'", session['user_id'], auto_commit=False)
        else:
            log_access(f"주문 #{order.id}의 '{field}' 필드를 '{value}'(으)로 변경", session['user_id'], auto_commit=False)

        db.commit()

        if field == 'address':
            enqueue_geocode_order_address(order_id)
        
        return jsonify(_build_order_update_response(order, field, value, structured_data))
    except ValueError as e:
        db.rollback()
        current_app.logger.warning(f"주문 #{order_id} 필드 업데이트 중단: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 409
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
            setattr(order, 'as_received_date', get_today_kst().strftime('%Y-%m-%d'))

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
                log_access(f"주문 #{order.id} 휴지통 이동 (bulk): {old_status_val} → DELETED", user_id, auto_commit=False)
                updated += 1
                continue
            setattr(order, 'status', new_status)
            # AS 접수 상태로 변경 시 접수일이 없으면 오늘 날짜 자동 설정
            if new_status == 'AS_RECEIVED' and not getattr(order, 'as_received_date', None):
                today_str = get_today_kst().strftime('%Y-%m-%d')
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
                    sync_erp_flat_columns(order, sd)
                db.add(OrderEvent(
                    order_id=order.id,
                    event_type='STAGE_CHANGED',
                    payload={'from': old_stage, 'to': new_status, 'manual': True, 'bulk': True},
                    created_by_user_id=user_id
                ))
            log_access(f"주문 #{order.id} 상태 변경: {old_status_val} → {new_status}", user_id, auto_commit=False)
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
