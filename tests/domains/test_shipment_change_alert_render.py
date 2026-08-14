"""출고 대시보드 시공일 변경 알림 렌더 계약 (T4 PC · T5 태블릿).

고정하는 것:

* 미확인 변경이 있는 행 → **행 배지 + [확인] 버튼**(data 속성 포함)이 뜨고, 상단 **배너**가
  그 주문을 칩으로 호명한다. 칩의 ``href`` 앵커는 **같은 응답 안에 실재하는 id** 여야 한다
  (죽은 점프 링크 회귀 차단).
* 미확인 변경이 없으면 배너도 배지도 없다. ack 후에도 (개인 윈도가 닫혀) 사라진다.
* 태블릿 클린 그리드 행도 **같은 매크로**로 같은 배지를 낸다(표면별 포크 금지) — 코호트
  게이트는 서버 렌더가 아니라 CSS 소유라 v2 코호트에서도 마크업은 동일하다.
* 모바일 v2/v3 출고 표면(모바일 큐·v3 페르소나 홈)에는 알림이 새지 않는다(범위 밖).
* 손댄 자산의 ?v 핀이 저장소 전체에서 동기(SW staticCacheFirst 캐시 함정 방지).
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path

from sqlalchemy import event
from werkzeug.security import generate_password_hash

from db import db_session, engine
from foms.services.erp_display import get_today_kst
from models import Order, OrderEvent, OrderScheduleDate, User

ROOT = Path(__file__).resolve().parents[2]

DASHBOARD_MAIN = "templates/shipment/partials/dashboard_main.html"
TABLET_GRID = "templates/shipment/partials/tablet_ship_grid.html"
TABLET_SHEET = "templates/shipment/partials/tablet_sheet.html"
CHANGE_MACROS = "templates/shipment/partials/shipment_change_macros.html"
DASHBOARD_SCRIPTS = "templates/shipment/partials/dashboard_scripts.html"
SHIP_ENTRY_JS = "static/js/shipment/shipment-entry.js"
CHANGE_ALERT_JS = "static/js/shipment/shipment-change-alert.js"
EXTRAS_CSS = "static/css/contexts/shipment/dashboard-table-extras.css"

_CHANGE = "CONSTRUCTION_DATE_CHANGED"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# helpers (렌더 경로)
# --------------------------------------------------------------------------- #
def _login(client, username: str = "ship_alert_user", *, team: str = "SHIPMENT") -> User:
    """출고 편집 권한이 있는 사용자로 로그인한다(ADMIN — 시공팀 차단 규칙 밖)."""
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role="ADMIN",
        team=team,
        name=f"{username} 이름",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _today() -> str:
    """라우트가 기본 선택하는 날짜(KST 오늘)."""
    return get_today_kst().strftime("%Y-%m-%d")


def _make_row_order(customer_name: str = "변경알림고객") -> Order:
    """오늘 시공 예정인 출고 대시보드 행 1건(스케줄 row 포함)."""
    today = _today()
    order = Order(
        received_date=today,
        customer_name=customer_name,
        phone="010-7777-8888",
        address="서울 출고로 9",
        product="붙박이장",
        status="IN_CONSTRUCTION",
        manager_name="담당",
        is_erp_order=True,
        structured_data={
            "workflow": {"stage": "SHIPMENT"},
            "parties": {"customer": {"name": customer_name}},
            "schedule": {"construction": {"date": today}},
            "shipment": {"construction_workers": ["시공1"]},
        },
        erp_stage_code="SHIPMENT",
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(
        OrderScheduleDate(
            order_id=order.id, kind="construction", date=today, source="beta_schedule"
        )
    )
    db_session.commit()
    return order


def _seed_change(order_id: int, from_date: str = "2026-07-20", to_date: str = "2026-07-28") -> None:
    """시공일 변경 이벤트 1건(미확인)을 심는다."""
    db_session.add(
        OrderEvent(
            order_id=order_id,
            event_type=_CHANGE,
            payload={"from": from_date, "to": to_date, "source": "test"},
            created_at=datetime.datetime(2026, 7, 1, 9, 0, 0),
        )
    )
    db_session.commit()


def _dashboard(client) -> str:
    resp = client.get("/erp/shipment")
    assert resp.status_code == 200, resp.get_data(as_text=True)[:500]
    return resp.get_data(as_text=True)


def _tablet_grid_html(body: str) -> str:
    """응답에서 태블릿 클린 그리드(#foms-tablet-ship-grid) 구간만 잘라낸다."""
    start = body.index('id="foms-tablet-ship-grid"')
    end = body.index("</table>", start)
    return body[start:end]


def _pc_row_html(body: str, order_id: int) -> str:
    """응답에서 PC 테이블의 그 주문 행(tr.shipment-row) 구간만 잘라낸다."""
    start = body.index(f'id="shipment-row-{order_id}"')
    end = body.index("</tr>", start)
    return body[start:end]


# --------------------------------------------------------------------------- #
# 1. PC — 배지 + 배너 + 점프 앵커
# --------------------------------------------------------------------------- #
def test_unacked_change_renders_row_badge_with_data_attributes(client):
    """미확인 변경이 있는 행 → 배지 + [확인] 버튼(주문 id data 속성 포함)."""
    _login(client, "ship_alert_badge")
    order_id = _make_row_order().id
    _seed_change(order_id)

    row = _pc_row_html(_dashboard(client), order_id)

    assert "data-shipment-change" in row
    assert f'data-shipment-change data-order-id="{order_id}"' in row
    assert "시공일" in row
    assert "7/20" in row and "7/28" in row  # 옛 날짜 → 새 날짜
    assert f'class="erp-ship-change__ack js-shipment-change-ack" data-order-id="{order_id}"' in row
    assert ">확인</button>" in row


def test_unacked_change_renders_banner_chip_pointing_at_live_anchor(client):
    """배너가 그 주문을 칩으로 호명하고, 칩 href 앵커가 **같은 응답에 실재**한다."""
    _login(client, "ship_alert_banner")
    order = _make_row_order("배너대상고객")
    order_id = order.id
    _seed_change(order_id)

    body = _dashboard(client)

    assert "data-shipment-change-banner" in body
    assert "현재 목록에서 시공일이 변경된 건" in body
    assert f'<span data-shipment-change-count>1</span>건' in body
    assert "배너대상고객" in body

    # PC 칩 · 태블릿 칩 두 개(같은 문서에 두 표면이 공존 → 앵커 접두어 분리).
    for prefix in ("shipment-row-", "shipment-tgrid-row-"):
        href = f'href="#{prefix}{order_id}"'
        assert href in body, f"점프 칩 href 부재: {href}"
        assert f'id="{prefix}{order_id}"' in body, f"점프 착지 앵커 부재: {prefix}{order_id}"

    # 칩은 주문 id 를 data 로도 실어야 ack 후 in-place 제거가 가능하다.
    assert f'data-shipment-change-chip data-order-id="{order_id}"' in body


def test_no_unacked_change_renders_neither_banner_nor_badge(client):
    """변경 이벤트가 없으면 배너도 행 배지도 렌더되지 않는다."""
    _login(client, "ship_alert_clean")
    order_id = _make_row_order("무변경고객").id

    body = _dashboard(client)

    assert f'id="shipment-row-{order_id}"' in body  # 행 자체는 뜬다
    assert "data-shipment-change-banner" not in body
    assert "data-shipment-change " not in body
    assert "js-shipment-change-ack" not in body


def test_badge_and_banner_disappear_after_ack(client):
    """[확인](ack) 후 같은 사용자 화면에서는 배지·배너가 사라진다(개인 윈도)."""
    _login(client, "ship_alert_ack")
    order_id = _make_row_order("확인후고객").id
    _seed_change(order_id)
    assert "data-shipment-change-banner" in _dashboard(client)

    resp = client.post(f"/api/orders/{order_id}/shipment/change-ack", json={})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["banner_count_hint"] == -1

    body = _dashboard(client)
    assert "data-shipment-change-banner" not in body
    assert "js-shipment-change-ack" not in body


# --------------------------------------------------------------------------- #
# 2. 태블릿 — 같은 매크로가 클린 그리드 행에도 배지를 낸다
# --------------------------------------------------------------------------- #
def test_tablet_grid_row_carries_same_badge(client, monkeypatch):
    """태블릿 코호트에서도 클린 그리드 행이 같은 배지·앵커를 낸다.

    코호트 자격은 기존 태블릿 테스트와 같은 방식으로 준다(FOMS_V3_SHELL_COHORT =
    사용자 id → erp_mobile_v2_enabled). 표시/은닉은 CSS 소유라 서버 마크업은 코호트와
    무관하게 동일해야 한다.
    """
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _login(client, "ship_alert_tablet")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    order_id = _make_row_order("태블릿고객").id
    _seed_change(order_id)

    body = _dashboard(client)
    assert 'class="erp-mobile-v2-layout"' in body, "태블릿/모바일 v2 코호트 미적용"

    grid = _tablet_grid_html(body)
    assert f'id="shipment-tgrid-row-{order_id}"' in grid
    assert f'data-shipment-change data-order-id="{order_id}"' in grid
    assert "js-shipment-change-ack" in grid
    assert "시공일" in grid


def test_tablet_grid_badge_absent_without_change(client, monkeypatch):
    """변경이 없으면 태블릿 그리드 행에도 배지가 없다."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _login(client, "ship_alert_tablet_clean")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    _make_row_order("태블릿무변경")

    grid = _tablet_grid_html(_dashboard(client))

    assert "data-shipment-change" not in grid


def test_tablet_sheet_renders_change_strip(client):
    """배정 시트도 같은 매크로로 스트립을 낸다(생산 시트 선례와 같은 자리)."""
    _login(client, "ship_alert_sheet")
    order_id = _make_row_order("시트고객").id
    _seed_change(order_id)

    resp = client.get(f"/erp/shipment/tablet-sheet/{order_id}")

    assert resp.status_code == 200
    sheet = resp.get_data(as_text=True)
    assert "foms-ship-sheet__change" in sheet
    assert f'data-shipment-change data-order-id="{order_id}"' in sheet
    assert "js-shipment-change-ack" in sheet


def _count_order_event_queries(fn) -> int:
    """fn 실행 중 ``order_events`` 를 읽는 SQL 문 수(N+1 가드)."""
    counter = {"n": 0}

    def _before(conn, cursor, statement, params, context, executemany):
        if "order_events" in (statement or "").lower():
            counter["n"] += 1

    event.listen(engine, "before_cursor_execute", _before)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", _before)
    return counter["n"]


def test_change_alert_costs_exactly_one_query_regardless_of_row_count(client):
    """행이 몇 개든 ``order_events`` 조회는 **1회**다(N+1 금지 · TTFB 예산 291ms).

    스펙 §6 이 예산 상향을 금지했으므로 추가 비용은 배치 1쿼리로 묶여 있어야 한다.
    """
    _login(client, "ship_alert_qcount")
    first = _make_row_order("쿼리고객1")
    _seed_change(first.id)
    one_row = _count_order_event_queries(lambda: _dashboard(client))

    for i in range(2, 6):
        order = _make_row_order(f"쿼리고객{i}")
        _seed_change(order.id)
    many_rows = _count_order_event_queries(lambda: _dashboard(client))

    assert one_row == 1, f"단일 행에서 order_events 쿼리 {one_row}회"
    assert many_rows == 1, f"5행에서 order_events 쿼리 {many_rows}회(N+1 회귀)"


# --------------------------------------------------------------------------- #
# 3. 범위 경계 — 모바일 v2/v3 출고 표면에는 새지 않는다
# --------------------------------------------------------------------------- #
def test_mobile_surfaces_do_not_render_change_alert():
    """모바일 큐·v3 페르소나 홈은 변경 알림 매크로를 호출하지 않는다(스펙 §7 범위 밖)."""
    for rel in (
        "templates/shipment/partials/shipment_mobile_queue.html",
        "templates/shipment/partials/shipment_mobile_controls.html",
        "templates/partials/v3/persona_home_shipment.html",
    ):
        html = _read(rel)
        assert "render_shipment_change" not in html, f"모바일 표면 누출: {rel}"
        assert "erp-ship-change" not in html, f"모바일 표면 누출: {rel}"


def test_banner_lives_inside_desktop_only_card():
    """배너는 `.erp-shipment-desktop-shell` 카드 안에 있어 모바일 v2/v3 에서 조상째 은닉된다."""
    body = _read(DASHBOARD_MAIN)
    card_idx = body.index('class="erp-pro-card erp-shipment-desktop-shell"')
    banner_idx = body.index("render_shipment_change_banner(shipment_change_banner)")
    assert card_idx < banner_idx, "배너가 데스크톱 전용 카드 밖에 있다(모바일 누출 위험)"


# --------------------------------------------------------------------------- #
# 4. 매크로 SSOT — 표면별 마크업 포크 금지
# --------------------------------------------------------------------------- #
def test_three_surfaces_share_one_macro():
    """PC 행·태블릿 그리드 행·배정 시트가 같은 매크로 파일을 import 한다."""
    for rel in (DASHBOARD_MAIN, TABLET_GRID, TABLET_SHEET):
        html = _read(rel)
        assert "shipment/partials/shipment_change_macros.html" in html, rel
        assert "render_shipment_change_badge(" in html, rel
        # 배지 마크업 자체는 어느 호출부에도 없다(포크 금지).
        assert "erp-ship-change__badge" not in html, f"표면별 배지 마크업 포크: {rel}"


def test_macro_file_has_no_inline_style_and_carries_ack_hooks():
    """매크로는 인라인 스타일 없이 ack 위임에 필요한 훅을 모두 낸다."""
    html = _read(CHANGE_MACROS)
    assert "style=" not in html
    for token in (
        "data-shipment-change",
        "data-shipment-change-chip",
        "data-shipment-change-banner",
        "data-shipment-change-count",
        "js-shipment-change-ack",
        "erp-ship-change__msg",
    ):
        assert token in html, f"ack 배선 훅 누락: {token}"


# --------------------------------------------------------------------------- #
# 5. ack 클라이언트 — defer · 싱글턴 · 무음 실패 금지 · 리로드 금지
# --------------------------------------------------------------------------- #
def test_ack_client_script_is_deferred_and_keeps_scripts_partial_untouched():
    """ack 스크립트는 dashboard_main 의 기존 defer 블록에 싣는다(G1: 동기 스크립트 0).

    dashboard_scripts.html 에 얹지 않는 이유: 그 파샬은 이미 <script src> 2개라
    perf_scan 의 fragment-multi-script(high) 가 deploy veto 를 낸다. 그 구조적 부채는
    별건이므로 여기서 건드리지 않고, 파샬이 무변경임을 함께 잠근다.
    """
    main = _read(DASHBOARD_MAIN)
    tag = re.search(r"<script[^>]*shipment-change-alert\.js[^>]*>", main)
    assert tag, "ack 스크립트 <script> 태그 부재"
    assert "defer" in tag.group(0), f"defer 부재(G1): {tag.group(0)}"

    scripts_partial = _read(DASHBOARD_SCRIPTS)
    assert "shipment-change-alert.js" not in scripts_partial
    assert len(re.findall(r"<script[^>]*src=", scripts_partial)) == 2, (
        "dashboard_scripts.html 의 <script src> 수가 바뀌었다 — perf_scan "
        "fragment-multi-script veto 를 확인하라"
    )


def test_ack_client_singleton_defensive_and_no_reload():
    """싱글턴 가드(G4) + 방어적 파싱 + .catch + 화면 노출, location.reload 금지(사용자 결정)."""
    js = _read(CHANGE_ALERT_JS)
    assert "window.__FOMS_SHIPMENT_CHANGE_ALERT_BOUND" in js
    assert "JSON.parse" in js and "res.text()" in js
    assert ".catch(" in js
    assert "showFailure" in js
    assert "location.reload" not in js, "확인은 리로드 없이 그 표시만 지운다(사용자 결정)"
    assert "banner_count_hint" in js
    assert "$(" not in js and "jQuery" not in js


def test_jump_landing_has_flash_animation_not_static_ring_only():
    """칩 점프 착지는 AS 드리프트와 같이 빨간 플래시 애니메이션이어야 한다.

    정적 ``inset 2px`` 테두리만 있으면 이미 화면에 보이는 행(오아영 #4606 같은)을
    눌렀을 때 스크롤이 없어 '애니메이션이 안 나온다'로 보인다. AS 키프레임을
    import 하지 않고 출고 시트에 같은 처방을 둔다(페이지 경계).
    """
    css = _read(EXTRAS_CSS)
    assert "@keyframes erp-ship-change-target-flash" in css
    assert "animation: erp-ship-change-target-flash" in css
    assert "tr:target > td" in css
    assert "erp-ship-change-flash" in css
    assert "as-drift-target-flash" not in css
    assert "@import" not in css
    # 출고 표 td 는 overflow:hidden 이라 착지 순간에 visible 이 아니면 플래시가 잘린다.
    target_block = css.split("tr:target > td", 1)[1]
    assert "overflow: visible" in target_block.split("@keyframes", 1)[0]


def test_chip_click_replays_landing_flash_even_on_same_hash():
    """같은 칩을 다시 눌러도 플래시가 재생되어야 한다(:target 은 재클릭 no-op)."""
    js = _read(CHANGE_ALERT_JS)
    assert "closest(CHIP)" in js
    assert "erp-ship-change-flash" in js
    assert "scrollIntoView" in js
    assert "event.preventDefault()" in js
    assert "getElementById" in js
    assert "foms:erp-shell-fragment-swapped" in js
    assert "$(" not in js and "jQuery" not in js


# --------------------------------------------------------------------------- #
# 6. 핀 동기 — 손댄 자산의 ?v 가 저장소 전체에서 일치해야 한다
# --------------------------------------------------------------------------- #
def test_extras_css_pin_bumped_and_unique():
    """dashboard-table-extras.css 는 20260814a 로 범프되고 옛 핀이 남아 있지 않다."""
    main = _read(DASHBOARD_MAIN)
    assert "dashboard-table-extras.css') }}?v=20260814a" in main
    assert "dashboard-table-extras.css') }}?v=20260805a" not in main
    # 새 규칙이 실제로 그 시트에 있어야 한다(핀만 올리고 내용이 없으면 배지가 무스타일).
    css = _read(EXTRAS_CSS)
    for selector in (
        ".erp-ship-change-banner",
        ".erp-ship-change-chip",
        ".erp-ship-change__badge",
        ".erp-ship-change__ack",
        ".foms-ship-sheet__change",
    ):
        assert selector in css, f"출고 컨텍스트 CSS 규칙 누락: {selector}"
    # AS 컨텍스트 시트를 끌어오지 않는다(페이지 경계 유지 — @import 0).
    assert "@import" not in css


def test_pc_table_badge_is_block_level_not_inline():
    """PC 표 고객 셀의 배지는 자기 줄로 내려야 한다(전화번호 옆 inline 배치 = 셀 밖 잘림).

    스테이징 실측(2026-08-05, 1600px): 고객 열 기본 폭 122px, 배지 폭 113px 인데
    inline-flex 라 전화번호 뒤에서 시작해 셀 오른쪽 밖으로 78px 밀렸고
    ``td { overflow: hidden }`` 이 잘라 35px 만 보였다. 태블릿 클린 그리드는 셀이 넓어
    고객명 옆 inline 배치가 의도이므로 이 규칙은 PC 표에만 건다.
    """
    css = _read(EXTRAS_CSS)
    assert "#shipment-dashboard-table .erp-ship-change {" in css
    block = css.split("#shipment-dashboard-table .erp-ship-change {", 1)[1].split("}", 1)[0]
    assert "display: flex" in block, "PC 표 배지가 블록 레벨이 아니다(셀 밖 잘림 회귀)"
    # 태블릿 그리드까지 블록으로 내리면 고객명 옆 배치가 깨진다.
    assert "#foms-tablet-ship-grid .erp-ship-change {" not in css


def test_touched_asset_pins_are_unique_repo_wide():
    """손댄 자산의 ?v 가 저장소 전체에서 하나의 값이어야 한다(SW staticCacheFirst 함정).

    한 곳만 범프하면 다른 링크가 옛 캐시본을 계속 물어 배포가 반영되지 않는다.
    """
    blobs = []
    for pattern in ("templates/**/*.html", "static/**/*.js", "static/**/*.css"):
        for path in ROOT.glob(pattern):
            rel = str(path.relative_to(ROOT)).replace("\\", "/")
            if "/backups/" in rel or "/node_modules/" in rel:
                continue
            blobs.append(path.read_text(encoding="utf-8", errors="ignore"))
    joined = "\n".join(blobs)

    for asset in ("shipment-change-alert.js", "dashboard-table-extras.css"):
        pins = set(re.findall(re.escape(asset) + r"['\"\s\)\}]*\?v=([0-9a-z]+)", joined))
        assert len(pins) == 1, f"{asset} 핀 불일치(동시 범프 누락): {sorted(pins)}"


def test_shipment_entry_chain_untouched():
    """shipment-entry.js CHAIN·버전은 건드리지 않았다(위 fragment-multi-script 회피 근거)."""
    entry = _read(SHIP_ENTRY_JS)
    assert "SHIP_JS_V = '20260730e'" in entry
    assert "shipment-change-alert.js" not in entry


def test_tablet_bundle_pin_untouched():
    """태블릿 번들은 건드리지 않았다(계약 테스트 2곳 락스텝 대상 — 범프 시 동반 수정 필요)."""
    head = _read("templates/partials/shared/layout_head.html")
    assert "foms-tablet-bundle.css') }}?v=20260727d" in head
