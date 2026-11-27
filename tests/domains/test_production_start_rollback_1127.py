"""도면이 연 제작 시작 되돌리기(사장님 2026-11-27 — 2026-11-23 설계서 §4-8 · §19 넷째를 뒤집는다).

결정(글자 그대로): "그 주문에 잡혀 있거나 완료된 도면이 하나도 없게 되면, 도면으로 걸렸던 제작 시작도 같이 취소됩니다. '남은 공정' 숫자가
줄고 주문은 '제작 대기'로 돌아갑니다. 작업 시트에서 [제작 시작]을 일부러 누른 주문, 보류 중이거나 불량 기록이 있는 주문은 건드리지 않습니다."

* 되돌림: 제작 대기 주문 첫 도면 [작업 시작] → [시작 취소] = 회차 닫힘 · '곧 올 것(제작 대기)' · '남은 공정' 숫자 원래대로 · 이벤트
  ``PRODUCTION_CANCELLED``(``via:'part_marks'``) · 단계 기록 "제작 시작 취소 (도면 작업 시작 취소)" · 감사 꼬리 · 버전 +1 한 번.
  [기본] → [기본 취소], 반장이 남의 시작을 취소, 반장 바로 완료 → [완료 취소], 한꺼번에 기본 뒤 한 장씩 취소도 같은 규칙.
* 대조군(회차 그대로): 작업 시트 [제작 시작]으로 연 주문 · 다른 도면이 작업 중 / 완료 / 기본 · 다른 파트 표시 · 공정 칸 하나 켜짐 · 보류 ·
  그 회차의 불량 기록 · 수정 제작 · 공장 완료 표지 · 시작 이벤트 없는 옛 회차 · 시작 이벤트보다 늦게 열린 회차.
* 멱등(같은 요청 두 번 = 바뀜 없음) · 다시 [작업 시작] = 새 회차 · 쿼리 수(취소 길만 늘어남) · 알림 줄 0 · 화면 글.

되돌리면 실패: [시작 취소] 뒤에도 '재단 1' · 회차가 남음 / 작업 시트로 시작한 주문 · 보류 · 불량 주문까지 닫힘 / 시작 · 완료 길 쿼리 증가.
이름은 모두 지어낸 값이다.
"""
from __future__ import annotations

import datetime

import pytest

import foms.services.production.part_mark_write as part_mark_write
from db import db_session
from foms.services.production.start_rollback import ROLLBACK_AUDIT_TAIL, run_tail
from foms.services.production.start_run import CARD_CANCEL_NOTE, CARD_START_NOTE, cancelled_event_values
from foms.services.production_home_read_model import (
    build_production_home,
    production_home_counts,
    production_home_step_queues,
)
from models import (
    DomainSideEffectOutbox,
    Notification,
    NotificationEvent,
    OrderMutationReceipt,
    ProductionRun,
    SecurityLog,
    User,
)
from tests.domains.test_production_home_query_count import _count_queries
from tests.domains.test_production_lead_direct_done_1127 import _admin, _check, _lead
from tests.domains.test_production_multi_holder_api import _audits
from tests.domains.test_production_multi_holder_board import _node, _page, _post, cohort  # noqa: F401
from tests.support.production_part_claim_seed import (
    BULK,
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

FIRST_LINE = "이 주문 첫 도면이라 제작 시작도 같이 돼요."


def _kim():
    return make_user("김재단", part="cut")


def _release(client, order, j: int = 0, part: str = "cut"):
    """화면이 보내는 몸 — 내가 작업 중인 칸 [시작 취소](본 내 몫 = 작업 중)."""
    return mark(client, order, j, part, "release", "need", seen_me="held")


def _data(resp) -> dict:
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["data"]


def _home(person) -> tuple[list[dict], dict]:
    db_session.expire_all()
    rows, _stats = build_production_home(db_session, db_session.get(User, person.id))
    return rows, production_home_counts(rows)


def _home_row(rows: list[dict], oid: int) -> dict:
    return next(r for r in rows if r["id"] == oid)


def _runs(oid: int) -> list[tuple[str, bool]]:
    db_session.expire_all()
    found = db_session.query(ProductionRun).filter_by(order_id=oid).order_by(ProductionRun.started_at).all()
    return [(r.status, bool(r.is_current)) for r in found]


def _kept(order, data: dict) -> None:
    """대조군 판정 — 회차 그대로 · 되돌림 표지 없음 · 취소 이벤트 없음."""
    assert data["run_cancelled"] is False
    assert current_runs(order.id) == 1 and events(order.id, "PRODUCTION_CANCELLED") == []
    assert ROLLBACK_AUDIT_TAIL not in _audits(order.id)[-1]


def _rolled_back(order, data: dict) -> None:
    assert data["run_cancelled"] is True and data["run_started"] is False
    assert current_runs(order.id) == 0 and len(events(order.id, "PRODUCTION_CANCELLED")) == 1
    assert _audits(order.id)[-1].endswith(ROLLBACK_AUDIT_TAIL)


# 되돌림 — [작업 시작] → [시작 취소]
def test_take_then_release_returns_order_to_waiting(client):
    order = make_order(2, run=False)
    kim = _kim()
    login(client, kim)
    rows, before = _home(kim)
    waiting_before = production_home_step_queues(rows)["waiting"]
    assert _home_row(rows, order.id)["home_stage"] == "제작 대기"
    version = fresh(order.id).mutation_version
    assert _data(mark(client, order, 0, "cut", "take", "none"))["run_started"] is True
    rows, during = _home(kim)
    assert _home_row(rows, order.id)["home_stage"] == "재단 작업 중" and during["making"] == before["making"] + 1
    assert production_home_step_queues(rows)["waiting"] == waiting_before - 1
    data = _data(_release(client, order))
    assert (data["changed"], data["mark"]["state"], data["order_step"]) == (True, "none", None)
    _rolled_back(order, data)
    assert _runs(order.id) == [("SUPERSEDED", False)]
    rows, after = _home(kim)  # '남은 공정' 숫자 원래대로 · 주문은 재단 줄의 '곧 올 것(제작 대기)'으로
    got = _home_row(rows, order.id)
    assert (got["home_stage"], got["home_has_run"], got["has_changes"]) == ("제작 대기", False, False)
    assert after == before
    queues = production_home_step_queues(rows)
    cut = queues["queues"][0]
    assert queues["waiting"] == waiting_before and cut["incoming_label"] == "제작 대기"
    assert order.id in [r["id"] for r in cut["incoming"]] and order.id not in [r["id"] for r in cut["rows"]]
    saved = fresh(order.id)  # 단계는 생산 그대로 · 버전은 시작 +1 · 되돌림 +1(시작 때와 같은 규칙 — 주문 쓰기 한 번)
    assert (saved.erp_stage_code, saved.status, saved.structured_data["workflow"]["stage"]) == ("PRODUCTION",) * 3
    assert saved.mutation_version == version + 2
    notes = [h["note"] for h in saved.structured_data["workflow"]["history"]]
    assert notes[-2:] == [CARD_START_NOTE, CARD_CANCEL_NOTE] == ["제작 시작 (도면 작업 시작)", "제작 시작 취소 (도면 작업 시작 취소)"]
    assert saved.structured_data["workflow"]["history"][-1]["stage"] == "PRODUCTION"
    assert saved.structured_data["workflow"]["history"][-1]["updated_by"] == "김재단"
    cancelled = events(order.id, "PRODUCTION_CANCELLED")[0]
    closed = db_session.query(ProductionRun).filter_by(order_id=order.id).one()
    assert cancelled.created_by_user_id == kim.id and cancelled.payload == {
        "domain": "PRODUCTION_DOMAIN", "action": "PRODUCTION_CANCELLED", "reason": "", "rework_cleared": False,
        "hold_released": False, "run_id": closed.id, "via": "part_marks"}
    audit = db_session.query(SecurityLog).filter_by(action="PRODUCTION_START_CANCELED", target_id=order.id).one()
    assert "제작 시작 취소: 도면 작업 시작 취소" in audit.message and audit.detail["via"] == "part_marks"
    marked = db_session.query(SecurityLog).filter_by(action="PRODUCTION_PART_MARKED", target_id=order.id).order_by(SecurityLog.id).all()
    assert marked[-1].detail["run_cancelled"] is True and marked[-1].detail["run_started"] is False
    assert marked[0].message.endswith(" · 제작 시작") and marked[0].detail["run_cancelled"] is False
    assert db_session.query(OrderMutationReceipt).filter_by(policy_id="STATE_PRODUCTION_CANCEL").count() == 1


def test_same_release_twice_changes_nothing_and_retake_opens_new_run(client):
    order = make_order(1, run=False)
    login(client, _kim())
    mark(client, order, 0, "cut", "take", "none")
    _rolled_back(order, _data(_release(client, order)))
    version, audits = fresh(order.id).mutation_version, len(_audits(order.id))
    again = _data(_release(client, order))  # 연결이 얼어 같은 요청이 한 번 더 — 바뀜 없음
    assert (again["changed"], again["run_cancelled"], again["run_started"], again["mark"]["state"]) == (False, False, False, "none")
    assert fresh(order.id).mutation_version == version and len(_audits(order.id)) == audits
    assert len(events(order.id, "PRODUCTION_CANCELLED")) == 1 and _runs(order.id) == [("SUPERSEDED", False)]
    retake = _data(mark(client, order, 0, "cut", "take", "none"))  # 다시 [작업 시작] = 새 회차로 다시 제작 시작
    assert retake["run_started"] is True and retake["run_cancelled"] is False
    assert sorted(_runs(order.id)) == [("IN_PROGRESS", True), ("SUPERSEDED", False)]
    assert len(events(order.id, "PRODUCTION_STARTED")) == 2 and fresh(order.id).mutation_version == version + 1
    twice = _data(_release(client, order))  # 새 회차도 도면이 연 것 — 다시 취소하면 다시 되돌아간다
    assert twice["run_cancelled"] is True and current_runs(order.id) == 0 and len(events(order.id, "PRODUCTION_CANCELLED")) == 2


# 대조군 — 회차 그대로
def test_order_started_from_work_sheet_is_untouched(client):
    order = make_order(2, run=False)
    login(client, _lead())
    started = client.post(f"/api/orders/{order.id}/production/start", json={})
    assert started.status_code == 200 and started.get_json()["run_started"] is True  # 작업 시트 [제작 시작]
    login(client, _kim())
    assert _data(mark(client, order, 0, "cut", "take", "none"))["run_started"] is False
    _kept(order, _data(_release(client, order)))
    assert fresh(order.id).structured_data["workflow"]["history"][-1]["note"] == "제작 시작"


def test_seeded_run_without_start_event_is_untouched(client):
    """시작 이벤트가 없는 옛 회차(되채운 회차 · 완료 취소가 다시 연 회차 꼴) — 누가 열었는지 모르면 건드리지 않는다."""
    order = make_order(1)
    login(client, _kim())
    mark(client, order, 0, "cut", "take", "none")
    _kept(order, _data(_release(client, order)))


def test_run_opened_after_the_card_start_event_is_untouched(client):
    """마지막 시작 이벤트는 도면 길이지만 지금 회차는 그 뒤에 따로 열린 것(완료 취소가 새로 연 회차 꼴) — 그 회차를 연 것이 도면이 아니다."""
    order = make_order(1, run=False)
    login(client, _kim())
    mark(client, order, 0, "cut", "take", "none")
    run = db_session.query(ProductionRun).filter_by(order_id=order.id).one()
    run.started_at = events(order.id, "PRODUCTION_STARTED")[-1].created_at + datetime.timedelta(hours=1)
    db_session.commit()
    _kept(order, _data(_release(client, order)))


@pytest.mark.parametrize("other", ["need", "done", "basic"])
def test_other_drawing_still_marked_keeps_run(client, other):
    """여러 장 주문에서 한 장만 취소 — 다른 도면이 작업 중 · 완료 · 기본이면 그대로."""
    order = make_order(3, run=False)
    login(client, _kim())
    if other == "need":
        mark(client, order, 1, "cut", "take", "none")
    elif other == "done":
        finish(client, order, 1, "cut")
    else:
        mark(client, order, 1, "cut", "basic", "none")
    assert current_runs(order.id) == 1
    mark(client, order, 0, "cut", "take", "none")
    _kept(order, _data(_release(client, order)))
    assert row(order.id, order.keys[1], "cut").state == other.upper()


def test_other_person_took_another_drawing_then_last_release_rolls_back(client):
    """그사이 다른 사람이 다른 도면을 잡았으면 되돌리지 않는다 — 그 사람까지 취소해 표시가 모두 미정이 되면 그때 되돌아간다."""
    order = make_order(2, run=False)
    kim, lee = _kim(), make_user("이시영", part="cut")
    login(client, kim)
    mark(client, order, 0, "cut", "take", "none")
    login(client, lee)
    assert _data(mark(client, order, 1, "cut", "take", "none"))["run_started"] is False
    login(client, kim)
    _kept(order, _data(_release(client, order, 0)))
    login(client, lee)
    _rolled_back(order, _data(_release(client, order, 1)))  # 회차를 연 사람이 아니어도 — 마지막 표시가 미정이 되면


def test_other_part_mark_keeps_run(client):
    order = make_order(1, run=False)
    login(client, make_user("박엣지", part="edge"))
    assert _data(mark(client, order, 0, "edge", "take", "none"))["run_started"] is True
    login(client, _kim())
    mark(client, order, 0, "cut", "take", "none")
    _kept(order, _data(_release(client, order)))
    assert row(order.id, order.keys[0], "edge").state == "NEED"


def test_hand_checked_step_keeps_run(client):
    """공정 칸 하나가 켜져 있으면(작업 시트에서 손으로 켠 칸) 그대로."""
    order = make_order(1, run=False, steps_done=("edge",))
    login(client, _kim())
    assert _data(mark(client, order, 0, "cut", "take", "none"))["run_started"] is True
    _kept(order, _data(_release(client, order)))
    assert step(order.id, "edge")["done"] is True


def test_hold_keeps_run_and_hold(client):
    order = make_order(1, run=False)
    login(client, _kim())
    mark(client, order, 0, "cut", "take", "none")
    patch_sd(order.id, hold={"active": True, "reason": "자재 기다림", "at": "2026-11-27T00:00:00", "by_name": "박반장"})
    _kept(order, _data(_release(client, order)))
    assert fresh(order.id).structured_data["production"]["hold"]["active"] is True  # 보류는 풀지 않는다


def test_defect_in_this_run_keeps_run_but_older_defect_does_not(client):
    order = make_order(1, run=False)
    kim, lead = _kim(), _lead()
    login(client, kim)
    mark(client, order, 0, "cut", "take", "none")
    login(client, lead)
    assert client.post(f"/api/orders/{order.id}/production/defect", json={"reason": "파손"}).status_code == 200
    login(client, kim)
    _kept(order, _data(_release(client, order)))
    assert len(fresh(order.id).structured_data["production"]["defects"]) == 1

    old = make_order(1, run=False)  # 이 회차가 열리기 전(옛 회차)의 불량 기록만 있는 주문 = 이 회차의 기록이 아니다 → 되돌린다
    patch_sd(old.id, defects=[{"reason": "파손", "at": "2026-11-01T00:00:00+00:00", "by_name": "박반장"}])
    mark(client, old, 0, "cut", "take", "none")
    _rolled_back(old, _data(_release(client, old)))
    assert len(fresh(old.id).structured_data["production"]["defects"]) == 1  # 기록은 그대로 남는다

    broken = make_order(1, run=False)  # 때를 못 읽는 기록 = 있는 것으로 본다(건드리지 않는 쪽)
    mark(client, broken, 0, "cut", "take", "none")
    patch_sd(broken.id, defects=[{"reason": "파손", "at": None, "by_name": "박반장"}])
    _kept(broken, _data(_release(client, broken)))


def test_rework_and_factory_done_mark_keep_run(client):
    login(client, _kim())
    rework = make_order(1, run=False)
    mark(client, rework, 0, "cut", "take", "none")
    patch_sd(rework.id, rework={"active": True, "count": 1, "reason": "다시", "at": "2026-11-27T00:00:00", "by_name": "박반장"})
    _kept(rework, _data(_release(client, rework)))
    assert fresh(rework.id).structured_data["production"]["rework"]["active"] is True  # 수정 제작 표지는 끄지 않는다

    factory = make_order(1, run=False)
    mark(client, factory, 0, "cut", "take", "none")
    done = {"2": {"keys": ["x/old.png"], "at": "2026-11-27T00:00:00+00:00", "by_name": "박반장", "by_user_id": 1}}
    patch_sd(factory.id, factory_done=done)
    _kept(factory, _data(_release(client, factory)))
    assert fresh(factory.id).structured_data["production"]["factory_done"] == done  # 공장 완료 표지는 지우지 않는다


# 같은 규칙 — [기본 취소] · 반장이 남의 시작 취소 · 바로 완료 → [완료 취소] · 한꺼번에 기본
def test_basic_then_basic_undo_rolls_back_with_step_in_one_order_write(client):
    order = make_order(1, run=False)
    login(client, _kim())
    took = _data(mark(client, order, 0, "cut", "basic", "none"))
    assert took["run_started"] is True and took["order_step"]["done"] is True
    version = fresh(order.id).mutation_version
    data = _data(mark(client, order, 0, "cut", "undo", "basic"))  # 켜진 재단 칸이 꺼지면서 되돌림까지 — 주문 쓰기는 한 번
    assert data["mark"]["state"] == "none" and data["order_step"] == {"order_id": order.id, "key": "cut", "done": False}
    _rolled_back(order, data)
    assert _audits(order.id)[-1].endswith(" · 공정 재단 끔 · 제작 시작 취소")
    assert fresh(order.id).mutation_version == version + 1 and step(order.id, "cut")["done"] is False
    assert db_session.query(OrderMutationReceipt).filter_by(policy_id="STATE_PRODUCTION_CANCEL").count() == 1
    assert _data(mark(client, order, 0, "cut", "take", "none"))["run_started"] is True  # 다시 시작된다


def test_lead_removing_someone_elses_start_rolls_back(client):
    order = make_order(2, run=False)
    kim = _kim()
    login(client, kim)
    mark(client, order, 0, "cut", "take", "none")
    login(client, _lead())
    data = _data(mark(client, order, 0, "cut", "remove", "need", target_user_id=kim.id, seen_me="none"))
    assert data["mark"]["state"] == "none"
    _rolled_back(order, data)
    assert events(order.id, "PRODUCTION_CANCELLED")[0].created_by_user_id != kim.id  # 누른 사람 = 반장
    assert fresh(order.id).structured_data["workflow"]["history"][-1]["updated_by"] == "박반장"


@pytest.mark.parametrize("sheets", [1, 2])
def test_lead_direct_done_then_undo_rolls_back(client, sheets):
    """반장 바로 완료 → [완료 취소](한 번에 미정) — 1장 주문은 켜진 칸이 꺼지면서, 2장 주문은 칸 바뀜 없이."""
    order = make_order(sheets, run=False)
    login(client, _lead())
    assert _data(_check(client, order, 0))["run_started"] is True
    data = _data(mark(client, order, 0, "cut", "undo", "done", seen_me="done"))
    assert data["mark"]["state"] == "none"
    _rolled_back(order, data)
    assert all(s["done"] is False for s in fresh(order.id).structured_data["production"]["steps"])
    again = make_order(1, run=False)  # 관리자가 반장의 바로 완료(엣지)를 취소 — 누가 눌러도 같은 규칙
    _check(client, again, 0, "edge")
    login(client, _admin())
    _rolled_back(again, _data(mark(client, again, 0, "edge", "undo", "done", seen_me="none")))


def test_bulk_basic_then_undo_each_rolls_back_on_the_last_one(client):
    order = make_order(2, run=False)
    login(client, _kim())
    items = [{"order_id": order.id, "drawing_key": k} for k in order.keys]
    assert client.post(BULK, json={"part": "cut", "seen": "none", "items": items}).get_json()["data"]["run_started"] == [order.id]
    _kept(order, _data(mark(client, order, 0, "cut", "undo", "basic")))
    _rolled_back(order, _data(mark(client, order, 1, "cut", "undo", "basic")))


def test_done_undo_back_to_working_never_rolls_back(client):
    """대조 — 파트 계정의 [완료 취소]는 작업 중으로 돌아갈 뿐(미정이 아님) → 판정 자체를 안 한다."""
    order = make_order(1, run=False)
    login(client, _kim())
    finish(client, order, 0, "cut")
    data = _data(mark(client, order, 0, "cut", "undo", "done"))
    assert data["mark"]["state"] == "need"
    _kept(order, data)


# 알림 — 되돌림은 알림 줄 · 바깥 보내기 줄을 만들지 않는다
def test_rollback_creates_no_notification_or_outbox_rows(client):
    def _counts() -> tuple[int, int, int]:
        db_session.expire_all()
        return tuple(db_session.query(model).count() for model in (Notification, NotificationEvent, DomainSideEffectOutbox))

    order = make_order(1, run=False)
    kim = _kim()
    login(client, kim)
    before = _counts()
    mark(client, order, 0, "cut", "take", "none")
    _rolled_back(order, _data(_release(client, order)))
    assert _counts() == before
    rows, counts = _home(kim)  # 생산 첫 화면 '바뀐 것'에도 안 뜬다
    assert _home_row(rows, order.id)["home_alerts"] == [] and counts["changed"] == 0


# 쿼리 수 — 취소 길에서만 는다(시작 · 완료 · 다른 표시가 남은 취소는 0 추가)
#: 실측(2026-11-27, SQLite 레인) — 되돌림 판정을 끈 값(= 고치기 전) → 켠 값.
#: 작업 시작 7 → 7 · 완료 6 → 6 · 다른 도면이 남은 시작 취소 6 → 6 · 작업 시트로 연 주문의 마지막 시작 취소 6 → 8(회차 · 마지막 시작 이벤트
#: 읽기 2) · 되돌림 6 → 18(읽기 2 + 주문 쓰기 한 번 10 — 주문 다시 잠금 · 저장 훅 3 · 주문 UPDATE · 영수증 · 읽기 자원 · 이벤트 INSERT ·
#: 되돌림 감사 INSERT · 회차 UPDATE). 첫 카드 제작 시작이 더하는 것과 같은 크기다(그쪽은 회차 INSERT, 이쪽은 회차 UPDATE).
READ_ONLY_EXTRA = 2
ROLLBACK_EXTRA_CAP = 14


def _measure(client, monkeypatch, prepare, press, *, planner: bool) -> int:
    with monkeypatch.context() as patch:
        if not planner:
            patch.setattr(part_mark_write, "plan_start_rollback", lambda *args, **kwargs: None)
        order = prepare()
        resp, n = _count_queries(lambda: press(order))
    assert resp.status_code == 200, resp.get_json()
    return n


def test_query_counts_grow_only_on_the_cancel_path(client, monkeypatch):
    kim, lead = _kim(), _lead()
    login(client, kim)
    mark(client, make_order(1), 0, "cut", "take", "none")  # warmup

    def _taken(n: int = 2, *, run: bool = False, both: bool = False):
        def _prepare():
            order = make_order(n, run=run)
            mark(client, order, 0, "cut", "take", "none")
            if both:
                mark(client, order, 1, "cut", "take", "none")
            return order
        return _prepare

    def _sheet_started():
        order = make_order(2, run=False)
        login(client, lead)
        assert client.post(f"/api/orders/{order.id}/production/start", json={}).status_code == 200
        login(client, kim)
        mark(client, order, 0, "cut", "take", "none")
        return order

    cases = {
        "take": (lambda: make_order(2), lambda o: mark(client, o, 0, "cut", "take", "none")),
        "done": (_taken(run=True), lambda o: mark(client, o, 0, "cut", "done", "need", seen_me="held")),
        "release_other_left": (_taken(both=True), lambda o: _release(client, o)),
        "release_sheet_started": (_sheet_started, lambda o: _release(client, o)),
        "release_rollback": (_taken(), lambda o: _release(client, o)),
    }
    got = {name: (_measure(client, monkeypatch, prep, press, planner=False), _measure(client, monkeypatch, prep, press, planner=True))
           for name, (prep, press) in cases.items()}
    for name in ("take", "done", "release_other_left"):
        assert got[name][1] == got[name][0], (name, got)  # 0 추가
    assert got["release_sheet_started"][1] - got["release_sheet_started"][0] == READ_ONLY_EXTRA, got
    extra = got["release_rollback"][1] - got["release_rollback"][0]
    assert READ_ONLY_EXTRA < extra <= ROLLBACK_EXTRA_CAP, got


# 낮은 층 — [제작 시작 취소] API 와 같이 쓰는 줄 값 · 감사 꼬리
def test_shared_cancel_event_values_and_audit_tails():
    plain = cancelled_event_values(7, 3, run_id="r1", reason="잘못 누름", rework_cleared=True, hold_released=True)
    assert plain["event_type"] == "PRODUCTION_CANCELLED" and (plain["order_id"], plain["created_by_user_id"]) == (7, 3)
    assert plain["payload"] == {"domain": "PRODUCTION_DOMAIN", "action": "PRODUCTION_CANCELLED", "reason": "잘못 누름",
                                "rework_cleared": True, "hold_released": True, "run_id": "r1"}  # [제작 시작 취소] 단추 — via 없음
    assert cancelled_event_values(7, 3, run_id="r1", via="part_marks")["payload"]["via"] == "part_marks"
    assert (run_tail([7], None), run_tail([], object()), run_tail([], None)) == (" · 제작 시작", " · 제작 시작 취소", "")


def test_sheet_cancel_button_still_closes_run_and_clears_flags(client):
    """[제작 시작 취소] 단추는 지금 그대로 — 회차 닫기 · 이벤트(via 없음) · 보류 해제까지(도면 길은 보류를 건드리지 않는다)."""
    order = make_order(1)
    patch_sd(order.id, hold={"active": True, "reason": "자재 기다림", "at": "2026-11-27T00:00:00", "by_name": "박반장"})
    login(client, _lead())
    res = client.post(f"/api/orders/{order.id}/production/cancel", json={"reason": "잘못 누름"})
    assert res.status_code == 200 and res.get_json()["new_status"] == "PRODUCTION"
    assert _runs(order.id) == [("SUPERSEDED", False)]
    payload = events(order.id, "PRODUCTION_CANCELLED")[0].payload
    assert "via" not in payload and (payload["reason"], payload["hold_released"]) == ("잘못 누름", True)
    assert payload["run_id"] == db_session.query(ProductionRun).filter_by(order_id=order.id).one().id
    assert fresh(order.id).structured_data["production"]["hold"]["active"] is False


# 화면 — 끝난 뒤 알림 글 · 첫 도면 안내가 다시 선다(서버 답은 진짜 API JSON)
def test_js_status_says_start_was_cancelled_too_and_first_drawing_line_returns(client, cohort, tmp_path):
    order = make_order(2, run=False)
    kim = _kim()
    page = tmp_path / "kim.html"
    page.write_text(_page(client, kim), encoding="utf-8")
    k = order.keys
    take = {"order_id": order.id, "drawing_key": k[0], "part": "cut", "action": "take", "seen": "none", "seen_me": "none"}
    release = {"order_id": order.id, "drawing_key": k[0], "part": "cut", "action": "release", "seen": "need", "seen_me": "held",
               "seen_by": kim.id}
    replies = [_post(client, kim, take), _post(client, kim, release)]
    assert (replies[0]["data"]["run_started"], replies[1]["data"]["run_cancelled"]) == (True, True)
    res = _node(page, {"posts": replies, "steps": [
        {"do": "click", "key": k[0], "act": "take"}, {"do": "run"},
        {"do": "click", "key": k[1], "act": "take"}, {"do": "close"},
        {"do": "click", "key": k[0], "act": "release"}, {"do": "run"},
        {"do": "click", "key": k[1], "act": "take"}, {"do": "close"},
        {"do": "card", "key": k[0]}]})
    out, calls = res["out"], res["calls"]
    assert [c["body"] for c in calls] == [take, release]  # 화면이 보내는 몸 = 위에서 진짜 API 에 보낸 몸
    assert out[0]["modal"]["body"] == FIRST_LINE and out[1]["status"] == "작업 시작했어요 · 제작 시작도 같이 됐어요"
    assert out[2]["modal"]["body"] == ""  # 제작이 시작돼 다른 도면도 첫 도면 안내가 없다
    assert out[5]["sent"] == 1 and out[5]["status"] == "시작 취소했어요 · 제작 시작도 같이 취소됐어요"
    assert out[6]["modal"]["body"] == FIRST_LINE  # 되돌려진 뒤에는 그 주문 모든 도면이 다시 '첫 도면'
    assert out[8]["card"]["state"] == "none"


def test_source_contract_status_words_pair_and_js_size():
    from pathlib import Path

    js = (Path(__file__).resolve().parents[2] / "static/js/production/foms-production-parts.js").read_text(encoding="utf-8")
    assert "' · 제작 시작도 같이 됐어요' : data.run_cancelled ? ' · 제작 시작도 같이 취소됐어요' : ''" in js
    assert "c.setAttribute('data-pp-first', '1')" in js and len(js.splitlines()) <= 299
    write = Path(part_mark_write.__file__).read_text(encoding="utf-8")
    assert len(write.splitlines()) <= 499
