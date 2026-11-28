"""생산 태블릿 비평 갈래 가 — 동작 고침(2026-11-26, 비평 C02 · C03 · C06 · C09).

* C02 공정 칸 쓰기의 공장 문: 장이 **모두** 남의 공장인 주문은 반장도 403 ``OTHER_FACTORY``(도면 칸과 같은 글) — 켜기 · 끄기 · 통째 작업 풀어 쓰기
  모두. 섞인 주문 · 관리자 · 자기 공장 반장은 지금 그대로(대조군). '내 공정' 줄 · 판 · PC 줄은 그 주문 [끝] 자리에 "2공장 작업"(누름 없음), 줄 끝으로.
* C03 그 파트가 도면 칸을 쓴 주문의 [끝](늘 409 ``PART_USES_CARDS``) 대신 "재단 1/3 · 2장 미완료" + 거절 글, 누르면 그 주문 도면 판.
* C06 30초 받아 오기가 주문마다 지금 막힘(보류 · 도면 고치는 중 · 생산 단계 아님)을 같은 쿼리 한 번에 싣고, 판 JS 가 카드를 막힘 칸으로 다시
  그린다(거절 409 를 받아도 바로). 머리 줄 받은 때는 받을 때마다 새로.
* C09 도면 칸으로 제작 완료한 뒤 그 주문 카드에 [되돌리기] 대신 "제작 완료"(받아 오기의 생산 단계 아님 칸과 같은 값).

이름은 모두 지어낸 값이다. JS 는 서버가 그린 진짜 판 위에서 Node 로 돌리고, 서버 답은 진짜 API 응답 JSON 이다.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from html import unescape
from pathlib import Path

import pytest

from db import db_session
from foms.services.production.factory_chip import factory_chips
from foms.services.production.part_mark_gates import HOLD_MESSAGE, REVISING_MESSAGE
from foms.services.production.part_mark_write import NOT_IN_PRODUCTION_MESSAGE
from foms.services.production.sync_blocks import DONE_WHY
from models import ProductionPartMark
from tests.support.production_factory_seed import HOME_NONE, PC, TABLET, factory_user, mixed_order, put_mark, set_cookies
from tests.support.production_part_claim_seed import (
    check_step,
    code,
    fresh,
    keep_mine_on_date_board,
    login,
    make_order,
    make_user,
    mark,
    patch_sd,
)
from tests.domains.test_production_home_query_count import _count_queries
from tests.support.production_steps_read import steps_read

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "tests/support/production_multi_holder_node_checks.js"
STEPS = "/erp/production/home?tab=steps"
SYNC = "/api/production/part-marks"
F2_CHIP = str(factory_chips("2공장 작업"))
ELSEWHERE_WHY = "2공장에서 작업하는 도면이에요."


@pytest.fixture
def cohort(monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")


def _page(client, url: str, cookies: dict = TABLET) -> str:
    set_cookies(client, cookies)
    resp = client.get(url)
    assert resp.status_code == 200, url
    return resp.get_data(as_text=True)


def _row(page: str, oid: int) -> str:
    return page.split(f'data-foms-home-qrow="{oid}"', 1)[1].split('data-foms-home-qrow="', 1)[0].split("곧 올 것", 1)[0]


def _pane(page: str, oid: int) -> str:
    return page.split(f'data-foms-step-pane="{oid}"', 1)[1].split("</section>", 1)[0]


def _node(page: Path, want: dict) -> dict:
    node = shutil.which("node")
    assert node, "node must be on PATH for JS checks"
    proc = subprocess.run([node, str(CHECK), str(page), json.dumps(want, ensure_ascii=False)], capture_output=True, text=True,
                          encoding="utf-8", timeout=60, cwd=str(ROOT))
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _synced(client, *oids: int) -> dict:
    resp = client.get(SYNC, query_string={"order_ids": ",".join(map(str, oids)), "since": "2000-01-01T00:00:00"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()


# --------------------------------------------------------------------------- #
# C02 — 공정 칸 쓰기의 공장 문
# --------------------------------------------------------------------------- #
def test_steps_api_refuses_an_order_whose_sheets_are_all_in_the_other_factory(client):
    only2 = mixed_order(1, f2=(0,))  # 도면 1장(여러 장은 공장 문을 지나도 켜기가 막힌다 — 사장님 2026-11-27)
    mixed = mixed_order(3, f2=(2,))
    lead1 = factory_user("박반장", lead=True)
    login(client, lead1)
    for done in (True, False):  # 켜기 · 끄기 모두
        refused = check_step(client, only2.id, "cut", done)
        body = refused.get_json()
        assert refused.status_code == 403 and code(refused) == "OTHER_FACTORY" and body["data"]["factory"] == 2
        assert body["error"] == ELSEWHERE_WHY + " [다시 받기]를 눌러 주세요."  # 도면 칸 남의 공장 거절과 같은 글
    assert fresh(only2.id).structured_data["production"]["steps"][0]["done"] is False  # 쓰기 0
    # 누르기 전에 — 공정 판정(작업 시트와 같은 조합, steps_read) · 작업 시트 공정 칸도 같은 판정으로 읽기 전용 + 남의 공장 카드 글
    got = steps_read(client, only2.id)
    assert (got["locked"], got["locked_note"]) == (True, ELSEWHERE_WHY)
    assert steps_read(client, mixed.id)["locked"] is False
    set_cookies(client, TABLET)  # 공정 칸이 단추로 그려지는 기기(터치)
    sheet = client.get(f"/erp/production/sheet/{only2.id}").get_data(as_text=True)
    # 도면 있는 주문의 공정 칸 = 보기 줄(사장님 2026-11-27 "도면이 주, 작업 시트는 보기") — 잠금 글은 그대로, 누를 체크 칸 없음
    assert f"data-foms-sheet-steps-locked>{ELSEWHERE_WHY}</p>" in sheet and 'data-foms-sheet-line="cut"' in sheet
    assert "data-foms-sheet-step=" not in sheet.split('aria-label="공정"', 1)[1].split("</section>", 1)[0]
    assert "data-foms-sheet-steps-locked" not in client.get(f"/erp/production/sheet/{mixed.id}").get_data(as_text=True)
    # 섞인 주문 = 공장 문은 지나간다(판결 A) — 도면이 여러 장이라 그다음 문에서 막힌다(409 STEP_PER_SHEET, 사장님 2026-11-27)
    assert code(check_step(client, mixed.id, "cut", True)) == "STEP_PER_SHEET"
    login(client, factory_user("최반장", factory=2, lead=True))
    # 그 공장 반장 · 관리자(두 공장)는 공장 문을 지나 다음 문 — 도면이 있어 409 STEP_PER_SHEET(사장님 2026-11-27 "도면이 주, 작업 시트는 보기", 옛 단언 200)
    assert code(check_step(client, only2.id, "cut", True)) == "STEP_PER_SHEET"
    login(client, make_user("오관리", role="ADMIN", team="CS"))
    assert code(check_step(client, only2.id, "edge", True)) == "STEP_PER_SHEET"
    login(client, make_user("한상담", team="CS"))  # 보기만 — 공장 글 없음(지금 그대로)
    assert "data-foms-sheet-steps-locked" not in client.get(f"/erp/production/sheet/{only2.id}").get_data(as_text=True)


def test_whole_step_expand_on_an_other_factory_order_is_refused_before_writing(client):
    """막힌 도면이 있어 통째 작업이 도면별 풀어 쓰기로 가는 길도 같은 문(쓰기 · 이벤트 0)."""
    only2 = mixed_order(2, f2=(0, 1))
    order = fresh(only2.id)
    sd = dict(order.structured_data)
    sd["drawing_fix"] = {"fixing": {f"sheet:{sd['drawing_current_files'][1]['sheet_id']}": {"no": 2, "by_name": "김도면"}}}
    order.structured_data = sd
    db_session.commit()
    login(client, factory_user("최반장", factory=2, lead=True))  # 대조군 — 그 공장 반장은 공장 문을 지나 다음 문(도면 여러 장, 사장님 2026-11-27)
    passed = check_step(client, only2.id, "edge", True)
    assert passed.status_code == 409 and code(passed) == "STEP_PER_SHEET" and "expanded" not in passed.get_json()["data"]
    assert db_session.query(ProductionPartMark).filter_by(order_id=only2.id).count() == 0  # 풀어 쓰기 없음 · 쓰기 0
    login(client, factory_user("박반장", lead=True))
    refused = check_step(client, only2.id, "cut", True)
    assert refused.status_code == 403 and code(refused) == "OTHER_FACTORY"
    assert "expanded" not in (refused.get_json().get("data") or {})


def test_my_steps_screen_draws_no_finish_for_other_factory_orders_and_puts_them_last(client, cohort):
    only2 = mixed_order(1, f2=(0,))  # 도면 1장 — 공장 막힘("2공장 작업")이 도면 막힘보다 먼저
    mine = make_order(0)  # 대조군 — [끝]이 남는 도면 0장 주문(사장님 2026-11-27 "도면이 주, 작업 시트는 보기")
    login(client, factory_user("박반장", lead=True))
    page = _page(client, STEPS)
    cut = page.split('data-foms-home-stepq="cut"', 1)[1].split('data-foms-home-stepq="edge"', 1)[0]
    assert cut.index(f'data-foms-home-qrow="{mine.id}"') < cut.index(f'data-foms-home-qrow="{only2.id}"')  # 남의 공장 줄은 끝으로
    row = _row(page, only2.id)
    assert "data-foms-home-step-done" not in row and f'<span class="fph-qr__hold is-elsewhere" title="{ELSEWHERE_WHY}">{F2_CHIP}</span>' in row
    assert f'<div class="fph-qr is-elsewhere" data-foms-home-qrow="{only2.id}"' in page  # 날짜 탭 남의 공장 줄과 같은 이름(꾸밈은 CSS 몫)
    assert f'data-foms-home-step-done data-order-id="{mine.id}"' in _row(page, mine.id)  # 대조군 — 내 공장 주문
    pane = _pane(_page(client, STEPS + f"&order={only2.id}"), only2.id)
    assert "data-foms-step-finish" not in pane and f"<b>{F2_CHIP}</b><span>{ELSEWHERE_WHY}</span>" in pane
    set_cookies(client, PC)
    client.set_cookie("foms_prod_edit", str(int(time.time())), domain="localhost", path="/erp/production")  # [고치기] 켬
    pc = client.get(STEPS).get_data(as_text=True)
    assert f'data-foms-home-step-done data-order-id="{only2.id}"' not in pc and f'<span class="fpc-hold is-elsewhere" title="{ELSEWHERE_WHY}">' in pc
    login(client, make_user("오관리", role="ADMIN", team="CS"))  # 관리자 = 두 공장 — 공장 막힘 없음(도면이 있어 [끝] 자리는 막힘 칸, 사장님 2026-11-27 "도면이 주, 작업 시트는 보기")
    admin_row = _row(_page(client, STEPS), only2.id)
    assert "is-elsewhere" not in admin_row and ">재단 0/1 · 1장 미완료</a>" in admin_row


# --------------------------------------------------------------------------- #
# C03 — 도면 칸을 쓴 파트의 [끝] 자리
# --------------------------------------------------------------------------- #
def test_part_that_uses_cards_shows_left_sheets_and_links_to_the_board(client, cohort):
    order = make_order(3)
    kim = make_user("김재단", part="cut")
    put_mark(order, 0, "cut", "DONE", kim)
    bare = make_order(0)  # 대조군 — 도면 칸을 안 쓴 주문(도면 0장 — 도면이 있으면 [끝] 자리가 막힌다, 사장님 2026-11-27 "도면이 주, 작업 시트는 보기")
    login(client, make_user("박반장", lead=True))
    refused = check_step(client, order.id, "cut", True)
    assert refused.status_code == 409 and code(refused) == "PART_USES_CARDS"
    why = refused.get_json()["error"]
    page = _page(client, STEPS)
    href = f"/erp/production/home?tab=parts&amp;part=cut&amp;order={order.id}"
    row = _row(page, order.id)
    assert "data-foms-home-step-done" not in row and "data-foms-sheet-parts" not in row
    assert f'<a class="fph-qr__hold is-cards" href="{href}" data-foms-step-cards title="{why}">재단 1/3 · 2장 미완료</a>' in row
    assert f'data-foms-home-step-done data-order-id="{bare.id}"' in _row(page, bare.id)
    pane = _pane(_page(client, STEPS + f"&order={order.id}"), order.id)
    assert f'<a class="fph-sp__hold is-cards" href="{href}" data-foms-step-cards><b>재단 1/3 · 2장 미완료</b><span>{why}</span></a>' in pane
    board = _page(client, href.replace("&amp;", "&"))  # 누른 곳 = 그 주문 도면 판(카드가 선 날 장)
    assert board.count(f'data-pp-card data-order-id="{order.id}"') == 3
    phone = _page(client, STEPS, {"foms_ptr": "coarse", "foms_vw": "narrow"})
    assert f'href="{href}" data-foms-step-cards' in _row(phone, order.id)  # 판이 없는 화면(폰 · 세로)도 같은 칸


def test_my_steps_query_count_is_unchanged_by_the_new_blocks(client, cohort):
    """새 막힘(C02 · C03)은 이미 읽은 주문 JSON · 표시 줄로 — 줄 수가 늘어도 쿼리가 같다."""
    login(client, factory_user("박반장", lead=True))
    set_cookies(client, TABLET)
    order = make_order(3)
    put_mark(order, 0, "cut", "DONE", make_user("김재단", part="cut"))
    client.get(STEPS)
    small = _count_queries(lambda: client.get(STEPS))[1]
    for _ in range(3):
        mixed_order(2, f2=(0, 1))
        extra = make_order(3)
        put_mark(extra, 1, "cut", "NEED", make_user("이시영", part="cut"))
    resp, big = _count_queries(lambda: client.get(STEPS))
    assert big == small and resp.get_data(as_text=True).count("data-foms-step-cards") >= 4, (small, big)


# --------------------------------------------------------------------------- #
# C06 — 받아 오기의 주문 막힘
# --------------------------------------------------------------------------- #
def test_sync_carries_each_orders_block_in_the_same_single_read(client):
    free, held, whole, part, done = (make_order(2) for _ in range(5))
    patch_sd(held.id, hold={"active": True, "reason": "자재 기다림"})
    for seed, extra in ((whole, {"drawing_status": "RETURNED"}),
                        (part, {"drawing_fix": {"fixing": {f"sheet:{part.keys[1].split('/')[0]}-s1": {"no": 2}}}}),
                        (done, {"workflow": {"stage": "CONSTRUCTION"}})):
        order = fresh(seed.id)
        order.structured_data = {**order.structured_data, **extra}
        if seed is done:
            order.erp_stage_code = "CONSTRUCTION"
        db_session.commit()
    kim = make_user("김재단", part="cut")
    put_mark(free, 0, "cut", "NEED", kim)
    put_mark(free, 1, "cut", "NEED", kim)  # 바뀐 표시 줄이 둘인 주문도 막힘은 한 번
    login(client, kim)
    data = _synced(client, free.id, held.id, whole.id, part.id, done.id)["data"]
    blocks = data["blocks"]
    assert len(data["marks"]) == 2 and blocks[str(free.id)] == {"all": None, "keys": {}}
    assert blocks[str(held.id)]["all"] == {"kind": "hold", "text": "보류 · 자재 기다림", "why": HOLD_MESSAGE, "code": "HOLD_ACTIVE"}
    assert blocks[str(whole.id)]["all"]["text"] == "도면 수정 중" and blocks[str(whole.id)]["all"]["why"] == REVISING_MESSAGE
    assert blocks[str(part.id)]["all"] is None and list(blocks[str(part.id)]["keys"]) == [part.keys[1]]  # 그 장만
    assert blocks[str(done.id)]["all"] == {"kind": "done", "text": "제작 완료", "why": DONE_WHY,
                                           "code": "NOT_IN_PRODUCTION"}


def _hold_flow(client, tmp_path):
    order = make_order(2)
    kim = make_user("김재단", part="cut")
    login(client, kim)
    page = tmp_path / "kim.html"
    page.write_text(_page(client, HOME_NONE), encoding="utf-8")
    held = client.post(f"/api/orders/{order.id}/production/hold", json={"active": True, "reason": "자재 기다림"})
    assert held.status_code == 200, held.get_json()  # 사무실이 보류로 돌림(진짜 보류 API — 화면은 모름)
    return order, kim, page


def test_js_sync_redraws_the_orders_cards_as_held_and_back(client, cohort, tmp_path):
    order, _kim, page = _hold_flow(client, tmp_path)
    held = _synced(client, order.id)
    released = client.post(f"/api/orders/{order.id}/production/hold", json={"active": False})  # 보류 풀기 = 버전 +1(막힘 캐시 새로)
    assert released.status_code == 200, released.get_json()
    free = _synced(client, order.id)
    assert free["data"]["blocks"][str(order.id)]["all"] is None
    res = _node(page, {"sync": True, "gets": [held, free],
                       "steps": [{"do": "sync"}, {"do": "card", "key": order.keys[0]}, {"do": "card", "key": order.keys[1]},
                                 {"do": "sync"}, {"do": "card", "key": order.keys[0]}]})
    for card in (res["out"][1]["card"], res["out"][2]["card"]):
        assert card["act"] == [{"tag": "button", "cls": "fph-wi pp-act pp-st-hold", "act": None, "text": "보류 · 자재 기다림", "kids": []}]
    assert res["out"][1]["counts"]["unseen"] == ["0"]  # 막힌 안 본 장은 [남은 n장 모두 기본]에서 빠진다(판이 그릴 때와 같다)
    back = res["out"][4]["card"]["act"][0]  # 보류가 풀리면 단추가 돌아온다
    assert [k["act"] for k in back["kids"]] == ["basic", "take"]
    assert res["out"][4]["counts"]["unseen"] == ["2"]


def test_js_sync_skips_a_card_in_the_confirm_window_and_draws_it_on_the_next_sync(client, cohort, tmp_path):
    """30초 받아 오기의 막힘 칸도 표시 줄처럼 확인 창 · 저장 중 카드는 건너뛴다(누르는 칸이 바뀌지 않게) — 저장이 끝난 뒤 다음 받아 오기에서
    막힘 칸. 같은 판의 다른 카드는 바로 막힘 칸."""
    order = make_order(2)
    kim = make_user("김재단", part="cut")
    login(client, kim)
    page = tmp_path / "kim.html"
    page.write_text(_page(client, HOME_NONE), encoding="utf-8")
    took = mark(client, order, 0, "cut", "take", "none")  # 확인 창에서 누를 [작업 시작]의 진짜 답(보류 전에 저장됨)
    assert took.status_code == 200
    patch_sd(order.id, hold={"active": True, "reason": "자재 기다림"})  # 그사이 사무실이 보류
    held = _synced(client, order.id)
    hold_chip = {"tag": "button", "cls": "fph-wi pp-act pp-st-hold", "act": None, "text": "보류 · 자재 기다림", "kids": []}
    res = _node(page, {"sync": True, "posts": [took.get_json()], "gets": [held, held],
                       "steps": [{"do": "card", "key": order.keys[0]}, {"do": "click", "key": order.keys[0], "act": "take"},
                                 {"do": "sync"}, {"do": "card", "key": order.keys[0]}, {"do": "card", "key": order.keys[1]},
                                 {"do": "run"}, {"do": "sync"}, {"do": "card", "key": order.keys[0]}]})
    out = res["out"]
    assert out[3]["card"]["act"] == out[0]["card"]["act"]  # 확인 창에 걸린 카드 = 단추 칸 그대로
    assert out[4]["card"]["act"] == [hold_chip]  # 같은 주문 다른 카드는 바로
    assert out[5]["sent"] == 1 and out[5]["modal"]["hidden"]
    after = out[7]["card"]["act"][0]  # 저장이 끝난 뒤 다음 받아 오기 = 막힘 칸(내 작업 한 층 — 시작 취소는 보류에도 된다)
    assert after["cls"] == "pp-two is-mine" and [k["text"] for k in after["kids"]] == ["재단 시작 취소", "보류 · 자재 기다림"]


def test_js_refusal_redraws_every_card_of_that_order_at_once(client, cohort, tmp_path):
    order, kim, page = _hold_flow(client, tmp_path)
    refused = mark(client, order, 0, "cut", "take", "none")
    assert refused.status_code == 409 and code(refused) == "HOLD_ACTIVE"
    res = _node(page, {"sync": True, "posts": [{"__status": 409, "body": refused.get_json()}], "gets": [_synced(client, order.id)],
                       "steps": [{"do": "click", "key": order.keys[0], "act": "take"}, {"do": "run"},
                                 {"do": "card", "key": order.keys[0]}, {"do": "card", "key": order.keys[1]}]})
    assert res["out"][1]["modal"]["lost"] and res["out"][1]["modal"]["err"] == HOLD_MESSAGE
    assert [c["method"] for c in res["calls"]] == ["POST", "GET"]  # 거절 뒤 바로 받아 오기 한 번
    for out in res["out"][2:]:
        assert out["card"]["act"][0]["text"] == "보류 · 자재 기다림" and out["card"]["act"][0]["cls"] == "fph-wi pp-act pp-st-hold"


def test_head_line_receive_time_follows_every_sync():
    sync = (ROOT / "static/js/production/foms-production-parts-sync.js").read_text(encoding="utf-8")
    home = (ROOT / "static/js/production/foms-production-home.js").read_text(encoding="utf-8")
    assert "document.dispatchEvent(new CustomEvent('foms:prod-parts-synced'))" in sync
    assert "document.addEventListener('foms:prod-parts-synced', function () { G.syncedAt = Date.now(); G.api.tick(); });" in home
    assert "return Math.max(stamped > 0 ? stamped : openedAt, G.syncedAt || 0);" in home
    for name in ("parts", "parts-sync", "parts-claim", "home", "home-steps"):
        assert len((ROOT / f"static/js/production/foms-production-{name}.js").read_text(encoding="utf-8").splitlines()) <= 300


# --------------------------------------------------------------------------- #
# C09 — 제작 완료 뒤 그 주문 카드
# --------------------------------------------------------------------------- #
def test_js_complete_from_the_last_inspect_card_drops_undo_for_that_order(client, cohort, tmp_path, monkeypatch):
    keep_mine_on_date_board(monkeypatch)  # 내 카드 조각 · JS 규칙만 본다 — 그 카드는 이제 '내 공정' 탭(2026-11-28 흐름)
    order = make_order(2, steps_done=("cut", "edge", "assemble"))
    kang = make_user("강검수", part="inspect")
    login(client, kang)
    for j in (0, 1):
        assert mark(client, order, j, "inspect", "take", "none").status_code == 200
    assert mark(client, order, 0, "inspect", "done", "need").status_code == 200
    html = _page(client, HOME_NONE)
    cfg = json.loads(unescape(re.search(r'data-foms-parts-config="([^"]+)"', html).group(1)))
    assert cfg["done_block"] == {"kind": "done", "text": "제작 완료", "why": DONE_WHY, "code": "NOT_IN_PRODUCTION"}
    page = tmp_path / "kang.html"
    page.write_text(html, encoding="utf-8")
    last = mark(client, order, 1, "inspect", "done", "need").get_json()
    assert last["data"]["order_ready"]
    complete = client.post(f"/api/orders/{order.id}/production/complete", json={})
    assert complete.status_code == 200, complete.get_json()
    after_undo = mark(client, order, 0, "inspect", "undo", "done")
    assert after_undo.status_code == 409 and after_undo.get_json()["error"] == NOT_IN_PRODUCTION_MESSAGE  # 지금 서버 글
    res = _node(page, {"posts": [last, complete.get_json()],
                       "steps": [{"do": "click", "key": order.keys[1], "act": "done"}, {"do": "run"}, {"do": "timers"}, {"do": "run"},
                                 {"do": "card", "key": order.keys[0]}, {"do": "card", "key": order.keys[1]}]})
    assert res["out"][1]["modal"]["title"] == "제작 완료할까요?" and res["out"][3]["sent"] == 1
    assert res["out"][3]["status"] == "제작 완료했어요 — 시공 대기로 넘어갔어요" and res["out"][3]["modal"]["hidden"]
    for out in res["out"][4:]:  # 두 장 모두 [되돌리기] 대신 '제작 완료'(받아 오기의 생산 단계 아님 칸과 같은 값)
        assert out["card"]["act"] == [{"tag": "button", "cls": "fph-wi pp-act pp-st-done", "act": None, "text": "제작 완료", "kids": []}]
    login(client, kang)
    assert _synced(client, order.id)["data"]["blocks"][str(order.id)]["all"]["text"] == "제작 완료"
