"""'바뀐 것'에서 "도면 수정 취소" 줄이 가끔 빠지던 결함 — 단계 쓰기가 같이 남긴 줄은 단계 시각과 같은 때여도 '뒤'다(2026-11-28).

들어온 길 기록(단계 이동 이벤트)이 없는 주문은 '바뀐 것' 창 시작이 ``erp_stage_updated_at``(마지막 단계 쓰기의 시각)이다. 생산에서 나가는
쓰기는 그 단계 시각을 먼저 읽고, 같이 남기는 "도면 수정 취소" 이벤트는 그 뒤(flush 때) 시각이 찍힌다 — 시계를 두 번 읽는다. 시계 눈금
(Windows 는 0.3 ~ 16ms)이 그 사이보다 굵으면 두 시각이 같아지고, 옛 판정(``ts <= 창 시작`` 이면 빠짐)은 그 줄을 '들어오기 전'으로 쳐서 버렸다
(가끔 실패하던 ``test_admin_punched_production_complete_releases_in_the_same_write`` 의 뿌리 — 재 보니 같은 때 24번 모두 빠지고 다른 때
16번 모두 보였다).

고친 뒤: 그 줄이 **주문의 지금 단계를 만든 단계 쓰기가 남긴 것**인지를 적어 둔 표지(이벤트 payload ``via: stage_exit`` + ``to`` = 지금 단계)로
읽는다 — 시각이 같아도 '뒤'로 본다. 규칙은 그대로: 그 밖 줄은 창 시작과 같은 때면 '앞'(빠짐), 생산에 들어온 뒤 바뀐 것만 알린다.

이 파일은 시계를 한 시각에 세워 놓고(:func:`clock`) 누른다 — 옛 코드에서는 늘 실패하고 고친 코드에서는 늘 통과한다(sleep · 재시도 없음).

되돌리면 실패: 같은 시각에 찍힌 단계 나감 줄이 '바뀐 것'에서 빠짐 / 표지 없는 줄 · 옛 머묾의 줄이 같은 때에 보임 / 확인한 줄이 다시 시끄러움.
이름은 모두 지어낸 값이다.
"""
from __future__ import annotations

import datetime

import pytest
from sqlalchemy import event

from db import db_session
from foms.api.orders import field_update
from foms.services.orders import order_transition_service, stage_override
from foms.services.orders.drawing_fix_marks import FIX_STOPPED_EVENT, VIA_STAGE_EXIT
from foms.services.production_change_alerts import (
    SHEET_FACTORY_CHANGE_EVENT,
    _build_change_lists,
    collect_production_change_alerts,
    compute_window_start,
)
from models import Order, OrderEvent
from tests.domains.test_drawing_fix_stage_exit import _fixing_order
from tests.support.drawing_fix_workbench_seed import login, people
from tests.support.production_steps_seed import mark_order_inspected

T = datetime.datetime(2026, 11, 28, 1, 0, 0, 123456)
LINE = "도면 수정 취소"


class _Clock:
    """세워 둔 시계 — ``at`` 을 바꾸면 그때부터 그 시각을 읽는다."""

    at = T


@pytest.fixture
def clock(monkeypatch):
    """단계 쓰기가 읽는 시계 셋(전이 엔진 · 강제 단계 변경 · 칸 하나 고치기)과 이벤트 시각 기본값을 한 시각에 세운다 — 시계 눈금 하나 안에
    단계 시각과 이벤트 시각이 든 꼴.

    이벤트 시각은 칸 기본값(``default=now_utc_naive``)을 바꿔 끼우지 않고 넣기 직전(``before_insert``)에 적는다 — SQLAlchemy 가 한 번
    짠 INSERT 에 기본값 함수를 붙들어 두어, 다른 시험이 먼저 돈 뒤에는 바꿔 끼운 기본값이 안 먹고 실제 시각이 찍힌다(재서 확인).
    """
    held = _Clock()
    for module in (order_transition_service, stage_override, field_update):
        monkeypatch.setattr(module, "now_utc_naive", lambda: held.at)

    def _stamp(_mapper, _connection, target) -> None:
        if target.created_at is None:
            target.created_at = held.at

    event.listen(OrderEvent, "before_insert", _stamp)
    yield held
    event.remove(OrderEvent, "before_insert", _stamp)


@pytest.fixture
def who():
    return people()


def _changes(oid: int, user_id: int | None = None) -> dict:
    db_session.expire_all()
    return collect_production_change_alerts(db_session, [db_session.get(Order, oid)], user_id)[oid]


def _lines(items: list[dict]) -> list[tuple[str, str, str]]:
    return [(i["label"], i["detail"], i["by_name"]) for i in items if i["label"] == LINE]


def _assert_same_tick(oid: int) -> None:
    """준비물 확인 — 창 시작이 그 단계 쓰기의 시각이고, 같이 남긴 줄도 정말 같은 시각을 적었다."""
    db_session.expire_all()
    order = db_session.get(Order, oid)
    events = db_session.query(OrderEvent).filter_by(order_id=oid).all()
    [stop] = [e for e in events if e.event_type == FIX_STOPPED_EVENT]
    assert stop.created_at == order.erp_stage_updated_at == compute_window_start(order, events, None) == T
    assert stop.payload["via"] == VIA_STAGE_EXIT and stop.payload["to"] == order.erp_stage_code


def _complete(client, oid: int) -> None:
    mark_order_inspected(oid)
    res = client.post(f"/api/orders/{oid}/production/complete", json={"admin_override": True, "override_reason": "시험 — 같은 시각"})
    assert res.status_code == 200, res.get_json()


def _override(client, oid: int, to_stage: str) -> None:
    res = client.post(f"/api/orders/{oid}/workflow/stage-override",
                      json={"to_stage": to_stage, "reason": "시험 — 같은 시각에 단계 옮김", "confirm": True})
    assert res.status_code == 200, res.get_json()


def _field_to_construction(client, oid: int) -> None:
    res = client.post("/api/update_order_field", json={"order_id": oid, "field": "status", "value": "CONSTRUCTION"})
    assert res.status_code == 200, res.get_json()


# --------------------------------------------------------------------------- #
# 재현 — 단계 시각과 같은 시각에 찍힌 "도면 수정 취소" 줄이 '바뀐 것'에 남는다(길마다)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("leave", [
    _complete,                                              # 제작 완료(전이 엔진) — 가끔 실패하던 시험의 길
    lambda client, oid: _override(client, oid, "CONFIRM"),  # 강제 단계 변경으로 컨펌에 되돌림
    _field_to_construction,                                 # 칸 하나 고치기 — 단계 이동 이벤트를 안 남기는 길
], ids=["complete", "override_to_confirm", "field_status"])
def test_stage_exit_line_stamped_in_the_same_tick_is_shown(client, who, clock, leave):
    oid = _fixing_order()
    login(client, who.admin)
    leave(client, oid)
    _assert_same_tick(oid)
    got = _changes(oid)
    assert _lines(got["alerts"]) == _lines(got["history"]) == [(LINE, "도면 2", who.admin.name)]
    assert _lines(_changes(oid, who.lead.id)["alerts"]) == [(LINE, "도면 2", who.admin.name)]  # 확인 안 한 사람에게도 같다


# --------------------------------------------------------------------------- #
# 규칙은 그대로 — 확인하면 조용해지고, 옛 머묾의 줄 · 표지 없는 줄은 같은 때에 안 보인다
# --------------------------------------------------------------------------- #
def test_ack_after_the_line_quiets_it_only_for_that_person(client, who, clock):
    oid = _fixing_order()
    login(client, who.admin)
    _complete(client, oid)
    _assert_same_tick(oid)
    clock.at = T + datetime.timedelta(seconds=30)
    login(client, who.lead)
    assert client.post(f"/api/orders/{oid}/production/change-ack", json={}).status_code == 200
    mine, other = _changes(oid, who.lead.id), _changes(oid, who.admin.id)
    assert _lines(mine["alerts"]) == [] and _lines(mine["history"]) == [(LINE, "도면 2", who.admin.name)]
    assert _lines(other["alerts"]) == [(LINE, "도면 2", who.admin.name)]


def test_line_from_an_earlier_stay_is_not_shown_after_coming_back_in_the_same_tick(client, who, clock):
    """생산 → 컨펌(줄) → 다시 생산이 모두 같은 시각 — 그 줄은 지금 머묾보다 앞이다(``to`` 가 지금 단계가 아니다 → 같은 때 = 앞)."""
    oid = _fixing_order()
    login(client, who.admin)
    _override(client, oid, "CONFIRM")
    _override(client, oid, "PRODUCTION")
    db_session.expire_all()
    order = db_session.get(Order, oid)
    events = db_session.query(OrderEvent).filter_by(order_id=oid).all()
    assert order.erp_stage_code == "PRODUCTION" and compute_window_start(order, events, None) == T  # 준비물 — 들어온 때도 같은 시각
    got = _changes(oid)
    assert _lines(got["alerts"]) == _lines(got["history"]) == []


def _event(event_type: str, payload: dict, at: datetime.datetime) -> OrderEvent:
    return OrderEvent(order_id=1, event_type=event_type, payload=payload, created_at=at, created_by_user_id=9)


def _exit_line(at: datetime.datetime, to: str = "CONSTRUCTION") -> OrderEvent:
    return _event(FIX_STOPPED_EVENT, {"numbers": [2], "by_name": "한관리", "via": VIA_STAGE_EXIT, "to": to}, at)


def _labels(events: list[OrderEvent], stage: str = "CONSTRUCTION", acked_at: datetime.datetime | None = None,
            ack_window: datetime.datetime = T) -> tuple[list[str], list[str]]:
    extra = () if acked_at is None else (acked_at,)  # 확인한 때가 없으면 옛 꼴(인자 넷) 그대로 부른다
    alerts, history = _build_change_lists(events, {"workflow": {"stage": stage}}, T, ack_window, *extra)
    return [a["label"] for a in alerts], [h["label"] for h in history]


def test_tie_with_the_window_start_still_drops_every_unmarked_line():
    """대조군 — 표지 없는 줄(시공일 · 단추로 누른 [수정 취소] · 공장 바뀜 · 도면 이력)은 창 시작과 같은 때면 전과 같이 빠진다."""
    second = T.replace(microsecond=0)  # 도면 이력은 초까지만 적는다 — 창 시작도 그 초에 맞춰 같은 때를 만든다
    payloads = [
        ("CONSTRUCTION_DATE_CHANGED", {"from": "2026-12-01", "to": "2026-12-03"}),
        (FIX_STOPPED_EVENT, {"numbers": [2], "by_name": "김도면"}),
        (SHEET_FACTORY_CHANGE_EVENT, {"changes": [{"index": 1, "total": 2, "from": 1, "to": 2}]}),
    ]
    sd = {"workflow": {"stage": "CONSTRUCTION"},
          "drawing_transfer_history": [{"action": "TRANSFER", "transferred_at": second.strftime("%Y-%m-%d %H:%M:%S")}]}
    tied = [_event(kind, payload, second) for kind, payload in payloads]
    assert _build_change_lists(tied, sd, second, second) == ([], [])
    later = [_event(kind, payload, T + datetime.timedelta(microseconds=1)) for kind, payload in payloads]
    assert _labels(later) == (["시공일 변경", LINE, "공장 바뀜"], ["시공일 변경", LINE, "공장 바뀜"])  # 한 눈금 뒤면 보인다


def test_marked_line_is_judged_by_the_mark_only_on_a_tie():
    before = T - datetime.timedelta(microseconds=1)
    assert _labels([_exit_line(T)]) == ([LINE], [LINE])                                  # 같은 때 + 지금 단계를 만든 쓰기 → 뒤
    assert _labels([_exit_line(before)]) == ([], [])                                     # 창 시작보다 앞이면 표지가 있어도 빠진다
    assert _labels([_exit_line(T, to="CONFIRM")], stage="PRODUCTION") == ([], [])        # 옛 머묾이 남긴 줄(지금 단계가 아님) → 앞
    assert _labels([_exit_line(T, to="CONSTRUCTION")], stage="시공") == ([LINE], [LINE])  # 한글로 적힌 옛 단계 값도 같은 단계다
    assert _labels([_exit_line(T, to="")], stage="") == ([], [])                         # 단계를 모르면 표지로 치지 않는다


def test_marked_line_goes_quiet_only_by_a_real_ack():
    after = T + datetime.timedelta(seconds=5)
    assert _labels([_exit_line(T)], acked_at=after, ack_window=after) == ([], [LINE])    # 본인이 그 뒤에 확인 → 이력에만
    assert _labels([_exit_line(T)], acked_at=T, ack_window=T) == ([], [LINE])            # 확인과 같은 때 = 확인한 것(전과 같다)
    assert _labels([_exit_line(after)], acked_at=T, ack_window=T) == ([LINE], [LINE])    # 확인 뒤에 생긴 줄은 다시 알린다
    plain = _event(FIX_STOPPED_EVENT, {"numbers": [2], "by_name": "김도면"}, after)       # 표지 없는 줄은 확인한 때를 줘도 전과 같이 창으로
    assert _labels([plain], acked_at=T, ack_window=after) == ([], [LINE])
