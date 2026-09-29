"""M14-a — 전달 버튼은 서버가 받아 주는 사람에게만 켜진다(화면 == 서버, 설계서 §4.10 a).

배경:
    화면(workbench.py · tablet_sheet.py)은 ``has_assignee and is_drawing_participant and
    (ADMIN or 도면팀)`` 이면 전달 버튼을 켰다 — 담당이 아닌 도면팀도 참. 서버
    (``perform_drawing_transfer``)는 ADMIN · 지정 도면 담당 · 사유 있는 MANAGER 만 받아
    나머지는 403 이었다. 담당 아닌 도면팀은 파일을 올린 뒤 403 을 받아 고아 업로드가 생겼다.

고친 방식:
    술어 하나 ``can_transfer_drawing(user, order)``(ADMIN 또는 지정 도면 담당, 담당이 한 명도
    없으면 거짓)를 서버·작업실(PC·모바일)·태블릿 시트가 함께 쓴다. MANAGER 사유 분기는
    서버에만 둔다. 담당 아닌 도면팀에게는 버튼 대신 "담당자만 전달할 수 있어요".

음성 대조:
    수정 전 코드에서 "담당 아닌 도면팀" 화면 단언이 빨간 것을 확인했다(보고서 negative_control).
    지정 담당은 버튼 + 200 인 것이 대조군이다.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from bs4 import BeautifulSoup
from werkzeug.security import generate_password_hash

import foms.api.drawing.erp_orders_drawing as drawing_routes
from db import db_session
from foms.services.erp_policy import can_transfer_drawing
from models import Order, User

HINT = "담당자만 전달할 수 있어요"


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    monkeypatch.setattr(drawing_routes, "emit_erp_notification_to_users", lambda *a, **k: None)


def _user(name: str, *, role: str = "STAFF", team: str | None = "DRAWING") -> SimpleNamespace:
    u = User(username=name, password=generate_password_hash("pw"), role=role, team=team, name=name, is_active=True)
    db_session.add(u)
    db_session.commit()
    return SimpleNamespace(id=u.id, username=u.username, role=u.role, name=u.name, team=team)


def _as(client, u: SimpleNamespace) -> None:
    with client.session_transaction() as s:
        s["user_id"], s["username"], s["role"] = u.id, u.username, u.role


def _order(assignee_ids: list[int]) -> int:
    oid_hint = len(assignee_ids)
    o = Order(
        received_date=date.today().strftime("%Y-%m-%d"), customer_name="M14고객", phone="010-1414-1414",
        address="Seoul", product="붙박이장", status="DRAWING", manager_name="영업M14", is_erp_order=True,
        erp_stage_code="DRAWING",
        structured_data={
            "parties": {"customer": {"name": "M14고객"}, "manager": {"name": "영업M14"}},
            "workflow": {"stage": "DRAWING"}, "drawing_status": "PENDING",
            "assignments": {"drawing_assignee_user_ids": list(assignee_ids)},
            "drawing_wizard": {"pending": {"s1": {"key": f"orders/0/drawing_wizard/exports/p{oid_hint}.png",
                                                  "filename": "s1.png", "sheet_name": "시트1"}}},
        },
    )
    db_session.add(o)
    db_session.commit()
    # pending key 는 주문 id 가 있어야 전달 필터를 통과한다 — 생성 뒤 채운다.
    sd = dict(o.structured_data)
    sd["drawing_wizard"] = {"pending": {"s1": {"key": f"orders/{o.id}/drawing_wizard/exports/s1.png",
                                               "filename": "s1.png", "sheet_name": "시트1"}}}
    o.structured_data = sd
    db_session.commit()
    return o.id


def _transfer_payload(oid: int) -> dict:
    return {"files": [{"key": f"orders/{oid}/drawing_wizard/exports/s1.png", "filename": "s1.png"}]}


def _pc_soup(client, oid: int) -> BeautifulSoup:
    res = client.get(f"/erp/drawing-workbench/{oid}")
    assert res.status_code == 200
    return BeautifulSoup(res.get_data(as_text=True), "html.parser")


def _mobile_bar(client, monkeypatch, who: SimpleNamespace, oid: int):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(who.id))
    res = client.get(f"/erp/drawing-workbench/{oid}")
    assert res.status_code == 200
    soup = BeautifulSoup(res.get_data(as_text=True), "html.parser")
    bar = soup.select_one(".erp-mobile-shell.foms-drawing-handoff .foms-drawing-action-bar")
    assert bar is not None, "v2 모바일 하단 바가 렌더되지 않았다"
    return bar


def _sheet_soup(client, oid: int) -> BeautifulSoup:
    res = client.get(f"/erp/drawing-workbench/tablet-sheet/{oid}")
    assert res.status_code == 200
    return BeautifulSoup(res.get_data(as_text=True), "html.parser")


def _opens_transfer_modal(soup) -> bool:
    return any(not b.has_attr("disabled") for b in soup.select('[data-bs-target="#dwTransferModal"]'))


# ── 술어 ─────────────────────────────────────────────────────────────────────
def test_predicate_admin_or_assignee_only():
    assigned = SimpleNamespace(id=11, role="STAFF", team="DRAWING")
    other_drawing = SimpleNamespace(id=12, role="STAFF", team="DRAWING")
    manager = SimpleNamespace(id=13, role="MANAGER", team="DRAWING")
    admin = SimpleNamespace(id=14, role="ADMIN", team=None)
    order = SimpleNamespace(structured_data={"assignments": {"drawing_assignee_user_ids": [11]}})
    no_assignee = SimpleNamespace(structured_data={"assignments": {}})
    assert can_transfer_drawing(assigned, order) is True
    assert can_transfer_drawing(other_drawing, order) is False
    assert can_transfer_drawing(manager, order) is False  # 사유 분기는 서버에만
    assert can_transfer_drawing(admin, order) is True
    assert can_transfer_drawing(None, order) is False
    # 담당이 아무도 없으면 서버가 400 으로 막는다 — 화면도 켜지 않는다(관리자 포함).
    assert can_transfer_drawing(admin, no_assignee) is False
    legacy = SimpleNamespace(structured_data={"drawing_assignees": [{"user_id": 11}]})
    assert can_transfer_drawing(assigned, legacy) is True


# ── 담당 아닌 도면팀: 버튼 없음 + 서버 403 ──────────────────────────────────
def test_non_assignee_drawing_team_sees_no_transfer_and_server_403(client, monkeypatch):
    d1 = _user("m14_d1")
    d2 = _user("m14_d2")
    oid = _order([d1.id])
    _as(client, d2)

    pc = _pc_soup(client, oid)
    assert not _opens_transfer_modal(pc), "담당 아닌 도면팀에게 PC 전달 버튼이 켜졌다"
    assert HINT in pc.get_text(" ", strip=True)

    bar = _mobile_bar(client, monkeypatch, d2, oid)
    assert not _opens_transfer_modal(bar), "담당 아닌 도면팀에게 모바일 전달 버튼이 켜졌다"
    assert HINT in bar.get_text(" ", strip=True)

    sheet = _sheet_soup(client, oid)
    assert sheet.select_one("[data-foms-drawing-transfer]") is None, "태블릿 시트 '시트 전달'이 켜졌다"
    assert HINT in sheet.get_text(" ", strip=True)

    # 서버: 전달 창 경로 · 태블릿 시트(마법사 전달 대기) 경로 모두 403.
    assert client.post(f"/api/orders/{oid}/transfer-drawing", json=_transfer_payload(oid)).status_code == 403
    assert client.post(f"/api/orders/{oid}/drawing-wizard/transfer-pending", json={}).status_code == 403


# ── 지정 담당: 버튼 + 서버 200 (대조군) ─────────────────────────────────────
def test_assignee_sees_transfer_and_server_200(client, monkeypatch):
    d1 = _user("m14_a1")
    oid = _order([d1.id])
    _as(client, d1)

    pc = _pc_soup(client, oid)
    assert _opens_transfer_modal(pc)
    assert HINT not in pc.get_text(" ", strip=True)
    sheet = _sheet_soup(client, oid)
    assert sheet.select_one("[data-foms-drawing-transfer]") is not None
    bar = _mobile_bar(client, monkeypatch, d1, oid)
    assert _opens_transfer_modal(bar)

    assert client.post(f"/api/orders/{oid}/transfer-drawing", json=_transfer_payload(oid)).status_code == 200


def test_admin_sees_transfer_and_server_200(client):
    d1 = _user("m14_adm_d")
    admin = _user("m14_adm", role="ADMIN", team=None)
    oid = _order([d1.id])
    _as(client, admin)
    assert _opens_transfer_modal(_pc_soup(client, oid))
    assert HINT not in _pc_soup(client, oid).get_text(" ", strip=True)
    assert client.post(f"/api/orders/{oid}/transfer-drawing", json=_transfer_payload(oid)).status_code == 200


def test_no_assignee_nobody_sees_transfer_and_server_400(client):
    admin = _user("m14_na_adm", role="ADMIN", team=None)
    oid = _order([])
    _as(client, admin)
    assert not _opens_transfer_modal(_pc_soup(client, oid))
    assert client.post(f"/api/orders/{oid}/transfer-drawing", json=_transfer_payload(oid)).status_code == 400


def test_non_assignee_drawing_team_does_not_see_cancel_transfer(client):
    """전달 취소도 서버(ADMIN · 담당 · 마지막 전달자)와 같다 — 담당 아닌 도면팀에 안 켜진다."""
    d1 = _user("m14_ct_d1")
    d2 = _user("m14_ct_d2")
    oid = _order([d1.id])
    _as(client, d1)
    assert client.post(f"/api/orders/{oid}/transfer-drawing", json=_transfer_payload(oid)).status_code == 200
    _as(client, d2)
    pc = _pc_soup(client, oid)
    assert pc.select_one("#btn-cancel-transfer") is None
    assert client.post(f"/api/orders/{oid}/cancel-transfer", json={}).status_code == 403
