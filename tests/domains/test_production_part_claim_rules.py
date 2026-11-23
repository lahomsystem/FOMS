"""파트 카드 규칙 — 손 체크 두 경우(B5′) · 제작 완료 규칙(B1)이 부르는 곳마다 같은 답 · 검수 순서(B11) — API 시험.

설계서 2026-11-23-production-self-claim-and-factory2 §4-2 · §4-3 · §4-7 + 승인 때 고친 것 2 · 3(P1).

되돌리면 실패: 카드를 쓴 파트의 손 체크를 켜기(3/5 에서 켜짐) · 막힘 글 바꾸기 · 손으로 켠 칸 위에 카드 쓰기 · 카드로 다 끝낸 칸
끄기 · 완료 판정을 부르는 곳 하나라도 칸 규칙만 보기 · 검수를 앞 파트 전에 열기 · 관리자는 검수 순서를 건너뛰기 · 검수 완료 장의
앞 파트 완료 취소 · 완료 물음을 검수 아닌 쓰기에서 주기.
대조군: 카드를 안 쓴 주문은 공정 칸 체크 · 제작 완료가 지금 그대로(같은 글 · 버전 +1 · 이벤트 하나) · 카드를 안 쓴 파트는
반장이 바로 체크 · 다른 장은 검수가 열린다.
"""
from __future__ import annotations

import pytest

from db import db_session
from foms.services.datetime_kst import now_utc_naive
from foms.services.production.part_progress import complete_ready
from foms.services.production_sheet_view import build_production_sheet_view
from models import ProductionPartMark, SecurityLog, User
from tests.support.production_part_claim_seed import (
    BULK,
    check_step,
    code,
    events,
    finish,
    fresh,
    login,
    make_order,
    make_user,
    mark,
    row,
    step,
)


def _seed(oid: int, key: str, part: str, state: str, *, holder: str | None = None, done_by: str | None = None) -> None:
    now = now_utc_naive()
    db_session.add(ProductionPartMark(order_id=oid, drawing_key=key, part=part, state=state, picked_by_name=holder,
                                      picked_at=now if holder else None, done_by_name=done_by,
                                      done_at=now if done_by else None, updated_at=now))
    db_session.commit()


# --------------------------------------------------------------------------- #
# §4-2 손 체크 — 카드를 한 장도 안 쓴 파트 = 칸이 기준
# --------------------------------------------------------------------------- #
def test_part_without_cards_hand_check_is_the_basis_and_blocks_its_cards(client):
    order = make_order(5)
    login(client, make_user("박반장", lead=True))  # 반장(관리자가 체크한 생산팀 — 승인 때 고친 것 5)
    on = check_step(client, order.id, "cut", True)
    assert on.status_code == 200, on.get_json()
    cut = step(order.id, "cut")
    assert (cut["done"], cut["by_name"], cut["via"]) == (True, "박반장", "sheet")
    payload = events(order.id, "PRODUCTION_STEP_CHECKED")[-1].payload
    assert (payload["via"], payload["by_name"], payload["done"]) == ("sheet", "박반장", True)
    assert on.get_json()["data"]["parts"]["cut"]["uses_cards"] is False and on.get_json()["data"]["sheets"] == 5

    login(client, make_user("김재단", part="cut"))
    take = mark(client, order, 0, "cut", "take", "none")  # 칸 먼저 → 카드 409
    assert take.status_code == 409 and code(take) == "STEP_SET_BY_HAND"
    assert take.get_json()["error"] == "박반장이 작업 시트에서 재단 칸을 체크했어요. 다시 해야 하면 박반장에게 말해 주세요."
    bulk = client.post(BULK, json={"part": "cut", "seen": "none",
                                   "items": [{"order_id": order.id, "drawing_key": k} for k in order.keys]})
    assert [s["reason"] for s in bulk.get_json()["data"]["skipped"]] == ["STEP_SET_BY_HAND"] * 5
    assert db_session.query(ProductionPartMark).filter_by(order_id=order.id).count() == 0

    login(client, make_user("박반장2", lead=True))
    assert check_step(client, order.id, "cut", False).status_code == 200
    assert "via" not in step(order.id, "cut")
    login(client, make_user("김재단2", part="cut"))
    assert mark(client, order, 0, "cut", "take", "none").status_code == 200  # 칸을 끄면 카드가 열린다


def test_cards_all_released_turns_part_back_to_hand_check(client):
    """카드를 쓰다가 모두 맡기 취소(NONE 만 남음) = 카드를 안 쓴 파트 → 반장이 손으로 체크할 수 있다."""
    order = make_order(2)
    login(client, make_user("김재단", part="cut"))
    assert mark(client, order, 0, "cut", "take", "none").status_code == 200
    assert mark(client, order, 0, "cut", "release", "need").status_code == 200
    login(client, make_user("박반장", lead=True))
    assert check_step(client, order.id, "cut", True).status_code == 200


# --------------------------------------------------------------------------- #
# §4-2 손 체크 — 카드를 한 장이라도 쓴 파트 = 카드가 기준
# --------------------------------------------------------------------------- #
def test_card_part_three_of_five_hand_check_is_refused_without_writing(client):
    """사장님 예: 도면 5장 중 3장만 재단 완료 — 반장이 칸을 눌러도 체크 안 됨, 남은 2장은 할 일 그대로."""
    order = make_order(5)
    login(client, make_user("김재단", part="cut"))
    for j in range(3):
        assert finish(client, order, j, "cut").status_code == 200
    version = fresh(order.id).mutation_version
    step_events = len(events(order.id, "PRODUCTION_STEP_CHECKED"))
    login(client, make_user("박반장", lead=True))
    resp = check_step(client, order.id, "cut", True)
    body = resp.get_json()
    assert resp.status_code == 409 and body["success"] is False
    assert body["error"] == "도면 2장이 아직 미완료예요. 남은 도면을 완료하면 자동으로 체크돼요."
    assert body["data"] == {"code": "PART_USES_CARDS", "part": "cut", "left": 2, "total": 5}
    assert step(order.id, "cut")["done"] is False and fresh(order.id).mutation_version == version
    assert len(events(order.id, "PRODUCTION_STEP_CHECKED")) == step_events
    assert db_session.query(SecurityLog).filter_by(action="PRODUCTION_STEP_CHECKED", target_id=order.id).count() == 0
    got = client.get(f"/api/orders/{order.id}/production/steps").get_json()["data"]
    assert got["parts"]["cut"] == {"uses_cards": True, "done": False, "done_n": 3, "total_n": 5, "via": None, "left_n": 2}
    blocked = client.post(f"/api/orders/{order.id}/production/complete", json={})
    assert blocked.status_code == 409
    assert blocked.get_json()["message"] == "아직 미완료가 있어요 — 재단 2장 · 엣지 5장 · 조립 5장 · 검수 5장"


def test_card_part_all_done_step_cannot_be_turned_off_by_hand(client):
    order = make_order(2)
    login(client, make_user("김재단", part="cut"))
    finish(client, order, 0, "cut")
    assert finish(client, order, 1, "cut").get_json()["data"]["order_step"]["done"] is True
    assert step(order.id, "cut")["via"] == "part_marks"
    login(client, make_user("박반장", lead=True))
    resp = check_step(client, order.id, "cut", False)
    assert resp.status_code == 409 and code(resp) == "STEP_SET_BY_CARDS"
    assert step(order.id, "cut")["done"] is True


def test_old_step_without_via_on_card_part_is_judged_by_cards(client):
    """3판 전 옛 칸(``via`` 없음)이 켜져 있어도 카드를 쓴 파트면 카드가 기준 — 완료 판정 · 손 체크 모두."""
    order = make_order(3, steps_done=("cut", "edge", "assemble", "inspect"), by_name="옛사람")
    _seed(order.id, order.keys[0], "cut", "DONE", done_by="김재단")
    assert "via" not in step(order.id, "cut")
    login(client, make_user("박반장", lead=True))
    got = client.get(f"/api/orders/{order.id}/production/steps").get_json()["data"]
    assert got["complete_ready"] is False and got["parts"]["cut"]["left_n"] == 2
    assert code(check_step(client, order.id, "cut", True)) == "PART_USES_CARDS"
    assert client.post(f"/api/orders/{order.id}/production/complete", json={}).status_code == 409


def test_control_order_without_cards_step_check_is_unchanged(client):
    """대조군: 카드를 안 쓴 주문 — 켜고 끌 때마다 200 · 버전 +1 · 이벤트 하나(지금 그대로)."""
    order = make_order(3)
    login(client, make_user("박반장", lead=True))
    for done in (True, False, True):
        before = fresh(order.id).mutation_version
        assert check_step(client, order.id, "edge", done).status_code == 200
        assert fresh(order.id).mutation_version == before + 1
    assert [e.payload["done"] for e in events(order.id, "PRODUCTION_STEP_CHECKED")] == [True, False, True]


# --------------------------------------------------------------------------- #
# §4-3 제작 완료 — 부르는 곳마다 같은 답
# --------------------------------------------------------------------------- #
_ALL = ("cut", "edge", "assemble", "inspect")
ROWS = {
    # 이름: (확정 도면 장 수, 손으로 켠 칸, 카드 표시 {파트: 완료 장 수} — 그 밖 장은 없음, 되는가)
    "no_cards_no_steps": (2, (), {}, True),
    "no_cards_some_steps": (2, ("cut", "edge"), {}, False),
    "no_cards_four_steps": (2, _ALL, {}, True),
    "cards_four_done_mixed": (2, ("edge",), {"cut": 2, "assemble": 2, "inspect": 2}, True),
    "cards_one_short": (2, _ALL, {"cut": 2, "edge": 2, "assemble": 2, "inspect": 1}, False),
    "cards_zero_drawings": (0, (), {"cut": 1}, False),
}


def _row_order(name: str) -> int:
    n, on, done, _ready = ROWS[name]
    order = make_order(n, steps_done=on)
    for part, count_done in done.items():
        keys = order.keys[:count_done] if n else ("gone/old.png",)
        for key in keys:
            _seed(order.id, key, part, "DONE", done_by="가짜완료")
    return order.id


@pytest.mark.parametrize("name", list(ROWS))
def test_every_caller_gives_the_same_completion_answer(client, name):
    ready = ROWS[name][3]
    admin = make_user("관리", team="CS", role="ADMIN")
    probe = _row_order(name)
    marks = db_session.query(ProductionPartMark).filter_by(order_id=probe).all()
    assert complete_ready(fresh(probe).structured_data, marks) is ready
    login(client, admin)
    assert client.get(f"/api/orders/{probe}/production/steps").get_json()["data"]["complete_ready"] is ready
    viewer = db_session.get(User, admin.id)
    assert build_production_sheet_view(db_session, fresh(probe), viewer, full=True)["complete_ready"] is ready

    expected = 200 if ready else 409
    calls = {
        "complete": lambda oid: client.post(f"/api/orders/{oid}/production/complete", json={}),
        "status": lambda oid: client.post("/api/update_order_status", json={"order_id": oid, "status": "CONSTRUCTION"}),
        "field": lambda oid: client.post("/api/update_order_field",
                                         json={"order_id": oid, "field": "status", "value": "CONSTRUCTION"}),
    }
    for label, call in calls.items():
        oid = _row_order(name)
        resp = call(oid)
        assert resp.status_code == expected, (label, resp.get_json())
        assert (fresh(oid).erp_stage_code == "CONSTRUCTION") is ready, label
        if not ready:
            assert resp.get_json()["code"] == "STEPS_INCOMPLETE", label
    oid = _row_order(name)
    bulk = client.post("/api/bulk_update_order_status", json={"order_ids": [oid], "status": "CONSTRUCTION"}).get_json()
    assert (bulk.get("blocked_steps_incomplete") or []) == ([] if ready else [oid])


def test_zero_drawings_card_order_message(client):
    login(client, make_user("가짜생산"))
    resp = client.post(f"/api/orders/{_row_order('cards_zero_drawings')}/production/complete", json={})
    assert resp.get_json()["message"] == "도면이 없어요 — 공정 칸을 체크하거나 관리자에게 말해 주세요."


# --------------------------------------------------------------------------- #
# §4-7 검수 순서 — 장마다 · 관리자도 같다
# --------------------------------------------------------------------------- #
def test_inspect_opens_per_sheet_after_cut_edge_assemble(client):
    order = make_order(2)
    inspector = make_user("윤검수", part="inspect")
    login(client, inspector)
    early = mark(client, order, 0, "inspect", "take", "none")
    assert early.status_code == 409 and code(early) == "INSPECT_NOT_READY"
    assert early.get_json()["data"]["left"] == [{"part": "cut", "holder": None}, {"part": "edge", "holder": None},
                                                {"part": "assemble", "holder": None}]
    login(client, make_user("관리", team="CS", role="ADMIN"))
    assert code(mark(client, order, 0, "inspect", "take", "none")) == "INSPECT_NOT_READY"  # 관리자도 막힌다
    assert mark(client, order, 0, "cut", "basic", "none").status_code == 200  # 재단 기본 = 완료
    for part in ("edge", "assemble"):
        finish(client, order, 0, part)
    login(client, inspector)
    assert mark(client, order, 0, "inspect", "take", "none").status_code == 200  # 1장째는 열림(2장째는 그대로)
    assert code(mark(client, order, 1, "inspect", "take", "none")) == "INSPECT_NOT_READY"


def test_old_inspect_claim_can_be_released_but_not_finished_or_taken_over(client):
    """규칙 전 검수 맡음은 지우지 않는다 — 완료 · 담당 바꾸기는 준비될 때까지 막히고, 맡기 취소는 된다."""
    order = make_order(1)
    holder = make_user("윤검수", part="inspect")
    _seed(order.id, order.keys[0], "inspect", "NEED", holder="윤검수")
    db_session.query(ProductionPartMark).filter_by(order_id=order.id).update({"picked_by_user_id": holder.id})
    db_session.commit()
    login(client, make_user("강검수", part="inspect"))
    other = mark(client, order, 0, "inspect", "takeover", "need", seen_by=holder.id)
    assert other.status_code == 409 and code(other) == "INSPECT_NOT_READY"
    login(client, holder)
    assert code(mark(client, order, 0, "inspect", "done", "need")) == "INSPECT_NOT_READY"
    assert mark(client, order, 0, "inspect", "release", "need").status_code == 200
    assert row(order.id, order.keys[0], "inspect").state == "NONE"


def test_hand_checked_parts_count_for_inspect(client):
    order = make_order(1, steps_done=("cut", "edge", "assemble"))
    login(client, make_user("윤검수", part="inspect"))
    assert mark(client, order, 0, "inspect", "take", "none").status_code == 200


def test_inspected_sheet_blocks_undo_of_an_earlier_part(client):
    order = make_order(1)
    login(client, make_user("관리", team="CS", role="ADMIN"))
    for part in ("cut", "edge", "assemble", "inspect"):
        finish(client, order, 0, part)
    undo = mark(client, order, 0, "edge", "undo", "done")
    assert undo.status_code == 409 and code(undo) == "INSPECT_DONE_FIRST"
    assert undo.get_json()["error"].startswith("관리가 이 장 검수를 완료했어요. 엣지 완료를 취소하려면")
    assert mark(client, order, 0, "inspect", "undo", "done").status_code == 200
    assert mark(client, order, 0, "edge", "undo", "done").status_code == 200  # 검수 완료를 먼저 취소하면 된다


def test_order_ready_only_after_the_inspect_card_that_completes_the_order(client):
    order = make_order(1)
    login(client, make_user("관리", team="CS", role="ADMIN"))
    for part in ("cut", "edge", "assemble"):
        assert finish(client, order, 0, part).get_json()["data"]["order_ready"] is None
    assert mark(client, order, 0, "inspect", "take", "none").get_json()["data"]["order_ready"] is None
    done = mark(client, order, 0, "inspect", "done", "need").get_json()["data"]
    assert done["order_ready"] == {"order_id": order.id}
    again = mark(client, order, 0, "inspect", "done", "need").get_json()["data"]  # 멱등 다시 보냄도 같은 물음
    assert again["changed"] is False and again["order_ready"] == {"order_id": order.id}
