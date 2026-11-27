"""창에 보인 대로만 된다 — 취소 창이 미리 알린 것과 실제 결과가 다르면 아무것도 바꾸지 않고 멈춘다(사장님 2026-11-27 "설계대로 만들기").

승인 글(글자 그대로): "취소 단추를 누를 때 화면이 '내 창에는 같이 취소된다는 줄이 보였다 / 안 보였다'를 서버에 같이 보냅니다. 서버가 실제로 해
보니 그와 다르면 아무것도 바꾸지 않고 멈춥니다. … 취소되지 않고 창에 '그 사이 이 주문이 바뀌었어요. 다시 확인해 주세요.' → 창이 스스로 다시
확인해 줄이 사라짐 → 한 번 더 누르면 내 시작만 취소됨. 반대(줄 없이 열렸는데 그 사이 남이 취소해서 제작 시작까지 취소될 차례)도 같이 멈추고,
다시 확인하면 줄이 나타납니다." · "무선망이 느려 3초 안에 확인을 못 받아 줄 없이 열린 창도 같은 규칙입니다."

* 보내는 칸 ``seen_cancel``(true = 줄이 보였다 · false = 안 보였다). 거절 = 409 ``CANCEL_NOTICE_STALE`` + 위 글. 판정은 쓰기 길이 이미 계산하는
  되돌림 판정(``plan_start_rollback``) 한 곳 — 쿼리가 늘지 않는다. 판정이 표시 쓰기 flush 뒤라 되감기가 다 되는지 전 · 후 모습으로 견준다.
* 값을 안 실은 쓰기(옛 화면 사본 · PC 창 · 작업 시트)는 지금 그대로. 미리 보기(``dry``)는 견주지 않는다. 문(로그인 · 파트 · 공장 · 낡은 화면)은 먼저.
* 화면(JS — 서버 답은 진짜 API JSON): 그 409 뒤 창이 그대로 · 서버 글 · 다시 물어 줄을 새 답으로 · 다시 누르면 새 값 · 고르기 창은 단추마다 따로.

되돌리면 실패: 줄이 보였는데 말없이 내 시작만 취소됨 / 줄 없이 제작 시작까지 취소됨 / 거절인데 표시 · 감사가 남음 / 거절 뒤 창이 닫힘.
이름은 모두 지어낸 값이다.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import event

from db import db_session, engine
from foms.services.orders.state_axes import read_main_stage
from foms.services.production.start_rollback import CANCEL_NOTICE_STALE, CANCEL_NOTICE_STALE_MESSAGE, check_cancel_notice
from foms.services.sales_commission.settings import load_settings, save_freelancer
from models import OrderEvent, ProductionPartMark, ProductionRun, SecurityLog, User
from tests.domains.test_production_cancel_notice_1127 import (
    CANCEL_LINE,
    CANCELLED_TAIL,
    _answer,
    _as_query,
    _ask,
    _body,
    _flag,
    _kim,
    _oh,
    _query,
    _took,
)
from tests.domains.test_production_cancel_notice_undo_1127 import UNDO_LINE, _undo
from tests.domains.test_production_home_query_count import _count_queries
from tests.domains.test_production_lead_direct_done_1127 import _check, _lead
from tests.domains.test_production_multi_holder_board import CUT_ADMIN, _node, _page, _post, cohort  # noqa: F401
from tests.support.production_part_claim_seed import ONE, code, current_runs, fresh, login, make_order, make_user, mark

ROOT = Path(__file__).resolve().parents[2]
MESSAGE = "그 사이 이 주문이 바뀌었어요. 다시 확인해 주세요."
KINDS = ("release", "remove", "undo", "basic")  # 내 시작 취소 · 반장이 남의 시작 취소 · 바로 완료한 도면의 완료 취소 · 기본 취소
SYNC = "/api/production/part-marks?order_ids={}&since=2000-01-01T00:00:00"


def _scene(client, kind: str, alone: bool):
    """도면 2장 주문의 도면 1 에 ``kind`` 가 취소할 표시를 만든다(그 표시가 회차를 연다). ``alone`` 이 아니면 오재단이 도면 2 를 시작해 둔다.

    Returns:
        (주문, 누를 사람, 화면이 보내는 쓰기 몸 — ``seen_cancel`` 없이, 오재단). 누를 사람으로 로그인해 둔다.
        ``alone`` 이면 그 누름으로 제작 시작도 같이 취소될 차례, 아니면 회차 그대로일 차례다.
    """
    kim, oh = _kim(), _oh()
    order = make_order(2, run=False)
    if kind in ("release", "remove"):
        login(client, kim)
        assert mark(client, order, 0, "cut", "take", "none").get_json()["data"]["run_started"] is True
        actor = kim if kind == "release" else _lead()
        body = _body(order, action=kind, seen_by=kim.id, **({"target_user_id": kim.id} if kind == "remove" else {}))
    elif kind == "undo":
        actor = _lead()
        login(client, actor)
        assert _check(client, order, 0).get_json()["data"]["run_started"] is True
        body = _undo(order, seen_me="done")
    else:
        actor = kim
        login(client, kim)
        assert mark(client, order, 0, "cut", "basic", "none").get_json()["data"]["run_started"] is True
        body = _undo(order, seen="basic")
    if not alone:
        login(client, oh)
        assert mark(client, order, 1, "cut", "take", "none").status_code == 200
    login(client, actor)
    return order, actor, body, oh


def _state(oid: int) -> dict:
    """주문 하나의 모습 전부 — 표시 줄(모든 칸) · 주문 단계 · 버전 · 공정 칸을 포함한 자료 · 회차 · 감사 줄 · 이벤트 수(전체 표 수까지)."""
    db_session.expire_all()
    order = fresh(oid)
    marks = sorted(json.dumps({c.name: getattr(m, c.name) for c in m.__table__.columns}, sort_keys=True, default=str)
                   for m in db_session.query(ProductionPartMark).filter_by(order_id=oid).all())
    runs = sorted((r.id, r.status, r.is_current) for r in db_session.query(ProductionRun).filter_by(order_id=oid).all())
    return {"version": order.mutation_version, "status": order.status, "stage": read_main_stage(order),
            "stage_code": order.erp_stage_code, "sd": json.dumps(order.structured_data, sort_keys=True, default=str),
            "marks": marks, "runs": runs, "current_runs": current_runs(oid),
            "events": db_session.query(OrderEvent).filter_by(order_id=oid).count(), "all_events": db_session.query(OrderEvent).count(),
            "audits": db_session.query(SecurityLog).filter_by(target_id=oid).count(), "all_audits": db_session.query(SecurityLog).count()}


def _refused(resp) -> None:
    assert resp.status_code == 409, resp.get_json()
    assert resp.get_json() == {"success": False, "data": {"code": "CANCEL_NOTICE_STALE"}, "error": MESSAGE}


# --------------------------------------------------------------------------- #
# 서버 — 본 것과 실제가 다르면 멈춘다(양쪽 다) · 아무것도 안 바뀐다
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("alone", [False, True], ids=["줄을_봤는데_안_취소될_차례", "줄을_못_봤는데_같이_취소될_차례"])
@pytest.mark.parametrize("kind", KINDS)
def test_stops_and_changes_nothing_when_the_window_showed_something_else(client, kind, alone):
    order, _actor, body, _oh_user = _scene(client, kind, alone)
    assert _flag(client, body) is alone  # 지금 서버 판정(창을 새로 열면 볼 것)
    before = _state(order.id)
    _refused(client.post(ONE, json={**body, "seen_cancel": not alone}))  # 창이 보여 준 것이 그 반대
    assert _state(order.id) == before, "거절인데 무언가 바뀌었다"
    assert _flag(client, body) is alone  # 다시 확인 = 새 답. 그 값으로 한 번 더 누르면 지금과 같은 성공
    resp = client.post(ONE, json={**body, "seen_cancel": alone})
    data = resp.get_json()["data"]
    assert resp.status_code == 200 and data["changed"] is True and data["run_cancelled"] is alone
    assert current_runs(order.id) == (0 if alone else 1) and _state(order.id) != before


def test_refusal_rolls_back_the_mark_write_that_was_already_flushed(client):
    """판정은 표시 쓰기 flush 뒤다 — 거절 요청 안에서 표시 줄 · 이벤트 쓰기가 나갔다가 되감기는 것을 SQL 로 확인한다(커밋 0)."""
    order, _actor, body, _oh_user = _scene(client, "release", alone=False)
    before = _state(order.id)
    seen: list[str] = []
    ends: list[str] = []

    def _sql(conn, cursor, statement, params, context, executemany):
        seen.append(" ".join(statement.split())[:60].lower())

    hooks = [("before_cursor_execute", _sql), ("commit", lambda conn: ends.append("commit")),
             ("rollback", lambda conn: ends.append("rollback"))]
    for name, fn in hooks:
        event.listen(engine, name, fn)
    try:
        _refused(client.post(ONE, json={**body, "seen_cancel": True}))
    finally:
        for name, fn in hooks:
            event.remove(engine, name, fn)
    assert any(s.startswith("update production_part_marks") for s in seen), seen  # 표시 줄 쓰기는 나갔다
    assert any(s.startswith("insert into order_events") for s in seen), seen
    assert not any("security_logs" in s or s.startswith("update orders") or "production_runs" in s and not s.startswith("select")
                   for s in seen), seen  # 주문 쓰기 · 감사 · 회차 쓰기는 시작도 안 했다
    assert "commit" not in ends and "rollback" in ends, ends
    assert _state(order.id) == before


@pytest.mark.parametrize("alone", [False, True])
@pytest.mark.parametrize("kind", KINDS)
def test_matching_value_and_no_value_succeed_exactly_like_today(client, kind, alone):
    """본 것과 실제가 같음(true/true · false/false) = 값 없는 쓰기와 같은 성공 응답. 값 없음(옛 화면 · PC 창)은 양쪽 경우 모두 지금 그대로."""
    answers = []
    for extra in ({}, {"seen_cancel": None}, {"seen_cancel": alone}):
        order, _actor, body, _oh_user = _scene(client, kind, alone)
        resp = client.post(ONE, json={**body, **extra})
        assert resp.status_code == 200, (extra, resp.get_json())
        data = resp.get_json()["data"]
        assert data["changed"] is True and data["run_cancelled"] is alone and current_runs(order.id) == (0 if alone else 1)
        audit = db_session.query(SecurityLog).filter_by(target_id=order.id, action="PRODUCTION_PART_MARKED").order_by(SecurityLog.id.desc()).first()
        answers.append((sorted(data), data["mark"]["state"], data["order_step"] and data["order_step"]["done"], data["run_started"],
                        (" · 제작 시작 취소" in audit.message) is alone, sorted(audit.detail)))
    assert answers[0] == answers[1] == answers[2]


def test_bad_value_is_a_400_like_the_other_fields(client):
    order, _actor, body, _oh_user = _scene(client, "release", alone=True)
    before = _state(order.id)
    for bad in ("true", "false", "", "yes", 1, 0, [], {}, [True]):
        resp = client.post(ONE, json={**body, "seen_cancel": bad})
        assert resp.status_code == 400 and code(resp) == "BAD_REQUEST", bad
        assert resp.get_json()["error"] == "본 취소 안내 값이 올바르지 않아요."
    login(client, make_user("박엣지", part="edge"))  # 몸 검사(400)는 다른 칸처럼 파트 문(403)보다 먼저
    assert client.post(ONE, json={**body, "seen_cancel": "x"}).status_code == client.post(ONE, json={**body, "seen_me": "x"}).status_code == 400
    assert _state(order.id) == before


def test_gates_still_refuse_first_and_unchanged(client):
    """로그인 · 프리랜서 · 파트 문 · 남의 공장 · 권한 · 낡은 화면 · 생산 단계 문은 지금 그대로 먼저 — 값이 어긋나 있어도 같은 답."""
    order, kim, body, _oh_user = _scene(client, "release", alone=False)
    wrong = {**body, "seen_cancel": True}  # 실제는 안 취소될 차례 — 문을 지나면 CANCEL_NOTICE_STALE
    before = _state(order.id)

    def _same(payload: dict, status: int, want: str | None = None) -> None:
        plain = client.post(ONE, json={k: v for k, v in payload.items() if k != "seen_cancel"})
        resp = client.post(ONE, json=payload)
        assert (resp.status_code, code(resp)) == (plain.status_code, code(plain)) and resp.status_code == status, (resp.get_json(), want)
        assert code(resp) != CANCEL_NOTICE_STALE and (want is None or code(resp) == want)

    login(client, make_user("박엣지", part="edge"))
    _same(wrong, 403, "PART_FORBIDDEN")
    login(client, make_user("상담", team="CS"))
    _same(wrong, 403, "PART_REQUIRED")
    free = make_user("프리영업", team="SALES")
    save_freelancer(db_session, free.id, {"match_name": "가짜프리", "start_month": "2020-01", "tax_type": "NONE", "active": True},
                    base_version=load_settings(db_session)[0], actor_user_id=None)
    db_session.commit()
    login(client, free)
    _same(wrong, 403)
    far = make_user("원반장", lead=True)  # 2공장 반장 — 1공장 장의 남의 시작 취소
    db_session.query(User).filter_by(id=far.id).update({"production_factory": 2})
    db_session.commit()
    login(client, far)
    _same({**_body(order, action="remove", seen_by=kim.id, target_user_id=kim.id), "seen_cancel": True}, 403, "OTHER_FACTORY")
    login(client, kim)
    _same({**wrong, "drawing_key": "x/none.png"}, 409, "DRAWING_NOT_CURRENT")
    _same({**wrong, "seen": "done", "action": "undo"}, 409, "MARK_CONFLICT")  # 낡은 화면(본 상태가 다름)이 먼저
    _same({**wrong, "order_id": 987654}, 404, "NOT_FOUND")
    assert _state(order.id) == before
    with client.session_transaction() as sess:
        sess.clear()
    assert client.post(ONE, json=wrong).status_code in (401, 302)
    login(client, kim)
    _refused(client.post(ONE, json=wrong))  # 대조 — 문을 다 지난 같은 몸은 이 규칙이 멈춘다
    assert _state(order.id) == before


def test_preview_ignores_the_value_and_same_press_again_is_idempotent(client):
    order, kim, body, _oh_user = _scene(client, "release", alone=True)
    for shown in ("true", "false", "x"):  # 미리 보기 질의에 실려 와도 읽지 않는다(견주면 409 → 거짓으로 답해 줄이 사라진다)
        assert _flag(client, {**body, "seen_cancel": shown}) is True
    assert _ask(client, {**body, "seen_cancel": "false"}).get_json()["data"] == {"run_cancelled": True}
    assert client.post(ONE, json={**body, "seen_cancel": True}).get_json()["data"]["run_cancelled"] is True
    again = client.post(ONE, json={**body, "seen_cancel": True})  # 같은 사람 · 같은 결과를 다시 보냄(멱등) — 판정까지 안 가 지금처럼 200
    assert again.status_code == 200 and again.get_json()["data"]["changed"] is False
    assert again.get_json()["data"]["run_cancelled"] is False
    # 취소가 아닌 누름에 실려 와도 같은 한 규칙 — 줄이 '안 보였다'면 그대로, '보였다'면 같이 취소될 것이 없어 멈춘다
    assert mark(client, order, 0, "cut", "take", "none", seen_me="none", seen_cancel=False).status_code == 200
    before = _state(order.id)
    _refused(mark(client, order, 1, "cut", "take", "none", seen_me="none", seen_cancel=True))
    assert _state(order.id) == before


def test_write_path_query_count_does_not_grow(client):
    """판정은 이미 쓰기 길에 있다 — 값을 실어도 쿼리 수가 같고, 멈추는 요청은 그보다 적다(주문 쓰기 · 감사 전에 멈춘다)."""
    kim = _kim()
    login(client, kim)
    mark(client, make_order(1), 0, "cut", "take", "none")  # warmup

    def _count(alone: bool, shown) -> int:
        order, _actor, body, _oh_user = _scene(client, "release", alone)
        payload = body if shown is None else {**body, "seen_cancel": shown}
        resp, n = _count_queries(lambda: client.post(ONE, json=payload))
        assert resp.status_code == (200 if shown in (None, alone) else 409)
        return n

    for alone in (True, False):
        plain, same, stale = _count(alone, None), _count(alone, alone), _count(alone, not alone)
        assert same == plain, (alone, plain, same)
        assert stale < plain, (alone, plain, stale)
        print(f"QUERY-COUNT alone={alone} plain={plain} same={same} stale={stale}")


def test_check_function_and_source_contract():
    class Refusal(Exception):
        pass

    for shown, closing in ((None, None), (None, object()), (True, object()), (False, None)):
        check_cancel_notice(shown, closing, Refusal)  # 안 실음 · 같음 = 통과
    for shown, closing in ((True, None), (False, object())):
        with pytest.raises(Refusal) as stop:
            check_cancel_notice(shown, closing, Refusal)
        assert stop.value.args == (409, CANCEL_NOTICE_STALE, CANCEL_NOTICE_STALE_MESSAGE)
    assert (CANCEL_NOTICE_STALE, CANCEL_NOTICE_STALE_MESSAGE) == ("CANCEL_NOTICE_STALE", MESSAGE)
    write = (ROOT / "foms/services/production/part_mark_write.py").read_text(encoding="utf-8")
    assert write.count("check_cancel_notice(seen_cancel, closing, MarkRefusal)") == 1 and len(write.splitlines()) <= 499
    assert (write.index("closing = plan_start_rollback(") < write.index("if dry:") < write.index("check_cancel_notice(seen_cancel, closing,")
            < write.index("steps, started = apply_order_changes("))  # 미리 보기는 견주지 않고, 주문 쓰기 · 감사 전에 멈춘다
    js = ROOT / "static/js/production"
    cancel = (js / "foms-production-parts-cancel.js").read_text(encoding="utf-8")
    parts = (js / "foms-production-parts.js").read_text(encoding="utf-8")
    assert cancel.count("body.seen_cancel = ") == 1 and "seen_cancel" not in parts.replace("(seen_cancel — 11-27", "")
    assert "if (M.seenCancel) { M.seenCancel(p, body); }" in parts and "if (M.staleCancel && M.staleCancel(p, data.code, text)) { return; }" in parts
    assert "'NOT_IN_PRODUCTION', 'CANCEL_NOTICE_STALE']" in parts and "var STALE = 'CANCEL_NOTICE_STALE';" in cancel
    assert cancel.count("fetch(") == 1 and "method: 'POST'" not in cancel and MESSAGE not in cancel + parts  # 글은 서버 글 그대로
    for other in ("foms-production-pc-sheet-write.js", "foms-production-sheet-parts.js", "foms-production-sheet-page.js"):
        assert "seen_cancel" not in (js / other).read_text(encoding="utf-8"), other  # PC 창 · 작업 시트는 값 없이 — 지금 그대로


# --------------------------------------------------------------------------- #
# 화면 — 거절 뒤 창 그대로 · 서버 글 · 다시 묻기 · 새 값으로 다시(서버 답은 진짜 API JSON)
# --------------------------------------------------------------------------- #
def _sync(client, who, order) -> dict:
    login(client, who)
    return client.get(SYNC.format(order.id)).get_json()


def test_js_release_window_stops_reasks_and_resends_both_ways(client, cohort, tmp_path):
    kim, oh = _kim(), _oh()
    order = _took(client, kim, 2)
    k = order.keys
    page = tmp_path / "kim.html"
    page.write_text(_page(client, kim), encoding="utf-8")
    rel0, rel_oh = _body(order, seen_by=kim.id), _body(order, 1, seen_by=oh.id)
    yes = _answer(client, kim, rel0)  # 김재단 창 — 줄이 뜬다
    login(client, oh)
    assert mark(client, order, 1, "cut", "take", "none").status_code == 200  # 그 사이 오재단이 같은 주문 다른 도면을 시작
    stop1 = _post(client, kim, {**rel0, "seen_cancel": True})  # [재단 시작 취소] — 멈춘다
    got1, no = _sync(client, kim, order), _answer(client, kim, rel0)
    login(client, oh)
    assert client.post(ONE, json=rel_oh).status_code == 200  # 다시 누르기 전에 오재단이 자기 것을 취소(계속 바뀌는 중)
    stop2 = _post(client, kim, {**rel0, "seen_cancel": False})  # 이번엔 줄 없이 봤는데 같이 취소될 차례 — 또 멈춘다
    got2, yes2 = _sync(client, kim, order), _answer(client, kim, rel0)
    done = _post(client, kim, {**rel0, "seen_cancel": True})
    assert (stop1["__status"], stop2["__status"], done["data"]["run_cancelled"]) == (409, 409, True)
    assert [a["data"]["run_cancelled"] for a in (yes, no, yes2)] == [True, False, True]
    res = _node(page, {"sync": True, "gets": [got1, got2], "posts": [stop1, stop2, done], "previews": [yes, {"__hold": no}, yes2], "steps": [
        {"do": "click", "key": k[0], "act": "release"}, {"do": "modal"},  # 0 1  줄이 뜬 창
        {"do": "run"}, {"do": "run"}, {"do": "answer"},                   # 2 3 4  멈춤 · 다시 묻는 동안 잠금 · 새 답
        {"do": "card", "key": k[0]}, {"do": "card", "key": k[1]},        # 5 6
        {"do": "run"}, {"do": "run"}]})                                   # 7 8  또 멈춤(줄이 나타남) · 한 번 더 = 같이 취소
    out, calls = res["out"], res["calls"]
    assert out[1]["modal"]["body"] == CANCEL_LINE and out[1]["modal"]["run"]["locked"] is False
    stop = out[2]["modal"]  # 창 그대로 · 서버 글(오류 줄) · [닫기] 하나로 바뀌지 않음 · 다시 묻는 동안만 잠금 · 알림 없음
    assert (stop["hidden"], stop["lost"], stop["err"], stop["title"]) == (False, False, MESSAGE, "재단 시작을 취소할까요?")
    assert stop["run"] == {"text": "재단 시작 취소", "hidden": False, "locked": True} and out[2]["status"] == ""
    assert out[3]["sent"] == 0 and out[3]["modal"]["body"] == CANCEL_LINE  # 잠긴 동안은 안 나간다 · 줄은 답이 와야 바뀐다
    asked = out[4]["modal"]
    assert (asked["body"], asked["run"]["locked"], asked["err"], asked["hidden"]) == ("", False, MESSAGE, False)  # 줄이 사라짐
    mine, other = out[5]["card"], out[6]["card"]  # 카드: 내 것은 그대로(내 작업) · 그 주문의 다른 카드는 다시 받아 오재단 작업 중
    assert (mine["state"], mine["picked_me"], mine["in_need"]) == ("need", "1", "1")
    assert (other["state"], other["picked_me"], other["crew"]["who"]) == ("need", "0", "오재단")
    again = out[7]["modal"]
    assert (again["hidden"], again["lost"], again["err"], again["body"]) == (False, False, MESSAGE, CANCEL_LINE)  # 줄이 나타남
    assert again["run"]["locked"] is False and out[7]["status"] == ""
    assert out[8]["modal"]["hidden"] is True and out[8]["status"] == "재단 시작 취소했어요" + CANCELLED_TAIL
    writes = [c["body"] for c in calls if c["method"] == "POST"]
    assert writes == [{**rel0, "seen_cancel": v} for v in (True, False, True)]  # 다시 누를 때마다 새로 본 값 · 저절로 다시 보내지 않는다
    assert [c["method"] for c in calls] == ["POST", "GET", "POST", "GET", "POST"]  # 거절마다 그 주문 카드 다시 받기 한 번
    assert [_query(u) for u in res["previews"]] == [_as_query(rel0)] * 3  # 묻는 칸에는 본 것 칸이 없다


def test_js_lead_choice_window_stops_and_keeps_its_buttons(client, cohort, tmp_path):
    kim, oh, lead = _kim(), _oh(), _lead()
    shown = _took(client, kim, 2)   # ㉮ 줄이 뜬 창 → 그 사이 오재단이 다른 도면을 시작
    hidden = _took(client, kim, 2)  # ㉯ 줄 없는 창(오재단도 시작해 둠) → 그 사이 오재단이 자기 것을 취소
    login(client, oh)
    assert mark(client, hidden, 1, "cut", "take", "none").status_code == 200
    page = tmp_path / "lead.html"
    page.write_text(_page(client, lead, CUT_ADMIN), encoding="utf-8")
    rm_a = _body(shown, action="remove", seen_by=kim.id, target_user_id=kim.id)
    rm_b = _body(hidden, action="remove", seen_by=kim.id, target_user_id=kim.id)
    yes_a, no_b = _answer(client, lead, rm_a), _answer(client, lead, rm_b)
    login(client, oh)
    assert mark(client, shown, 1, "cut", "take", "none").status_code == 200
    assert client.post(ONE, json=_body(hidden, 1, seen_by=oh.id)).status_code == 200
    stop_a = _post(client, lead, {**rm_a, "seen_cancel": True})
    stop_b = _post(client, lead, {**rm_b, "seen_cancel": False})
    no_a, yes_b = _answer(client, lead, rm_a), _answer(client, lead, rm_b)
    done_a = _post(client, lead, {**rm_a, "seen_cancel": False})
    done_b = _post(client, lead, {**rm_b, "seen_cancel": True})
    assert (stop_a["__status"], stop_b["__status"]) == (409, 409)
    assert (done_a["data"]["run_cancelled"], done_b["data"]["run_cancelled"]) == (False, True)
    pick = {"do": "choice", "text": "김재단 시작 취소"}
    res = _node(page, {"posts": [stop_a, done_a, stop_b, done_b], "previews": [yes_a, no_a, no_b, yes_b], "steps": [
        {"do": "click", "key": shown.keys[0], "act": "held"}, {"do": "modal"}, pick, pick,     # 0 1 2 3
        {"do": "click", "key": hidden.keys[0], "act": "held"}, {"do": "modal"}, pick, pick]})  # 4 5 6 7
    out = res["out"]
    line = "[김재단 시작 취소]를 누르면 제작 시작도 같이 취소돼요."
    buttons = [c["text"] for c in out[1]["modal"]["choices"]]
    assert out[1]["modal"]["body"] == line and buttons == ["김재단 시작 취소", "담당 바꾸기", "같이 작업", "대신 완료"]
    stop = out[2]["modal"]  # 고르기 창 그대로 — 단추 넷 · 서버 글 · 줄만 새 답으로(사라짐)
    assert (stop["hidden"], stop["lost"], stop["err"], stop["body"]) == (False, False, MESSAGE, "")
    assert [c["text"] for c in stop["choices"]] == buttons and stop["choices_hidden"] is False and stop["title"] == out[1]["modal"]["title"]
    assert out[2]["sent"] == 1 and out[2]["status"] == ""
    assert out[3]["sent"] == 1 and out[3]["status"] == "김재단 시작 취소했어요" and out[3]["modal"]["hidden"] is True  # 꼬리 없음
    assert out[5]["modal"]["body"] == ""
    stop = out[6]["modal"]  # 반대쪽 — 줄이 나타난다
    assert (stop["hidden"], stop["lost"], stop["err"], stop["body"]) == (False, False, MESSAGE, line)
    assert [c["text"] for c in stop["choices"]] == buttons
    assert out[7]["status"] == "김재단 시작 취소했어요" + CANCELLED_TAIL
    assert [c["body"] for c in res["calls"]] == [{**rm_a, "seen_cancel": True}, {**rm_a, "seen_cancel": False},
                                                 {**rm_b, "seen_cancel": False}, {**rm_b, "seen_cancel": True}]
    assert [_query(u) for u in res["previews"]] == [_as_query(b) for b in (rm_a, rm_a, rm_b, rm_b)]


def test_js_choice_window_sends_each_buttons_own_value(client, cohort, tmp_path):
    """고르기 창에 시작 취소 단추가 둘 — 줄에 이름이 불린 단추만 true 로 나간다. 줄을 만든 참 답은 **지어낸 답**이다(진짜 서버는 둘 다 거짓)."""
    kim, oh, lead = _kim(), _oh(), _lead()
    both = _took(client, kim)
    login(client, oh)
    mark(client, both, 0, "cut", "join", "need", seen_me="none")
    page = tmp_path / "lead.html"
    page.write_text(_page(client, lead, CUT_ADMIN), encoding="utf-8")
    rm_kim, rm_oh = (_body(both, action="remove", seen_by=kim.id, target_user_id=who.id) for who in (kim, oh))
    real = [_answer(client, lead, rm_kim), _answer(client, lead, rm_oh)]
    assert [a["data"]["run_cancelled"] for a in real] == [False, False]
    made_yes = {"success": True, "data": {"run_cancelled": True}, "error": None}
    stop = _post(client, lead, {**rm_oh, "seen_cancel": True})  # 줄에 불린 단추 — 진짜 서버는 멈춘다(한 사람만 빼서는 같이 취소되지 않는다)
    done = _post(client, lead, {**rm_kim, "seen_cancel": False})
    assert stop["__status"] == 409 and done["data"]["run_cancelled"] is False
    click = {"do": "click", "key": both.keys[0], "act": "held"}
    res = _node(page, {"posts": [stop, done], "previews": [real[0], made_yes, *real], "steps": [
        click, {"do": "modal"}, {"do": "choice", "text": "오재단 시작 취소"}, {"do": "choice", "text": "김재단 시작 취소"}]})
    out = res["out"]
    assert out[1]["modal"]["body"] == "[오재단 시작 취소]를 누르면 제작 시작도 같이 취소돼요."
    assert (out[2]["modal"]["hidden"], out[2]["modal"]["err"], out[2]["modal"]["body"]) == (False, MESSAGE, "")  # 진짜 답으로 줄이 사라짐
    assert [c["text"] for c in out[2]["modal"]["choices"]][:2] == ["김재단 시작 취소", "오재단 시작 취소"]
    assert out[3]["status"] == "김재단 시작 취소했어요"
    assert [c["body"] for c in res["calls"]] == [{**rm_oh, "seen_cancel": True}, {**rm_kim, "seen_cancel": False}]
    assert [(q["action"], q["target_user_id"]) for q in map(_query, res["previews"])] == [("remove", str(u.id)) for u in (kim, oh, kim, oh)]


def test_js_undo_window_stops_and_reasks(client, cohort, tmp_path):
    lead, kim = _lead(), _kim()
    order = make_order(2, run=False)
    login(client, lead)
    assert _check(client, order, 0).get_json()["data"]["run_started"] is True  # 반장이 바로 [재단 완료] — 유일한 표시
    page = tmp_path / "lead.html"
    page.write_text(_page(client, lead, CUT_ADMIN), encoding="utf-8")
    undo = _undo(order, seen_me="done")
    yes = _answer(client, lead, undo)
    login(client, kim)
    assert mark(client, order, 1, "cut", "take", "none").status_code == 200  # 그 사이 김재단이 다른 도면을 시작
    stop = _post(client, lead, {**undo, "seen_cancel": True})
    no = _answer(client, lead, undo)
    done = _post(client, lead, {**undo, "seen_cancel": False})
    assert (stop["__status"], yes["data"]["run_cancelled"], no["data"]["run_cancelled"], done["data"]["run_cancelled"]) == (409, True, False, False)
    res = _node(page, {"posts": [stop, done], "previews": [yes, no], "steps": [
        {"do": "click", "key": order.keys[0], "act": "undo"}, {"do": "modal"}, {"do": "run"}, {"do": "run"}]})
    out = res["out"]
    assert out[1]["modal"]["body"] == UNDO_LINE
    stopped = out[2]["modal"]
    assert (stopped["hidden"], stopped["lost"], stopped["err"], stopped["body"]) == (False, False, MESSAGE, "")
    assert stopped["run"] == {"text": "재단 완료 취소", "hidden": False, "locked": False} and stopped["line"] == "재단 완료 → 미정"
    assert out[3]["modal"]["hidden"] is True and out[3]["status"] == "재단 완료 취소했어요"
    assert [c["body"].get("seen_cancel") for c in res["calls"]] == [True, False] and len(res["previews"]) == 2


def test_js_window_that_got_no_answer_in_time_sends_false(client, cohort, tmp_path):
    """3초 안에 답을 못 받아 줄 없이 열린 창도 같은 규칙 — 안 보였다(false)로 나가고, 같이 취소될 차례면 멈춘 뒤 다시 물어 줄이 나타난다."""
    kim = _kim()
    order = _took(client, kim, 2)
    page = tmp_path / "kim.html"
    page.write_text(_page(client, kim), encoding="utf-8")
    rel0 = _body(order, seen_by=kim.id)
    yes = _answer(client, kim, rel0)
    stop = _post(client, kim, {**rel0, "seen_cancel": False})
    assert stop["__status"] == 409 and yes["data"]["run_cancelled"] is True
    res = _node(page, {"posts": [stop], "previews": ["__hang", yes], "steps": [
        {"do": "click", "key": order.keys[0], "act": "release"}, {"do": "timers"}, {"do": "modal"}, {"do": "run"}]})
    out = res["out"]
    assert out[2]["modal"]["body"] == "" and out[2]["modal"]["run"]["locked"] is False
    assert (out[3]["modal"]["hidden"], out[3]["modal"]["err"], out[3]["modal"]["body"]) == (False, MESSAGE, CANCEL_LINE)
    assert [c["body"] for c in res["calls"]] == [{**rel0, "seen_cancel": False}]
