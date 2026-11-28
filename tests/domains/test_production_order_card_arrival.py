"""'도면 없음' 카드로 일한 뒤 도면이 **처음** 올라올 때 — 한 번 옮기기(설계서 2026-11-28-production-my-steps-flow §3-5 '만드는 꼴' ·
사장님 답 27 "완료 그대로 둠" · 33 "새 도면 2장도 김재단 작업 중" · 35 "손으로 끝낸 것도 똑같이 완료 그대로").

생산 단계 바로 반영 전달(``transfer-drawing``)이 0장 → n장으로 바꾸는 같은 tx 에서 미정이 아닌 ``@order`` 줄 · 손 체크 파트를 새 도면 key 마다
같은 파트 줄로 넣고 ``@order`` 줄은 미정으로 돌린다. 되돌리면 실패: 끝낸 재단이 도면이 오자 미완료 · 칸 꺼짐 · 작업 중이던 사람의 내 공정에 새
도면이 없음 · 손 체크 칸이 꺼짐 · 안 건드린 파트에 줄이 생김 · 이벤트 표지 없음 · ``@order`` 작업 중 줄이 남아 한 장 더 셈 · 그 뒤 도면이 다시
바뀌어도 완료로 번짐. 이름은 모두 지어낸 값이다(김재단 · 오재단 · 박엣지 · 최조립 · 박반장 · 김도면).
"""
from __future__ import annotations

from db import db_session
from foms.services.production.order_card_carry import VIA_ORDER_CARD
from models import ProductionPartMark, User
from tests.domains.test_production_flow_read import _cards, my_steps_of
from tests.support.drawing_fix_transfer_seed import key, login as dfx_login, make_order, marks, quiet, send, team  # noqa: F401
from tests.support.production_part_claim_seed import check_step, events, login, make_user, step

ORDER = "@order"


def _press(client, who, oid: int, part: str, action: str, seen: str, **extra) -> dict:
    login(client, who)
    resp = client.post("/api/production/part-marks",
                       json={"order_id": oid, "drawing_key": ORDER, "part": part, "action": action, "seen": seen, **extra})
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["data"]


def _arrive(client, team, oid: int, sheets: tuple[str, ...] = ("s0", "s1")) -> list[str]:
    dfx_login(client, team.drawer)
    resp = send(client, "drawing", oid, *sheets)
    assert resp.status_code == 200, resp.get_json()
    return [key(oid, f"{s}-v2") for s in sheets]


def _carry_events(oid: int) -> list[dict]:
    return [e.payload for e in events(oid, "PRODUCTION_PART_MARKED") if e.payload.get("via") == VIA_ORDER_CARD]


def test_done_order_card_stays_done_on_every_new_drawing(client, quiet, team):
    oid = make_order(0)
    kim = make_user("김재단", part="cut")
    _press(client, kim, oid, "cut", "take", "none")
    _press(client, kim, oid, "cut", "done", "need")
    assert step(oid, "cut")["done"] is True
    new = _arrive(client, team, oid)
    rows = marks(oid)
    assert [(rows[(k, "cut")].state, rows[(k, "cut")].done_by_name, rows[(k, "cut")].done_by_user_id) for k in new] == \
        [("DONE", "김재단", kim.id)] * 2
    assert rows[(new[0], "cut")].sheet_id == "s0" and rows[(new[1], "cut")].sheet_id == "s1"
    assert rows[(ORDER, "cut")].state == "NONE"  # 옮긴 @order 줄은 미정(기록으로 남김)
    cut = step(oid, "cut")
    assert cut["done"] is True and cut["by_name"] == "김재단"  # 뒤 공정 칸 맞추기가 돌아도 켜진 채(27번 답)
    copies = [p for p in _carry_events(oid) if p["action"] == "done"]
    assert [(p["key"], p["part"], p["from"], p["to"], p["by_name"]) for p in copies] == [
        (new[0], "cut", "NONE", "DONE", "김재단"), (new[1], "cut", "NONE", "DONE", "김재단")]
    cleared = [p for p in _carry_events(oid) if p["action"] == "order_card"]
    assert [(p["key"], p["from"], p["to"], p["to_keys"]) for p in cleared] == [(ORDER, "DONE", "NONE", new)]


def test_working_order_card_becomes_that_person_working_on_every_new_drawing(client, quiet, team):
    oid = make_order(0)
    kim, oh = make_user("김재단", part="cut"), make_user("오재단", part="cut")
    _press(client, kim, oid, "cut", "take", "none")
    _press(client, oh, oid, "cut", "join", "need")
    new = _arrive(client, team, oid)
    rows = marks(oid)
    for k in new:
        assert rows[(k, "cut")].state == "NEED" and [m["uid"] for m in rows[(k, "cut")].holders] == [kim.id, oh.id]
    assert rows[(ORDER, "cut")].state == "NONE" and step(oid, "cut")["done"] is False
    mine = _cards(my_steps_of(db_session.get(User, kim.id)))
    assert [(c["key"], c["order_card"]) for c in mine] == [(new[0], False), (new[1], False)]  # 33번 답 — 새 도면 2장이 내 공정에
    # '작업 중 장 수'(공장을 바꾼 사람 안내 등)에 @order 가 한 장 더 안 든다 — NEED 줄은 새 key 둘뿐
    db_session.expire_all()
    held = db_session.query(ProductionPartMark).filter_by(order_id=oid, state="NEED").all()
    assert sorted(m.drawing_key for m in held) == sorted(new)


def test_hand_checked_part_is_written_done_on_new_drawings_and_untouched_parts_stay_open(client, quiet, team):
    oid = make_order(0)
    lead, edge = make_user("박반장", lead=True), make_user("박엣지", part="edge")
    login(client, lead)
    assert check_step(client, oid, "assemble", True).status_code == 200  # 손 체크(35번 답)
    _press(client, edge, oid, "edge", "take", "none")
    _press(client, edge, oid, "edge", "release", "need")  # 맡았다 취소 — 미정 @order 줄은 옮기지 않는다
    new = _arrive(client, team, oid)
    rows = marks(oid)
    assert [(rows[(k, "assemble")].state, rows[(k, "assemble")].done_by_name) for k in new] == [("DONE", "박반장")] * 2
    assert step(oid, "assemble")["done"] is True  # 지금 코드는 여기서 칸을 껐다(expand_hand_parts — 모든 장이 새 장)
    assert not any((k, "edge") in rows for k in new) and not any((k, "cut") in rows for k in new)  # 미정 파트 = 새 도면 미정
    assert step(oid, "edge")["done"] is False and step(oid, "cut")["done"] is False


def test_drawings_changing_again_follow_the_usual_rule(client, quiet, team):
    """옮긴 뒤 그 도면이 다시 바뀌면(key1 → key1′) 지금 규칙 그대로 — 새 장 미정 · 칸 꺼짐(옮기기는 처음 올 때 한 번)."""
    oid = make_order(0)
    kim = make_user("김재단", part="cut")
    _press(client, kim, oid, "cut", "take", "none")
    _press(client, kim, oid, "cut", "done", "need")
    new = _arrive(client, team, oid)
    dfx_login(client, team.drawer)
    files = [{"key": key(oid, "s0-v3"), "filename": "s0-v3.png", "sheet_id": "s0"}]
    resp = client.post(f"/api/orders/{oid}/transfer-drawing",
                       json={"note": "상판 깊이 600 → 580", "files": files, "mode": "APPEND", "ack_worked": ["sheet:s0"]})
    assert resp.status_code == 200, resp.get_json()
    rows = marks(oid)
    assert (key(oid, "s0-v3"), "cut") not in rows and rows[(new[1], "cut")].state == "DONE"
    assert step(oid, "cut")["done"] is False
    assert len([p for p in _carry_events(oid) if p["action"] == "done"]) == 2  # 두 번째 전달은 옮기지 않았다


def test_first_drawings_on_an_order_without_order_card_rows_change_nothing_new(client, quiet, team):
    """대조군 — @order 줄도 손 체크도 없는 0장 주문은 지금 그대로(새 줄 0 · 이벤트 0)."""
    oid = make_order(0)
    _arrive(client, team, oid)
    assert [k for k in marks(oid)] == [] and _carry_events(oid) == []
