"""생산 태블릿 도면 판 작은 화면 · 흐름 고침 넷(사장님 결정 2026-11-26 — C56 · C57 · C58 · C69 · C71).

1. 남의 공장 도면의 못 누르는 상태 칸(.pp-elsewhere-note)은 테두리 · 바탕 · 그림자 없이 색 글자만(누르면 까닭 말풍선은 그대로).
2. 남의 공장 도면 묶음은 처음 접힌 한 줄(<details> "1공장 작업 n장 ›") — 누르면 펼침, 새 JS 없음.
3. [완료 취소] 줄(pp-only-done)이 '전체 도면' 칸에서도 보인다('작업 중' 칸만 숨김). 누가 무를 수 있는지는 그대로.
4. 주소 order=(옛 focus_order=)로 연 주문의 도면 칸에 is-focus 테두리 · 첫 칸으로 굴림. 아침 칩 [보기]는 같은 날이면 다시 읽지 않고
   내 칸으로 굴림, 다른 날이면 #pp-mine 으로 가서 같은 표시.

되돌리면 실패: 흰 테두리 칸이 돌아옴 · 남의 공장 칸이 펼쳐져 나옴 · 전체 도면 칸에서 취소 단추 숨김 · 연 주문 표시 없음.
대조군: order= 없는 화면은 is-focus 0 · 다른 주문 칸은 테두리 없음 · 내 공장 칸은 접힘 밖.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from tests.domains.test_production_factory_screens import F2, _html, cohort  # noqa: F401 (fixture)
from tests.support.production_factory_seed import HOME_NONE, TABLET, factory_user, mixed_order, put_mark, set_cookies
from tests.support.production_part_claim_seed import login

ROOT = Path(__file__).resolve().parents[2]
CSS = (ROOT / "static/css/contexts/production/parts.css").read_text(encoding="utf-8")
TPL = (ROOT / "templates/production/partials/home_parts.html").read_text(encoding="utf-8")
CLAIM_JS = ROOT / "static/js/production/foms-production-parts-claim.js"
PIN = "20261128g"  # parts.css 핀(11-27 비평 시안 · 카드 키 일괄 · [<파트> 같이 작업] 짝 폭 · 11-28 "누구에게 줄까요?" 사람 칸 굴림으로 올림)


def _rule(selector: str) -> str:
    m = re.search(r"(?m)^" + re.escape(selector) + r" \{([^}]*)\}", CSS)
    assert m, selector
    return m.group(1)


def _elsewhere(html: str) -> str:
    start = html.index('<section class="pp-elsewhere"')
    return html[start:html.index("</section>", start)]


# --------------------------------------------------------------------------- #
# 1. 못 누르는 칸 — 테두리 빼기(C58)
# --------------------------------------------------------------------------- #
def test_elsewhere_note_renders_as_disabled_text_with_why(client, cohort):
    seed = mixed_order(5, f2=(3, 4))
    login(client, factory_user("박엣지", part="edge"))
    set_cookies(client, TABLET)
    block = _elsewhere(_html(client))
    assert block.count('class="fph-wi pp-act pp-elsewhere-note" aria-disabled="true"') == 2  # 까닭 말풍선 칸 그대로
    assert block.count('data-pp-why="2공장에서 작업하는 도면이에요."') == 2
    assert f'data-order-id="{seed.id}"' in block


def test_elsewhere_note_css_has_no_border_background_shadow_but_keeps_color_and_focus():
    note = _rule(".fph-wi.pp-elsewhere-note")
    assert "background: transparent" in note and "border-color: transparent" in note and "box-shadow: none" in note
    assert "color: var(--fph-text)" in note  # 글자 색 그대로(회색으로 안 바꿈)
    assert "border-color: transparent" in _rule(".fph-wi.pp-elsewhere-note:hover")
    assert ".fph-wi.pp-act:focus-visible" in CSS  # 키보드 초점 테두리 유지
    # 다른 못 누르는 칸(보류 · 도면 수정 중 · 작업 시트에서 완료)은 건드리지 않았다
    assert "border-color: transparent" not in CSS.split(".fph-wi.pp-elsewhere-note {")[0]


# --------------------------------------------------------------------------- #
# 2. 남의 공장 도면 한 줄로 접기(C57 · 결정 ⑦)
# --------------------------------------------------------------------------- #
def test_elsewhere_cards_fold_into_one_closed_summary_line(client, cohort):
    seed = mixed_order(5, f2=(3, 4))
    login(client, factory_user("박엣지", part="edge"))
    set_cookies(client, TABLET)
    html = _html(client)
    block = _elsewhere(html)
    assert '<details class="pp-fold" data-pp-fold>' in block and "<details class=\"pp-fold\" data-pp-fold open" not in block  # 처음 접힘
    summary = f'<summary class="pp-fold__sum"><h3 class="pp-otherg">{F2} 작업 2장 <span class="pp-fold__go" aria-hidden="true">›</span></h3></summary>'
    assert summary in block  # 머리 글 · 장 수 그대로 + ›
    inside = block[block.index("</summary>"):block.index("</details>")]
    assert inside.count("data-pp-elsewhere ") == 2  # 남의 공장 칸은 접힘 안
    own = re.findall(r'data-pp-card data-order-id="%d"' % seed.id, html)
    assert len(own) == 3 and "data-pp-card " not in block  # 내 공장 칸은 접힘 밖 · 칸 숫자 계약 그대로
    assert 'data-pp-count="all">3<' in html


def test_fold_css_touch_target_focus_and_tab_hiding():
    assert "min-height: 48px" in _rule(".pp-fold__sum .pp-otherg")
    assert "outline: 3px solid var(--fph-brand)" in _rule(".pp-fold__sum:focus-visible")
    assert "display: none" in _rule(".pp-fold__sum::-webkit-details-marker")
    assert "rotate(90deg)" in _rule(".pp-fold[open] .pp-fold__go")
    # '내 작업' · '완료' 칸에서는 묶음째 숨김(그대로)
    assert '.fph-parts[data-pp-on="need"] .pp-elsewhere, .fph-parts[data-pp-on="done"] .pp-elsewhere { display: none; }' in CSS


def test_sync_only_edits_cards_inside_so_fold_state_survives():
    sync = (ROOT / "static/js/production/foms-production-parts-sync.js").read_text(encoding="utf-8")
    assert "data-pp-fold" not in sync and ".open" not in sync and "innerHTML" not in sync  # 접힘 칸을 다시 만들지 않는다


# --------------------------------------------------------------------------- #
# 3. [전체 도면] 칸에서도 [완료 취소](C56)
# --------------------------------------------------------------------------- #
def test_undo_row_is_rendered_for_my_done_card(client, cohort):
    seed = mixed_order(3, f2=())
    me = factory_user("박엣지", part="edge")
    put_mark(seed, 0, "edge", "DONE", me)
    login(client, me)
    set_cookies(client, TABLET)
    html = _html(client)
    assert '<span class="fph-wi pp-act pp-st-done pp-not-done">엣지 완료 · 박엣지</span>' in html
    assert ('<div class="fph-wi pp-act pp-undo-row pp-st-done pp-only-done"><span>엣지 완료 · 박엣지</span><button type="button" '
            'class="foms-prod-home__btn pp-undo" data-pp-act="undo">엣지 완료 취소</button></div>') in html


def test_undo_visible_in_all_and_done_hidden_only_in_need_view():
    rule = re.search(r"\.pp-grid:not\(\.is-need\) \.pp-only-need[^{]*\{ display: none; \}", CSS).group(0)
    assert ".pp-grid.is-need .pp-only-done" in rule and ".pp-grid:not(.is-need) .pp-not-done" in rule
    assert ".pp-grid:not(.is-done) .pp-only-done" not in CSS and ".pp-grid.is-done .pp-not-done" not in CSS
    # 짝 규칙: 취소 줄이 보이는 칸에서는 글 칸이 숨어 한 줄만(전체 · 완료 칸 높이가 같다)
    assert ".pp-grid.is-need .pp-not-need" in rule and ".pp-grid:not(.is-need) .pp-only-need" in rule


def test_who_can_undo_rule_unchanged():
    assert "{%- set can_undo = pb.writable and (c.done_by_me or not pb.mine) -%}" in TPL


# --------------------------------------------------------------------------- #
# 4. 알림 · 아침 칩으로 연 주문 표시(C69 · C71)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("arg", ["order", "focus_order"])
def test_order_arg_marks_only_that_orders_cards(client, cohort, arg):
    other = mixed_order(2, f2=())
    seed = mixed_order(3, f2=())
    login(client, factory_user("박엣지", part="edge"))
    set_cookies(client, TABLET)
    plain = _html(client)
    assert not re.search(r'<article class="pp-card[^"]* is-focus"', plain)  # 대조군: order= 없으면 테두리 0
    html = _html(client, f"/erp/production/home?{arg}={seed.id}")
    focused = re.findall(r'<article class="pp-card[^"]* is-focus"\s+data-pp-card data-order-id="(\d+)"', html)
    assert focused == [str(seed.id)] * 3
    assert not re.search(r'<article class="pp-card[^"]* is-focus"\s+data-pp-card data-order-id="%d"' % other.id, html)


def test_order_arg_marks_elsewhere_cards_too(client, cohort):
    seed = mixed_order(5, f2=(3, 4))
    login(client, factory_user("박엣지", part="edge"))
    set_cookies(client, TABLET)
    block = _elsewhere(_html(client, f"/erp/production/home?order={seed.id}"))
    assert block.count('class="pp-card is-elsewhere is-focus"') == 2


def test_focus_css_reuses_focus_token_and_morning_link_carries_hash():
    assert _rule(".pp-card.is-focus").strip() == "outline: 3px solid var(--fph-brand); outline-offset: 2px;"
    assert "{{ home_href(None, dd.part or pb.url_part, dd.key) }}#pp-mine" in TPL


def test_claim_js_scrolls_to_focus_and_morning_view_in_place():
    src = CLAIM_JS.read_text(encoding="utf-8")
    assert "scrollIntoView({ block: 'center' })" in src and "fold.open = true" in src
    assert "window.location.hash === '#pp-mine'" in src and "e.preventDefault(); setChip(false)" in src
    assert "data-picked-me=\"1\"" in src  # 아침 칩이 세는 내 칸
    assert len(src.splitlines()) <= 300
    out = subprocess.run(["node", "--check", str(CLAIM_JS)], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr


def test_pins_bumped():
    scripts = (ROOT / "templates/production/partials/home_scripts.html").read_text(encoding="utf-8")
    styles = (ROOT / "templates/production/partials/home_styles.html").read_text(encoding="utf-8")
    assert "foms-production-parts-claim.js') }}?v=20261127w" in scripts  # 11-27 반장 미정 바로 완료 · [<파트> 시작 취소]가 claim 을 한 번 더
    assert f"parts.css') }}}}?v={PIN}" in styles


def test_home_none_still_renders(client, cohort):
    mixed_order(2, f2=())
    login(client, factory_user("박엣지", part="edge"))
    set_cookies(client, TABLET)
    assert "data-pp-card" in _html(client, HOME_NONE)
