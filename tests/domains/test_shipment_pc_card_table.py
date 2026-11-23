"""PC 출고 탭 — 표 안쪽 카드 모양 계약 (설계서 docs/specs/2026-11-23-pc-shipment-card-table_SPEC.md §4.1).

PC 표(#shipment-dashboard-table)를 그대로 두고 모양만 바꾼다:
  - 줄 순서 · 번호 · 사람 색 = 태블릿 하루치 출고표와 같은 값(pc_card_rows) — 시공자 없음 묶음이 맨 위.
  - 줄 식별(class="shipment-row" · data-order-id) · 시공자 목록(ul.shipment-workers-list)은 그대로 — 이미지 저장 ·
    AS 추천 · 폰 늦게 받기가 읽는다. 카드 정보는 data-card 로만 얹는다.
  - 시공자 칸 단추(이름판) · 틈 줄 · 번호는 PC 문지기(pc-card-table.css) 밖에서는 숨는다.
  - 칸 세로 선 인라인 스타일은 CSS 로 옮겼다.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from werkzeug.security import generate_password_hash

from db import db_session
from models import User

ROOT = Path(__file__).resolve().parents[2]
PC_GATE = "@media (min-width: 992px) and (pointer: fine)"
MOUSE_PC = {"foms_ptr": "fine", "foms_vw": "wide", "foms_scr": "1920"}


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _order(oid: int, workers: list[str], status: str = "CONSTRUCTION"):
    return SimpleNamespace(
        id=oid, status=status, is_erp_order=True, shipment_visible_items=[],
        structured_data={"shipment": {"construction_workers": workers}, "items": []},
    )


def test_pc_card_rows_순서_번호_카드_경계() -> None:
    """시공자 없음 → 설정 순 → 그 밖. 카드 = 첫 시공자 묶음, 덩어리 = 같은 구성끼리 이어진다."""
    from foms.services.shipment.tablet_day_sheet import build_tablet_day_sheet, pc_card_rows

    rows = [_order(1, ["나"]), _order(2, []), _order(3, ["가"]), _order(4, ["가", "나"]), _order(5, ["가"]), _order(6, [])]
    sheet = build_tablet_day_sheet(rows, [{"name": "가", "capacity": 60}, {"name": "나", "capacity": 60}], "2026-11-23")
    out = pc_card_rows(sheet)

    assert [o.id for o in out] == [2, 6, 3, 4, 5, 1]
    assert [o.pc_card["no"] for o in out] == [1, 2, 3, 4, 5, 6]
    cards = {o.id: o.pc_card for o in out}
    assert cards[2]["miss"] and cards[6]["miss"] and not cards[3]["miss"]
    assert cards[2]["count"] == 2 and cards[3]["count"] == 3 and cards[1]["count"] == 1
    assert (cards[2]["first"], cards[2]["last"]) == (True, False)
    assert (cards[6]["first"], cards[6]["last"]) == (False, True)
    assert (cards[1]["first"], cards[1]["last"]) == (True, True)
    # '가' 카드: 3(가) · 4(가+나) · 5(가) — 구성이 달라 덩어리가 줄마다 끊긴다.
    assert [(cards[i]["blob_top"], cards[i]["blob_bottom"]) for i in (3, 4, 5)] == [(True, True)] * 3
    # 시공자 없음 두 줄은 같은 구성(빈 값)이라 위아래로 이어진다.
    assert (cards[2]["blob_top"], cards[2]["blob_bottom"]) == (True, False)
    assert (cards[6]["blob_top"], cards[6]["blob_bottom"]) == (False, True)
    assert [w["name"] for w in cards[4]["workers"]] == ["가", "나"]
    assert pc_card_rows(None) == [] and pc_card_rows({"groups": []}) == []


def _login(client, monkeypatch, username: str, team: str = "CS", role: str = "ADMIN") -> None:
    user = User(username=username, password=generate_password_hash("x"), role=role, team=team, name=username, is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _seed(today: str) -> list[int]:
    from models import Order, OrderScheduleDate

    ids = []
    for i, workers in enumerate([["가짜기사B"], [], ["가짜기사A", "가짜기사C"], ["가짜기사B"]]):
        sd = {"workflow": {"stage": "CONSTRUCTION"}, "shipment": {"construction_workers": workers},
              "schedule": {"construction": {"date": today}}, "items": [{"product_name": "붙박이장", "spec_width": "1200"}]}
        o = Order(received_date=today, customer_name=f"가짜카드{i}", phone="010-0000-0000", address="가짜시 가짜로 1",
                  product="붙박이장", status="CONSTRUCTION", manager_name="가짜영업", is_erp_order=True, structured_data=sd,
                  erp_stage_code="CONSTRUCTION", scheduled_date=today)
        db_session.add(o)
        db_session.flush()
        db_session.add(OrderScheduleDate(order_id=o.id, kind="construction", date=today, source="beta_schedule"))
        ids.append(o.id)
    db_session.commit()
    return ids


def test_pc_표_렌더_카드_순서와_시공자_단추(client, monkeypatch) -> None:
    from foms.services.erp_display import get_today_kst

    _login(client, monkeypatch, "pc_card_table_admin")
    ids = _seed(get_today_kst().isoformat())
    for name, value in MOUSE_PC.items():
        client.set_cookie(name, value, domain="localhost")
    res = client.get("/erp/shipment")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    table = html[html.index('id="shipment-dashboard-table"'):]
    table = table[:table.index("</table>")]

    assert 'data-ship-card="1"' in html[html.index('id="shipment-dashboard-table"') - 200:html.index('id="shipment-dashboard-table"') + 200]
    # 줄 식별은 그대로(폰 늦게 받기 · 이미지 저장 · AS 추천이 읽는다).
    for oid in ids:
        assert f'id="shipment-row-{oid}" data-order-id="{oid}" class="shipment-row"' in table, oid
    # 순서: 시공자 없음(ids[1]) 이 맨 위, 같은 시공자(B: ids[0] · ids[3])는 붙어 있다.
    order = [int(m) for m in re.findall(r'<tr id="shipment-row-(\d+)"', table)]
    assert order[0] == ids[1]
    assert abs(order.index(ids[0]) - order.index(ids[3])) == 1
    assert "시공자 없음 1건" in table
    miss_row = re.search(rf'<tr id="shipment-row-{ids[1]}"[^>]*>', table).group(0)
    assert re.search(r'data-card="[^"]*\bmiss\b', miss_row) and "first" in miss_row and "last" in miss_row
    # 카드 틈 줄 = 묶음 수(없음 · A · B).
    assert table.count('<tr class="shipment-card-gap') == 3
    # 시공자 칸: 예전 목록은 그대로 + 이름판 단추. 고칠 수 있는 계정이라 단추마다 주문 번호 · 이름 배열이 실린다.
    assert table.count('class="shipment-edit-list shipment-workers-list') == 4
    assert table.count("data-ship-worker-cell") == 4
    assert re.search(rf'data-ship-worker-cell data-order-id="{ids[2]}"', table)
    two = table[table.index(f'data-ship-worker-cell data-order-id="{ids[2]}"'):]
    two = two[:two.index("</button>")]
    assert "가짜기사A" in two and "가짜기사C" in two and two.count('data-ship-color="') == 2
    assert "＋ 시공자" in table
    # 이름판 자료는 표 래퍼에.
    wrapper = re.search(r'<div class="table-responsive shipment-table-wrapper"[^>]*>', html).group(0)
    assert "data-ship-people='" in wrapper and 'data-ship-can-assign="true"' in wrapper


def test_보기만_하는_계정은_눌리지_않는_단추(client, monkeypatch) -> None:
    """영업팀은 출고 배정 권한이 없다(D31) — 사람 색 덩어리는 보이되 이름판은 안 열린다."""
    from foms.services.erp_display import get_today_kst

    _login(client, monkeypatch, "pc_card_table_sales", team="SALES", role="STAFF")
    _seed(get_today_kst().isoformat())
    res = client.get("/erp/shipment")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    if 'id="shipment-dashboard-table"' not in html:
        return  # 이 계정 범위에 줄이 없으면 표가 비어 온다(범위 규칙은 다른 시험 몫).
    assert "data-ship-worker-cell" not in html
    assert 'data-ship-can-assign="false"' in html or "shipment-wk-btn" not in html


def test_템플릿_칸_세로_선은_css_로() -> None:
    tpl = _read("templates/shipment/partials/dashboard_main.html")
    assert "border-right: 1px solid #e0e0e0" not in tpl
    extras = _read("static/css/contexts/shipment/dashboard-table-extras.css")
    assert "#shipment-dashboard-table > tbody > tr.shipment-row > td:not(:last-child)" in extras
    assert "border-right: 1px solid #e0e0e0;" in extras
    # PC 카드 전용 마크업은 문지기 밖 기본이 숨김.
    for sel in (".shipment-card-gap", ".shipment-card-no", ".shipment-th-no", ".shipment-wk-btn"):
        assert f"#shipment-dashboard-table {sel}" in extras, sel


def test_pc_card_css_는_전부_pc_문지기_안() -> None:
    css = _read("static/css/contexts/shipment/pc-card-table.css")
    body = re.sub(r"/\*.*?\*/", "", css, flags=re.S).strip()
    assert body.startswith(PC_GATE) and body.count("@media") == 1 and body.endswith("}")
    assert "body.erp-mobile-v2-layout" not in body  # 태블릿 코호트 규칙을 건드리지 않는다
    # 글자를 줄이지 않는다 — 표 안 글자 크기는 손대지 않고, 이름판 글자는 13px 이상.
    sizes = [float(n) for n in re.findall(r"font-size:\s*calc\((\d+(?:\.\d+)?)px \* var\(--foms-fs, 1\)\)", body)]
    assert sizes and min(sizes) >= 13
    assert len(re.findall(r"font-size:", body)) == len(sizes)
    # 사람 색 10개 = 태블릿 띠와 같은 값 · 같은 순서.
    strip = _read("static/css/components/foms-tablet-day-strip.css")
    for n in range(1, 11):
        color = re.search(rf'\[data-ship-color="{n}"\] {{ --ship-pc: (#[0-9A-Fa-f]{{6}}); }}', strip).group(1)
        assert f'#shipment-dashboard-table [data-ship-color="{n}"], .foms-ship-names [data-ship-color="{n}"] {{ --ship-pc: {color}; }}' in body, n
    # PC 이름판은 글자 입력 칸이 늘 열려 있다(사장님 2026-11-23).
    assert ".foms-ship-names__write[hidden]" in body and '[data-ship-act="write"] { display: none; }' in body


def test_js_pc_카드에서는_줄을_옮기지_않고_이름판은_표에서도_열린다() -> None:
    dash = _read("static/js/shipment/shipment-dashboard.js")
    start = dash.index("function applyShipmentWorkerSortAndColors()")
    assert "if (isPcCardTable()) return;" in dash[start:start + 200]
    assert "window.matchMedia('(min-width: 992px) and (pointer: fine)')" in dash
    assign = _read("static/js/shipment/tablet-ship-assign.js")
    assert "btn.closest('[data-ship-people]')" in assign
    entry = _read("static/js/shipment/shipment-entry.js")
    assert "/static/js/shipment/pc-ship-sheet.js?v=" in entry
    tpl = _read("templates/shipment/partials/dashboard_main.html")
    assert "css/contexts/shipment/pc-card-table.css') }}?v=" in tpl and "css/contexts/shipment/pc-ship-sheet.css') }}?v=" in tpl
