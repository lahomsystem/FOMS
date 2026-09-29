"""2a-2 Q2 화면 — 생산 보드 "도면 수정 중" 배지와 [제작 시작] 막힘(화면 == 서버).

사용자 결정(2026-09-29): 생산 대기 주문에 수정요청이 오면 [제작 시작] 을 막고(관리자만 사유 적고
가능), 생산팀이 수정요청을 알 수 있게 PC 생산 보드·모바일 생산 카드에 배지를 단다. 배지는
대기·진행 중 모두, 버튼 막기는 대기만. 판정은 제작 시작 라우트와 같은 함수
(``confirm_drawing_gate``)이고, 수령 확정되면 배지가 바로 사라져야 한다.

실제 라우트 순서를 밟는다(합성 상태 주입 없음): 전달 → 수령 확정 → 고객컨펌 승인(생산 대기)
→ 수정요청(RETURNED) → 재전달(TRANSFERRED) → 수령 확정(CONFIRMED).
"""
from __future__ import annotations

import re
from pathlib import Path

from db import db_session
from models import ProductionRun
from tests.support.confirm_seed import (
    confirmed_drawing_sd,
    login_as,
    reload_order,
    seed_erp_order,
    seed_user,
)

_BADGE = "data-drawing-revision-badge"
_BLOCKED = "data-production-start-blocked"
_OVERRIDE = {"admin_override": True, "override_reason": "현장 구두 확인 — 옛 도면 그대로 제작"}


def _enable_v2(monkeypatch, *user_ids: int) -> None:
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", ",".join(str(i) for i in user_ids))


def _board(client) -> str:
    resp = client.get("/erp/production/dashboard")
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


def _section(body: str, start_marker: str, end_marker: str) -> str:
    assert start_marker in body, start_marker
    start = body.index(start_marker)
    return body[start:body.index(end_marker, start)]


def _pc_grid(body: str) -> str:
    return _section(body, 'id="erp-grid"', "</table>")


def _mobile_queue(body: str) -> str:
    return _section(body, 'aria-label="생산 모바일 작업 큐"', "</section>")


def _kanban(body: str) -> str:
    return _section(body, 'aria-label="생산 칸반 보드"', "</section>")


def _row(grid: str, order_id: int) -> str:
    """PC 그리드에서 그 주문의 본행(<tr class="erp-main-row" ...>) 한 줄만."""
    marker = f'<tr class="erp-main-row" data-order-id="{order_id}">'
    return _section(grid, marker, "</tr>")


def _card(queue: str, order_id: int) -> str:
    marker = f'<article class="queue-card foms-queue-card-v2" data-order-id="{order_id}"'
    return _section(queue, marker, "</article>")


def _start(client, order_id: int, body: dict | None = None):
    return client.post(f"/api/orders/{order_id}/production/start", json=body or {})


def _walk_to_production_waiting(client, tag: str):
    """전달 → 수령 확정 → 고객컨펌 승인으로 생산 대기(PRODUCTION·run 없음)까지. (id, 영업, 도면)."""
    sales = seed_user(f"pb_s_{tag}", team="SALES")
    drafter = seed_user(f"pb_d_{tag}", team="DRAWING")
    oid = seed_erp_order("DRAWING", sales=sales, drafter=drafter)
    key = f"orders/{oid}/drawing_wizard/exports/v1.png"
    login_as(client, drafter)
    assert client.post(f"/api/orders/{oid}/transfer-drawing",
                       json={"files": [{"key": key, "filename": "v1.png"}]}).status_code == 200
    login_as(client, sales)
    assert client.post(f"/api/orders/{oid}/confirm-drawing-receipt", json={}).status_code == 200
    approved = client.post(f"/api/orders/{oid}/quest/approve", json={})
    assert approved.status_code == 200, approved.get_json()
    assert reload_order(oid).erp_stage_code == "PRODUCTION"
    return oid, sales, drafter


def _request_revision(client, oid: int, sales) -> None:
    login_as(client, sales)
    asked = client.post(f"/api/orders/{oid}/request-revision", json={"note": "손잡이 색 변경"})
    assert asked.status_code == 200, asked.get_json()
    assert reload_order(oid).structured_data["drawing_status"] == "RETURNED"


# --------------------------------------------------------------------------- #
# 수정요청 → 재전달 → 수령 확정: 배지·막힘이 서버 판정과 같이 켜지고 꺼진다
# --------------------------------------------------------------------------- #
def test_badge_and_start_block_follow_revision_then_vanish_on_receipt(client, monkeypatch):
    oid, sales, drafter = _walk_to_production_waiting(client, "flow")
    prod = seed_user("pb_p_flow", team="PRODUCTION")
    _enable_v2(monkeypatch, prod.id)

    # 음성 대조(모집단 안): 수령 확정된 생산 대기 주문 — 배지 없음, 제작 시작 버튼 그대로.
    login_as(client, prod)
    body = _board(client)
    row = _row(_pc_grid(body), oid)
    assert _BADGE not in row and _BLOCKED not in row
    assert 'data-action="startProduction"' in row
    assert _BADGE not in _card(_mobile_queue(body), oid)

    # 수정요청(RETURNED) — PC·모바일·칸반 모두 배지, 비관리자는 버튼 대신 막힌 이유(영업 이름 포함).
    _request_revision(client, oid, sales)
    login_as(client, prod)
    body = _board(client)
    row = _row(_pc_grid(body), oid)
    assert _BADGE in row and "도면 수정 중" in row
    assert 'data-action="startProduction"' not in row
    assert _BLOCKED in row and sales.name in row and "도면을 고치는 중" in row
    card = _card(_mobile_queue(body), oid)
    assert _BADGE in card and _BLOCKED in card
    assert 'data-action="startProduction"' not in card
    assert "도면 확정 대기" in card
    assert _BADGE in _kanban(body)
    # 화면 == 서버: 같은 사람이 눌러도 409 DRAWING_STATUS(같은 생산팀 문구).
    resp = _start(client, oid)
    assert resp.status_code == 409 and resp.get_json()["code"] == "DRAWING_STATUS"
    assert sales.name in resp.get_json()["message"]

    # 반영 체크 → 재전달(TRANSFERRED) — 아직 수령 확정 전이라 배지·막힘 유지(문구만 "확정 대기").
    req = [h for h in reload_order(oid).structured_data["drawing_transfer_history"]
           if h.get("action") == "REQUEST_REVISION"][-1]
    login_as(client, drafter)
    assert client.post(f"/api/orders/{oid}/request-revision-check",
                       json={"request_at": req["at"], "by_user_id": req["by_user_id"], "checked": True}).status_code == 200
    key = f"orders/{oid}/drawing_wizard/exports/v2.png"
    sent = client.post(f"/api/orders/{oid}/transfer-drawing",
                       json={"files": [{"key": key, "filename": "v2.png"}], "mode": "APPEND", "is_retransfer": True})
    assert sent.status_code == 200, sent.get_json()
    login_as(client, prod)
    row = _row(_pc_grid(_board(client)), oid)
    assert "도면 수정 중 · 확정 대기" in row and _BLOCKED in row
    assert _start(client, oid).status_code == 409

    # 수령 확정(단계 유지) — 새로고침 즉시 배지·막힘이 사라지고 버튼이 돌아온다(캐시 무효화 포함).
    login_as(client, sales)
    received = client.post(f"/api/orders/{oid}/confirm-drawing-receipt", json={})
    assert received.status_code == 200, received.get_json()
    assert reload_order(oid).erp_stage_code == "PRODUCTION"
    login_as(client, prod)
    body = _board(client)
    row = _row(_pc_grid(body), oid)
    assert _BADGE not in row and _BLOCKED not in row
    assert 'data-action="startProduction"' in row
    card = _card(_mobile_queue(body), oid)
    assert _BADGE not in card and 'data-action="startProduction"' in card
    assert _start(client, oid).status_code == 200


def test_admin_sees_warning_start_button_and_reason_then_punches(client, monkeypatch):
    oid, sales, _drafter = _walk_to_production_waiting(client, "adm")
    _request_revision(client, oid, sales)
    admin = seed_user("pb_admin", role="ADMIN", team=None)
    _enable_v2(monkeypatch, admin.id)
    login_as(client, admin)

    body = _board(client)
    row = _row(_pc_grid(body), oid)
    assert 'data-action="startProduction"' in row and "btn-warning" in row
    assert _BLOCKED in row
    card = _card(_mobile_queue(body), oid)
    assert 'data-action="startProduction"' in card and "foms-btn--warning" in card
    assert "foms-kanban-move-btn--warn" in _kanban(body)
    # 경고 버튼의 요청: 보통 요청은 409, 사유를 실은 재시도(FomsAdminOverride)는 통과.
    assert _start(client, oid).status_code == 409
    assert _start(client, oid, _OVERRIDE).status_code == 200


def test_badge_shows_while_in_progress_but_does_not_block(client):
    """이미 만드는 중(run 있음)이면 배지는 달되 막지 않는다(제작 완료 버튼 그대로)."""
    prod = seed_user("pb_p_run", team="PRODUCTION")
    running = seed_erp_order("PRODUCTION", **confirmed_drawing_sd(drawing_status="RETURNED"))
    db_session.add(ProductionRun(order_id=running, status="IN_PROGRESS", steps=[], defects=[], is_current=True))
    db_session.commit()
    login_as(client, prod)

    row = _row(_pc_grid(_board(client)), running)
    assert _BADGE in row and "생산 중" in row
    assert _BLOCKED not in row


def test_confirm_compat_waiting_row_blocks_on_allowlist_like_server(client):
    """CONFIRM 호환 제작 대기(퀘스트 완료)는 허용 목록 — 기록 없음(NONE)도 막힌다(배지는 없다)."""
    from tests.support.quest_seed import confirm_quest_completed

    prod = seed_user("pb_p_cc", team="PRODUCTION")
    sales = seed_user("pb_s_cc", team="SALES")
    oid = seed_erp_order("CONFIRM", sales=sales, quests=[confirm_quest_completed()])
    login_as(client, prod)

    row = _row(_pc_grid(_board(client)), oid)
    assert _BLOCKED in row and _BADGE not in row
    assert "수령 확정 기록이 없어" in row
    resp = _start(client, oid)
    assert resp.status_code == 409 and resp.get_json()["code"] == "DRAWING_STATUS"


def test_tablet_sheet_shows_badge_and_blocked_reason(client):
    oid, sales, _drafter = _walk_to_production_waiting(client, "sheet")
    _request_revision(client, oid, sales)
    prod = seed_user("pb_p_sheet", team="PRODUCTION")
    login_as(client, prod)

    html = client.get(f"/erp/production/tablet-sheet/{oid}").get_data(as_text=True)
    assert _BADGE in html and _BLOCKED in html
    assert 'data-tablet-sheet-action="production-start"' not in html

    admin = seed_user("pb_admin_sheet", role="ADMIN", team=None)
    login_as(client, admin)
    html = client.get(f"/erp/production/tablet-sheet/{oid}").get_data(as_text=True)
    assert 'data-tablet-sheet-action="production-start"' in html and "foms-prod-sheet__btn--warn" in html


# --------------------------------------------------------------------------- #
# PC 생산 보드 관리자 재시도 연결(§4.2.5 · §10-12)
# --------------------------------------------------------------------------- #
def test_wide_pc_board_carries_reason_sheet_and_override_script_once(client):
    """광폭 PC(모바일 큐·칸반 미렌더)에도 사유 시트·재시도 스크립트가 실린다 — 없으면 재시도가 무음 실패."""
    admin = seed_user("pb_admin_pc", role="ADMIN", team=None)
    login_as(client, admin)
    body = _board(client)
    assert 'aria-label="생산 모바일 작업 큐"' not in body  # v2 꺼짐 = 광폭 PC 표면만
    assert len(re.findall(r"<div class=\"foms-reason-sheet\"", body)) == 1
    assert body.count("js/foms/foms-admin-override.js") == 1
    assert "punchProductionTransition" in body and "FomsAdminOverride" in body


def test_v2_board_does_not_duplicate_reason_sheet_from_scripts(client, monkeypatch):
    prod = seed_user("pb_p_dup", team="PRODUCTION")
    _enable_v2(monkeypatch, prod.id)
    login_as(client, prod)
    body = _board(client)
    # 모바일 큐·칸반이 이미 실었다(기존 2벌) — scripts.html 이 3벌째를 더하지 않는다.
    assert len(re.findall(r"<div class=\"foms-reason-sheet\"", body)) == 2


def test_shell_does_not_hold_production_board_for_primary_ttl():
    """셸 탭 이동도 배지 신선도를 지킨다(리뷰 P2).

    서버 생산 보드는 캐시가 없지만, 셸이 조각을 primary TTL(5분) 동안 쥐고 있으면 탭 이동으로
    돌아왔을 때 수령 확정 뒤에도 배지·'도면 확정 대기'가 남는다. 생산 보드는 홈 대시보드와 같은
    fresh 경로(60초·하트비트 50초·복귀 재수혈)에 있어야 한다.
    """
    root = Path(__file__).resolve().parents[2]
    js = (root / "static/js/runtime/erp-shell.js").read_text(encoding="utf-8")
    fresh_block = js.split("var FRESH_TTL_PATHS = [", 1)[1].split("];", 1)[0]
    assert "'/erp/production/dashboard'" in fresh_block
    layout = (root / "templates/partials/shared/layout_scripts.html").read_text(encoding="utf-8")
    assert "js/runtime/erp-shell.js') }}?v=20260929i" in layout
