"""카카오 알림톡 v1 — 변수 빌더·자격 판정 순수 로직 테스트 (T1).

발송·outbox·Solapi 호출은 이 파일 범위 밖(T2).
"""

from foms.services.kakao_alimtalk import (
    ALIMTALK_MAX_BODY_LEN,
    ALIMTALK_TEMPLATE_MEASURE,
    build_dedupe_key,
    build_variables,
    extract_valid_phone,
    normalize_measure_schedule,
    render_preview,
)


def _sd(**overrides):
    """최소 유효 sd(실측일 있음) 기반 픽스처."""
    sd = {
        'parties': {'customer': {'name': '임다슬', 'phone': '010-2473-6730'}},
        'schedule': {'measurement': {'date': '2026-08-14', 'time': '3시 30분'}},
        'items': [{'product_name': '무몰딩 여닫이'}],
    }
    sd.update(overrides)
    return sd


# --- normalize_measure_schedule -------------------------------------------------


def test_normalize_multi_date_order_insensitive():
    sd = {'schedule': {'measurement': {'date': '2026-08-15, 2026-08-14', 'time': ' 3시 30분 '}}}
    sd2 = {'schedule': {'measurement': {'date': '2026-08-14,2026-08-15', 'time': '3시 30분'}}}
    assert normalize_measure_schedule(sd) == normalize_measure_schedule(sd2)


def test_normalize_returns_sorted_pipe_joined_dates():
    sd = {'schedule': {'measurement': {'date': '2026/08/15, 2026.08.14, 2026-08-14', 'time': ' 오후 2시 '}}}
    assert normalize_measure_schedule(sd) == ('2026-08-14|2026-08-15', '오후 2시')


def test_normalize_drops_unparseable_tokens():
    sd = {'schedule': {'measurement': {'date': '상담, 2026-08-14, ', 'time': ''}}}
    assert normalize_measure_schedule(sd) == ('2026-08-14', '')


def test_normalize_none_when_no_valid_date():
    assert normalize_measure_schedule({'schedule': {'measurement': {'date': '상담'}}}) is None
    assert normalize_measure_schedule({'schedule': {'measurement': {}}}) is None
    assert normalize_measure_schedule({}) is None
    assert normalize_measure_schedule(None) is None


# --- build_dedupe_key -----------------------------------------------------------


def test_dedupe_key_none_without_valid_date():
    assert build_dedupe_key(1, {'schedule': {'measurement': {'date': '상담'}}}) is None


def test_dedupe_key_shape_and_stability():
    sd = {'schedule': {'measurement': {'date': '2026-08-15, 2026-08-14', 'time': ' 3시 '}}}
    key = build_dedupe_key(42, sd)
    assert key == 'alimtalk:measure:42:2026-08-14|2026-08-15:3시'
    assert key == build_dedupe_key(42, {'schedule': {'measurement': {'date': '2026-08-14,2026-08-15', 'time': '3시'}}})


def test_dedupe_key_changes_when_time_changes():
    base = {'schedule': {'measurement': {'date': '2026-08-14', 'time': '3시'}}}
    moved = {'schedule': {'measurement': {'date': '2026-08-14', 'time': '4시'}}}
    assert build_dedupe_key(7, base) != build_dedupe_key(7, moved)


# --- extract_valid_phone --------------------------------------------------------


def test_phone_multi_takes_first_valid():
    sd = {'parties': {'customer': {'phone': '010-2473-6730 / 010-1111-2222'}}}
    assert extract_valid_phone(sd) == '01024736730'


def test_phone_invalid_returns_none():
    assert extract_valid_phone({'parties': {'customer': {'phone': '1234'}}}) is None


def test_phone_landline_and_missing_return_none():
    assert extract_valid_phone({'parties': {'customer': {'phone': '02-1234-5678'}}}) is None
    assert extract_valid_phone({'parties': {'customer': {'phone': ''}}}) is None
    assert extract_valid_phone({}) is None


def test_phone_skips_invalid_first_token():
    sd = {'parties': {'customer': {'phone': '없음, 010-1111-2222'}}}
    assert extract_valid_phone(sd) == '01011112222'


# --- build_variables ------------------------------------------------------------


def test_variables_deposit_and_fallbacks():
    sd = {'parties': {'customer': {'name': '임다슬', 'phone': '010-2473-6730'}},
          'payment': {'deposit': 100000}, 'schedule': {'measurement': {'date': '2026-08-14', 'time': '3시 30분'}},
          'items': [{'product_name': '무몰딩 여닫이'}]}
    v = build_variables(sd)
    assert v['#{예약금}'] == '100,000원' and v['#{실측일}'] == '8월 14일'
    assert v['#{시공일}'] == '상담' and '무몰딩 여닫이' in v['#{품목내역}']


def test_variables_multi_date_korean_join():
    sd = _sd(schedule={'measurement': {'date': '2026-08-14, 2026-08-15', 'time': '3시'}})
    assert build_variables(sd)['#{실측일}'] == '8월 14일, 8월 15일'


def test_variables_time_blank_falls_back_to_undecided():
    sd = _sd(schedule={'measurement': {'date': '2026-08-14', 'time': '  '}})
    assert build_variables(sd)['#{실측시간}'] == '미정'


def test_variables_unparseable_date_excluded_from_display():
    sd = _sd(schedule={'measurement': {'date': '2026-08-14, 다음주', 'time': '3시'}})
    assert build_variables(sd)['#{실측일}'] == '8월 14일'


def test_variables_orderer_and_address_fallbacks():
    v = build_variables(_sd())
    assert v['#{발주사}'] == '라홈'
    assert v['#{주소}'] == '상담'
    assert v['#{예약금}'] == '없음'

    sd = _sd(parties={'customer': {'name': '임다슬', 'phone': '010-2473-6730'}, 'orderer': {'name': '한샘'}},
             site={'address_full': '서울시 강남구 1'})
    v2 = build_variables(sd)
    assert v2['#{발주사}'] == '한샘' and v2['#{주소}'] == '서울시 강남구 1'


def test_variables_construction_date_korean_when_present():
    sd = _sd(schedule={'measurement': {'date': '2026-08-14', 'time': '3시'},
                       'construction': {'date': '2026-09-01'}})
    assert build_variables(sd)['#{시공일}'] == '9월 1일'


def test_variables_item_block_has_six_labels_with_fallback():
    block = build_variables(_sd())['#{품목내역}']
    assert block.splitlines() == [
        '제품명 : 무몰딩 여닫이',
        '내 부 : 상담',
        '색 상 : 상담',
        '옵 션 : 상담',
        '손잡이 : 상담',
        '기 타 : 상담',
    ]


def test_variables_items_joined_by_blank_line():
    sd = _sd(items=[{'product_name': 'A'}, {'product_name': 'B'}])
    block = build_variables(sd)['#{품목내역}']
    assert '\n\n' in block and '제품명 : A' in block and '제품명 : B' in block


def test_variables_never_empty():
    """알림톡 변수는 빈 문자열이면 발송이 거부되므로 전부 채워져야 한다."""
    v = build_variables({})
    assert set(v) == set(_template_var_names())
    assert all(val.strip() for val in v.values())


# --- render_preview -------------------------------------------------------------


def _template_var_names():
    import re
    return set(re.findall(r'#\{[^}]+\}', ALIMTALK_TEMPLATE_MEASURE))


def test_render_preview_substitutes_every_variable():
    text = render_preview(_sd())
    assert '#{' not in text
    assert '임다슬' in text and '8월 14일' in text


def test_render_preview_under_1000_with_many_items():
    items = [{'product_name': f'제품{i}', 'internal': 'x' * 30, 'color': 'y' * 30} for i in range(30)]
    sd = {'parties': {'customer': {'name': 'a', 'phone': '010-2473-6730'}}, 'items': items,
          'schedule': {'measurement': {'date': '2026-08-14', 'time': '3시'}}}
    text = render_preview(sd)
    assert len(text) <= 1000 and '외 29건' in text


def test_render_preview_hard_guard_with_single_huge_item():
    """축약 후에도 초과하면 하드 가드가 추가로 잘라 1,000자를 넘기지 않는다."""
    sd = _sd(items=[{'product_name': 'P', 'misc': '가' * 3000}])
    assert len(render_preview(sd)) <= ALIMTALK_MAX_BODY_LEN


def test_render_preview_keeps_short_items_intact():
    text = render_preview(_sd())
    assert '외 ' not in text and '무몰딩 여닫이' in text
