"""2a-2 화면 — 고객컨펌 승인 CTA 4곳·단계 강제 변경 경고(Q5)·일괄 알림이 서버와 같은 답을 낸다.

도면이 수령 확정(CONFIRMED)이 아니면 승인 라우트는 409 ``DRAWING_STATUS`` 로 막는다. 화면은 같은
판정 함수(``build_approve_cta(sd=)`` → ``confirm_exit_block``)로 그린다:

* 비관리자 — 승인·팀·재전이 버튼 대신 막힌 이유 한 줄(서버 409 문구와 같은 글자).
* 관리자 — 이유 한 줄 + 경고 모양 버튼(누르면 409 → FomsAdminOverride 사유 시트로 1회 재시도).

음성 대조군(모집단 안): 같은 화면·같은 사람·CONFIRMED 주문은 보통 버튼, 이유 줄 없음.
생산 보드 배지·[제작 시작] 막힘은 ``test_production_drawing_revision_badge.py``.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from foms.services.orders.confirm_drawing_gate import confirm_exit_block, stage_override_drawing_warning
from tests.support.confirm_seed import confirmed_drawing_sd, login_as, seed_erp_order, seed_user
from tests.support.quest_seed import confirm_quest_open

_ROOT = Path(__file__).resolve().parents[2]
_REASON_ATTR = "data-quest-approve-blocked"
_RETURNED_REASON = confirm_exit_block({"drawing_status": "RETURNED"}).reason


def _read(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


def _seed(tag: str, drawing_status: str):
    """CONFIRM 단계 + OPEN 고객 컨펌 quest(담당자 모드) + 영업 담당 지정. (id, 영업)."""
    sales = seed_user(f"scr_s_{tag}", team="SALES")
    oid = seed_erp_order("CONFIRM", sales=sales, quests=[confirm_quest_open()],
                         **confirmed_drawing_sd(drawing_status=drawing_status))
    return oid, sales


def _enable_v2(monkeypatch, *user_ids: int) -> None:
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", ",".join(str(i) for i in user_ids))


def _get(client, url: str, **kw) -> str:
    resp = client.get(url, **kw)
    assert resp.status_code == 200, url
    return resp.get_data(as_text=True)


def _grid_row_block(html: str, order_id: int) -> str:
    """PC 그리드에서 그 주문의 퀘스트 칸(스택 + 펼침 카드)."""
    start = html.index(f'data-bs-target="#quest-collapse-{order_id}"')
    start = html.rindex('<td data-col-key="quest"', 0, start)
    end = html.index(f'id="quest-approvals-{order_id}"', start)
    end = html.index("</td>", end)
    return html[start:end]


def _card(html: str, order_id: int) -> str:
    marker = f'<article class="queue-card foms-queue-card-v2" data-order-id="{order_id}"'
    start = html.index(marker)
    return html[start:html.index("</article>", start)]


# --------------------------------------------------------------------------- #
# PC 그리드(주문 대시보드)
# --------------------------------------------------------------------------- #
def test_pc_grid_non_admin_sees_reason_instead_of_approve_button(client):
    blocked, sales = _seed("pc", "RETURNED")
    ok = seed_erp_order("CONFIRM", sales=sales, quests=[confirm_quest_open()], **confirmed_drawing_sd())
    login_as(client, sales)

    html = _get(client, "/erp/dashboard", query_string={"stage": "고객컨펌"})

    cell = _grid_row_block(html, blocked)
    assert _REASON_ATTR in cell and _RETURNED_REASON in cell
    assert "erp-btn-approve-assignee" not in cell
    assert "(도면 수령 확정 전)" in cell and "(담당자만 누를 수 있어요)" not in cell
    # 대조군: 같은 사람·CONFIRMED 주문은 보통 버튼, 이유 줄 없음.
    control = _grid_row_block(html, ok)
    assert _REASON_ATTR not in control
    assert 'class="btn btn-primary fw-semibold ms-2 erp-btn-approve-assignee"' in control
    # 화면 == 서버: 막힌 주문 승인은 409 DRAWING_STATUS, 문구가 화면 이유와 같다.
    resp = client.post(f"/api/orders/{blocked}/quest/approve", json={})
    assert resp.status_code == 409 and resp.get_json()["message"] == _RETURNED_REASON


def test_pc_grid_admin_keeps_warning_button_with_reason(client):
    blocked, _sales = _seed("pca", "TRANSFERRED")
    admin = seed_user("scr_admin_pc", role="ADMIN", team=None)
    login_as(client, admin)

    cell = _grid_row_block(_get(client, "/erp/dashboard", query_string={"stage": "고객컨펌"}), blocked)

    assert _REASON_ATTR in cell
    assert 'class="btn btn-warning fw-semibold ms-2 erp-btn-approve-assignee"' in cell


# --------------------------------------------------------------------------- #
# 모바일 상세 · 모바일 큐 카드 · 태블릿 시트
# --------------------------------------------------------------------------- #
def test_mobile_detail_reason_for_staff_warning_button_for_admin(client, monkeypatch):
    blocked, sales = _seed("md", "RETURNED")
    admin = seed_user("scr_admin_md", role="ADMIN", team=None)
    _enable_v2(monkeypatch, sales.id, admin.id)

    login_as(client, sales)
    html = _get(client, f"/erp/orders/{blocked}/mobile")
    assert _REASON_ATTR in html and _RETURNED_REASON in html
    assert "erp-mobile-quest-approve-assignee" not in html
    assert "js/foms/foms-admin-override.js" in html and "data-foms-reason-sheet" in html

    login_as(client, admin)
    html = _get(client, f"/erp/orders/{blocked}/mobile")
    assert _REASON_ATTR in html
    assert "erp-mobile-quest-approve-assignee foms-btn--warning" in html


def test_mobile_queue_card_reason_and_admin_warning(client, monkeypatch):
    blocked, sales = _seed("qc", "RETURNED")
    ok = seed_erp_order("CONFIRM", sales=sales, quests=[confirm_quest_open()], **confirmed_drawing_sd())
    admin = seed_user("scr_admin_qc", role="ADMIN", team=None)
    _enable_v2(monkeypatch, sales.id, admin.id)

    login_as(client, sales)
    html = _get(client, "/erp/dashboard?view=queue")
    card = _card(html, blocked)
    assert _REASON_ATTR in card and _RETURNED_REASON in card
    assert "erp-queue-card__quest-approve" not in card
    control = _card(html, ok)
    assert _REASON_ATTR not in control and "erp-queue-card__quest-approve" in control

    login_as(client, admin)
    card = _card(_get(client, "/erp/dashboard?view=queue"), blocked)
    assert _REASON_ATTR in card
    assert "foms-btn--primary foms-btn--warning foms-btn--sm erp-queue-card__quest-approve" in card


def test_tablet_sheet_reason_and_admin_warning(client):
    blocked, sales = _seed("ts", "RETURNED")
    admin = seed_user("scr_admin_ts", role="ADMIN", team=None)

    login_as(client, sales)
    html = _get(client, f"/erp/dashboard/tablet-sheet/{blocked}")
    assert _REASON_ATTR in html and _RETURNED_REASON in html
    assert "erp-btn-approve-assignee" not in html

    login_as(client, admin)
    html = _get(client, f"/erp/dashboard/tablet-sheet/{blocked}")
    assert "erp-btn-approve-assignee foms-tsheet-foot__btn--warn" in html


# --------------------------------------------------------------------------- #
# 단계 강제 변경 경고(Q5) — 창을 여는 버튼이 판정 정본 값을 싣고, JS 문구 == 서버 문구
# --------------------------------------------------------------------------- #
def test_stage_override_opener_carries_effective_drawing_status(client):
    blocked, _sales = _seed("so", "RETURNED")
    manager = seed_user("scr_mgr_so", role="MANAGER", team="SALES")
    login_as(client, manager)

    html = _get(client, f"/edit/{blocked}")

    assert 'data-drawing-status="RETURNED"' in html
    assert 'id="erp-stage-override-drawing-warning"' in html


@pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")
@pytest.mark.parametrize(
    ("status", "to_stage"),
    [("RETURNED", "PRODUCTION"), ("TRANSFERRED", "CONSTRUCTION"), ("NONE", "PRODUCTION"),
     ("PENDING", "COMPLETED"), ("CONFIRMED", "PRODUCTION"), ("RETURNED", "CONFIRM")],
)
def test_stage_override_js_warning_matches_server_text(status, to_stage):
    """강제 변경 창 경고(erp-stage-override.js)가 서버 STAGE_OVERRIDE 판정과 같은 글자를 낸다."""
    script = (
        "global.window={};"
        "global.document={readyState:'complete',addEventListener(){},querySelectorAll(){return []},"
        "getElementById(){return null},querySelector(){return null}};"
        f"require({json.dumps(str(_ROOT / 'static/js/orders/erp-stage-override.js'))});"
        f"process.stdout.write(JSON.stringify(window.FOMS_STAGE_OVERRIDE.drawingWarningText("
        f"{json.dumps(status)},{json.dumps(to_stage)})));"
    )
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8",
                         timeout=60, check=True).stdout
    expected = stage_override_drawing_warning({"drawing_status": status}, to_stage) or ""
    assert json.loads(out) == expected


def test_stage_override_js_warns_when_status_unknown_only_toward_production():
    js = _read("static/js/orders/erp-stage-override.js")
    assert "drawingStatus: btn.getAttribute('data-drawing-status')" in js
    assert "DRAWING_UNKNOWN_WARNING" in js and "syncDrawingWarning" in js


# --------------------------------------------------------------------------- #
# 일괄 상태 바꾸기 알림(Q1) · 타임라인 라벨 · 핀
# --------------------------------------------------------------------------- #
def test_bulk_bar_alerts_command_required_ids():
    js = _read("static/js/orders/dashboard/erp-dashboard-detail-dom.js")
    assert "data.blocked_command_required && data.blocked_command_required.length" in js


def test_timeline_label_does_not_call_confirm_punch_a_drawing_punch():
    from foms.services import order_event_display

    assert "'COMMAND_REQUIRED': '전용 버튼 경로'" in _read("foms/services/order_event_display.py").replace('"', "'")
    assert order_event_display is not None


def test_asset_pins_bumped_to_20260929i():
    """CSS·JS 를 바꿨으니 부모 번들까지 핀을 올린다(SW 캐시로 옛 파일이 살지 않게)."""
    assert "erp-pro.css') }}?v=20261001d" in _read("templates/partials/shared/layout_head.html")
    assert ".foms-gate-blocked-reason" in _read("static/css/foundation/erp-pro.css")
    assert "erp-dashboard-entry.js') }}?v=20261002p" in _read("templates/partials/shared/layout_scripts.html")
    assert "erp-dashboard-detail-dom.js?v=20261001a" in _read("static/js/orders/erp-dashboard-entry.js")
    for rel in ("templates/orders/dashboard.html", "templates/channel/chat.html",
                "templates/measurement/metropolitan_dashboard.html",
                "templates/measurement/regional_dashboard.html"):
        assert "erp-stage-override.js') }}?v=20260929i" in _read(rel), rel
