"""조립할 것 없는 도면 — [조립 없음] 화면(설계서 2026-11-28 흐름 셋 §3-2 · §3-7 '실화면').

서버가 그린 판(템플릿)과 판 JS 를 같은 표시 줄 위에서 본다 — 조립 판이 재단 판과 같은 꼴(한 줄 [조립 없음][조립 시작], 반장 · 관리자는
그 아래 [조립 완료], 판 머리 "미정 도면 n장" [남은 n장 모두 조립 없음])이고 글만 조립 말인지. 서버 답은 진짜 API JSON 이다.
쓰기 · 판정 · DB 시험은 ``test_production_assemble_none_1128.py``. 1280 × 720 실화면(글자 배율 · 한 줄에 서는지)은 지휘가 본다.

되돌리면 실패: 조립 판에 [조립 없음]이 없기 · 서버가 그린 칸과 JS 가 다시 그린 칸이 다르기 · 조립 창 · 알림 글에 "기본"이 남기 ·
JS 에 "조립 없음" 글을 박기(글은 서버 설정 ``part_config.basic`` 하나). 대조군: 재단 판 글 · 엣지 판(단추 없음)은 그대로.
이름은 모두 지어낸 값이다.
"""
from __future__ import annotations

import json
import pathlib
import re
from html import unescape

from tests.domains.test_production_multi_holder_board import _act, _card, _node, _page, cohort  # noqa: F401
from tests.support.production_factory_seed import HOME_NONE
from tests.support.production_part_claim_seed import BULK, ONE, login, make_order, make_user, mark

ROOT = pathlib.Path(__file__).resolve().parents[2]
JS = ROOT / "static/js/production"


def _board(part: str) -> str:
    return f"{HOME_NONE}&tab=parts&part={part}"


def _config(html: str) -> dict:
    return json.loads(unescape(re.search(r'data-foms-parts-config="([^"]+)"', html).group(1)))


def _api(client, who, url: str, body: dict) -> dict:
    login(client, who)
    resp = client.post(url, json=body)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def test_assemble_board_is_drawn_like_the_cut_board(client, cohort):  # noqa: F811
    order = make_order(3)
    choi, lead = make_user("최조립", part="assemble"), make_user("박반장", lead=True)
    login(client, choi)
    assert mark(client, order, 2, "assemble", "basic", "none").status_code == 200
    mine = _page(client, choi)  # 조립 계정 자기 판(날짜 탭)
    row = ('<div class="pp-two"><button type="button" class="foms-prod-home__btn pp-pick-basic" data-pp-act="basic">조립 없음</button>'
           '<button type="button" class="foms-prod-home__btn foms-prod-home__btn--pri" data-pp-act="take">조립 시작</button></div>')
    assert _act(_card(mine, order.keys[0])).strip() == row + "</div>"  # 재단 [기본][재단 시작]과 같은 꼴 · 같은 색(진한 단추는 [조립 시작] 하나)
    done = _act(_card(mine, order.keys[2]))
    assert ">조립 없음 · 최조립</span>" in done and 'data-pp-act="undo">조립 없음 취소</button>' in done and "기본" not in done
    assert '<span class="pp-unseen" data-pp-unseen-text="2">미정 도면 <b>2</b>장</span>' in mine
    assert '<span>남은 <span data-pp-count="unseen">2</span>장 모두 조립 없음</span>' in mine
    assert _config(mine)["basic"] == {"word": "조립 없음", "short": "없음", "toward": "조립 없음으로", "ask": "조립할 것이 없는 도면인가요?",
                                      "undo": "조립 없음 취소", "undo_ask": "조립 없음을 취소할까요?", "unseen": "미정 도면"}
    board = _page(client, lead, _board("assemble"))  # 반장 — 그 아래 [조립 완료](재단 판과 같은 두 줄 꼴)
    assert '<div class="fph-parts pp-finrow" data-pp-pane=' in board
    assert _act(_card(board, order.keys[0])).strip() == (
        '<div class="pp-two"><button type="button" class="foms-prod-home__btn pp-pick-basic" data-pp-act="basic">조립 없음</button>'
        '<button type="button" class="foms-prod-home__btn" data-pp-act="take">조립 시작</button></div>'
        '<button type="button" class="fph-qr__done pp-act pp-fin is-pair" data-pp-act="check">조립 완료</button></div>')
    edge = _page(client, lead, _board("edge"))  # 대조군 — 엣지 · 검수 판에는 없다(사장님 "조립만")
    assert 'data-pp-act="basic"' not in edge and 'data-pp-act="bulk"' not in edge and "pp-finrow" not in edge and _config(edge)["basic"] is None
    assert '<i>조립</i> 없음' in _card(edge, order.keys[2]) and '<i>조립</i> 미정' in _card(edge, order.keys[0])  # 다른 파트 줄 낱말
    cut = _page(client, lead, _board("cut"))  # 대조군 — 재단 판 글은 한 글자도 안 바뀐다
    assert 'data-pp-act="basic">기본</button>' in cut and "안 본 도면 <b>3</b>장" in cut
    assert '<span>남은 <span data-pp-count="unseen">3</span>장 모두 기본</span>' in cut and _config(cut)["basic"]["word"] == "기본"


def test_js_assemble_none_windows_and_toasts(client, cohort, tmp_path):  # noqa: F811
    order = make_order(4)
    choi = make_user("최조립", part="assemble")
    page = tmp_path / "choi.html"
    page.write_text(_page(client, choi), encoding="utf-8")
    k = order.keys
    one = {"order_id": order.id, "drawing_key": k[0], "part": "assemble", "action": "basic", "seen": "none", "seen_me": "none"}
    undo = {"order_id": order.id, "drawing_key": k[0], "part": "assemble", "action": "undo", "seen": "basic", "seen_me": "none", "seen_cancel": False}
    bulk = {"part": "assemble", "seen": "none", "items": [{"order_id": order.id, "drawing_key": key} for key in k]}
    replies = [_api(client, choi, ONE, one), _api(client, choi, ONE, undo), _api(client, choi, BULK, bulk)]
    res = _node(page, {"posts": replies, "steps": [
        {"do": "parity"},                                                                              # 0
        {"do": "click", "key": k[0], "act": "basic"}, {"do": "run"}, {"do": "card", "key": k[0]},     # 1 2 3
        {"do": "click", "key": k[0], "act": "undo"}, {"do": "run"}, {"do": "card", "key": k[0]},      # 4 5 6
        {"do": "bulk"}, {"do": "run"}, {"do": "card", "key": k[3]}, {"do": "parity"}, {"do": "head"}]})  # 7 8 9 10 11
    out, calls = res["out"], res["calls"]
    assert out[0]["cards"] == 4 and out[0]["diffs"] == []  # 서버가 그린 칸 = JS 가 다시 그린 칸
    ask = out[1]["modal"]
    assert (ask["title"], ask["line"], ask["run"]["text"], ask["close"]) == ("조립할 것이 없는 도면인가요?", "미정 → 조립 없음 · 최조립", "조립 없음", "닫기")
    assert out[2]["sent"] == 1 and calls[0]["body"] == one and out[2]["status"] == "조립 없음으로 처리했어요"
    done = out[3]["card"]
    assert done["state"] == "basic" and done["act"][0]["text"] == "조립 없음 · 최조립" and done["act"][1]["kids"][1]["text"] == "조립 없음 취소"
    assert out[3]["counts"]["unseen"] == ["3"]  # 판 머리 일괄 단추 숫자도 같이 준다
    back = out[4]["modal"]
    assert (back["title"], back["line"], back["run"]["text"]) == ("조립 없음을 취소할까요?", "조립 없음 → 미정", "조립 없음 취소")
    assert out[5]["sent"] == 1 and calls[1]["body"] == undo and out[5]["status"] == "조립 없음 취소했어요"
    assert [kid["text"] for kid in out[6]["card"]["act"][0]["kids"]] == ["조립 없음", "조립 시작"]
    many = out[7]["modal"]
    assert (many["title"], many["line"], many["run"]["text"]) == ("4장을 조립 없음으로 할까요?", "미정 → 조립 없음 · 최조립", "4장 조립 없음으로")
    assert out[8]["sent"] == 1 and calls[2]["body"] == bulk and out[8]["status"] == "4장 조립 없음으로 했어요"
    assert out[9]["card"]["state"] == "basic" and out[10]["diffs"] == []
    assert out[11]["text"] == "미정 도면 없어요"  # 판 머리 글도 조립 말(재단 판 "안 본 도면 없어요")

    lead = tmp_path / "lead.html"  # 반장 — 남이 조립 없음으로 한 도면: 칸 · 취소 창 · 한 줄 더
    lead.write_text(_page(client, make_user("박반장", lead=True), _board("assemble")), encoding="utf-8")
    res = _node(lead, {"steps": [{"do": "parity"}, {"do": "click", "key": k[1], "act": "undo"}]})
    assert res["out"][0]["cards"] == 4 and res["out"][0]["diffs"] == []
    theirs = res["out"][1]["modal"]
    assert (theirs["title"], theirs["line"], theirs["note"]) == ("조립 없음을 취소할까요?", "조립 없음 → 미정", "최조립이 조립 없음으로 한 도면이에요")


def test_js_keeps_no_assemble_words_and_cut_words_come_from_the_same_setting():
    for name in ("parts", "parts-crew", "parts-modal", "parts-sync", "parts-claim", "parts-cancel", "parts-give", "drawing-request",
                 "sheet-parts"):
        text = (JS / f"foms-production-{name}.js").read_text(encoding="utf-8")
        code = "\n".join(re.sub(r"//.*$", "", line) for line in re.sub(r"/\*.*?\*/", "", text, flags=re.S).splitlines())
        assert "조립 없음" not in code and "'없음'" not in code, name  # 글은 서버 설정(part_config.basic) · 서버 기록 낱말(word)에서만
    modal = (JS / "foms-production-parts-modal.js").read_text(encoding="utf-8")
    for piece in ("title: BASIC.ask, line: '미정 → ' + BASIC.word + ' · ' + NAME, run: BASIC.word, tone: 'basic'",
                  "title: BASIC.undo_ask, line: BASIC.word + ' → 미정', run: BASIC.undo, tone: 'unbasic'",
                  "title: cards.length + '장을 ' + BASIC.toward + ' 할까요?'", "run: cards.length + '장 ' + BASIC.toward",
                  "' ' + BASIC.toward + ' 한 도면이에요'", "'지금: ' + BASIC.word"):
        assert piece in modal, piece
    crew = (JS / "foms-production-parts-crew.js").read_text(encoding="utf-8")
    assert "el('button', 'foms-prod-home__btn pp-pick-basic', BASIC.word, 'basic')" in crew and "st === 'basic' ? BASIC.undo" in crew
    parts = (JS / "foms-production-parts.js").read_text(encoding="utf-8")
    assert "var IS_CUT = !!cfg.basic;" in parts and "p.action === 'basic' ? BASIC.toward + ' 처리했어요'" in parts
    assert "item.word || KIND[item.kind] || item.kind" in (JS / "foms-production-sheet-parts.js").read_text(encoding="utf-8")
    assert "(cfg.basic || {}).word || '기본'" in (JS / "foms-production-parts-sync.js").read_text(encoding="utf-8")
    tpl = (ROOT / "templates/production/partials/home_parts.html").read_text(encoding="utf-8")
    assert "{% set is_cut = pb.basic is not none %}" in tpl and 'data-pp-act="basic">{{ pb.basic.word }}</button>' in tpl
    assert "모두 {{ pb.basic.word }}</span>" in tpl and "조립 없음</button>" not in tpl  # 템플릿도 글을 박지 않는다
    css = (ROOT / "static/css/contexts/production/parts.css").read_text(encoding="utf-8")
    assert ".pp-two > .pp-pick-basic { white-space: normal; word-break: keep-all; line-height: 1.05; }" in css
    scripts = (ROOT / "templates/production/partials/home_scripts.html").read_text(encoding="utf-8")
    for name in ("parts", "parts-modal", "parts-crew", "parts-sync", "drawing-request"):
        assert f"foms-production-{name}.js') }}}}?v=20261128h" in scripts, name


def test_history_line_words_for_none_and_rework():
    from foms.api.production.part_history import REWORK_WORD, history_word

    assert history_word({"action": "basic", "part": "assemble"}) == "조립 없음"
    assert history_word({"action": "undo", "part": "assemble", "from": "BASIC"}) == "조립 없음 취소"
    assert history_word({"action": "undo", "part": "assemble", "from": "DONE"}) is None  # 조립 완료 취소는 화면 낱말 그대로
    assert history_word({"action": "basic", "part": "cut"}) is None and history_word({"action": "undo", "part": "cut", "from": "BASIC"}) is None
    assert history_word({"action": "take", "part": "assemble"}) is None
    # 수정 제작이 고른 도면을 미정으로 돌린 줄(약속 9 — 이벤트는 수정 제작 쪽이 쓴다): "박반장 수정 제작 — 미정으로 11/28 10:20"
    assert history_word({"action": "rework", "part": "cut", "from": "DONE", "to": "NONE"}) == REWORK_WORD == "수정 제작 — 미정으로"
