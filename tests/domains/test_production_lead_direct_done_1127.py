"""반장 · 관리자가 '미정' 도면을 한 장씩 바로 완료(사장님 2026-11-27 "두 번으로 줄이기 (Recommended)" · "각 도면을 체크하면서 완료하는 게 맞다").

반장(자기 공장) · 관리자 화면의 미정 · 안 본 도면 칸에 [작업 시작] 옆 [<파트> 완료](``data-pp-act="check"`` — 남이 시작한 도면의 대신 완료 ·
PC [완료 처리]와 같은 요청)가 보인다. 재단은 [기본][작업 시작] 아래 둘째 줄, 그 밖 파트는 [작업 시작][엣지 완료] 한 줄. 확인 창 한 번 →
그 도면 그 파트 완료, 기록은 누른 반장 이름("재단 완료 · 박반장"). 여러 장 한 번에 완료하는 새 단추는 없다(한 장씩만).

* 서버(새 규칙 없음 — 지금 ``check`` 길 그대로): 빈 줄 = 누른 사람 시작 + 완료 · 막는 문(남의 공장 403 · 보류 · 도면 수정 중 · 손 체크 칸 ·
  생산 단계 아님 409 · 검수는 앞 공정 완료 뒤) · 파트 계정은 403 ``PART_FORBIDDEN`` · 제작 대기 주문의 첫 도면이면 [작업 시작]처럼 제작
  시작 · 감사 글 "재단 안 봄 → 재단 완료"(대신 꼬리 없음).
* [완료 취소]는 한 번에 미정(사장님 2026-11-27 "한 번에 미정으로" — 자세한 시험은 ``test_production_direct_done_undo_1127.py``).
* 화면: 템플릿 ↔ JS(crew.render) 같은 규칙 · 창 글("미정 → 재단 완료 · 박반장" / "미정 → 엣지 완료 · 박반장" — 11-27 네 파트 같은 꼴, 첫 도면 안내 줄) · 완료 뒤 칸
  · 숫자 · 409 뒤 다시 그리기 · 받아 오기 표시로 다시 그리기. 파트 계정 · 막힌 칸 · 보기만은 지금 그대로(음성 대조).

되돌리면 실패: 반장 미정 칸에 [완료]가 없음 · 파트 계정 화면에 [완료]가 생김 · 막힌 칸에 [완료] · 창 앞말 "작업 중 →" · 감사에 "(대신
처리)" · 첫 도면 제작 시작 빠짐 · JS 다시 그리기가 단추를 잃음. 이름은 모두 지어낸 값이다.
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest
from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from models import Order, User
from tests.domains.test_production_multi_holder_api import _audits, _names
from tests.domains.test_production_multi_holder_board import CUT_ADMIN, _act, _card, _node, _page, _post, cohort  # noqa: F401
from tests.support.production_factory_seed import HOME_NONE
from tests.support.production_part_claim_seed import (
    HISTORY,
    code,
    current_runs,
    events,
    finish,
    fresh,
    login,
    make_order,
    make_user,
    mark,
    patch_sd,
    row,
    step,
)

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / "static/js/production"
EDGE_ADMIN = HOME_NONE + "&tab=parts&part=edge"
INSPECT_ADMIN = HOME_NONE + "&tab=parts&part=inspect"
CUT_LEAD_NONE = ('<div class="pp-two"><button type="button" class="foms-prod-home__btn pp-pick-basic" data-pp-act="basic">기본</button>'
                 '<button type="button" class="foms-prod-home__btn" data-pp-act="take">재단 시작</button></div>'
                 '<button type="button" class="fph-qr__done pp-act pp-fin is-pair" data-pp-act="check">재단 완료</button>')
EDGE_LEAD_NONE = ('<div class="pp-two"><button type="button" class="foms-prod-home__btn pp-act" data-pp-act="take">엣지 시작</button>'
                  '<button type="button" class="fph-qr__done pp-act pp-fin is-pair" data-pp-act="check">엣지 완료</button></div>')
CUT_PART_NONE = ('<div class="pp-two"><button type="button" class="foms-prod-home__btn pp-pick-basic" data-pp-act="basic">기본</button>'
                 '<button type="button" class="foms-prod-home__btn foms-prod-home__btn--pri" data-pp-act="take">재단 시작</button></div>')


def _box(html: str, key: str) -> str:
    """카드 단추 칸 안쪽(까닭 말풍선 뒤 ~ 단추 칸 닫는 꼬리 앞)."""
    inner = _act(_card(html, key)).strip()
    assert inner.endswith("</div>")
    return inner[:-len("</div>")].strip()


def _lead():
    return make_user("박반장", lead=True)


def _admin():
    return make_user("관리", team="CS", role="ADMIN")


def _check(client, order, j: int, part: str = "cut"):
    """화면이 보내는 몸 그대로 — 미정 칸 [<파트> 완료](action check · 본 상태 none · 본 내 몫 none)."""
    return mark(client, order, j, part, "check", "none", seen_me="none")


def _set_sd(oid: int, **top) -> None:
    order = db_session.get(Order, oid)
    sd = copy.deepcopy(order.structured_data)
    sd.update(top)
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()


# --------------------------------------------------------------------------- #
# 서버 — 지금 check 길이 빈 줄을 받는다(새 규칙 없음)
# --------------------------------------------------------------------------- #
def test_lead_finishes_unseen_cut_drawing_in_one_press_recorded_as_lead(client):
    order = make_order(3)
    login(client, _lead())
    res = _check(client, order, 0)
    assert res.status_code == 200, res.get_json()
    data = res.get_json()["data"]
    assert (data["changed"], data["proxied"], data["joined_late"], data["notice"]) == (True, False, False, None)
    assert data["mark"]["state"] == "done" and data["mark"]["crew"]["done"] == "박반장"  # 화면 글 "재단 완료 · 박반장"
    saved = row(order.id, order.keys[0], "cut")
    assert (saved.state, saved.picked_by_name, saved.done_by_name) == ("DONE", "박반장", "박반장")
    assert _names(order.id, order.keys[0]) == [("박반장", True)]
    audit = _audits(order.id)[-1]
    assert "재단 안 봄 → 재단 완료" in audit and "(대신 처리)" not in audit  # 지금 낱말 함수 그대로 · 남의 몫이 아니라 대신 꼬리 없음
    payload = events(order.id, "PRODUCTION_PART_MARKED")[-1].payload
    assert (payload["action"], payload["from"], payload["to"], payload["override"], payload["by_name"]) == (
        "check", "NONE", "DONE", False, "박반장")
    assert "holder_name" not in payload
    items = client.get(HISTORY, query_string={"order_id": order.id, "part": "cut"}).get_json()["data"]["items"]
    assert [(i["kind"], i["by_name"]) for i in items] == [("check", "박반장")]
    again = _check(client, order, 0)  # 연결이 얼어 두 번 = 멱등
    assert again.status_code == 200 and again.get_json()["data"]["changed"] is False


def test_admin_finishes_unseen_edge_drawing_and_one_drawing_turns_the_step_on(client):
    order = make_order(1)
    login(client, _admin())
    data = _check(client, order, 0, "edge").get_json()["data"]
    assert data["mark"]["state"] == "done" and _names(order.id, order.keys[0], "edge") == [("관리", True)]
    audit = _audits(order.id)[-1]
    assert "엣지 안 고름 → 엣지 완료" in audit and "덮어쓰기" not in audit
    assert data["order_step"]["done"] is True and step(order.id, "edge")["by_name"] == "관리"  # 도면 한 장 = 공정 칸도 켜짐(지금 규칙)


def test_part_account_and_view_only_staff_are_refused_as_today(client):
    order = make_order(2)
    login(client, make_user("이시영", part="cut"))
    res = _check(client, order, 0)
    assert (res.status_code, code(res), res.get_json()["error"]) == (403, "PART_FORBIDDEN", "[완료 처리]는 반장이나 관리자만 할 수 있어요.")
    login(client, make_user("보기만"))  # 파트도 반장도 아닌 생산팀
    assert _check(client, order, 1).status_code == 403
    assert row(order.id, order.keys[0], "cut") is None and row(order.id, order.keys[1], "cut") is None
    login(client, make_user("김재단", part="cut"))  # 파트 계정은 지금처럼 [작업 시작] 뒤 [완료]
    assert mark(client, order, 0, "cut", "take", "none").status_code == 200
    assert mark(client, order, 0, "cut", "done", "need").get_json()["data"]["mark"]["state"] == "done"


def test_same_gates_as_proxy_finish(client):
    """남이 시작한 도면의 대신 완료와 같은 문 — 남의 공장 · 보류 · 도면 수정 중 · 손 체크 칸 · 생산 단계 아님 · 검수 순서."""
    lead = _lead()
    far = make_order(1, extra={"drawing_factory": {"sheets": {}}})
    other = make_user("원반장", lead=True)
    db_session.query(User).filter_by(id=other.id).update({"production_factory": 2})
    db_session.commit()
    login(client, other)
    assert (lambda r: (r.status_code, code(r)))(_check(client, far, 0)) == (403, "OTHER_FACTORY")

    login(client, lead)
    held = make_order(1)
    patch_sd(held.id, hold={"active": True, "reason": "자재 기다림"})
    assert (lambda r: (r.status_code, code(r)))(_check(client, held, 0)) == (409, "HOLD_ACTIVE")
    revising = make_order(1)
    _set_sd(revising.id, drawing_status="RETURNED")
    res = _check(client, revising, 0)
    assert (res.status_code, code(res)) == (409, "DRAWING_REVISING")
    assert res.get_json()["error"] == "도면 수정 중이라 지금은 못 눌러요. 새 도면이 오면 다시 돼요."
    hand = make_order(1, steps_done=("edge",))
    assert (lambda r: (r.status_code, code(r)))(_check(client, hand, 0, "edge")) == (409, "STEP_SET_BY_HAND")
    gone = make_order(1)
    _set_sd(gone.id, workflow={"stage": "CONSTRUCTION"})
    db_session.query(Order).filter_by(id=gone.id).update({"erp_stage_code": "CONSTRUCTION"})
    db_session.commit()
    assert (lambda r: (r.status_code, code(r)))(_check(client, gone, 0)) == (409, "NOT_IN_PRODUCTION")
    early = make_order(1)
    res = _check(client, early, 0, "inspect")
    assert (res.status_code, code(res)) == (409, "INSPECT_NOT_READY")
    for o, part in ((far, "cut"), (held, "cut"), (revising, "cut"), (hand, "edge"), (gone, "cut"), (early, "inspect")):
        assert row(o.id, o.keys[0], part) is None, (o.id, part)  # 막히면 아무것도 안 씀


def test_last_inspect_drawing_finished_directly_asks_to_complete(client):
    order = make_order(1)
    login(client, _admin())
    for part in ("cut", "edge", "assemble"):
        finish(client, order, 0, part)
    login(client, _lead())
    data = _check(client, order, 0, "inspect").get_json()["data"]
    assert data["mark"]["state"] == "done" and data["order_ready"] == {"order_id": order.id}  # "제작 완료할까요?" 이어서 물음(지금 규칙)


def test_first_drawing_of_waiting_order_starts_production_like_take(client):
    login(client, _lead())
    waiting, control = make_order(2, run=False), make_order(1, run=False)
    data = _check(client, waiting, 0).get_json()["data"]
    assert data["run_started"] is True and current_runs(waiting.id) == 1
    assert " · 제작 시작" in _audits(waiting.id)[-1]
    took = mark(client, control, 0, "cut", "take", "none").get_json()["data"]  # 대조 — [작업 시작]도 같은 동작
    assert took["run_started"] is True and current_runs(control.id) == 1 and " · 제작 시작" in _audits(control.id)[-1]
    second = _check(client, waiting, 1).get_json()["data"]
    assert second["run_started"] is False and current_runs(waiting.id) == 1  # 둘째 장은 제작 시작 없음


def test_undo_of_direct_done_goes_back_to_unseen_in_one_press(client):
    """[재단 완료 취소] = 한 번에 안 봄(미정) — 사장님 2026-11-27 "한 번에 미정으로"(자세한 시험은 test_production_direct_done_undo_1127)."""
    order = make_order(2)
    login(client, _lead())
    _check(client, order, 0)
    undo = mark(client, order, 0, "cut", "undo", "done", seen_me="done")  # 화면이 보내는 몸(대상 없음)
    assert undo.status_code == 200, undo.get_json()
    assert undo.get_json()["data"]["mark"]["state"] == "none" and _names(order.id, order.keys[0]) == []
    assert "재단 완료 → 안 봄" in _audits(order.id)[-1]
    assert row(order.id, order.keys[0], "cut").state == "NONE"


def test_started_meanwhile_becomes_proxy_finish_not_join(client):
    """미정으로 보고 눌렀는데 그사이 파트 계정이 시작 = 지금 판결 2 그대로 대신 완료(반장은 목록에 안 들어감)."""
    order = make_order(1)
    login(client, make_user("박엣지", part="edge"))
    assert mark(client, order, 0, "edge", "take", "none").status_code == 200
    login(client, _lead())
    data = _check(client, order, 0, "edge").get_json()["data"]
    assert (data["proxied"], data["mark"]["state"]) == (True, "done")
    assert _names(order.id, order.keys[0], "edge") == [("박엣지", True)]
    assert row(order.id, order.keys[0], "edge").holders[0]["done_name"] == "박반장"
    assert "(대신 처리)" in _audits(order.id)[-1]


# --------------------------------------------------------------------------- #
# 화면 — 서버가 그린 판
# --------------------------------------------------------------------------- #
def test_lead_and_admin_boards_show_take_and_finish_on_unseen_cards(client, cohort):
    order, held = make_order(3), make_order(1)
    patch_sd(held.id, hold={"active": True, "reason": "자재 기다림"})
    lead, admin = _lead(), _admin()
    page = _page(client, lead, CUT_ADMIN)
    assert _box(page, order.keys[0]) == CUT_LEAD_NONE  # 재단 = [기본][작업 시작] / 둘째 줄 [재단 완료]
    held_act = _act(_card(page, held.keys[0]))
    assert "pp-st-hold" in held_act and 'data-pp-act="check"' not in held_act  # 보류 칸 = 지금 그대로
    assert _box(_page(client, admin, CUT_ADMIN), order.keys[1]) == CUT_LEAD_NONE
    assert _box(_page(client, admin, EDGE_ADMIN), order.keys[0]) == EDGE_LEAD_NONE  # 그 밖 = 한 줄 둘
    assert _box(_page(client, lead, EDGE_ADMIN), order.keys[2]) == EDGE_LEAD_NONE
    pre = _act(_card(_page(client, lead, INSPECT_ADMIN), order.keys[0]))
    assert "pp-st-pre" in pre and 'data-pp-act="check"' not in pre  # 검수 전 칸 = 지금 그대로


def test_part_account_and_view_only_boards_are_unchanged(client, cohort):
    order = make_order(2)
    part_page = _page(client, make_user("이시영", part="cut"))
    assert _box(part_page, order.keys[0]) == CUT_PART_NONE and 'data-pp-act="check"' not in part_page
    edge_page = _page(client, make_user("박엣지", part="edge"))
    assert _box(edge_page, order.keys[0]) == (
        '<button type="button" class="foms-prod-home__btn foms-prod-home__btn--pri pp-act" data-pp-act="take">엣지 시작</button>')  # 11-27 재단처럼 진하게
    assert 'data-pp-act="check"' not in edge_page
    view = _act(_card(_page(client, make_user("상담", team="CS"), CUT_ADMIN), order.keys[0]))
    assert "<button" not in view


def test_done_card_reads_lead_name_on_every_board(client, cohort):
    order = make_order(2)
    login(client, _lead())
    _check(client, order, 0)
    lead = _act(_card(_page(client, _lead(), CUT_ADMIN), order.keys[0]))
    assert '<span class="fph-wi pp-act pp-st-done pp-not-done">재단 완료 · 박반장</span>' in lead and 'data-pp-act="undo"' in lead
    part = _act(_card(_page(client, make_user("이시영", part="cut")), order.keys[0]))
    assert "재단 완료 · 박반장" in part and "<button" not in part  # 파트 계정은 남의 완료를 못 되돌림(지금 그대로)


# --------------------------------------------------------------------------- #
# 화면 — JS(서버가 그린 판 위에서, 서버 답은 진짜 API JSON)
# --------------------------------------------------------------------------- #
def test_js_redraws_unseen_cards_like_the_server(client, cohort, tmp_path):
    order, held = make_order(3), make_order(1)
    patch_sd(held.id, hold={"active": True, "reason": "자재 기다림"})
    login(client, make_user("이시영", part="cut"))
    mark(client, order, 1, "cut", "take", "none")
    lead, admin = _lead(), _admin()
    for who, url in ((lead, CUT_ADMIN), (admin, EDGE_ADMIN), (lead, INSPECT_ADMIN), (make_user("김재단", part="cut"), HOME_NONE),
                     (make_user("박엣지", part="edge"), HOME_NONE), (make_user("상담", team="CS"), CUT_ADMIN)):
        page = tmp_path / f"b_{who.id}_{url[-4:]}.html"
        page.write_text(_page(client, who, url), encoding="utf-8")
        out = _node(page, {"steps": [{"do": "parity"}]})["out"][0]
        assert out["cards"] == 4 and out["diffs"] == [], (who.name, url, out["diffs"])


def test_js_cut_direct_done_window_counts_and_first_drawing(client, cohort, tmp_path):
    order = make_order(3, run=False)  # 제작 대기 — 첫 도면
    lead = _lead()
    page = tmp_path / "lead.html"
    page.write_text(_page(client, lead, CUT_ADMIN), encoding="utf-8")
    k = order.keys
    reply = _post(client, lead, {"order_id": order.id, "drawing_key": k[0], "part": "cut", "action": "check", "seen": "none",
                                 "seen_me": "none"})
    res = _node(page, {"posts": [reply], "steps": [
        {"do": "card", "key": k[0]}, {"do": "click", "key": k[0], "act": "check"}, {"do": "run"}, {"do": "card", "key": k[0]},
        {"do": "card", "key": k[1]}]})
    out, calls = res["out"], res["calls"]
    w = out[1]["modal"]
    assert (w["title"], w["line"], w["run"]["text"], w["note"], w["body"]) == (
        "재단 완료할까요?", "미정 → 재단 완료 · 박반장", "재단 완료", "", "이 주문 첫 도면이라 제작 시작도 같이 돼요.")  # 11-27 안 봄 → 미정
    assert calls[0]["body"] == {"order_id": order.id, "drawing_key": k[0], "part": "cut", "action": "check", "seen": "none",
                                "seen_me": "none"}
    assert out[2]["sent"] == 1 and out[2]["modal"]["hidden"] is True
    assert out[2]["status"] == "재단 완료했어요 · 제작 시작도 같이 됐어요"
    before, after = out[0], out[3]
    assert (after["card"]["state"], after["card"]["in_done"], after["card"]["in_need"]) == ("done", "1", "0")
    assert after["card"]["act"][0]["text"] == "재단 완료 · 박반장" and after["card"]["act"][1]["kids"][1]["act"] == "undo"
    assert int(after["counts"]["done"][0]) == int(before["counts"]["done"][0]) + 1
    assert int(after["counts"]["unseen"][0]) == int(before["counts"]["unseen"][0]) - 1  # [남은 N장 모두 기본]
    assert after["counts"]["need"] == before["counts"]["need"] and after["counts"]["all"] == before["counts"]["all"]
    assert [a["act"] for a in out[4]["card"]["act"][0]["kids"]] == ["basic", "take"] and out[4]["card"]["act"][1]["act"] == "check"


def test_js_edge_window_409_redraw_and_synced_mark(client, cohort, tmp_path):
    order = make_order(3)
    admin = _admin()
    page = tmp_path / "admin.html"
    page.write_text(_page(client, admin, EDGE_ADMIN), encoding="utf-8")
    k = order.keys
    patch_sd(order.id, hold={"active": True, "reason": "자재 기다림"})  # 그사이 보류 — 서버 거절 409 + 서버 모습
    refused = _post(client, admin, {"order_id": order.id, "drawing_key": k[0], "part": "edge", "action": "check", "seen": "none",
                                    "seen_me": "none"})
    assert refused["__status"] == 409 and refused["body"]["data"]["code"] == "HOLD_ACTIVE"
    patch_sd(order.id, hold={"active": False})
    login(client, make_user("박엣지", part="edge"))
    mark(client, order, 2, "edge", "take", "none")
    mark(client, order, 2, "edge", "release", "need")  # 시작했다 취소 = 표시 줄 NONE(받아 오기가 다시 그릴 줄)
    login(client, admin)
    got = client.get(f"/api/production/part-marks?order_ids={order.id}&since=2000-01-01T00:00:00").get_json()["data"]["marks"]
    synced = next(m for m in got if m["drawing_key"] == k[2] and m["part"] == "edge")
    assert synced["state"] == "none"
    res = _node(page, {"posts": [refused], "steps": [
        {"do": "click", "key": k[0], "act": "check"}, {"do": "run"}, {"do": "card", "key": k[0]},
        {"do": "apply", "key": k[2], "mark": synced}]})
    out = res["out"]
    w = out[0]["modal"]
    assert (w["title"], w["line"], w["run"]["text"], w["body"]) == ("엣지 완료할까요?", "미정 → 엣지 완료 · 관리", "엣지 완료", "")
    assert out[1]["modal"]["lost"] is True and out[1]["modal"]["err"] == refused["body"]["error"]  # 서버 글 그대로
    two = [{"tag": "div", "cls": "pp-two", "act": None, "text": "엣지 시작엣지 완료", "kids": [
        {"tag": "button", "cls": "foms-prod-home__btn pp-act", "act": "take", "text": "엣지 시작", "kids": []},
        {"tag": "button", "cls": "fph-qr__done pp-act pp-fin is-pair", "act": "check", "text": "엣지 완료", "kids": []}]}]
    assert out[2]["card"]["state"] == "none" and out[2]["card"]["act"] == two  # 409 뒤 서버 모습으로 다시 그려도 같은 규칙
    assert out[3]["card"]["state"] == "none" and out[3]["card"]["act"] == two  # 받아 오기 표시로 다시 그려도 같은 규칙


# --------------------------------------------------------------------------- #
# JS · 템플릿 원문 계약
# --------------------------------------------------------------------------- #
def test_source_contract_one_drawing_at_a_time():
    crew = (JS / "foms-production-parts-crew.js").read_text(encoding="utf-8")
    modal = (JS / "foms-production-parts-modal.js").read_text(encoding="utf-8")
    parts = (JS / "foms-production-parts.js").read_text(encoding="utf-8")
    tpl = (ROOT / "templates/production/partials/home_parts.html").read_text(encoding="utf-8")
    assert "if (!o.mine) { (o.cut ? box : row).appendChild(el('button', 'fph-qr__done pp-act pp-fin is-pair', LABEL + ' 완료', 'check')); }" in crew
    assert '<button type="button" class="fph-qr__done pp-act pp-fin is-pair" data-pp-act="check">{{ pb.part_label }} 완료</button>' in tpl
    assert "{% if not pb.mine %}{{ pp_fin_now(pb) }}{% endif %}" in tpl and "{%- elif pb.writable and not pb.mine -%}" in tpl
    assert "['take', 'basic', 'bulk', 'check'].indexOf(action) >= 0" in modal
    assert "cut: IS_CUT" in parts and " 시작', 'take'" not in parts  # 안 봄 칸 그리기는 crew 한 곳
    # 한 장씩만 — 여러 장을 한 번에 완료하는 새 단추 · 요청 없음(일괄은 [남은 N장 모두 기본] 하나)
    assert tpl.count('data-pp-act="bulk"') == 1 and parts.count("'/api/production/part-marks/basic'") == 1
    assert tpl.count('data-pp-act="check"') == 2 and crew.count("'check')") == 2  # 반장 칸 대신 완료 + 미정 칸 바로 완료, 둘뿐
    for f in ("foms-production-parts.js", "foms-production-parts-crew.js", "foms-production-parts-modal.js"):
        assert len((JS / f).read_text(encoding="utf-8").splitlines()) <= 300, f


@pytest.mark.parametrize("name,pin", [("parts", "20261128e"), ("parts-claim", "20261127w"), ("parts-modal", "20261128e"),
                                      ("parts-crew", "20261127z")])  # modal · crew = 바로 완료 취소 한 번에 미정 + 단추 무게 · 차례 맞춤(비평 C59) + [<파트> 시작] 글을 합쳐 r
def test_pins_bumped(name, pin):
    tpl = (ROOT / "templates/production/partials/home_scripts.html").read_text(encoding="utf-8")
    assert f"foms-production-{name}.js') }}}}?v={pin}\" defer" in tpl
