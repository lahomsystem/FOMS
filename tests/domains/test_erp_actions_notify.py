"""새 ERP 할 일 제안 → 승인할 사람 폰 알림(설계서 2026-11-14-foms-graft 3.14 · D210 · D215).

완료 기준:
- 스위치 ``FOMS_GRAFT_PUSH`` 가 꺼지면 알림 줄 0(지금과 같다) · 켜지면 받는 사람마다 ``ERP_ACTION_PROPOSAL`` 한 줄 + 받는 사람 상태.
- 받는 사람(D215): 주문 담당 먼저(승인할 수 없는 담당은 빠짐) → 그런 담당이 없으면 할 일의 팀 · 프리랜서는 남의 주문에서 빠짐 ·
  ``actions`` 스위치가 꺼진 사람 빠짐 · 20명 상한 · 0명이면 아무것도 안 만듦(제안은 생김).
- 겹친 제안(``propose`` 가 ``None``)은 알림 0 · 알림 만들기가 실패해도 제안은 생김(저장점만 되감김).
- 폰 보내기 줄 세우기는 **진짜 커밋 뒤에만** — 저장점 풀기 · 되감기 · 커밋 전에는 0.
- 알림 줄 · 잠금화면 글에 손님 이름 · 날짜가 없다.
**폰으로는 보내지 않는다** — 줄 세우기 함수(``enqueue_push_for_notification``)는 모든 시험에서 가짜다. 합성 사람 · 주문만.
"""

from __future__ import annotations

import datetime

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.persistence.graft.models import ErpActionProposal
from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.erp_actions import notify
from foms.services.erp_actions.lifecycle import propose
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.graft_flags import FLAGS
from foms.services.notifications import push_sender
from models import Notification, NotificationUserState, Order, User

CUSTOMER = "합성손님"


def _day(offset: int) -> str:
    return (get_today_kst() + datetime.timedelta(days=offset)).isoformat()


@pytest.fixture(autouse=True)
def world(app, monkeypatch):
    """접목판 스위치를 모두 끈 뒤 화면 · 할 일 · 폰 알림만 켠다. 폰 보내기 줄 세우기는 가짜(부른 번호만 모은다)."""
    for env in FLAGS.values():
        monkeypatch.delenv(f"{env}_ENABLED", raising=False)
        monkeypatch.delenv(f"{env}_COHORT", raising=False)
    for short in ("brain_ui", "actions"):
        monkeypatch.setenv(f"{FLAGS[short]}_ENABLED", "1")
        monkeypatch.setenv(f"{FLAGS[short]}_COHORT", "all")
    monkeypatch.setenv("FOMS_GRAFT_PUSH_ENABLED", "1")
    queued: list[int] = []
    monkeypatch.setattr(notify, "enqueue_push_for_notification",
                        lambda notification_id, db=None: (queued.append(notification_id), {"enqueued": True})[1])
    yield queued
    db_session.rollback()


_seq = iter(range(1, 10_000))


def _user(role: str = "STAFF", team: str | None = "SALES", name: str | None = None, active: bool = True) -> User:
    number = next(_seq)
    user = User(username=f"nt_user_{number}", password=generate_password_hash("pw"), role=role, team=team,
                name=name or f"가짜직원{number}", is_active=active)
    db_session.add(user)
    db_session.commit()
    return user


def _order(manager: str | None = None, stage: str = "PRODUCTION") -> Order:
    sd = {"workflow": {"stage": stage}, "parties": {"customer": {"name": CUSTOMER, "phone": "010-0000-0002"}}}
    if manager:
        sd["parties"]["manager"] = {"name": manager}
    order = Order(received_date="2030-01-01", customer_name=CUSTOMER, phone="010-0000-0000", address="합성 주소",
                  product="합성 품목", status=stage, is_erp_order=True, structured_data=sd, manager_name=manager)
    sync_erp_flat_columns(order, sd)
    db_session.add(order)
    db_session.commit()
    return order


def _propose(order: Order, *, date: int = 10, commit: bool = True) -> ErpActionProposal | None:
    row = propose(db_session, action="schedule_construction", proposed_by="agent:schedule", order=order,
                  params={"date": _day(date), "time": "오전"}, reason="합성 이유", evidence=[], source_kind="sweep",
                  source_ref="1", level=2, now=now_utc_naive())
    if commit:
        db_session.commit()
    return row


def _notes() -> list[Notification]:
    return (db_session.query(Notification).filter(Notification.notification_type == "ERP_ACTION_PROPOSAL")
            .order_by(Notification.id).all())


def _targets() -> list[int]:
    return [note.target_user_id for note in _notes()]


# ── 스위치 ───────────────────────────────────────────────────────────────
def test_switch_off_makes_no_notification(world, monkeypatch):
    monkeypatch.delenv("FOMS_GRAFT_PUSH_ENABLED")
    manager = _user(name="가짜담당")
    row = _propose(_order(manager="가짜담당"))
    assert row is not None and row.status == "open"
    assert _notes() == [] and world == [] and manager.id is not None


# ── 받는 사람 ────────────────────────────────────────────────────────────
def test_order_manager_gets_one_line_with_state_and_no_private_text(world):
    manager = _user(name="가짜담당")
    _user(team="SHIPMENT")  # 팀 사람은 담당이 있으면 받지 않는다
    row = _propose(_order(manager="가짜담당"))
    (note,) = _notes()
    assert (note.target_type, note.target_user_id, note.order_id, note.is_urgent) == ("USER", manager.id, row.order_id,
                                                                                      False)
    assert note.title == "AI 제안 승인 대기" and note.message == f"시공 잡기 · 주문 #{row.order_id} · 제안 #{row.id}"
    assert note.created_by_name == "일정 AI"
    states = db_session.query(NotificationUserState).filter(NotificationUserState.notification_id == note.id).all()
    assert [state.user_id for state in states] == [manager.id]
    payload = push_sender._build_payload(note, CUSTOMER)
    assert payload["body"] == f"시공 잡기 · 주문 #{row.order_id}" and CUSTOMER not in str(payload)
    assert _day(10) not in str(payload) and _day(10) not in note.message and CUSTOMER not in note.message
    assert payload["data"]["deep_link"] == f"/brain?tab=inbox&proposal={row.id}"
    assert world == [note.id]  # 커밋 뒤 한 번


def test_no_manager_goes_to_the_action_team(world):
    first, second = _user(team="SHIPMENT"), _user(team="SHIPMENT")
    _user(team="DRAWING")  # 다른 팀
    _user(team="SHIPMENT", active=False)  # 꺼진 계정
    _user(role="VIEWER", team="SHIPMENT")  # 조회 전용 — 승인할 수 없다
    _propose(_order())
    assert _targets() == sorted([first.id, second.id])


def test_manager_who_cannot_approve_is_dropped_and_the_team_gets_it(world):
    _user(team="PRODUCTION", name="가짜생산담당")  # 시공일 쓰기 정책을 못 지난다
    shipment = _user(team="SHIPMENT")
    _propose(_order(manager="가짜생산담당"))
    assert _targets() == [shipment.id]


def test_manager_without_the_actions_switch_is_dropped(world, monkeypatch):
    manager = _user(name="가짜담당")
    shipment = _user(team="SHIPMENT")
    monkeypatch.setenv("FOMS_GRAFT_ACTIONS_COHORT", str(shipment.id))  # 담당은 할 일 스위치 밖
    _propose(_order(manager="가짜담당"))
    assert _targets() == [shipment.id] and manager.id not in _targets()


def test_freelancer_gets_only_own_orders(world):
    """켜진 프리랜서(영업팀) — 자기 주문(담당 이름 → 저장 훅이 연결 줄을 만든다)은 받고, 팀으로 넘어간 남의 주문은 받지 않는다."""
    from foms.services.sales_commission.settings import load_settings, save_freelancer

    freelancer = _user(name="가짜프리담당")
    save_freelancer(db_session, freelancer.id, {"match_name": "가짜프리담당", "start_month": "2020-01", "tax_type": "NONE",
                                                "active": True},
                    base_version=load_settings(db_session)[0], actor_user_id=None)
    db_session.commit()
    sales = _user(team="SALES")  # 대조군 — 같은 팀의 프리랜서 아닌 직원

    def _measure_proposal(order):
        return propose(db_session, action="move_measurement", proposed_by="agent:cs", order=order,
                       params={"date": _day(5)}, reason="합성 이유", evidence=[], source_kind="cs_turn",
                       source_ref="1", level=2, now=now_utc_naive())

    own = _measure_proposal(_order(manager="가짜프리담당", stage="MEASURE"))
    db_session.commit()
    assert [n.target_user_id for n in _notes() if n.order_id == own.order_id] == [freelancer.id]
    other = _measure_proposal(_order(stage="MEASURE"))  # 담당 없음 → 영업팀 — 남의 주문
    db_session.commit()
    assert [n.target_user_id for n in _notes() if n.order_id == other.order_id] == [sales.id]


def test_twenty_people_at_most(world):
    team = [_user(team="SHIPMENT") for _ in range(notify.MAX_RECIPIENTS + 5)]
    _propose(_order())
    assert _targets() == sorted(user.id for user in team)[: notify.MAX_RECIPIENTS]
    assert len(world) == notify.MAX_RECIPIENTS


def test_nobody_to_tell_makes_nothing_but_the_proposal(world):
    _user(team="DRAWING")
    row = _propose(_order())
    assert row is not None and db_session.get(ErpActionProposal, row.id).status == "open"
    assert _notes() == [] and world == []


# ── 겹침 · 실패 ──────────────────────────────────────────────────────────
def test_duplicate_proposal_sends_nothing_more(world):
    _user(name="가짜담당")
    order = _order(manager="가짜담당")
    assert _propose(order) is not None and len(_notes()) == 1
    assert _propose(order) is None  # 같은 열쇠 — 겹침
    assert len(_notes()) == 1 and len(world) == 1


def test_notification_failure_keeps_the_proposal(world, monkeypatch):
    _user(name="가짜담당")

    def _boom(*args, **kwargs):
        raise RuntimeError("합성 실패")

    monkeypatch.setattr(notify, "fan_out_new_notification", _boom)
    row = _propose(_order(manager="가짜담당"))
    assert row is not None
    db_session.expire_all()
    assert db_session.get(ErpActionProposal, row.id).status == "open"
    assert _notes() == [] and world == []  # 저장점만 되감겼다


# ── 커밋 뒤에만 ──────────────────────────────────────────────────────────
def test_queue_waits_for_the_real_commit(world):
    _user(name="가짜담당")
    order = _order(manager="가짜담당")
    row = _propose(order, commit=False)
    assert row is not None and len(_notes()) == 1 and world == []  # 커밋 전 — 줄 세우지 않음
    with db_session.begin_nested():  # 저장점 풀기도 '커밋' 사건을 내지만 진짜 커밋이 아니다
        pass
    assert world == []
    db_session.commit()
    assert world == [_notes()[0].id]
    db_session.commit()
    assert len(world) == 1  # 한 번만


def test_rolled_back_proposal_never_queues(world):
    _user(name="가짜담당")
    order = _order(manager="가짜담당")
    # 시험 DB(pysqlite)는 쓰기 전에는 BEGIN 을 내지 않아 첫 저장점 풀기가 곧 커밋이 된다 — 쓰기 하나로 트랜잭션을 먼저 연다
    # (운영 PostgreSQL 은 늘 BEGIN 안에서 저장점을 쓴다).
    db_session.add(User(username="nt_tx_opener", password="x", role="STAFF", name="가짜여는줄", is_active=False))
    db_session.flush()
    assert _propose(order, commit=False) is not None
    db_session.rollback()
    assert _notes() == [] and world == []
    db_session.commit()
    assert world == []  # 버린 번호가 다음 커밋으로 새지 않는다
