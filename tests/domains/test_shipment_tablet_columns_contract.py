"""출고 대시보드 태블릿 가로 — 하루치 출고표(시공자 묶음 카드 · 9칸 · 이름판) 계약.

[2026-11-11 설계서 tablet-production-ui §14.3 · 시안 안 17 · 결정 D29 · D30] 옛 6칸 클린 그리드
(시공일 · 고객 · 발주사 · 제품 · 자수 · 도면담당 + 시공팀 머리줄)를 회사 출고일지 9칸 표로 바꿨다.
코호트 태블릿 가로(body.erp-mobile-v2-layout + coarse landscape ≥992)에서:
  - PC 테이블은 래퍼(.shipment-table-wrapper)째 숨는다(shipment-dashboard-columns.css 문지기).
  - 하루치 출고표(tablet_ship_grid.html)가 대신한다: 머리 한 줄 + 시공자 묶음 카드(시공자 없음 묶음이 맨 위).
    칸 = 번호 · 대리점 · 제품명 · 규격 · 현장주소 · 고객 · 시공시간 · 영업 담당 · 시공자. 본문 칠 없음,
    남는 색 = 시공자 칸 사람 색(1~10, PC PASTEL_COLORS 순서). 모양은 tablet-day-sheet.css(같은 문지기 안).
  - 줄 누름 → 시트: 감싸는 div 의 .foms-tablet-workqueue-wrap + tr.erp-main-row[data-order-id]
    [data-foms-sheet-url] 를 tablet-side-sheet.js(수정 금지)가 잡는다. 시공자 칸은 button 이라 그 파일의
    INTERACTIVE 가드에 걸려 시트를 열지 않고, tablet-ship-assign.js 가 이름판을 연다.
  - 묶음 · 번호 · 사람 색 · 사람별 집계는 서버 build_tablet_day_sheet 한 곳(라우트가 tablet_day_sheet 로 넘김).
PC(fine) · 폰 · 세로 무회귀 = 모든 코호트 규칙이 body 클래스 + 코어 MQ 문지기 안.

[은퇴한 계약(옛 6칸 그리드 — 근거와 함께 이관)]
  - test_num_column_right_aligned_tabular_nums · test_construction_date_stack_styles ·
    test_group_header_team_pastel_tint · test_clean_grid_row_touch_height ·
    test_clean_grid_group_header_carries_team_color_index · test_clean_grid_group_sum_source_is_server_meta
    → 9칸 묶음 카드 계약(칸 순서 · 사람 색 번호 · 줄 46px · 묶음 = 서버 tablet_day_sheet)으로 이관.
문자열 부분일치로 잠그되 whitespace-exact 블록은 잠그지 않는다(resilient). 렌더 시험은 가짜 줄로
partial 하나만 그린다(DB 불필요).
"""

from __future__ import annotations

import html as html_lib
import json
import re
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]

COLUMNS_CSS = "static/css/contexts/shipment/shipment-dashboard-columns.css"
DASHBOARD_MAIN = "templates/shipment/partials/dashboard_main.html"
TABLET_GRID = "templates/shipment/partials/tablet_ship_grid.html"
TABLET_SHEET = "templates/shipment/partials/tablet_sheet.html"
DAY_SHEET_CSS = "static/css/contexts/shipment/tablet-day-sheet.css"
ASSIGN_JS = "static/js/shipment/tablet-ship-assign.js"
SHIPMENT_ENTRY_JS = "static/js/shipment/shipment-entry.js"
DASHBOARD_SCRIPTS = "templates/shipment/partials/dashboard_scripts.html"

CORE_MEDIA_QUERY = (
    "(min-width: 992px) and (orientation: landscape) and (pointer: coarse)"
)


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text)


# --- (1) CSS 문지기 + PC 테이블 숨김 / 하루치 출고표 표시 · 모양 ------------------


def test_tablet_gate_uses_core_cohort_media_query() -> None:
    """코어 코호트 MQ(coarse landscape ≥992)로 게이트한다."""
    css = _read(COLUMNS_CSS)
    assert CORE_MEDIA_QUERY in css


def test_pc_table_wrapper_hidden_in_cohort() -> None:
    """[은퇴 대체] 저우선 열 개별 은닉 대신, 코호트에서 PC 테이블 래퍼째 은닉한다.
    body 클래스 스코프 + !important(Bootstrap .table-responsive 특이도 대비)."""
    css = _norm(_read(COLUMNS_CSS))
    assert "body.erp-mobile-v2-layout .erp-dashboard-shipment .shipment-table-wrapper" in css
    assert "display: none !important;" in css


def test_clean_grid_shown_in_cohort() -> None:
    """클린 그리드 wrap 은 base-hide → 코호트에서만 display:block(순서 계약 = base-hide 선행)."""
    css = _norm(_read(COLUMNS_CSS))
    assert ".foms-tablet-shipgrid-wrap { display: none; }" in css
    assert "body.erp-mobile-v2-layout .foms-tablet-shipgrid-wrap" in css
    assert "display: block;" in css


def test_no_data_col_key_gating_remains() -> None:
    """[은퇴] data-col-key 기반 열 은닉/폭 회수 규칙은 전부 제거되어야 한다
    (PC 테이블은 래퍼째 은닉 — 개별 열 CSS 게이트 불필요). 단 PC 리사이즈용 data-col-key
    마크업(dashboard_main.html)은 유지된다(별도 테스트)."""
    css = _read(COLUMNS_CSS)
    assert 'data-col-key="detail"' not in css
    assert 'data-col-key="address"' not in css
    assert 'data-col-key="spec"' not in css
    assert "width: 0 !important;" not in css


def test_retired_six_column_rules_removed() -> None:
    """[은퇴] 옛 6칸 그리드(시공일 스택 · 자수 오른쪽 · 팀 머리줄 칠) · 상단 KPI 네 칸 규칙이 남지 않는다(죽은 선택자 금지)."""
    css = _read(COLUMNS_CSS) + _read(DAY_SHEET_CSS)
    for dead in (
        "foms-tablet-shipgrid__grp", "foms-tablet-shipgrid__when", "foms-tablet-shipgrid__date",
        "foms-tablet-shipgrid__clock", "foms-tablet-shipgrid__num", "foms-tablet-shipgrid__cap",
        "tablet-ship-kpis", "data-team-color-index",
    ):
        assert dead not in css, f"옛 규칙이 남았다: {dead}"
    html = _read(DASHBOARD_MAIN)
    assert "tablet-ship-kpis" not in html and "tablet_ship_kpis" not in html


def test_day_sheet_css_rules_only_inside_cohort_gate() -> None:
    """tablet-day-sheet.css 의 규칙은 전부 코어 MQ 한 블록 안 + body.erp-mobile-v2-layout 로 시작한다."""
    css = re.sub(r"/\*.*?\*/", "", _read(DAY_SHEET_CSS), flags=re.S).strip()
    head = "@media " + CORE_MEDIA_QUERY + " {"
    assert css.startswith(head), "MQ 블록 앞에 규칙이 있다"
    depth, end = 0, None
    for i, ch in enumerate(css):
        depth += (ch == "{") - (ch == "}")
        if ch == "}" and depth == 0:
            end = i
            break
    assert end is not None and css[end + 1:].strip() == "", "MQ 블록 뒤에 규칙이 있다"
    inner = css[len(head):end]
    assert "@media" not in inner
    blocks = list(re.finditer(r"([^{}]+)\{[^{}]*\}", inner))
    assert blocks
    for block in blocks:
        for sel in block.group(1).split(","):
            assert sel.strip().startswith("body.erp-mobile-v2-layout"), f"문지기 밖 선택자: {sel.strip()}"


def test_day_sheet_css_font_sizes_scale_and_min_13() -> None:
    """글자 크기는 모두 calc(Npx * var(--foms-fs, 1)) 이고 가장 작은 글자는 13px 이다."""
    css = re.sub(r"/\*.*?\*/", "", _read(DAY_SHEET_CSS), flags=re.S)
    sizes = re.findall(r"font-size:\s*([^;]+);", css)
    assert sizes
    for value in sizes:
        m = re.fullmatch(r"calc\((\d+)px \* var\(--foms-fs, 1\)\)", value.strip())
        assert m, f"글자 손잡이를 안 따르는 font-size: {value}"
        assert int(m.group(1)) >= 13, f"13px 보다 작은 글자: {value}"


def test_day_sheet_css_row_height_density_and_people_colors() -> None:
    """줄 46px(밀도 40/56 은 #foms-tablet-ship-grid 변수로) · 사람 색 1~10 = PC PASTEL_COLORS 순서."""
    css = _norm(_read(DAY_SHEET_CSS))
    assert "--ship-rh: 46px;" in css
    assert '#foms-tablet-ship-grid[data-foms-density="40"] { --ship-rh: 40px; }' in css
    assert '#foms-tablet-ship-grid[data-foms-density="56"] { --ship-rh: 56px; }' in css
    pastel = ["#B8D4E3", "#FFE5CC", "#E8D5E9", "#D5E9D5", "#F0D5D5", "#D5D5E9", "#FFF0D5", "#D5E9E5", "#F5D5E5", "#E9E5D5"]
    for i, color in enumerate(pastel, start=1):
        assert f'[data-ship-color="{i}"] {{ --ship-pc: {color}; }}' in css
    assert "table-layout: fixed;" in css


def test_day_sheet_assets_pinned_where_shipment_css_loads() -> None:
    """새 CSS 는 출고 CSS 가 실리는 dashboard_main.html(온전한 페이지 · 셸 조각 공통)에 ?v= 핀으로 실린다.
    새 JS 는 셸 조각에서 이중 실행되지 않게 shipment-entry.js CHAIN 으로 ?v= 핀을 붙여 싣는다."""
    html = _read(DASHBOARD_MAIN)
    assert re.search(r"css/contexts/shipment/tablet-day-sheet\.css'\) \}\}\?v=\d{8}[a-z]", html)
    assert re.search(r"'/static/js/shipment/tablet-ship-assign\.js\?v=\d{8}[a-z]'", _read(SHIPMENT_ENTRY_JS))
    assert "tablet-ship-assign.js" not in _read(DASHBOARD_SCRIPTS)


# --- (2) 하루치 출고표 템플릿 계약 ---------------------------------------------


def test_day_sheet_header_nine_columns_in_order() -> None:
    """머리 한 줄 = 출고일지 9칸, 이 순서."""
    html = _read(TABLET_GRID)
    head = html[html.index("<thead>"):html.index("</thead>")]
    labels = re.findall(r"<th[^>]*>([^<]+)</th>", head)
    assert labels == ["번호", "대리점", "제품명", "규격", "현장주소", "고객", "시공시간", "영업 담당", "시공자"]


def test_day_sheet_row_sheet_tap_contract() -> None:
    """줄 누름 → 시트 계약(tablet-side-sheet.js 무수정): 감싸는 클래스 2개 · tr.erp-main-row · data-order-id ·
    data-foms-sheet-url · 줄 id(배너 점프 착지점) · 시공일 변경 배지 매크로 · 협력사 희망 표시."""
    html = _read(TABLET_GRID)
    assert 'class="foms-tablet-shipgrid-wrap foms-tablet-workqueue-wrap"' in html
    assert 'id="shipment-tgrid-row-{{ r.id }}" class="erp-main-row' in html
    assert 'data-order-id="{{ r.id }}"' in html
    assert "erp_shipment_page.erp_shipment_tablet_sheet" in html
    assert "render_shipment_change_badge(" in html
    assert "data-shipment-partner-request" in html
    assert "tablet_day_sheet" in html  # 묶음은 서버 한 곳(build_tablet_day_sheet)


def test_day_sheet_template_has_no_inline_style_paint_or_amount() -> None:
    """인라인 style 없음 · 본문 칠 클래스 없음(D29) · 금액 없음(D7). 주석({# #})은 빼고 본다."""
    html = re.sub(r"\{#.*?#\}", "", _read(TABLET_GRID), flags=re.S)
    assert "style=" not in html
    for paint in ("table-warning", "table-info", "table-danger", "bg-warning", "bg-info", "bg-danger", "text-bg-",
                  "shipment-row--as", "data-team-color-index"):
        assert paint not in html, f"본문 칠: {paint}"
    for money in ("금액", "price", "amount", "₩"):
        assert money not in html, f"금액 글자: {money}"


def test_day_sheet_js_contract() -> None:
    """이름판 JS: 300줄 미만 · jQuery 없음 · safeJsonParse · Idempotency-Key · settings_version · 같은 저장 API ·
    fetch 실패 처리 · 409 문구 · 다시 받기 길(FOMS_ERP_SHELL.navigateByShell) · 배율 나누기 · 싱글턴."""
    js = _read(ASSIGN_JS)
    assert len(js.splitlines()) < 300
    assert "jQuery" not in js and "$(" not in js
    assert "safeJsonParse(" in js and "JSON.parse(" in js
    assert "'Idempotency-Key'" in js
    assert "settings_version" in js
    assert "/api/erp/shipment/update/" in js
    assert ".catch(" in js and "data.success" in js
    assert "다른 사람이 먼저 고쳤어요. 다시 받을게요" in js
    assert "navigateByShell" in js and "bypassCache: true" in js
    assert "fomsUiZoom" in js
    assert "__FOMS_SHIP_ASSIGN_BOUND" in js
    assert "data-ship-people" in js and "data-ship-worker-cell" in js


# --- (2-1) 렌더 계약: 가짜 줄로 partial 하나만 그린다(DB 불필요) ---------------


def _fake_row(oid, workers, units=0.0, status="RECEIVED", as_text=""):
    items = [{"product_name": "여닫이", "spec_width": str(int(units * 300))}] if units else []
    sd = {
        "shipment": {"construction_workers": list(workers)},
        "items": items,
        "parties": {"manager": {"name": "윤가람"}},
    }
    return SimpleNamespace(id=oid, status=status, is_erp_order=True, structured_data=sd,
                           shipment_visible_items=items, customer_name=f"고객{oid}", address=f"성남 분당구 {oid}",
                           orderer_name="라홈", mutation_version=3, as_content_text=as_text, product="")


def _render(app, rows, can_edit=True, freelancer=False):
    from flask import render_template

    from foms.services.shipment.tablet_day_sheet import build_tablet_day_sheet

    settings = [{"name": "김팀", "capacity": 10, "off_dates": []}, {"name": "박팀", "capacity": 10, "off_dates": []}]
    sheet = build_tablet_day_sheet(rows, settings, "2026-11-13")
    with app.test_request_context("/erp/shipment?date=2026-11-13"):
        html = render_template("shipment/partials/tablet_ship_grid.html", tablet_day_sheet=sheet,
                               can_edit_shipment=can_edit, shipment_freelancer_view=freelancer,
                               can_edit_order_here=False)
    return html, sheet


def test_day_sheet_render_groups_chips_and_people_json(app) -> None:
    """시공자 없음 카드가 맨 위 · AS 딱지 · ＋ 시공자 · 사람 색 번호 속성 · data-ship-people 이 JSON 으로 읽힌다."""
    rows = [
        _fake_row(1, ["김팀"], units=10.0),
        _fake_row(2, []),
        _fake_row(3, ["김팀", "박팀"], units=20.0),
        _fake_row(4, ["김팀"], status="AS_RECEIVED", as_text="레일 교체\n두 번째 줄"),
    ]
    html, sheet = _render(app, rows)
    assert html.index("시공자 없음 1건") < html.index('id="shipment-tgrid-row-1"')
    assert "foms-tablet-shipgrid__card--miss" in html
    assert html.count('class="erp-main-row foms-tablet-shipgrid__row"') == 4
    assert '<span class="foms-tablet-shipgrid__as">AS</span>' in html
    assert "레일 교체" in html and "두 번째 줄" not in html  # AS 줄 규격 = 접수 내용 첫 줄
    assert html.count("＋ 시공자") == 1
    assert 'data-ship-color="1">김팀' in html and 'data-ship-color="2">박팀' in html
    m = re.search(r"data-ship-people='([^']*)'", html)
    people = json.loads(html_lib.unescape(m.group(1)))
    assert [p["name"] for p in people] == ["김팀", "박팀"]
    assert people == json.loads(json.dumps(sheet["people"]))
    workers = [json.loads(html_lib.unescape(w)) for w in re.findall(r"data-workers='([^']*)'", html)]
    assert ["김팀", "박팀"] in workers and [] in workers
    assert 'data-version="3"' in html and 'data-ship-can-assign="true"' in html
    assert "data-shipment-as-recommend-open" in html  # 표 아래 AS 넣기 = 기존 추천 창


def test_day_sheet_render_read_only_has_no_worker_button(app) -> None:
    """편집 불가(또는 켜진 프리랜서)면 시공자 칸은 글자뿐 — 단추 · ＋ 시공자 · AS 넣기 단추가 없다."""
    rows = [_fake_row(1, ["김팀"], units=10.0), _fake_row(2, [])]
    for can_edit, freelancer in ((False, False), (True, True)):
        html, _ = _render(app, rows, can_edit=can_edit, freelancer=freelancer)
        assert "data-ship-worker-cell" not in html
        assert "＋ 시공자" not in html
        assert "data-shipment-as-recommend-open" not in html
        assert 'data-ship-can-assign="false"' in html
        assert ">김팀<" in html


def test_day_sheet_render_empty_day(app) -> None:
    """줄이 없으면 한 줄 안내."""
    html, _ = _render(app, [])
    assert "이 날 출고가 없어요" in html
    assert "erp-main-row" not in html


def test_dashboard_main_top_bar_summary_pill() -> None:
    """위 줄(태블릿 코호트) = N건 + 시공자 없음 알약(0 이면 숨김). KPI 네 칸은 걷어 냈다."""
    html = _read(DASHBOARD_MAIN)
    assert "{{ rows|length }}건" in html
    assert "{% if tablet_day_sheet and tablet_day_sheet.unassigned %}" in html
    assert 'class="foms-ship-pcbar__miss">시공자 없음 {{ tablet_day_sheet.unassigned }}' in html


def test_density_toggle_targets_clean_grid() -> None:
    """밀도 토글 대상에 하루치 출고표 id 가 포함(결합 셀렉터)."""
    html = _read(DASHBOARD_MAIN)
    assert "#foms-tablet-ship-grid" in html
    assert "foms_density_target" in html
    assert "tablet_ship_grid.html" in html
    assert 'id="foms-tablet-ship-grid"' in _read(TABLET_GRID)


# --- (3) PC 테이블 마크업은 PC(fine) 리사이즈용으로 유지 ----------------------


def test_dashboard_main_pc_table_keeps_data_col_key() -> None:
    """PC 테이블은 코호트에서 은닉되나 마크업은 유지 — PC(fine) 컬럼 리사이즈용 data-col-key
    (dashboard-columns.js SSOT)는 그대로 있어야 한다."""
    html = _read(DASHBOARD_MAIN)
    for key in ("detail", "spec", "address", "construction_workers", "manager"):
        assert f'data-col-key="{key}"' in html, f"PC 테이블 data-col-key 누락: {key}"
    assert 'data-col-key="construction_time"' in html
    assert 'data-col-key="drawing_managers"' in html


# --- (4) 숨긴 주소는 배정 시트에서 접근 가능 ----------------------------------


def test_tablet_sheet_exposes_site_address() -> None:
    """그리드에서 숨긴 현장주소를 배정 시트에서 노출(order.address)."""
    html = _read(TABLET_SHEET)
    assert "현장주소" in html
    assert "order.address" in html
