"""FCOMM-01 T13 — 배정 알림 ``SALES_ORDER_ASSIGNED``(설계서 §5 마지막 항목 · §7 · §6.1-2).

알림이 가는 때: 로그인한 사람의 요청 저장에서, 초안 · 삭제가 아닌 주문에 켜진 프리랜서가 **이전에 없던** 담당
관계(대표 · 다른 담당)로 들어갈 때 — 한 번만. 안 가는 때: 초안 자동 저장, 되채우기, 설정 저장 뒤 다시 맞추기,
서버 시작 · 스크립트(요청 밖), 저장한 본인, 이미 담당이던 사람(대표 ↔ 다른 담당 이동). 이름은 모두 가짜 값이다.
"""
from __future__ import annotations

from types import SimpleNamespace

from db import db_session
from foms.services.notifications import push_sender
from foms.services.sales_commission import link_hook
from foms.services.sales_commission.links import REL_MANAGER_PRIMARY, sync_links_for_orders
from models import Notification, NotificationUserState, Order, OrderFreelancerLink
from tests.domains.test_sales_freelancer_links import (
    MATCH,
    OTHER,
    _client_as,
    _freelancer,
    _links,
    _order,
    _resave,
    _sd,
)

_TYPE = link_hook.NOTIFICATION_TYPE


def _assigned(oid: int) -> list[Notification]:
    db_session.expire_all()
    return (db_session.query(Notification).filter_by(order_id=oid, notification_type=_TYPE)
            .order_by(Notification.id).all())


def _put(client, oid: int, sd: dict):
    resp = client.put(f"/api/orders/{oid}/structured", json={"structured_data": sd})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp


def test_assignment_notifies_once_per_transition(app):
    f = _freelancer()
    oid = _order(_sd("", customer="가짜손님"))
    client, _cs = _client_as(app)
    _put(client, oid, _sd(MATCH, customer="가짜손님"))
    rows = _assigned(oid)
    assert len(rows) == 1
    row = rows[0]
    assert (row.target_type, row.target_user_id, row.title) == ("USER", f.id, "새 주문 배정")
    assert row.message == "가짜손님 주문이 배정됐어요"
    states = db_session.query(NotificationUserState).filter_by(notification_id=row.id).all()
    assert [s.user_id for s in states] == [f.id]

    _put(client, oid, _sd(MATCH, customer="가짜손님"))  # 같은 저장 다시
    _put(client, oid, _sd("일반직원", names=["일반직원", MATCH], customer="가짜손님"))  # 대표 → 다른 담당
    assert len(_assigned(oid)) == 1
    _put(client, oid, _sd("일반직원", names=["일반직원"], customer="가짜손님"))  # 빠졌다가
    assert _links(oid) == set()
    _put(client, oid, _sd(MATCH, customer="가짜손님"))  # 다시 들어오면 새 배정
    assert len(_assigned(oid)) == 2


def test_orderer_only_and_other_paths(app):
    f, g = _freelancer(), _freelancer(OTHER)
    oid = _order(_sd(""), status="MEASURE")
    client, _cs = _client_as(app)
    _put(client, oid, _sd("", orderer=MATCH))  # 발주사만 — 담당이 아니라 알림 없음
    assert _assigned(oid) == []
    resp = client.post(f"/api/erp/measurement/update/{oid}", json={"field": "manager", "value": OTHER})
    assert resp.status_code == 200
    resp = client.post("/api/update_order_field",
                       json={"order_id": oid, "field": "manager_name", "value": f"{OTHER}, {MATCH}"})
    assert resp.status_code == 200, resp.get_json()
    assert sorted(n.target_user_id for n in _assigned(oid)) == sorted([g.id, f.id])


def test_drafts_never_notify_but_promotion_does_once(app):
    f = _freelancer()
    client, _cs = _client_as(app)
    body = {"draft_token": "fcomm-notify-1", "structured_data": _sd(MATCH, customer="가짜초안손님")}
    resp = client.post("/api/orders/erp/draft/autosave", json=body)
    oid = resp.get_json()["order_id"]
    assert client.post("/api/orders/erp/draft/autosave", json=body).status_code == 200
    assert _links(oid) == {(f.id, REL_MANAGER_PRIMARY)}
    assert _assigned(oid) == []
    _put(client, oid, _sd(MATCH, customer="가짜초안손님"))  # 명시 저장 = 등록(승격)
    db_session.expire_all()
    assert db_session.get(Order, oid).status != "DRAFT"
    assert len(_assigned(oid)) == 1
    _put(client, oid, _sd(MATCH, customer="가짜초안손님"))
    assert len(_assigned(oid)) == 1


def test_self_assignment_is_skipped_but_other_actor_is_not(app):
    f = _freelancer()
    oid = _order(_sd(MATCH))
    db_session.query(Order).count()
    link_hook.queue_assignment(db_session(), oid, [f.id], actor_user_id=f.id)  # 저장한 본인
    db_session.commit()
    assert _assigned(oid) == []
    db_session.query(Order).count()
    link_hook.queue_assignment(db_session(), oid, [f.id], actor_user_id=None)  # 대조군
    db_session.commit()
    assert len(_assigned(oid)) == 1


def test_outside_request_backfill_and_resync_do_not_notify(app):
    from foms.services.app_init import _backfill_erp_flat_columns

    f = _freelancer()
    oid = _order(_sd(MATCH))  # 스크립트 · 서버 시작처럼 요청 밖 저장
    _resave(oid, _sd(OTHER))
    _resave(oid, _sd(MATCH))
    with app.app_context():
        _backfill_erp_flat_columns()  # 서버 시작 때 최근 주문 다시 맞추기(app_init)
    db_session.query(OrderFreelancerLink).filter_by(order_id=oid).delete()
    db_session.commit()
    sync_links_for_orders(db_session)  # 되채우기 · 설정 저장 뒤 다시 맞추기 기본값
    db_session.commit()
    assert _links(oid) == {(f.id, REL_MANAGER_PRIMARY)}
    assert _assigned(oid) == []


def test_sync_with_notify_skips_drafts(app):
    live, draft = _order(_sd(MATCH)), _order(_sd(MATCH), status="DRAFT")  # 아직 프리랜서 없음 → 연결 없음
    f = _freelancer()
    assert _links(live) == set() and _links(draft) == set()
    sync_links_for_orders(db_session, [live, draft], notify=True)
    db_session.commit()
    assert [n.target_user_id for n in _assigned(live)] == [f.id]
    assert _assigned(draft) == []


def test_notification_failure_does_not_block_the_save(app, monkeypatch):
    from foms.services.notifications import recipients

    f = _freelancer()
    oid = _order(_sd(""))
    client, _cs = _client_as(app)

    def _boom(*_a, **_k):
        raise RuntimeError("가상 알림 실패")

    monkeypatch.setattr(recipients, "fan_out_new_notification", _boom)
    _put(client, oid, _sd(MATCH))
    assert _links(oid) == {(f.id, REL_MANAGER_PRIMARY)}
    assert _assigned(oid) == []  # savepoint 만 되돌아갔다


def test_rollback_drops_pending_candidates(app):
    f = _freelancer()
    oid = _order(_sd(MATCH))
    db_session.query(Order).count()  # 트랜잭션 시작
    link_hook.queue_assignment(db_session(), oid, [f.id])
    db_session.rollback()
    db_session.commit()
    assert _assigned(oid) == []


def test_push_banner_and_links():
    assert _TYPE == "SALES_ORDER_ASSIGNED"
    assert _TYPE in push_sender._DEFAULT_P1_TYPES, "P1 에 없으면 폰에 안 간다"
    notif = SimpleNamespace(id=9, order_id=5, notification_type=_TYPE, is_urgent=False, created_at=None,
                            message="가짜손님 주문이 배정됐어요", title="새 주문 배정", target_user_id=1)
    assert push_sender._deep_link(notif) == "/erp/orders/5/mobile"
    named = push_sender._build_payload(notif, "가짜손님")
    generic = push_sender._build_payload(notif, "")
    assert (named["title"], named["body"]) == ("새 주문 배정 · 가짜손님", "가짜손님 주문이 배정됐어요")
    assert generic["title"] == "새 주문 배정" and "가짜손님" not in generic["body"]
    for payload in (named, generic):
        assert payload["data"]["deep_link"] == "/erp/orders/5/mobile"

    from foms.api.notifications import _resolve_notification_deep_link

    bell = SimpleNamespace(notification_type=_TYPE, order_id=5, created_at=None)
    assert _resolve_notification_deep_link(bell, {})["deep_link_url"] == "/erp/orders/5/mobile"


def test_listener_registered_once():
    link_hook.register_freelancer_link_listener()
    link_hook.register_freelancer_link_listener()
    assert link_hook.is_freelancer_link_listener_registered()
