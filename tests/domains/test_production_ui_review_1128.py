"""생산 화면 UI 평가 다섯 고치기(사장님 2026-11-28 고르심 — B1 · B2 · B3 · G1 · G3).

* B1 "태블릿 날짜 줄에 '늦음' 표시": 태블릿 · 폰 날짜 줄 단계 칸 맨 아래에 PC 줄과 같은 늦음 · 빠듯 글(``pc_late`` — 같은 함수 ·
  같은 날 · 글자까지 같음, 쿼리 0). 멀리 있는 주문은 글이 없다(음성 대조).
* B2 "담당 없으면 '조립 미정'": 지금 공정에 담당이 아무도 없으면 큰 글 "조립 미정"(칸 아래 이름과 같은 판정), 담당이 있으면
  "조립 작업 중" 그대로(음성 대조). 태블릿 · 폰 날짜 줄과 PC 상태 칸이 같은 값.
* B3 "남은 공정: 고른 줄로 굴리기": 판이 처음 고르는 줄은 [끝] 자리 막힘(도면 칸 "재단 0/3 · 3장 미완료") 줄도 고른다 — 보류 ·
  도면 고치는 중만 건너뛴다. 공정 탭을 보일 때 판의 고른 줄이 목록 밖이면 그 줄로 굴린다(steppane.js reveal — Node 로 잰다).
* G1 "줄 순서": 하루 장 만들 것 줄 = 바뀐 것 먼저, 그다음 덜 간 것부터(제작 대기 → 끝난 공정 적은 것 → 검수 완료).
* G3 "카드 품목 줄": 도면 카드 품목 줄 = "치수 · 색 · 품목 이름"(한 줄 말줄임이 이름 쪽을 자른다), 색 = 판 색.

되돌리면 실패: 태블릿 줄에 늦음 글이 없음 · PC 와 다른 글 · 담당 없는 공정에 "작업 중" · 담당 있는 공정에 "미정" · 판이 도면 칸
줄을 건너뜀 · 고른 줄로 안 굴림 · 많이 간 것부터 · 품목 이름이 앞 · 색 없음. 이름은 모두 지어낸 값이다.
"""
from __future__ import annotations

import copy
import datetime
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from foms.services.production.home_step_panel import attach_step_panels
from foms.services.production.part_board import card_item_parts, card_item_text
from foms.services.production.part_holders import stage_none
from foms.services.production.pc_view import attach_late_rows, attach_pc_rows
from foms.services.production_home_days import production_home_days
from tests.domains.test_production_home_step_panel import _row as step_row
from tests.domains.test_production_pc_sheet import HOME, PC, TABLET, _login, _mark, _order, _user, cohort  # noqa: F401

ROOT = Path(__file__).resolve().parents[2]
PHONE = {"foms_ptr": "coarse", "foms_vw": "narrow", "foms_scr": "844"}
_STEPS = (("cut", "재단"), ("edge", "엣지"), ("assemble", "조립"), ("inspect", "검수"))


def _steps(done: int) -> list[dict]:
    return [{"key": k, "label": lb, "done": i < done, "now": i == done} for i, (k, lb) in enumerate(_STEPS)]


def _tab_row(html: str, oid: int) -> str:
    return html.split(f'data-foms-home-dayrow="{oid}"', 1)[1].split("</a>", 1)[0]


def _pc_row(html: str, oid: int) -> str:
    return html.split(f'data-foms-home-dayrow="{oid}"', 1)[1].split('<div class="fpc-r', 1)[0]


def _sg(row_html: str) -> str:
    """태블릿 · 폰 줄 단계 칸 HTML."""
    return row_html.split('<span class="fph-dr__sg">', 1)[1].split('<span class="fph-dr__who">', 1)[0]


# --------------------------------------------------------------------------- #
# B1 — 태블릿 · 폰 날짜 줄 늦음 글 = PC 줄 글
# --------------------------------------------------------------------------- #
def test_b1_late_value_is_the_pc_value_for_every_row_kind() -> None:
    """같은 함수 · 같은 날: 늦음(내일 재단) · 빠듯 · 없음(멀리) · 지난 날 · 시공일 없음 — 태블릿 값이 PC 값과 똑같다(쿼리 0 순수 함수)."""
    today = datetime.date(2026, 11, 25)  # 수요일

    def row(rid: int, day: str | None, stage: str, done: int) -> dict:
        return {"id": rid, "construction_date": day, "home_view": "prod", "home_stage": stage, "home_steps": _steps(done),
                "structured_data": {}, "home_alerts": []}

    rows = [row(1, "2026-11-26", "재단 작업 중", 0), row(2, "2026-11-28", "조립 작업 중", 2), row(3, "2026-12-15", "재단 작업 중", 0),
            row(4, "2026-11-22", "엣지 작업 중", 1), row(5, None, "재단 작업 중", 0), row(6, "2026-11-27", "제작 대기", 0)]
    tablet, pc = copy.deepcopy(rows), copy.deepcopy(rows)
    attach_late_rows(tablet, today)
    attach_pc_rows(pc, today)
    assert [r["pc_late"] for r in tablet] == [r["pc_late"] for r in pc]
    lines = [r["pc_late"]["line"] for r in tablet]
    assert lines[0] == "늦음 — 내일 시공, 아직 재단" and lines[3] == "늦음 — 시공 3일 지남, 아직 엣지"
    assert lines[2] == "" and lines[4] == "" and tablet[2]["pc_late"]["level"] is None  # 대조: 멀리 · 시공일 없음
    assert "pc_due" not in tablet[0] and "pc_steps" not in tablet[0]  # 태블릿은 늦음 표만(PC 칸은 안 단다)


def test_b1_tablet_and_phone_rows_show_the_pc_late_line(client, cohort) -> None:
    viewer = _user("관리", role="ADMIN", team="CS")
    late = _order("정하늘", 1)  # 내일 시공 · 재단 작업 중 → 늦음
    far = _order("윤봄", 1, off=9)  # 대조 — 9일 뒤(일하는 날 5일 넘음) → 늦음 · 빠듯 없음
    late_id, far_id = late.id, far.id
    tomorrow, far_day = late.erp_construction_date, far.erp_construction_date
    _login(client, viewer, PC)
    pc = _pc_row(client.get(f"{HOME}?day={tomorrow}").get_data(as_text=True), late_id)
    pc_line = re.search(r'<span class="fpc-st[^>]*><b>[^<]*</b><small>([^<]*)</small>', pc).group(1)
    assert pc_line == "늦음 — 내일 시공, 아직 재단"
    for cookies in (TABLET, PHONE):
        _login(client, viewer, cookies)
        sg = _sg(_tab_row(client.get(f"{HOME}?day={tomorrow}").get_data(as_text=True), late_id))
        assert f'<small class="is-late">{pc_line}</small>' in sg, cookies  # PC 와 글자까지 같은 글 · 빨강 꼴
        # 날 조각(날 누름 — ?view=day)도 같은 값(장마다 다시 센 사본 길)
        piece = client.get(f"{HOME}?view=day&day={tomorrow}").get_data(as_text=True)
        assert f'<small class="is-late">{pc_line}</small>' in _sg(_tab_row(piece, late_id)), cookies
        far_sg = _sg(_tab_row(client.get(f"{HOME}?day={far_day}").get_data(as_text=True), far_id))
        assert "is-late" not in far_sg and "is-tight" not in far_sg and "늦음" not in far_sg, cookies


def test_b1_late_line_css_is_red_and_tight_brown_like_pc() -> None:
    css = (ROOT / "static/css/contexts/production/home.css").read_text(encoding="utf-8")
    pc = (ROOT / "static/css/contexts/production/pc.css").read_text(encoding="utf-8")
    assert ".is-late > .fpc-st small { color: var(--fpc-danger-ink); }" in pc  # PC 늦음 = #b91c1c
    rule = re.search(r"\.fph-dr \.fph-dr__sg small\.is-late, \.fph-dr \.fph-dr__sg small\.is-tight \{([^}]*)\}", css).group(1)
    assert "color: var(--fph-danger);" in rule and "calc(14px * var(--foms-fs, 1))" in rule
    assert ".fph-dr .fph-dr__sg small.is-tight { color: var(--fph-why); }" in css
    assert "--fph-danger: #b91c1c;" in css and "--fph-why: #92400e;" in css and "--fpc-warn-ink: #92400e;" in pc  # PC 와 같은 색 값
    # 바뀐 줄 빨간 작은 글 규칙보다 뒤(같은 특이도에서 이긴다)
    assert css.index(".fph-dr.is-chg .fph-dr__sg small") < css.index("small.is-late, .fph-dr .fph-dr__sg small.is-tight")
    assert "home.css') }}?v=20261128y" in (ROOT / "templates/production/partials/home_styles.html").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# B2 — 담당 없으면 "조립 미정"
# --------------------------------------------------------------------------- #
def test_b2_stage_none_follows_holder_judgment() -> None:
    none, held = {"kind": "none"}, {"kind": "held"}
    done = {"kind": "done"}
    row = {"home_stage": "조립 작업 중", "home_steps": _steps(2)}
    assert stage_none(row, [done, done, none, none]) == "조립 미정"
    assert stage_none(row, [done, done, held, none]) == ""  # 대조: 담당 한 사람이라도 있으면 그대로
    for stage, steps in (("보류", _steps(2)), ("제작 대기", _steps(0)), ("검수 완료", _steps(4))):
        assert stage_none({"home_stage": stage, "home_steps": steps}, [none] * 4) == "", stage


def test_b2_tablet_phone_and_pc_say_assemble_undecided_only_when_nobody_holds(client, cohort) -> None:
    viewer = _user("관리", role="ADMIN", team="CS")
    free = _order("서가을", 2, done=("cut", "edge"))  # 조립 차례, 아무도 안 잡음
    held = _order("강단비", 2, done=("cut", "edge"))  # 대조 — 최조립 작업 중
    _mark(held, 0, "assemble", "NEED", _user("최조립", part="assemble"))
    free_id, held_id, day = free.id, held.id, free.erp_construction_date
    for cookies in (TABLET, PHONE):
        _login(client, viewer, cookies)
        html = client.get(f"{HOME}?day={day}").get_data(as_text=True)
        assert _sg(_tab_row(html, free_id)).startswith("조립 미정"), cookies
        assert _sg(_tab_row(html, held_id)).startswith("조립 작업 중"), cookies
        assert "조립 <b>미정</b>" in _tab_row(html, free_id)  # 칸 아래 이름 한 줄과 같은 판정
    _login(client, viewer, PC)
    html = client.get(f"{HOME}?day={day}").get_data(as_text=True)
    assert "<b>조립 미정</b>" in _pc_row(html, free_id) and "<b>조립 작업 중</b>" in _pc_row(html, held_id)
    assert 'aria-label="조립 미정 · 제작 시작' in _pc_row(html, free_id)  # 마우스 · 읽기 글도 같은 큰 글


# --------------------------------------------------------------------------- #
# B3 — 판이 고르는 줄 · 고른 줄로 굴리기
# --------------------------------------------------------------------------- #
def test_b3_panel_picks_first_row_even_with_cards_block_and_skips_only_stopped_rows() -> None:
    cards = {"kind": "cards", "text": "재단 0/3 · 3장 미완료", "why": "도면이 있는 주문은 도면 화면에서 완료해 주세요.", "code": "STEP_PER_SHEET"}
    first = dict(step_row(1), step_block=cards)
    revise = dict(step_row(5), revise_block={"kind": "revise", "text": "도면 고치는 중", "why": "", "code": "DRAWING_REVISING"})
    queues = {"queues": [{"key": "cut", "label": "재단", "rows": [first, step_row(2, hold=True), step_row(3)]},
                         {"key": "edge", "label": "엣지", "rows": [step_row(4, hold=True), revise, step_row(6)]},
                         {"key": "assemble", "label": "조립", "rows": [step_row(7, hold=True), dict(step_row(8), revise_block=revise["revise_block"])]}]}
    attach_step_panels(queues, None)
    cut, edge, asm = queues["queues"]
    assert cut["selected_id"] == 1 and cut["panels"][0]["step_block"]["text"] == "재단 0/3 · 3장 미완료"  # 예전: 3(목록 밖 큰 [재단 완료])
    assert cut["panels"][0]["next_id"] == 3  # '끝내면 다음은' 은 그대로 막힌 줄을 건너뛴다
    assert edge["selected_id"] == 6  # 대조: 보류 · 도면 고치는 중은 그대로 건너뛴다
    assert asm["selected_id"] == 7  # 모두 멈추면 첫 줄(그대로)
    assert attach_step_panels(queues, 3) == "cut" and cut["selected_id"] == 3  # order= 가 먼저(그대로)


REVEAL_JS = r"""
const fs = require('fs'); const vm = require('vm');
const ctx = {window: {}, console: console}; vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), ctx);
const calls = [];
function queue(shown, on) {
  const row = {scrollIntoView: function (o) { calls.push(o); }};
  const box = {getClientRects: function () { return shown ? [{}] : []; }};
  return {querySelector: function (s) { return s === '[data-foms-step-panes]' ? box : (s === '[data-foms-home-qrow].is-on' && on ? row : null); }};
}
const api = ctx.window.FomsProdStepPanes;
api.reveal(queue(true, true)); api.reveal(queue(false, true)); api.reveal(queue(true, false)); api.reveal(null);
console.log(JSON.stringify({calls: calls, create: typeof api.create}));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")
def test_b3_reveal_scrolls_selected_row_only_when_panel_is_shown() -> None:
    out = subprocess.run(["node", "-e", REVEAL_JS, str(ROOT / "static/js/production/foms-production-home-steppane.js")],
                         capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout.strip().splitlines()[-1])
    assert got == {"calls": [{"block": "nearest", "inline": "nearest"}], "create": "function"}  # 판이 안 보임 · 고른 줄 없음 = 0


def test_b3_home_js_reveals_after_showing_the_step_tab_and_pins_moved() -> None:
    js = (ROOT / "static/js/production/foms-production-home.js").read_text(encoding="utf-8")
    body = js.split("function selectStepTab(key) {", 1)[1].split("\n  }\n", 1)[0]
    assert body.index("q.hidden = q.getAttribute('data-foms-home-stepq') !== key;") < body.index("panes.reveal(q)")
    assert "if (!q.hidden && panes && typeof panes.reveal === 'function')" in body  # 처음 그릴 때 · 탭 바꿀 때 같은 함수
    scripts = (ROOT / "templates/production/partials/home_scripts.html").read_text(encoding="utf-8")
    early = (ROOT / "templates/production/partials/home_early.html").read_text(encoding="utf-8")
    assert "foms-production-home.js') }}?v=20261128y" in scripts
    assert "foms-production-home-steppane.js') }}?v=20261128y" in early


# --------------------------------------------------------------------------- #
# G1 — 하루 장 줄 순서 = 바뀐 것 먼저, 덜 간 것부터
# --------------------------------------------------------------------------- #
def test_g1_make_rows_least_progress_first_changed_still_first() -> None:
    today = datetime.date(2026, 11, 25)

    def row(rid: int, stage: str, done: int, changed: bool = False) -> dict:
        return {"id": rid, "construction_date": "2026-11-26", "home_view": "prod", "home_stage": stage, "home_steps": _steps(done),
                "has_changes": changed}

    rows = [row(10, "검수 완료", 4), row(9, "검수 작업 중", 3), row(4, "엣지 작업 중", 1), row(11, "재단 작업 중", 0),
            row(3, "제작 대기", 0), row(5, "조립 작업 중", 2, changed=True), row(12, "재단 작업 중", 0)]
    pane = next(p for p in production_home_days(rows, today)["panes"] if p["key"] == "2026-11-26")
    assert [r["id"] for r in pane["make_rows"]] == [5, 3, 11, 12, 4, 9, 10]  # 같은 자리는 들어온 순서 그대로(11 → 12)


def test_g1_pc_and_tablet_rows_share_the_order(client, cohort) -> None:
    viewer = _user("관리", role="ADMIN", team="CS")
    ahead = _order("강단비", 1, done=("cut", "edge", "assemble"))  # 검수만 남음
    behind = _order("정하늘", 1)  # 재단 작업 중
    ids, day = (behind.id, ahead.id), behind.erp_construction_date
    for cookies in (TABLET, PC, PHONE):
        _login(client, viewer, cookies)
        html = client.get(f"{HOME}?day={day}").get_data(as_text=True)
        assert html.index(f'data-foms-home-dayrow="{ids[0]}"') < html.index(f'data-foms-home-dayrow="{ids[1]}"'), cookies


# --------------------------------------------------------------------------- #
# G3 — 카드 품목 줄 = "치수 · 색 · 품목 이름"
# --------------------------------------------------------------------------- #
def test_g3_card_item_parts_color_from_linked_item_else_row() -> None:
    uid = "33333333-3333-4333-8333-333333333333"  # 서버 uid 꼴(36자)
    sd = {"items": [{"uid": "44444444-4444-4444-8444-444444444444", "product_name": "붙박이장", "color": "포그그레이"},
                    {"uid": uid, "product_name": "신발장", "spec_width": "900", "spec_height": "1200", "color": "화이트 무광"}]}
    assert card_item_parts(sd, {"item_uids": [uid]}, {}) == ("신발장", "W900 × H1200", "화이트 무광")  # 이은 품목의 색
    row = {"v3_product_label": "붙박이장", "v3_spec_display": "W2400", "v3_material": "포그그레이"}
    assert card_item_parts({}, {}, row) == ("붙박이장", "W2400", "포그그레이")
    assert card_item_text({}, {}, row) == ("붙박이장", "W2400")  # PC 도면 목록 창 글은 그대로(색 없음)


def test_g3_card_item_line_is_spec_color_then_name(client, cohort) -> None:
    viewer = _user("관리", role="ADMIN", team="CS")
    order = _order("윤봄", 1)
    sd = copy.deepcopy(order.structured_data)
    sd["items"][0]["color"] = "화이트 무광"
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()
    plain = _order("서가을", 1)  # 대조 — 색 없는 주문은 "치수 · 품목 이름"
    oid, plain_id, day = order.id, plain.id, order.erp_construction_date
    _login(client, viewer, TABLET)
    html = client.get(f"{HOME}?tab=parts&part=cut&day={day}").get_data(as_text=True)
    card = html.split(f'data-order-id="{oid}"', 1)[1].split("</article>", 1)[0]
    item = re.search(r'<span class="fph-dr__pr pp-item">([^<]*)</span>', card).group(1)
    assert item == "W2400 · 화이트 무광 · 붙박이장"
    plain_card = html.split(f'data-order-id="{plain_id}"', 1)[1].split("</article>", 1)[0]
    assert re.search(r'<span class="fph-dr__pr pp-item">([^<]*)</span>', plain_card).group(1) == "W2400 · 붙박이장"
