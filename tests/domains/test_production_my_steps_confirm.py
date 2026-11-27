"""'내 공정' [<공정> 끝] — 도면이 있는 주문만 한 번 묻는다(사장님 2026-11-25 "도면이 있는 주문만 한 번 묻기").

확정 도면이 1장 이상인 주문의 [끝]은 작업 시트 공정 칸과 **같은 창**(``sheet_step_confirm.html``) · **같은 글**(foms-production-sheet-parts.js
``ask``) · **같은 판정**(``beforeToggle`` — 켤 때만 · 카드를 쓴 파트는 묻지 않고 서버가 판정)으로 먼저 묻는다. 도면 없는 주문은 지금처럼 바로 저장,
[되돌리기]는 그대로. 장 수 = 작업 시트 · 공정 API 와 같은 서버 값(``step_api_extras`` — 2공장 계정도 주문 전체 장 수, 작업 시트와 같다).
자료는 서버가 [끝]에 싣는다(``data-foms-sheet-parts`` = 행 ``step_confirm``) — 누를 때 받기(GET)가 없어 공장 와이파이에서도 창이 바로 뜬다.
쿼리 +1 은 [끝]을 그리는 사람 · 도면 있는 막히지 않은 줄이 있을 때만. 보류 · 도면 고치는 중 줄은 [끝] 자리가 막힘 글이라 창보다 먼저다(⑺).
나오는 자리: 태블릿 가로 판 · 폰 · 세로 줄 · PC [고치기] 줄 — 판은 태블릿 가로뿐이고 줄 [끝]이 그 밖을 맡는다(같은 규칙).

되돌리면 실패: 도면 있는 [끝]에 자료가 없음 · 도면 없는 [끝]에 자료가 붙음 · 창이 없거나 둘 · 작업 시트와 다른 창 마크업 · 장 수가 작업 시트와 다름 ·
Node 에서 [취소]에 POST · 두 번 누름이 [작업 완료]로 · 셸 교체 뒤 창 단추가 안 먹음 · 판이 바뀐 뒤 엉뚱한 주문 저장.

2026-11-27 뒤 결정("도면이 주, 작업 시트는 보기" — test_production_steps_view_only_1127): 도면이 1장이라도 있는 줄은 [끝] 자리가 막힘 칸 링크
("재단 0/1 · 1장 미완료", 누르면 그 주문 도면 판)라 누를 단추도 물을 창도 없다. 그래서 "도면 있는 [끝]은 묻는다" 시험은 "도면 있는 줄은 [끝]
없음 · 막힘 칸 · 자료 없음"으로, 창 흐름(Node [취소] · 두 번 누름 · 셸 교체 · 판 바뀜)은 탈 길이 없어 "도면 없는 줄 = 묻지 않고 바로 저장"으로
바꿨다. 장 수(작업 시트 = 공정 API), 창 조각 · 핀 · 겉틀 CSS 한 번, 보기만은 [끝] · 창 없음, 쿼리 +1 은 그대로 본다.
"""
from __future__ import annotations

import html as html_lib
import json
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from sqlalchemy import event

from db import db_session, engine
from models import Order, ProductionPartMark
from tests.support.production_factory_seed import factory_user, mixed_order
from tests.support.production_home_step_panel_seed import HOME, SHELL, TABLET, add_order, get_html, login, pane_html, set_cookies
from tests.support.production_part_claim_seed import login as login_person
from tests.support.production_steps_read import steps_read

ROOT = Path(__file__).resolve().parents[2]
NODE_CHECK = ROOT / "tests/support/production_my_steps_confirm_node_checks.js"
PHONE = {"foms_ptr": "coarse", "foms_vw": "narrow"}
PC = {"foms_ptr": "fine", "foms_vw": "wide", "foms_scr": "1920"}
CONFIRM_ATTR = re.compile(r'data-foms-sheet-parts="([^"]+)"')
PARTS_PIN = "foms-production-sheet-parts.js?v=20261127u"
REASON_CSS = "css/components/foms-reason-sheet.css?v=20261122t"


@pytest.fixture
def cohort(monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")


def _revise(order_id: int) -> None:
    db_session.expire_all()
    order = db_session.get(Order, order_id)
    order.structured_data = {**order.structured_data, "drawing_status": "RETURNED"}
    db_session.commit()


def _seed(pngs: int = 1):
    """재단 줄: 도면 있는 주문(먼저 — 기본 1장) · 도면 없음 · 도면 고치는 중 · 보류 — 시공일 순.

    확인 창은 도면 1장 주문에만 뜬다 — 여러 장이면 [<공정> 완료] 자리가 막힌다(사장님 2026-11-27, test_production_per_sheet_only_1127).
    """
    drawn = add_order("가짜도면집", 1, pngs=pngs)
    bare = add_order("가짜빈집", 2, pngs=0)
    revising = add_order("가짜고침집", 3, pngs=2)
    _revise(revising.id)
    held = add_order("가짜보류집", 4, pngs=2, hold="자재 기다림")
    return drawn, bare, revising, held


def _row(page: str, oid: int) -> str:
    return page.split(f'data-foms-home-qrow="{oid}"', 1)[1].split('data-foms-home-qrow="', 1)[0]


def _data(fragment: str) -> dict:
    return json.loads(html_lib.unescape(CONFIRM_ATTR.search(fragment).group(1)))


def _dialog(page: str) -> str:
    start = page.index('<div class="foms-reason-sheet fpp-confirm" data-foms-sheet-confirm')
    return page[start: page.index("</div>", page.index("data-foms-sheet-confirm-yes", start))]


def _work_sheet_sheets(client, oid: int) -> int:
    page = get_html(client, f"/erp/production/sheet/{oid}")
    return _data(page.split('aria-label="공정"', 1)[1])["sheets"]


def _api_sheets(client, oid: int) -> int:
    return steps_read(client, oid)["sheets"]


CARDS = "재단 0/1 · 1장 미완료"  # 도면 있는 줄의 [끝] 자리(사장님 2026-11-27 "도면이 주, 작업 시트는 보기")


def test_tablet_finish_buttons_carry_the_work_sheet_value_only_on_drawn_rows(client, cohort):
    drawn, bare, revising, held = _seed()
    login(client)  # 반장
    set_cookies(client, TABLET)
    page = get_html(client, HOME + "?tab=steps")
    pane = pane_html(get_html(client, HOME + f"?tab=steps&order={drawn.id}"), drawn.id)  # 막힌 줄은 처음 고른 줄에서 빠진다
    assert "data-foms-step-finish" not in pane and "data-foms-sheet-parts" not in pane and f"<b>{CARDS}</b>" in pane  # 판 [끝] 자리
    row = _row(page, drawn.id)
    assert "data-foms-home-step-done" not in row and "data-foms-sheet-parts" not in row and f">{CARDS}</a>" in row  # 줄 [끝] 자리
    # 같은 서버 값 — 작업 시트 화면 자료 · 공정 API 와 같은 장 수
    assert _work_sheet_sheets(client, drawn.id) == _api_sheets(client, drawn.id) == 1
    # 도면 없는 줄 = 자료 없음(지금처럼 바로 저장 — 단추 마크업 그대로)
    assert f'data-foms-home-step-done data-order-id="{bare.id}" data-step-key="cut"><svg' in _row(page, bare.id)
    # 도면 고치는 중 · 보류 = [끝] 자리가 막힘 글(⑺) — 창보다 먼저, 자료도 없다
    for oid in (revising.id, held.id):  # 자료는 [끝] 단추에만 붙는다 — 그 주문 [끝]이 없으면 자료도 없다
        assert f'data-foms-home-step-done data-order-id="{oid}"' not in page and f'data-foms-step-finish data-order-id="{oid}"' not in page
    # 창 = 화면에 하나, 작업 시트와 같은 조각 · 같은 파일(같은 핀)
    assert page.count("data-foms-sheet-confirm hidden") == 1
    assert _dialog(page) == _dialog(get_html(client, f"/erp/production/sheet/{bare.id}"))
    assert page.count(PARTS_PIN) == 1 and PARTS_PIN in get_html(client, f"/erp/production/sheet/{bare.id}")
    assert page.count(REASON_CSS) == 1  # 겉틀(판 화면은 몸통이 [보류] 사유 창과 같이 싣는다 — 두 번 싣지 않는다)


@pytest.mark.parametrize("where", ["phone", "pc"])
def test_phone_and_pc_rows_use_the_same_data_and_dialog(client, cohort, where):
    drawn, bare, _revising, _held = _seed()
    login(client)
    set_cookies(client, PHONE if where == "phone" else PC)
    if where == "pc":
        client.set_cookie("foms_prod_edit", str(int(time.time())), domain="localhost", path="/erp/production")  # [고치기] 켬(2시간 안)
    page = get_html(client, HOME + "?tab=steps")
    row = _row(page, drawn.id)
    assert "data-foms-sheet-parts" not in row and "data-foms-home-step-done" not in row and f">{CARDS}</a>" in row
    assert "data-foms-sheet-parts" not in _row(page, bare.id) and "data-foms-home-step-done" in _row(page, bare.id)
    assert page.count("data-foms-sheet-confirm hidden") == 1 and page.count(PARTS_PIN) == 1 and page.count(REASON_CSS) == 1


def test_viewers_get_no_button_no_dialog_and_no_extra_query(client, cohort):
    _seed()
    login(client)
    set_cookies(client, PC)  # PC [고치기] 끔 = 보기만
    page = get_html(client, HOME + "?tab=steps")
    assert "data-foms-home-step-done" not in page and "data-foms-sheet-confirm" not in page and PARTS_PIN not in page
    assert REASON_CSS not in page
    login(client, "보기만", lead=False)  # 파트도 반장도 아닌 생산팀(태블릿) — [끝] 없음
    set_cookies(client, TABLET)
    page = get_html(client, HOME + "?tab=steps")
    assert "data-foms-step-finish" not in page and "data-foms-sheet-confirm" not in page and PARTS_PIN not in page


def _count(client, url: str) -> int:
    seen = {"n": 0}

    def _before(*_args):
        seen["n"] += 1

    event.listen(engine, "before_cursor_execute", _before)
    try:
        assert client.get(url).status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", _before)
    return seen["n"]


def test_extra_query_only_for_writers_with_drawn_rows(client, cohort):
    login(client)
    for i in range(3):
        add_order(f"가짜빈줄{i}", i + 1, pngs=0)
    set_cookies(client, TABLET)
    url = HOME + "?tab=steps"
    client.get(url)  # warmup
    bare_only = _count(client, url)
    add_order("가짜도면줄", 5, pngs=2)
    add_order("가짜도면줄2", 6, pngs=1)
    drawn = _count(client, url)
    assert drawn == bare_only + 1, (bare_only, drawn)  # 도면 있는 줄의 표시 줄 한 번(줄 수와 무관)
    set_cookies(client, PC)
    assert _count(client, url) == bare_only  # 보기만(PC [고치기] 끔)은 0개 더함


def test_part_that_uses_cards_shows_left_sheets_instead_of_a_finish_that_is_always_refused(client, cohort):
    """도면 칸을 쓴 파트의 [끝]은 서버가 늘 409 PART_USES_CARDS — [끝] 자리에 남은 장(비평 C03, 대조군 = 도면 칸을 안 쓴 줄은 [끝] 그대로)."""
    drawn, bare, *_ = _seed(3)  # 도면 3장 — 카드를 쓴 파트는 여러 장 막힘(STEP_PER_SHEET)보다 지금 글이 먼저
    db_session.add(ProductionPartMark(order_id=drawn.id, drawing_key="orders/x/drawing/가짜도면집_0.png", part="cut", state="NEED"))
    db_session.commit()
    login(client)
    set_cookies(client, TABLET)
    page = get_html(client, HOME + f"?tab=steps&order={drawn.id}")  # 막힌 줄은 처음 고른 줄에서 빠진다 — 주소로 고른다
    pane = pane_html(page, drawn.id)
    assert "data-foms-step-finish" not in pane and "data-foms-sheet-parts" not in pane
    assert "<b>재단 0/3 · 3장 미완료</b><span>도면 3장이 미완료예요. 남은 도면을 완료하면 자동으로 작업 완료 처리돼요.</span>" in pane
    refused = client.post(f"/api/orders/{drawn.id}/production/steps", json={"key": "cut", "done": True})
    assert refused.status_code == 409 and refused.get_json()["error"] in pane  # 판 글 = 서버 거절 글 그대로
    assert f'data-foms-home-step-done data-order-id="{bare.id}"' in _row(page, bare.id)  # 대조군


def test_second_factory_lead_gets_the_whole_order_count_like_the_work_sheet(client, cohort):
    order = mixed_order(5, f2=(3, 4))
    for factory in (2, 1):
        login_person(client, factory_user(f"가짜반장{factory}", factory=factory, lead=True))
        set_cookies(client, TABLET)
        # 도면 5장(2공장 장 포함) = 여러 장 주문 — 두 공장 반장 모두 [끝] 자리에 주문 전체 장 수(사장님 2026-11-27)
        pane = pane_html(get_html(client, HOME + f"?tab=steps&order={order.id}"), order.id)
        assert "<b>재단 0/5 · 5장 미완료</b>" in pane and "data-foms-step-finish" not in pane
        assert _work_sheet_sheets(client, order.id) == _api_sheets(client, order.id) == 5


def _node(tmp_path, page: str, want: dict) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 없음")
    path = tmp_path / f"{want['mode']}_{want.get('first')}.html"
    path.write_text(page, encoding="utf-8")
    proc = subprocess.run([node, str(NODE_CHECK), str(path), json.dumps(want, ensure_ascii=False)], capture_output=True, text=True,
                          encoding="utf-8", timeout=60)
    assert proc.returncode == 0 and proc.stdout.strip().endswith("OK"), proc.stdout + proc.stderr


WORDS = {"key": "cut", "cards": CARDS}


def test_node_tablet_panel_asks_once_cancel_posts_nothing_and_double_tap_is_dropped(client, cohort, tmp_path):
    """옛 "한 번 묻기" 판 — 도면 있는 줄은 이제 [끝]이 없다(막힘 칸 링크 · 창 숨김 · 요청 0, 사장님 2026-11-27)."""
    drawn, bare, _revising, _held = _seed()
    login(client)
    set_cookies(client, TABLET)
    page = get_html(client, HOME + f"?tab=steps&order={drawn.id}&view=fragment", SHELL)
    _node(tmp_path, page, {"mode": "panel", "first": drawn.id, "sheets": 1, **WORDS})


def test_node_tablet_panel_without_drawings_saves_at_once(client, cohort, tmp_path):
    bare = add_order("가짜빈집", 1, pngs=0)
    add_order("가짜도면집", 2, pngs=3)
    login(client)
    set_cookies(client, TABLET)
    page = get_html(client, HOME + "?tab=steps&view=fragment", SHELL)
    _node(tmp_path, page, {"mode": "panel", "first": bare.id, "sheets": 0, **WORDS})


@pytest.mark.parametrize("where", ["phone", "pc"])
def test_node_rows_ask_only_for_drawn_orders(client, cohort, tmp_path, where):
    drawn, bare, _revising, _held = _seed()
    login(client)
    set_cookies(client, PHONE if where == "phone" else PC)
    if where == "pc":
        client.set_cookie("foms_prod_edit", str(int(time.time())), domain="localhost", path="/erp/production")
    page = get_html(client, HOME + "?tab=steps&view=fragment", SHELL)
    _node(tmp_path, page, {"mode": "row", "first": drawn.id, "bare": bare.id, **WORDS})


def test_js_contract_and_css_same_values_as_the_work_sheet():
    steps = (ROOT / "static/js/production/foms-production-home-steps.js").read_text(encoding="utf-8")
    home = (ROOT / "static/js/production/foms-production-home.js").read_text(encoding="utf-8")
    parts = (ROOT / "static/js/production/foms-production-sheet-parts.js").read_text(encoding="utf-8")
    for src in (steps, home):
        assert len(src.splitlines()) <= 300
        assert "sp.beforeToggle(btn, btn, true," in src and "btn.hasAttribute('data-foms-sheet-parts')" in src
        assert "document.contains(btn)" in src  # 창이 뜬 사이 단추가 화면에서 빠지면 저장하지 않는다
        assert "완료할까요" not in src  # 글은 sheet-parts.js 한 곳
    assert "document.addEventListener(" not in steps and re.findall(r"'/api/[^']*'", steps) == ["'/api/orders/'"]
    assert "var OPEN_GUARD_MS = 400;" in parts and "if (!S.bound) {" in parts and "S.api.close(" in parts
    assert "btn.getAttribute('data-foms-sheet-step') || btn.getAttribute('data-step-key')" in parts
    assert "page.hasAttribute('data-foms-sheet-parts') ? page :" in parts
    css = (ROOT / "static/css/contexts/production/home.css").read_text(encoding="utf-8")
    sheet = (ROOT / "static/css/contexts/production/sheet.css").read_text(encoding="utf-8")
    body = "margin: 0 0 14px; font-size: calc(17px * var(--foms-fs, 1)); font-weight: 600; line-height: 1.5;"
    assert f".foms-prod-home .fpp-confirm-body {{ {body} color: var(--fph-text); word-break: keep-all; }}" in css and body in sheet
    for rule in ("gap: max(8px, calc(8px / var(--foms-ui-zoom, 1)))", "min-height: calc(48px / var(--foms-ui-zoom, 1))"):  # 11-27 단추 48px 이상
        assert rule in css.split("/* ── 내 공정 [<공정> 끝] 확인 창", 1)[1].split("/* ──", 1)[0] and rule in sheet
