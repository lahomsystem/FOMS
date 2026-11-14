"""ERP 할 일 제안 권한(설계서 2026-11-14-foms-graft 3.5 · 7) — 보는 사람 = 그 할 일을 실행할 수 있는 사람.

- 할 일 정책 판정표(역할 · 팀마다 실행할 수 있는 할 일) — 조회 전용(VIEWER)은 정책과 상관없이 아무것도 못 한다.
- 정책을 못 넘는 할 일의 제안은 수 · 칩 · 카드 0, 자세히 · 승인 · 거절 · 나중에 404(제안은 그대로).
- VIEWER 404 · 협력사(앞 문지기가 막음 — 답에 제안이 없다) · 꺼진 계정 401 · 스위치 밖 사람 404.
- 프리랜서: 앞 문지기가 이 길을 막는다(403). 서비스 판정은 자기 주문(연결 표)만 — 남의 주문 제안은 결정도 못 한다.
- 감사 줄에 손님 이름 · 전화 · 이유 글이 없다. 근거 칩 가운데 볼 수 없는 회사 지식은 빠진다.
합성 계정 · 합성 주문 · 합성 글만.
"""

from __future__ import annotations

import datetime

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.persistence.graft.models import ErpActionProposal
from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.erp_actions import views
from foms.services.erp_actions.access import actions_viewer, can_run, runnable_actions
from foms.services.erp_actions.lifecycle import ActionError, approve, propose, reject
from foms.services.erp_actions.registry import ACTIONS
from foms.services.erp_actions.runners import RunOutcome
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.graft_flags import FLAGS
from models import Order, OrderFreelancerLink, PartnerOrg, SecurityLog, SystemSetting, User
from tests.support.brain_support import create

BASE = "/api/erp-actions"
CUSTOMER, PHONE, REASON = "합성손님", "010-0000-0000", "손님이 토요일이 좋다고 적음"
ALL = tuple(name for name, spec in ACTIONS.items() if spec.mode != "human")
SCHEDULE = ("schedule_construction", "move_construction")
STAFF_ONLY = ("send_measure_alimtalk", "advance_stage", "assign_draftsman", "send_construction_alimtalk")
MATRIX = {
    ("ADMIN", None): ALL, ("STAFF", "CS"): ALL, ("STAFF", "SALES"): ALL, ("STAFF", "ACCOUNTING"): ALL,
    ("MANAGER", "PRODUCTION"): tuple(a for a in ALL if a not in SCHEDULE),
    ("STAFF", "SHIPMENT"): SCHEDULE + STAFF_ONLY,
    ("STAFF", "CONSTRUCTION"): ("register_as",) + STAFF_ONLY,
    ("STAFF", "PRODUCTION"): STAFF_ONLY, ("STAFF", "DRAWING"): STAFF_ONLY,
    ("VIEWER", "CS"): (), ("VIEWER", None): (),
}


def _day(offset: int) -> str:
    return (get_today_kst() + datetime.timedelta(days=offset)).isoformat()


@pytest.fixture
def switches(monkeypatch):
    for env in FLAGS.values():
        monkeypatch.delenv(f"{env}_ENABLED", raising=False)
        monkeypatch.delenv(f"{env}_COHORT", raising=False)
    for env in ("FOMS_GRAFT_BRAIN_UI", "FOMS_GRAFT_ACTIONS"):
        monkeypatch.setenv(f"{env}_ENABLED", "1")
        monkeypatch.setenv(f"{env}_COHORT", "all")
    return monkeypatch


def _user(name: str, role: str, team=None, **extra) -> User:
    user = User(username=name, password=generate_password_hash("pw"), role=role, team=team, name=f"{name}-이름",
                is_active=extra.pop("is_active", True), **extra)
    db_session.add(user)
    db_session.commit()
    return user


def _order(stage: str) -> Order:
    sd = {"workflow": {"stage": stage}}
    order = Order(received_date="2030-01-01", customer_name=CUSTOMER, phone=PHONE, address="합성 주소",
                  product="합성 품목", status=stage, is_erp_order=True, structured_data=sd)
    sync_erp_flat_columns(order, sd)
    db_session.add(order)
    db_session.commit()
    return order


def _propose(order: Order, action: str, agent: str, params: dict, level: int, evidence=None) -> int:
    row = propose(db_session, action=action, proposed_by=agent, order=order, params=params, reason=REASON,
                  evidence=evidence or [], source_kind="sweep", source_ref="1", level=level, now=now_utc_naive())
    db_session.commit()
    return row.id


@pytest.fixture
def world(app, switches):
    schedule_order, drawing_order = _order("RECEIVED"), _order("DRAWING")
    return {
        "schedule_id": _propose(schedule_order, "schedule_construction", "agent:schedule",
                                {"date": _day(9), "time": "오전"}, 2),
        "assign_id": _propose(drawing_order, "assign_draftsman", "agent:ops", {}, 1),
        "orders": (schedule_order.id, drawing_order.id),
    }


def _client(app, user_id):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    return client


def _routes(pid: int) -> list[tuple[str, str]]:
    return [("post", f"{BASE}/proposals/{pid}/approve"), ("post", f"{BASE}/proposals/{pid}/reject"),
            ("post", f"{BASE}/proposals/{pid}/snooze"), ("get", f"{BASE}/proposals/{pid}")]


@pytest.mark.parametrize("persona, expected", sorted(MATRIX.items(), key=str))
def test_policy_matrix(app, persona, expected):
    role, team = persona
    assert runnable_actions(_user(f"mx_{role}_{team}", role, team)) == expected


def test_actions_viewer_needs_switch_internal_account_and_policy(app, switches):
    admin, viewer = _user("av_admin", "ADMIN"), _user("av_viewer", "VIEWER", "CS")
    org = PartnerOrg(name="합성 협력사")
    db_session.add(org)
    db_session.commit()
    partner = _user("av_partner", "PARTNER", partner_org_id=org.id)
    asleep = _user("av_off", "ADMIN", is_active=False)
    assert actions_viewer(admin) and not any(actions_viewer(u) for u in (viewer, partner, asleep, None))
    switches.setenv("FOMS_GRAFT_ACTIONS_COHORT", str(admin.id + 1000))
    assert not actions_viewer(admin)
    switches.setenv("FOMS_GRAFT_ACTIONS_COHORT", "all")
    switches.setenv("FOMS_GRAFT_BRAIN_UI_ENABLED", "0")  # 할 일은 새 화면 스위치에 기댄다
    assert not actions_viewer(admin)


def test_staff_outside_the_policy_sees_and_decides_nothing_of_it(app, world):
    production = _user("pr_staff", "STAFF", "PRODUCTION")
    client = _client(app, production.id)
    badge = client.get(f"{BASE}/badge").get_json()["data"]
    assert badge["actions"] == 1 and badge["labels"] == ["도면 담당 맡기기"]
    cards = client.get(f"{BASE}/inbox").get_json()["data"]["cards"]
    assert [card["id"] for card in cards] == [world["assign_id"]]
    ids = ",".join(str(oid) for oid in world["orders"])
    assert list(client.get(f"{BASE}/open?order_ids={ids}").get_json()["data"]["items"]) == [str(world["orders"][1])]
    for method, path in _routes(world["schedule_id"]):
        resp = getattr(client, method)(path, json={"base_version": 1, "code": "other"})
        assert resp.status_code == 404 and resp.get_json()["data"] is None, path
    db_session.expire_all()
    assert db_session.get(ErpActionProposal, world["schedule_id"]).status == "open"


def test_viewer_partner_and_signed_out_accounts(app, world):
    viewer = _user("vw_cs", "VIEWER", "CS")
    org = PartnerOrg(name="합성 협력사 둘")
    db_session.add(org)
    db_session.commit()
    partner = _user("pt_user", "PARTNER", partner_org_id=org.id)
    asleep = _user("off_admin", "ADMIN", is_active=False)
    viewer_id, partner_id, asleep_id = viewer.id, partner.id, asleep.id  # 요청 뒤에는 ORM 객체가 떨어진다
    paths = [("get", f"{BASE}/badge"), ("get", f"{BASE}/inbox"), *_routes(world["schedule_id"])]
    for method, path in paths:
        resp = getattr(_client(app, viewer_id), method)(path, json={"base_version": 1})
        assert resp.status_code == 404, path
        body = getattr(_client(app, partner_id), method)(path, json={"base_version": 1})
        assert body.status_code in (403, 404) and body.get_json()["data"] is None, path
        assert getattr(_client(app, asleep_id), method)(path, json={}).status_code == 401, path


def _freelancer(order_id: int) -> User:
    user = _user("fl_sales", "STAFF", "SALES")
    db_session.add(SystemSetting(setting_key="sales_freelancer_settings", setting_value={"freelancers": {
        str(user.id): {"active": True, "match_name": "합성프리", "start_month": "2030-01", "tax_type": "NONE"}}}))
    db_session.add(OrderFreelancerLink(order_id=order_id, user_id=user.id, relation="CREATOR"))
    db_session.commit()
    return user


def test_freelancer_sees_only_own_orders(app, world):
    own_id, other_id = world["orders"]
    own_note = _propose(db_session.get(Order, own_id), "add_construction_note", "agent:cs", {"note": "자재 먼저"}, 2)
    freelancer = _freelancer(own_id)
    freelancer_id = freelancer.id
    assert _client(app, freelancer_id).get(f"{BASE}/inbox").status_code == 403  # 앞 문지기(허용 목록 밖)
    freelancer = db_session.get(User, freelancer_id)
    now = now_utc_naive()
    own_cards = [own_note, world["schedule_id"]]  # 새것 먼저 — 자기 주문의 제안 둘만
    assert [card["id"] for card in views.inbox(db_session, freelancer, now)["cards"]] == own_cards
    assert set(views.open_for_orders(db_session, freelancer, [own_id, other_id])) == {own_id}
    assert views.badge(db_session, freelancer, now=now)["actions"] == 2
    assert views.detail(db_session, freelancer, world["assign_id"], now) is None
    assert views.detail(db_session, freelancer, own_note, now)["id"] == own_note
    other_order = db_session.get(Order, other_id)
    assert not can_run(freelancer, ACTIONS["assign_draftsman"], other_order)
    with pytest.raises(ActionError) as hidden:
        reject(db_session, world["assign_id"], actor=freelancer, code="other", now=now)
    assert hidden.value.code == "ACTION_FORBIDDEN"


def test_audit_lines_carry_no_customer_text(app, world):
    admin = _user("au_admin", "ADMIN")
    row = db_session.get(ErpActionProposal, world["schedule_id"])
    approve(db_session, row.id, actor=admin, runners={"schedule_construction": lambda s, r: RunOutcome.executed("합성")},
            base_version=row.base_version, now=now_utc_naive())
    reject(db_session, world["assign_id"], actor=admin, code="misread", now=now_utc_naive())
    db_session.commit()
    logs = db_session.query(SecurityLog).filter(SecurityLog.action.like("ERP_ACTION_%")).all()
    assert {log.action for log in logs} == {"ERP_ACTION_APPROVED", "ERP_ACTION_EXECUTED", "ERP_ACTION_REJECTED"}
    for log in logs:
        text = f"{log.message} {log.detail}"
        assert CUSTOMER not in text and PHONE not in text and REASON not in text, log.action
        assert set(log.detail) >= {"proposal_id", "action", "order_id", "agent", "level"}


def test_hidden_knowledge_evidence_is_dropped(app, switches):
    admin, cs_staff = _user("ev_admin", "ADMIN"), _user("ev_cs", "STAFF", "CS")
    create(db_session, admin, "common/open-rule", item_type="question", name="보이는 지식")
    create(db_session, admin, "common/secret-rule", item_type="question", name="숨긴 지식", visibility="admin")
    db_session.commit()
    evidence = [{"kind": "brain", "ref": "common/open-rule", "label": "보이는 지식"},
                {"kind": "brain", "ref": "common/secret-rule", "label": "숨긴 지식"}]
    pid = _propose(_order("RECEIVED"), "schedule_construction", "agent:schedule", {"date": _day(9), "time": ""}, 2,
                   evidence=evidence)
    now = now_utc_naive()
    labels = {who: [chip["label"] for chip in views.detail(db_session, user, pid, now)["evidence"]]
              for who, user in (("admin", admin), ("cs", cs_staff))}
    assert labels == {"admin": ["보이는 지식", "숨긴 지식"], "cs": ["보이는 지식"]}
