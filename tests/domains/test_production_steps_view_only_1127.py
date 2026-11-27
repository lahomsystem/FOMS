"""도면이 주, 작업 시트는 보기(사장님 2026-11-27).

사장님 결정(질문 창 설명 그대로): "작업 시트의 공정 칸은 누르는 칸이 아니라 '재단 2/3 · 김재단 작업 중', '엣지 미정' 같은 진행 표시가
되고, 누르면 그 주문의 도면 화면으로 갑니다. 도면이 한 장뿐인 주문도 박반장이 도면 화면에서 [재단 완료]를 누릅니다. 도면이 아예 없는
주문만 지금처럼 칸을 누릅니다. [제작 시작] · [제작 완료] · [보류] · [불량 알리기] · [패킹]은 작업 시트에 그대로 남습니다." · "태블릿과 PC
에서만 하면 됨"(폰은 보기만).

규칙: 확정 도면 **1장 이상** 주문의 공정 칸 켜기 = 누구든 409 ``STEP_PER_SHEET``(글 "도면이 있는 주문은 도면 화면에서 완료해 주세요.") · 쓰기 0.
끄기(손으로 켜 둔 옛 칸) = 200. 도면 0장 주문 = 지금처럼 켜고 끔(대조군). 작업 시트 = 체크 칸 대신 보기 줄 넷(글 · 색 · 도면 화면 링크),
'남은 공정' = [<공정> 완료] 대신 막힘 칸 링크, PC [모두 완료 처리] 없음.

되돌리면 실패: 1장 주문 켜기 200 · 끄기 막힘 · 0장 주문 막힘 · 작업 시트에 도면 있는 주문 체크 칸 · 줄 글이 바뀜 · 링크가 엉뚱한 곳 · 폰에
링크 · 손 체크 칸을 끌 길이 없음 · '남은 공정'에 [재단 완료]. 이름은 지어낸 값. 줄 끝 글자(CRLF)는 보지 않는다.
"""
from __future__ import annotations

import datetime
import json
import re
import shutil
import subprocess
from html import unescape
from pathlib import Path

import pytest

from db import db_session
from foms.services.production.part_mark_gates import STEP_PER_SHEET, step_cell_gate
from foms.services.production.part_progress import STEP_PER_SHEET_MESSAGE, WHOLE_STEP_MAX_SHEETS, per_sheet_only, step_api_extras
from foms.services.production.pc_sheet import build_part_sheet
from foms.services.production.sheet_step_lines import sheet_step_lines
from models import ProductionPartMark, SecurityLog
from tests.support.production_home_step_panel_seed import HOME, TABLET, add_order, get_html, pane_html, set_cookies
from tests.support.production_home_step_panel_seed import login as home_login
from tests.support.production_part_claim_seed import check_step, code, events, fresh, login, make_order, make_user, patch_sd, step

ROOT = Path(__file__).resolve().parents[2]
NODE_CHECK = ROOT / "tests/support/production_per_sheet_only_node_checks.js"
MSG = "도면이 있는 주문은 도면 화면에서 완료해 주세요."
PARTS = ("cut", "edge", "assemble", "inspect")
PC = {"foms_ptr": "fine", "foms_vw": "wide", "foms_scr": "1920"}
PHONE = {"foms_ptr": "coarse", "foms_vw": "narrow", "foms_scr": "844"}
SHEET = "/erp/production/sheet/{}"
BASE = datetime.datetime(2026, 11, 27, 0, 30)


@pytest.fixture
def cohort(monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")


def _put(order, j: int, part: str, state: str, name: str, *, at: datetime.datetime = BASE) -> None:
    done = state == "DONE"
    db_session.add(ProductionPartMark(order_id=order.id, drawing_key=order.keys[j], sheet_id=f"s{j}", part=part, state=state,
                                      picked_by_name=name, picked_at=at, done_by_name=name if done else None,
                                      done_at=at if done else None))
    db_session.commit()


def _marks(oid: int) -> list:
    db_session.expire_all()
    return db_session.query(ProductionPartMark).filter_by(order_id=oid).all()


def _snapshot(oid: int) -> tuple:
    order = fresh(oid)
    audits = db_session.query(SecurityLog).filter_by(target_id=oid, action="PRODUCTION_STEP_CHECKED").count()
    return (order.mutation_version, json.dumps(order.structured_data, sort_keys=True), len(events(oid, "PRODUCTION_STEP_CHECKED")),
            audits, len(_marks(oid)))


def _box(page: str) -> str:
    return page.split('aria-label="공정"', 1)[1].split("</section>", 1)[0]


def _lines(page: str) -> dict[str, dict]:
    """보기 줄 — 파트 → {tag, href, text}(이름 칸 + 진행 글을 한 칸 띄어 잇는다)."""
    out = {}
    for m in re.finditer(r'<(a|div) class="foms-prod-page__step is-view is-line([^"]*)"([^>]*)data-foms-sheet-line="(\w+)"([^>]*)>'
                         r'<span>([^<]*)</span> <small class="fpp-note is-(\w+)">([^<]*)</small>', _box(page)):
        tag, cls, attrs, key, tail, label, tone, rest = m.groups()
        href = re.search(r'href="([^"]*)"', attrs + tail)
        out.setdefault(key, {"tag": tag, "cls": cls.strip(), "href": unescape(href.group(1)) if href else None,
                             "text": f"{label} {rest}", "tone": tone, "hidden": " hidden" in tail})
    return out


def _node(tmp_path, page: str, want: dict) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 없음")
    path = tmp_path / f"{want['mode']}.html"
    path.write_text(page, encoding="utf-8")
    proc = subprocess.run([node, str(NODE_CHECK), str(path), json.dumps(want, ensure_ascii=False)], capture_output=True, text=True,
                          encoding="utf-8", timeout=60, cwd=str(ROOT))
    assert proc.returncode == 0 and proc.stdout.strip().endswith("OK"), proc.stdout + proc.stderr


# --------------------------------------------------------------------------- #
# 서버 규칙 — 한 장 이상 켜기 409 · 끄기 200 · 0장 대조군
# --------------------------------------------------------------------------- #
def test_rule_is_one_sheet_or_more_and_the_words_fit_any_count():
    assert WHOLE_STEP_MAX_SHEETS == 0 and STEP_PER_SHEET_MESSAGE == MSG and "여러 장" not in MSG
    sd = lambda n: {"drawing_current_files": [{"key": f"k{j}"} for j in range(n)], "production": {"steps": []}}  # noqa: E731
    assert [per_sheet_only(sd(n)) for n in (0, 1, 2)] == [False, True, True]
    gate = step_cell_gate(sd(1), [], "cut", True)
    assert (gate.status, gate.code, gate.message, gate.extra) == (409, STEP_PER_SHEET, MSG, {"part": "cut", "left": 1, "total": 1})
    assert step_cell_gate(sd(1), [], "cut", False) is None and step_api_extras(sd(1), [])["per_sheet"] == MSG
    assert step_cell_gate(sd(0), [], "cut", True) is None and "per_sheet" not in step_api_extras(sd(0), [])  # 대조군


@pytest.mark.parametrize("who", ["lead", "admin"])
def test_one_sheet_turn_on_is_refused_without_any_write(client, who):
    seed = make_order(1)
    login(client, make_user("가짜반장", lead=True) if who == "lead" else make_user("가짜관리", role="ADMIN", team="CS"))
    for part in PARTS:
        before = _snapshot(seed.id)
        res = check_step(client, seed.id, part, True)
        assert res.status_code == 409
        assert res.get_json() == {"success": False, "data": {"code": STEP_PER_SHEET, "part": part, "left": 1, "total": 1}, "error": MSG}
        assert _snapshot(seed.id) == before


def test_one_sheet_hand_cell_turns_off_and_zero_sheet_control_turns_on_and_off(client):
    hand = make_order(1, steps_done=("cut",))
    zero = make_order(0)
    login(client, make_user("가짜반장", lead=True))
    off = check_step(client, hand.id, "cut", False)
    assert off.status_code == 200 and step(hand.id, "cut")["done"] is False and off.get_json()["data"]["per_sheet"] == MSG
    assert code(check_step(client, hand.id, "cut", True)) == STEP_PER_SHEET  # 끈 뒤 다시 켜기는 도면 화면에서
    on = check_step(client, zero.id, "cut", True)
    assert on.status_code == 200 and step(zero.id, "cut")["done"] is True and step(zero.id, "cut")["via"] == "sheet"
    assert "per_sheet" not in on.get_json()["data"]
    assert check_step(client, zero.id, "cut", False).status_code == 200 and step(zero.id, "cut")["done"] is False


# --------------------------------------------------------------------------- #
# 보기 줄 글 — 상태마다 원문
# --------------------------------------------------------------------------- #
def test_line_words_for_every_state():
    seed = make_order(3)
    _put(seed, 0, "cut", "DONE", "김재단")
    _put(seed, 1, "cut", "DONE", "김재단")
    _put(seed, 2, "cut", "NEED", "오재단")
    _put(seed, 0, "edge", "NEED", "박엣지")
    _put(seed, 0, "assemble", "DONE", "이조립")
    today = datetime.date(2026, 11, 27)
    lines = sheet_step_lines(fresh(seed.id).structured_data, _marks(seed.id), today)
    assert {k: (v["text"], v["tone"]) for k, v in lines.items()} == {
        "cut": ("재단 2/3 완료 · 오재단 11/27 09:30부터 작업 중", "run"),
        "edge": ("엣지 박엣지 11/27 09:30부터 작업 중", "run"),
        "assemble": ("조립 1/3 완료 · 미정", "miss"),
        "inspect": ("검수 미정", "miss"),
    }
    assert lines["cut"]["label"] == "재단" and lines["cut"]["rest"] == "2/3 완료 · 오재단 11/27 09:30부터 작업 중"
    one = make_order(1)
    _put(one, 0, "cut", "DONE", "김재단")
    got = sheet_step_lines(fresh(one.id).structured_data, _marks(one.id), today)
    assert got["cut"]["text"] == "재단 완료 · 김재단 11/27 09:30" and got["cut"]["tone"] == "ok" and got["cut"]["done"] is True
    hand = make_order(1, steps_done=("edge",))
    got = sheet_step_lines(fresh(hand.id).structured_data, [], today)
    assert (got["edge"]["text"], got["edge"]["hand"], got["edge"]["off"]["text"]) == ("엣지 완료 · 박반장 · 작업 시트에서 완료", True, "엣지 미정")
    patch_sd(hand.id, steps=[{**s, "at": "2026-11-27T01:20:00+00:00"} if s["key"] == "edge" else s
                             for s in fresh(hand.id).structured_data["production"]["steps"]])
    got = sheet_step_lines(fresh(hand.id).structured_data, [], today)
    assert got["edge"]["text"] == "엣지 완료 · 박반장 11/27 10:20 · 작업 시트에서 완료"  # 손 체크 칸 때(칸에 적힌 때)
    assert sheet_step_lines(fresh(make_order(0).id).structured_data, [], today) is None  # 도면 0장 = 체크 칸 그대로


def test_basic_cut_sheets_keep_the_card_word_and_late_ones_are_counted():
    """재단 [기본] 장 = 카드 낱말 "기본" + 장 수(완료로 센다) · 같이 작업 중인 사람은 이름 줄로 · 때는 맨 먼저 시작한 사람 것."""
    seed = make_order(3)
    _put(seed, 0, "cut", "BASIC", "김재단")
    _put(seed, 1, "cut", "DONE", "오재단", at=BASE + datetime.timedelta(hours=1))
    _put(seed, 2, "cut", "DONE", "김재단", at=BASE + datetime.timedelta(minutes=10))
    _put(seed, 0, "edge", "NEED", "박엣지", at=BASE + datetime.timedelta(minutes=5))
    _put(seed, 1, "edge", "NEED", "한엣지")
    _put(seed, 2, "edge", "NEED", "서엣지", at=BASE + datetime.timedelta(minutes=9))
    lines = sheet_step_lines(fresh(seed.id).structured_data, _marks(seed.id), datetime.date(2026, 11, 27))
    assert lines["cut"]["text"] == "재단 완료 · 기본 1장 · 오재단 · 김재단 11/27 10:30"
    assert lines["edge"]["text"] == "엣지 한엣지 · 박엣지 외 1 11/27 09:30부터 작업 중"
    partial = make_order(3)
    _put(partial, 0, "cut", "BASIC", "김재단")
    lines = sheet_step_lines(fresh(partial.id).structured_data, _marks(partial.id), datetime.date(2026, 11, 27))
    assert lines["cut"]["text"] == "재단 1/3 완료 · 기본 1장 · 미정"


def test_three_people_line_uses_the_card_name_line():
    seed = make_order(3)
    for j, name in enumerate(("김재단", "오재단", "서재단")):
        _put(seed, j, "cut", "DONE", name, at=BASE + datetime.timedelta(minutes=j))
    lines = sheet_step_lines(fresh(seed.id).structured_data, _marks(seed.id), datetime.date(2026, 11, 27))
    assert lines["cut"]["text"] == "재단 완료 · 서재단 · 오재단 외 1 11/27 09:32"  # 마지막에 완료한 사람부터 둘까지, 나머지 "외 n"


# --------------------------------------------------------------------------- #
# 작업 시트 — 태블릿 반장 · 파트 계정 · 보기만 · PC · 폰
# --------------------------------------------------------------------------- #
def test_tablet_lead_sheet_has_four_lines_no_checkbox_and_links_to_the_drawing_screen(client, cohort, tmp_path):
    seed = make_order(2)
    _put(seed, 0, "cut", "NEED", "김재단")
    login(client, make_user("가짜반장", lead=True))
    set_cookies(client, TABLET)
    page = get_html(client, SHEET.format(seed.id))
    box = _box(page)
    assert "data-foms-sheet-step=" not in box and "<i><svg" not in box  # 체크 칸 · 체크 네모 0
    lines = _lines(page)
    assert list(lines) == list(PARTS)
    assert [v["text"] for v in lines.values()] == ["재단 김재단 11/27 09:30부터 작업 중", "엣지 미정", "조립 미정", "검수 미정"]
    assert {k: v["href"] for k, v in lines.items()} == {k: f"/erp/production/home?tab=parts&part={k}&order={seed.id}" for k in PARTS}
    assert lines["cut"]["tag"] == "a" and "is-now" in lines["cut"]["cls"]  # 지금 공정 표시는 그대로
    # 공정 칸은 오른쪽 맨 위(11-21 결정) — 보류 사유 · 공정 다음이 바뀐 것 · 만들 것
    side = page.split('class="foms-prod-page__side-scroll"', 1)[1]
    assert side.index('aria-label="공정"') < side.index('aria-label="만들 것"')
    # [제작 시작] · [제작 완료] · [보류] · [불량 알리기]는 그대로
    assert 'data-tablet-sheet-action="production-hold"' in page and "data-foms-sheet-defect-toggle" in page
    assert "data-foms-sheet-complete" in page
    _node(tmp_path, page, {"key": "edge", "mode": "view"})


def test_hand_cell_keeps_the_turn_off_way_for_writers_and_swaps_to_the_line(client, cohort, tmp_path):
    seed = make_order(1, steps_done=("cut",))
    login(client, make_user("가짜반장", lead=True))
    set_cookies(client, TABLET)
    page = get_html(client, SHEET.format(seed.id))
    box = _box(page)
    assert box.count("data-foms-sheet-step=") == 1 and 'data-foms-sheet-step="cut" aria-pressed="true"' in box
    assert ('<span>재단</span> <small class="fpp-note is-ok" data-foms-sheet-step-meta data-foms-sheet-cardnote>'
            '완료 · 박반장 · 작업 시트에서 완료</small>') in box
    after = _lines(page)["cut"]
    assert after["hidden"] and after["text"] == "재단 미정" and after["href"].endswith(f"part=cut&order={seed.id}")
    reply = {"steps": [{"key": k, "done": False} for k in PARTS], "complete_ready": True, "sheets": 1, "per_sheet": MSG,
             "parts": {k: {"uses_cards": False, "done": False, "done_n": 0, "total_n": 1, "left_n": 1, "via": None} for k in PARTS}}
    _node(tmp_path, page, {"key": "cut", "mode": "off", "reply": reply, "text": "재단 미정"})
    # 회색 [제작 완료] = 칸 이름 대신 서버 자료로 남은 공정(옛 글 "공정 0칸()" 이 나오면 실패)
    _node(tmp_path, page, {"mode": "why", "text": "검수까지 끝나야 제작 완료할 수 있어요. (남은 공정: 엣지 · 조립 · 검수)"})


def test_part_account_and_readonly_get_the_same_lines_with_their_own_links(client, cohort):
    seed = make_order(1, steps_done=("cut",))
    set_cookies(client, TABLET)
    login(client, make_user("가짜엣지", part="edge"))
    page = get_html(client, SHEET.format(seed.id))
    lines = _lines(page)
    assert "data-foms-sheet-step=" not in _box(page)  # 파트 계정 = 손 체크 칸도 보기 줄(끄기 길 없음)
    assert lines["cut"]["text"] == "재단 완료 · 박반장 · 작업 시트에서 완료" and lines["cut"]["tag"] == "div"
    assert lines["edge"]["href"] == f"/erp/production/home?part=edge&order={seed.id}"  # 내 파트 = 날짜 탭 판
    assert {k: lines[k]["href"] for k in ("cut", "assemble", "inspect")} == {"cut": None, "assemble": None, "inspect": None}
    login(client, make_user("가짜상담", team="CS"))
    page = get_html(client, SHEET.format(seed.id))
    lines = _lines(page)
    assert lines["edge"]["href"] == f"/erp/production/home?tab=parts&part=edge&order={seed.id}"  # 보기만 = 도면 카드 화면
    assert lines["cut"]["text"] == "재단 완료 · 박반장 · 작업 시트에서 완료" and "data-foms-sheet-step=" not in _box(page)


def test_part_account_lock_note_stays_on_the_lines(client):
    """파트 계정 = 공정 잠금 글 그대로 + 보기 줄 넷(옛 체크 칸 잠금 꼴은 도면 0장 주문 — test_production_part_steps_sync)."""
    seed = make_order(1, steps_done=("cut",))
    login(client, make_user("가짜재단", part="cut"))
    page = get_html(client, SHEET.format(seed.id))
    assert "data-foms-sheet-step=" not in _box(page) and len(_lines(page)) == 4
    assert "data-foms-sheet-steps-locked>공정은 도면에서 작업해요</p>" in page


def test_pc_lines_open_the_drawing_list_window_and_phone_lines_are_text_only(client, cohort):
    seed = make_order(2)
    login(client, make_user("가짜관리", role="ADMIN", team="CS"))
    set_cookies(client, PC)
    page = get_html(client, SHEET.format(seed.id))
    box = _box(page)
    assert "data-foms-sheet-step=" not in box and box.count('role="button" aria-haspopup="dialog" data-foms-pc-sheet=') == 4
    assert all(v["tag"] == "div" and v["href"] is None for v in _lines(page).values())
    set_cookies(client, PHONE)
    page = get_html(client, SHEET.format(seed.id))
    lines = _lines(page)
    assert [v["text"] for v in lines.values()] == ["재단 미정", "엣지 미정", "조립 미정", "검수 미정"]
    assert all(v["tag"] == "div" and v["href"] is None for v in lines.values()) and "data-foms-pc-sheet=" not in _box(page)
    assert "data-foms-sheet-step=" not in _box(page)  # 폰 = 완료 길 없음


def test_zero_sheet_sheet_keeps_today_checkboxes(client, cohort, tmp_path):
    zero = make_order(0)
    login(client, make_user("가짜반장", lead=True))
    set_cookies(client, TABLET)
    page = get_html(client, SHEET.format(zero.id))
    box = _box(page)
    assert box.count("data-foms-sheet-step=") == 4 and "data-foms-sheet-line" not in box and box.count("<i><svg") == 4
    _node(tmp_path, page, {"key": "cut", "mode": "zero"})
    _node(tmp_path, page, {"key": "edge", "mode": "stale", "msg": MSG})  # 낡은 화면(그사이 도면이 옴) = 칸 아래 서버 글 · 요청 0


# --------------------------------------------------------------------------- #
# '남은 공정' 판 · 줄 · PC 창
# --------------------------------------------------------------------------- #
def test_my_steps_one_sheet_row_is_a_link_and_zero_sheet_keeps_the_button(client, cohort):
    one = add_order("가짜한장", 1, pngs=1)
    zero = add_order("가짜없음", 2, pngs=0)
    home_login(client)  # 반장
    set_cookies(client, TABLET)
    html = get_html(client, HOME + "?tab=steps")
    href = f"/erp/production/home?tab=parts&amp;part=cut&amp;order={one.id}"
    row = html.split(f'data-foms-home-qrow="{one.id}"', 1)[1].split('data-foms-home-qrow="', 1)[0]
    assert f'<a class="fph-qr__hold is-cards" href="{href}" data-foms-step-cards title="{MSG}">재단 0/1 · 1장 미완료</a>' in row
    assert "data-foms-home-step-done" not in row
    pane = pane_html(get_html(client, HOME + f"?tab=steps&order={one.id}"), one.id)
    assert f'<a class="fph-sp__hold is-cards" href="{href}" data-foms-step-cards><b>재단 0/1 · 1장 미완료</b><span>{MSG}</span></a>' in pane
    assert "data-foms-step-finish" not in pane
    zero_row = html.split(f'data-foms-home-qrow="{zero.id}"', 1)[1].split('data-foms-home-qrow="', 1)[0]
    assert f'data-foms-home-step-done data-order-id="{zero.id}" data-step-key="cut"' in zero_row  # 대조군
    assert "data-foms-sheet-parts" not in zero_row  # 도면 0장 = 묻지 않는다(지금 그대로)


def test_pc_window_never_offers_check_all_for_drawn_orders(client):
    sd = lambda n: {"drawing_current_files": [{"key": f"k{j}"} for j in range(n)], "production": {"steps": []}}  # noqa: E731
    for n in (1, 3):
        data = build_part_sheet(sd(n), [], "cut", hold_active=False)
        assert data["all"] is False and [r["act"] for r in data["rows"]] == ["check"] * n  # 한 장씩 [완료 처리] 그대로
    hand = build_part_sheet({**sd(1), "production": {"steps": [{"key": "cut", "done": True, "by_name": "박반장"}]}}, [], "cut",
                            hold_active=False)
    assert hand["hand_off"] is True  # 손 체크 칸 [모두 완료 취소](끄기)는 그대로
    one = make_order(1)
    login(client, make_user("가짜관리", role="ADMIN", team="CS"))
    got = client.get(f"/api/production/part-sheet?order_id={one.id}&part=edge").get_json()["data"]
    assert got["all"] is False and [r["act"] for r in got["rows"]] == ["check"] and got["can_write"] is True


# --------------------------------------------------------------------------- #
# 파일 계약 — 핀 · 줄 수 · 글은 서버 한 곳
# --------------------------------------------------------------------------- #
def test_files_contract():
    parts = (ROOT / "static/js/production/foms-production-sheet-parts.js").read_text(encoding="utf-8")
    assert MSG not in parts and len(parts.splitlines()) <= 300
    assert "function ask(" not in parts and "이 주문의 도면 '" not in parts  # 탈 길이 없는 옛 확인 창 글은 뺐다
    for rel, n in (("templates/production/sheet.html", 1),  # 칸반 본문(옆 시트)은 2026-11-27 옛 보드와 함께 지움
                   ("templates/production/partials/home_scripts.html", 2)):
        assert (ROOT / rel).read_text(encoding="utf-8").count("foms-production-sheet-parts.js') }}?v=20261127z") == n, rel
    for rel in ("templates/production/sheet.html",):
        assert "css/contexts/production/sheet.css') }}?v=20261127x" in (ROOT / rel).read_text(encoding="utf-8"), rel
    css = (ROOT / "static/css/contexts/production/sheet.css").read_text(encoding="utf-8")
    assert ".foms-prod-page__step small.fpp-note.is-run { color: var(--fpp-brand-dark); }" in css
    assert ".foms-prod-page__step[hidden] { display: none; }" in css
