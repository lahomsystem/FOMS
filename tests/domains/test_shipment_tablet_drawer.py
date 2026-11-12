"""태블릿 가로 출고 탭 줄 누름 세부정보 서랍 계약 (설계서 2026-11-09-tablet-production-ui §14.3 P14-4, sqlite domains lane).

표는 한 줄에 요점만 — 줄을 누르면 오른쪽 서랍(``GET /erp/shipment/tablet-sheet/<id>``)에서 세부를 읽고
시공시간 · 현장 메모를 고친다. 시공자는 표의 이름판이 정하므로 서랍은 팀 고르기가 없고, 저장은
``construction_workers`` 를 보내지 않는다(보내면 이름판에서 방금 고친 값을 덮는다). 고정하는 것:

* 일반 줄: 전화(tel:) · 주소 전체 · 그날 품목 전부 · 시간 단추 ``오전 8시`` / ``오후 1시`` · 라디오 없음 · 금액 없음.
* AS 줄: ``AS 정보`` · 접수 내용 · 불러올 AS 탭 읽기 조각 주소 · [AS 탭에서 열기].
* 편집 불가(영업팀): 단추 · 입력 없음.
* 저장 JS(``shipment-save``)가 ``construction_workers`` 를 싣지 않는다 + API 는 없는 키를 그대로 둔다.
* AS 탭 읽기 조각(``?readonly=1``)은 기록 추가 · 수정 · 삭제 단추를 내지 않는다.

모든 이름 · 번호 · 주소는 지어낸 값이다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.erp_display import get_today_kst
from models import Order, OrderScheduleDate, User

ROOT = Path(__file__).resolve().parents[2]
DOMAIN_SHEETS_JS = ROOT / "static/js/foms/tablet-domain-sheets.js"
SHIP_SHEET_JS = ROOT / "static/js/shipment/tablet-ship-sheet.js"

LONG_ADDR = "가짜시 가짜구 서랍로 123번길 45 가짜아파트 101동 1203호 (현관 비번 따로)"
PRICE = "987654"


def _login(client, role: str, team: str | None) -> None:
    user = User(
        username=f"ship-drawer-{role}-{team}".lower(), password=generate_password_hash("secret"),
        role=role, team=team, name="서랍시험", is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _order(customer: str, *, status: str = "IN_CONSTRUCTION", extra: dict | None = None) -> Order:
    today = get_today_kst().isoformat()
    sd = {
        "parties": {"manager": {"name": "가짜영업"}, "customer": {"name": customer}, "orderer": {"name": "가짜대리점"}},
        "items": [
            {"product_name": "가짜붙박이장 W2400", "spec_width": "2400", "quantity": 1, "price": PRICE},
            {"product_name": "가짜화장대", "spec_width": "900", "quantity": 2, "price": PRICE},
            {"product_name": "가짜신발장", "spec_width": "1200", "quantity": 1, "construction_date": "2099-01-01"},
        ],
        "schedule": {"construction": {"date": today, "time": "오전"}},
        "shipment": {"construction_workers": ["가짜1팀", "가짜2팀"], "construction_time": "",
                     "site_extra": [{"text": "엘리베이터 없음", "color": "black"}]},
        "notes": {"construction_note": "주차는 뒤쪽"},
        "payment": {"total_amount": int(PRICE)},
        **(extra or {}),
    }
    order = Order(
        received_date=today, customer_name=customer, phone="010-1234-5678", address=LONG_ADDR,
        product="가짜붙박이장", status=status, is_erp_order=True, structured_data=sd,
        as_received_date="2026-11-01" if status.startswith("AS") else None,
    )
    db_session.add(order)
    db_session.flush()
    kind = "as_visit" if status.startswith("AS") else "construction"
    db_session.add(OrderScheduleDate(order_id=order.id, kind=kind, date=today, source="beta_schedule"))
    db_session.commit()
    return order


def _sheet(client, order_id: int, query: str = "") -> str:
    resp = client.get(f"/erp/shipment/tablet-sheet/{order_id}{query}")
    assert resp.status_code == 200, resp.status_code
    return resp.get_data(as_text=True)


def test_drawer_regular_row_shows_details_and_time_presets(client) -> None:
    _login(client, "STAFF", "SHIPMENT")
    order = _order("서랍일반고객")
    html = _sheet(client, order.id, f"?date={get_today_kst().isoformat()}")

    assert "서랍일반고객" in html and f"#{order.id}" in html
    assert 'href="tel:01012345678"' in html and "010-1234-5678" in html
    assert LONG_ADDR in html  # 주소 전체(표는 잘리지만 서랍은 다 보인다)
    assert "map.kakao.com/?q=" in html
    assert "가짜대리점" in html and "가짜영업" in html
    # 그날 품목 전부(다른 날 품목은 빠진다) · 규격 · 자수.
    assert "가짜붙박이장" in html and "가짜화장대" in html and "가짜신발장" not in html
    assert "2400 · 8.0자" in html and "2개" in html
    # 시공자는 읽기만 + 안내, 팀 고르기 라디오 · 잔여 없음.
    assert "가짜1팀, 가짜2팀" in html and "시공자는 표의 시공자 칸에서 골라요" in html
    assert 'type="radio"' not in html and "tablet-assign-team" not in html and "잔여" not in html
    # 시간 단추는 PC 와 같은 미리 값 + 영업 메모.
    assert 'value="오전 8시">오전 8시</button>' in html and 'value="오후 1시">오후 1시</button>' in html
    assert "data-tablet-time-custom-trigger" in html and "09:00" not in html and "14:00" not in html
    assert "영업 메모: 오전" in html
    # 현장 메모(고칠 수 있음) + 주문서 시공 메모(읽기).
    assert 'data-tablet-assign-memo value="엘리베이터 없음"' in html and "주차는 뒤쪽" in html
    assert 'data-tablet-sheet-action="shipment-save"' in html and ">저장</button>" in html
    assert "배정 적용" not in html and "shipment-assign" not in html
    # 금액 없음 · AS 묶음 없음 · 인라인 style 없음.
    assert PRICE not in html and "987,654" not in html
    assert "AS 정보" not in html and "data-ship-as-log-url" not in html
    assert "style=" not in html


def test_drawer_without_date_uses_order_first_construction_date(client) -> None:
    _login(client, "STAFF", "CS")
    html = _sheet(client, _order("서랍날짜없음").id)
    assert "가짜붙박이장" in html and "가짜신발장" not in html


def test_drawer_as_row_has_as_info_and_lazy_as_tab_log(client) -> None:
    _login(client, "STAFF", "SHIPMENT")
    order = _order("서랍AS고객", status="AS_RECEIVED",
                   extra={"shipment": {"as_content": "<p>문짝 처짐</p><p>경첩 교체</p>", "construction_workers": []}})
    html = _sheet(client, order.id)

    assert 'class="foms-ship-sheet__as">AS</span>' in html
    assert "AS 정보" in html and "2026-11-01" in html
    assert "문짝 처짐" in html and "경첩 교체" in html and "<p>문짝" not in html
    assert f'data-ship-as-log-url="/erp/as/timeline/{order.id}?readonly=1"' in html
    assert "AS 기록을 불러오는 중이에요" in html
    assert f'href="/erp/as?focus_order={order.id}" data-foms-erp-no-shell="1">AS 탭에서 열기</a>' in html
    assert "foms-as-round-chart.css') }}" not in html and "foms-as-round-chart.css?v=20260828a" in html
    assert "아직 없음" in html  # 시공자 없음
    assert PRICE not in html


def test_as_tab_readonly_fragment_has_no_write_controls(client) -> None:
    """서랍이 불러 붙이는 AS 탭 조각 — readonly=1 이면 기록 추가 · 수정 · 삭제 · 판정 단추가 없다(대조: 없으면 있다)."""
    _login(client, "STAFF", "CS")
    order = _order("서랍AS조각", status="AS_RECEIVED", extra={"shipment": {"as_content": "<p>문짝 처짐</p>"}})
    ro = client.get(f"/erp/as/timeline/{order.id}?readonly=1")
    assert ro.status_code == 200
    ro_html = ro.get_data(as_text=True)
    assert 'class="as-rchart"' in ro_html
    for mark in ("as-timeline__quick-add", "as-tl-item__edit", "as-tl-item__delete", "as-billing-edit",
                 "as-sales-delivery-btn", "as-rchart-avail-edit"):
        assert mark not in ro_html, mark
    rw_html = client.get(f"/erp/as/timeline/{order.id}").get_data(as_text=True)
    assert "as-timeline__quick-add" in rw_html  # 대조군: 같은 사람 · 같은 주문, readonly 없으면 쓰기 칸이 있다


def test_drawer_read_only_for_sales_has_no_buttons_or_inputs(client) -> None:
    _login(client, "STAFF", "SALES")
    html = _sheet(client, _order("서랍영업보기").id)
    assert "서랍영업보기" in html and LONG_ADDR in html and "엘리베이터 없음" in html
    assert "<input" not in html and "data-tablet-time-chip" not in html
    assert "shipment-save" not in html and ">닫기</button>" in html


def _shipment_save_source() -> str:
    js = DOMAIN_SHEETS_JS.read_text(encoding="utf-8")
    start = js.index("function shipmentSave(")
    body = js[start:js.index("// ---- 생산 칸반 필터", start)]
    return "\n".join(line for line in body.splitlines() if not line.strip().startswith("//"))


def test_shipment_save_js_never_sends_construction_workers() -> None:
    src = _shipment_save_source()
    assert "/api/erp/shipment/update/" in src and "JSON.stringify(payload)" in src
    assert "construction_time" in src and "site_extra" in src
    assert "construction_workers" not in src and "tablet-assign-team" not in src
    js = DOMAIN_SHEETS_JS.read_text(encoding="utf-8")
    assert 'action === "shipment-save"' in js and "shipment-assign" not in js


def test_update_api_keeps_workers_when_key_absent(client) -> None:
    """저장이 construction_workers 를 빼고 보내면 서버는 시공자를 그대로 둔다(이름판 값 보존)."""
    _login(client, "STAFF", "SHIPMENT")
    order_id = _order("서랍저장보존").id
    resp = client.post(f"/api/erp/shipment/update/{order_id}", json={"construction_time": "오전 8시"})
    assert resp.status_code == 200, resp.get_data(as_text=True)[:200]
    db_session.remove()
    shipment = db_session.get(Order, order_id).structured_data["shipment"]
    assert shipment["construction_time"] == "오전 8시"
    assert shipment["construction_workers"] == ["가짜1팀", "가짜2팀"]
    assert shipment["site_extra"] == [{"text": "엘리베이터 없음", "color": "black"}]


def test_ship_sheet_js_contract() -> None:
    js = SHIP_SHEET_JS.read_text(encoding="utf-8")
    assert "__FOMS_SHIP_SHEET_BOUND" in js
    assert "foms:erp-shell-fragment-swapped" in js and '"tablet-sheet"' in js
    assert "data-ship-as-log-url" in js and "try {" in js and "catch (err)" in js
    assert "AS 기록을 못 불러왔어요" in js and "as-rchart-field--billing" in js
    assert "jQuery(" not in js and not re.search(r"\$\(", js)
    assert len(js.splitlines()) < 150


@pytest.mark.parametrize("path", [
    "static/js/shipment/shipment-entry.js",
])
def test_entry_chain_loads_ship_sheet_js(path) -> None:
    entry = (ROOT / path).read_text(encoding="utf-8")
    assert "'/static/js/shipment/tablet-ship-sheet.js?v=20261111a'" in entry
    assert "'/static/js/foms/tablet-domain-sheets.js?v=20261111a'" in entry


# --------------------------------------------------------------------------- #
# P14-5 — 태블릿 위 줄: 꺼진 [출고 확정] 대신 [이미지 저장], [AS 추천] → [AS 넣기].
# --------------------------------------------------------------------------- #
def _pcbar(html: str) -> str:
    start = html.index('class="foms-ship-pcbar"')
    return html[start:html.index('class="erp-pro-card erp-shipment-desktop-shell"', start)]


@pytest.mark.parametrize("team,can_edit", [("SHIPMENT", True), ("SALES", False)])
def test_tablet_pcbar_export_and_as_insert(client, team, can_edit) -> None:
    _login(client, "STAFF", team)
    _order("위줄단추")
    resp = client.get(f"/erp/shipment?date={get_today_kst().isoformat()}")
    assert resp.status_code == 200
    bar = _pcbar(resp.get_data(as_text=True))
    # 이미지 저장 = PC 머리 · 모바일과 같은 방아쇠(숨은 #btn-export-image 를 누른다). 읽기 기능이라 권한 무관.
    assert "js-shipment-export-trigger" in bar and "<span>이미지 저장</span>" in bar
    assert "출고 확정" not in bar and "disabled" not in bar
    assert ("data-shipment-as-recommend-open" in bar) is can_edit
    assert ("<span>AS 넣기</span>" in bar) is can_edit
    assert "AS 추천</span>" not in bar


def test_as_log_font_floor_scoped_to_drawer() -> None:
    """불러 붙인 AS 탭 조각 글자를 출고 서랍 안에서만 13px 이상으로(AS 탭 CSS 는 그대로)."""
    css = (ROOT / "static/css/foundation/foms-tablet-landscape.css").read_text(encoding="utf-8")
    assert ".foms-ship-sheet .foms-ship-sheet__aslog .as-rchart * {" in css
    block = css[css.index(".foms-ship-sheet .foms-ship-sheet__aslog .as-rchart * {"):]
    assert "font-size: calc(13px * var(--foms-fs, 1));" in block[:120]
    bundle = (ROOT / "static/css/foundation/foms-tablet-bundle.css").read_text(encoding="utf-8")
    assert 'foms-tablet-landscape.css?v=20261111b' in bundle
