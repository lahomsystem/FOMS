"""PARTNER-FOMS 3-2: 협력사 주문 목록(우리 ERP 대시보드 모양) — 프로세스 맵 · 필터 · 작업 큐 · 내 차례.

스펙 docs/specs/2026-10-19-partner-foms-mode_SPEC.md §3.1 · §3.2.
각 필터에는 걸러져야 할 대조군(다른 단계 · 다른 담당 · 다른 회사)을 같이 둔다.
"""
from __future__ import annotations

from db import db_session
from foms.services.partners.order_list import partner_list_filters, partner_order_board
from models import Order, User
from tests.security.partner_fixtures import (  # noqa: F401 — pytest fixture 재노출
    _PAYLOAD,
    _client,
    _create,
    _to_confirm,
    _to_stage,
    world,
)


def _order(app, partner_id, name, phone="010-1234-5678") -> int:
    resp = _create(app, partner_id, {**_PAYLOAD, "customer_name": name, "customer_phone": phone})
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["data"]["order_id"]


def _seed(app, world) -> dict[str, int]:
    ids = {
        "measure": _order(app, world["partner_a"], "접수고객"),
        "confirm": _order(app, world["partner_a"], "확인고객", phone="010-7777-8888"),
        "done": _order(app, world["partner_a"], "완료고객"),
        "as": _order(app, world["partner_a"], "에이에스고객"),
        "mine2": _order(app, world["partner_a2"], "둘째고객"),
        "other": _order(app, world["partner_b"], "남의고객"),
    }
    _to_confirm(ids["confirm"])
    _to_stage(ids["done"], "COMPLETED")
    _to_stage(ids["as"], "COMPLETED")
    db_session.get(Order, ids["as"]).as_axis_status = "RECEIVED"
    db_session.commit()
    return ids


def _board(world, user_key="partner_a", **args):
    filters = partner_list_filters(args)
    return partner_order_board(db_session, world["org_a"], world[user_key], filters, {})


def test_pipeline_counts_own_company_only_and_turn_first(app, world):
    ids = _seed(app, world)
    board = _board(world)
    counts = {step["label"]: step["count"] for step in board["pipeline"]}
    assert counts == {"접수 확인 중": 2, "도면 작업 중": 0, "도면 확인 대기": 1, "생산 중": 0,
                      "시공 예정": 0, "완료": 1, "AS 진행 중": 1}
    assert board["turn_count"] == 1
    assert board["orders"][0]["id"] == ids["confirm"] and board["orders"][0]["turn"] is True
    assert ids["other"] not in {o["id"] for o in board["orders"]}


def test_filters_narrow_and_unknown_values_are_ignored(app, world):
    ids = _seed(app, world)
    assert [o["id"] for o in _board(world, stage="완료")["orders"]] == [ids["done"]]
    assert [o["id"] for o in _board(world, turn="1")["orders"]] == [ids["confirm"]]
    assert [o["id"] for o in _board(world, q="7777")["orders"]] == [ids["confirm"]]  # 연락처 숫자
    assert [o["id"] for o in _board(world, q=str(ids["done"]))["orders"]] == [ids["done"]]  # 주문 번호
    assert [o["id"] for o in _board(world, q="둘째")["orders"]] == [ids["mine2"]]
    assert [o["id"] for o in _board(world, "partner_a2", mine="1")["orders"]] == [ids["mine2"]]
    assert [o["id"] for o in _board(world, manager=str(world["partner_a2"]))["orders"]] == [ids["mine2"]]
    # 모르는 단계 · 숫자 아닌 담당은 버린다(전체 목록).
    assert len(_board(world, stage="xyz", manager="abc")["orders"]) == 5


def test_list_page_renders_board_and_hides_other_company(app, world):
    ids = _seed(app, world)
    client = _client(app, db_session.get(User, world["partner_a"]))
    html = client.get("/partner").get_data(as_text=True)
    assert "프로세스 맵" in html and "작업 큐" in html and "pp-pipe--turn" in html
    assert f'data-pp-row-href="/partner/orders/{ids["confirm"]}"' in html and "남의고객" not in html
    filtered = client.get("/partner?stage=완료").get_data(as_text=True)
    assert "완료고객" in filtered and "접수고객" not in filtered


def test_nav_turn_badge_on_every_partner_page(app, world):
    ids = _seed(app, world)
    client = _client(app, db_session.get(User, world["partner_a"]))
    page = client.get(f"/partner/orders/{ids['measure']}").get_data(as_text=True)
    assert '도면 확인 <span class="badge rounded-pill bg-danger">1</span>' in page
    # 대조군: 다른 회사 직원에게는 우리 회사 차례 수가 보이지 않는다.
    other = _client(app, db_session.get(User, world["partner_b"])).get("/partner").get_data(as_text=True)
    assert 'bg-danger">1</span>' not in other
