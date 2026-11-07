"""FCOMM-01 D27 후속(11-07): 프리랜서도 자기 주문의 고객 공유 링크를 보내고 · 회수하고 · 열람 이력을 본다.

이 다섯 API 는 주소에 주문 번호가 아니라 링크 · 이력 줄 번호가 있어 문지기(겹 2)가 주문을 못 본다 — 번호만 바꾸면
남의 주문 링크를 끊을 수 있는 틈. 그래서 핸들러가 그 줄의 주문을 보고(``foms.api.share._share_hidden_from_user``),
남의 주문이면 **없는 줄과 똑같이** 답한다(존재 여부가 새지 않는다). 회사 직원은 이전과 같다.

설계서 docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §6.6
"""
from __future__ import annotations

import pytest

from db import db_session
from foms.services import order_share as osvc
from foms.services import order_share_history as share_history
from foms.services.auth.freelancer_scope import is_freelancer_request_allowed
from models import Order, OrderShareToken, User
from tests.domains.test_auth_finance import _make_user
from tests.security.test_freelancer_own_order_rights import _client, _freelancer, _link, _order

_ROW_PATHS = ("send-sms", "send-alimtalk")
_MISSING = 99_999_999


@pytest.fixture
def world(app):
    fl = _freelancer()
    own = _order(fl.match_name)
    other = _order("남의담당")
    _link(own, fl)
    rows = {}
    for key, oid in (("own", own), ("other", other)):
        row, token = osvc.create_share_token(db_session, oid, "estimate")
        rows[key] = (row.id, token)
    db_session.commit()
    return {"fl": fl, "own": own, "other": other, "rows": rows}


def _snapshot_id(order_id: int, share_id: int) -> int:
    order = db_session.get(Order, order_id)
    snap = share_history.record_snapshot_view(
        db_session, db_session.get(OrderShareToken, share_id), osvc.build_estimate_snapshot(order))
    db_session.commit()
    return snap.id


def test_share_row_endpoints_are_allowlisted_for_freelancer():
    for name in ("send_sms", "send_alimtalk", "revoke", "history", "history_page"):
        assert is_freelancer_request_allowed(f"share_api.api_share_{name}", "POST" if "send" in name
                                             or name == "revoke" else "GET")


@pytest.mark.parametrize("path", _ROW_PATHS)
def test_send_own_link_reaches_handler_other_link_is_missing(app, world, path):
    client = _client(app, world["fl"])
    own_id, _own_token = world["rows"]["own"]
    other_id, other_token = world["rows"]["other"]
    # 내 링크: 문지기 · 주문 확인을 지나 핸들러의 토큰 확인까지 간다(틀린 토큰 → 400, 아무것도 안 보냄).
    resp = client.post(f"/api/share/{path}/{own_id}", json={"token": "wrong"})
    assert resp.status_code == 400 and resp.get_json()["error"] == "token_mismatch"
    # 남의 링크: 맞는 토큰을 실어도 없는 링크와 똑같은 404.
    other = client.post(f"/api/share/{path}/{other_id}", json={"token": other_token})
    missing = client.post(f"/api/share/{path}/{_MISSING}", json={"token": other_token})
    assert other.status_code == missing.status_code == 404
    assert other.get_json() == missing.get_json()


def test_revoke_own_link_only(app, world):
    client = _client(app, world["fl"])
    own_id, _ = world["rows"]["own"]
    other_id, _ = world["rows"]["other"]
    other = client.post(f"/api/share/revoke/{other_id}")
    missing = client.post(f"/api/share/revoke/{_MISSING}")
    assert other.status_code == missing.status_code == 404
    assert other.get_json() == missing.get_json()
    assert db_session.get(OrderShareToken, other_id).revoked_at is None
    resp = client.post(f"/api/share/revoke/{own_id}")
    assert resp.status_code == 200 and resp.get_json()["success"] is True
    db_session.expire_all()
    assert db_session.get(OrderShareToken, own_id).revoked_at is not None


def test_history_own_only_other_looks_missing(app, world):
    own_id, _ = world["rows"]["own"]
    other_id, _ = world["rows"]["other"]
    own_snap = _snapshot_id(world["own"], own_id)
    other_snap = _snapshot_id(world["other"], other_id)
    client = _client(app, world["fl"])
    own = client.get(f"/api/share/history/{own_id}").get_json()
    assert [i["snapshot_id"] for i in own["data"]["items"]] == [own_snap]
    other = client.get(f"/api/share/history/{other_id}")
    assert other.status_code == 200 and other.get_json() == client.get(f"/api/share/history/{_MISSING}").get_json()
    assert client.get(f"/api/share/history/{own_snap}/page").status_code == 200
    other_page = client.get(f"/api/share/history/{other_snap}/page")
    missing_page = client.get(f"/api/share/history/{_MISSING}/page")
    assert other_page.status_code == missing_page.status_code == 404
    assert other_page.get_data() == missing_page.get_data()


def test_company_staff_unchanged(app, world):
    """회사 영업 직원은 판정하지 않는다 — 누구 주문 링크든 이전과 같이 회수 · 이력."""
    staff: User = _make_user("STAFF", "SALES")
    client = _client(app, staff)
    other_id, _ = world["rows"]["other"]
    other_snap = _snapshot_id(world["other"], other_id)
    assert client.get(f"/api/share/history/{other_id}").get_json()["data"]["items"]
    assert client.get(f"/api/share/history/{other_snap}/page").status_code == 200
    assert client.post(f"/api/share/revoke/{other_id}").status_code == 200
