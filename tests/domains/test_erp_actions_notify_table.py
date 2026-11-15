"""폰 알림 받는 사람 — 할 일 × 받는 사람 표(D215 · D217 · D221 · D223 · 점검 2차 w6-03).

못박는 것:
- '담당 먼저'(D215)는 그 담당이 그 제안을 **결정할 수 있을 때만**(:func:`foms.services.erp_actions.access.can_settle` — 감싼 본체도
  받는 사람) 팀을 건너뛴다. 도면 담당 맡기기는 담당 영업이 결정할 수 없어(본체 — 관리자 · 도면팀 · 지정 도면 담당만) 도면팀(D221)에 간다.
- 결정 못 하는 담당도 볼 수 있으면 그대로 받는다(D217 '보이고 폰 알림도 가며 누르면 막힘'). 관리자는 늘 받는다(D221).
- 담당이 없으면 할 일의 팀들(D221 · D223). 사람만 할 일(주문 취소)은 아무도 받지 않는다.
폰으로는 보내지 않는다(받는 사람 판정 :func:`notify.recipients` 만 부른다). 합성 사람 · 주문만.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.erp_actions import notify
from foms.services.erp_actions.access import can_run, can_settle
from foms.services.erp_actions.registry import ACTIONS
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.graft_flags import FLAGS
from models import Order, User

MANAGER = "가짜영업담당"
#: 할 일 → (담당 영업이 있을 때, 담당이 없을 때) 받는 무리 — 'manager' · 'admin' · 팀 이름(그 팀 사람 모두, 번호 순).
TABLE: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "schedule_construction": (("manager", "admin"), ("admin", "SALES", "SHIPMENT")),
    "move_construction": (("manager", "admin"), ("admin", "SALES", "SHIPMENT")),
    "schedule_as_visit": (("manager", "admin"), ("admin", "SALES", "CS")),  # D223
    "register_as": (("manager", "admin"), ("admin", "SALES", "CS")),
    "send_measure_alimtalk": (("manager", "admin"), ("admin", "SALES", "CS")),
    "add_construction_note": (("manager", "admin"), ("admin", "SALES", "CS")),
    "advance_stage": (("manager", "admin"), ("admin", "SALES", "CS")),
    "assign_draftsman": (("manager", "admin", "DRAWING"), ("admin", "DRAWING")),  # w6-03 — 담당 영업은 결정 못 함
    "move_measurement": (("manager", "admin"), ("admin", "SALES", "CS")),
    "send_construction_alimtalk": (("manager", "admin"), ("admin", "SALES", "CS")),
    "cancel_order": ((), ()),  # 사람만 — 제안 길이 없다
}


@pytest.fixture
def people(app, monkeypatch):
    """접목판 스위치를 끈 뒤 화면 · 할 일만 켠다 — 영업 담당 · 팀마다 한 사람 · 관리자(합성)."""
    for env in FLAGS.values():
        monkeypatch.delenv(f"{env}_ENABLED", raising=False)
        monkeypatch.delenv(f"{env}_COHORT", raising=False)
    for short in ("brain_ui", "actions"):
        monkeypatch.setenv(f"{FLAGS[short]}_ENABLED", "1")
        monkeypatch.setenv(f"{FLAGS[short]}_COHORT", "all")
    made: dict[str, int] = {}
    for key, role, team, name in (("manager", "STAFF", "SALES", MANAGER), ("SALES", "STAFF", "SALES", "가짜영업"),
                                  ("CS", "STAFF", "CS", "가짜상담"), ("SHIPMENT", "STAFF", "SHIPMENT", "가짜출고"),
                                  ("DRAWING", "STAFF", "DRAWING", "가짜도면"), ("admin", "ADMIN", None, "가짜관리자")):
        user = User(username=f"tbl_{key.lower()}", password=generate_password_hash("pw"), role=role, team=team, name=name,
                    is_active=True)
        db_session.add(user)
        db_session.commit()
        made[key] = user.id
    yield made
    db_session.rollback()


def _order(manager: str | None) -> Order:
    sd = {"workflow": {"stage": "PRODUCTION"}, "parties": {"customer": {"name": "합성손님"}}}
    if manager:
        sd["parties"]["manager"] = {"name": manager}
    order = Order(received_date="2030-01-01", customer_name="합성손님", phone="010-0000-0000", address="합성 주소",
                  product="합성 품목", status="PRODUCTION", is_erp_order=True, structured_data=sd, manager_name=manager)
    sync_erp_flat_columns(order, sd)
    db_session.add(order)
    db_session.commit()
    return order


def _expected(groups: tuple[str, ...], made: dict[str, int], with_manager: bool) -> list[int]:
    """무리 이름 → 번호(무리 차례 · 팀 안은 번호 순 · 겹침 한 번). 담당이 없으면 담당 영업도 그냥 영업팀 사람이다."""
    teams = {"SALES": ["SALES"] if with_manager else ["manager", "SALES"], "CS": ["CS"], "SHIPMENT": ["SHIPMENT"],
             "DRAWING": ["DRAWING"]}
    out: list[int] = []
    team_ids = sorted(made[key] for group in groups if group in teams for key in teams[group])
    for group in groups:
        ids = [made[group]] if group in ("manager", "admin") else []
        out.extend(uid for uid in ids if uid not in out)
    out.extend(uid for uid in team_ids if uid not in out)
    return out


def test_the_table_covers_every_action():
    assert set(TABLE) == set(ACTIONS)


@pytest.mark.parametrize("action", list(TABLE))
@pytest.mark.parametrize("with_manager", [True, False])
def test_who_gets_the_phone_alert_for_each_action(people, action, with_manager):
    order = _order(MANAGER if with_manager else None)
    got = notify.recipients(db_session, SimpleNamespace(action=action, order_id=order.id))
    assert got == _expected(TABLE[action][0 if with_manager else 1], people, with_manager), action


def test_a_drawing_manager_who_can_decide_keeps_the_team_out(people):
    """대조군 — 도면 담당 맡기기라도 결정할 수 있는 담당(도면팀 사람)이 담당이면 '담당 먼저' 그대로(팀은 받지 않는다)."""
    order = _order("가짜도면")
    got = notify.recipients(db_session, SimpleNamespace(action="assign_draftsman", order_id=order.id))
    assert got == [people["DRAWING"], people["admin"]]


def test_can_settle_follows_the_wrapped_bodies(people):
    order = _order(MANAGER)
    users = {key: db_session.get(User, uid) for key, uid in people.items()}
    spec = ACTIONS["assign_draftsman"]
    assert can_run(users["manager"], spec, order) and not can_settle(users["manager"], spec, order)  # D217 — 보이되 결정 못 함
    assert can_settle(users["DRAWING"], spec, order) and can_settle(users["admin"], spec, order)
    for name in ("schedule_construction", "advance_stage", "move_measurement", "register_as"):
        assert can_settle(users["manager"], ACTIONS[name], order), name
    assert not can_settle(users["manager"], ACTIONS["cancel_order"], order)
