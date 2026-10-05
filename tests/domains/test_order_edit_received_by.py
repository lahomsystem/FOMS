"""주문 수정 화면 접수인(최초 주문 생성자) 표시 계약 (2026-10-05).

접수인은 ``ORDER_CREATED`` 이벤트 author 에서 읽는다. 그 이벤트는 ``create_order`` 가 모든
생성 경로에서 남긴다. 이벤트가 없는 옛 주문은 추정하지 않고 "기록 없음" 으로 둔다.

PC·모바일 폼 둘 다 접수 칸을 3등분(접수인 | 접수일 | 접수시간)한다.
"""

from __future__ import annotations

import datetime
import itertools
import re
from pathlib import Path

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.order_edit_view_context import build_order_creator
from foms.services.orders.order_create import CREATED_EVENT
from models import Order, OrderEvent, User

ROOT = Path(__file__).resolve().parents[2]
_counter = itertools.count(1)


def _make_user(name: str) -> int:
    n = next(_counter)
    user = User(
        username=f"received-by-{n}",
        password=generate_password_hash("pw"),
        role="ADMIN",
        team="SALES",
        name=name,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user.id


def _make_order(*, creator_id: int | None) -> int:
    order = Order(
        received_date="2026-10-05",
        received_time="10:00",
        customer_name="접수인 고객",
        phone="010-1234-5678",
        address="서울 접수구 1",
        product="붙박이장",
        status="RECEIVED",
        is_erp_order=True,
        erp_stage_code="RECEIVED",
        structured_data={
            "workflow": {"stage": "RECEIVED"},
            "parties": {"customer": {"name": "접수인 고객", "phone": "010-1234-5678"}},
            "items": [{"product_name": "붙박이장"}],
        },
    )
    db_session.add(order)
    db_session.flush()
    if creator_id is not None:
        db_session.add(
            OrderEvent(
                order_id=order.id, event_type=CREATED_EVENT,
                payload={"owner_user_id": creator_id, "status": "RECEIVED"},
                created_by_user_id=creator_id,
                # UTC-naive 규약 — 화면은 KST(+9h) 로 보여 준다.
                created_at=datetime.datetime(2026, 10, 5, 1, 30),
            )
        )
    db_session.commit()
    return order.id


def test_build_order_creator_reads_created_event_author(app):
    creator = _make_user("김접수")
    order_id = _make_order(creator_id=creator)

    info = build_order_creator(db_session, order_id)

    assert info == {"name": "김접수", "created_at": "2026-10-05 10:30"}


def test_build_order_creator_none_without_event(app):
    """옛 주문(이벤트 없음)은 담당자 등으로 추정하지 않는다."""
    order_id = _make_order(creator_id=None)

    assert build_order_creator(db_session, order_id) is None


def test_edit_page_shows_creator_not_viewer(client):
    creator = _make_user("김접수")
    viewer = _make_user("박열람")
    order_id = _make_order(creator_id=creator)
    with client.session_transaction() as sess:
        sess["user_id"] = viewer

    html = client.get(f"/edit/{order_id}").get_data(as_text=True)

    block = re.search(r'<div class="erp-received-by[^"]*".*?</div>', html, re.S)
    assert block, "접수인 칸이 렌더되지 않았다"
    assert "김접수" in block.group(0)
    assert "박열람" not in block.group(0)
    assert "주문 처음 등록 2026-10-05 10:30" in block.group(0)


def test_edit_page_legacy_order_says_no_record(client):
    viewer = _make_user("박열람")
    order_id = _make_order(creator_id=None)
    with client.session_transaction() as sess:
        sess["user_id"] = viewer

    html = client.get(f"/edit/{order_id}").get_data(as_text=True)

    assert 'erp-received-by is-empty' in html
    assert "기록 없음" in html


def _trio_labels(template: str) -> list[str]:
    src = (ROOT / "templates/orders/partials" / template).read_text(encoding="utf-8")
    start = src.index('<div class="erp-received-trio">')
    end = src.index('id="erp-received-time"', start)
    return re.findall(r">(접수인|접수일|접수시간)</", src[start:end])


def test_pc_and_mobile_split_received_row_in_three():
    assert _trio_labels("erp_order_tab.html") == ["접수인", "접수일", "접수시간"]
    assert _trio_labels("erp_order_tab_mobile.html") == ["접수인", "접수일", "접수시간"]
    pc = (ROOT / "templates/orders/partials/erp_order_tab.html").read_text(encoding="utf-8")
    # 예전 접수일+접수시간 두 칸 자리(8/12)를 3등분한다. 1200px 미만은 한 줄 전체(1/3 칸이면
    # 날짜가 잘린다) — 긴급 칸도 같은 경계(col-xl-4)로 아랫줄에 간다.
    assert '<div class="col-xl-8">\n                            <div class="erp-received-trio">' in pc
    assert '<div class="col-xl-4">\n                            <div class="d-flex align-items-center gap-2 mb-1 flex-wrap">\n                                <label class="form-label mb-0">긴급 발주</label>' in pc
    css = (ROOT / "static/css/foundation/erp-pro.css").read_text(encoding="utf-8")
    assert re.search(
        r"\.erp-received-trio \{[^}]*grid-template-columns: repeat\(3, minmax\(0, 1fr\)\)", css
    )
