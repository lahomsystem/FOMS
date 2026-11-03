"""협력사 단가표 API · 화면 권한(설계서 docs/specs/2026-11-03-partner-statement_SPEC.md §5.1 · §6).

ADMIN 만 쓴다 — MANAGER · 직원 · 협력사(자기 회사 단가표라도) 403, 로그인 안 함 401, 화면은 ADMIN 만 200.
대조군: ADMIN 은 불러오기(저장 안 함) → 저장(201 · 감사 한 줄) → 목록 · 판 보기가 된다. 쓰기 정책 엔진을 켠 운영 모양에서도
ADMIN 저장은 지나가고 MANAGER 는 막힌다. 단가 · 이름은 가짜다.
"""
from __future__ import annotations

import io
import json

import pytest

from db import db_session
from models import PartnerPriceList, SecurityLog, User
from tests.security.partner_fixtures import _client, _user, world  # noqa: F401 — pytest fixture 재노출

_SOURCE = {"brands": {"test": [
    {"id": "h0", "side": "left", "kind": "custom", "title": "기본 제품 가격", "headers": ["제품명", "자당 단가"],
     "types": ["text", "price"], "rows": [["슬라이딩", 100000], ["몰딩 여닫이", 90000]]},
    {"id": "h1", "side": "left", "kind": "single", "title": "제품 추가 옵션", "headers": ["품목", "추가 금액"],
     "types": ["text", "price"], "rows": [["피닉스바", 10000]]},
]}}
_HTML = '<html><script id="data" type="application/json">' + json.dumps(_SOURCE, ensure_ascii=False) + "</script></html>"


def _base(world) -> str:
    return f"/api/admin/partners/{world['org_a']}/price-lists"


def _admin(app, world):
    return _client(app, db_session.get(User, world["admin"]))


def _imported(app, world) -> dict:
    resp = _admin(app, world).post(_base(world) + "/import", json={"html": _HTML})
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["data"]["sheets"]["test"]


def _save(client, world, sheet, base_id=None):
    return client.post(_base(world), json={"sheet": sheet, "label": "11월판", "effective_from": "2026-11-01",
                                           "base_id": base_id})


@pytest.fixture
def manager(app):
    return _user(role="MANAGER", team="CS", name="매니저").id


@pytest.fixture
def policy_on(app):
    """운영처럼 쓰기 정책 엔진(AUTH-01)을 켠다(테스트 기본은 꺼짐)."""
    sentinel = object()
    prev = app.config.get("AUTH_POLICY_ENABLED", sentinel)
    app.config["AUTH_POLICY_ENABLED"] = True
    yield
    if prev is sentinel:
        app.config.pop("AUTH_POLICY_ENABLED", None)
    else:
        app.config["AUTH_POLICY_ENABLED"] = prev


@pytest.mark.parametrize("who", ["staff", "sales", "partner_a", "manager"])
@pytest.mark.parametrize("method, suffix, body", [
    ("get", "", None), ("get", "/{id}", None), ("post", "/import", {"html": _HTML}), ("post", "", "save"),
])
def test_only_admin_reaches_price_list_api(app, world, manager, who, method, suffix, body):
    sheet = _imported(app, world)
    saved = _save(_admin(app, world), world, sheet)
    assert saved.status_code == 201
    list_id = saved.get_json()["data"]["id"]
    user_id = manager if who == "manager" else world[who]
    client = _client(app, db_session.get(User, user_id))
    kwargs = {}
    if body == "save":
        kwargs = {"json": {"sheet": sheet, "label": "몰래", "effective_from": "2026-11-02", "base_id": list_id}}
    elif body:
        kwargs = {"json": body}
    resp = getattr(client, method)(_base(world) + suffix.format(id=list_id), **kwargs)
    assert resp.status_code == 403
    assert resp.get_json()["success"] is False
    assert db_session.query(PartnerPriceList).count() == 1


def test_requires_login(app, world):
    client = _client(app, None)
    assert client.get(_base(world)).status_code == 401
    assert client.post(_base(world) + "/import", json={"html": _HTML}).status_code == 401


def test_admin_import_save_list_and_view(app, world):
    client = _admin(app, world)
    empty = client.get(_base(world)).get_json()["data"]
    assert empty["active"] is None and empty["versions"] == []
    upload = client.post(_base(world) + "/import", data={"file": (io.BytesIO(_HTML.encode("utf-8")), "단가표.html")},
                         content_type="multipart/form-data")
    assert upload.status_code == 200
    sheet = upload.get_json()["data"]["sheets"]["test"]
    assert db_session.query(PartnerPriceList).count() == 0  # 불러오기는 저장하지 않는다
    first = _save(client, world, sheet)
    assert first.status_code == 201
    first_id = first.get_json()["data"]["id"]
    log = db_session.query(SecurityLog).filter(SecurityLog.action == "PARTNER_PRICE_LIST_SAVED").one()
    assert log.target_id == first_id and log.detail["partner_org_id"] == world["org_a"]
    stale = _save(client, world, sheet, base_id=None)
    assert stale.status_code == 409
    second = _save(client, world, sheet, base_id=first_id)
    assert second.status_code == 201 and second.get_json()["data"]["version"] == 2
    listed = client.get(_base(world)).get_json()["data"]
    assert [v["status"] for v in listed["versions"]] == ["ACTIVE", "RETIRED"]
    assert listed["active"]["id"] == second.get_json()["data"]["id"]
    old = client.get(_base(world) + f"/{first_id}").get_json()["data"]
    assert old["status"] == "RETIRED" and old["sheet"]["categories"][0]["rows"][0]["cells"][1] == 100000


def test_other_org_cannot_read_a_version_through_wrong_path(app, world):
    sheet = _imported(app, world)
    list_id = _save(_admin(app, world), world, sheet).get_json()["data"]["id"]
    resp = _admin(app, world).get(f"/api/admin/partners/{world['org_b']}/price-lists/{list_id}")
    assert resp.status_code == 404


def test_bad_sheet_returns_error_list(app, world):
    sheet = _imported(app, world)
    sheet["categories"][0]["rows"][0]["cells"][1] = "십만원"
    resp = _save(_admin(app, world), world, sheet)
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["success"] is False and "숫자가 아닌 값" in body["error"] and body["data"]["errors"]


def test_policy_engine_lets_admin_save_and_blocks_manager(app, world, manager, policy_on):
    sheet = _imported(app, world)
    assert _save(_admin(app, world), world, sheet).status_code == 201
    blocked = _save(_client(app, db_session.get(User, manager)), world, sheet)
    assert blocked.status_code == 403


@pytest.mark.parametrize("who, status", [("admin", 200), ("manager", 403), ("staff", 403), ("partner_a", 403)])
def test_price_list_page_is_admin_only(app, world, manager, who, status):
    user_id = manager if who == "manager" else world[who]
    resp = _client(app, db_session.get(User, user_id)).get(f"/admin/partners/{world['org_a']}/price-list")
    if status == 200:
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "data-pl-root" in html and f"/api/admin/partners/{world['org_a']}/price-lists" in html
    else:
        assert resp.status_code in (302, 403)
