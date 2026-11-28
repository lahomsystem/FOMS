"""생산 새 흐름 ⓒ2 화면(설계서 2026-11-28-production-my-steps-flow §3-3 · §3-5 · §3-7 · §3-8, 사장님 답 1 · 8 · 14 · 20 · 21 · 25).

① 반장 · 관리자의 미정 카드 = 시작만 — 재단 [기본][재단 시작] · 조립 [조립 없음][조립 시작] 한 줄, 엣지 · 검수 [<파트> 시작] 하나(파트 계정과
   같은 꼴 · 같은 카드 키). 남이 작업 중인 칸 [이름 작업 중 ›] + [재단 완료](대신 완료)는 그대로. 템플릿 ↔ JS 거울(crew.render) 같은 규칙.
② 바로 완료 = [<파트> 시작] 확인 창 실행 단추 아래 작은 글 "이미 끝난 작업이면 바로 완료"(반장 · 관리자 창에만). 누르면 check 한 번 · 창 닫힘 ·
   알림 "재단 완료했어요"(cut · 409 길은 test_production_lead_direct_done_1127) · 검수 마지막 장은 "제작 완료할까요?"가 이어 뜬다.
③ 날짜 띠(태블릿 = 새 흐름 문 안): 도면 글 대신 막대(안 온 도면 빨강) + 맨 아래 색 설명 한 줄. PC 띠는 바이트 그대로(옛 원문으로 그려 견줌).
④ '도면 없음' 카드(key @order — 서버 카드는 ⓑ 몫이라 판 dict 에 넣어 그린다): 그림 칸 · 번호 칸 "도면 없음", 크게 보기 · [도면 수정 요청] 없음,
   단추 · 카드 키는 보통 카드와 같다. JS 거울 · 창 목록 줄이 @order 카드에서 죽지 않는다.
되돌리면 실패: 반장 미정 칸 [완료]가 되살아남 · 파트 계정 창에 바로 완료 글 · 태블릿 띠에 "도면 a/b" 글 · PC 띠가 바뀜 · 설명 줄 없음 ·
안 온 도면이 연두 · 도면 없음 카드가 크게 보기 단추 · 창 목록 줄 "도면 0/0". 이름은 모두 지어낸 값이다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from flask import template_rendered

from tests.domains.test_production_multi_holder_board import _act, _card, _node, _page, _post, cohort  # noqa: F401
from tests.domains.test_production_multi_parts import _get, _tablet, _user
from tests.domains.test_production_part_board import _files, _order
from foms.services.common.html_whitespace import trim_html_indentation
from tests.support.color_contrast import hex_rgb, pair_distances
from tests.support.production_factory_seed import HOME_NONE
from tests.support.production_part_claim_seed import Seed, finish, login, make_order, make_user, mark

ROOT = Path(__file__).resolve().parents[2]
HOME = "/erp/production/home"
DIRECT = "이미 끝난 작업이면 바로 완료"
HOME_CSS = (ROOT / "static/css/contexts/production/home.css").read_text(encoding="utf-8").replace("\r\n", "\n")
PARTS_CSS = (ROOT / "static/css/contexts/production/parts.css").read_text(encoding="utf-8").replace("\r\n", "\n")
TABLET = "@media (min-width: 992px) and (orientation: landscape) and (pointer: coarse) {"
BASIC_BTN = '<button type="button" class="foms-prod-home__btn pp-pick-basic" data-pp-act="basic">{}</button>'
LEAD_TAKE = '<button type="button" class="foms-prod-home__btn{}" data-pp-act="take">{} 시작</button>'
# 옛 날짜 띠 원문(세션 머리 7de2b88e2 home_date.html 14-37행 그대로) — PC 띠가 이것과 바이트까지 같아야 한다(사장님 22번 답 "PC 도 같이"는 안 고르심)
OLD_STRIP = """{% from 'production/partials/home_date_macros.html' import home_href %}
  <div class="fph-stripbox">
  <aside class="fph-strip" aria-label="출고일 2주">
    <div class="fph-strip__h">출고일 2주<small>만들 것 / 전체</small></div>
    {% for d in days.strip %}
    <a class="fph-sd{% if d.key == days.selected %} is-on{% endif %}{% if d.is_weekend %} is-wk{% endif %}{% if not d.total %} is-zero{% endif %}"
       href="{{ home_href(tab, part_board.url_part if part_board else None, d.key, factory=part_board.url_factory if part_board else None) }}" data-foms-erp-no-shell="1" data-foms-home-daybtn="{{ d.key }}"{% if d.key == days.selected %} aria-current="true"{% endif %}>
      {%- set sub = d.sub ~ (' · 없음' if not d.total and not d.show_day else '') %}
      <span class="fph-sd__d"><b>{{ d.label }}</b><small>{{ sub }}</small></span>
      {%- if pc_view %}{# PC #}
      {%- set _bar %}<svg class="fph-sd__bar" viewBox="0 0 100 10" preserveAspectRatio="none" aria-hidden="true">{% for s in d.segs %}<rect class="is-{{ s.k }}" x="{{ s.x }}" y="0" width="{{ s.w }}" height="10"/>{% endfor %}</svg>{% endset %}
      {% if d.arrival %}<span class="fph-sd__mid">{{ _bar }}<span class="fph-sd__dw is-{{ d.arrival.state }}">{{ d.arrival.strip }}</span></span>{% else %}{{ _bar }}{% endif %}
      {%- else %}{# 태블릿(옛) #}
      <span class="fph-sd__mid">{% if d.arrival %}<span class="fph-sd__dw is-{{ d.arrival.state }}">{{ d.arrival.strip }}</span>{% endif %}</span>
      {%- endif %}
      <span class="fph-sd__n">{% if d.total or d.show_day %}<b>{{ d.make }}</b><small> / {{ d.total }}</small>{% endif %}</span>{# 빈 날 #}
    </a>
    {% endfor %}
    <div class="fph-strip__f">
      {% for d in days.footer %}
      <a class="fph-sf{% if d.key == days.selected %} is-on{% endif %}" href="{{ home_href(tab, part_board.url_part if part_board else None, d.key, factory=part_board.url_factory if part_board else None) }}" data-foms-erp-no-shell="1" data-foms-home-daybtn="{{ d.key }}"{% if d.key == days.selected %} aria-current="true"{% endif %}>{{ d.label }} {{ d.total }}건{% if d.hidden %}<small>{{ d.hidden }}건 더</small>{% endif %}</a>
      {% endfor %}
    </div>
  </aside>
  </div>"""


def _board(part: str) -> str:
    return HOME_NONE + "&tab=parts&part=" + part


def _box(html: str, key: str) -> str:
    inner = _act(_card(html, key)).strip()
    assert inner.endswith("</div>")
    return inner[:-len("</div>")].strip()


# --------------------------------------------------------------------------- #
# ① 반장 · 관리자 미정 카드 = 시작만(템플릿 · JS 거울)
# --------------------------------------------------------------------------- #
def test_lead_unseen_cards_start_only_on_all_four_parts_and_proxy_finish_kept(client, cohort):
    order, ready = make_order(2), make_order(1, steps_done=("cut", "edge", "assemble"))  # ready = 검수 칸이 열린 주문
    lead, admin, kim = make_user("박반장", lead=True), make_user("관리", team="CS", role="ADMIN"), make_user("김재단", part="cut")
    login(client, kim)
    assert mark(client, order, 1, "cut", "take", "none").status_code == 200  # 도면 2 = 김재단 작업 중(대신 완료 대조군)
    want = {"cut": "<div class=\"pp-two\">" + BASIC_BTN.format("기본") + LEAD_TAKE.format("", "재단") + "</div>",
            "assemble": "<div class=\"pp-two\">" + BASIC_BTN.format("조립 없음") + LEAD_TAKE.format("", "조립") + "</div>",
            "edge": LEAD_TAKE.format(" pp-act", "엣지"), "inspect": LEAD_TAKE.format(" pp-act", "검수")}
    for who in (lead, admin):
        for part, box in want.items():
            page = _page(client, who, _board(part))
            key = ready.keys[0] if part == "inspect" else order.keys[0]
            assert _box(page, key) == box, (who.name, part)
            assert '<div class="fph-parts" data-pp-pane=' in page and "pp-finrow" not in page  # 카드 키 = 파트 계정 판과 같은 꼴
            assert page.count(f'data-pp-direct hidden>{DIRECT}</button>') == 1  # 바로 완료 글 자리는 창 안 하나
    cut = _page(client, lead, _board("cut"))
    held = _box(cut, order.keys[1])
    assert 'data-pp-act="held"' in held and "김재단" in held  # [김재단 작업 중 ›]
    assert held.endswith('<button type="button" class="fph-qr__done pp-act pp-fin pp-only-need" data-pp-act="check">재단 완료</button>')
    assert cut.count('data-pp-act="check"') == 1  # 판 전체에서 대신 완료 하나뿐(미정 칸에는 없다)


def test_part_account_cards_and_window_unchanged(client, cohort):
    order = make_order(2)
    cut = _page(client, make_user("오재단", part="cut"))
    assert _box(cut, order.keys[0]) == ("<div class=\"pp-two\">" + BASIC_BTN.format("기본")
                                        + LEAD_TAKE.format(" foms-prod-home__btn--pri", "재단") + "</div>")
    edge = _page(client, make_user("박엣지", part="edge"))
    assert _box(edge, order.keys[0]) == LEAD_TAKE.format(" foms-prod-home__btn--pri pp-act", "엣지")
    for page in (cut, edge):
        assert '<div class="fph-parts" data-pp-pane=' in page and DIRECT not in page and "data-pp-direct" not in page
        assert 'data-pp-act="check"' not in page
    view = _page(client, make_user("상담", team="CS"), _board("cut"))  # 보기만 = 창 없음 · 단추 없음
    assert "data-pp-direct" not in view and "<button" not in _act(_card(view, order.keys[0]))


def test_js_mirror_draws_the_same_start_only_cards(client, cohort, tmp_path):
    order, ready = make_order(3), make_order(1, steps_done=("cut", "edge", "assemble"))
    lead = make_user("박반장", lead=True)
    login(client, make_user("김재단", part="cut"))
    mark(client, order, 1, "cut", "take", "none")
    for part in ("cut", "edge", "assemble", "inspect"):
        page = tmp_path / f"lead_{part}.html"
        page.write_text(_page(client, lead, _board(part)), encoding="utf-8")
        out = _node(page, {"steps": [{"do": "parity"}, {"do": "card", "key": order.keys[0]}]})["out"]
        assert out[0]["cards"] == 4 and out[0]["diffs"] == [], (part, out[0]["diffs"])  # 서버 칸 = JS 가 다시 그린 칸
        acts = [a["act"] for a in out[1]["card"]["act"]] + [k["act"] for a in out[1]["card"]["act"] for k in a["kids"]]
        assert "check" not in acts, part


def test_part_account_window_has_no_direct_link(client, cohort, tmp_path):
    order = make_order(2)
    page = tmp_path / "kim.html"
    page.write_text(_page(client, make_user("김재단", part="cut")), encoding="utf-8")
    out = _node(page, {"steps": [{"do": "click", "key": order.keys[0], "act": "take"}, {"do": "direct"}]})["out"]
    assert out[0]["modal"]["title"] == "재단 시작할까요?" and out[1]["direct"] is None  # 창은 그대로, 바로 완료 글은 없다


def test_direct_link_on_last_inspect_drawing_asks_to_complete(client, cohort, tmp_path):
    """검수 마지막 장 — 바로 완료 뒤 지금처럼 같은 창이 "제작 완료할까요?"(바로 완료 글은 숨음)."""
    order = make_order(1)
    login(client, make_user("관리", team="CS", role="ADMIN"))
    for part in ("cut", "edge", "assemble"):
        finish(client, order, 0, part)
    lead = make_user("박반장", lead=True)
    page = tmp_path / "inspect.html"
    page.write_text(_page(client, lead, _board("inspect")), encoding="utf-8")
    reply = _post(client, lead, {"order_id": order.id, "drawing_key": order.keys[0], "part": "inspect", "action": "check",
                                 "seen": "none", "seen_me": "none"})
    assert reply["data"]["order_ready"] == {"order_id": order.id}
    res = _node(page, {"posts": [reply], "steps": [
        {"do": "click", "key": order.keys[0], "act": "take"}, {"do": "press", "sel": "[data-pp-direct]"}, {"do": "direct"}]})
    out, calls = res["out"], res["calls"]
    assert [c["body"]["action"] for c in calls] == ["check"]
    w = out[1]["modal"]
    assert w["hidden"] is False and w["title"] == "제작 완료할까요?" and w["close"] == "나중에" and w["run"]["text"] == "제작 완료"
    assert out[1]["status"] == "검수 완료했어요" and out[2]["direct"]["hidden"] is True
    assert w["body"] == f"가짜고객 #{order.id} · 도면 1장이 모두 완료됐어요. 제작 완료하면 시공 대기로 넘어가요."  # 도면 카드는 장수 그대로


def test_order_card_last_inspect_asks_to_complete_without_sheet_count(client, cohort, tmp_path):
    """'도면 없음' 카드(@order) 검수 마지막 — 이어 뜨는 창 몸 글에 "도면 0장" 같은 장수가 없다(11-28 걷기 어긋남 1)."""
    plain = Seed(make_order(0).id, ("@order",))
    login(client, make_user("관리", team="CS", role="ADMIN"))
    for part in ("cut", "edge", "assemble"):
        assert finish(client, plain, 0, part).status_code == 200
    lead = make_user("박반장", lead=True)
    page = tmp_path / "inspect_order.html"
    page.write_text(_page(client, lead, _board("inspect")), encoding="utf-8")
    reply = _post(client, lead, {"order_id": plain.id, "drawing_key": "@order", "part": "inspect", "action": "check",
                                 "seen": "none", "seen_me": "none"})
    assert reply["data"]["order_ready"] == {"order_id": plain.id}
    res = _node(page, {"posts": [reply], "steps": [
        {"do": "click", "key": "@order", "act": "take"}, {"do": "press", "sel": "[data-pp-direct]"}]})
    w = res["out"][1]["modal"]
    assert [c["body"]["action"] for c in res["calls"]] == ["check"] and w["title"] == "제작 완료할까요?"
    assert w["body"] == f"가짜고객 #{plain.id} · 모두 완료됐어요. 제작 완료하면 시공 대기로 넘어가요."


# --------------------------------------------------------------------------- #
# ③ 날짜 띠 — 태블릿 막대 + 색 설명 / PC 바이트 그대로
# --------------------------------------------------------------------------- #
def _strip(html: str) -> str:
    start = html.index('<div class="fph-stripbox">')
    return html[start:html.index("</aside>", start) + len("</aside>")]


def _seed_strip() -> None:
    _order("한빛", _files("s1", 2))  # 내일 — 제작 대기(미정 주황)
    _order("두빛", [], stage="DRAWING")  # 내일 — 도면 기다림(안 온 도면 빨강)
    _order("세빛", _files("s3", 1), day=3)


def test_tablet_strip_draws_bars_and_legend_without_drawing_text(client, cohort):
    _seed_strip()
    _tablet(client, _user("최보기"))  # 읽기 전용 = 새 흐름 문 안(작업 중 탭)
    html = _get(client, HOME)
    strip = _strip(html)
    rows = re.findall(r'<a class="fph-sd[ "].*?</a>', strip, re.S)
    assert len(rows) == 13
    assert "fph-sd__dw" not in strip and not any("도면 " in r for r in rows)  # "도면 a/b" 글 · 마감 색 글 없음(답 21)
    full = [r for r in rows if "<b>0</b>" not in r and 'class="fph-sd__n"></span>' not in r]
    assert all('<span class="fph-sd__mid"><svg class="fph-sd__bar"' in r for r in full) and len(full) >= 2
    empty = [r for r in rows if 'class="fph-sd__n"></span>' in r]
    assert empty and all('<span class="fph-sd__mid"></span>' in r for r in empty)  # 빈 날 = 빈 가운데 칸(숫자 자리)
    tomorrow = next(r for r in rows if "aria-current" in r)
    assert '<rect class="is-w"' in tomorrow and '<rect class="is-x"' in tomorrow  # 미정 · 안 온 도면 조각
    legend = ('<p class="fph-lg" aria-hidden="true"><span><i class="is-f"></i>완료</span><span><i class="is-p"></i>작업 중</span>'
              '<span><i class="is-w"></i>미정</span><span><i class="is-x"></i>안 온 도면</span></p>')
    assert strip.count(legend) == 1 and strip.index('class="fph-strip__f"') < strip.index(legend)  # 아래 단추 둘 밑
    assert strip.endswith(legend + "\n</aside>")  # 응답은 줄 앞 들여쓰기를 지운다(html_whitespace)
    assert "만들 것 / 전체" in strip and strip.count('data-foms-home-daybtn="') == 15  # 머리 글 · 줄 수 · 아래 단추 둘 그대로


def _captured(app, client, url: str) -> tuple[str, dict]:
    seen: list[dict] = []

    def grab(sender, template, context, **extra):
        if template.name == "production/home.html":
            seen.append(dict(context))

    template_rendered.connect(grab, app)
    try:
        html = _get(client, url)
    finally:
        template_rendered.disconnect(grab, app)
    return html, seen[-1]


def _old_strip(app, ctx: dict) -> str:
    """옛 원문을 같은 템플릿 값으로 그리고 응답과 같은 줄 앞 들여쓰기 지우기를 거친 띠 — 서버가 내보낼 바이트 그대로."""
    with app.test_request_context(HOME):
        html = app.jinja_env.from_string(OLD_STRIP).render(**ctx)
    return _strip(trim_html_indentation(html.encode("utf-8")).decode("utf-8"))


def test_pc_and_door_outside_strips_are_byte_identical_to_before(app, client, cohort):
    _seed_strip()
    _tablet(client, _user("최보기"))
    client.set_cookie("foms_ptr", "fine", domain="localhost")  # PC(마우스)
    html, ctx = _captured(app, client, HOME)
    assert ctx["pc_view"] is True and ctx["flow"] is None
    assert _strip(html) == _old_strip(app, ctx)  # 막대 + 도면 글 그대로, 설명 줄 없음
    assert "fph-lg" not in html and _strip(html).count('class="fph-sd__bar"') == 13 and "fph-sd__dw is-" in _strip(html)
    client.set_cookie("foms_ptr", "coarse", domain="localhost")
    client.set_cookie("foms_scr", "390", domain="localhost")  # 폰(긴 변 992 미만 — 새 흐름 문 밖)
    html, ctx = _captured(app, client, HOME)
    assert ctx["pc_view"] is False and ctx["flow"] is None
    assert _strip(html) == _old_strip(app, ctx) and "fph-lg" not in html  # 폰도 한 글자도 안 바뀐다(공통 문서 1)


def test_strip_css_red_only_with_legend_and_fits_the_container_rule():
    assert ".fph-sd__bar rect.is-x { fill: var(--fph-wait-300); }" in HOME_CSS  # PC 띠의 기다림 연두 그대로
    assert ".fph-strip:has(> .fph-lg) .fph-sd__bar rect.is-x { fill: var(--fph-dw-late); }" in HOME_CSS  # 설명이 있는 띠(태블릿)만 빨강
    lg = re.search(r"\n\.fph-lg \{([^}]*)\}", HOME_CSS).group(1)
    for piece in ("position: sticky;", "bottom: 0;", "flex-shrink: 0;", "padding: 6px 14px;", "border-top: 1px solid var(--fph-line);",
                  "font-size: calc(12px * var(--foms-fs, 1));", "line-height: 1.25;", "background: var(--fph-surface);"):
        assert piece in lg, piece
    swatch = {k: re.search(rf"\.fph-lg \.is-{k} \{{ background: ([^;]+); \}}", HOME_CSS).group(1) for k in "fpwx"}
    bar = {k: re.search(rf"\n\.fph-sd__bar rect\.is-{k} \{{ fill: ([^;]+); \}}", HOME_CSS).group(1) for k in "fpw"}
    assert swatch == {**bar, "x": "var(--fph-dw-late)"}  # 설명 칸 색 = 막대 조각 색
    base = re.search(r"@container fph-strip \(min-height: calc\(([^\n]+)\)\) \{", HOME_CSS).group(1)
    guard = re.search(r"@container fph-strip \(max-height: calc\(([^\n]+)\)\) \{\n  ([^\n]+)\n\}", HOME_CSS)
    assert guard.group(1) == base + " + 13px + 0.9375rem - 0.02px"  # 설명 줄 키(6 + 6 + 12 × 1.25 × 배율 + 선 1)까지 들어갈 때만 44px
    assert guard.group(2) == ".fph-strip:has(> .fph-lg) .fph-sd { flex-shrink: 0; min-height: 48px; }"


def test_four_bar_colors_stay_apart_for_color_blind_eyes():
    tokens = dict(re.findall(r"(--fph-[\w-]+): (#[0-9a-f]{6});", HOME_CSS))
    colors = {"완료": tokens["--fph-ok"], "작업 중": tokens["--fph-brand"], "미정": "#f59e0b", "안 온 도면": tokens["--fph-dw-late"]}
    names = list(colors)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            normal, deut, prot = pair_distances(hex_rgb(colors[a]), hex_rgb(colors[b]))
            assert normal >= 10 and deut >= 6 and prot >= 6, (a, b, normal, deut, prot)  # 상태 색 쌍 규칙(재서 고른다)
            assert min(normal, deut, prot) >= 17, (a, b)  # 잰 값(2026-11-28): 가장 가까운 짝 = 완료 · 안 온 도면 녹색맹 17.7


# --------------------------------------------------------------------------- #
# ② 창 안 바로 완료 글 단추 CSS
# --------------------------------------------------------------------------- #
def test_direct_link_is_a_small_underlined_text_button_with_44px_target():
    rule = re.search(r"\.foms-prod-home \.pp-modal \.pp-mdirect \{([^}]*)\}", PARTS_CSS).group(1)
    for piece in ("min-height: 44px;", "border: 0;", "background: transparent;", "text-decoration: underline;", "align-self: flex-end;",
                  "font-size: calc(16px * var(--foms-fs, 1));"):
        assert piece in rule, piece
    assert ".foms-prod-home .pp-modal .pp-mdirect[hidden] { display: none; }" in PARTS_CSS
    block = PARTS_CSS[PARTS_CSS.index(TABLET, PARTS_CSS.index("가로 터치 태블릿 누름 칸")):]
    block = block[:block.index("\n}\n")]
    assert ".foms-prod-home .pp-modal .pp-mdirect { min-height: calc(44px / var(--foms-ui-zoom, 1)); }" in block  # 80% 에서도 보이는 44px


# --------------------------------------------------------------------------- #
# ④ '도면 없음' 카드(@order)
# --------------------------------------------------------------------------- #
@pytest.fixture
def order_card(monkeypatch):
    """'도면 없음' 카드 = 서버(order_card · part_board)가 도면 0장 생산 주문에 주는 진짜 카드(key @order · no 0 · of 0).
    여기서는 그 주문에 [도면 수정 요청] 고르기만 억지로 넣는다 — 고르기가 있어도 카드에 단추가 없어야 한다(템플릿 문)."""
    import foms.web.production.home as home

    real = home.build_part_board
    made: dict = {}

    def board(*args, **kwargs):
        b = real(*args, **kwargs)
        if made.get("oid"):
            b["req_opts"] = {**(b.get("req_opts") or {}), made["oid"]: [{"no": 0, "label": "도면 없음"}]}  # 있어도 단추 없음
        return b

    monkeypatch.setattr(home, "build_part_board", board)
    return made


def test_order_card_shows_no_drawing_and_keeps_buttons(client, cohort, order_card):
    order = make_order(2)
    order_card["oid"] = make_order(0).id
    for who, url in ((make_user("박반장", lead=True), _board("assemble")), (make_user("최조립", part="assemble"), HOME_NONE)):
        page = _page(client, who, url)
        card, normal = _card(page, "@order"), _card(page, order.keys[0])
        assert 'data-order-card="1"' in card and 'data-order-card' not in normal
        assert '<span class="pp-img pp-none">도면 없음</span>' in card and "data-pp-open" not in card and "<img" not in card
        assert '<span class="pp-no">도면 없음</span>' in card and "작업 시트 열기 · 도면 없음" in card and "도면 0/0" not in card
        assert "data-pp-req" not in card and "pp-ptag" not in card  # [도면 수정 요청] · 펜 기록 딱지 없음
        assert _act(card) == _act(normal)  # 단추는 보통 카드와 같다([조립 없음][조립 시작])
        assert 'class="pp-img" data-pp-open' in normal and '<span class="pp-no">도면 1/2</span>' in normal  # 대조군 — 보통 카드 그대로


def test_js_mirror_redraws_order_card_and_window_names_it(client, cohort, order_card, tmp_path):
    order = make_order(2)
    order_card["oid"] = make_order(0).id
    lead, kim = make_user("박반장", lead=True), make_user("김재단", part="cut")
    page = tmp_path / "lead.html"
    page.write_text(_page(client, lead, _board("cut")), encoding="utf-8")
    took = _post(client, kim, {"order_id": order.id, "drawing_key": order.keys[1], "part": "cut", "action": "take", "seen": "none",
                               "seen_me": "none"})
    assert took["success"] is True
    login(client, lead)  # 받아 오기 표시는 보는 사람 몫(crew.me)으로 온다 — 반장이 받은 꼴 그대로 @order 카드에
    got = client.get(f"/api/production/part-marks?order_ids={order.id}&since=2000-01-01T00:00:00").get_json()["data"]["marks"]
    held = {**next(m for m in got if m["drawing_key"] == order.keys[1]), "order_id": order_card["oid"], "drawing_key": "@order"}
    out = _node(page, {"steps": [{"do": "parity"}, {"do": "click", "key": "@order", "act": "take"}, {"do": "direct"}, {"do": "close"},
                                 {"do": "apply", "key": "@order", "mark": held}, {"do": "card", "key": "@order"}]})["out"]
    assert out[0]["cards"] == 3 and out[0]["diffs"] == []  # @order 카드도 서버 칸 = JS 칸
    assert out[1]["modal"]["title"] == "재단 시작할까요?" and out[2]["direct"]["hidden"] is False
    assert out[2]["list"].startswith("도면 없음가짜고객 #") and out[2]["list"].count("도면 없음") == 2 and "0/0" not in out[2]["list"]
    after = out[5]["card"]
    assert after["state"] == "need" and [a["act"] for a in after["act"]] == ["held", "check"]  # 받아 오기로 다시 그려도 안 죽는다
