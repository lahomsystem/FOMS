"""도면 작업실 모집단(seed) 스코프 계약 — 접수순 창 밖 도면 주문 누락 차단.

운영 사고(2026-08-23): ERP 프로세스 맵은 도면 28건인데 작업실에는 1건만 떴다.
seed 가 **단계 조건 없이** ``created_at desc LIMIT cap`` 으로 최신 N건만 뽑고 그 뒤
파이썬에서 ``stage == 'DRAWING'`` 을 거르는 구조라, 오래 머문 도면 주문 27건이
창 밖으로 밀려 조용히 사라졌다(활성 ERP 2480건 / cap 250).

근본 수정 = 모집단 술어를 SQL 로 내린다. 아래 계약이 그 구조를 잠근다:
- 접수순 창 밖(오래된) 도면 단계 주문이 목록에 남는다.
- ``drawing_status == 'RETURNED'`` 은 단계와 무관하게 남는다(수령확정 후 수정요청은
  stage 를 되돌리지 않으므로 단계 조건만으로는 사라진다).
"""
from __future__ import annotations

import datetime

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.common import dashboard_cache as dc
from foms.services.drawing_workbench_read_model import fetch_drawing_seed_order_ids
from models import Order, User

_OLD = datetime.datetime(2026, 1, 5, 9, 0, 0)
_NEW = datetime.datetime(2026, 8, 20, 9, 0, 0)


@pytest.fixture(autouse=True)
def _reset_cache_runtime(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    dc.reset_dashboard_cache_runtime_for_tests()
    yield
    dc.reset_dashboard_cache_runtime_for_tests()


def _login_admin(client) -> User:
    user = User(
        username="drawing_seed_admin",
        password=generate_password_hash("x"),
        role="ADMIN",
        team="DRAWING",
        name="도면담당",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _seed_order(
    idx: int,
    *,
    stage: str,
    created_at: datetime.datetime,
    drawing_status: str | None = None,
) -> int:
    """활성 ERP 주문 1건. erp_stage_code 는 workflow.stage 미러(운영과 동일 규칙)."""
    sd = {
        "workflow": {"stage": stage},
        "parties": {
            "customer": {"name": f"고객{idx}", "phone": f"010-7000-{idx:04d}"},
            "manager": {"name": "도면담당"},
        },
        "site": {"address_full": f"서울시 계약구 {idx}"},
        "items": [{"product_name": "붙박이장", "spec_width": "1500"}],
        "drawing_assignees": [],
    }
    if drawing_status:
        sd["drawing_status"] = drawing_status
    order = Order(
        received_date="2026-01-05",
        customer_name=f"고객{idx}",
        phone=f"010-7000-{idx:04d}",
        address=f"서울시 계약구 {idx}",
        product="붙박이장",
        status="RECEIVED",
        manager_name="도면담당",
        is_erp_order=True,
        erp_stage_code=stage,
        structured_data=sd,
        created_at=created_at,
    )
    db_session.add(order)
    db_session.flush()
    return order.id


def _seed_newest_noise(count: int) -> None:
    """도면 단계가 아닌 최신 주문 — seed 창(접수순)을 통째로 채우는 소음."""
    for i in range(count):
        _seed_order(
            9000 + i,
            stage="MEASURE",
            created_at=_NEW + datetime.timedelta(minutes=i),
        )
    db_session.commit()


def _detail_link(order_id: int) -> str:
    """행 존재 판정용 고유 문자열 — ``#<id>`` 는 CSS hex 색상과 충돌해 오탐한다."""
    return f"/erp/drawing-workbench/{order_id}?tab=timeline"


def _fragment_get(client):
    return client.get(
        "/erp/drawing-workbench?view=fragment",
        headers={"X-FOMS-ERP-SHELL": "1"},
    )


def test_old_drawing_order_survives_newest_window(client):
    """접수순 창(cap) 밖으로 밀린 도면 단계 주문도 목록에 남는다."""
    _login_admin(client)
    old_id = _seed_order(1, stage="DRAWING", created_at=_OLD)
    db_session.commit()
    _seed_newest_noise(260)

    resp = _fragment_get(client)

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert _detail_link(old_id) in html, (
        "접수순 창 밖 도면 주문이 목록에서 사라졌다 — seed 가 단계 조건 없이 "
        "최신 N건만 뽑는 구조(운영 28건 중 27건 실종 사고)"
    )


def test_returned_outside_drawing_stage_survives(client):
    """수정요청(RETURNED)은 단계와 무관하게 남는다 — 수령확정 후 요청은 stage 무변경."""
    _login_admin(client)
    returned_id = _seed_order(
        2, stage="PRODUCTION", created_at=_OLD, drawing_status="RETURNED"
    )
    db_session.commit()
    _seed_newest_noise(260)

    resp = _fragment_get(client)

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert _detail_link(returned_id) in html, (
        "도면 단계 밖 RETURNED 주문이 사라졌다 — 모집단 술어가 단계만 보고 있다"
    )


def test_seed_query_scopes_to_drawing_queue_before_cap(app):
    """seed 는 cap 을 적용하기 전에 도면 모집단으로 선스코프한다(cap 무관 계약)."""
    old_id = _seed_order(3, stage="DRAWING", created_at=_OLD)
    _seed_order(4, stage="MEASURE", created_at=_NEW)
    _seed_order(5, stage="MEASURE", created_at=_NEW + datetime.timedelta(minutes=1))
    db_session.commit()

    query = db_session.query(Order).filter(
        Order.active_filter(), Order.is_erp_order.is_(True)
    )
    ids = fetch_drawing_seed_order_ids(query, cap=2)

    assert old_id in ids, (
        "cap 안에 최신 비(非)도면 주문만 들어차 도면 주문이 밀렸다 — "
        "단계 술어가 SQL 로 내려가지 않았다"
    )


def test_include_confirmed_lists_confirmed_outside_drawing_stage(client):
    """``?include_confirmed=1`` 은 수령확정 도면을 단계와 무관하게 보여준다.

    과거 이 경로는 ``erp_stage_code IN ('CONFIRM','고객컨펌')`` 으로 뽑은 뒤
    ``drawing_status == 'CONFIRMED'`` 만 남겼다. 도면 전달/수령확정이 stage 를 바꾸지
    않으므로(erp_orders_drawing.py) 두 조건이 동시에 참인 주문은 사실상 없었고,
    운영에서 컨펌 포함 토글은 CONFIRMED 36건을 두고도 0건을 보였다.
    """
    _login_admin(client)
    confirmed_id = _seed_order(
        6, stage="PRODUCTION", created_at=_OLD, drawing_status="CONFIRMED"
    )
    db_session.commit()
    _seed_newest_noise(260)

    off = _fragment_get(client)
    on = client.get(
        "/erp/drawing-workbench?view=fragment&include_confirmed=1",
        headers={"X-FOMS-ERP-SHELL": "1"},
    )

    assert off.status_code == 200 and on.status_code == 200
    link = _detail_link(confirmed_id)
    assert link not in off.get_data(as_text=True), "기본 목록은 컨펌 주문을 제외한다"
    assert link in on.get_data(as_text=True), "컨펌 포함 토글이 수령확정 도면을 못 찾는다"
