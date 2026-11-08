"""생산 · 시공 판 PC 작업 큐 표가 비면 빈 줄 하나를 그린다(2026-11-08 점검 ui-pc 3).

출고 · AS · 완료 표와 같은 말 · 같은 클래스("데이터가 없습니다." · text-center text-muted py-4).
대조군: 주문이 하나라도 있으면 빈 줄이 없다.
"""

from __future__ import annotations

from datetime import date

import pytest
from bs4 import BeautifulSoup
from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User

EMPTY_TEXT = "데이터가 없습니다."
BOARDS = {
    # 화면 주소: (주문 status, 단계 원문 — 단계 SQL 필터가 erp_stage_code 를 읽는다)
    "/erp/production/dashboard": ("PRODUCTION", "생산"),
    "/erp/construction/dashboard": ("CONSTRUCTION", "CONSTRUCTION"),
}


def _login_plain_admin(client) -> None:
    """팀 없는 ADMIN — 시공팀 mine 강제 없이 전체를 본다."""
    user = User(
        username="board_grid_empty_admin", password=generate_password_hash("admin"),
        role="ADMIN", team=None, name="판 빈 줄 관리자", is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _grid_body(client, url: str):
    resp = client.get(url)
    assert resp.status_code == 200
    grid = BeautifulSoup(resp.get_data(as_text=True), "html.parser").find("table", id="erp-grid")
    assert grid is not None, "PC 작업 큐 표(#erp-grid)가 없다"
    return grid.find("tbody")


@pytest.mark.parametrize("url", sorted(BOARDS))
def test_빈_판은_빈_줄_하나(client, url: str) -> None:
    _login_plain_admin(client)
    body = _grid_body(client, url)
    rows = body.find_all("tr")
    assert len(rows) == 1
    cell = rows[0].find("td")
    assert cell.get_text(strip=True) == EMPTY_TEXT
    assert cell.get("colspan") == "13"  # 머리 칸 13개를 다 덮는다
    assert cell.get("class") == ["text-center", "text-muted", "py-4"]


@pytest.mark.parametrize("url", sorted(BOARDS))
def test_대조군_주문이_있으면_빈_줄이_없다(client, url: str) -> None:
    _login_plain_admin(client)
    status, stage = BOARDS[url]
    order = Order(
        received_date=date.today().strftime("%Y-%m-%d"), customer_name="판 빈 줄 대조군",
        phone="010-0000-0000", address="Seoul", product="붙박이장", status=status,
        manager_name="Bob", is_erp_order=True, structured_data={"workflow": {"stage": stage}},
        erp_stage_code=stage,
    )
    db_session.add(order)
    db_session.commit()
    body = _grid_body(client, url)
    assert body.find("tr", attrs={"data-order-id": str(order.id)}) is not None
    assert EMPTY_TEXT not in body.get_text()
