"""완료 주문 AS 도면 — 도면 작업실 목록·실행판 화면 (설계서 2026-11-11-as-drawing-after-completion §6.1 · §4).

새 칸·새 열 없이 기존 칸(상태 · 다음 액션 · 시공일)과 맨 위 단추 글자만 바뀌는지 본다.
API·규칙 시험은 ``test_as_drawing_round.py``.
"""

from __future__ import annotations

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
