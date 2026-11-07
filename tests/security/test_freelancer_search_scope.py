"""FCOMM-01 긴급 호출 주문 고르기 · 통합 검색 범위 (스테이징 T18 남은 것 1).

설계서 docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §6.1 · §6.3 겹 1 · 겹 3.

* 긴급 호출 창의 주문 고르기(static/js/foms/urgent-call-order.js)는 통합 검색 JSON(``/api/foms/search?group=all``)을
  부른다. 켜진 프리랜서에게 그 문이 막혀 주문을 못 골랐다 → 문을 열고, 서비스가 연결 표의 내 주문으로만 좁힌다.
* 고객 · 주문 · 도면 세 묶음 모두 내 주문만 — 남의 주문과 고객 이름 · 전화 · 초성이 같아도, 남의 주문 번호를 쳐도.
* 음성 대조군(같은 자료): 직원(CS)은 남의 주문도 본다. 머리 검색 창 조각(``/search/fragment``)은 여전히 막힌다.
"""
from __future__ import annotations

import itertools
import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from db import db_session
from foms.services.auth.freelancer_scope import FREELANCER_ALLOWED_ENDPOINTS, FREELANCER_DENIED_MSG
from foms.services.foms_unified_search import construction_scope_user, search_unified
from models import Order
from tests.domains.test_auth_finance import _make_user
from tests.security.test_freelancer_edit_guards import _client, _ensure_link, _freelancer

_seq = itertools.count(1)
_GROUPS = ("customer", "order", "drawing")
_PICKER_JS = Path(__file__).resolve().parents[2] / "static" / "js" / "foms" / "urgent-call-order.js"


def _search_order(customer: str, phone: str, manager: str, address: str) -> int:
    """도면 묶음에도 걸리게 도면 단계 · 도면 그림을 둔 ERP 주문(가짜 값)."""
    sd = {
        "parties": {"manager": {"name": manager}, "orderer": {"name": "라홈"},
                    "customer": {"name": customer, "phone": phone}},
        "site": {"address_full": address},
        "items": [{"product_name": "가짜장", "price": 1_000_000}],
        "workflow": {"stage": "DRAWING"},
        "drawing": {"status": "IN_PROGRESS"},
    }
    order = Order(
        received_date="2030-01-01", customer_name=customer, phone=phone, address=address,
        product="가짜장", status="DRAWING", manager_name=manager, is_erp_order=True,
        erp_phone_digits="".join(ch for ch in phone if ch.isdigit()),
        structured_data=sd, erp_stage_code="DRAWING", blueprint_image_url="orders/0/blueprint.png",
    )
    db_session.add(order)
    db_session.commit()
    return order.id


@pytest.fixture
def w(app):
    n = next(_seq)
    customer = f"검색범위고객{n}"
    phone = f"010-77{n:02d}-31{n:02d}"
    address = f"가짜시 검색범위로{n}길"
    fl = _freelancer()
    own = _search_order(customer, phone, fl.match_name, address)
    other = _search_order(customer, phone, "남의담당", address)
    _ensure_link(own, fl)
    staff = _make_user("STAFF", "CS")
    return {"fl": fl, "own": own, "other": other, "customer": customer, "phone": phone, "address": address,
            "client": _client(app, fl), "staff_client": _client(app, staff)}


def _ids_by_group(data: dict) -> dict[str, set[int]]:
    return {group: {hit["order_id"] for hit in data.get(group, [])} for group in _GROUPS if group in data}


def _get(client, query: str, group: str = "all") -> dict:
    resp = client.get("/api/foms/search", query_string={"q": query, "group": group})
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    body = resp.get_json()
    assert body["success"] is True
    return body["data"]


def _queries(w) -> list[str]:
    digits = "".join(ch for ch in w["phone"] if ch.isdigit())
    return [w["customer"], w["phone"], digits, digits[-4:], "ㄱㅅㅂㅇㄱㄱ", w["address"], f"{w['customer']} 가짜시"]


def _positive_query(w, group: str) -> str:
    """묶음마다 내 주문이 실제로 걸리는 검색어 — 고객 · 도면은 고객 이름, 주문은 주소(주문 묶음은 이름을 안 본다)."""
    return w["address"] if group == "order" else w["customer"]


def test_freelancer_search_returns_only_own_orders_in_every_group(w):
    for query in _queries(w):
        by_group = _ids_by_group(_get(w["client"], query))
        assert set(by_group) == set(_GROUPS), query
        assert all(w["other"] not in ids for ids in by_group.values()), (query, by_group)
    # 내 주문은 실제로 잡힌다(빈 결과로 통과하는 것이 아니다) — 묶음마다
    for group in _GROUPS:
        assert _ids_by_group(_get(w["client"], _positive_query(w, group)))[group] == {w["own"]}, group
    assert w["own"] in _ids_by_group(_get(w["client"], w["phone"]))["customer"]


@pytest.mark.parametrize("group", _GROUPS)
def test_freelancer_single_group_is_scoped(w, group):
    data = _get(w["client"], _positive_query(w, group), group)
    assert list(data) == [group]
    assert {hit["order_id"] for hit in data[group]} == {w["own"]}


def test_freelancer_cannot_find_others_order_by_number(w):
    for query in (str(w["other"]), f"#{w['other']}"):
        # 번호 글자가 내 주문의 전화 · 주소에 들어 있으면 내 주문은 걸려도 된다 — 남의 주문만 없으면 된다.
        found = set().union(*_ids_by_group(_get(w["client"], query)).values())
        assert w["other"] not in found and found <= {w["own"]}, (query, found)
    assert w["own"] in _ids_by_group(_get(w["client"], str(w["own"])))["order"]


def test_staff_sees_others_orders_negative_control(w):
    """대조군(같은 자료 · 같은 검색어): 직원은 두 주문을 다 본다 — 위 시험이 검색이 비어서 통과한 것이 아니다."""
    for query in _queries(w):
        found = set().union(*_ids_by_group(_get(w["staff_client"], query)).values())
        assert {w["own"], w["other"]} <= found, (query, found)


def test_scope_user_service_level(w):
    """서비스 직접 호출: 프리랜서는 좁히는 사람, 직원 · 꺼진 프리랜서는 아니다."""
    assert construction_scope_user(w["fl"]) is w["fl"]
    assert construction_scope_user(_make_user("STAFF", "CS")) is None
    assert construction_scope_user(_freelancer(active=False)) is None
    scoped = search_unified(db_session, w["customer"], restrict_to_user=construction_scope_user(w["fl"]))
    assert {hit["order_id"] for hits in scoped.values() for hit in hits} == {w["own"]}


def test_unlinked_order_disappears_from_freelancer_search(w):
    """담당에서 빠지면(연결 표 줄 삭제) 다음 요청부터 검색에도 안 나온다."""
    from models import OrderFreelancerLink

    db_session.query(OrderFreelancerLink).filter_by(order_id=w["own"], user_id=w["fl"].id).delete()
    db_session.commit()
    assert _ids_by_group(_get(w["client"], w["customer"])) == {group: set() for group in _GROUPS}


def test_header_search_fragment_stays_blocked(w):
    resp = w["client"].get("/api/foms/search/fragment", query_string={"q": w["customer"]})
    assert resp.status_code == 403
    assert resp.get_json()["error"] == FREELANCER_DENIED_MSG
    assert "foms_search.api_foms_search_fragment" not in FREELANCER_ALLOWED_ENDPOINTS


def test_urgent_picker_endpoint_is_the_allowed_one(app):
    """주문 고르기 JS 가 부르는 주소가 허용한 endpoint(통합 검색 JSON)로 이어진다."""
    src = _PICKER_JS.read_text(encoding="utf-8")
    paths = re.findall(r"'(/api/foms/search[^']*)'", src)
    assert paths, "urgent-call-order.js 의 검색 주소를 못 찾음"
    adapter = app.url_map.bind("localhost")
    for path in paths:
        endpoint, _args = adapter.match(urlsplit(path).path, method="GET")
        assert endpoint == "foms_search.api_foms_search", (path, endpoint)
        assert endpoint in FREELANCER_ALLOWED_ENDPOINTS
