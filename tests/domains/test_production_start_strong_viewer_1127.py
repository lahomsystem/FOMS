"""생산 태블릿 두 가지 작은 고침(사장님 2026-11-27 질문 창 답).

일 1 "재단처럼 진하게": 엣지 · 조립 · 검수 계정 자기 판의 미정 칸 [<파트> 시작]이 재단 계정 [재단 시작]처럼 진한 남색
  (``foms-prod-home__btn--pri``). 반장 · 관리자 칸은 그대로 옅게(비평 C59 — 2026-11-28 흐름부터 미정 칸은 시작만, 바로 완료는 시작 창 안).
  서버(home_parts.html pp_act)와 JS(crew.render) 그림이 같은 클래스 — 크게 보기는 카드 단추를 복사하므로 따라 진해진다.
일 2 "둘 다 고치기" → "단추는 그대로, 글만 더하기"(사장님 11-27 두 번째 답, 지휘 마무리 고침): 완료된 도면의 카드에 완료 줄
  (글 + [<파트> 완료 취소])이 보이면 크게 보기에도 그 글("재단 완료 · 박재단", 카드 글 칸 그대로)을 단추 앞에 한 번. 단추 목록은 그대로.
  계정을 가르지 않는다. 자기 몫만 완료("재단 1/2 완료" — 이름 칸 둘째 줄에 이미 있음) · 카드가 완료 줄을 안 보여 줄 때(작업 중 칸) ·
  기본 · 남이 작업 중 · 미정 · 내 작업 · 남의 완료 글 칸은 지금 그대로.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.domains.test_production_multi_holder_board import _act, _card, _node, _page, _post, cohort  # noqa: F401
from tests.support.production_factory_seed import HOME_NONE
from tests.support.production_part_claim_seed import HOME_MINE, login, make_order, make_user, mark

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / "static/js/production"
TPL = ROOT / "templates/production/partials/home_parts.html"
VIEWER_CHECK = ROOT / "tests/support/production_viewer_zoom_node_checks.js"
PRI = "foms-prod-home__btn foms-prod-home__btn--pri"
LEAD_CUT = HOME_NONE + "&tab=parts&part=cut"


def _press(client, who, order, j, action, seen, part="cut"):
    login(client, who)
    resp = mark(client, order, j, part, action, seen)
    assert resp.status_code == 200, resp.get_json()


# --------------------------------------------------------------------------- #
# 일 1 — [<파트> 시작] 진하게
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("part,label", (("edge", "엣지"), ("inspect", "검수")))  # 조립은 11-28 부터 재단 꼴([조립 없음][조립 시작])
def test_part_account_start_is_strong_like_cut(client, cohort, part, label):
    order = make_order(2, steps_done=("cut", "edge", "assemble") if part == "inspect" else ())
    act = _act(_card(_page(client, make_user(f"가짜{label}", part=part)), order.keys[0]))
    assert f'<button type="button" class="{PRI} pp-act" data-pp-act="take">{label} 시작</button>' in act
    assert act.count("btn--pri") == 1  # 진한 단추는 한 칸에 하나


def test_cut_account_and_lead_boards_are_unchanged(client, cohort):
    order = make_order(2)
    cut = _act(_card(_page(client, make_user("김재단", part="cut")), order.keys[0]))
    assert f'<button type="button" class="{PRI}" data-pp-act="take">재단 시작</button>' in cut  # 본보기 = 그대로
    lead = make_user("박반장", lead=True)
    for part, label in (("cut", "재단"), ("edge", "엣지"), ("assemble", "조립")):
        act = _act(_card(_page(client, lead, HOME_NONE + "&tab=parts&part=" + part), order.keys[0]))
        assert f'data-pp-act="take">{label} 시작</button>' in act and "btn--pri" not in act  # 반장 칸 [<파트> 시작]은 옅게 그대로
        assert 'data-pp-act="check"' not in act  # 11-28 흐름: 미정 칸에 [<파트> 완료] 없음(시작 창 안 바로 완료)
    admin = _act(_card(_page(client, make_user("관리", team="CS", role="ADMIN"), HOME_NONE + "&tab=parts&part=edge"),
                       order.keys[0]))
    assert '<button type="button" class="foms-prod-home__btn pp-act" data-pp-act="take">엣지 시작</button>' in admin
    view = _act(_card(_page(client, make_user("상담", team="CS"), HOME_NONE + "&tab=parts&part=edge"), order.keys[0]))
    assert "<button" not in view  # 보기만 = 단추 없음


def test_js_redraw_draws_the_same_strong_start(client, cohort, tmp_path):
    order = make_order(3)
    me = make_user("박엣지", part="edge")
    page = tmp_path / "edge.html"
    page.write_text(_page(client, me), encoding="utf-8")
    took = _post(client, me, {"order_id": order.id, "drawing_key": order.keys[0], "part": "edge", "action": "take",
                              "seen": "none", "seen_me": "none"})
    assert took["success"] is True
    out = _node(page, {"posts": [took], "steps": [{"do": "parity"}, {"do": "card", "key": order.keys[1]}]})["out"]
    assert out[0]["cards"] == 3 and out[0]["diffs"] == []  # 서버 칸 = JS 가 다시 그린 칸
    assert out[1]["card"]["act"] == [{"tag": "button", "cls": PRI + " pp-act", "act": "take", "text": "엣지 시작", "kids": []}]
    lead = tmp_path / "lead.html"
    lead.write_text(_page(client, make_user("박반장", lead=True), HOME_NONE + "&tab=parts&part=edge"), encoding="utf-8")
    res = _node(lead, {"posts": [], "steps": [{"do": "parity"}, {"do": "card", "key": order.keys[1]}]})["out"]
    assert res[0]["diffs"] == []
    assert res[1]["card"]["act"] == [{"tag": "button", "cls": "foms-prod-home__btn pp-act", "act": "take", "text": "엣지 시작", "kids": []}]  # 반장 = 옅게 · 시작만


def test_source_contract_strong_start_and_viewer_width():
    crew = (JS / "foms-production-parts-crew.js").read_text(encoding="utf-8")
    tpl = TPL.read_text(encoding="utf-8")
    assert "'foms-prod-home__btn' + (o.mine ? ' foms-prod-home__btn--pri' : '') + (o.cut ? '' : ' pp-act'), LABEL + ' 시작', 'take'" in crew
    assert ('<button type="button" class="foms-prod-home__btn{% if pb.mine %} foms-prod-home__btn--pri{% endif %} pp-act" data-pp-act="take">'
            '{{ pb.part_label }} 시작</button>') in tpl  # 11-28 흐름: 반장 · 관리자 엣지 칸도 같은 줄(진하게는 파트 계정만)
    assert tpl.count("btn--pri") == 3  # 재단 시작(파트 계정) · 파트 시작(새) · 같이 작업 — 반장 칸에는 없다
    css = (ROOT / "static/css/contexts/production/parts.css").read_text(encoding="utf-8")
    assert ".pp-vact .foms-prod-home__btn--pri { min-width: 250px; }" in css  # 크게 보기에서 재단 계정과 같은 꼴(CSS 는 그대로)
    assert len(crew.splitlines()) <= 181


# --------------------------------------------------------------------------- #
# 일 2 — 완료된 도면 크게 보기 = 카드 완료 줄(글 + [완료 취소])
# --------------------------------------------------------------------------- #
def _viewer(html: str, tmp_path: Path, steps: list[dict]) -> list[dict]:
    page = tmp_path / "board.html"
    page.write_text(html, encoding="utf-8")
    node = shutil.which("node")
    assert node, "node must be on PATH for JS checks"
    proc = subprocess.run([node, str(VIEWER_CHECK), str(page), json.dumps({"steps": steps}, ensure_ascii=False)],
                          capture_output=True, text=True, encoding="utf-8", timeout=60, cwd=str(ROOT))
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)["out"]


def _acts(snap: dict) -> list[tuple[str, str]]:
    """창 아래 줄 — (단추면 대신 누를 이름 · 글 칸이면 '', 글)."""
    return [(a["proxy"], a["text"]) for a in snap["acts"]]


def _seed(client):
    """도면 7장(재단): 0 = 박재단 완료, 1 = 오재단 완료, 2 = 박재단 기본, 3 = 박재단 작업 중, 4 = 미정,
    5 = 박반장 시작 → 박재단 같이 작업 → 박반장 자기 몫 완료("재단 1/2 완료"), 6 = 박재단 시작 → 오재단 같이 → 박재단 자기 몫 완료."""
    park, oh, lead = make_user("박재단", part="cut"), make_user("오재단", part="cut"), make_user("박반장", lead=True)
    order = make_order(7)
    _press(client, park, order, 0, "take", "none")
    _press(client, park, order, 0, "done", "need")
    _press(client, oh, order, 1, "take", "none")
    _press(client, oh, order, 1, "done", "need")
    _press(client, park, order, 2, "basic", "none")
    _press(client, park, order, 3, "take", "none")
    _press(client, lead, order, 5, "take", "none")
    _press(client, park, order, 5, "join", "need")
    _press(client, lead, order, 5, "done", "need")
    _press(client, park, order, 6, "take", "none")
    _press(client, oh, order, 6, "join", "need")
    _press(client, park, order, 6, "done", "need")
    return park, oh, lead, order


def test_lead_done_drawing_viewer_shows_card_done_line(client, cohort, tmp_path):
    park, _oh, lead, order = _seed(client)
    html = _page(client, lead, LEAD_CUT)
    card = _act(_card(html, order.keys[0]))
    assert '<span class="fph-wi pp-act pp-st-done pp-not-done">재단 완료 · 박재단</span>' in card  # 카드 글(원본)
    out = _viewer(html, tmp_path, [{"do": "open", "no": n} for n in (1, 2, 3, 4, 5, 6)])
    done = out[0]
    assert _acts(done) == [("", "재단 완료 · 박재단"), ("undo", "재단 완료 취소")]
    assert done["acts"][0]["cls"] == "fph-wi pp-st-done"  # 카드 완료 줄 색 클래스 그대로(새 배지 없음)
    assert _acts(out[1]) == [("", "재단 완료 · 오재단"), ("undo", "재단 완료 취소")]
    # (나) 자기 몫만 완료 — 고치기 전과 글자까지 같다(글 칸 안 붙음, 단추 셋 그대로)
    half = _acts(out[5])
    assert [p for p, _ in half] == ["held", "check", "undo"] and half[1:] == [("check", "재단 완료"), ("undo", "재단 완료 취소")]
    assert half[0][1].count("재단 1/2 완료") == 1  # 이름 칸 둘째 줄 한 번뿐
    # 그대로인 것 — 기본(완료 아님) · 남이 작업 중(다) · 미정(라)
    assert _acts(out[2]) == [("undo", "기본 취소")]
    assert [p for p, _ in _acts(out[3])] == ["held", "check"] and "오재단" not in _acts(out[3])[0][1]  # 글 칸 안 붙음
    assert [p for p, _ in _acts(out[4])] == ["basic", "take"]  # 11-28 흐름: 미정 = 시작만


def test_part_account_viewer_adds_only_own_done_line(client, cohort, tmp_path):
    park, _oh, _lead, order = _seed(client)
    html = _page(client, park)
    out = _viewer(html, tmp_path, [{"do": "open", "no": n} for n in (1, 2, 5, 7)])
    assert _acts(out[0]) == [("", "재단 완료 · 박재단"), ("undo", "재단 완료 취소")]  # 내 완료 — 지휘 11-27 이 한 가지만 바뀜
    assert _acts(out[1]) == [("", "재단 완료 · 오재단")]  # 남의 완료 글 칸 = 그대로(단추 없음)
    assert [p for p, _ in _acts(out[2])] == ["basic", "take"]
    assert _acts(out[3]) == [("undo", "재단 완료 취소")]  # 내 몫만 완료 = 고치기 전 그대로(글 칸 안 붙음)
    mine = _viewer(_page(client, park, HOME_MINE), tmp_path, [{"do": "open", "no": 4}])  # 내 작업은 '내 공정' 탭(2026-11-28 흐름)
    assert [p for p, _ in _acts(mine[0])] == ["release", "done"]  # 내 작업 [재단 시작 취소][재단 완료] = 그대로


def test_need_view_hides_done_line_so_viewer_adds_nothing(client, cohort, tmp_path):
    _park, _oh, lead, order = _seed(client)
    html = _page(client, lead, LEAD_CUT)
    out = _viewer(html, tmp_path, [{"do": "view", "v": "need"}, {"do": "open", "no": 1}, {"do": "close"},
                                   {"do": "view", "v": "done"}, {"do": "open", "no": 1}])
    assert _acts(out[1]) == [("undo", "재단 완료 취소")]  # 작업 중 칸 = 카드에 완료 줄이 숨어 있다 → 지금 그대로
    assert _acts(out[4]) == [("", "재단 완료 · 박재단"), ("undo", "재단 완료 취소")]  # 완료 칸 = 완료 줄이 보인다


def test_source_contract_viewer_copies_card_text_only():
    viewer = (JS / "foms-production-parts-viewer.js").read_text(encoding="utf-8")
    fill = viewer.replace("\r\n", "\n").split("function fillActions(card) {", 1)[1].split("\n  }\n", 1)[0]
    assert "copy = el.cloneNode(true)" in fill and "createElement" not in fill and "textContent = '" not in fill.split("box.textContent = '';", 1)[1]
    assert "'완료" not in fill and "완료'" not in fill  # 글을 새로 짓지 않음(카드 칸 복사뿐)
    assert "card.getAttribute('data-state') === 'done'" in fill and "classList.contains('is-need')" in fill
    assert "style" not in fill and "fetch(" not in viewer
    assert len(viewer.splitlines()) <= 300
    scripts = (ROOT / "templates/production/partials/home_scripts.html").read_text(encoding="utf-8")
    assert "foms-production-parts-viewer.js') }}?v=20261127y" in scripts
    assert "foms-production-parts-crew.js') }}?v=20261128x" in scripts
