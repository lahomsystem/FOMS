"""검색어 낱말 규칙 — 통합 검색 미리보기와 과거 이력 화면이 같은 결과를 내는지(2026-09-29).

두 화면이 같은 규칙(`search_query_tokens` + `visible_order_search_clause`)을 쓴다.
검색 키·최근 검색 칩·"전체 결과 보기"가 모두 이력 화면으로 가므로, 미리보기에 뜬
주문이 거기서 빠지거나 반대로 늘면 입구마다 결과가 달라 보인다.
"""

from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.common import dashboard_cache as dc
from foms.services.erp_dashboard_search import search_query_tokens
from foms.services.foms_unified_search import search_unified
from foms.services.phone_search import normalize_phone_digits
from models import Order, User


@pytest.fixture(autouse=True)
def _reset_cache_runtime(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    dc.reset_dashboard_cache_runtime_for_tests()
    yield
    dc.reset_dashboard_cache_runtime_for_tests()


def _login_admin(client) -> None:
    user = User(
        username="search_word_rules_admin",
        password=generate_password_hash("x"),
        role="ADMIN",
        team="CS",
        name="낱말규칙",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _seed(name: str, phone: str) -> int:
    order = Order(
        received_date="2026-09-01",
        customer_name=name,
        phone=phone,
        address="서울시 낱말구 1",
        product="붙박이장",
        status="RECEIVED",
        is_erp_order=True,
        erp_stage_code="RECEIVED",
        # 실제 쓰기 경로는 sync_erp_flat_columns 가 채운다(flush 훅이 아니라 테스트에선 직접).
        erp_phone_digits=normalize_phone_digits(phone),
        structured_data={
            "workflow": {"stage": "RECEIVED"},
            "parties": {"customer": {"name": name, "phone": phone}},
        },
    )
    db_session.add(order)
    db_session.commit()
    return int(order.id)


def _preview_ids(query: str) -> set[int]:
    buckets = search_unified(db_session, query)
    return {hit["order_id"] for group in buckets.values() for hit in group}


def _history_ids(client, query: str) -> str:
    return client.get(
        "/erp/history/",
        query_string={"view": "fragment", "q": query},
        headers={"X-FOMS-ERP-SHELL": "1"},
    ).get_data(as_text=True)


def test_search_query_tokens_rules() -> None:
    assert search_query_tokens("010 8201 6514") == ["01082016514"]
    assert search_query_tokens("010-8201-6514") == ["010-8201-6514"]
    assert search_query_tokens("#5335") == ["5335"]
    assert search_query_tokens("수지구  용인시") == ["수지구", "용인시"]
    assert search_query_tokens("서장군 #5335") == ["서장군", "5335"]
    assert search_query_tokens("   ") == []


def test_spaced_phone_number_found_in_both(client, app) -> None:
    """띄어 친 전화번호 — 낱말로 나누면 "8201" 이 끝자리 규칙에 걸려 0건이 됐다."""
    _login_admin(client)
    target = _seed("띄어친전화", "010-3030-4040")

    assert target in _preview_ids("010 3030 4040")
    assert f'data-order-id="{target}"' in _history_ids(client, "010 3030 4040")


def test_four_digit_rule_same_in_both(client, app) -> None:
    """숫자 4자리 = 전화 끝자리. 미리보기만 가운데 자리까지 잡으면 결과 화면과 갈린다."""
    _login_admin(client)
    tail = _seed("끝자리", "010-8201-6514")
    middle = _seed("가운데", "010-6514-3333")

    preview = _preview_ids("6514")
    history = _history_ids(client, "6514")
    assert tail in preview
    assert f'data-order-id="{tail}"' in history
    assert middle not in preview, "미리보기가 가운데 자리까지 잡음"
    assert f'data-order-id="{middle}"' not in history


def test_construction_search_words_in_any_order(app) -> None:
    """시공 화면: 공백만 지운 한 덩어리("%용인시수지구%")는 늘 0건이었다."""
    from foms.services.construction_read_model import apply_construction_search_filter

    target = _seed("시공어순", "010-1212-3434")
    order = db_session.get(Order, target)
    order.address = "경기 용인시 수지구 풍덕천로 1"
    db_session.commit()

    def ids(q: str) -> set[int]:
        rows = apply_construction_search_filter(db_session.query(Order), q).all()
        return {int(o.id) for o in rows}

    assert target in ids("용인시 수지구")
    assert target in ids("수지구 용인시")
    assert target not in ids("용인시 기흥구")


def test_completion_search_words_in_any_order(client, app) -> None:
    """완료 화면 검색도 같은 낱말 규칙."""
    _login_admin(client)
    order = Order(
        received_date="2026-01-01",
        customer_name="완료어순",
        phone="010-5656-7878",
        address="경기 용인시 수지구 1",
        product="붙박이",
        status="COMPLETED",
        is_erp_order=True,
        structured_data={"parties": {"customer": {"name": "완료어순", "phone": "010-5656-7878"}}},
    )
    db_session.add(order)
    db_session.commit()

    for q in ("용인시 수지구", "수지구 완료어순"):
        hits = client.get("/api/orders/completion", query_string={"q": q}).get_json()["orders"]
        assert order.id in {row["id"] for row in hits}, q
