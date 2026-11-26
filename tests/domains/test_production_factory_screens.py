"""2공장 생산 화면(설계서 2026-11-23 §4-6 · §4-13 · §5 · §8-1 ~ §8-4 · §11, 3단계 ⑤) — 공장 문 · 도면 판 · 날짜 줄 · PC · '바뀜'.

* 공장 문: 쓰기 API 가 남의 공장 장을 403 ``OTHER_FACTORY`` 로 막는다(관리자는 두 공장, 내가 맡은 장의 맡기 취소는 된다). 막히면 쓰기 0.
* 도면 판: 내 공장 카드 먼저(칸 숫자도 내 공장만), 남의 공장 카드는 판 뒤 묶음 "2공장 작업 n장" — ``data-pp-card`` 없음(누름 · 숫자 밖),
  글 한 줄 + 칩. 관리자는 판 머리 공장 고르기(2공장 그림이 켜졌을 때만).
* 날짜 줄: 섞인 주문 도면 칸 두 줄(보는 공장 줄이 위), 한 공장 계정에게 남의 공장 장만 있는 줄은 만들 것 끝 작은 머리 아래, 내 공장 완료가
  살아 있는 섞인 주문은 '제작 완료' 칸으로. PC 는 두 공장을 합쳐 본다(감독용). PC 도면 목록 창은 줄마다 공장 · 남의 공장 줄 단추 없음.
* '바뀜': 공장 옮김 이벤트가 "공장 바뀜 도면 2/3 1공장 → 2공장".

되돌리면 실패: 공장 문 빠짐 · 남의 공장 카드에 단추 · 칸 숫자에 남의 공장 셈 · 2공장 장 없는 주문에 공장 칸 · PC 줄 묶음 · 반장이 남의 공장
줄 단추를 받음. 대조군: 2공장 장이 없는 주문 · 1공장 계정의 화면은 지금 그대로(바탕 HTML 견줌은 실화면 h).
"""
from __future__ import annotations

import datetime
import re

import pytest

from db import db_session
from foms.services.datetime_kst import now_utc_naive
from foms.services.production.factory_scope import OTHER_FACTORY, elsewhere_line, factory_gate
from foms.services.production.factory_home import drawing_cell
from foms.services.production_change_alerts import collect_production_change_alerts
from models import Order, OrderEvent, ProductionPartMark
from tests.support.production_factory_seed import (
    HOME_NONE,
    PC,
    TABLET,
    factory_user,
    mixed_order,
    put_mark,
    set_cookies,
    set_factory_done,
)
from tests.support.production_part_claim_seed import BULK, fresh, login, mark, row

#: 공장 칩(사장님 2026-11-24 식별성 — 두 공장 모두 같은 칩, foms-factory-chip.css). 글은 그대로 "1공장" · "2공장".
F1 = '<em class="foms-fac foms-fac--1">1공장</em>'
F2 = '<em class="foms-fac foms-fac--2">2공장</em>'
CHIP_CSS = "css/components/foms-factory-chip.css?v="

MSG2 = "2공장에서 작업하는 도면이에요. [다시 받기]를 눌러 주세요."


@pytest.fixture
def cohort(monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")


def _html(client, url: str = HOME_NONE) -> str:
    res = client.get(url)
    assert res.status_code == 200
    return res.get_data(as_text=True)


# --------------------------------------------------------------------------- #
# 공장 문(§4-6 · C6)
# --------------------------------------------------------------------------- #
def test_part_account_cannot_write_other_factory_sheet(client):
    seed = mixed_order(5, f2=(3, 4))
    cut1 = factory_user("김재단", part="cut")
    login(client, cut1)
    res = mark(client, seed, 3, "cut", "take", "none")
    body = res.get_json()
    assert res.status_code == 403 and body["data"]["code"] == OTHER_FACTORY and body["error"] == MSG2
    assert body["data"]["factory"] == 2 and row(seed.id, seed.keys[3], "cut") is None  # 쓰기 0
    assert mark(client, seed, 0, "cut", "take", "none").status_code == 200  # 대조군: 내 공장 장


def test_second_factory_lead_is_blocked_on_first_factory_sheet_and_admin_writes_both(client):
    seed = mixed_order(3, f2=(2,))
    boss2 = factory_user("강반장", factory=2, lead=True)
    login(client, boss2)
    res = mark(client, seed, 0, "edge", "take", "none")
    assert res.status_code == 403 and res.get_json()["error"] == "1공장에서 작업하는 도면이에요. [다시 받기]를 눌러 주세요."
    assert mark(client, seed, 2, "edge", "take", "none").status_code == 200
    admin = factory_user("정관리", role="ADMIN", team="CS")
    login(client, admin)
    assert mark(client, seed, 0, "assemble", "take", "none").status_code == 200
    assert mark(client, seed, 2, "assemble", "take", "none").status_code == 200


def test_own_old_claim_can_be_released_after_the_sheet_moved(client):
    seed = mixed_order(2, f2=())
    edge1 = factory_user("박엣지", part="edge")
    put_mark(seed, 1, "edge", "NEED", edge1)
    mixed = mixed_order(1, f2=())  # 다른 주문(쓰지 않음) — 순서 흔들기
    assert mixed.id != seed.id
    order = db_session.get(Order, seed.id)  # 맡은 뒤 장이 2공장으로 옮겨짐(옛 담당 — 막힘 없이 맡기 취소만)
    sd = dict(order.structured_data)
    sd["drawing_factory"] = {"sheets": {sd["drawing_current_files"][1]["sheet_id"]: 2}}
    order.structured_data = sd
    db_session.commit()
    login(client, edge1)
    assert mark(client, seed, 1, "edge", "done", "need", seen_by=edge1.id).status_code == 403
    assert mark(client, seed, 1, "edge", "release", "need", seen_by=edge1.id).status_code == 200
    assert row(seed.id, seed.keys[1], "edge").state == "NONE"


def test_bulk_basic_skips_other_factory_sheets(client):
    seed = mixed_order(3, f2=(2,))
    cut1 = factory_user("김재단", part="cut")
    login(client, cut1)
    items = [{"order_id": seed.id, "drawing_key": k} for k in seed.keys]
    data = client.post(BULK, json={"part": "cut", "seen": "none", "items": items}).get_json()["data"]
    assert [s["reason"] for s in data["skipped"]] == [OTHER_FACTORY] and len(data["applied"]) == 2
    assert row(seed.id, seed.keys[2], "cut") is None


def test_gate_function_reads_only_the_sheet_and_the_account():
    sd = {"drawing_current_files": [{"key": "k1", "sheet_id": "s1"}], "drawing_factory": {"sheets": {"s1": 2}}}

    class U:  # 이미 읽은 사용자 행 꼴
        id, role, team, is_active, partner_org_id, production_parts, production_part = 7, "STAFF", "PRODUCTION", True, None, ["cut"], "cut"
        production_lead, production_factory = None, None

    gate = factory_gate(U(), sd, {"key": "k1", "sheet_id": "s1"}, action="take")
    assert (gate.status, gate.code, gate.extra) == (403, OTHER_FACTORY, {"factory": 2})
    U.production_factory = 2
    assert factory_gate(U(), sd, {"key": "k1", "sheet_id": "s1"}, action="take") is None


# --------------------------------------------------------------------------- #
# 도면 판(§4-13 · §8-1)
# --------------------------------------------------------------------------- #
def test_board_puts_own_factory_first_and_other_factory_behind(client, cohort):
    seed = mixed_order(5, f2=(3, 4))
    edge2 = factory_user("최가은", factory=2, part="edge")
    put_mark(seed, 3, "edge", "NEED", edge2)
    edge1 = factory_user("박엣지", part="edge")
    login(client, edge1)
    set_cookies(client, TABLET)
    html = _html(client)
    own = re.findall(r'data-pp-card data-order-id="%d" data-key="([^"]+)"' % seed.id, html)
    other = re.findall(r'data-pp-elsewhere data-order-id="%d" data-key="([^"]+)"' % seed.id, html)
    assert own == list(seed.keys[:3]) and other == list(seed.keys[3:])
    assert html.index("data-pp-card ") < html.index(f'<h3 class="pp-otherg">{F2} 작업 2장</h3>') < html.index("data-pp-elsewhere ")
    assert html.count(CHIP_CSS) == 1  # 2공장 그림이 켜진 화면만 칩 모양을 싣는다
    assert 'data-pp-count="all">3<' in html  # 칸 숫자는 내 공장 카드만
    block = html[html.index('<section class="pp-elsewhere"'):html.index("</section>", html.index('<section class="pp-elsewhere"'))]
    assert "data-pp-act" not in block and "data-pp-card" not in block  # 누름 없음
    assert f'{F2} <span data-pp-elsewhere-text>최가은 작업 중</span>' in block  # 칩은 공장 이름만('작업' 두 번 → 한 번, 생산 비평 C29)
    assert f'{F2} 작업 <span data-pp-elsewhere-text>' not in block
    assert block.count('data-pp-why="2공장에서 작업하는 도면이에요."') == 2


def test_second_factory_account_sees_the_reverse(client, cohort):
    seed = mixed_order(5, f2=(3, 4))
    edge2 = factory_user("최가은", factory=2, part="edge")
    login(client, edge2)
    set_cookies(client, TABLET)
    html = _html(client)
    own = re.findall(r'data-pp-card data-order-id="%d" data-key="([^"]+)"' % seed.id, html)
    assert own == list(seed.keys[3:]) and f'<h3 class="pp-otherg">{F1} 작업 3장</h3>' in html
    assert f'<span class="foms-prod-home__date"><b class="fph-fac-now">{F2}</b></span>' in html  # 위 줄 공장 표만(이름 붙는 제목 — 날짜 · 건수 글 뺌, 2026-11-26)


def test_admin_gets_factory_picker_only_when_second_factory_exists(client, cohort):
    admin = factory_user("정관리", role="ADMIN", team="CS")
    login(client, admin)
    set_cookies(client, TABLET)
    mixed_order(3, f2=())
    html = _html(client, "/erp/production/home?tab=parts&part=cut&day=none")
    assert 'aria-label="공장 고르기"' not in html and "pp-elsewhere" not in html and "factory=" not in html
    assert "foms-fac" not in html  # 2공장 장이 없으면 칩 · 칩 모양 파일 없음(바이트 그대로)
    seed = mixed_order(3, f2=(2,))
    html = _html(client, "/erp/production/home?tab=parts&part=cut&day=none")
    assert 'aria-label="공장 고르기"' in html and "factory=2" in html
    assert f'aria-current="page">{F1}</a>' in html and f'factory=2">{F2}</a>' in html  # 고르기 단추도 같은 칩
    html2 = _html(client, "/erp/production/home?tab=parts&part=cut&day=none&factory=2")
    own = re.findall(r'data-pp-card data-order-id="%d" data-key="([^"]+)"' % seed.id, html2)
    assert own == [seed.keys[2]] and f'<h3 class="pp-otherg">{F1} 작업' in html2


def test_elsewhere_line_words():
    assert elsewhere_line("edge", "need", picked="최가은", done=None) == "최가은 작업 중"
    assert elsewhere_line("edge", "need", picked="최가은 · 박엣지", done=None) == "최가은 · 박엣지 작업 중"
    assert elsewhere_line("edge", "need", picked=None, done=None) == "작업 중"
    assert elsewhere_line("edge", "done", picked="최가은", done="최가은") == "엣지 완료 · 최가은"
    assert elsewhere_line("cut", "basic", picked=None, done="김재단") == "기본 · 김재단"
    assert elsewhere_line("cut", "none", picked=None, done=None) == "미정"


# --------------------------------------------------------------------------- #
# 날짜 줄 · PC(§8-2 · §8-4 · §4-14)
# --------------------------------------------------------------------------- #
def test_drawing_cell_two_lines_viewer_first_and_none_without_second_factory():
    sd = {"drawing_current_files": [{"key": f"k{j}", "sheet_id": f"s{j}"} for j in range(5)],
          "drawing_factory": {"sheets": {"s3": 2, "s4": 2}}}
    cell = drawing_cell(sd, 2)
    assert [(line["label"], line["n"], line["me"]) for line in cell["lines"]] == [("2공장", 2, True), ("1공장", 3, False)]
    sd["production"] = {"factory_done": {"2": {"keys": ["k3", "k4"]}}}
    assert drawing_cell(sd, 1)["pc"] == "1공장 3장 · 2공장 2장 완료"
    assert drawing_cell({"drawing_current_files": [{"key": "k"}]}, 1) is None


def test_lead_date_rows_group_other_factory_and_route_own_done(client, cohort):
    only2 = mixed_order(2, f2=(0, 1))
    done2 = mixed_order(3, f2=(2,))
    set_factory_done(done2.id, 2, [done2.keys[2]])
    boss1 = factory_user("박반장", lead=True)
    boss2 = factory_user("강반장", factory=2, lead=True)
    login(client, boss1)
    set_cookies(client, TABLET)
    html = _html(client)
    head = html.index(f'<h3 class="fph-pane__g is-elsewhere">{F2} 작업 <small>1건</small></h3>')
    assert html.index(f'data-foms-home-dayrow="{only2.id}"') > head
    assert f'class="fph-dr is-p is-elsewhere"' in html
    login(client, boss2)
    html = _html(client)
    done_at = html.index('<h3 class="fph-pane__g">제작 완료')
    assert html.index(f'#{done2.id} · {F2} 완료 · {F1} 제작 중') > done_at  # 내 공장 완료 = '제작 완료' 칸
    assert f'<span class="fph-fac is-me">{F2} 1장 <b class="is-ok">완료</b></span>' not in html  # 완료 칸으로 갔다(줄 아님)


def test_pc_rows_are_combined_and_pc_sheet_marks_each_row(client, cohort):
    seed = mixed_order(3, f2=(2,))
    boss1 = factory_user("박반장", lead=True)
    login(client, boss1)
    set_cookies(client, PC)
    html = _html(client)
    assert "is-elsewhere" not in html  # PC 는 묶지 않는다(감독용)
    assert (f'<span class="fpc-dw is-split"><span class="fph-fac is-me">{F1} 2장</span>'
            f'<span class="fph-fac">{F2} 1장</span></span>') in html
    data = client.get(f"/api/production/part-sheet?order_id={seed.id}&part=cut").get_json()["data"]
    assert [(r["factory_label"], r["act"]) for r in data["rows"]] == [("1공장", "check"), ("1공장", "check"), ("2공장", None)]
    assert data["rows"][2]["other_factory"] is True and data["rows"][2]["lines"] == ["담당 미정"]  # 자세히 보임(줄 글 — 2026-11-25 multi-holder K6)
    admin = factory_user("정관리", role="ADMIN", team="CS")
    login(client, admin)
    data = client.get(f"/api/production/part-sheet?order_id={seed.id}&part=cut").get_json()["data"]
    assert [r["act"] for r in data["rows"]] == ["check", "check", "check"]
    plain = mixed_order(2, f2=())
    data = client.get(f"/api/production/part-sheet?order_id={plain.id}&part=cut").get_json()["data"]
    assert all("factory" not in r and "other_factory" not in r for r in data["rows"])  # 한 공장 주문은 지금 그대로


def test_work_sheet_marks_second_factory_thumbs(client, cohort):
    seed = mixed_order(3, f2=(1,))
    login(client, factory_user("박반장", lead=True))
    set_cookies(client, TABLET)
    html = _html(client, f"/erp/production/sheet/{seed.id}")
    assert html.count(f'<span class="fpp-fac">{F2}</span>') == 1 and html.count(CHIP_CSS) == 1
    plain = mixed_order(2, f2=())
    plain_html = _html(client, f"/erp/production/sheet/{plain.id}")
    assert "fpp-fac" not in plain_html and "foms-fac" not in plain_html and CHIP_CSS not in plain_html


# --------------------------------------------------------------------------- #
# '바뀜'(§11)
# --------------------------------------------------------------------------- #
def test_factory_move_event_shows_in_production_changes(client):
    seed = mixed_order(3, f2=())
    db_session.get(Order, seed.id).erp_stage_updated_at = now_utc_naive() - datetime.timedelta(days=1)  # 생산 진입 기준선
    db_session.add(OrderEvent(order_id=seed.id, event_type="DRAWING_SHEET_FACTORY_CHANGED", payload={
        "changes": [{"sheet_id": "x", "key": seed.keys[1], "name": "", "index": 2, "total": 3, "from": 1, "to": 2}],
        "by_name": "오가람", "stage": "PRODUCTION"}, created_at=now_utc_naive() + datetime.timedelta(minutes=5)))
    db_session.commit()
    order = fresh(seed.id)
    alerts = collect_production_change_alerts(db_session, [order], None)[seed.id]["alerts"]
    assert [(a["label"], a["detail"], a["by_name"]) for a in alerts] == [("공장 바뀜", "도면 2/3 1공장 → 2공장", "오가람")]
    assert db_session.query(ProductionPartMark).count() == 0


def test_other_factory_only_order_cards_read_their_marks(client, cohort):
    """남의 공장 장만 있는 주문(날짜 줄 2공장 묶음)의 카드도 같은 표시 줄 읽기로 그린다 — 줄을 빼먹으면 '미정'으로 틀리게 보인다."""
    only1 = mixed_order(2, f2=())
    edge1 = factory_user("박엣지", part="edge")
    put_mark(only1, 0, "edge", "DONE", edge1)
    login(client, factory_user("최가은", factory=2, part="edge"))
    set_cookies(client, TABLET)
    html = _html(client)
    card = html[html.index(f'data-pp-elsewhere data-order-id="{only1.id}" data-key="{only1.keys[0]}"'):]
    assert "<span data-pp-elsewhere-text>엣지 완료 · 박엣지</span>" in card[:3000]
