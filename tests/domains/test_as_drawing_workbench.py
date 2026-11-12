"""완료 주문 AS 도면 — 도면 작업실 목록·실행판 화면 (설계서 2026-11-11-as-drawing-after-completion §6.1 · §4).

새 칸·새 열 없이 기존 칸(상태 · 다음 액션 · 시공일)과 맨 위 단추 글자만 바뀌는지 본다.
API·규칙 시험은 ``test_as_drawing_round.py``.
"""

from __future__ import annotations

import pytest

from tests.domains.test_as_drawing_round import (  # noqa: F401 - 픽스처도 함께 가져온다
    _as,
    _order,
    _put,
    _reset_cache_runtime,
    _sheet_png,
    _start,
    _user,
    storage,
)


# --------------------------------------------------------------------------
# 도면 작업실 목록 — 기존 칸에 글만 바뀐다(설계서 §6.1)
# --------------------------------------------------------------------------

def _workbench(client, query=""):
    res = client.get(f"/erp/drawing-workbench?view=fragment{query}", headers={"X-FOMS-ERP-SHELL": "1"})
    assert res.status_code == 200
    return res.get_data(as_text=True)


def _row_html(body, oid):
    marker = f"/erp/drawing-workbench/{oid}?tab=timeline"
    assert marker in body, "행이 목록에 없다"
    start = body.index(marker)
    return body[max(0, start - 200): start + 4000]


def test_workbench_lists_open_as_round_with_existing_cells(client):
    drafter = _user("asd_draw20")
    oid = _order(drawing_ids=[drafter.id], name="에이에스목록고객")
    other = _order(name="닫힌완료고객")  # 음성 대조: 차수 없는 완료 주문은 평소 목록에 없다
    _as(client, drafter)
    assert _start(client, oid, memo="문짝", as_register={"content": "문 처짐"}).status_code == 200

    body = _workbench(client)

    row = _row_html(body, oid)
    assert "AS 도면 그리기 · 1차" in row
    assert "AS 방문 미정" in row
    assert f"/erp/drawing-workbench/{other}?tab=timeline" not in body


def test_workbench_search_finds_completed_order_to_start(client):
    drafter = _user("asd_draw21")
    # 09-28 전 옛 주문처럼 도면 상태가 확정이 아니어도 검색으로 찾는다.
    oid = _order(name="검색완료고객", drawing_status="PENDING", with_wizard=False)
    _as(client, drafter)

    assert f"/erp/drawing-workbench/{oid}?tab=timeline" not in _workbench(client)
    body = _workbench(client, "&q=검색완료고객")

    assert "AS 도면 시작할 수 있어요" in _row_html(body, oid)



# --------------------------------------------------------------------------
# 실행판 — 맨 위 단추 글자와 AS 카드(설계서 §4.2 · §4.3)
# --------------------------------------------------------------------------

def _detail(client, oid):
    res = client.get(f"/erp/drawing-workbench/{oid}")
    assert res.status_code == 200
    return res.get_data(as_text=True)


def test_detail_shows_start_then_draw_then_review(client, storage):
    drafter = _user("asd_draw30")
    sales = _user("asd_sales30", team="SALES")
    oid = _order(drawing_ids=[drafter.id], name="실행판고객")
    _as(client, drafter)

    body = _detail(client, oid)
    assert "data-dw-as-start-open" in body and "AS 도면 시작" in body
    assert "AS 접수하고 도면 시작" in body  # AS 접수가 없으니 접수 칸이 함께 나온다
    assert "js/drawing/workbench-as.js" in body

    assert _start(client, oid, memo="문짝", as_register={"content": "문 처짐"}).status_code == 200
    body = _detail(client, oid)
    assert "data-dw-as-start-open" not in body
    assert "AS 도면 그리기" in body and "AS 도면 1차" in body
    assert "채널톡 AS방에 접수 올리기" in body  # 아직 AS PUSH 이력이 없다

    assert _put(client, oid, [{"id": "s-1", "name": "냉장고장", "form": {}, "objects": []},
                              {"id": "s-2", "name": "AS 문짝", "form": {}, "objects": []}]).status_code == 200
    assert _sheet_png(client, oid, "s-2", "as1.png").status_code == 200
    assert 'data-dw-as-act="transfer"' in _detail(client, oid)
    assert client.post(f"/api/orders/{oid}/drawing/as/transfer", json={}).status_code == 200

    _as(client, sales)
    body = _detail(client, oid)
    assert 'data-dw-as-act="confirm"' in body and "확인했어요" in body
    assert 'data-dw-as-act="transfer"' not in body


def test_detail_for_open_drawing_stage_order_has_no_as_card(client):
    drafter = _user("asd_draw31")
    oid = _order(stage="DRAWING", drawing_ids=[drafter.id], name="도면단계고객")
    _as(client, drafter)

    body = _detail(client, oid)

    assert 'id="dw-as-card"' not in body and "data-dw-as-start-open" not in body
    assert "도면 마법사" in body


# --------------------------------------------------------------------------
# 흐름 1 화면 — AS 접수 창 '도면팀에 정확한 도면 부탁' 한 줄(설계서 §4.1)
# --------------------------------------------------------------------------

def test_as_receive_modal_has_drawing_request_line():
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2]
    for name in ("erp_order_tab.html", "erp_order_tab_mobile.html"):
        html = (root / "templates" / "orders" / "partials" / name).read_text(encoding="utf-8")
        assert 'id="as-receive-drawing-request"' in html and "도면팀에 정확한 도면 부탁" in html, name
        assert 'id="as-receive-drawing-wrap"' in html, name
    js = (root / "static" / "js" / "orders" / "erp-order-shared.js").read_text(encoding="utf-8")
    assert "regPayload.drawing_request = { memo:" in js
    # 시공이 끝난 단계에서만 보이고, 열 때마다 초기화한다.
    helper = js[js.index("function erpRefreshAsDrawingRequest("):]
    helper = helper[: helper.index("\n}\n")]
    assert "'COMPLETED'" in helper and "'CS'" in helper and "box.checked = false" in helper
    assert "erpRefreshAsDrawingRequest();" in js


# --------------------------------------------------------------------------
# 마법사 — 설정값 · [저장] 창 보내기 = AS 도면 보내기(설계서 §4.3)
# --------------------------------------------------------------------------

import copy  # noqa: E402

from db import db_session  # noqa: E402
from foms.services.orders import as_drawing as asd  # noqa: E402
from models import Order, SecurityLog, User  # noqa: E402


def _sd(oid):
    db_session.expire_all()
    return copy.deepcopy(db_session.get(Order, oid).structured_data or {})


def test_wizard_page_carries_as_config_only_after_completion(client):
    drafter = _user("asd_draw40")
    done = _order(drawing_ids=[drafter.id], name="마법사완료고객")
    open_stage = _order(stage="DRAWING", drawing_ids=[drafter.id], name="마법사도면고객")
    _as(client, drafter)

    body = client.get(f"/erp/drawing-workbench/{done}/wizard").get_data(as_text=True)
    assert "js/drawing/wizard-as.js" in body and '"as_drawing": {' in body
    assert '"locked_sheet_ids": ["s-1"]' in body and '"round": null' in body

    other = client.get(f"/erp/drawing-workbench/{open_stage}/wizard").get_data(as_text=True)
    assert "js/drawing/wizard-as.js" not in other and '"as_drawing": null' in other


# 마법사 [저장] 창 '도면 발송'(save-send.js)은 transfer-drawing 에 pending_sheet_ids 를 싣고,
# 작업실 일괄 전달은 transfer-pending 을 부른다 — 완료 주문이면 둘 다 AS 도면 보내기다(스테이징 실화면 11-12).
_SAVE_WINDOW_ROUTES = [
    ("drawing-wizard/transfer-pending", {"note": "확인"}),
    ("transfer-drawing", {"note": "확인", "files": [], "pending_sheet_ids": ["s-1", "s-2"], "mode": "APPEND"}),
]


@pytest.mark.parametrize("route,body", _SAVE_WINDOW_ROUTES, ids=["transfer-pending", "transfer-drawing"])
def test_save_window_send_becomes_as_transfer_after_completion(client, storage, route, body):
    drafter = _user(f"asd_draw41_{len(route)}")
    oid = _order(drawing_ids=[drafter.id], name="저장창고객")
    original = _sd(oid)
    _as(client, drafter)

    r0 = client.post(f"/api/orders/{oid}/{route}", json=body)
    assert r0.status_code == 400 and r0.get_json()["error"] == "NO_OPEN_ROUND"

    assert _start(client, oid, memo="m", as_register={"content": "c"}).status_code == 200
    assert _put(client, oid, [{"id": "s-1", "name": "냉장고장", "form": {}, "objects": []},
                              {"id": "s-2", "name": "AS", "form": {}, "objects": []}]).status_code == 200
    assert _sheet_png(client, oid, "s-2", "as.png").status_code == 200

    res = client.post(f"/api/orders/{oid}/{route}", json=body)

    body = res.get_json()
    assert res.status_code == 200, body
    assert body["data"]["as_drawing"] is True and body["data"]["count"] == 1
    sd = _sd(oid)
    assert asd.current_round(sd)["status"] == asd.STATUS_TRANSFERRED
    for key in ("drawing_current_files", "drawing_status", "drawing_transfer_history"):
        assert sd[key] == original[key], key
    # 행위 1건 = 감사 1행(누가 · 어느 주문 · 몇 차).
    logs = db_session.query(SecurityLog).filter_by(action="AS_DRAWING_TRANSFERRED", target_id=oid).all()
    assert len(logs) == 1 and logs[0].user_id == drafter.id and logs[0].detail["round_no"] == 1


def test_main_transfer_function_refuses_wizard_sheet_files_after_completion(app):
    from foms.api.drawing.erp_orders_drawing import perform_drawing_transfer

    drafter = _user("asd_draw42")
    oid = _order(drawing_ids=[drafter.id], name="방어고객")
    with app.test_request_context():
        order = db_session.get(Order, oid)
        user = db_session.get(User, drafter.id)
        payload, status = perform_drawing_transfer(
            db_session, order, oid, user, user.id,
            files=[{"key": f"orders/{oid}/drawing_wizard/exports/x.png", "filename": "x.png", "sheet_id": "s-1"}])
    db_session.rollback()
    assert status == 400 and payload["error"] == "USE_AS_TRANSFER"


# --------------------------------------------------------------------------
# 주문 화면 'AS 도면' 묶음(설계서 §4.3-5) — 원래 도면 갤러리와 따로
# --------------------------------------------------------------------------

def test_order_page_has_as_panel_and_get_view_lets_sales_review(client, storage):
    drafter = _user("asd_draw50")
    sales = _user("asd_sales50", team="SALES")
    admin = _user("asd_admin50", role="ADMIN", team="CS")
    oid = _order(drawing_ids=[drafter.id], name="주문화면고객")
    _as(client, admin)
    page = client.get(f"/edit/{oid}", headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/130"})
    html = page.get_data(as_text=True)
    assert 'id="erp-as-drawing-panel"' in html and "js/orders/erp-as-drawing-panel" in html

    _as(client, drafter)
    assert _start(client, oid, memo="m", as_register={"content": "c"}).status_code == 200
    assert _put(client, oid, [{"id": "s-1", "name": "냉장고장", "form": {}, "objects": []},
                              {"id": "s-2", "name": "AS", "form": {}, "objects": []}]).status_code == 200
    assert _sheet_png(client, oid, "s-2", "as.png").status_code == 200
    assert client.post(f"/api/orders/{oid}/drawing/as/transfer", json={}).status_code == 200
    assert client.get(f"/api/orders/{oid}/drawing/as").get_json()["data"]["can_review"] is False  # 도면팀

    _as(client, sales)
    data = client.get(f"/api/orders/{oid}/drawing/as").get_json()["data"]
    assert data["can_review"] is True
    assert data["current"]["files"][0]["view_url"].startswith(f"/api/files/view/orders/{oid}/")
    assert data["workbench_url"] == f"/erp/drawing-workbench/{oid}"
