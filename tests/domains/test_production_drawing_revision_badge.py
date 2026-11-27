"""2a-2 Q2 화면 — 생산 "도면 수정 중" [제작 시작] 막힘(화면 == 서버). 옛 생산 보드 화면은 2026-11-27 지워 작업 시트로 본다.

사용자 결정(2026-09-29): 생산 대기 주문에 수정요청이 오면 [제작 시작] 을 막고(관리자만 사유 적고
가능), 생산팀이 수정요청을 알 수 있게 PC 생산 보드·모바일 생산 카드에 배지를 단다. 배지는
대기·진행 중 모두, 버튼 막기는 대기만. 판정은 제작 시작 라우트와 같은 함수
(``confirm_drawing_gate``)이고, 수령 확정되면 배지가 바로 사라져야 한다.

실제 라우트 순서를 밟는다(합성 상태 주입 없음): 전달 → 수령 확정 → 고객컨펌 승인(생산 대기)
→ 수정요청(RETURNED) → 재전달. 생산 단계 재전달은 도면팀 바로 반영이라 곧바로 CONFIRMED 다
(2026-10-27 결정, docs/specs/2026-10-27-drawing-team-production-fix_SPEC.md).
"""
from __future__ import annotations

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

_BLOCKED = "data-production-start-blocked"
_OVERRIDE = {"admin_override": True, "override_reason": "현장 구두 확인 — 옛 도면 그대로 제작"}


def _sheet(client, order_id: int) -> str:
    """전체 화면 작업 시트(옛 생산 보드 PC 표 · 폰 큐 · 칸반 · 옆 시트는 2026-11-27 지움 — 막힌 이유 글은 작업 시트가 그린다)."""
    resp = client.get(f"/erp/production/sheet/{order_id}")
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


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
# 수정요청 → 재전달 → 수령 확정: 막힘이 서버 판정과 같이 켜지고 꺼진다
# --------------------------------------------------------------------------- #
def test_badge_and_start_block_follow_revision_then_vanish_on_receipt(client):
    oid, sales, drafter = _walk_to_production_waiting(client, "flow")
    prod = seed_user("pb_p_flow", team="PRODUCTION")

    # 음성 대조(모집단 안): 수령 확정된 생산 대기 주문 — 막힌 이유 없음.
    login_as(client, prod)
    assert _BLOCKED not in _sheet(client, oid)

    # 수정요청(RETURNED) — 작업 시트에 막힌 이유(영업 이름 포함).
    _request_revision(client, oid, sales)
    login_as(client, prod)
    page = _sheet(client, oid)
    assert _BLOCKED in page and sales.name in page and "도면 수정 중이라" in page
    # 화면 == 서버: 같은 사람이 눌러도 409 DRAWING_STATUS(같은 생산팀 문구).
    resp = _start(client, oid)
    assert resp.status_code == 409 and resp.get_json()["code"] == "DRAWING_STATUS"
    assert sales.name in resp.get_json()["message"]

    # 반영 체크 → 재전달(TRANSFERRED).
    req = [h for h in reload_order(oid).structured_data["drawing_transfer_history"]
           if h.get("action") == "REQUEST_REVISION"][-1]
    login_as(client, drafter)
    assert client.post(f"/api/orders/{oid}/request-revision-check",
                       json={"request_at": req["at"], "by_user_id": req["by_user_id"], "checked": True}).status_code == 200
    key = f"orders/{oid}/drawing_wizard/exports/v2.png"
    # 2026-11-25 D2: 생산 단계 수정본은 메모를 적고 직접 올린 파일은 바꿀 도면(v1)을 고른다.
    sent = client.post(f"/api/orders/{oid}/transfer-drawing",
                       json={"files": [{"key": key, "filename": "v2.png",
                                        "replace_of": f"orders/{oid}/drawing_wizard/exports/v1.png"}],
                             "mode": "APPEND", "is_retransfer": True, "note": "손잡이 색 변경"})
    assert sent.status_code == 200, sent.get_json()
    # 생산 단계 재전달 = 도면팀 바로 반영(2026-10-27 결정) — 영업 수령 확정 없이 곧바로 확정이라
    # "확정 대기" 중간 상태가 없다. 새로고침 즉시 막힘이 사라진다(캐시 무효화 포함).
    assert sent.get_json().get("hotfix") is True
    assert reload_order(oid).structured_data["drawing_status"] == "CONFIRMED"
    assert reload_order(oid).erp_stage_code == "PRODUCTION"
    login_as(client, prod)
    assert _BLOCKED not in _sheet(client, oid)
    assert _start(client, oid).status_code == 200


def test_admin_sees_warning_start_button_and_reason_then_punches(client):
    """관리자: 보통 요청은 409, 사유를 실은 재시도(FomsAdminOverride)는 통과(화면 단추 꼴은 작업 시트 시험 몫)."""
    oid, sales, _drafter = _walk_to_production_waiting(client, "adm")
    _request_revision(client, oid, sales)
    admin = seed_user("pb_admin", role="ADMIN", team=None)
    login_as(client, admin)
    assert _start(client, oid).status_code == 409
    assert _start(client, oid, _OVERRIDE).status_code == 200


def test_badge_shows_while_in_progress_but_does_not_block(client):
    """이미 만드는 중(run 있음)이면 막지 않는다."""
    prod = seed_user("pb_p_run", team="PRODUCTION")
    running = seed_erp_order("PRODUCTION", **confirmed_drawing_sd(drawing_status="RETURNED"))
    db_session.add(ProductionRun(order_id=running, status="IN_PROGRESS", steps=[], defects=[], is_current=True))
    db_session.commit()
    login_as(client, prod)
    assert _BLOCKED not in _sheet(client, running)


def test_confirm_compat_waiting_row_blocks_on_allowlist_like_server(client):
    """CONFIRM 호환 제작 대기(퀘스트 완료)는 허용 목록 — 기록 없음(NONE)도 막힌다."""
    from tests.support.quest_seed import confirm_quest_completed

    prod = seed_user("pb_p_cc", team="PRODUCTION")
    sales = seed_user("pb_s_cc", team="SALES")
    oid = seed_erp_order("CONFIRM", sales=sales, quests=[confirm_quest_completed()])
    login_as(client, prod)

    page = _sheet(client, oid)
    assert _BLOCKED in page and "수령 확정 기록이 없어" in page
    resp = _start(client, oid)
    assert resp.status_code == 409 and resp.get_json()["code"] == "DRAWING_STATUS"


def test_shell_does_not_hold_production_board_for_primary_ttl():
    """셸 탭 이동도 배지 신선도를 지킨다(리뷰 P2).

    서버 생산 보드는 캐시가 없지만, 셸이 조각을 primary TTL(5분) 동안 쥐고 있으면 탭 이동으로
    돌아왔을 때 수령 확정 뒤에도 배지·'도면 확정 대기'가 남는다. 9탭의 생산 칸은 홈 대시보드와 같은
    fresh 경로(60초·하트비트 50초·복귀 재수혈)에 있어야 한다 — 2026-11-21 부터 그 칸은 생산 첫 화면이다
    (설계서 production-pc-viewer §9-5). 옛 보드(하위 조각 LEGACY_SWAP)는 2026-11-27 없앴다.
    """
    root = Path(__file__).resolve().parents[2]
    js = (root / "static/js/runtime/erp-shell.js").read_text(encoding="utf-8")
    fresh_block = js.split("var FRESH_TTL_PATHS = [", 1)[1].split("];", 1)[0]
    assert "'/erp/production/home'" in fresh_block
    ttl = js[js.index("function cacheTtlForKey(key)"):].split("function ", 2)[1]
    assert "FRESH_TTL_PATHS.indexOf(path) >= 0" in ttl and "FRESH_TTL_MS : CACHE_TTL_MS" in ttl
    assert "LEGACY_SWAP_PATHS" not in js
    layout = (root / "templates/partials/shared/layout_scripts.html").read_text(encoding="utf-8")
    assert "js/runtime/erp-shell.js') }}?v=20261127h" in layout
