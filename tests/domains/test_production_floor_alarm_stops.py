"""생산 현장 알람 서버 — 멈춤 · 띠 · 까닭이 풀리면 닫기 · 쓰기 자리에 건 줄(설계서 2026-11-28 생산 현장 알람 §1-2 · §2-3 · §4-3 · §6-3).

'작업 중인 사람'은 진짜 카드 누름으로 만든 표시 줄에서 읽는다(준비물 :func:`floor`). 도면 수정 시작 · 취소, 공장 수정 요청, 생산 변경 알림
(시공일 · 취소)은 **진짜 쓰기 자리**를 지나 알람이 나오는지 본다. 보류 · 불량 · 수정 제작(다른 일꾼이 ``orders.py`` 에 거는 줄)은 약속 4 재료를
직접 넣는다.

되돌리면 실패: 완료한 사람 · 누른 사람 · 도면에 없는 사람에게 멈춤 · 옛 도면 key 줄로 작업 중 판정 · 막혀 있던 도면의 반영이 멈춤으로 감 ·
같은 주문에 안 누른 멈춤이 있는데 또 만듦 · 풀린 뒤에도 전체 화면이 남음 · 미뤄진 시공일에 띠 · 다른 공장 반장에게 띠 · 팀 알림 줄이
없을 때 알람을 안 보냄.
"""
from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest
from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from foms.api.drawing import erp_orders_drawing_fix as fix_api
from foms.services.notifications import production_change
from foms.services.production import floor_alarm
from foms.services.production import floor_alarm_text as T
from foms.services.production.floor_alarm_text import pulled_forward
from models import Order, User
from tests.support.production_factory_seed import factory_user
from tests.support.production_floor_alarm_seed import (
    SWITCH,
    TODAY,
    ack,
    alarm_order,
    alarms,
    capture,
    count_queries,
    fire,
    give,
    kinds,
    press,
    state_of,
    switch_on,
    who,
)
from tests.support.production_part_claim_seed import finish, login, make_user, mark

WHERE = "11/30 시공 · 정하늘"


@pytest.fixture
def floor(client, monkeypatch):
    """도면 3장 주문 — 김재단이 1번 재단 작업 중 · 오재단이 2번 재단 완료 · 박엣지가 2번 엣지 작업 중. 3번은 아무도 없다."""
    clock, wire = switch_on(monkeypatch), capture(monkeypatch)
    people = {"lead": make_user("박반장", lead=True), "kim": make_user("김재단", part="cut"),
              "oh": make_user("오재단", part="cut"), "park": make_user("박엣지", part="edge"),
              "draw": make_user("김도면", team="DRAWING"), "admin": make_user("관리", team="CS", role="ADMIN")}
    order = alarm_order(3)
    login(client, people["kim"])
    assert mark(client, order, 0, "cut", "take", "none").status_code == 200
    login(client, people["oh"])
    assert finish(client, order, 1, "cut").status_code == 200
    login(client, people["park"])
    assert mark(client, order, 1, "edge", "take", "none").status_code == 200
    assert alarms() == []  # 카드 누름 자체는 알람이 없다(#17 · #18 · #19)
    return {"order": order, "clock": clock, "wire": wire, "client": client, **people}


def _texts(uid: int) -> list[tuple[str, str, str]]:
    return [(n.notification_type[len(T.PREFIX):], n.title, n.message) for n in alarms(uid)]


def _patch_sd(order_id: int, fn) -> None:
    order = db_session.get(Order, order_id)
    sd = copy.deepcopy(order.structured_data)
    fn(sd)
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()


# --------------------------------------------------------------------------- #
# 보류 · 보류 풀림(#8 · #9) — 재료는 약속 4(다른 일꾼이 orders.py 에서 넣는다)
# --------------------------------------------------------------------------- #
def test_hold_stops_only_people_working_and_release_closes_it(floor):
    order, wire = floor["order"], floor["wire"]
    fire("hold", order, floor["lead"], reason="자재 기다림")
    expected = ("STOP_HOLD", "멈추세요 — 보류됐어요", f"{WHERE}\n박반장이 보류했어요. 사유: 자재 기다림")
    assert _texts(floor["kim"].id) == [expected] and _texts(floor["park"].id) == [expected]
    assert alarms(floor["oh"].id) == [] and alarms(floor["lead"].id) == [] and alarms(floor["admin"].id) == []  # 완료한 사람 · 본인 · 관리자
    assert all(n.is_urgent for n in alarms()) and len(wire.pushed) == 2
    kim_stop, park_stop = alarms(floor["kim"].id)[0], alarms(floor["park"].id)[0]
    ack(kim_stop.id)  # 김재단은 눌렀다 · 박엣지는 안 눌렀다
    wire.sent.clear()
    fire("hold_released", order, floor["lead"])
    band = ("NOTICE_HOLD_RELEASED", "보류가 풀렸어요 — 다시 작업하세요", "정하늘")
    assert _texts(floor["kim"].id)[-1] == band and _texts(floor["park"].id)[-1] == band
    assert state_of(park_stop.id).archived_at is not None and state_of(kim_stop.id).archived_at is None  # 안 누른 것만 닫는다
    closed = [body for body in wire.to(floor["park"].id) if body.get("floor_closed")]
    assert closed == [{"urgent": False, "floor_closed": True, "notification_ids": [park_stop.id]}]
    assert not [body for body in wire.to(floor["kim"].id) if body.get("floor_closed")]
    # 누른 사람이 작업 중인 사람이면 본인은 뺀다(내가 건 보류).
    fire("hold", order, floor["kim"])
    assert kinds(floor["kim"].id).count("STOP_HOLD") == 1 and kinds(floor["park"].id).count("STOP_HOLD") == 2
    assert alarms(floor["park"].id)[-1].message == f"{WHERE}\n김재단이 보류했어요."  # 사유가 없으면 사유 글도 없다


def test_release_sends_the_close_before_the_band_so_the_band_sound_plays(floor):
    """안 누른 멈춤 창을 닫으며 띠를 보낼 때는 닫기가 먼저 간다(11-28 실측 결함 — 띠가 먼저 가면 화면은 멈춤 소리가 울리는 중이라
    띠 소리를 건너뛰고 곧이어 창만 닫혀 띠 소리 0회). 되돌리면(띠 먼저) 실패."""
    order, wire = floor["order"], floor["wire"]
    fire("hold", order, floor["lead"], reason="자재 기다림")
    park_stop = alarms(floor["park"].id)[0]
    wire.sent.clear()
    fire("hold_released", order, floor["lead"])
    seen = [("closed", body["notification_ids"]) if body.get("floor_closed") else ("band", body.get("notification_type"))
            for body in wire.to(floor["park"].id)]
    assert seen == [("closed", [park_stop.id]), ("band", "PRODUCTION_FLOOR_NOTICE_HOLD_RELEASED")]


def _reads_of(kind: str, order, actor, **material) -> tuple[int, int]:
    """그 사건의 ``flush`` 가 낸 (읽기 수, 넣기 수)."""
    floor_alarm.note(db_session, kind, order.id, actor, **material)
    db_session.commit()
    _none, queries = count_queries(lambda: floor_alarm.flush(db_session))
    head = [q.lstrip().upper()[:6] for q in queries]
    return head.count("SELECT"), head.count("INSERT")


def test_stop_events_cost_a_fixed_number_of_reads(floor):
    """§4-10 — 멈춤 사건 한 번: 주문 1 + 표시 줄 1 + 사람 1(+ 앞 알람 찾기 1) + 받는 사람마다 넣기 3. 받는 사람 수와 상관없다."""
    order = floor["order"]
    lead = db_session.get(User, floor["lead"].id)
    assert _reads_of("hold", order, lead, reason="자재") == (3, 6)  # 받는 사람 둘
    assert _reads_of("drawing_revising", order, db_session.get(User, floor["draw"].id)) == (3, 0)  # 막힌 도면이 없어 받는 사람도 없다 — 사람은 안 읽는다

    def block_first(sd):
        sd["drawing_fix"] = {"fixing": {f"sheet:{sd['drawing_current_files'][0]['sheet_id']}": {"no": 1, "by_name": "김도면"}}}

    _patch_sd(order.id, block_first)
    assert _reads_of("drawing_revising", order, db_session.get(User, floor["draw"].id)) == (4, 3)  # 주문 · 앞 알람 · 표시 줄 · 사람 + 김재단 한 줄
    assert _reads_of("hold_released", order, db_session.get(User, floor["lead"].id)) == (3, 8)  # 주문 · 앞 알람 · 사람 + 띠 둘(6) · 닫기 둘(2)


# --------------------------------------------------------------------------- #
# 주문 취소 · 품목 취소 · 시공일(#10 · #12) — 생산 변경 알림 두 함수를 지나서
# --------------------------------------------------------------------------- #
def _change(order_id: int, kind: str, detail: str, actor) -> None:
    """지금 쓰기 자리들이 하는 차례 그대로 — 커밋 전 apply, 커밋, 커밋 뒤 finalize(팀 알림 줄 없이도 알람은 나간다)."""
    production_change.apply_production_change_alert(db_session, db_session.get(Order, order_id), kind, detail,
                                                    actor_user_id=actor.id, actor_name=actor.name)
    db_session.commit()
    production_change.finalize_production_change_alert(db_session, [], created_new=False)


def test_cancel_paths_stop_people_working(floor):
    order = floor["order"]
    _change(order.id, "cancelled", "", floor["admin"])
    stop = ("STOP_CANCELLED", "멈추세요 — 주문이 취소됐어요", f"{WHERE}\n더 만들지 말고 반장에게 알려 주세요.")
    assert _texts(floor["kim"].id) == [stop] and _texts(floor["park"].id) == [stop] and alarms(floor["oh"].id) == []
    _change(order.id, "item_cancel", "붙박이장 취소", floor["admin"])
    assert _texts(floor["kim"].id)[-1] == ("STOP_CANCELLED", "멈추세요 — 품목이 취소됐어요",
                                           f"{WHERE}\n어느 품목인지 반장에게 확인해 주세요.")
    # 바로 반영(drawing_hotfix)은 이 길에서 적지 않는다 — 옛 key 를 아는 전달 API 가 적는다(§6-3).
    before = len(alarms())
    _change(order.id, "drawing_hotfix", "도면 바뀜", floor["draw"])
    assert len(alarms()) == before


def test_pulled_forward_date_bands_the_factory_lead_only(floor):
    order, lead2 = floor["order"], factory_user("이반장", factory=2, lead=True)
    _change(order.id, "construction_date", "12/2 → 11/30", floor["admin"])
    assert _texts(floor["lead"].id) == [("NOTICE_DATE", "시공일이 당겨졌어요 — 12/2 → 11/30", "정하늘 · 남은 공정: 재단 · 엣지 · 조립 · 검수")]
    assert alarms(lead2.id) == [] and alarms(floor["kim"].id) == []  # 다른 공장 반장 · 작업자에게는 안 간다
    assert alarms(floor["lead"].id)[0].is_urgent is False
    _change(order.id, "construction_date", "11/29 → 11/30", floor["admin"])  # 미뤄짐
    far = alarm_order(1, build="2026-12-05")
    _change(far.id, "construction_date", "12/9 → 12/5", floor["admin"])  # 당겨졌지만 이틀 밖
    assert len(alarms()) == 1
    _change(order.id, "construction_date", "미정 → 11/30", floor["admin"])  # 글을 못 풀면 이틀 안일 때 낸다(§4-9 의 2)
    assert kinds(floor["lead"].id) == ["NOTICE_DATE", "NOTICE_DATE"]
    assert (pulled_forward("12/2 → 11/30", TODAY), pulled_forward("11/29 → 11/30", TODAY), pulled_forward("미정 → 11/30", TODAY),
            pulled_forward("1/3 → 12/30", TODAY)) == (True, False, None, True)  # 해 넘김: 1/3(내년) → 12/30(올해)


# --------------------------------------------------------------------------- #
# 불량 · 수정 제작(#13 · #14) — 그 공장 반장 띠
# --------------------------------------------------------------------------- #
def test_defect_and_rework_band_the_lead(floor):
    order, lead2 = floor["order"], factory_user("이반장", factory=2, lead=True)
    fire("defect", order, floor["park"], label="파손")
    assert _texts(floor["lead"].id) == [("NOTICE_DEFECT", "박엣지가 불량을 알렸어요 — 파손", "정하늘 · 11/30 시공")]
    assert alarms(lead2.id) == []
    fire("rework", order, floor["admin"], drawing_keys=list(order.keys[:2]), factories=[1])
    assert _texts(floor["lead"].id)[-1] == ("NOTICE_REWORK", "관리가 수정 제작으로 되돌렸어요 — 도면 2장", "정하늘 · 11/30 시공")
    fire("rework", order, floor["admin"], steps=["assemble", "inspect"], factories=[2])  # 도면 없는 주문 꼴 — 다시 할 칸
    assert _texts(lead2.id) == [("NOTICE_REWORK", "관리가 수정 제작으로 되돌렸어요 — 조립 · 검수", "정하늘 · 11/30 시공")]
    before = len(alarms())
    fire("rework", order, floor["lead"], drawing_keys=list(order.keys[:1]), factories=[1])  # 누른 반장 본인은 뺀다
    assert len(alarms()) == before


# --------------------------------------------------------------------------- #
# 도면 수정 중(#7) → 수정 취소(#20) — 도면팀 [수정 시작] · [수정 취소] API 를 지나서
# --------------------------------------------------------------------------- #
def _fix(client, order, verb: str, *indexes: int):
    return client.post(f"/api/orders/{order.id}/drawing/fix/{verb}", json={"targets": [{"key": order.keys[j]} for j in indexes]})


def test_fix_start_stops_the_worker_of_that_drawing_and_stop_closes_it(floor):
    order, client, wire = floor["order"], floor["client"], floor["wire"]
    login(client, floor["draw"])
    assert _fix(client, order, "start", 0).get_json()["data"]["changed"] is True
    assert _texts(floor["kim"].id) == [("STOP_REVISING", "멈추세요 — 도면을 고치는 중이에요",
                                        f"{WHERE} · 도면 1번\n도면팀 김도면이 고치고 있어요. 새 도면이 오면 알려 드려요.")]
    assert alarms(floor["park"].id) == [] and alarms(floor["oh"].id) == []  # 다른 도면 · 완료한 사람
    assert _fix(client, order, "start", 0).get_json()["data"]["changed"] is False  # 멱등 — 쓰기도 알람도 없다
    assert _fix(client, order, "start", 1).get_json()["data"]["changed"] is True
    assert kinds(floor["kim"].id) == ["STOP_REVISING"] and kinds(floor["park"].id) == ["STOP_REVISING"]
    ack(alarms(floor["park"].id)[0].id)  # 박엣지는 눌렀다
    wire.sent.clear()
    assert _fix(client, order, "stop", 0, 1).get_json()["data"]["changed"] is True
    kim_stop = alarms(floor["kim"].id)[0]
    assert state_of(kim_stop.id).archived_at is not None
    assert _texts(floor["kim"].id)[-1] == ("NOTICE_UNBLOCKED", "도면 수정이 취소됐어요 — 다시 작업하세요", "정하늘 · 도면 1번")
    assert kinds(floor["park"].id) == ["STOP_REVISING"]  # 이미 누른 사람에게는 띠가 없다(안 누른 멈춤이 닫힐 때만)
    assert {"urgent": False, "floor_closed": True, "notification_ids": [kim_stop.id]} in wire.to(floor["kim"].id)


def test_switch_off_adds_no_query_to_a_real_write_path(client, monkeypatch):
    """스위치가 꺼져 있으면 쓰기 길의 쿼리가 하나도 안 는다(§4-10) — 알람 거는 줄을 아예 뺀 것과 같은 수."""
    monkeypatch.delenv(SWITCH, raising=False)
    login(client, make_user("김도면", team="DRAWING"))
    counts = []
    for turn in ("몸 풀기", "스위치 꺼짐", "거는 줄 없음"):
        if turn == "거는 줄 없음":
            monkeypatch.setattr(fix_api, "floor_alarm", SimpleNamespace(note=lambda *a, **k: None, flush=lambda *a, **k: None))
        order = alarm_order(1)
        res, queries = count_queries(lambda: _fix(client, order, "start", 0))
        assert res.status_code == 200 and res.get_json()["data"]["changed"] is True
        counts.append(len(queries))
    assert counts[1] == counts[2] and alarms() == []


def test_factory_request_stops_coworkers_but_not_the_requester(floor):
    order, client = floor["order"], floor["client"]
    choi = make_user("최조립", part="assemble")
    login(client, choi)
    assert mark(client, order, 1, "assemble", "take", "none").status_code == 200
    login(client, floor["park"])
    res = client.post(f"/api/orders/{order.id}/production/drawing-request",
                      json={"note": "치수가 달라요", "targets": [{"key": order.keys[1]}]})
    assert res.status_code == 200, res.get_json()
    assert _texts(choi.id) == [("STOP_REVISING", "멈추세요 — 도면을 고치는 중이에요",
                                f"{WHERE} · 도면 2번\n박엣지가 도면 수정을 요청했어요. 새 도면이 오면 알려 드려요.")]
    assert alarms(floor["park"].id) == [] and alarms(floor["kim"].id) == []  # 요청한 본인 · 다른 도면
    # 반려(#15) — 요청한 사람 + 그 도면에서 멈춰 있던 사람.
    fire("fix_rejected", order, floor["draw"], numbers=[2], request_user_id=floor["park"].id, reason="치수 맞음")
    band = ("NOTICE_FIX_REJECTED", "도면 수정 요청이 반려됐어요 — 그대로 작업하세요", "정하늘 · 도면 2번 · 사유: 치수 맞음")
    assert _texts(floor["park"].id) == [band] and _texts(choi.id)[-1] == band and alarms(floor["kim"].id) == []


# --------------------------------------------------------------------------- #
# 도면이 새 도면으로 바뀜(#5 · #6 · #16) · 공장 옮김(#11)
# --------------------------------------------------------------------------- #
def _replace(order, *indexes: int) -> dict:
    """확정 도면 장을 새 key 로 바꾸고(옛 줄은 이력으로 남는다) 전달 API 가 넘기는 재료를 돌려준다."""
    old = copy.deepcopy(db_session.get(Order, order.id).structured_data["drawing_current_files"])
    new = [{**f, "key": f["key"] + ".v2"} if j in indexes else f for j, f in enumerate(old)]

    def swap(sd):
        sd["drawing_current_files"] = new
        sd.pop("drawing_fix", None)

    _patch_sd(order.id, swap)
    return floor_alarm.replaced_material(old, new, {"closed_requests": []})


def test_replaced_drawing_stops_workers_and_bands_finishers(floor):
    order = floor["order"]
    material = _replace(order, 0, 1)
    assert material["numbers"] == {order.keys[0]: 1, order.keys[1]: 2} and material["drawing_keys"] == list(order.keys[:2])
    fire("drawing_replaced", order, floor["draw"], **material)
    said = "도면팀 김도면이 새 도면을 보냈어요. 새 도면을 보고 다시 시작해 주세요."
    assert _texts(floor["kim"].id) == [("STOP_DRAWING", "멈추세요 — 도면이 바뀌었어요", f"{WHERE} · 도면 1번\n{said}")]
    assert _texts(floor["park"].id) == [("STOP_DRAWING", "멈추세요 — 도면이 바뀌었어요", f"{WHERE} · 도면 2번\n{said}")]
    assert _texts(floor["oh"].id) == [("NOTICE_DRAWING", "도면이 바뀌었어요 — 완료한 도면을 다시 봐 주세요", "정하늘 · 도면 2번")]
    # 옛 key 줄은 이력이다 — 그 뒤 보류는 새 도면을 아무도 안 맡았으니 받는 사람이 없다.
    before = len(alarms())
    fire("hold", order, floor["lead"], reason="자재")
    assert len(alarms()) == before


def test_replacement_of_a_blocked_drawing_is_a_band_not_a_stop(floor):
    order, client = floor["order"], floor["client"]
    login(client, floor["draw"])
    assert _fix(client, order, "start", 0).status_code == 200
    kim_stop = alarms(floor["kim"].id)[0]
    fire("drawing_replaced", order, floor["draw"], **{**_replace(order, 0), "request_user_id": floor["park"].id})
    band = ("NOTICE_FIX_APPLIED", "새 도면이 왔어요 — 다시 시작할 수 있어요", "정하늘 · 도면 1번")
    assert _texts(floor["kim"].id) == [("STOP_REVISING", kim_stop.title, kim_stop.message), band]  # #5 가 아니라 #16
    assert state_of(kim_stop.id).archived_at is not None  # 풀린 멈춤은 닫는다
    assert _texts(floor["park"].id) == [band]  # 수정 요청한 사람도 #16


def test_whole_order_block_lifted_by_a_replacement_bands_everyone_who_was_stopped(floor):
    """영업 수정 요청(주문 통째 막힘)으로 멈춘 사람 — 다른 도면이 바뀌어 막힘이 풀리면 멈춤을 닫고 띠를 준다(조용히 사라지지 않게)."""
    order = floor["order"]
    _patch_sd(order.id, lambda sd: sd.update(drawing_status="RETURNED"))
    _change(order.id, "drawing", "도면 수정요청", floor["admin"])  # 영업 수정 요청 자리(생산 변경 알림 '도면')
    assert kinds(floor["kim"].id) == ["STOP_REVISING"] and kinds(floor["park"].id) == ["STOP_REVISING"]
    assert alarms(floor["kim"].id)[0].message.endswith("관리가 도면 수정을 요청했어요. 새 도면이 오면 알려 드려요.")
    material = _replace(order, 2)  # 아무도 안 맡은 3번 도면만 바뀌고 주문 막힘이 풀린다
    _patch_sd(order.id, lambda sd: sd.update(drawing_status="CONFIRMED"))
    fire("drawing_replaced", order, floor["draw"], **material)
    assert _texts(floor["kim"].id)[-1] == ("NOTICE_FIX_APPLIED", "새 도면이 왔어요 — 다시 시작할 수 있어요", "정하늘 · 도면 1번")
    assert _texts(floor["park"].id)[-1][2] == "정하늘 · 도면 2번"
    assert all(state_of(n.id).archived_at is not None for n in alarms() if n.notification_type == T.STOP_REVISING)


def test_factory_move_stops_the_worker_of_the_moved_drawing(floor):
    order = floor["order"]
    fire("factory_moved", order, floor["draw"], drawing_keys=[order.keys[0]], to_factory=2)
    assert _texts(floor["kim"].id) == [("STOP_FACTORY", "멈추세요 — 2공장으로 옮겨졌어요",
                                        f"{WHERE} · 도면 1번\n2공장에서 작업하는 도면이에요.")]
    assert alarms(floor["park"].id) == []
    fire("factory_moved", order, floor["draw"], drawing_keys=[], to_factory=2)  # 안 보낸 시트만 옮김 — 받는 사람 없음
    assert len(alarms()) == 1


def test_real_factory_move_api_refuses_started_drawings_so_no_alarm(floor):
    """지금 서버는 일이 시작된 도면의 공장 옮김을 409 로 막는다 — #11 은 지금 규칙에서 받는 사람이 없다(설계서와 다른 현실)."""
    order, client = floor["order"], floor["client"]
    login(client, floor["draw"])
    refused = client.post(f"/api/orders/{order.id}/drawing/sheet-factory", json={"items": [{"key": order.keys[0], "factory": 2}]})
    assert refused.status_code == 409 and refused.get_json()["data"]["code"] == "SHEET_HAS_WORK"
    moved = client.post(f"/api/orders/{order.id}/drawing/sheet-factory", json={"items": [{"key": order.keys[2], "factory": 2}]})
    assert moved.status_code == 200 and alarms() == []


# --------------------------------------------------------------------------- #
# 담당 변경 '새 일' 알람 — 받은 사람이 그 파트 도면에서 다 빠지면 닫는다(§2-2)
# --------------------------------------------------------------------------- #
def test_new_job_alarm_closes_when_the_receiver_leaves(floor):
    order, wire = floor["order"], floor["wire"]
    give(order, 2, "cut", by=floor["lead"], src=None, to=floor["kim"])  # 김재단은 1번 재단을 진짜 작업 중
    give(order, 2, "edge", by=floor["lead"], src=None, to=floor["oh"])  # 오재단은 엣지 표시 줄이 없다
    kim_new, oh_new = alarms(floor["kim"].id)[0], alarms(floor["oh"].id)[0]
    wire.sent.clear()
    for person, part in ((floor["kim"], "cut"), (floor["oh"], "edge")):
        floor_alarm.note_mark(db_session, floor["lead"], press(order, 2, part, "remove"),
                              {"changed": True, "holders_before": [who(person, done=False)], "mark": {"holders": []}})
    db_session.commit()
    floor_alarm.flush(db_session)
    assert state_of(oh_new.id).archived_at is not None  # 그 파트 도면이 하나도 안 남았다
    assert state_of(kim_new.id).archived_at is None     # 아직 1번 재단을 작업 중이라 남긴다
    assert {"urgent": False, "floor_closed": True, "notification_ids": [oh_new.id]} in wire.to(floor["oh"].id)
    assert kinds(floor["oh"].id) == ["NEW_GIVEN", "NOTICE_START_CANCELLED"]
