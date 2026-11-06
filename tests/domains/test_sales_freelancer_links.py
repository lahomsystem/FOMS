"""FCOMM-01 T13 — 주문 ↔ 프리랜서 연결 표(``order_freelancer_links``) · 저장 훅 · 되채우기.

설계서 docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §4.4 · §5 · §6.1 · J8 · J10, 검수 원장 A7 · A8 · A19 · F1 · F2.
이름 · 고객은 모두 가짜 값이다(저장소 공개). 배정 알림은 ``test_sales_order_assigned_notify.py``.
"""
from __future__ import annotations

import copy
import datetime
import importlib.util
import pathlib
import unicodedata
from types import SimpleNamespace

import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified

from db import db_session, engine
from foms.services.sales_commission import links as link_rules
from foms.services.sales_commission.links import (
    REL_CREATOR,
    REL_MANAGER,
    REL_MANAGER_PRIMARY,
    REL_ORDERER,
    desired_links,
    sync_links_for_orders,
)
from foms.services.sales_commission.settings import load_settings, save_freelancer
from models import Notification, Order, OrderEvent, OrderFreelancerLink
from tests.domains.test_auth_finance import _login, _make_user

ROOT = pathlib.Path(__file__).resolve().parents[2]
MATCH = "가짜프리"
OTHER = "다른가짜"
_TYPE = "SALES_ORDER_ASSIGNED"


# --------------------------------------------------------------------------
# 시드
# --------------------------------------------------------------------------
def _plain(user) -> SimpleNamespace:
    """요청이 세션을 닫아도 읽을 수 있게 id · 아이디 · 역할만 떼어 둔다."""
    return SimpleNamespace(id=user.id, username=user.username, role=user.role)


def _freelancer(match: str = MATCH, start: str = "2026-01") -> SimpleNamespace:
    user = _plain(_make_user("STAFF", "SALES"))
    save_freelancer(db_session, user.id, {"match_name": match, "start_month": start, "tax_type": "NONE",
                                          "active": True},
                    base_version=load_settings(db_session)[0], actor_user_id=None)
    db_session.commit()
    return user


def _sd(manager: str = "", names=None, orderer: str = "", customer: str = "가짜고객") -> dict:
    manager_party: dict = {"name": manager}
    if names:
        manager_party["names"] = list(names)
    return {
        "entity_type": "order_structured",
        "workflow": {"stage": "RECEIVED"},
        "parties": {"customer": {"name": customer, "phone": "010-0000-0000"}, "manager": manager_party,
                    "orderer": {"name": orderer}},
        "site": {"address_full": "가짜시 가짜로 1", "address_main": "가짜시 가짜로 1"},
        "items": [{"product_name": "가짜장", "price": 0}],
        "flags": {"urgent": False, "urgent_reason": "", "factory2": False},
    }


def _order(sd: dict | None = None, *, status: str = "RECEIVED", is_erp: bool = True) -> int:
    sd = sd if sd is not None else _sd()
    manager = ((sd.get("parties") or {}).get("manager") or {}).get("name") or ""
    order = Order(received_date="2026-11-06", customer_name="가짜고객", phone="010-0000-0000", address="가짜시",
                  product="가짜장", status=status, manager_name=manager, is_erp_order=is_erp, structured_data=sd)
    db_session.add(order)
    db_session.commit()
    return order.id


def _resave(oid: int, sd: dict) -> None:
    order = db_session.get(Order, oid)
    order.structured_data = copy.deepcopy(sd)
    flag_modified(order, "structured_data")
    db_session.commit()


def _links(oid: int) -> set[tuple[int, str]]:
    db_session.expire_all()
    return {(r.user_id, r.relation) for r in db_session.query(OrderFreelancerLink).filter_by(order_id=oid)}


def _assigned(oid: int) -> list[Notification]:
    db_session.expire_all()
    return db_session.query(Notification).filter_by(order_id=oid, notification_type=_TYPE).all()


def _client_as(app, role="ADMIN", team="CS"):
    client = app.test_client()
    user = _make_user(role, team)
    _login(client, user)
    return client, user


# --------------------------------------------------------------------------
# 순수 계산 — desired_links
# --------------------------------------------------------------------------
def test_desired_links_primary_other_orderer():
    sd = _sd(MATCH, names=[MATCH, OTHER], orderer=MATCH)
    got = desired_links(sd, {MATCH: 1, OTHER: 2})
    assert got == {(1, REL_MANAGER_PRIMARY), (2, REL_MANAGER), (1, REL_ORDERER)}


def test_desired_links_exact_normalized_match_only():
    nfd = unicodedata.normalize("NFD", MATCH)
    assert desired_links(_sd(f"  {nfd} "), {MATCH: 1}) == {(1, REL_MANAGER_PRIMARY)}
    assert desired_links(_sd(f"{MATCH}님"), {MATCH: 1}) == set()
    assert desired_links(_sd(MATCH, orderer=f"{MATCH} 하우드"), {MATCH: 1}) == {(1, REL_MANAGER_PRIMARY)}
    assert desired_links(_sd(MATCH), {f" {MATCH} ": 1}) == {(1, REL_MANAGER_PRIMARY)}  # 표 열쇠도 정리


def test_desired_links_legacy_one_cell_names_and_duplicates():
    assert desired_links(_sd(f"{OTHER}, {MATCH}"), {MATCH: 1, OTHER: 2}) == {
        (2, REL_MANAGER_PRIMARY), (1, REL_MANAGER)}
    nfd = unicodedata.normalize("NFD", MATCH)
    assert desired_links(_sd(MATCH, names=[MATCH, nfd]), {MATCH: 1}) == {(1, REL_MANAGER_PRIMARY)}


def test_desired_links_creator_only_for_active_freelancer():
    assert desired_links(_sd(), {MATCH: 1}, creator_user_id=1) == {(1, REL_CREATOR)}
    assert desired_links(_sd(), {MATCH: 1}, creator_user_id=99) == set()
    assert desired_links(_sd(MATCH), {}, creator_user_id=1) == set()  # 켜진 프리랜서 없음
    assert desired_links(None, {MATCH: 1}, creator_user_id="1") == {(1, REL_CREATOR)}
    assert desired_links({"parties": "깨짐"}, {MATCH: 1}) == set()


# --------------------------------------------------------------------------
# 모델
# --------------------------------------------------------------------------
def test_model_unique_and_relation_check(app):
    user = _make_user("STAFF", "SALES")
    oid = _order()
    db_session.add(OrderFreelancerLink(order_id=oid, user_id=user.id, relation=REL_MANAGER))
    db_session.commit()
    db_session.add(OrderFreelancerLink(order_id=oid, user_id=user.id, relation=REL_MANAGER))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
    db_session.add(OrderFreelancerLink(order_id=oid, user_id=user.id, relation="BOSS"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_migration_matches_model():
    path = ROOT / "migrations" / "versions" / "fcomm_02_order_freelancer_links.py"
    spec = importlib.util.spec_from_file_location("fcomm_02", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert (module.revision, module.down_revision) == ("fcomm_02", "fcomm_01")
    text = path.read_text(encoding="utf-8")
    for needle in ("ck_order_freelancer_links_relation", "uq_order_freelancer_links_order_user_rel",
                   "ix_order_freelancer_links_order_id", "ix_order_freelancer_links_user_id",
                   "ondelete='CASCADE'", "'MANAGER_PRIMARY','MANAGER','ORDERER','CREATOR'"):
        assert needle in text
    table = OrderFreelancerLink.__table__
    assert {c.name for c in table.columns} == {"id", "order_id", "user_id", "relation", "created_at"}
    assert {i.name for i in table.indexes} == {"ix_order_freelancer_links_order_id",
                                                "ix_order_freelancer_links_user_id"}
    assert next(iter(table.c.order_id.foreign_keys)).ondelete == "CASCADE"


# --------------------------------------------------------------------------
# 훅 — 쓰기 길마다
# --------------------------------------------------------------------------
def test_hook_follows_direct_saves(app):
    f1, f2 = _freelancer(), _freelancer(OTHER)
    oid = _order(_sd(MATCH, orderer=OTHER))
    assert _links(oid) == {(f1.id, REL_MANAGER_PRIMARY), (f2.id, REL_ORDERER)}
    _resave(oid, _sd(OTHER, names=[OTHER, MATCH]))
    assert _links(oid) == {(f2.id, REL_MANAGER_PRIMARY), (f1.id, REL_MANAGER)}
    _resave(oid, _sd("일반직원"))
    assert _links(oid) == set()
    other = _order(_sd(MATCH), is_erp=False)  # ERP 주문이 아니면 보지 않는다
    assert _links(other) == set()
    assert _assigned(oid) == []  # 요청 밖 저장(스크립트 · 서버 시작)은 알림 없음


def test_structured_put_path(app):
    f = _freelancer()
    oid = _order(_sd(""))
    client, _cs = _client_as(app)
    resp = client.put(f"/api/orders/{oid}/structured", json={"structured_data": _sd(MATCH)})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _links(oid) == {(f.id, REL_MANAGER_PRIMARY)}
    resp = client.put(f"/api/orders/{oid}/structured", json={"structured_data": _sd("")})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _links(oid) == set()


def test_measurement_manager_update_path(app):
    f = _freelancer()
    oid = _order(_sd(""), status="MEASURE")
    client, _cs = _client_as(app)
    resp = client.post(f"/api/erp/measurement/update/{oid}", json={"field": "manager", "value": MATCH})
    assert resp.status_code == 200 and resp.get_json()["success"] is True
    assert _links(oid) == {(f.id, REL_MANAGER_PRIMARY)}
    resp = client.post(f"/api/erp/measurement/update/{oid}", json={"field": "manager", "value": ""})
    assert resp.status_code == 200
    assert _links(oid) == set()


def test_inline_field_update_manager_path(app):
    f = _freelancer()
    oid = _order(_sd(""))
    client, _cs = _client_as(app)
    resp = client.post("/api/update_order_field",
                       json={"order_id": oid, "field": "manager_name", "value": f"일반직원, {MATCH}"})
    assert resp.status_code == 200, resp.get_json()
    assert _links(oid) == {(f.id, REL_MANAGER)}
    resp = client.post("/api/update_order_field", json={"order_id": oid, "field": "manager_name", "value": MATCH})
    assert resp.status_code == 200
    assert _links(oid) == {(f.id, REL_MANAGER_PRIMARY)}


def test_freelancer_draft_autosave_gets_creator_that_survives(app):
    f = _freelancer()
    client = app.test_client()
    _login(client, f)
    body = {"draft_token": "fcomm-tok-1", "structured_data": _sd("", customer="가짜새손님")}
    resp = client.post("/api/orders/erp/draft/autosave", json=body)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    oid = resp.get_json()["order_id"]
    assert oid and _links(oid) == {(f.id, REL_CREATOR)}
    body["structured_data"] = _sd(MATCH, customer="가짜새손님")
    assert client.post("/api/orders/erp/draft/autosave", json=body).status_code == 200
    assert _links(oid) == {(f.id, REL_CREATOR), (f.id, REL_MANAGER_PRIMARY)}
    body["structured_data"] = _sd("", customer="가짜새손님")  # 자동 저장이 담당을 지워도
    assert client.post("/api/orders/erp/draft/autosave", json=body).status_code == 200
    assert _links(oid) == {(f.id, REL_CREATOR)}  # 만든 사람 연결은 남는다
    assert _assigned(oid) == []  # 초안은 배정 알림 없음


def test_staff_draft_has_no_creator(app):
    f = _freelancer()
    client, _cs = _client_as(app)
    resp = client.post("/api/orders/erp/draft/autosave",
                       json={"draft_token": "fcomm-tok-2", "structured_data": _sd(MATCH, customer="가짜손님2")})
    oid = resp.get_json()["order_id"]
    assert _links(oid) == {(f.id, REL_MANAGER_PRIMARY)}
    assert _assigned(oid) == []


def test_offline_merge_path(app):
    from foms.services.orders.offline_recovery import _apply_entry

    f = _freelancer()
    oid = _order(_sd(""))
    order = db_session.get(Order, oid)
    _apply_entry(db_session, order, "structured_data_merge", {"parties": _sd(MATCH)["parties"]})
    db_session.commit()
    assert _links(oid) == {(f.id, REL_MANAGER_PRIMARY)}
    assert _assigned(oid) == []


def test_flat_audit_shim_is_untouched(app):
    from foms.services.orders.erp_flat_audit import audit_orders, classify_order

    f = _freelancer()
    oid = _order(_sd(MATCH))
    before = _links(oid)
    assert before == {(f.id, REL_MANAGER_PRIMARY)}
    assert classify_order(db_session.get(Order, oid)) is not None
    audit_orders(db_session)
    assert not db_session.dirty and not db_session.new
    assert _links(oid) == before


# --------------------------------------------------------------------------
# 켜진 프리랜서가 없으면 아무 일도 안 한다
# --------------------------------------------------------------------------
def test_no_freelancers_means_no_link_queries(app, monkeypatch):
    statements: list[str] = []
    loads: list[int] = []
    real_load = link_rules.load_link_snapshot

    def _count_load(db):
        loads.append(1)
        return real_load(db)

    def _capture(_conn, _cursor, statement, *_args):
        statements.append(statement)

    monkeypatch.setattr(link_rules, "load_link_snapshot", _count_load)
    oid = _order(_sd(MATCH))
    client, _cs = _client_as(app)
    event.listen(engine, "before_cursor_execute", _capture)
    try:
        loads.clear()
        resp = client.put(f"/api/orders/{oid}/structured", json={"structured_data": _sd(MATCH, names=[MATCH, OTHER])})
        assert resp.status_code == 200, resp.get_data(as_text=True)
    finally:
        event.remove(engine, "before_cursor_execute", _capture)
    assert statements, "SQL 수집이 비었다 — 대조군"
    assert not [s for s in statements if "order_freelancer_links" in s]
    assert len(loads) <= 1  # 요청 한 번에 설정 읽기 한 번
    assert _links(oid) == set()


# --------------------------------------------------------------------------
# 설정 저장 뒤 다시 맞추기
# --------------------------------------------------------------------------
def test_settings_save_resyncs_that_freelancer_only(app):
    sales = _plain(_make_user("STAFF", "SALES"))
    other = _freelancer(OTHER)
    first = _order(_sd(MATCH, orderer=OTHER))
    second = _order(_sd("새가짜"))
    assert _links(first) == {(other.id, REL_ORDERER)}  # 아직 프리랜서가 아니라 연결 없음
    db_session.add(OrderFreelancerLink(order_id=second, user_id=sales.id, relation=REL_CREATOR))
    db_session.commit()
    client, _admin = _client_as(app, "ADMIN", None)
    body = {"user_id": sales.id, "match_name": MATCH, "start_month": "2026-01", "tax_type": "NONE", "active": True}
    resp = client.post("/api/admin/sales-freelancers", json={**body, "version": load_settings(db_session)[0]})
    assert resp.status_code == 200, resp.get_json()
    assert _links(first) == {(sales.id, REL_MANAGER_PRIMARY), (other.id, REL_ORDERER)}
    resp = client.post("/api/admin/sales-freelancers",
                       json={**body, "match_name": "새가짜", "version": load_settings(db_session)[0]})
    assert resp.status_code == 200, resp.get_json()
    assert _links(first) == {(other.id, REL_ORDERER)}
    assert _links(second) == {(sales.id, REL_MANAGER_PRIMARY), (sales.id, REL_CREATOR)}
    resp = client.post("/api/admin/sales-freelancers",
                       json={**body, "match_name": "새가짜", "active": False, "version": load_settings(db_session)[0]})
    assert resp.status_code == 200, resp.get_json()
    assert _links(second) == {(sales.id, REL_CREATOR)}  # 끄면 이름 연결은 빠지고 만든 사람 연결은 남는다
    assert _links(first) == {(other.id, REL_ORDERER)}  # 다른 프리랜서 줄은 그대로
    assert _assigned(first) == [] and _assigned(second) == []


# --------------------------------------------------------------------------
# 되채우기
# --------------------------------------------------------------------------
def _script():
    path = ROOT / "scripts" / "maintenance" / "backfill_freelancer_links.py"
    spec = importlib.util.spec_from_file_location("backfill_freelancer_links", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_backfill_dry_run_apply_idempotent(app, capsys):
    stale_user = _plain(_make_user("STAFF", "SALES"))
    managed = _order(_sd(MATCH, names=[MATCH, OTHER]))
    created = _order(_sd("일반직원"))
    old_created = _order(_sd("일반직원"))
    draft = _order(_sd(MATCH), status="DRAFT")
    db_session.add(OrderFreelancerLink(order_id=created, user_id=stale_user.id, relation=REL_MANAGER))
    db_session.commit()
    f = _freelancer(start="2026-01")  # 주문보다 늦게 켜짐 → 훅이 못 본 주문들
    now = datetime.datetime(2026, 11, 6, 3, 0, 0)
    db_session.add_all([
        OrderEvent(order_id=created, event_type="ORDER_DRAFT_CREATED", created_by_user_id=f.id, created_at=now),
        OrderEvent(order_id=old_created, event_type="ORDER_CREATED", created_by_user_id=f.id,
                   created_at=datetime.datetime(2025, 3, 1)),  # 시작 달 전(회사 직원 때) — 넣지 않는다
    ])
    db_session.commit()
    assert _links(managed) == set()

    script = _script()
    preview = script.run(db_session, apply=False)
    assert preview["added"] == 3 and preview["removed"] == 1 and preview["freelancers"] == 1
    assert _links(managed) == set() and _links(created) == {(stale_user.id, REL_MANAGER)}  # 미리 보기 = 쓰기 0

    applied = script.run(db_session, apply=True, chunk_size=2)
    assert (applied["added"], applied["removed"]) == (3, 1)
    assert _links(managed) == {(f.id, REL_MANAGER_PRIMARY)}
    assert _links(created) == {(f.id, REL_CREATOR)}
    assert _links(old_created) == set()
    assert _links(draft) == {(f.id, REL_MANAGER_PRIMARY)}
    again = script.run(db_session, apply=True)
    assert (again["added"], again["removed"]) == (0, 0)  # 멱등
    assert all(_assigned(oid) == [] for oid in (managed, created, draft))

    assert script.main(["--chunk-size", "50"]) == 0
    captured = capsys.readouterr()
    assert "가짜고객" not in captured.out + captured.err  # 숫자만 찍는다


def test_sync_limited_to_given_orders(app):
    f = _freelancer()
    one, two = _order(_sd("일반직원")), _order(_sd("일반직원"))
    for oid in (one, two):
        db_session.add(OrderFreelancerLink(order_id=oid, user_id=f.id, relation=REL_MANAGER))
    db_session.commit()
    stats = sync_links_for_orders(db_session, order_ids=[one])
    db_session.commit()
    assert stats["orders"] == 1 and stats["removed"] == 1
    assert _links(one) == set() and _links(two) == {(f.id, REL_MANAGER)}
