"""[수정 제작] 고르기 — 다시 만들 도면 · 다시 할 공정(설계서 2026-11-28 흐름 셋 §2, 사장님 답 6 "다시 할 칸 고르기").

전에는 [수정 제작]이 단계만 생산으로 돌리고 표시 줄 · 공정 칸을 안 건드려, 되돌리자마자 [제작 완료]가 다시 눌렸다(파트 화면에 할 일이
안 생김). 이제 창에서 고른 것만 다시 할 일이 된다.

* 도면이 있는 주문: 고른 도면만 네 파트 '미정'(줄은 남고 이벤트에 예전 사람) · 공정 칸 넷 꺼짐 · 고른 도면이 끝나야 [제작 완료].
  표시를 한 줄도 안 쓴 파트(손으로 켠 옛 칸 · 칸도 도면도 안 쓰고 완료된 주문)는 안 고른 도면이 완료로 풀려 적힌다.
* 도면이 없는 주문: 고른 칸만 꺼짐 · 안 고른 꺼진 칸은 이름 없이 켜짐 · 넷을 다 고르면 넷을 다시 완료해야 한다.
* 한 장도(한 칸도) 안 고른 요청(값 없는 옛 화면 포함)은 400 — 아무것도 안 바뀐다. 공장 둘 주문은 고른 도면이 있는 공장 표지만 지운다.

되돌리면 실패: 안 고른 도면이 미정이 됨 · 고른 도면을 안 끝내도 [제작 완료]가 눌림(구멍) · 안 고른 요청이 지나감 · 거절인데 무엇인가 바뀜 ·
반장이 남의 공장 도면을 고름 · 안 고른 공장 표지가 지워짐 · 옛 수정 제작 기록(고른 것 없음)의 판정이 바뀜.
화면(고르기 창 · Node 길) · 알람 거는 줄 · 원문 계약은 ``test_production_rework_pick_screen_1128.py``.
모든 이름 · 번호는 가짜 값이다.
"""
from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest
from sqlalchemy import event

from db import db_session, engine
from foms.services.orders.drawing_factory import factory_done_entry
from foms.services.production.part_progress import cards_used, parts_in_use, parts_progress
from foms.services.production.part_steps_sync import plan_part_step_changes
from foms.services.production.rework_sheets import (
    BAD_STEP_MESSAGE,
    NOT_CURRENT_MESSAGE,
    PICK_DRAWINGS_MESSAGE,
    PICK_STEPS_MESSAGE,
    ReworkPick,
)
from foms.services.production.steps import production_steps_missing, rework_pick
from models import OrderEvent, ProductionPartMark, ProductionRun
from tests.support.production_factory_seed import factory_user, mixed_order, put_mark
from tests.support.production_part_claim_seed import (
    check_step,
    current_runs,
    events,
    finish,
    fresh,
    login,
    make_order,
    mark,
    patch_sd,
    row,
    step,
)

PARTS = ("cut", "edge", "assemble", "inspect")
ALL_LEFT = "미완료가 있어요 — 재단 {n}장 · 엣지 {n}장 · 조립 {n}장 · 검수 {n}장"


@pytest.fixture
def people():
    return {"lead": factory_user("박반장", lead=True), "lead2": factory_user("강반장", factory=2, lead=True),
            "admin": factory_user("정관리", role="ADMIN", team="CS"), "cut": factory_user("김재단", part="cut")}


def _all_done(seed, who, js=None) -> None:
    for j in (range(len(seed.keys)) if js is None else js):
        for part in PARTS:
            put_mark(seed, j, part, "DONE", who)


def _complete(client, oid: int):
    return client.post(f"/api/orders/{oid}/production/complete", json={})


def _rework(client, oid: int, **body):
    return client.post(f"/api/orders/{oid}/production/rework", json=body)


def _done_seed(client, n: int, who, **kwargs):
    """도면 ``n`` 장을 네 파트 모두 완료하고 제작 완료한 주문(시공 대기)."""
    seed = make_order(n, **kwargs)
    _all_done(seed, who)
    assert _complete(client, seed.id).status_code == 200
    return seed


def _states(seed) -> dict:
    db_session.expire_all()
    rows = db_session.query(ProductionPartMark).filter_by(order_id=seed.id).all()
    return {(seed.keys.index(r.drawing_key), r.part): r.state for r in rows}


def _snapshot(oid: int) -> dict:
    """거절 앞뒤로 견줄 값 전부 — 단계 · 버전 · 주문 JSON · 표시 줄 · 이벤트 · 회차."""
    order = fresh(oid)
    marks = db_session.query(ProductionPartMark).filter_by(order_id=oid).order_by(ProductionPartMark.id).all()
    return {
        "stage": (order.erp_stage_code, order.status), "version": order.mutation_version,
        "sd": copy.deepcopy(order.structured_data),
        "marks": [(m.drawing_key, m.part, m.state, m.done_by_name, m.picked_by_name, copy.deepcopy(m.holders)) for m in marks],
        "events": [e.id for e in db_session.query(OrderEvent).filter_by(order_id=oid).order_by(OrderEvent.id)],
        "runs": [(r.id, r.status, r.is_current) for r in db_session.query(ProductionRun).filter_by(order_id=oid).order_by(ProductionRun.id)],
    }


def _rework_of(oid: int) -> dict:
    return fresh(oid).structured_data["production"]["rework"]


def _marks(oid: int) -> list:
    db_session.expire_all()
    return db_session.query(ProductionPartMark).filter_by(order_id=oid).all()


# --------------------------------------------------------------------------- #
# 1. 도면이 있는 주문 — 고른 도면만 네 파트 미정
# --------------------------------------------------------------------------- #
def test_고른_도면만_네_파트_미정이고_줄과_예전_사람은_남는다(client, people) -> None:
    login(client, people["lead"])
    seed = _done_seed(client, 3, people["cut"], steps_done=PARTS)
    resp = _rework(client, seed.id, reason="  문짝 치수  ", keys=[seed.keys[2], seed.keys[0]])
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json() == {"success": True, "message": "수정 제작을 시작했어요. 도면 2장을 다시 만들어요.", "new_status": "PRODUCTION"}

    states = _states(seed)
    assert {k: v for k, v in states.items() if k[0] in (0, 2)} == {(j, p): "NONE" for j in (0, 2) for p in PARTS}  # 줄은 남는다
    assert {k: v for k, v in states.items() if k[0] == 1} == {(1, p): "DONE" for p in PARTS}  # 안 고른 도면 그대로
    cleared = row(seed.id, seed.keys[0], "cut")
    assert (cleared.picked_by_name, cleared.done_by_name, cleared.done_at, cleared.holders, cleared.handed_from_name) == (None, None, None, [], None)
    assert row(seed.id, seed.keys[1], "edge").done_by_name == "김재단"

    marked = [e.payload for e in events(seed.id, "PRODUCTION_PART_MARKED") if e.payload.get("action") == "rework"]
    assert len(marked) == 8 and {(p["key"], p["part"]) for p in marked} == {(seed.keys[j], part) for j in (0, 2) for part in PARTS}
    for payload in marked:  # 약속 9 — 바뀐 기록 글은 이 모양을 읽는다
        assert (payload["from"], payload["to"], payload["by_name"], payload["rework_count"]) == ("DONE", "NONE", "박반장", 1)
        assert payload["holders_before"] == [{"uid": people["cut"].id, "name": "김재단", "done": True}]

    order = fresh(seed.id)
    assert (order.erp_stage_code, order.status) == ("PRODUCTION", "PRODUCTION")
    rework = order.structured_data["production"]["rework"]
    assert (rework["active"], rework["reason"], rework["count"], rework["by_name"]) == (True, "문짝 치수", 1, "박반장")
    assert rework["keys"] == [seed.keys[0], seed.keys[2]] and "steps" not in rework  # 도면 번호 순
    assert [step(seed.id, p)["done"] for p in PARTS] == [False] * 4  # 공정 칸 넷 꺼짐
    offs = [e.payload for e in events(seed.id, "PRODUCTION_STEP_CHECKED")]
    assert [(p["key"], p["done"], p["via"], p["trigger"]) for p in offs] == [(p, False, "part_marks", "rework") for p in PARTS]
    started = events(seed.id, "PRODUCTION_REWORK_STARTED")[-1].payload
    assert started["keys"] == [seed.keys[0], seed.keys[2]] and started["numbers"] == [1, 3] and started["count"] == 1
    assert current_runs(seed.id) == 1

    progress = parts_progress(order.structured_data, _marks(seed.id))  # 날짜 줄 "재단 1/3"
    assert {p: (progress[p]["done_n"], progress[p]["total_n"], progress[p]["uses_cards"]) for p in PARTS} == {p: (1, 3, True) for p in PARTS}
    blocked = _complete(client, seed.id)
    assert blocked.status_code == 409 and blocked.get_json()["code"] == "STEPS_INCOMPLETE"
    assert blocked.get_json()["message"] == ALL_LEFT.format(n=2)


def test_구멍_막기_한_장짜리_주문도_고른_도면이_끝나야_완료된다(client, people) -> None:
    """표시가 전부 미정이 돼도 공정 칸 규칙("한 칸도 안 켰으면 막지 않는다")으로 떨어지지 않는다. 대조군 = 같은 주문의 [완료 취소]."""
    login(client, people["lead"])
    seed = _done_seed(client, 1, people["cut"])
    assert _rework(client, seed.id, keys=[seed.keys[0]]).status_code == 200
    assert set(_states(seed).values()) == {"NONE"} and cards_used(_marks(seed.id)) == set()
    blocked = _complete(client, seed.id)
    assert blocked.status_code == 409 and blocked.get_json()["code"] == "STEPS_INCOMPLETE"
    assert blocked.get_json()["message"] == ALL_LEFT.format(n=1)

    control = _done_seed(client, 1, people["cut"])  # 대조군 — 완료 취소는 표시를 안 건드려 바로 다시 완료된다
    assert client.post(f"/api/orders/{control.id}/production/uncomplete", json={}).status_code == 200
    assert _complete(client, control.id).status_code == 200


def test_고른_도면을_다시_끝내면_제작_완료가_되고_수정_제작이_꺼진다(client, people) -> None:
    login(client, people["lead"])
    seed = _done_seed(client, 2, people["cut"])
    assert _rework(client, seed.id, keys=[seed.keys[1]]).status_code == 200
    for part in PARTS[:3]:
        assert finish(client, seed, 1, part).status_code == 200
    assert mark(client, seed, 1, "inspect", "take", "none").status_code == 200
    last = mark(client, seed, 1, "inspect", "done", "need")
    assert last.status_code == 200 and last.get_json()["data"]["order_ready"] == {"order_id": seed.id}  # "제작 완료할까요?"
    assert [step(seed.id, p)["done"] for p in PARTS] == [True] * 4
    assert _complete(client, seed.id).status_code == 200
    rework = _rework_of(seed.id)
    assert rework["active"] is False and rework["completed_at"] and rework["keys"] == [seed.keys[1]]
    assert fresh(seed.id).erp_stage_code == "CONSTRUCTION"
    assert parts_in_use(fresh(seed.id).structured_data, []) == set()  # 완료되면 규칙도 꺼진다


def test_손으로_켠_옛_칸은_안_고른_도면이_완료로_풀려_적힌다(client, people) -> None:
    login(client, people["lead"])
    seed = make_order(3, steps_done=PARTS, by_name="오반장")  # 표시 줄 0 · 공정 칸 넷을 손으로 켠 주문
    assert _complete(client, seed.id).status_code == 200
    assert _rework(client, seed.id, keys=[seed.keys[1]]).status_code == 200
    assert _states(seed) == {(j, p): "DONE" for j in (0, 2) for p in PARTS}  # 고른 도면은 줄이 없다(= 미정)
    filled = row(seed.id, seed.keys[2], "assemble")
    assert (filled.done_by_name, filled.picked_by_name) == ("오반장", None)  # 칸을 켠 사람
    expanded = [e.payload for e in events(seed.id, "PRODUCTION_PART_MARKED")]
    assert len(expanded) == 8 and {p["via"] for p in expanded} == {"step_expand"} and {p["by_name"] for p in expanded} == {"오반장"}
    assert [step(seed.id, p)["done"] for p in PARTS] == [False] * 4
    order = fresh(seed.id)
    assert {p: v["done_n"] for p, v in parts_progress(order.structured_data, _marks(seed.id)).items()} == {p: 2 for p in PARTS}
    assert _complete(client, seed.id).get_json()["message"] == ALL_LEFT.format(n=1)


def test_칸도_도면도_안_쓰고_완료된_주문은_안_고른_도면을_이름_없이_완료로_채운다(client, people) -> None:
    login(client, people["lead"])
    seed = make_order(3)  # 표시 줄 0 · 공정 칸 0 — 옛 규칙으로 제작 완료된 주문
    assert _complete(client, seed.id).status_code == 200
    assert _rework(client, seed.id, keys=[seed.keys[0]]).status_code == 200
    assert _states(seed) == {(j, p): "DONE" for j in (1, 2) for p in PARTS}
    filled = row(seed.id, seed.keys[1], "cut")
    assert (filled.done_by_name, filled.done_by_user_id, filled.picked_by_name) == (None, None, None)
    payloads = [e.payload for e in events(seed.id, "PRODUCTION_PART_MARKED")]
    assert len(payloads) == 8 and all(p["by_unknown"] is True and p["by_name"] is None for p in payloads)
    order = fresh(seed.id)
    assert {p: v["done_n"] for p, v in parts_progress(order.structured_data, _marks(seed.id)).items()} == {p: 2 for p in PARTS}
    assert _complete(client, seed.id).get_json()["message"] == ALL_LEFT.format(n=1)


def test_표시_줄이_하나도_없는_주문도_고르면_된다(client, people) -> None:
    """칸도 도면도 안 쓴 한 장짜리 주문 — 고른 뒤에도 표시 줄이 0 이다. 네 파트를 도면으로 보는 규칙이 줄 없는 파트에서 죽지 않는다
    (공정 칸 동기화 ``part_steps_after`` — 도면 전달이 같은 함수를 부른다)."""
    login(client, people["lead"])
    seed = make_order(1)
    assert _complete(client, seed.id).status_code == 200
    assert _rework(client, seed.id, keys=[seed.keys[0]]).status_code == 200
    assert _marks(seed.id) == [] and _rework_of(seed.id)["keys"] == [seed.keys[0]]
    assert _complete(client, seed.id).get_json()["message"] == ALL_LEFT.format(n=1)
    sd = copy.deepcopy(fresh(seed.id).structured_data)
    sd["production"]["steps"][0]["done"] = True  # 켜진 칸이 남아 있어도 도면이 기준 — 줄이 없으면 끈다
    assert [(c.key, c.done) for c in plan_part_step_changes(sd, [])] == [("cut", False)]


def test_고른_도면_시작_취소가_제작_시작을_되돌리지_않는다(client, people) -> None:
    login(client, people["lead"])
    seed = _done_seed(client, 1, people["cut"])
    assert _rework(client, seed.id, keys=[seed.keys[0]]).status_code == 200
    assert mark(client, seed, 0, "cut", "take", "none").status_code == 200
    released = mark(client, seed, 0, "cut", "release", "need")
    assert released.status_code == 200 and released.get_json()["data"]["run_cancelled"] is False
    assert current_runs(seed.id) == 1 and _rework_of(seed.id)["active"] is True


def test_쓰기_문_수는_고른_장_수와_무관하다(client, people) -> None:
    login(client, people["lead"])

    def count(n_pick: int) -> int:
        seed = _done_seed(client, 4, people["cut"], steps_done=PARTS)
        seen = {"n": 0}

        def _before(conn, cursor, statement, params, context, executemany):
            seen["n"] += 1

        event.listen(engine, "before_cursor_execute", _before)
        try:
            assert _rework(client, seed.id, keys=list(seed.keys[:n_pick])).status_code == 200
        finally:
            event.remove(engine, "before_cursor_execute", _before)
        return seen["n"]

    count(1)  # 데우기
    assert count(1) == count(3)


# --------------------------------------------------------------------------- #
# 2. 거절 — 안 고름 · 옛 도면 · 남의 공장. 아무것도 안 바뀐다
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("body", [{}, {"reason": "옛 화면"}, {"keys": []}, {"keys": "d0.png"}, {"keys": None}, {"steps": ["cut"]}])
def test_도면을_안_고른_수정_제작은_400이고_아무것도_안_바뀐다(client, people, body) -> None:
    login(client, people["lead"])
    seed = _done_seed(client, 2, people["cut"])
    before = _snapshot(seed.id)
    resp = _rework(client, seed.id, **body)
    assert resp.status_code == 400, resp.get_json()
    assert resp.get_json() == {"success": False, "code": "REWORK_PICK_REQUIRED", "message": PICK_DRAWINGS_MESSAGE}
    assert _snapshot(seed.id) == before


def test_옛_도면_남의_공장_도면은_거절이고_보류_풀기도_같이_되감긴다(client, people) -> None:
    login(client, people["admin"])
    seed = mixed_order(3, f2=(2,))
    _all_done(seed, people["cut"])
    assert _complete(client, seed.id).status_code == 200
    patch_sd(seed.id, hold={"active": True, "reason": "자재 기다림", "at": None, "by_name": "박반장"})
    before = _snapshot(seed.id)

    login(client, people["lead"])  # 1공장 반장
    stale = _rework(client, seed.id, keys=[seed.keys[0], "c0/옛도면.png"], release_hold=True)
    assert stale.status_code == 409
    assert stale.get_json() == {"success": False, "code": "DRAWING_NOT_CURRENT", "message": NOT_CURRENT_MESSAGE}
    other = _rework(client, seed.id, keys=[seed.keys[0], seed.keys[2]], release_hold=True)
    assert other.status_code == 403
    assert other.get_json() == {"success": False, "code": "OTHER_FACTORY",
                                "message": "2공장에서 작업하는 도면이에요. [다시 받기]를 눌러 주세요."}
    assert _snapshot(seed.id) == before  # 보류 그대로 · 풀림 이벤트 없음
    held = _rework(client, seed.id, keys=[seed.keys[0]])  # 지금 문이 먼저 — 보류
    assert held.status_code == 409 and held.get_json()["code"] == "HOLD_ACTIVE"
    assert _snapshot(seed.id) == before


# --------------------------------------------------------------------------- #
# 3. 공장 둘 주문 — 고른 도면이 있는 공장 표지만 지운다
# --------------------------------------------------------------------------- #
def test_한_공장_도면만_고르면_다른_공장_완료는_그대로다(client, people) -> None:
    login(client, people["admin"])
    seed = mixed_order(3, f2=(2,))
    _all_done(seed, people["cut"])
    assert _complete(client, seed.id).status_code == 200
    assert set(fresh(seed.id).structured_data["production"]["factory_done"]) == {"1", "2"}

    login(client, people["lead"])  # 1공장 반장이 자기 공장 도면만 고른다
    assert _rework(client, seed.id, keys=[seed.keys[1]]).status_code == 200
    sd = fresh(seed.id).structured_data
    assert set(sd["production"]["factory_done"]) == {"2"}
    assert factory_done_entry(sd, 2) is not None and factory_done_entry(sd, 1) is None
    assert events(seed.id, "PRODUCTION_REWORK_STARTED")[-1].payload["numbers"] == [2]
    for part in PARTS:
        assert finish(client, seed, 1, part).status_code == 200
    final = client.post(f"/api/orders/{seed.id}/production/factory-done", json={"factory": 1, "done": True})
    assert final.status_code == 200 and final.get_json()["data"]["final"] is True  # 2공장은 또 누르지 않는다
    assert fresh(seed.id).erp_stage_code == "CONSTRUCTION"


# --------------------------------------------------------------------------- #
# 4. 도면이 없는 주문 — 다시 할 칸 고르기
# --------------------------------------------------------------------------- #
def _no_drawing_done(client, **kwargs):
    seed = make_order(0, **kwargs)
    assert _complete(client, seed.id).status_code == 200
    return seed


def test_고른_칸만_꺼지고_다시_켜야_완료된다(client, people) -> None:
    login(client, people["lead"])
    seed = _no_drawing_done(client, steps_done=PARTS, by_name="오반장")
    resp = _rework(client, seed.id, reason="조립 다시", steps=["inspect", "assemble"], keys=["안 읽는 값"])
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["message"] == "수정 제작을 시작했어요. 조립 · 검수를 다시 해요."
    assert [(step(seed.id, p)["done"], step(seed.id, p)["by_name"]) for p in PARTS] == [
        (True, "오반장"), (True, "오반장"), (False, None), (False, None)]
    rework = _rework_of(seed.id)
    assert rework["steps"] == ["assemble", "inspect"] and "keys" not in rework and rework["active"] is True
    offs = [e.payload for e in events(seed.id, "PRODUCTION_STEP_CHECKED")]
    assert [(p["key"], p["done"], p["via"], p["trigger"], p["by_name"]) for p in offs] == [
        ("assemble", False, "rework", "rework", "박반장"), ("inspect", False, "rework", "rework", "박반장")]
    assert events(seed.id, "PRODUCTION_REWORK_STARTED")[-1].payload["steps"] == ["assemble", "inspect"]
    assert _marks(seed.id) == []

    blocked = _complete(client, seed.id)
    assert blocked.status_code == 409 and blocked.get_json()["code"] == "STEPS_INCOMPLETE"
    assert blocked.get_json()["message"].endswith("(남은 공정: 조립 · 검수)")
    assert check_step(client, seed.id, "assemble", True).status_code == 200
    assert _complete(client, seed.id).status_code == 409
    assert check_step(client, seed.id, "inspect", True).status_code == 200
    assert _complete(client, seed.id).status_code == 200
    assert _rework_of(seed.id)["active"] is False


def test_칸을_한_번도_안_쓴_주문은_안_고른_칸을_이름_없이_켠다(client, people) -> None:
    login(client, people["lead"])
    seed = _no_drawing_done(client)  # 칸 넷이 모두 꺼진 채 완료
    assert _rework(client, seed.id, steps=["assemble"]).status_code == 200
    cells = {p: step(seed.id, p) for p in PARTS}
    assert {p: c["done"] for p, c in cells.items()} == {"cut": True, "edge": True, "assemble": False, "inspect": True}
    for part in ("cut", "edge", "inspect"):  # 사람이 누른 완료와 가린다
        assert (cells[part]["via"], cells[part]["by_name"]) == ("rework", None) and cells[part]["at"]
    filled = [e.payload for e in events(seed.id, "PRODUCTION_STEP_CHECKED")]
    assert [(p["key"], p["done"], p["via"]) for p in filled] == [("cut", True, "rework"), ("edge", True, "rework"), ("inspect", True, "rework")]
    assert all(p["by_unknown"] is True and "by_name" not in p for p in filled)
    assert _complete(client, seed.id).status_code == 409
    assert check_step(client, seed.id, "assemble", True).status_code == 200
    assert _complete(client, seed.id).status_code == 200


def test_넷을_다_고르면_넷을_다시_완료해야_한다(client, people) -> None:
    """넷이 다 꺼진 주문은 "한 칸도 안 켰으면 막지 않는다"에 걸리는데, 수정 제작 중에는 그 예외를 쓰지 않는다. 대조군 = 수정 제작이 아닌 주문."""
    login(client, people["lead"])
    seed = _no_drawing_done(client, steps_done=PARTS)
    assert _rework(client, seed.id, steps=list(PARTS)).status_code == 200
    assert [step(seed.id, p)["done"] for p in PARTS] == [False] * 4
    blocked = _complete(client, seed.id)
    assert blocked.status_code == 409 and blocked.get_json()["message"].endswith("(남은 공정: 재단 · 엣지 · 조립 · 검수)")
    for part in PARTS:
        assert check_step(client, seed.id, part, True).status_code == 200
    assert _complete(client, seed.id).status_code == 200

    control = make_order(0)  # 대조군 — 수정 제작 중이 아니면 넷이 다 꺼져 있어도 지금처럼 완료된다
    assert _complete(client, control.id).status_code == 200


@pytest.mark.parametrize("body,code,message", [
    ({}, "REWORK_PICK_REQUIRED", PICK_STEPS_MESSAGE),
    ({"steps": []}, "REWORK_PICK_REQUIRED", PICK_STEPS_MESSAGE),
    ({"keys": ["d0.png"]}, "REWORK_PICK_REQUIRED", PICK_STEPS_MESSAGE),
    ({"steps": ["cut", "paint"]}, "BAD_REQUEST", BAD_STEP_MESSAGE),
    ({"steps": [1]}, "BAD_REQUEST", BAD_STEP_MESSAGE),
])
def test_칸을_안_고르거나_모르는_칸이면_400이고_아무것도_안_바뀐다(client, people, body, code, message) -> None:
    login(client, people["lead"])
    seed = _no_drawing_done(client, steps_done=PARTS)
    before = _snapshot(seed.id)
    resp = _rework(client, seed.id, **body)
    assert resp.status_code == 400 and resp.get_json() == {"success": False, "code": code, "message": message}
    assert _snapshot(seed.id) == before


# --------------------------------------------------------------------------- #
# 5. 판정 함수 — 옛 기록은 그대로 · 고른 것이 있을 때만 새 규칙
# --------------------------------------------------------------------------- #
def test_옛_수정_제작_기록은_지금_판정_그대로다() -> None:
    def sd(rework=None, on=()):
        steps = [{"key": p, "done": p in on} for p in PARTS]
        return {"production": {"steps": steps, **({"rework": rework} if rework is not None else {})}}

    used = [SimpleNamespace(drawing_key="k1", part="cut", state="DONE")]
    for rework in (None, {"active": True, "count": 1}, {"active": True, "keys": []}, {"active": True, "keys": "k1"},
                   {"active": False, "keys": ["k1"]}, {"active": True, "steps": ["cut"]}):
        assert parts_in_use(sd(rework), used) == cards_used(used) == {"cut"}, rework
        assert parts_in_use(sd(rework), []) == set(), rework
    assert parts_in_use(sd({"active": True, "keys": ["k1"]}), []) == set(PARTS)
    assert rework_pick(sd({"active": True, "keys": ["k1", "", 3, "k2"]}), "keys") == ["k1", "k2"]
    assert rework_pick(sd({"active": True, "keys": ["k1"]}), "steps") == [] and rework_pick(None, "keys") == []

    for rework in (None, {"active": True, "count": 2}, {"active": False, "steps": ["cut"]}, {"active": True, "keys": ["k1"]}):
        assert production_steps_missing(sd(rework)) == [], rework  # 넷이 다 꺼진 옛 주문 = 막지 않는다
    strict = production_steps_missing(sd({"active": True, "steps": ["cut"]}))
    assert [m["key"] for m in strict] == list(PARTS)
    assert [m["key"] for m in production_steps_missing(sd({"active": True, "steps": ["cut"]}, on=("edge", "assemble", "inspect")))] == ["cut"]


def test_끝난_뒤_알림_글은_낱말_받침에_맞는다() -> None:
    assert ReworkPick(steps=("cut",)).message() == "수정 제작을 시작했어요. 재단을 다시 해요."
    assert ReworkPick(steps=("cut", "edge")).message() == "수정 제작을 시작했어요. 재단 · 엣지를 다시 해요."
    assert ReworkPick(steps=PARTS).message() == "수정 제작을 시작했어요. 재단 · 엣지 · 조립 · 검수를 다시 해요."
    assert ReworkPick(entries=({"key": "k"},), numbers=(1,), factories=(1,)).message() == "수정 제작을 시작했어요. 도면 1장을 다시 만들어요."
