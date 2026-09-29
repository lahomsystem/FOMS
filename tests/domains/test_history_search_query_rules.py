"""과거 이력 검색의 검색어 규칙 — 통합 검색 미리보기와 같은 규칙인지(2026-09-29).

검색 키·최근 검색 칩·"전체 결과 보기"가 모두 이 화면으로 온다. 미리보기에 뜬 주문이
여기서 빠지면 입구마다 결과가 달라 보인다.
"""

from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.common import dashboard_cache as dc
from models import Order, User


@pytest.fixture(autouse=True)
def _reset_cache_runtime(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    dc.reset_dashboard_cache_runtime_for_tests()
    yield
    dc.reset_dashboard_cache_runtime_for_tests()


def _login_admin(client) -> User:
    user = User(
        username="history_search_rules_admin",
        password=generate_password_hash("x"),
        role="ADMIN",
        team="CS",
        name="검색규칙",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _seed_search_order(name: str, phone: str, *, sd_extra: dict | None = None) -> int:
    order = Order(
        received_date="2026-09-01",
        customer_name=name,
        phone=phone,
        address="서울시 검색구 1",
        product="붙박이장",
        status="COMPLETED",
        manager_name="이력담당",
        is_erp_order=True,
        erp_stage_code="COMPLETED",
        structured_data={
            "workflow": {"stage": "COMPLETED"},
            "parties": {"customer": {"name": name, "phone": phone}},
            **(sd_extra or {}),
        },
    )
    db_session.add(order)
    db_session.commit()
    return int(order.id)


def test_history_search_words_match_in_any_order(client):
    """낱말 순서가 DB 값과 달라도 찾는다 — 통합 검색 미리보기와 같은 규칙(2026-09-29).

    검색 키·최근 검색 칩이 이 화면으로 온다. 통째 ILIKE 면 미리보기에 뜬 주문이
    여기선 0건이 된다("수지구 용인시" vs 주소 "경기 용인시 수지구").
    """
    _login_admin(client)
    target = _seed_search_order(
        "어순고객", "010-3030-4040", sd_extra={"site": {"address_full": "경기 용인시 수지구 풍덕천로 1"}}
    )
    other = _seed_search_order(
        "다른동네", "010-5050-6060", sd_extra={"site": {"address_full": "경기 용인시 기흥구 1"}}
    )

    def ids_for(q: str) -> str:
        return client.get(
            f"/erp/history/?view=fragment&q={q}",
            headers={"X-FOMS-ERP-SHELL": "1"},
        ).get_data(as_text=True)

    body = ids_for("수지구 용인시")
    assert f'data-order-id="{target}"' in body, "어순이 다르면 못 찾음"
    assert f'data-order-id="{other}"' not in body, "낱말 하나만 맞는 주문까지 나옴(AND 아님)"

    body = ids_for("어순고객 4040")
    assert f'data-order-id="{target}"' in body, "이름 + 전화 끝 4자리 조합을 못 찾음"
    assert f'data-order-id="{other}"' not in body


def test_history_search_accepts_hash_order_number(client):
    """카드에 찍힌 "#번호" 를 그대로 쳐도 그 주문을 찾는다(미리보기와 같은 규칙)."""
    _login_admin(client)
    target = _seed_search_order("샵번호고객", "010-7070-8080")
    body = client.get(
        f"/erp/history/?view=fragment&q=%23{target}",
        headers={"X-FOMS-ERP-SHELL": "1"},
    ).get_data(as_text=True)
    assert f'data-order-id="{target}"' in body
