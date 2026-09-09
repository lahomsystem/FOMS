"""모바일 v3 영업 홈 '오늘 동선 · 동행 전달' 렌더 계약 (스펙 §6.3, T6).

라우트를 타지 않고 파샬(`partials/v3/persona_home_sales.html`)을 직접 렌더한다 —
이 화면의 데이터 wiring(`sales_delivery_by_ref`·`mobile_queue_time_hm`)은 실측
대시보드 라우트(T5 소유 파일)가 붙이므로, 마크업 계약은 컨텍스트 계약만 고정하고
라우트 구현과 분리해 판정한다.

컨텍스트 계약(라우트가 채워야 하는 것):
  - ``sales_delivery_by_ref`` : ``{실측 주문 id: [item, ...]}``
    (= ``build_sales_delivery_by_ref(db)["by_ref"]``, 라우트에서 1회 호출)
  - ``mobile_queue_time_hm``  : ``{실측 주문 id: "HH:MM"}``
    (= ``format_minutes_hm(measurement_time_minutes_of(order))``, 신규 쿼리 없음)
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = "partials/v3/persona_home_sales.html"

V3_CSS = ROOT / "static" / "css" / "v3" / "foms-mobile-v3.css"
V3_JS = ROOT / "static" / "js" / "v3" / "foms-mobile-v3.js"
LAYOUT_HEAD = ROOT / "templates" / "partials" / "shared" / "layout_head.html"

ASSET_PIN = "20260909a"


def _row(order_id: int, name: str, address: str = "성남시 분당구 정자로 45") -> dict:
    """실측 큐 행(build_mobile_queue_order_row 결과)의 최소 형태를 만든다.

    Args:
        order_id: 실측 주문 id. name: 고객명. address: 표시 주소.

    Returns:
        파샬이 소비하는 키만 담은 dict.
    """
    return {
        "id": order_id,
        "customer_name": name,
        "address": address,
        "manager_name": "이정민",
        "stage": "실측",
        "stage_code": "MEASURE",
        "product_subtitle": "붙박이장",
        "phone": "010-1111-2222",
        "structured_data": {},
        "measurement_completed": False,
    }


def _delivery(order_id: int, name: str, item_text: str, state: str = "assigned") -> dict:
    """build_sales_delivery_by_ref 의 item 한 건(스펙 §4.2 형태).

    Args:
        order_id: AS 전달 주문 id. name: 고객명. item_text: 챙길 품목 문구.
        state: 'assigned' 또는 'delivered'.

    Returns:
        파샬이 소비하는 키만 담은 dict.
    """
    return {
        "order_id": order_id,
        "customer_name": name,
        "address": "광주시 오포읍 능평로 74",
        "item_text": item_text,
        "state": state,
        "ref_date": "2026-09-09",
        "ref_manager": "이정민",
        "assigned_by": "관리자",
        "assigned_at": "2026-09-09T01:00:00",
    }


def _render(app, **ctx) -> str:
    """영업 페르소나 홈 파샬을 요청 컨텍스트 안에서 렌더한다.

    Args:
        app: Flask 앱 픽스처. **ctx: 파샬에 넘길 템플릿 컨텍스트.

    Returns:
        렌더된 HTML 문자열.
    """
    base = {
        "mobile_queue_rows": [],
        "measurement_panel_dates": [],
        "today_date": "2026-09-09",
        "erp_mine_only": True,
        "sales_delivery_by_ref": {},
        "mobile_queue_time_hm": {},
    }
    base.update(ctx)
    with app.test_request_context("/erp/measurement"):
        return app.jinja_env.get_template(TEMPLATE).render(**base)


@pytest.fixture()
def rows_with_delivery():
    """실측 3건(09:30 / 11:00 / 15:30) + 09:30 건에만 전달 1건."""
    rows = [_row(5133, "신동혁"), _row(5142, "윤아름"), _row(5098, "오세영")]
    time_hm = {5098: "09:30", 5133: "11:00", 5142: "15:30"}
    by_ref = {5098: [_delivery(4760, "한지훈", "상판 마감캡 6EA")]}
    return rows, time_hm, by_ref


def test_delivery_subcard_renders_only_under_assigned_measurement(app, rows_with_delivery):
    """전달이 배정된 실측 아래에만 서브카드가 붙는다(나머지는 실측 카드만)."""
    rows, time_hm, by_ref = rows_with_delivery
    html = _render(
        app,
        mobile_queue_rows=rows,
        mobile_queue_time_hm=time_hm,
        sales_delivery_by_ref=by_ref,
    )
    assert html.count("data-sales-delivery-card") == 1
    assert 'data-order-id="4760"' in html
    assert "AS #4760 한지훈" in html
    assert "상판 마감캡 6EA" in html
    assert "광주시 오포읍 능평로 74" in html
    # 전달이 붙은 step 만 표식을 갖는다.
    assert html.count('data-has-delivery="1"') == 1


def test_run_timeline_is_ordered_by_measurement_time(app, rows_with_delivery):
    """시간축은 mobile_queue_time_hm(HH:MM) 오름차순 — 큐 입력 순서가 아니다."""
    rows, time_hm, by_ref = rows_with_delivery
    html = _render(
        app,
        mobile_queue_rows=rows,
        mobile_queue_time_hm=time_hm,
        sales_delivery_by_ref=by_ref,
    )
    assert html.index("09:30") < html.index("11:00") < html.index("15:30")
    # 09:30(오세영)이 먼저 나오고, 그 아래에 전달 서브카드가 붙는다.
    assert html.index("오세영") < html.index("AS #4760 한지훈") < html.index("윤아름")


def test_unknown_measurement_time_sorts_last(app):
    """시각 미상 건은 '시간 미정'으로 시간축 맨 뒤에 둔다."""
    html = _render(
        app,
        mobile_queue_rows=[_row(1, "미상고객"), _row(2, "오전고객")],
        mobile_queue_time_hm={2: "08:00"},
    )
    assert "시간 미정" in html
    # 히어로('다음 방문')는 큐 첫 행이라 시간축과 별개 — 시간축 구간만 잘라 비교한다.
    timeline = html[html.index("data-run-timeline"):]
    assert timeline.index("오전고객") < timeline.index("미상고객")


def test_banner_shows_count_and_items(app, rows_with_delivery):
    """안내 배너: '오늘 전달 N건 — 출발 전 <품목> 을 챙기세요.'"""
    rows, time_hm, by_ref = rows_with_delivery
    html = _render(
        app,
        mobile_queue_rows=rows,
        mobile_queue_time_hm=time_hm,
        sales_delivery_by_ref=by_ref,
    )
    assert "오늘 전달 1건 — 출발 전 상판 마감캡 6EA 을 챙기세요." in html
    assert "data-run-banner" in html


def test_banner_counts_every_attached_delivery(app):
    """건수는 오늘 동선에 붙은 전달 카드 총수(여러 실측에 걸쳐 합산)."""
    rows = [_row(10, "가고객"), _row(20, "나고객")]
    by_ref = {
        10: [_delivery(101, "고객A", "손잡이 2EA")],
        20: [_delivery(201, "고객B", "경첩 4EA"), _delivery(202, "고객C", "")],
    }
    html = _render(
        app,
        mobile_queue_rows=rows,
        mobile_queue_time_hm={10: "09:00", 20: "13:00"},
        sales_delivery_by_ref=by_ref,
    )
    assert "오늘 전달 3건 — 출발 전 손잡이 2EA, 경첩 4EA 을 챙기세요." in html
    assert html.count("data-sales-delivery-card") == 3


def test_banner_omits_item_phrase_when_no_item_text(app):
    """품목 문구(item_text)가 하나도 없으면 '챙기세요' 절을 생략한다."""
    html = _render(
        app,
        mobile_queue_rows=[_row(10, "가고객")],
        mobile_queue_time_hm={10: "09:00"},
        sales_delivery_by_ref={10: [_delivery(101, "고객A", "")]},
    )
    assert "오늘 전달 1건" in html
    assert "챙기세요" not in html


def test_banner_hidden_when_no_delivery(app, rows_with_delivery):
    """전달 0건이면 배너를 아예 렌더하지 않는다(빈 배너 금지)."""
    rows, time_hm, _ = rows_with_delivery
    html = _render(app, mobile_queue_rows=rows, mobile_queue_time_hm=time_hm)
    assert "data-run-banner" not in html
    assert "오늘 전달" not in html
    assert "data-sales-delivery-card" not in html
    # 실측 카드(시간축)는 그대로 렌더된다.
    assert html.count("px-run__step") >= 3


def test_deliver_button_and_skip_link_hooks(app, rows_with_delivery):
    """큰 '전달 완료' 버튼 + 보조 '전달 못 함'(서버 액션 없음) 훅이 있다."""
    rows, time_hm, by_ref = rows_with_delivery
    html = _render(
        app,
        mobile_queue_rows=rows,
        mobile_queue_time_hm=time_hm,
        sales_delivery_by_ref=by_ref,
    )
    assert "data-sales-delivery-done" in html
    assert "전달 완료</button>" in html
    assert "data-sales-delivery-skip" in html
    assert "전달 못 함" in html
    assert "data-sales-delivery-msg" in html


def test_delivered_state_disables_button(app):
    """이미 전달 완료된 건은 버튼이 disabled + 카드가 is-done."""
    html = _render(
        app,
        mobile_queue_rows=[_row(10, "가고객")],
        mobile_queue_time_hm={10: "09:00"},
        sales_delivery_by_ref={10: [_delivery(101, "고객A", "손잡이", state="delivered")]},
    )
    assert "px-run-deliv is-done" in html
    assert "disabled" in html
    # 이미 전달된 건은 '챙기세요' 목록에서 빠진다.
    assert "챙기세요" not in html


def test_no_inline_style_and_no_tojson_parse_in_partial():
    """인라인 style·JSON.parse('{{ ... |tojson }}') 금지(프로젝트 규약)."""
    src = (ROOT / "templates" / "partials" / "v3" / "persona_home_sales.html").read_text(
        encoding="utf-8"
    )
    # 기존 큐 카드 dot 의 --sc 커스텀 프로퍼티 1건 외에 style= 를 늘리지 않는다.
    assert src.count("style=") == 1
    assert "JSON.parse" not in src
    assert "<script" not in src


def test_run_styles_live_in_v3_css_not_surfaces_bundle():
    """v3 셸은 surfaces 번들을 안 싣는다 — 동선/전달 CSS 는 v3 CSS 안에 있다."""
    css = V3_CSS.read_text(encoding="utf-8")
    for selector in (
        ".px-run-banner",
        ".px-run__step",
        ".px-run__time",
        ".px-run-deliv",
        ".px-run-deliv__done",
        ".px-run-deliv__skip",
    ):
        assert selector in css, selector
    # 터치 타깃 하한(48px)
    assert "min-height:48px" in css.replace(" ", "")


def test_shell_js_owns_the_single_write_call():
    """전달 완료는 셸 JS 가 POST /api/orders/<id>/sales-delivery 로 1회만 쓴다."""
    js = V3_JS.read_text(encoding="utf-8")
    assert "/sales-delivery" in js
    assert 'action: "deliver"' in js
    assert "data-sales-delivery-done" in js
    assert "data-sales-delivery-skip" in js
    assert "success !== true" in js  # data.success 검증
    assert "jQuery" not in js and "$(" not in js
    # CSRF 수동 주입 금지(전역 인터셉터 소관)
    assert "X-CSRF-Token" not in js


def test_asset_pins_synced():
    """변경한 v3 CSS·JS 의 ?v= 핀이 20260909a 로 동기화돼 있다."""
    head = LAYOUT_HEAD.read_text(encoding="utf-8")
    assert f"css/v3/foms-mobile-v3.css') }}}}?v={ASSET_PIN}" in head
    assert f"js/v3/foms-mobile-v3.js') }}}}?v={ASSET_PIN}" in head
