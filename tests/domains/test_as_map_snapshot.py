"""AS 미완료 지도 쿼리·API 계약 테스트 (2026-08-05).

핵심 계약: 지도 모집단 == AS 탭 미완료 판정 SSOT(`incomplete_non_sales_condition`).
- 날짜 무관(미완료 전체), 지방(is_regional) 포함, sales_delivery 제외
- 버킷 필터는 탭 요약 pill과 동일 조건(build_as_incomplete_bucket_conditions)
"""

from db import db_session
from models import Order
from foms.services.map_snapshot import build_as_incomplete_map_query


def _make_as_order(customer_name, *, status='AS', as_completed_date=None,
                   sales_delivery=None, is_regional=False, shipment_extra=None,
                   schedule=None, lat=None, lng=None):
    shipment = dict(shipment_extra or {})
    if sales_delivery is not None:
        shipment['sales_delivery'] = sales_delivery
    order = Order(
        received_date='2026-08-01',
        customer_name=customer_name,
        phone='010-0000-0000',
        address='서울시 강남구 테헤란로 1',
        product='붙박이장',
        status=status,
        as_received_date='2026-08-01',
        as_completed_date=as_completed_date,
        is_regional=is_regional,
        is_erp_order=True,
        lat=lat,
        lng=lng,
        geocode_status='success' if lat is not None else None,
        structured_data={
            'parties': {'customer': {'name': customer_name, 'phone': '010-0000-0000'}},
            'site': {'address_full': '서울시 강남구 테헤란로 1'},
            'shipment': shipment,
            'schedule': schedule or {},
        },
    )
    db_session.add(order)
    return order


def test_as_map_query_matches_tab_incomplete_population(app):
    included_as = _make_as_order('AS처리중')
    included_received = _make_as_order('AS접수', status='AS_RECEIVED')
    included_completed_no_date = _make_as_order(
        'AS완료-완료일공란', status='AS_COMPLETED', as_completed_date='')
    included_regional = _make_as_order('지방AS', is_regional=True)
    excluded_completed = _make_as_order(
        '완료탭행', status='AS_COMPLETED', as_completed_date='2026-08-01')
    excluded_sales = _make_as_order('영업택배', sales_delivery='true')
    excluded_status = _make_as_order('실측주문', status='MEASURE')
    db_session.commit()

    rows = build_as_incomplete_map_query(db_session, '', '', limit=100).all()
    row_ids = {r.id for r in rows}

    assert included_as.id in row_ids
    assert included_received.id in row_ids
    assert included_completed_no_date.id in row_ids
    assert included_regional.id in row_ids  # 지방 AS 포함(generic 분기 회귀 방지)
    assert excluded_completed.id not in row_ids
    assert excluded_sales.id not in row_ids
    assert excluded_status.id not in row_ids

    # 탭 SSOT 교차검증: 같은 모집단을 read model 조건으로 직접 뽑아 일치 확인
    from foms.services.as_dashboard_read_model import build_as_tab_query_conditions
    conditions = build_as_tab_query_conditions(dialect_name='sqlite')
    tab_ids = {
        r.id
        for r in db_session.query(Order)
        .filter(Order.active_filter())
        .filter(Order.status.in_(['AS', 'AS_RECEIVED', 'AS_COMPLETED']))
        .filter(conditions['incomplete_non_sales_condition'])
        .all()
    }
    assert row_ids == tab_ids


def test_as_map_query_bucket_filters_match_tab_buckets(app):
    visit_confirmed = _make_as_order(
        '방문확정', schedule={'as_visit': {'date': '2026-08-10'}})
    pending = _make_as_order('미결', shipment_extra={'as_pending': True})
    unassigned = _make_as_order('아직미정')
    paid_unconfirmed = _make_as_order(
        '유상미확정',
        shipment_extra={'as_billing': {'type': 'paid', 'confirmed': False}},
        schedule={'as_visit': {'date': '2026-08-11'}},
    )
    db_session.commit()

    def bucket_ids(bucket):
        return {r.id for r in build_as_incomplete_map_query(
            db_session, '', '', bucket=bucket, limit=100).all()}

    assert bucket_ids('visit_confirmed') == {visit_confirmed.id, paid_unconfirmed.id}
    assert bucket_ids('pending') == {pending.id}
    assert bucket_ids('unassigned') == {unassigned.id}
    assert bucket_ids('paid_unconfirmed') == {paid_unconfirmed.id}
    # 무효 버킷은 전체(필터 미적용)
    assert bucket_ids('nonsense') == {
        visit_confirmed.id, pending.id, unassigned.id, paid_unconfirmed.id}


def test_as_dashboard_open_map_redirects_to_as_map(client, login):
    response = login.get('/erp/as?tab=incomplete&open_map=1')
    assert response.status_code == 302
    assert 'dashboard=as' in response.headers['Location']
    assert 'date=' not in response.headers['Location']  # AS 지도는 날짜 무관

    response = login.get('/erp/as?tab=incomplete&bucket=pending&open_map=1')
    assert response.status_code == 302
    assert 'dashboard=as' in response.headers['Location']
    assert 'bucket=pending' in response.headers['Location']

    # 무효 버킷은 전달하지 않음
    response = login.get('/erp/as?tab=incomplete&bucket=zzz&open_map=1')
    assert response.status_code == 302
    assert 'bucket=' not in response.headers['Location']


def test_as_map_query_availability_filters(app):
    weekend_pm = _make_as_order(
        '주말오후', schedule={'as_visit': {'availability': {'days': 'weekend', 'time': 'pm'}}})
    weekday_am = _make_as_order(
        '평일오전', schedule={'as_visit': {'availability': {'days': 'weekday', 'time': 'am'}}})
    any_any = _make_as_order(
        '무관메모', schedule={'as_visit': {'availability': {'days': 'any', 'time': 'any', 'note': '3시 이후'}}})
    unknown = _make_as_order('미기입')
    db_session.commit()

    def ids(**kw):
        return {r.id for r in build_as_incomplete_map_query(db_session, '', '', **kw).all()}

    # '가능' 필터 = 명시적 무관(any) 포함, 미기입 제외
    assert ids(avail_days='weekend') == {weekend_pm.id, any_any.id}
    assert ids(avail_days='weekday') == {weekday_am.id, any_any.id}
    assert ids(avail_days='unknown') == {unknown.id}
    assert ids(avail_time='pm') == {weekend_pm.id, any_any.id}
    assert ids(avail_time='am') == {weekday_am.id, any_any.id}
    # 무효 값은 무시(전체)
    assert ids(avail_days='fri') == {weekend_pm.id, weekday_am.id, any_any.id, unknown.id}


def test_as_map_api_reports_unknown_excluded(client, login):
    _make_as_order(
        '주말가능', lat=37.5, lng=127.0,
        schedule={'as_visit': {'availability': {'days': 'weekend', 'time': 'any'}}})
    _make_as_order('미기입1')
    _make_as_order('미기입2')
    db_session.commit()

    response = login.get('/api/map_data?dashboard=as&avail_days=weekend')
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True
    assert payload['summary']['availability_unknown_excluded'] == 2
    labels = {o['customer_name']: o['as_availability_label'] for o in payload['orders']}
    assert labels == {'주말가능': '주말·시간무관'}

    # 필터 미사용 시 고지 0
    response = login.get('/api/map_data?dashboard=as')
    assert response.get_json()['summary']['availability_unknown_excluded'] == 0


def test_map_view_renders_with_as_dashboard_param(client, login):
    response = login.get('/map_view?dashboard=as')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'as-bucket-filter' in html  # AS 버킷 필터 UI 존재
    assert 'map-truncate-banner' in html


def test_as_map_api_returns_incomplete_orders(client, login):
    with_coords = _make_as_order('좌표있는AS', lat=37.501, lng=127.039)
    no_coords = _make_as_order('좌표없는AS')
    db_session.commit()

    response = login.get('/api/map_data?dashboard=as')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True
    order_ids = {item['id'] for item in payload['orders']}
    assert {with_coords.id, no_coords.id} <= order_ids
    marker_ids = {item['id'] for item in payload['markers']}
    assert with_coords.id in marker_ids
    assert no_coords.id not in marker_ids  # 좌표 없으면 markers 제외(목록에는 존재)
    assert payload['summary']['limit_truncated'] is False
    # AS 마커는 담당자 팔레트 미사용(상태색) — source != 'palette' 계약
    # (markerTheme는 'palette'일 때만 담당자색을 쓴다)
    marker = next(m for m in payload['markers'] if m['id'] == with_coords.id)
    assert marker['manager_bg_source'] != 'palette'
