"""태블릿 칸반 전량 렌더 회귀 고정 (page 윈도 소실 버그).

R1 시공일 정렬 도입 후, 시공일 변경으로 rank>page_size 가 된 카드가 page1 윈도에서만
렌더돼 사라진 회귀. 칸반은 정렬 전량(캡 300)을 소비해야 한다.

- (a) 51건 시드 → rank51 주문이 kanban_orders 에 존재(page1 orders 엔 없음).
- (b) orders 는 여전히 50건 페이지.
- (c) 캡 초과 → 상위 N 제한 + kanban_capped=True.
- (d) changed_count 는 kanban(보드 전체) 기준.
"""

from __future__ import annotations

import datetime

from werkzeug.security import generate_password_hash

import foms.web.production.dashboard as pd
from db import db_session
from models import Order, OrderEvent, User

_T0 = datetime.datetime(2026, 7, 1, 0, 0, 0)


def _make_user(username="kanban_admin"):
    u = User(
        username=username,
        password=generate_password_hash("pw"),
        role="ADMIN",
        name=username,
        is_active=True,
    )
    db_session.add(u)
    db_session.commit()
    return u


def _login(client, user):
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _make_prod_order(cdate: str) -> Order:
    order = Order(
        received_date="2026-07-01",
        customer_name=f"고객{cdate}",
        phone="010-0000-0000",
        address="Seoul",
        product="붙박이장",
        status="PRODUCTION",
        is_erp_order=True,
        structured_data={"workflow": {"stage": "PRODUCTION"}},
        erp_stage_code="PRODUCTION",
        erp_construction_date=cdate,
        erp_stage_updated_at=_T0,
    )
    db_session.add(order)
    db_session.commit()
    return order


def _get_ctx(client, monkeypatch, query=""):
    captured = {}

    def _fake_render(template_name, **ctx):
        captured.update(ctx)
        return ""

    monkeypatch.setattr(pd, "render_template", _fake_render)
    res = client.get("/erp/production/dashboard" + query)
    assert res.status_code == 200
    return captured


def test_rank51_order_in_kanban_but_not_page1(client, monkeypatch):
    user = _make_user("kanban_a")
    _login(client, user)
    # 51건: 시공일 asc 정렬 시 마지막(가장 늦은 날짜)이 rank 51.
    ids_by_rank = []
    for i in range(1, 52):
        o = _make_prod_order(f"2026-08-{i:02d}" if i <= 31 else f"2026-09-{i - 31:02d}")
        ids_by_rank.append(o.id)
    rank51_id = ids_by_rank[-1]

    ctx = _get_ctx(client, monkeypatch)
    kanban_ids = {r["id"] for r in ctx["kanban_orders"]}
    page_ids = {r["id"] for r in ctx["orders"]}

    # (a) rank51 은 칸반엔 있고 page1 엔 없다 — 회귀 고정.
    assert rank51_id in kanban_ids
    assert rank51_id not in page_ids
    # (b) orders 는 50건 페이지, kanban 은 전량 51.
    assert len(ctx["orders"]) == 50
    assert len(ctx["kanban_orders"]) == 51
    assert ctx["kanban_capped"] is False


def test_cap_limits_kanban_and_flags(client, monkeypatch):
    user = _make_user("kanban_b")
    _login(client, user)
    monkeypatch.setattr(pd, "PRODUCTION_KANBAN_MAX_ROWS", 3)
    for i in range(1, 5):  # 4건 > cap 3
        _make_prod_order(f"2026-08-{i:02d}")

    ctx = _get_ctx(client, monkeypatch)
    assert ctx["kanban_capped"] is True
    assert len(ctx["kanban_orders"]) == 3
    # PC 리스트는 페이지네이션(50)이라 4건 전부.
    assert len(ctx["orders"]) == 4


def test_changed_count_is_kanban_based(client, monkeypatch):
    user = _make_user("kanban_c")
    _login(client, user)
    ids_by_rank = []
    for i in range(1, 52):
        o = _make_prod_order(f"2026-08-{i:02d}" if i <= 31 else f"2026-09-{i - 31:02d}")
        ids_by_rank.append(o.id)
    rank51_id = ids_by_rank[-1]
    # rank51(=page1 밖) 주문에 시공일 변경 이벤트(윈도 이후) → has_changes.
    ev = OrderEvent(
        order_id=rank51_id,
        event_type="CONSTRUCTION_DATE_CHANGED",
        payload={"from": "2026-09-20", "to": "2026-09-25"},
        created_at=_T0 + datetime.timedelta(days=3),
    )
    db_session.add(ev)
    db_session.commit()

    ctx = _get_ctx(client, monkeypatch)
    page_ids = {r["id"] for r in ctx["orders"]}
    assert rank51_id not in page_ids            # page1 밖임을 확인
    # 보드 전체 기준이라 page 밖 변경도 카운트된다(구 버그: page 기준이면 0).
    assert ctx["changed_count"] == 1
    changed = [r["id"] for r in ctx["kanban_orders"] if r.get("has_changes")]
    assert changed == [rank51_id]
