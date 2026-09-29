"""도면 결함 2차 묶음 2d — 화면·서버 불일치(M14 b~e) · v2 도면방 보내기(M13) · 반영 체크 접근성(R12).

설계서 `docs/specs/2026-09-29-drawing-defects-batch2_SPEC.md` §4.10(b~e) · §4.11 · §4.12.

- M14-b 반영 체크로 막힌 RETURNED 주문인데 차례 리본이 '내 차례'(mine) 색이었다.
- M14-c 알림 착지(`?tab=requests`)가 도면 여러 장 주문에서 목록 화면에 떨어져 대화 스레드가 안 보였다.
- M14-d 태블릿 관리 시트의 '시트 전달' 이 서버가 400 으로 거절할 상태(반영 체크 남음 · RETURNED 이고
  현재본 2장 이상)에서도 켜져 있었다.
- M14-e ERP 대시보드 상세 DOM 의 `requestTabHtml` 은 만들고 쓰지 않는 코드였다.
- M13 v2 모바일에는 도면방 PUSH 가 없었다(옛 모바일 바에만 있었고 v2 는 그 바를 숨긴다).
- R12 반영 체크 토글에 상태·대상 이름이 없고, 막힌 이유가 disabled 버튼 안에 있어 탭 이동으로 못 닿았다.
  관리자 하단 바(이유 줄 포함)가 본문 아래 여백보다 커서 마지막 줄을 가렸다.

같은 응답에 숨은 PC 마크업이 함께 오므로 문자열 검색 대신 모바일 표면(`.foms-drawing-handoff`)을 파서로 잘라 본다.
"""

from __future__ import annotations

import re
from pathlib import Path

from bs4 import BeautifulSoup
from werkzeug.security import generate_password_hash

from db import db_session
from foms.api.notifications import _resolve_notification_deep_link
from foms.services.datetime_kst import get_today_kst
from foms.services.notifications.push_sender import _deep_link as push_deep_link
from foms.web.drawing.workbench import _build_drawing_turn
from models import Notification, Order, User

ROOT = Path(__file__).resolve().parents[2]
HANDOFF_JS = ROOT / "static/js/foms/drawing-handoff.js"
DETAIL_DOM_JS = ROOT / "static/js/orders/dashboard/erp-dashboard-detail-dom.js"
MOBILE_CSS = ROOT / "static/css/components/foms-drawing-mobile.css"


def _user(username: str, *, role: str, team: str) -> dict:
    user = User(username=username, password=generate_password_hash("pw"), role=role,
                team=team, name=username, is_active=True)
    db_session.add(user)
    db_session.commit()
    return {"id": user.id, "username": user.username, "role": user.role}


def _login(client, who: dict) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = who["id"]
        sess["username"] = who["username"]
        sess["role"] = who["role"]


def _order(drafter_id: int, *, status: str = "RETURNED", files: int = 2, checked: bool = False,
           pending: bool = False) -> int:
    """1차 전달 뒤 수정요청 1건이 들어온 주문(기본: RETURNED · 도면 2장 · 반영 체크 안 함).

    key 는 전달 조립(`materialize_transfer_attachments`)이 이 주문 경로만 받으므로 주문 id 로 만든다.
    """
    order = Order(received_date=get_today_kst().strftime("%Y-%m-%d"), customer_name="2d 고객",
                  phone="010-0000-0024", address="서울", product="붙박이장", status="DRAWING",
                  manager_name="영업담당", is_erp_order=True, structured_data={})
    db_session.add(order)
    db_session.flush()
    keys = [f"orders/{order.id}/drawing/plan-{i}.png" for i in range(1, files + 1)]
    history = [
        {"action": "TRANSFER", "by_user_id": drafter_id, "by_user_name": "도면담당", "at": "2026-09-20 01:00:00",
         "note": "1차 전달", "files": [{"key": k, "filename": k.rsplit("/", 1)[-1]} for k in keys]},
    ]
    if status == "RETURNED":
        history.append({
            "action": "REQUEST_REVISION", "by_user_id": 1, "by_user_name": "영업담당", "at": "2026-09-21 01:00:00",
            "note": "2번 도면 높이 수정", "target_drawing_number": files, "files": [],
            **({"review_check": {"checked": True, "checked_by_name": "도면담당"}} if checked else {}),
        })
    sd = {
        "parties": {"customer": {"name": "2d 고객"}, "manager": {"name": "영업담당"}},
        "workflow": {"stage": "DRAWING"},
        "drawing_status": status,
        "assignments": {"drawing_assignee_user_ids": [drafter_id]},
        "drawing_current_files": [
            {"key": k, "filename": k.rsplit("/", 1)[-1], "view_url": f"/api/files/view/{k}"} for k in keys
        ],
        "drawing_transfer_history": history,
    }
    if pending:
        wiz_key = f"orders/{order.id}/drawing_wizard/exports/s1.png"
        sd["drawing_wizard"] = {"pending": {"s1": {"key": wiz_key, "filename": "s1.png", "sheet_name": "거실"}}}
    order.structured_data = sd
    db_session.commit()
    return order.id


def _phone(client, monkeypatch, who: dict, url: str):
    _login(client, who)
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(who["id"]))
    res = client.get(url)
    assert res.status_code == 200
    handoff = BeautifulSoup(res.get_data(as_text=True), "html.parser").select_one(
        ".erp-mobile-shell.foms-drawing-handoff"
    )
    assert handoff is not None, "v2 모바일 표면이 렌더되지 않았다"
    return handoff


# ── M14-b 차례 리본 ────────────────────────────────────────────────────────────


def test_turn_ribbon_is_not_mine_when_gated_by_revision_checklist():
    """막힘을 아는 리본: 전달 권한이 있어도 반영 체크가 남으면 'other' 색 + 이유 라벨."""
    gated = _build_drawing_turn("RETURNED", True, True, False, 2, 1, gated=True)
    assert gated["tone"] == "other"
    assert gated["label"] == "수정요청 반영 체크 필요"
    # 대조: 같은 값에서 막힘이 없으면 여전히 내 차례다(판정이 통째로 꺼진 것이 아님).
    open_turn = _build_drawing_turn("RETURNED", True, True, False, 2, 1, gated=False)
    assert open_turn["tone"] == "mine" and open_turn["label"] == "도면팀 수정 차례"


def test_turn_ribbon_renders_gated_tone_on_phone(client, monkeypatch):
    drafter = _user("b2d_turn_drafter", role="STAFF", team="DRAWING")
    oid = _order(drafter["id"], files=1)
    handoff = _phone(client, monkeypatch, drafter, f"/erp/drawing-workbench/{oid}")
    turn = handoff.select_one("section.foms-drawing-turn")
    assert "foms-drawing-turn--other" in turn["class"], turn["class"]
    assert "수정요청 반영 체크 필요" in turn.get_text(" ", strip=True)


# ── M14-c 딥링크 tab=requests ─────────────────────────────────────────────────


def _notification(order_id: int) -> Notification:
    notif = Notification(order_id=order_id, notification_type="DRAWING_REVISION", title="수정요청",
                         message="수정요청", target_team="DRAWING")
    db_session.add(notif)
    db_session.commit()
    return notif


def test_requests_tab_deeplink_lands_on_detail_with_highlighted_request(client, monkeypatch):
    """도면 2장 주문 + 알림 착지 `?tab=requests` → 상세 보기 · 스레드 · 미체크 수정요청 말풍선 강조."""
    drafter = _user("b2d_tab_drafter", role="STAFF", team="DRAWING")
    oid = _order(drafter["id"], files=2)
    notif = _notification(oid)
    sd = db_session.get(Order, oid).structured_data
    urls = {
        "push": push_deep_link(notif),
        "bell": _resolve_notification_deep_link(notif, sd)["deep_link_url"],
        "js": f"/erp/drawing-workbench/{oid}?tab=requests",  # foms-drawing-alert.js deepLink
    }
    for landing, url in urls.items():
        assert "tab=requests" in url, (landing, url)
        handoff = _phone(client, monkeypatch, drafter, url)
        assert handoff["data-handoff-mode"] == "detail", landing
        highlighted = handoff.select(".foms-drawing-thread__msg.is-highlight")
        assert len(highlighted) == 1, (landing, [str(h)[:120] for h in highlighted])
        assert "2번 도면 높이 수정" in highlighted[0].get_text(" ", strip=True)

    # 대조: 탭 없이 들어오면 지금처럼 도면 목록이다(여러 장 주문의 기본 착지).
    plain = _phone(client, monkeypatch, drafter, f"/erp/drawing-workbench/{oid}")
    assert plain["data-handoff-mode"] == "list"
    assert plain.select(".foms-drawing-thread__msg") == []


def test_requests_tab_highlights_nothing_when_all_checked(client, monkeypatch):
    drafter = _user("b2d_tab_checked", role="STAFF", team="DRAWING")
    oid = _order(drafter["id"], files=2, checked=True)
    handoff = _phone(client, monkeypatch, drafter, f"/erp/drawing-workbench/{oid}?tab=requests")
    assert handoff["data-handoff-mode"] == "detail"
    assert handoff.select(".foms-drawing-thread__msg.is-highlight") == []


# ── M14-d 태블릿 관리 시트 '시트 전달' ────────────────────────────────────────


def _sheet(client, who: dict, oid: int):
    _login(client, who)
    res = client.get(f"/erp/drawing-workbench/tablet-sheet/{oid}")
    assert res.status_code == 200
    soup = BeautifulSoup(res.get_data(as_text=True), "html.parser")
    return soup.select_one("[data-foms-drawing-transfer]"), soup


def test_tablet_sheet_transfer_disabled_when_revision_check_pending(client):
    admin = _user("b2d_sheet_admin1", role="ADMIN", team="DRAWING")
    oid = _order(admin["id"], files=1, pending=True)
    btn, soup = _sheet(client, admin, oid)
    assert btn is not None and btn.has_attr("disabled")
    reason = soup.select_one("#dw-sheet-transfer-reason")
    assert reason is not None and "작업실에서" in reason.get_text()
    assert btn.get("aria-describedby") == "dw-sheet-transfer-reason"


def test_tablet_sheet_transfer_disabled_when_returned_with_two_current_drawings(client):
    """반영 체크는 끝났어도 RETURNED + 현재본 2장이면 교체 대상이 필요하다(서버 400) — 켜지 않는다."""
    admin = _user("b2d_sheet_admin2", role="ADMIN", team="DRAWING")
    oid = _order(admin["id"], files=2, checked=True, pending=True)
    btn, soup = _sheet(client, admin, oid)
    assert btn is not None and btn.has_attr("disabled")
    assert soup.select_one("#dw-sheet-transfer-reason") is not None

    # 서버도 같은 이유로 거절한다(화면 == 서버).
    res = client.post(f"/api/orders/{oid}/drawing-wizard/transfer-pending", json={"mode": "APPEND"})
    assert res.status_code == 400, res.get_data(as_text=True)
    assert "교체할 도면" in (res.get_json() or {}).get("message", "")


def test_tablet_sheet_transfer_enabled_when_not_blocked(client):
    """대조: 첫 전달(IN_PROGRESS) + 대기 시트가 있으면 버튼은 켜지고 이유 줄은 없다."""
    admin = _user("b2d_sheet_admin3", role="ADMIN", team="DRAWING")
    oid = _order(admin["id"], status="IN_PROGRESS", files=2, pending=True)
    btn, soup = _sheet(client, admin, oid)
    assert btn is not None and not btn.has_attr("disabled")
    assert soup.select_one("#dw-sheet-transfer-reason") is None


# ── M14-e 죽은 코드 ───────────────────────────────────────────────────────────


def test_dashboard_detail_dom_has_no_dead_request_tab_markup():
    source = DETAIL_DOM_JS.read_text(encoding="utf-8")
    assert "requestTabHtml" not in source
    assert "canToggleRevisionCheck" not in source  # requestTabHtml 에서만 쓰던 값


# ── M13 v2 도면방 보내기 ──────────────────────────────────────────────────────


def test_v2_phone_has_one_drawing_room_push_button_in_current_drawing_block(client, monkeypatch):
    drafter = _user("b2d_push_drafter", role="STAFF", team="DRAWING")
    oid = _order(drafter["id"], status="TRANSFERRED", files=1)
    handoff = _phone(client, monkeypatch, drafter, f"/erp/drawing-workbench/{oid}")
    buttons = handoff.select('[data-drawing-handoff-action="drawing-room-push"]')
    assert len(buttons) == 1
    assert buttons[0].find_parent(class_="foms-drawing-handoff-detail") is not None
    assert not buttons[0].has_attr("disabled")
    # 하단 바에는 더하지 않는다(바 높이를 키우지 않기).
    assert buttons[0].find_parent(class_="foms-drawing-action-bar") is None


def test_v2_phone_push_button_disabled_without_transferred_drawing(client, monkeypatch):
    drafter = _user("b2d_push_empty", role="STAFF", team="DRAWING")
    oid = _order(drafter["id"], status="IN_PROGRESS", files=0)
    handoff = _phone(client, monkeypatch, drafter, f"/erp/drawing-workbench/{oid}")
    button = handoff.select_one('[data-drawing-handoff-action="drawing-room-push"]')
    assert button is not None and button.has_attr("disabled")
    assert "전달된 도면이 없습니다" in (button.get("title") or "")


def test_v2_phone_push_button_hidden_for_non_participant_sales(client, monkeypatch):
    drafter = _user("b2d_push_owner", role="STAFF", team="DRAWING")
    sales = _user("b2d_push_sales", role="MANAGER", team="SALES")
    oid = _order(drafter["id"], status="TRANSFERRED", files=1)
    handoff = _phone(client, monkeypatch, sales, f"/erp/drawing-workbench/{oid}")
    assert handoff.select('[data-drawing-handoff-action="drawing-room-push"]') == []


def test_handoff_js_proxies_drawing_room_push_to_pc_button():
    source = HANDOFF_JS.read_text(encoding="utf-8")
    assert "'drawing-room-push': 'dw-btn-drawing-room-push'" in source


# ── R12 반영 체크 접근성 + 하단 바 가림 ────────────────────────────────────────


def test_revision_toggle_names_its_state(client, monkeypatch):
    drafter = _user("b2d_a11y_drafter", role="STAFF", team="DRAWING")
    oid = _order(drafter["id"], files=1)
    handoff = _phone(client, monkeypatch, drafter, f"/erp/drawing-workbench/{oid}")
    toggle = handoff.select_one('[data-drawing-handoff-action="revision-check"]')
    assert toggle["aria-pressed"] == "false"
    assert toggle["aria-label"].endswith("수정요청 반영 완료 표시"), toggle["aria-label"]

    checked_oid = _order(drafter["id"], files=1, checked=True)
    handoff = _phone(client, monkeypatch, drafter, f"/erp/drawing-workbench/{checked_oid}")
    toggle = handoff.select_one('[data-drawing-handoff-action="revision-check"]')
    assert toggle["aria-pressed"] == "true"
    assert toggle["aria-label"].endswith("수정요청 반영 완료 해제"), toggle["aria-label"]


def test_gate_reason_is_outside_disabled_button_and_described(client, monkeypatch):
    drafter = _user("b2d_reason_drafter", role="STAFF", team="DRAWING")
    oid = _order(drafter["id"], files=1)
    handoff = _phone(client, monkeypatch, drafter, f"/erp/drawing-workbench/{oid}")
    reason = handoff.select_one("#dw-transfer-gate-reason")
    assert reason is not None and reason.name == "p"
    assert "foms-drawing-action-bar__reason" in reason["class"]
    assert reason.find_parent("button") is None
    assert reason.find_parent(class_="foms-drawing-action-bar") is not None
    gated = handoff.select_one(".foms-drawing-action-bar__btn--gated")
    assert gated.has_attr("disabled") and gated["aria-describedby"] == "dw-transfer-gate-reason"
    # 이유 줄이 있는 바는 더 높다 — 본문 여백 규칙이 그 표시를 본다.
    assert "foms-drawing-handoff--bar-reason" in handoff["class"]


def test_bar_without_reason_keeps_default_padding_class(client, monkeypatch):
    drafter = _user("b2d_reason_none", role="STAFF", team="DRAWING")
    oid = _order(drafter["id"], files=1, checked=True)
    handoff = _phone(client, monkeypatch, drafter, f"/erp/drawing-workbench/{oid}")
    assert handoff.select_one("#dw-transfer-gate-reason") is None
    assert "foms-drawing-handoff--bar-reason" not in handoff["class"]


def _rule(css: str, selector: str) -> str:
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert match, selector
    return match.group(1)


def test_css_reason_font_and_body_padding_follow_bar_height():
    css = MOBILE_CSS.read_text(encoding="utf-8")
    reason = _rule(css, "body.erp-mobile-v2-layout .foms-drawing-action-bar__reason")
    assert "font-size: 0.72rem" in reason and "0.62rem" not in reason
    body = _rule(css, "body.erp-mobile-v2-layout .foms-drawing-handoff__body")
    assert "var(--foms-drawing-action-bar-h" in body
    tall = _rule(css, "body.erp-mobile-v2-layout .foms-drawing-handoff--bar-reason")
    assert "--foms-drawing-action-bar-h" in tall
