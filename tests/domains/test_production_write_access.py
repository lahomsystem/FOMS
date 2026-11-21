"""생산 쓰기 = 관리자 + 생산팀만, 기기 무관(설계서 2026-11-21-production-pc-viewer §13 결정 2 · §11).

CS · 회계 · 영업 · 도면 · 시공 · 출고 · 조회 전용 · 협력사는 생산 쓰기 API 아홉
(start · complete · rework · cancel · uncomplete · change-ack · steps POST · defect · hold)이 403.
한 함수(``can_write_production``)를 문지기 정책 PRODUCTION_EDIT(gate) · 라우트 데코레이터 · 화면이 같이 본다.
모든 이름 · 번호는 가짜 값이다.
"""
from __future__ import annotations

import pytest

from db import db_session
from foms.services.orders.order_mutation_policy import POLICY_REGISTRY, evaluate_policy
from foms.services.production.part_access import writable_parts
from foms.services.production.write_access import PRODUCTION_WRITE_DENIED_MESSAGE, can_write_production
from models import PartnerOrg
from tests.support.production_access_support import PEOPLE, WRITE_ENDPOINTS, login, make_order, make_user, ns

# --------------------------------------------------------------------------- #
# 1. 한 함수 — 쓰기 표
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name,role,team,write,view", PEOPLE)
def test_write_matrix(name, role, team, write, view):
    assert can_write_production(ns(role, team)) is write, name


def test_partner_inactive_and_anonymous_never_write():
    assert can_write_production(None) is False
    assert can_write_production(ns("ADMIN", None, is_active=False)) is False
    assert can_write_production(ns("PARTNER", "PRODUCTION", partner_org_id=7)) is False


@pytest.mark.parametrize("name,role,team,write,view", PEOPLE)
def test_policy_gate_is_the_same_function(name, role, team, write, view):
    """문지기 정책 PRODUCTION_EDIT 가 같은 답 — MANAGER 가 팀 검사보다 먼저 지나가던 길(엔진 3단계)이 없다."""
    assert evaluate_policy(POLICY_REGISTRY["PRODUCTION_EDIT"], ns(role, team)).allowed is write, name


def test_policy_gate_points_at_write_access():
    policy = POLICY_REGISTRY["PRODUCTION_EDIT"]
    assert policy.gate == "foms.services.production.write_access:can_write_production"
    assert policy.teams == ("PRODUCTION",)


@pytest.mark.parametrize("name,role,team,write,view", PEOPLE)
def test_part_card_writers_are_inside_write_set(name, role, team, write, view):
    """파트 카드(D53 · D55)를 쓰는 사람은 모두 생산 쓰기 사람 안에 있다 — 파트 규칙은 그 위에 얹힌다."""
    for part in (None, "cut", "edge"):
        person = ns(role, team)
        person.production_part = part
        if writable_parts(person):
            assert can_write_production(person), (name, part)


# --------------------------------------------------------------------------- #
# 2. 생산 쓰기 API 아홉 × 사람 — HTTP
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name,role,team,write,view", PEOPLE)
def test_write_api_matrix(client, name, role, team, write, view):
    """쓰는 사람은 권한 문을 지난다(상태 때문에 400 · 409 는 될 수 있다), 그 밖은 아홉 모두 403."""
    user = make_user(f"pw_{name}", role, team)
    login(client, user)
    order_id = make_order().id
    for path, body in WRITE_ENDPOINTS:
        resp = client.post(f"/api/orders/{order_id}/production/{path}", json=body)
        if write:
            assert resp.status_code != 403, (name, path, resp.get_json())
        else:
            assert resp.status_code == 403, (name, path, resp.status_code)
            assert resp.get_json()["success"] is False


def test_write_api_denied_by_route_decorator_message(app, client, monkeypatch):
    """문지기가 지나보내도(시험으로 끔) 라우트 데코레이터가 같은 함수로 막고 쉬운 글을 준다."""
    from foms.services.orders import order_mutation_policy as omp

    monkeypatch.setitem(omp.POLICY_REGISTRY, "PRODUCTION_EDIT",
                        omp.Policy("PRODUCTION_EDIT", teams="*"))
    user = make_user("pw_cs_deco", "STAFF", "CS")
    login(client, user)
    order_id = make_order().id
    resp = client.post(f"/api/orders/{order_id}/production/steps", json={"key": "cut", "done": True})
    assert resp.status_code == 403
    assert resp.get_json() == {"success": False, "error": PRODUCTION_WRITE_DENIED_MESSAGE}


def test_partner_account_write_api_403(client):
    org = PartnerOrg(name="가짜협력사생산")
    db_session.add(org)
    db_session.commit()
    user = make_user("pw_partner", "PARTNER", None, partner_org_id=org.id)
    login(client, user)
    order_id = make_order().id
    resp = client.post(f"/api/orders/{order_id}/production/start", json={})
    assert resp.status_code == 403
