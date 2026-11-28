"""'도면 없음' 주문 카드(key ``@order``) — 쓰기 문 · 공정 칸 맞추기 · 진행 · 제작 완료 판정 · 수정 제작(설계서
2026-11-28-production-my-steps-flow §3-5 · 사장님 답 11).

확정 도면이 0장인 생산 단계 주문은 표시 줄 key ``@order`` 한 장으로 담고 끝낸다. 되돌리면 실패: 0장 주문 ``@order`` 가 409 · 1장 이상 주문이
``@order`` 를 받음 · 끝내도 공정 칸이 안 켜짐(이름 없음) · 완료 취소 뒤 칸이 켜진 채 남아 ``STEP_SET_BY_HAND`` 로 잠김 · ``@order`` 줄 하나 때문에
네 공정을 모두 카드로 요구 · 막힘 글 "도면이 없어요" · 일괄 기본에 ``@order`` 가 듦 · 수정 제작 뒤 ``@order`` 완료 줄이 남아 곧바로 완료 ·
생산 밖에서 도면을 받고 다시 생산에 들어와도 카드 일이 새 도면에 안 옮겨짐(ⓑ 검토 2 — 사장님 "고침").
이름은 모두 지어낸 값이다(김재단 · 오재단 · 박엣지 · 최조립 · 한검수 · 박반장).
"""
from __future__ import annotations

import pytest

from db import db_session
from foms.services.production.part_mark_gates import ORDER_CARD_DONE_MESSAGE, ORDER_CARD_LEFT_MESSAGE
from foms.services.production.part_progress import complete_block_body, complete_state, part_progress
from foms.services.production.part_marks_query import order_marks
from models import Order, User
from tests.domains.test_production_flow_read import _cards, my_steps_of
from tests.support.drawing_fix_transfer_seed import key as dfx_key, login as dfx_login, make_order as dfx_order, quiet, send, team  # noqa: F401
from tests.support.production_factory_seed import factory_user
from tests.support.production_part_claim_seed import (
    BULK,
    Seed,
    check_step,
    code,
    events,
    fresh,
    login,
    make_order,
    make_user,
    mark,
    patch_sd,
    row,
    step,
)

KEY = "@order"
PARTS = ("cut", "edge", "assemble", "inspect")


def _card(n_done: tuple[str, ...] = (), *, run: bool = True) -> Seed:
    """도면 0장 생산 단계 주문(주문 카드 하나 — key @order)."""
    seed = make_order(0, steps_done=n_done, run=run)
    return Seed(seed.id, (KEY,))


@pytest.fixture
def people():
    return {"kim": make_user("김재단", part="cut"), "oh": make_user("오재단", part="cut"), "edge": make_user("박엣지", part="edge"),
            "asm": make_user("최조립", part="assemble"), "insp": make_user("한검수", part="inspect"),
            "lead": make_user("박반장", lead=True)}


def _press(client, who, order: Seed, part: str, action: str, seen: str, **extra):
    login(client, who)
    return mark(client, order, 0, part, action, seen, **extra)


def _ok(resp):
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["data"]


def _finish(client, who, order: Seed, part: str):
    _ok(_press(client, who, order, part, "take", "none"))
    return _ok(_press(client, who, order, part, "done", "need"))


# --------------------------------------------------------------------------- #
# 1. 쓰기 문
# --------------------------------------------------------------------------- #
def test_order_key_is_accepted_only_while_the_order_has_no_drawings(client, people):
    card = _card()
    data = _ok(_press(client, people["kim"], card, "cut", "take", "none"))
    assert data["mark"]["drawing_key"] == KEY and data["mark"]["state"] == "need" and data["run_started"] is False
    drawn = make_order(1)  # 대조군 — 도면 1장 주문의 @order 는 지금처럼 409
    refused = _press(client, people["kim"], Seed(drawn.id, (KEY,)), "cut", "take", "none")
    assert refused.status_code == 409 and code(refused) == "DRAWING_NOT_CURRENT"
    assert row(drawn.id, KEY, "cut") is None


def test_first_order_card_starts_production_like_a_drawing_card(client, people):
    card = _card(run=False)
    data = _ok(_press(client, people["kim"], card, "cut", "take", "none"))
    assert data["run_started"] is True  # 첫 카드 = 제작 시작(§4-8) — 주문 카드도 같다


def test_nine_actions_round_trip_on_the_order_card(client, people):
    """파트 직원 take → release · take → done / 둘이 같이(join) · 반장 takeover · check · undo · remove · 재단 기본(basic)."""
    kim, oh, lead = people["kim"], people["oh"], people["lead"]
    card = _card()
    _ok(_press(client, kim, card, "cut", "take", "none"))
    assert _ok(_press(client, kim, card, "cut", "release", "need"))["mark"]["state"] == "none"
    _ok(_press(client, kim, card, "cut", "take", "none"))
    joined = _ok(_press(client, oh, card, "cut", "join", "need"))
    assert joined["mark"]["holder_n"] == 2
    _ok(_press(client, kim, card, "cut", "done", "need"))
    assert step(card.id, "cut")["done"] is False  # 오재단이 아직 — "재단 1/2 완료"
    _ok(_press(client, lead, card, "cut", "remove", "need", target_user_id=oh.id))  # 반장이 오재단 몫을 뺌 → 남은 몫이 모두 완료
    assert row(card.id, KEY, "cut").state == "DONE" and step(card.id, "cut")["done"] is True
    assert _ok(_press(client, lead, card, "cut", "undo", "done"))["mark"]["state"] in ("none", "need")
    assert step(card.id, "cut")["done"] is False
    # 반장 대신 시작(담당 바꾸기 — 받는 사람 = 김재단) · 대신 완료(check)
    edge = people["edge"]
    _ok(_press(client, edge, card, "edge", "take", "none"))
    given = _ok(_press(client, lead, card, "edge", "takeover", "need", seen_by=edge.id, to_user_id=make_user("오엣지", part="edge").id))
    assert given["mark"]["state"] == "need" and given["mark"]["picked_by_name"] == "오엣지"  # 반장이 남에게 줌
    checked = _ok(_press(client, lead, card, "edge", "check", "need"))
    assert checked["mark"]["state"] == "done" and step(card.id, "edge")["done"] is True
    # 재단 [기본]은 주문 카드에도 있다(설계서 §3-5) — 기본 = 완료로 셈, 칸 켜짐
    other = _card()
    _ok(_press(client, kim, other, "cut", "basic", "none"))
    assert row(other.id, KEY, "cut").state == "BASIC" and step(other.id, "cut")["done"] is True


def test_inspect_order_card_needs_the_three_parts_first(client, people):
    card = _card()
    refused = _press(client, people["insp"], card, "inspect", "take", "none")
    assert refused.status_code == 409 and code(refused) == "INSPECT_NOT_READY"
    _finish(client, people["kim"], card, "cut")
    _finish(client, people["edge"], card, "edge")
    login(client, people["lead"])
    assert check_step(client, card.id, "assemble", True).status_code == 200  # 조립은 손 체크(카드 안 씀) — 섞여도 된다
    assert _press(client, people["insp"], card, "inspect", "take", "none").status_code == 200


def test_hold_blocks_order_card_but_release_still_works(client, people):
    card = _card()
    _ok(_press(client, people["kim"], card, "cut", "take", "none"))
    patch_sd(card.id, hold={"active": True, "reason": "자재 기다림"})
    blocked = _press(client, people["oh"], card, "cut", "join", "need")
    assert blocked.status_code == 409 and code(blocked) == "HOLD_ACTIVE"
    assert _press(client, people["kim"], card, "cut", "release", "need").status_code == 200


def test_part_permission_still_applies(client, people):
    refused = _press(client, people["edge"], _card(), "cut", "take", "none")
    assert refused.status_code == 403


def test_second_factory_part_account_is_refused_by_the_factory_door(client):
    """주문 카드는 1공장 장 — 2공장 파트 계정은 지금 공장 문 그대로 403 OTHER_FACTORY."""
    f2 = factory_user("김재단", factory=2, part="cut")
    resp = _press(client, f2, _card(), "cut", "take", "none")
    assert resp.status_code == 403 and code(resp) == "OTHER_FACTORY"
    assert resp.get_json()["error"] == "1공장에서 작업하는 도면이에요. [다시 받기]를 눌러 주세요."


def test_bulk_basic_never_takes_the_order_card(client, people):
    card = _card()
    login(client, people["kim"])
    resp = client.post(BULK, json={"part": "cut", "seen": "none", "items": [{"order_id": card.id, "drawing_key": KEY}]})
    data = _ok(resp)
    assert data["applied"] == [] and [s["reason"] for s in data["skipped"]] == ["DRAWING_NOT_CURRENT"]
    assert row(card.id, KEY, "cut") is None


# --------------------------------------------------------------------------- #
# 2. 공정 칸 맞추기 · 반장 손 체크와의 맞물림
# --------------------------------------------------------------------------- #
def test_finishing_turns_the_step_on_with_the_finisher_and_undo_turns_it_off(client, people):
    card = _card()
    data = _finish(client, people["kim"], card, "cut")
    assert data["order_step"] == {"order_id": card.id, "key": "cut", "done": True}
    cut = step(card.id, "cut")
    assert cut["done"] is True and cut["by_name"] == "김재단" and cut["via"] == "part_marks"
    _ok(_press(client, people["lead"], card, "cut", "undo", "done"))  # 반장 완료 취소 → 미정
    assert step(card.id, "cut")["done"] is False
    # 칸이 켜진 채 남아 손 체크 칸으로 잠기지 않는다(조사 위험 1) — 다시 담을 수 있다
    assert _press(client, people["kim"], card, "cut", "take", "none").status_code == 200


def test_start_cancel_after_done_cancel_leaves_no_stale_step(client, people):
    card = _card()
    _finish(client, people["kim"], card, "cut")
    _ok(_press(client, people["lead"], card, "cut", "undo", "done"))
    _ok(_press(client, people["kim"], card, "cut", "take", "none"))
    _ok(_press(client, people["kim"], card, "cut", "release", "need"))
    assert step(card.id, "cut")["done"] is False and row(card.id, KEY, "cut").state == "NONE"


def test_hand_check_without_order_rows_is_unchanged(client, people):
    card = _card()
    login(client, people["lead"])
    assert check_step(client, card.id, "cut", True).status_code == 200  # @order 줄 없음 = 지금 그대로
    assert check_step(client, card.id, "cut", False).status_code == 200


def test_hand_check_on_is_refused_while_the_order_card_is_in_work(client, people):
    card = _card()
    _ok(_press(client, people["kim"], card, "cut", "take", "none"))
    login(client, people["lead"])
    resp = check_step(client, card.id, "cut", True)
    assert resp.status_code == 409 and code(resp) == "PART_USES_CARDS"
    assert resp.get_json()["error"] == ORDER_CARD_LEFT_MESSAGE == "도면 없음 1장이 미완료예요. 그 장을 완료하면 자동으로 작업 완료 처리돼요."
    assert resp.get_json()["data"]["left"] == 1 and resp.get_json()["data"]["total"] == 1
    assert check_step(client, card.id, "edge", True).status_code == 200  # @order 를 안 쓴 파트는 손 체크 그대로


def test_hand_check_off_is_refused_when_the_order_card_finished_it(client, people):
    card = _card()
    _finish(client, people["kim"], card, "cut")
    login(client, people["lead"])
    resp = check_step(client, card.id, "cut", False)
    assert resp.status_code == 409 and code(resp) == "STEP_SET_BY_CARDS"
    assert resp.get_json()["error"] == ORDER_CARD_DONE_MESSAGE.format(label="재단")
    assert step(card.id, "cut")["done"] is True


def test_order_card_on_a_hand_checked_part_is_refused(client, people):
    card = _card()
    login(client, people["lead"])
    assert check_step(client, card.id, "cut", True).status_code == 200
    resp = _press(client, people["kim"], card, "cut", "take", "none")
    assert resp.status_code == 409 and code(resp) == "STEP_SET_BY_HAND"
    assert row(card.id, KEY, "cut") is None


# --------------------------------------------------------------------------- #
# 3. 진행 · 제작 완료 판정
# --------------------------------------------------------------------------- #
def _state(oid: int):
    order = fresh(oid)
    return order.structured_data, order_marks(db_session, oid)


def test_progress_counts_the_order_card_as_one_sheet_and_others_stay_on_steps(client, people):
    card = _card()
    _finish(client, people["kim"], card, "cut")
    sd, marks = _state(card.id)
    cut = part_progress(sd, marks, "cut")
    assert (cut["uses_cards"], cut["done"], cut["done_n"], cut["total_n"]) == (True, True, 1, 1)
    edge = part_progress(sd, marks, "edge")
    assert (edge["uses_cards"], edge["done"], edge["left_keys"]) == (False, False, [KEY])  # 공정 칸이 기준(꺼짐)
    body = complete_block_body(sd, marks)
    assert body["message"] == "미완료가 있어요 — 엣지 1장 · 조립 1장 · 검수 1장"  # "도면이 없어요 — …" 가 아니다
    assert body["left"] == {"edge": 1, "assemble": 1, "inspect": 1}


def test_all_four_parts_on_order_card_ask_to_finish_production(client, people):
    card = _card()
    for who, part in ((people["kim"], "cut"), (people["edge"], "edge"), (people["asm"], "assemble")):
        _finish(client, who, card, part)
    data = _finish(client, people["insp"], card, "inspect")
    assert data["order_ready"] == {"order_id": card.id}  # "제작 완료할까요?"
    sd, marks = _state(card.id)
    assert complete_state(sd, marks)["ready"] is True and all(step(card.id, p)["done"] for p in PARTS)


def test_cut_by_order_card_and_the_rest_by_hand_also_completes(client, people):
    card = _card()
    _finish(client, people["kim"], card, "cut")
    login(client, people["lead"])
    for part in ("edge", "assemble", "inspect"):
        assert check_step(client, card.id, part, True).status_code == 200
    sd, marks = _state(card.id)
    assert complete_state(sd, marks)["ready"] is True and complete_block_body(sd, marks) is None


def test_released_order_card_does_not_turn_the_order_into_a_card_order(client, people):
    """맡았다 취소해 @order 줄이 미정만 남으면 카드를 안 쓴 주문 — 칸 규칙 그대로(칸을 하나도 안 켰으면 막지 않음)."""
    card = _card()
    _ok(_press(client, people["kim"], card, "cut", "take", "none"))
    _ok(_press(client, people["kim"], card, "cut", "release", "need"))
    sd, marks = _state(card.id)
    assert complete_state(sd, marks)["uses_cards"] is False and complete_block_body(sd, marks) is None


# --------------------------------------------------------------------------- #
# 4. 수정 제작(도면 0장 주문 = 공정 고르기)
# --------------------------------------------------------------------------- #
def test_rework_pick_resets_the_picked_order_card_row(client, people):
    from tests.domains.test_production_rework_pick_1128 import _complete, _rework  # noqa: PLC0415

    card = _card()
    for who, part in ((people["kim"], "cut"), (people["edge"], "edge"), (people["asm"], "assemble"), (people["insp"], "inspect")):
        _finish(client, who, card, part)
    login(client, people["lead"])
    assert _complete(client, card.id).status_code == 200
    assert _rework(client, card.id, steps=["cut"]).status_code == 200
    assert row(card.id, KEY, "cut").state == "NONE" and row(card.id, KEY, "edge").state == "DONE"
    assert step(card.id, "cut")["done"] is False and step(card.id, "edge")["done"] is True
    sd, marks = _state(card.id)
    assert part_progress(sd, marks, "cut")["done"] is False  # 곧바로 완료로 읽히지 않는다(조사 위험 3)
    rework = [e.payload for e in events(card.id, "PRODUCTION_PART_MARKED") if e.payload.get("action") == "rework"]
    assert [(p["key"], p["part"], p["from"], p["to"]) for p in rework] == [(KEY, "cut", "DONE", "NONE")]
    assert _press(client, people["kim"], card, "cut", "take", "none").status_code == 200  # 다시 담는다


def _override(client, admin, oid: int, to_stage: str):
    login(client, admin)
    resp = client.post(f"/api/orders/{oid}/workflow/stage-override", json={"to_stage": to_stage, "reason": "시험 되돌림", "confirm": True})
    assert resp.status_code == 200, resp.get_json()


def test_order_card_work_moves_to_drawings_that_came_while_outside_production(client, people, quiet, team):
    """사장님 답 2026-11-28 "고침"(ⓑ 검토 2) — 생산 → 앞 단계로 강제 되돌림 → 도면 받음(바로 반영 단계가 아니라 전달은 안 옮김) → 다시
    생산: 생산으로 들어가는 쓰기(강제 단계 변경)에서 한 번 옮긴다. 재단 칸 켜진 채 · 진행 완료 · 박엣지 작업 중이 새 도면 '내 공정'에.

    되돌리면 실패(옛 꼴): 재단 진행 0/2 · 새 도면 미정 · 박엣지 작업 중은 @order 줄에만 남음.
    """
    oid = dfx_order(0, assignees=(team.drawer.id,))
    card = Seed(oid, (KEY,))
    _finish(client, people["kim"], card, "cut")
    _ok(_press(client, people["edge"], card, "edge", "take", "none"))
    admin = make_user("관리", team="CS", role="ADMIN")
    _override(client, admin, oid, "DRAWING")
    dfx_login(client, team.drawer)
    assert send(client, "drawing", oid, "s0", "s1").status_code == 200
    new = [dfx_key(oid, "s0-v2"), dfx_key(oid, "s1-v2")]
    assert row(oid, KEY, "cut").state == "DONE" and row(oid, new[0], "cut") is None  # 생산 밖 전달은 안 옮긴다
    _override(client, admin, oid, "PRODUCTION")
    sd, marks = _state(oid)
    cut = part_progress(sd, marks, "cut")
    assert (cut["done"], cut["done_n"], cut["total_n"]) == (True, 2, 2) and step(oid, "cut")["done"] is True
    assert [row(oid, k, "edge").state for k in new] == ["NEED", "NEED"] and row(oid, KEY, "edge").state == "NONE"
    mine = _cards(my_steps_of(db_session.get(User, people["edge"].id)))
    assert sorted((c["key"], c["order_card"]) for c in mine) == sorted((k, False) for k in new)
    carried = [e.payload for e in events(oid, "PRODUCTION_PART_MARKED") if e.payload.get("via") == "order_card"]
    assert sorted((p["key"], p["part"], p["action"]) for p in carried if p["action"] != "order_card") == sorted(
        [(new[0], "cut", "done"), (new[1], "cut", "done"), (new[0], "edge", "take"), (new[1], "edge", "take")])
    _override(client, admin, oid, "DRAWING")  # 한 번만 — 다시 들어와도 더 안 옮긴다(@order 줄이 미정)
    _override(client, admin, oid, "PRODUCTION")
    assert len([e for e in events(oid, "PRODUCTION_PART_MARKED") if e.payload.get("via") == "order_card"]) == len(carried)


def test_status_write_into_production_also_carries_the_order_card(client, people, quiet, team):
    """생산 진입의 다른 길(``update_order_status`` — 단계 쓰기 자리마다 부르는 ``release_on_stage_exit``)도 같은 옮기기를 탄다."""
    oid = dfx_order(0, assignees=(team.drawer.id,))
    _finish(client, people["kim"], Seed(oid, (KEY,)), "cut")
    admin = make_user("관리", team="CS", role="ADMIN")
    _override(client, admin, oid, "DRAWING")
    dfx_login(client, team.drawer)
    assert send(client, "drawing", oid, "s0").status_code == 200
    login(client, admin)
    resp = client.post("/api/update_order_status", json={"order_id": oid, "status": "PRODUCTION", "admin_override": True,
                                                         "override_reason": "시험 — 다시 생산으로"})
    assert resp.status_code == 200, resp.get_json()
    assert row(oid, dfx_key(oid, "s0-v2"), "cut").state == "DONE" and row(oid, KEY, "cut").state == "NONE"
    assert step(oid, "cut")["done"] is True


def test_the_production_entry_carry_is_wired_into_every_stage_write():
    """단계 쓰기 자리마다 부르는 한 곳(``release_on_stage_exit``)에 옮기기가 걸려 있다 — 앱을 만들면 늘(그 모듈이 import 될 때 스스로 건다)."""
    from foms.services.orders.drawing_fix_marks import STAGE_WRITE_HOOKS  # noqa: PLC0415
    from foms.services.production.order_card_carry import carry_on_production_entry  # noqa: PLC0415

    assert STAGE_WRITE_HOOKS.count(carry_on_production_entry) == 1
