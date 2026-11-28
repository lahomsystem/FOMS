"""반장 · 관리자 미정 카드 [<파트> 시작] 창의 사람 고르기(사장님 2026-11-28 "시작 창에 사람 고르기 붙임").

물음: 반장이 '미정' 카드에서 [재단 시작]을 누르면 반장 자신이 담당이 된다(창 글 "미정 → 작업 중 · 박반장") → 답 "시작 창에 사람 고르기
붙임"(고른 안의 설명 "반장 시작 창 안에 직원 이름 단추가 나와 바로 고릅니다. 아무도 안 고르면 지금처럼 반장이 담당입니다. 새 창은 없습니다.").
* 쓰기: 남을 고르면 요청 한 번 — ``takeover`` + ``seen:'none'`` + ``seen_by: null`` + ``to_user_id``(전이 표에 (takeover, none) 칸 하나를
  더했다 — 전에는 400). 막는 문(2공장 · 보류 · 도면 고치는 중 · 검수 앞 공정 · 손 체크 · 받는 사람)은 지금 [<파트> 시작]과 같은 차례이고,
  이벤트 · 감사 · 응답 재료(``gave`` · ``holders_before`` — 알람이 읽는다)는 지금 담당 바꾸기 꼴이다(``gave.from`` = null). 파트 계정이 몸을
  꾸며 보내면 403 ``GIVE_FORBIDDEN``.
* 화면: 같은 읽기(GET …/part-marks/receivers) · 같은 단추(data-pp-who · data-pp-give) · 줄 "미정 → 작업 중 · {고른 사람}" · 실행 단추 글은
  [재단 시작] 그대로 · 알림은 지금 담당 바꾸기 글("김재단에게 줬어요"). 아무도 안 고르거나 '나'를 고르면 지금 take 그대로, "이미 끝난 작업이면
  바로 완료"는 지금 check 그대로(받는 사람 칸 없이). 파트 계정 창에는 사람 단추 0 · 읽기 0.
되돌리면 실패: (takeover, none) 칸을 빼기 · 파트 계정에게 미정 주기를 열기 · 고른 사람을 몸에 안 싣기 · 아무도 안 골라도 takeover ·
바로 완료에 to_user_id 싣기 · 시작 창 실행을 잠그기 · 목록을 못 받으면 창에 빨간 글 · 파트 계정 창에서 목록 읽기. 이름은 모두 지어낸 값이다.
"""
from __future__ import annotations

import datetime
import re

from db import db_session
from foms.services.production import floor_alarm, mark_crew as mc
from foms.services.production.part_mark_decide import decide_mark
from foms.services.production.part_mark_rules import NEW_STALE_MESSAGE, MarkSnapshot, action_target
from models import SecurityLog, User
from tests.domains.test_production_multi_holder_board import CUT_ADMIN, _node, _page, _post, cohort  # noqa: F401
from tests.support.production_factory_seed import HOME_NONE
from tests.support.production_part_claim_seed import (HISTORY, HOME_MINE, Seed, code, events, login, make_order, make_user,
                                                       mark, patch_sd, row)

RECEIVERS = "/api/production/part-marks/receivers"
NOW = datetime.datetime(2026, 11, 28, 5, 20)
KIM, OH, LEAD = 11, 12, 99


def _give(client, order, j: int, to: int, part: str = "cut"):
    """화면이 보내는 몸 그대로 — 미정 카드를 고른 사람에게(seen_by = null: 본 담당 없음)."""
    return mark(client, order, j, part, "takeover", "none", seen_by=None, seen_me="none", to_user_id=to)


def _audit(oid: int) -> str:
    db_session.expire_all()
    return (db_session.query(SecurityLog).filter_by(action="PRODUCTION_PART_MARKED", target_id=oid)
            .order_by(SecurityLog.id.desc()).first().message)


def _crew(oid: int, key: str, part: str = "cut") -> list[tuple[str, bool]]:
    return [(m["name"], m["done_at"] is not None) for m in (row(oid, key, part).holders or [])]


# --------------------------------------------------------------------------- #
# 순수 판정
# --------------------------------------------------------------------------- #
def test_decide_gives_a_none_drawing_and_keeps_take_rules():
    assert action_target("takeover", "none") == "NEED" and action_target("take", "none") == "NEED"
    base = dict(action="takeover", seen="none", actor_id=LEAD, admin=True, actor_name="박반장", now=NOW, label="재단")
    given = decide_mark(MarkSnapshot(), **base, to_uid=KIM, to_name="김재단")
    assert (given.kind, given.target, given.action, given.to_uid, given.to_name, given.target_uid, given.target_name) == (
        "apply", "NEED", "takeover", KIM, "김재단", None, "")
    assert [(m["uid"], m["name"], mc.is_done(m)) for m in given.crew] == [(KIM, "김재단", False)]
    assert given.crew[0]["at"] == mc.to_iso(NOW) and given.override is False
    after = MarkSnapshot(state="NEED", picked_by_user_id=KIM, picked_by_name="김재단", updated_by_user_id=LEAD, crew=given.crew)
    assert decide_mark(after, **base, to_uid=KIM, to_name="김재단").kind == "same"  # 연결이 얼어 두 번 — 바뀐 것 없음
    other = MarkSnapshot(state="NEED", picked_by_user_id=OH, picked_by_name="오재단", updated_by_user_id=OH,
                         crew=(mc.member(OH, "오재단", "2026-11-28T05:00:00+00:00"),))
    stale = decide_mark(other, **base, to_uid=KIM, to_name="김재단")  # 그사이 오재단이 시작 — 낡은 화면
    assert (stale.kind, stale.message) == ("conflict", NEW_STALE_MESSAGE)


# --------------------------------------------------------------------------- #
# 쓰기 API
# --------------------------------------------------------------------------- #
def test_lead_gives_a_none_drawing_in_one_request(client, cohort):  # noqa: F811
    order = make_order(2, run=False)  # 제작 대기 — 첫 도면이면 제작 시작도 같이(지금 [재단 시작]과 같다)
    kim, oh, lead = make_user("김재단", part="cut"), make_user("오재단", part="cut"), make_user("박반장", lead=True)
    login(client, lead)
    resp = _give(client, order, 0, kim.id)
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert (data["changed"], data["run_started"], data["holders_before"]) == (True, True, [])
    assert data["gave"] == {"order_id": order.id, "drawing_key": order.keys[0], "part": "cut",
                            "by": {"user_id": lead.id, "name": "박반장"}, "from": None, "to": {"user_id": kim.id, "name": "김재단"},
                            "self": False}
    assert data["mark"]["state"] == "need" and [(h["user_id"], h["name"], h["done"]) for h in data["mark"]["holders"]] == [
        (kim.id, "김재단", False)]
    saved = row(order.id, order.keys[0], "cut")
    assert (saved.state, saved.picked_by_user_id, saved.picked_by_name, saved.handed_from_name, saved.updated_by_user_id) == (
        "NEED", kim.id, "김재단", None, lead.id)  # 넘겨준 사람이 없으니 '바뀜' 글도 없다
    payload = events(order.id, "PRODUCTION_PART_MARKED")[-1].payload
    picked = ("action", "from", "to", "by_name", "from_user_id", "from_name", "to_user_id", "to_name", "override",
              "holders_before", "holders_after")
    assert {k: payload.get(k) for k in picked} == {
        "action": "takeover", "from": "NONE", "to": "NEED", "by_name": "박반장", "from_user_id": None, "from_name": None,
        "to_user_id": kim.id, "to_name": "김재단", "override": False, "holders_before": [],
        "holders_after": [{"uid": kim.id, "name": "김재단", "done": False}]}
    assert _audit(order.id).endswith("재단 담당 바꿈 (담당 없음 → 김재단, 박반장) · 제작 시작")  # 지금 담당 바꾸기 감사 글 꼴 + 첫 도면 꼬리
    item = [i for i in client.get(f"{HISTORY}?order_id={order.id}").get_json()["data"]["items"] if i["kind"] == "takeover"][-1]
    assert (item["by_name"], item["from_name"], item["to_name"]) == ("박반장", None, "김재단")
    # 알람 재료 — 받은 사람에게 '새 일'(given) 하나, 자리를 내준 사람이 없으니 taken 은 없다(지금 담당 바꾸기와 같은 함수)
    assert floor_alarm.mark_events(lead.id, "takeover", data) == [("given", {"to": [kim.id]})]
    again = _give(client, order, 0, kim.id)
    assert again.status_code == 200 and again.get_json()["data"]["changed"] is False
    assert len(events(order.id, "PRODUCTION_PART_MARKED")) == 1
    page = _page(client, kim, HOME_MINE)  # 김재단 '내 공정'에 그 카드가 있다
    screen = page[page.index("data-flow-screen"):page.index('class="pp-overlays"')]
    assert f'data-key="{order.keys[0]}"' in screen and f'data-key="{order.keys[1]}"' not in screen


def test_admin_gives_too_and_order_card_works(client, cohort):  # noqa: F811
    order = make_order(1)
    kim, admin = make_user("김재단", part="cut"), make_user("관리", team="CS", role="ADMIN")
    login(client, admin)
    data = _give(client, order, 0, kim.id).get_json()["data"]
    assert data["gave"]["to"] == {"user_id": kim.id, "name": "김재단"} and data["gave"]["self"] is False
    assert _audit(order.id).endswith("재단 담당 바꿈 (담당 없음 → 김재단, 관리)")
    plain = Seed(make_order(0).id, ("@order",))  # '도면 없음' 카드도 같은 길
    lead, edge = make_user("박반장", lead=True), make_user("박엣지", part="edge")
    login(client, lead)
    resp = _give(client, plain, 0, edge.id, part="edge")
    assert resp.status_code == 200, resp.get_json()
    assert _crew(plain.id, "@order", "edge") == [("박엣지", False)]


def test_part_account_cannot_give_a_none_drawing(client):
    order = make_order(1)
    kim, choi = make_user("김재단", part="cut"), make_user("최재단", part="cut")
    login(client, choi)
    for extra in ({"to_user_id": kim.id}, {"to_user_id": choi.id}, {}):  # 남에게 · 나에게 · 받는 사람 없이 — 모두 반장 · 관리자만
        refused = mark(client, order, 0, "cut", "takeover", "none", seen_by=None, seen_me="none", **extra)
        assert (refused.status_code, code(refused), refused.get_json()["error"]) == (
            403, "GIVE_FORBIDDEN", "다른 사람에게 주는 것은 반장이나 관리자만 할 수 있어요."), extra
    assert row(order.id, order.keys[0], "cut") is None and events(order.id, "PRODUCTION_PART_MARKED") == []
    assert mark(client, order, 0, "cut", "take", "none").status_code == 200  # 대조군 — 내 [재단 시작]은 지금 그대로


def test_give_takes_the_same_gates_as_start(client, monkeypatch):
    """지금 [<파트> 시작](반장 자신)과 같은 문 · 같은 코드 — 보류 · 손 체크 · 검수 앞 공정 · 2공장 · 도면 고치는 중."""
    kim, insp, lead = make_user("김재단", part="cut"), make_user("한검수", part="inspect"), make_user("박반장", lead=True)

    def both(order, j=0, part="cut", to=None):
        login(client, lead)
        start = mark(client, order, j, part, "take", "none")
        give = _give(client, order, j, to or (kim.id if part == "cut" else insp.id), part=part)
        return code(start), code(give)

    held = make_order(1)
    patch_sd(held.id, hold={"active": True, "reason": "자재 기다림"})
    assert both(held) == ("HOLD_ACTIVE", "HOLD_ACTIVE")
    assert both(make_order(1, steps_done=("cut",))) == ("STEP_SET_BY_HAND", "STEP_SET_BY_HAND")
    assert both(make_order(1), part="inspect") == ("INSPECT_NOT_READY", "INSPECT_NOT_READY")
    far = make_order(1)
    db_session.query(User).filter_by(id=lead.id).update({"production_factory": 2})
    db_session.commit()
    assert both(far) == ("OTHER_FACTORY", "OTHER_FACTORY")
    db_session.query(User).filter_by(id=lead.id).update({"production_factory": None})
    db_session.commit()
    monkeypatch.setattr("foms.services.notifications.push_sender.enqueue_push_for_notification", lambda *a, **k: None)
    monkeypatch.setattr("foms.api.drawing.erp_orders_revision.emit_erp_notification_to_users", lambda *a, **k: None)
    fixing = make_order(2, extra={"drawing_status": "CONFIRMED"})
    login(client, make_user("가짜관리", team="CS", role="ADMIN"))
    asked = client.post(f"/api/orders/{fixing.id}/request-revision", json={"note": "측판 길이", "target_drawing_keys": [fixing.keys[0]]})
    assert asked.status_code == 200, asked.get_json()
    assert both(fixing) == ("DRAWING_REVISING", "DRAWING_REVISING")
    other_part = make_order(1)
    login(client, lead)
    wrong = _give(client, other_part, 0, make_user("박엣지", part="edge").id)  # 받는 사람 문(지금 담당 바꾸기와 같은 판정)
    assert (wrong.status_code, code(wrong)) == (409, "RECEIVER_NOT_ALLOWED")
    assert row(other_part.id, other_part.keys[0], "cut") is None


# --------------------------------------------------------------------------- #
# 화면(Node — 서버가 그린 진짜 판 · 진짜 API 답)
# --------------------------------------------------------------------------- #
def _lists(client, who, order, part: str = "cut") -> list[dict]:
    login(client, who)
    return [client.get(RECEIVERS, query_string={"order_id": order.id, "drawing_key": key, "part": part}).get_json()
            for key in order.keys]


def _body(order, j: int, action: str, part: str = "cut", **extra) -> dict:
    return {"order_id": order.id, "drawing_key": order.keys[j], "part": part, "action": action, "seen": "none", "seen_me": "none", **extra}


def test_js_lead_start_window_picks_a_person(client, cohort, tmp_path):  # noqa: F811
    order = make_order(4)
    kim, oh, lead = make_user("김재단", part="cut"), make_user("오재단", part="cut"), make_user("박반장", lead=True)
    make_user("박엣지", part="edge")  # 다른 파트 — 목록에 없다
    page = tmp_path / "lead.html"
    page.write_text(_page(client, lead, CUT_ADMIN), encoding="utf-8")
    lists = _lists(client, lead, order)
    give = _body(order, 0, "takeover", seen_by=None, to_user_id=kim.id)
    plain, me, direct = _body(order, 1, "take"), _body(order, 2, "take"), _body(order, 3, "check")
    replies = [_post(client, lead, b) for b in (give, plain, me, direct)]
    res = _node(page, {"posts": replies, "gets": lists, "steps": [
        {"do": "click", "key": order.keys[0], "act": "take"}, {"do": "wait"}, {"do": "who", "index": 1},     # 0 1 2
        {"do": "run"}, {"do": "card", "key": order.keys[0]},                                               # 3 4
        {"do": "click", "key": order.keys[1], "act": "take"}, {"do": "wait"}, {"do": "run"},               # 5 6 7 아무도 안 고름
        {"do": "click", "key": order.keys[2], "act": "take"}, {"do": "wait"}, {"do": "who", "index": 0},     # 8 9 10 '나'
        {"do": "run"},                                                                                     # 11
        {"do": "click", "key": order.keys[3], "act": "take"}, {"do": "wait"}, {"do": "who", "index": 2},     # 12 13 14
        {"do": "press", "sel": "[data-pp-direct]"}]})                                                      # 15 바로 완료
    out, calls = res["out"], res["calls"]
    opened, loaded, picked = out[0]["modal"], out[1]["modal"], out[2]["modal"]
    assert (opened["title"], opened["line"], opened["run"], opened["choices"]) == (
        "재단 시작할까요?", "미정 → 작업 중 · 박반장", {"text": "재단 시작", "hidden": False, "locked": False}, [])  # 지금 창 그대로 · 실행 열림
    gets = [c for c in calls if c["method"] == "GET"]
    assert len(gets) == 4 and all(c["url"].startswith(RECEIVERS + "?") and "part=cut" in c["url"] for c in gets)
    assert f"drawing_key={order.keys[0]}".replace("/", "%2F") in gets[0]["url"] and "target_user_id" not in gets[0]["url"]
    assert [(c["text"], c["who"], c["pressed"]) for c in loaded["choices"]] == [
        ("나 (박반장)", str(lead.id), "false"), ("김재단", str(kim.id), "false"), ("오재단", str(oh.id), "false")]  # 담당 바꾸기와 같은 목록
    assert loaded["choices_cls"] == "pp-mchoices pp-mchoices--who pp-mchoices--give" and all(
        c["cls"] == "foms-prod-change-modal__btn pp-mbtn pp-mwho" for c in loaded["choices"])  # 같은 꼴
    assert (loaded["line"], loaded["run"]["locked"], loaded["body"], loaded["err"]) == ("미정 → 작업 중 · 박반장", False, "", "")
    assert picked["line"] == "미정 → 작업 중 · 김재단" and picked["run"]["text"] == "재단 시작"  # 실행 단추 글은 그대로
    assert [c["pressed"] for c in picked["choices"]] == ["false", "true", "false"]
    posts = [c["body"] for c in calls if c["method"] == "POST"]
    assert posts == [give, plain, me, direct]  # 요청은 누름마다 한 번 — 바로 완료는 지금 check 그대로(받는 사람 칸 없음)
    assert out[3]["sent"] == 1 and out[3]["status"] == "김재단에게 줬어요" and out[3]["modal"]["hidden"] is True
    card = out[4]["card"]
    assert card["state"] == "need" and card["act"][0]["text"].startswith("김재단 작업 중")
    assert [a["act"] for a in card["act"]] == ["held", "check"] and card["act"][1]["text"] == "재단 완료"
    assert out[7]["status"] == "재단 시작했어요" and out[11]["status"] == "재단 시작했어요"  # 대조군 · '나' = 지금 동작
    assert out[10]["modal"]["line"] == "미정 → 작업 중 · 박반장"
    assert out[14]["modal"]["line"] == "미정 → 작업 중 · 오재단" and out[15]["status"] == "재단 완료했어요"


def test_js_part_account_window_has_no_people_and_failed_list_keeps_todays_window(client, cohort, tmp_path):  # noqa: F811
    order = make_order(2)
    kim, lead = make_user("김재단", part="cut"), make_user("박반장", lead=True)
    make_user("오재단", part="cut")
    page = tmp_path / "kim.html"
    page.write_text(_page(client, kim, HOME_NONE), encoding="utf-8")
    res = _node(page, {"steps": [{"do": "click", "key": order.keys[0], "act": "take"}, {"do": "wait"}, {"do": "direct"}]})
    mine = res["out"][1]["modal"]
    assert res["calls"] == [] and mine["choices"] == [] and mine["line"] == "미정 → 작업 중 · 김재단"  # 사람 단추 0 · 읽기 0
    assert res["out"][2]["direct"] is None
    lead_page = tmp_path / "lead.html"
    lead_page.write_text(_page(client, lead, CUT_ADMIN), encoding="utf-8")
    refused = {"__status": 403, "body": {"success": False, "data": {"code": "OTHER_FACTORY"}, "error": "2공장에서 작업하는 도면이에요."}}
    took = _post(client, lead, _body(order, 0, "take"))
    res = _node(lead_page, {"gets": [refused], "posts": [took], "steps": [
        {"do": "click", "key": order.keys[0], "act": "take"}, {"do": "wait"}, {"do": "timers"}, {"do": "modal"}, {"do": "run"}]})
    failed = res["out"][3]["modal"]  # 목록을 못 받음 · 3초 넘김 — 지금 창 그대로(빨간 글 없음 · 실행 열림)
    assert (failed["err"], failed["choices"], failed["body"], failed["run"]["locked"]) == ("", [], "", False)
    assert [c["body"] for c in res["calls"] if c["method"] == "POST"] == [_body(order, 0, "take")]
    assert res["out"][4]["status"] == "재단 시작했어요"


def test_js_crew_tab_edge_none_card_lists_edge_people(client, cohort, tmp_path):  # noqa: F811
    """'작업 중' 탭(카드 data-part) 엣지 미정 카드 — 그 카드 파트(엣지) 사람 목록 · 요청 part edge."""
    order = make_order(1)
    edge, lead = make_user("박엣지", part="edge"), make_user("박반장", lead=True)
    make_user("김재단", part="cut")
    url = "/erp/production/home?tab=crew&part=edge"
    html = _page(client, lead, url)
    none = html[html.index('class="fpf-none'):]
    assert re.search(rf'data-key="{re.escape(order.keys[0])}"[^>]*data-part="edge"', none)
    page = tmp_path / "crew.html"
    page.write_text(html, encoding="utf-8")
    lists = _lists(client, lead, order, part="edge")
    give = _body(order, 0, "takeover", part="edge", seen_by=None, to_user_id=edge.id)
    res = _node(page, {"gets": lists, "posts": [_post(client, lead, give)], "steps": [
        {"do": "click", "key": order.keys[0], "act": "take"}, {"do": "wait"}, {"do": "who", "index": 1}, {"do": "run"}]})
    out, calls = res["out"], res["calls"]
    assert out[0]["modal"]["title"] == "엣지 시작할까요?" and "part=edge" in calls[0]["url"]
    assert [c["text"] for c in out[1]["modal"]["choices"]] == ["나 (박반장)", "박엣지"]  # 재단 사람(김재단)은 없다
    assert out[2]["modal"]["line"] == "미정 → 작업 중 · 박엣지"
    assert [c["body"] for c in calls if c["method"] == "POST"] == [give] and out[3]["status"] == "박엣지에게 줬어요"


def test_source_wiring_and_limits():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    give = (root / "static/js/production/foms-production-parts-give.js").read_text(encoding="utf-8")
    parts = (root / "static/js/production/foms-production-parts.js").read_text(encoding="utf-8")
    assert "var START_LINE = '미정 → 작업 중 · ';" in give and "start ? START_LINE + p.name : p.line || ''" in give
    assert "if (start) { return; }" in give and "if (!start) { M.setText('[data-pp-modal-body]', WAIT); }" in give
    assert "give.load && (action === 'give' || p.direct)" in parts and "give.load(pending, cards[0], !!p.direct)" in parts
    assert "action: hand ? 'takeover' : p.action" in parts and "if (body.seen === 'need' || hand)" in parts
    modal = (root / "static/js/production/foms-production-parts-modal.js").read_text(encoding="utf-8")
    assert "line: '미정 → 작업 중 · ' + NAME, run: LABEL + ' 시작'" in modal  # 시작 창 글 · 실행 단추 글은 그대로
    for f in ("foms-production-parts.js", "foms-production-parts-give.js"):
        assert len((root / "static/js/production" / f).read_text(encoding="utf-8").splitlines()) < 300, f
    scripts = (root / "templates/production/partials/home_scripts.html").read_text(encoding="utf-8")
    for name in ("parts-give", "parts"):
        assert f"foms-production-{name}.js') }}}}?v=20261128r\" defer" in scripts, name
