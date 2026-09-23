"""네이버 채널 마크(A안) 표시 계약 — 고객 이름 바로 뒤에 붙는 출처 마크.

고정하는 계약:

* 행 DTO 의 ``channel_source`` 는 **출처**(``structured_data['source'] == SOURCE_MARKER``)
  하나로만 정해진다.
* 출처가 없으면 ``None`` 이다(음성 대조군 — 이게 없으면 1번은 아무것도 증명하지 않는다).
* ``naver_linked`` 만 참인 주문은 출처가 아니다. ERP 에서 직접 받은 주문에 네이버
  재결제를 붙인 경우라 마크가 뜨면 안 된다(오용 차단).
* PC 그리드가 공용 매크로를 부르고, 대시보드 스타일 partial 이 마크 CSS 를 핀과 함께 싣는다.
  마크가 대시보드 밖(전체 주문 목록 · 실측)까지 나가면서 전역 head 도 같은 CSS 를
  싣는다. 저장소에서 ``?v=20260913a`` 를 못박는 곳은 그 두 자리이고, 둘은 늘 같은
  값이어야 한다.
* 매크로는 채널이 없을 때 **빈 문자열**을 낸다 — 빈 span 도 공백 한 칸도 남기면 안 된다.
"""

from __future__ import annotations

from pathlib import Path

from db import db_session
from foms.services.integrations.naver_commerce.constants import (
    LINKED_MARKER_KEY,
    SOURCE_MARKER,
)
from foms.services.orders.dashboard_dto import build_orders_row_dtos
from models import Order

ROOT = Path(__file__).resolve().parents[2]

GRID = "templates/orders/partials/dashboard_grid.html"
STYLES = "templates/orders/partials/dashboard_styles.html"
LAYOUT_HEAD = "templates/partials/shared/layout_head.html"
ORDERS_LISTING = "foms/web/orders/listing.py"
MEASUREMENT_DASHBOARD = "foms/web/measurement/dashboard.py"
IMPORT_LINE = "{% from 'partials/shared/channel_mark.html' import channel_mark %}"

# 마크를 다는 표면 전수(코호트 9/9 — 모바일 홈 CS 히어로는 2026-09-20 카드째 제거). 값은 그 표면이 매크로를 부르는 호출 문자열이다 —
# 화면마다 행 DTO 이름이 달라서 호출 인자까지 같이 못박아야 전수 확인이 된다.
# 실측 모바일 큐 카드(erp_mobile_queue_card_v2.html)는 이미 이 표에 있다: 실측 라우트가
# 행 dict 의 channel_source 키를 채우는 것만으로 켜져서 템플릿 편집이 없었다.
SURFACES = {
    GRID: "channel_mark(o.channel_source)",
    "templates/orders/partials/tablet_dashboard_sheet.html": "channel_mark(o.channel_source)",
    "templates/partials/shared/erp_mobile_queue_card_v2.html": "channel_mark(order.channel_source|default(none, true))",
    "templates/partials/v3/persona_home_cs.html": "channel_mark(_hero.channel_source)",
    "templates/orders/partials/tablet_workqueue_grid.html": "channel_mark(o.channel_source)",
    "templates/orders/index.html": "channel_mark(order.channel_source)",
    "templates/measurement/partials/dashboard_main.html": "channel_mark(r.channel_source|default(none, true))",
    "templates/measurement/partials/mobile_list.html": "channel_mark(o.channel_source|default(none, true))",
    "templates/measurement/partials/tablet_split_body.html": "channel_mark(r.channel_source|default(none, true))",
}
MACRO = "templates/partials/shared/channel_mark.html"
CSS = "static/css/components/foms-channel-mark.css"
CSS_PIN = "css/components/foms-channel-mark.css') }}?v=20260913a"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _code_only(rel: str) -> str:
    """주석과 문서 문자열을 뺀 코드 본문. 음성 대조군이 산문에 걸리지 않게 한다.

    라우트 주석은 "naver_linked 는 출처가 아니다 — 쓰지 마라" 라고 적어 둔다.
    그 경고 자체를 위반으로 세면 경고를 지우는 쪽으로 압력이 생긴다 — 축은 코드다.
    """
    import io
    import tokenize

    readline = io.StringIO(_read(rel)).readline
    return "\n".join(tok.string for tok in tokenize.generate_tokens(readline)
                     if tok.type != tokenize.COMMENT)


def _order(sd: dict) -> Order:
    """표시용 주문 1건. 배정은 이 계약과 무관하므로 만들지 않는다."""
    order = Order(customer_name="테스트고객", phone="010-0000-0000", address="서울",
                  product="붙박이장", options="", received_date="2026-09-13",
                  status="RECEIVED", is_erp_order=True, structured_data=sd)
    db_session.add(order)
    db_session.commit()
    return order


def _row(sd: dict) -> dict:
    order = _order(sd)
    return build_orders_row_dtos([order], {order.id: sd}, {}, {}, None)[0]


def test_naver_source_order_carries_channel_source(app):
    """출처가 네이버면 행 DTO 에 채널이 실린다."""
    sd = {"source": SOURCE_MARKER, "parties": {"customer": {"name": "테스트고객"}}}

    assert _row(sd)["channel_source"] == "NAVER"


def test_plain_order_has_no_channel_source(app):
    """음성 대조군: 출처가 없으면 채널도 없다."""
    sd = {"parties": {"customer": {"name": "테스트고객"}}}

    assert _row(sd)["channel_source"] is None


def test_linked_marker_alone_is_not_a_source(app):
    """오용 차단: naver_linked 만 참인 주문은 네이버 출처가 아니다."""
    sd = {LINKED_MARKER_KEY: True, "parties": {"customer": {"name": "테스트고객"}}}

    assert _row(sd)["channel_source"] is None


def test_grid_and_styles_wire_the_mark() -> None:
    """마크를 다는 표면 전수가 매크로를 부르고, 스타일 partial 이 CSS 를 핀과 함께 싣는다."""
    for rel, call in SURFACES.items():
        body = _read(rel)
        assert IMPORT_LINE in body, f"{rel} 에 매크로 import 줄이 없다"
        assert call in body, f"{rel} 가 {call} 을 부르지 않는다"

    styles = _read(STYLES)
    assert CSS_PIN in styles, "마크 CSS 링크 핀(?v=20260913a)이 없다 — 전역 head 와 짝을 이루는 두 자리 중 하나다"
    assert "?v=20260814a" in styles, "기존 dashboard-grid.css 핀을 건드리면 안 된다"

    assert (ROOT / CSS).is_file(), "마크 CSS 파일이 없다"
    assert 'style="' not in _read(MACRO), "매크로에 인라인 style 속성 금지"


def test_mark_css_is_delivered_globally_with_the_same_pin() -> None:
    """마크 CSS 는 전역 head 에서 실린다. 두 곳이 **같은 핀**을 쓰는 것 자체가 계약이다.

    대시보드 밖(전체 주문 목록 · 실측)까지 마크가 나가므로 전역 로드로 올렸다.
    대시보드 스타일 partial 의 같은 링크는 프래그먼트 주입 경로의 보험으로 남긴다 —
    한쪽 핀만 올리면 브라우저가 두 URL 을 서로 다른 자원으로 보고 둘 다 받는다.
    """
    assert CSS_PIN in _read(LAYOUT_HEAD), "전역 head 에 마크 CSS 링크가 없다"
    assert CSS_PIN in _read(STYLES), "대시보드 스타일 partial 의 링크를 지우면 안 된다"


def test_routes_decide_the_mark_by_source_only() -> None:
    """두 라우트가 출처 하나로 채널을 정한다 — 음성 대조군(naver_linked 부재)까지 본다."""
    for rel in (ORDERS_LISTING, MEASUREMENT_DASHBOARD):
        body = _read(rel)
        head = body.split("def ", 1)[0]
        assert "from foms.services.integrations.naver_commerce.constants import SOURCE_MARKER" in head, (
            f"{rel} 이 SOURCE_MARKER 를 모듈 상단에서 import 하지 않는다")
        assert "channel_source" in body, f"{rel} 이 channel_source 를 채우지 않는다"
        # 음성 대조군: 이게 없으면 위 두 단언은 아무것도 증명하지 않는다.
        # 주석은 뺀 코드만 본다 — 주석의 '쓰지 마라' 경고를 위반으로 세면 안 된다.
        code = _code_only(rel)
        assert "naver_linked" not in code, f"{rel} 이 출처가 아닌 축(naver_linked)을 본다"
        assert "LINKED_MARKER_KEY" not in code, f"{rel} 이 출처가 아닌 축을 import 한다"


def test_order_list_page_marks_only_the_naver_sourced_row(auth_client):
    """실제 렌더 계약: `/` 본문에 마크가 네이버 주문 수만큼만 나온다."""
    _order({"source": SOURCE_MARKER, "parties": {"customer": {"name": "네이버고객"}}})
    _order({"parties": {"customer": {"name": "직접고객"}}})

    resp = auth_client.get("/", follow_redirects=False)

    assert resp.status_code == 200, f"`/` 가 200 이 아니다(status={resp.status_code})"
    body = resp.get_data(as_text=True)
    # 음성 대조군이 여기 들어 있다: 출처 없는 주문이 마크를 만들면 2가 된다.
    assert body.count("foms-channel-mark--naver") == 1


def test_macro_renders_nothing_without_a_channel(app):
    """매크로 음성 대조군: 채널이 없으면 빈 문자열이다(공백 한 칸도 안 된다)."""
    mark = app.jinja_env.get_template("partials/shared/channel_mark.html").module.channel_mark

    assert str(mark(None)) == "", "빈 span 이나 공백이 남으면 안 된다"

    html = str(mark("NAVER"))
    assert "foms-channel-mark--naver" in html
    assert 'role="img"' in html, "바깥 span 이 role=img 여야 한다"
    assert 'aria-hidden="true"' in html, "안쪽 svg 가 aria-hidden 이어야 한다"
    assert "#03C75A" in html, "색은 SVG 속성으로 직접 박는다(CSS 변수 금지)"
    assert 'width="22"' in html, "크기도 표시 속성으로 박는다 — CSS 미도착 fragment 방어"
    assert 'height="22"' in html, "크기도 표시 속성으로 박는다 — CSS 미도착 fragment 방어"
