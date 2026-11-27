"""도면 카드 [같이 작업] · [시작 취소]에도 파트 이름(사장님 2026-11-27 "둘 다 파트 이름 붙이기") + 확인 창의 '안 봄' → '미정'
(같은 날 "창 글을 '미정'으로").

* 카드 단추(서버 home_parts.html pp_act · JS claim.special / crew.render · 크게 보기는 카드 단추 복사): [엣지 같이 작업] · [엣지 시작 취소].
  파트 이름은 [<파트> 시작] · [<파트> 완료]와 같은 원본(판 ``part_label`` → JS cfg.label). 카드 글의 "같이 작업" · "시작 취소"는 칸 없는
  띄어쓰기 — 칸이 모자라면 파트 이름 뒤에서만 두 줄("엣지" / "같이 작업").
* 확인 창: "엣지 같이 작업할까요?" [엣지 같이 작업] · "엣지 시작을 취소할까요?" [엣지 시작 취소], 끝난 뒤 알림 = 누른 단추 말
  ("엣지 같이 작업 시작했어요" · "엣지 시작 취소했어요").
* 창 줄: 네 파트 모두 "미정 → 작업 중 · 이름" · "미정 → 기본 · 이름" · "기본 → 미정" · "미정 → <파트> 완료 · 이름"(옛 재단 "안 봄", 그 밖 앞말 없음).
* 그대로(대조군): 반장 고르기 창 [{이름} 시작 취소] · [같이 작업](사람 이름 · 제목이 이미 말한다) · '안 본 도면 N장' · [남은 N장 모두 기본] ·
  감사 글 '안 봄' · PC 창 낱말 · 서버 거절 글.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.domains.test_production_multi_holder_board import _act, _card, _node, _page, _post, cohort  # noqa: F401
from tests.support.production_part_claim_seed import login, make_order, make_user, mark

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / "static/js/production"
TPL = ROOT / "templates/production/partials"
CSS = ROOT / "static/css/contexts/production/parts.css"
PARTS = (("cut", "재단"), ("edge", "엣지"), ("assemble", "조립"), ("inspect", "검수"))
PIN = "20261127w"


def _press(client, who, order, j, part, action, seen, **extra):
    login(client, who)
    resp = mark(client, order, j, part, action, seen, **extra)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["data"]


@pytest.mark.parametrize("part,label", PARTS)
def test_part_account_card_buttons_say_part_name(client, cohort, part, label):
    order = make_order(3, steps_done=("cut", "edge", "assemble") if part == "inspect" else ())
    me, other = make_user(f"김{label}", part=part), make_user(f"최{label}", part=part)
    _press(client, me, order, 0, part, "take", "none")  # 도면 1 = 내 작업 한 층
    _press(client, other, order, 1, part, "take", "none")  # 도면 2 = 남이 작업 중
    html = _page(client, me)
    mine, theirs = _act(_card(html, order.keys[0])), _act(_card(html, order.keys[1]))
    assert f'data-pp-act="release">{label} 시작&nbsp;취소</button>' in mine
    assert f'data-pp-act="done">{label} 완료</button>' in mine  # 짝 [<파트> 완료]는 그대로
    assert f'data-pp-act="join">{label} 같이&nbsp;작업</button>' in theirs
    assert ">시작 취소<" not in html and ">같이 작업<" not in html  # 옛 글 없음
    others = [lb for _, lb in PARTS if lb != label]
    assert not any(f">{lb} 시작&nbsp;취소<" in html or f">{lb} 같이&nbsp;작업<" in html for lb in others)  # 음성 대조


def test_js_redraw_windows_and_notices_follow_the_button(client, cohort, tmp_path):
    order = make_order(3)
    me, choi = make_user("박엣지", part="edge"), make_user("최엣지", part="edge")
    _press(client, choi, order, 1, "edge", "take", "none")
    page = tmp_path / "edge.html"
    page.write_text(_page(client, me), encoding="utf-8")
    k = order.keys
    replies = [_post(client, me, {"order_id": order.id, "drawing_key": k[1], "part": "edge", "action": "join", "seen": "need",
                                  "seen_me": "none", "seen_by": choi.id}),
               _post(client, me, {"order_id": order.id, "drawing_key": k[0], "part": "edge", "action": "take", "seen": "none",
                                  "seen_me": "none"}),
               _post(client, me, {"order_id": order.id, "drawing_key": k[0], "part": "edge", "action": "release", "seen": "need",
                                  "seen_me": "held", "seen_by": me.id})]
    assert all(r.get("success") is True for r in replies), replies
    res = _node(page, {"posts": replies, "steps": [
        {"do": "parity"},
        {"do": "click", "key": k[1], "act": "join"}, {"do": "run"}, {"do": "card", "key": k[1]},
        {"do": "click", "key": k[1], "act": "release"}, {"do": "close"},
        {"do": "click", "key": k[0], "act": "take"}, {"do": "run"}, {"do": "card", "key": k[0]},
        {"do": "click", "key": k[0], "act": "release"}, {"do": "run"}]})
    out = res["out"]
    assert out[0]["diffs"] == []  # 서버 칸 = JS 가 다시 그린 칸
    join = out[1]["modal"]
    assert (join["title"], join["run"]["text"]) == ("엣지 같이 작업할까요?", "엣지 같이 작업")
    assert join["line"] == "최엣지 작업 중 → 최엣지 · 박엣지 작업 중"
    assert out[2]["status"] == "엣지 같이 작업 시작했어요"  # 누른 단추 말 + 시작했어요
    assert [b["text"] for b in out[3]["card"]["act"][0]["kids"]] == ["엣지 시작 취소", "엣지 완료"]  # JS 다시 그리기도 파트 이름
    crew_rel = out[4]["modal"]  # 남은 사람이 있는 내 시작 취소(crew 창)
    assert (crew_rel["title"], crew_rel["run"]["text"]) == ("엣지 시작을 취소할까요?", "엣지 시작 취소")
    assert crew_rel["line"] == "최엣지 · 박엣지 작업 중 → 최엣지 작업 중"
    assert [b["text"] for b in out[8]["card"]["act"][0]["kids"]] == ["엣지 시작 취소", "엣지 완료"]
    solo = out[9]["modal"]
    assert (solo["title"], solo["line"], solo["run"]["text"]) == ("엣지 시작을 취소할까요?", "담당 박엣지 → 미정", "엣지 시작 취소")
    assert out[10]["status"] == "엣지 시작 취소했어요"


def test_source_contract_words_kept_and_changed():
    modal = (JS / "foms-production-parts-modal.js").read_text(encoding="utf-8")
    crew = (JS / "foms-production-parts-crew.js").read_text(encoding="utf-8")
    claim = (JS / "foms-production-parts-claim.js").read_text(encoding="utf-8")
    parts = (JS / "foms-production-parts.js").read_text(encoding="utf-8")
    assert "run: LABEL + ' 시작 취소'" in modal and "run: '시작 취소'" not in modal
    assert "LABEL + ' 같이\\u00a0작업', 'join'" in crew and "run: LABEL + ' 같이 작업'" in crew
    assert "c.label + ' 시작\\u00a0취소', 'release'" in claim
    assert "['remove', p.name + ' 시작 취소', 'release', p.uid]" in crew  # 대조군 — 반장 고르기 창 사람 이름 단추
    assert "['join', '같이 작업', 'join', null, true]" in crew
    assert "/ 같이 작업$/.test(p.run || '') ? p.run + ' 시작했어요'" in parts
    assert "'안 본 도면 '" in parts  # 대조군 — '안 본 도면 N장' 글 그대로
    tpl = (TPL / "home_parts.html").read_text(encoding="utf-8")
    assert "안 본 도면" in tpl
    sheet = (JS / "foms-production-sheet-parts.js").read_text(encoding="utf-8")
    assert "join: '같이 작업'" in sheet and "release: '시작 취소'" in sheet  # 대조군 — 바뀐 기록 낱말(PC · 작업 시트)
    notes = (ROOT / "foms/services/production/part_mark_notes.py").read_text(encoding="utf-8")
    assert '"안 봄" if part == BASIC_ALLOWED_PART' in notes  # 대조군 — 감사 글 낱말 그대로


def test_css_fits_longer_words_without_new_font_sizes_and_pins():
    css = CSS.read_text(encoding="utf-8")
    assert ".pp-two.pp-two--join { grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr); }" in css
    assert ".pp-two.is-mine { display: flex; }" in css and ".pp-two.is-mine > .pp-release { flex: 0 1 auto; }" in css
    assert ".pp-two.is-mine > .pp-fin { min-width: max-content; }" in css
    rule = ".pp-two.is-mine > .pp-release, .pp-two--join > .foms-prod-home__btn { padding: 0 4px; white-space: normal; word-break: keep-all;"
    assert rule in css and "font-size" not in css[css.index(rule):css.index("\n", css.index(rule))]  # 글자 크기는 그대로
    scripts = (TPL / "home_scripts.html").read_text(encoding="utf-8")
    for name in ("parts", "parts-claim", "parts-modal", "parts-crew"):
        assert f"foms-production-{name}.js') }}}}?v={PIN}" in scripts, name
    assert f"parts.css') }}}}?v={PIN}" in (TPL / "home_styles.html").read_text(encoding="utf-8")
