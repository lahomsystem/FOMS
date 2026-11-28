"""담당 바꾸기 — "누구에게 줄까요?" 창(설계서 2026-11-28 흐름 셋 §1-2 · §1-6 '화면').

서버가 그린 진짜 판 위에서 판 JS(viewer → claim → modal → cancel → crew → give → parts)를 Node 로 돌린다 — 서버 답(받을 사람 목록 · 쓰기
응답)은 진짜 API JSON 이다. 쓰기 · 목록 API 시험은 ``test_production_give_holder_1128.py``(500줄 래칫이라 나눴다). 실화면은 지휘가 본다.

되돌리면 실패: [담당 바꾸기 ›]가 바로 실행 · '나'를 미리 골라 둠 · 고르기 전 실행이 열림 · 남에게 준 뒤 알림이 "담당 바꿨어요" ·
여럿이 같이 작업 중인데 자리 고르기를 건너뜀 · 새 JS 를 안 싣거나 쓰기(parts) 뒤에 실음. 대조군: '나'를 고르면 지금 글 "담당 바꿨어요"
(``test_production_multi_holder_board.py`` 가 같은 판에서 본다). 이름은 모두 지어낸 값이다.
"""
from __future__ import annotations

import pathlib

from tests.domains.test_production_multi_holder_board import CUT_ADMIN, _node, _page, cohort  # noqa: F401
from tests.support.production_factory_seed import HOME_NONE
from tests.support.production_part_claim_seed import ONE, login, make_order, make_user, mark

ROOT = pathlib.Path(__file__).resolve().parents[2]
RECEIVERS = "/api/production/part-marks/receivers"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _api(client, who, body: dict) -> dict:
    login(client, who)
    resp = client.post(ONE, json=body)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def test_js_lead_picks_who_gets_the_drawing(client, cohort, tmp_path):  # noqa: F811
    order = make_order(2)
    kim, oh, choi, lead = (make_user("김재단", part="cut"), make_user("오재단", part="cut"), make_user("최재단", part="cut"),
                           make_user("박반장", lead=True))
    login(client, kim)
    assert mark(client, order, 0, "cut", "take", "none").status_code == 200  # 도면 1 = 김재단
    assert mark(client, order, 1, "cut", "take", "none").status_code == 200
    login(client, choi)
    assert mark(client, order, 1, "cut", "join", "need").status_code == 200  # 도면 2 = 김재단 · 최재단
    page = tmp_path / "lead.html"
    page.write_text(_page(client, lead, CUT_ADMIN), encoding="utf-8")
    k = order.keys
    ask = {"order_id": order.id, "part": "cut", "target_user_id": kim.id}
    one = client.get(RECEIVERS, query_string={**ask, "drawing_key": k[0]}).get_json()
    two = client.get(RECEIVERS, query_string={**ask, "drawing_key": k[1]}).get_json()
    base = {"order_id": order.id, "part": "cut", "action": "takeover", "seen": "need", "seen_me": "none", "seen_by": kim.id,
            "target_user_id": kim.id, "to_user_id": oh.id}
    give_one, give_two = {**base, "drawing_key": k[0]}, {**base, "drawing_key": k[1]}
    replies = [_api(client, lead, give_one), _api(client, lead, give_two)]
    res = _node(page, {"posts": replies, "gets": [one, two], "steps": [
        {"do": "click", "key": k[0], "act": "held"}, {"do": "choice", "text": "담당 바꾸기 ›"}, {"do": "run"},   # 0 1 2
        {"do": "who", "index": 1}, {"do": "run"}, {"do": "card", "key": k[0]},                                # 3 4 5
        {"do": "click", "key": k[1], "act": "held"}, {"do": "choice", "text": "담당 바꾸기 ›"}, {"do": "run"},   # 6 7 8
        {"do": "who", "index": 0}, {"do": "run"}, {"do": "who", "index": 1}, {"do": "run"}]})                 # 9 10 11 12
    out, calls = res["out"], res["calls"]
    held = out[0]["modal"]  # 반장 고르기 창 — [담당 바꾸기 ›]는 다음 창으로 가는 단추(바로 실행하지 않는다)
    assert [(c["text"], c["choice"], c["next"]) for c in held["choices"]] == [
        ("김재단 시작 취소", "remove", False), ("담당 바꾸기 ›", "give", True), ("같이 작업", "join", True), ("대신 완료", "check", False)]
    ask_one = out[1]["modal"]  # "누구에게 줄까요?" — 맨 앞 '나', 그다음 이름 순 · 아무도 미리 고르지 않음 · 실행 잠김
    assert out[1]["sent"] == 1 and (calls[0]["method"], calls[0]["body"]) == ("GET", None)
    assert f"order_id={order.id}" in calls[0]["url"] and f"target_user_id={kim.id}" in calls[0]["url"] and "part=cut" in calls[0]["url"]
    assert (ask_one["title"], ask_one["line"], ask_one["close"], ask_one["body"], ask_one["err"]) == ("누구에게 줄까요?", "담당 김재단", "닫기", "", "")
    assert ask_one["note"].startswith("김재단이 ") and ask_one["note"].endswith("부터 작업 중인 도면이에요.")
    assert [(c["text"], c["who"], c["pressed"]) for c in ask_one["choices"]] == [
        ("나 (박반장)", str(lead.id), "false"), ("오재단", str(oh.id), "false"), ("최재단", str(choi.id), "false")]
    assert ask_one["choices_cls"] == "pp-mchoices pp-mchoices--who pp-mchoices--give"
    assert ask_one["run"] == {"text": "담당 바꾸기", "hidden": False, "locked": True}
    assert out[2]["sent"] == 0  # 고르기 전 실행 = 안 나감
    picked = out[3]["modal"]
    assert picked["line"] == "담당 김재단 → 담당 오재단" and picked["run"]["locked"] is False
    assert [c["pressed"] for c in picked["choices"]] == ["false", "true", "false"]
    assert out[4]["sent"] == 1 and calls[1]["body"] == give_one and out[4]["status"] == "오재단에게 줬어요" and out[4]["modal"]["hidden"] is True
    assert out[5]["card"]["act"][0]["text"].startswith("오재단 작업")  # 그 도면 칸이 그 자리에서 바뀐다

    seat = out[7]["modal"]  # 여럿이 같이 작업 — 누구 자리인지 먼저(완료를 누른 사람은 못 고름), 실행 단추는 [다음]
    assert out[7]["sent"] == 0 and (seat["title"], seat["line"], seat["note"]) == (
        "누구와 담당을 바꿀까요?", "담당 김재단 · 최재단", "완료를 누른 사람은 바꿀 수 없어요.")
    assert seat["run"] == {"text": "다음", "hidden": False, "locked": True} and out[8]["sent"] == 0
    assert out[9]["modal"]["line"] == "담당 김재단 · 최재단" and out[9]["modal"]["run"]["locked"] is False  # 자리만 골랐다 — 바뀔 줄은 아직
    ask_two = out[10]["modal"]  # [다음] → "누구에게 줄까요?"(요청은 읽기 한 번 — 쓰기 0)
    assert out[10]["sent"] == 1 and calls[2]["method"] == "GET" and f"target_user_id={kim.id}" in calls[2]["url"]
    assert (ask_two["title"], ask_two["run"]["text"], ask_two["run"]["locked"]) == ("누구에게 줄까요?", "담당 바꾸기", True)
    assert [c["text"] for c in ask_two["choices"]] == ["나 (박반장)", "오재단"]  # 최재단은 이미 든 사람이라 빠진다
    assert out[11]["modal"]["line"] == "담당 김재단 · 최재단 → 담당 오재단 · 최재단"
    assert out[12]["sent"] == 1 and calls[3]["body"] == give_two and out[12]["status"] == "오재단에게 줬어요"


def test_js_give_window_when_the_list_fails_or_nobody_else_can_take(client, cohort, tmp_path):  # noqa: F811
    order = make_order(1)
    edge, lead = make_user("박엣지", part="edge"), make_user("박반장", lead=True)
    login(client, edge)
    assert mark(client, order, 0, "edge", "take", "none").status_code == 200
    page = tmp_path / "lead.html"
    page.write_text(_page(client, lead, HOME_NONE + "&tab=parts&part=edge"), encoding="utf-8")
    alone = client.get(RECEIVERS, query_string={"order_id": order.id, "drawing_key": order.keys[0], "part": "edge"}).get_json()
    assert [p["me"] for p in alone["data"]["people"]] == [True]
    refused = {"__status": 403, "body": {"success": False, "data": {"code": "OTHER_FACTORY"}, "error": "2공장에서 작업하는 도면이에요. [다시 받기]를 눌러 주세요."}}
    held = {"do": "click", "key": order.keys[0], "act": "held"}
    go = {"do": "choice", "text": "담당 바꾸기 ›"}
    res = _node(page, {"gets": [alone, refused], "steps": [held, go, {"do": "close"}, held, go, {"do": "close"}, held, go,
                                                         {"do": "timers"}, {"do": "modal"}]})
    out = res["out"]
    only_me = out[1]["modal"]  # 받을 사람이 '나'뿐 — 창은 그대로 뜨고 단추 하나 + 안내
    assert [c["text"] for c in only_me["choices"]] == ["나 (박반장)"] and only_me["body"] == "이 도면을 받을 수 있는 다른 사람이 없어요."
    assert only_me["run"]["locked"] is True
    failed = out[4]["modal"]  # 서버가 거절 — 서버 글 그대로 · 사람 단추 없음 · 실행 잠김
    assert (failed["err"], failed["choices"], failed["run"]["locked"]) == ("2공장에서 작업하는 도면이에요. [다시 받기]를 눌러 주세요.", [], True)
    late = out[9]["modal"]  # 답이 틀린 꼴이거나 3초를 넘김 — 정해 둔 글
    assert (late["err"], late["body"], late["choices"]) == ("받을 사람을 못 불러왔어요. 닫고 다시 눌러 주세요.", "", [])
    assert all(c["method"] == "GET" for c in res["calls"]) and len(res["calls"]) == 3  # 쓰기는 한 번도 안 나갔다


# --------------------------------------------------------------------------- #
# 화면 — 글 · 싣는 순서 · 핀
# --------------------------------------------------------------------------- #
def test_give_modal_words_and_wiring():
    give = _read("static/js/production/foms-production-parts-give.js")
    for words in ("'누구에게 줄까요?'", "'받을 사람을 불러오는 중…'", "'받을 사람을 못 불러왔어요. 닫고 다시 눌러 주세요.'",
                  "'이 도면을 받을 수 있는 다른 사람이 없어요.'", "'나 (' + p.name + ')'", "run: '담당 바꾸기'", "locked: true",
                  "/api/production/part-marks/receivers", "ASK_MS = 3000", "data-pp-give"):
        assert words in give, words
    assert "is-on" not in give and "aria-pressed', 'true'" not in give  # '나'를 미리 골라 두지 않는다
    assert "method: 'POST'" not in give  # 쓰기는 parts.js 의 send() 하나
    crew = _read("static/js/production/foms-production-parts-crew.js")
    assert "[['give', '담당 바꾸기 ›', 'taken', left[0].uid, true]]" in crew  # 한 명이어도 바로 실행하지 않는다
    assert "[['takeover', '담당 바꾸기', 'taken', left[0].uid]]" not in crew
    assert "run: MINE ? '담당 바꾸기' : '다음'" in crew and "next: MINE ? null : 'give'" in crew
    modal = _read("static/js/production/foms-production-parts-modal.js")
    assert "['give', '담당 바꾸기 ›', 'taken', null, true]" in modal
    parts = _read("static/js/production/foms-production-parts.js")
    for piece in ("action === 'give' ? give.plan(cards[0], seat)", "action === 'give' ? 'takeover' : action",
                  "if (p.to != null && body.action === 'takeover') { body.to_user_id = p.to; }", "data.gave.to.name + '에게 줬어요'", "'담당 바꾸기': '담당 바꿨어요'",
                  "who.hasAttribute('data-pp-give') ? 'to' : 'target'", "if (pending.next) { openModal(pending.next"):
        assert piece in parts, piece
    sheet = _read("static/js/production/foms-production-sheet-parts.js")
    assert "var to = item.to_name || who;" in sheet and "who + ': ' + (item.from_name ? item.from_name + ' → ' : '')" in sheet
    css = _read("static/css/contexts/production/parts.css")
    assert ".pp-mchoices.pp-mchoices--give { max-height: 236px; overflow-y: auto;" in css


def test_give_script_is_loaded_between_crew_and_parts_with_fresh_pins():
    scripts = _read("templates/production/partials/home_scripts.html")
    order = [scripts.index(f"js/production/foms-production-parts{name}.js') }}}}?v=") for name in ("-modal", "-cancel", "-crew", "-give", "")]
    assert order == sorted(order)  # modal → cancel → crew → give → parts(뒤 파일이 앞 파일의 window.* 를 쓴다)
    for name in ("-modal", "-crew", "-give", ""):
        assert f"js/production/foms-production-parts{name}.js') }}}}?v=20261128" in scripts, name
    assert scripts.count("foms-production-parts-give.js") == 1  # 판이 있는 화면(part_board)에서만 한 번
