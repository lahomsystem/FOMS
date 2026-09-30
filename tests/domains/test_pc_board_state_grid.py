"""PC 주문 대시보드 '현재 작업' 칸 — 생산·시공·완료·AS 줄은 board_state 배지·링크로 그린다(2단계)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

STYLE_FILES = (
    "static/css/contexts/orders/dashboard-grid.css",
    "static/css/contexts/construction/dashboard.css",
    "templates/production/partials/styles.html",
)
BOARD_GRIDS = (
    "templates/construction/partials/filters_grid.html",
    "templates/production/partials/filters_grid.html",
)


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _db_user(username: str, *, role: str, team: str | None):
    from werkzeug.security import generate_password_hash

    from db import db_session
    from models import User

    user = User(username=username, password=generate_password_hash("pw"), role=role, team=team,
                name=f"{username} 이름", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _db_order(stage_code: str, customer_name: str, history: list | None = None):
    from db import db_session
    from foms.services.erp_display import get_today_kst
    from models import Order

    workflow = {"stage": stage_code}
    if history is not None:
        workflow["history"] = history
    order = Order(
        received_date=get_today_kst().isoformat(), customer_name=customer_name, phone="010-1234-5678",
        address="서울 테헤란로 123", product="붙박이장", status=stage_code, manager_name="담당",
        is_erp_order=True, structured_data={"workflow": workflow, "quests": []},
        erp_stage_code=stage_code,
    )
    db_session.add(order)
    db_session.commit()
    return order


def _grid_html(client, user, stage_label: str) -> str:
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    resp = client.get("/erp/dashboard", query_string={"stage": stage_label})
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


def _board_cell(html: str, order_id: int):
    from bs4 import BeautifulSoup

    row = BeautifulSoup(html, "html.parser").find("tr", attrs={"data-order-id": str(order_id)})
    assert row is not None
    cell = row.find("td", attrs={"data-col-key": "quest"})
    assert cell is not None
    return cell


def test_construction_rows_show_wait_or_running_with_board_link(client):
    user = _db_user("board_cons_admin", role="ADMIN", team="CS")
    waiting_id = _db_order("CONSTRUCTION", "시공 대기").id
    running_id = _db_order("CONSTRUCTION", "시공 진행", history=[{"note": "시공 시작"}]).id

    html = _grid_html(client, user, "시공")
    waiting = _board_cell(html, waiting_id)
    assert waiting.select_one(".erp-board-state .badge").get_text(strip=True) == "시공대기"
    link = waiting.select_one(".erp-board-state a")
    assert link["href"] == f"/erp/construction/dashboard?focus_order={waiting_id}"
    assert link.get_text(strip=True) == "시공 보드 열기"

    running = _board_cell(html, running_id)
    assert running.select_one(".erp-board-state .badge").get_text(strip=True) == "시공중"


def test_production_row_with_current_run_shows_running(client):
    from db import db_session
    from models import ProductionRun

    user = _db_user("board_prod_admin", role="ADMIN", team="CS")
    order = _db_order("PRODUCTION", "제작 진행")
    db_session.add(ProductionRun(order_id=order.id, status="IN_PROGRESS", steps=[], defects=[], is_current=True))
    db_session.commit()

    cell = _board_cell(_grid_html(client, user, "생산"), order.id)
    assert cell.select_one(".erp-board-state .badge").get_text(strip=True) == "제작중"
    link = cell.select_one(".erp-board-state a")
    assert link["href"] == f"/erp/production/dashboard?focus_order={order.id}"
    assert link.get_text(strip=True) == "생산 보드 열기"


def test_completed_row_is_green_badge_only(client):
    user = _db_user("board_done_admin", role="ADMIN", team="CS")
    order_id = _db_order("COMPLETED", "완료 주문").id

    html = _grid_html(client, user, "완료")
    cell = _board_cell(html, order_id)
    badge = cell.select_one(".erp-board-state .badge")
    assert "bg-success" in badge["class"]
    assert badge.get_text(strip=True) == "완료"
    assert cell.select_one(".erp-board-state a") is None
    assert f"quest-collapse-{order_id}" not in html


def test_as_row_shows_title_and_as_link(client):
    user = _db_user("board_as_admin", role="ADMIN", team="CS")
    order_id = _db_order("AS", "AS 주문").id

    html = _grid_html(client, user, "AS처리")
    cell = _board_cell(html, order_id)
    badge = cell.select_one(".erp-board-state .badge")
    assert "bg-warning" in badge["class"]
    assert badge.get_text(strip=True) == "할 일"
    assert cell.select_one(".erp-board-state strong").get_text(strip=True) == "AS 확인"
    link = cell.select_one(".erp-board-state a")
    assert link["href"] == f"/erp/as?focus_order={order_id}"
    assert link.get_text(strip=True) == "AS 화면 열기"
    assert "(보드에서 진행)" not in html


def test_대조군_주문접수는_여전히_quest_펼침과_넘기기_버튼(client):
    user = _db_user("board_recv_admin", role="ADMIN", team="CS")
    order_id = _db_order("RECEIVED", "접수 주문").id

    html = _grid_html(client, user, "주문접수")
    cell = _board_cell(html, order_id)
    assert cell.select_one(".erp-board-state") is None
    assert f"quest-collapse-{order_id}" in html
    buttons = cell.select(".erp-btn-approve-team")
    assert [b.get_text(" ", strip=True) for b in buttons] == ["실측 단계로 넘기기"]


def test_quest_cell_selectors_use_class_not_label():
    for rel in STYLE_FILES:
        body = _read(rel)
        assert 'data-label="퀘스트"' not in body, rel
        assert "td.erp-quest-cell" in body, rel


def test_board_grids_use_phase1_names():
    for rel in BOARD_GRIDS:
        body = _read(rel)
        for old in ("퀘스트", "진행중", "팀별 승인", "승인완료"):
            assert old not in body, (rel, old)
