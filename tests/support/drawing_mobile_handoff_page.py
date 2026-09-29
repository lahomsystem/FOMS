"""도면 방(모바일) 렌더 테스트 조각 — S3 테스트와 합친 뒤 테스트(실제 S1 빌더 출력)가 같이 쓴다.

상세 라우트를 실제로 타고(v2 모바일 표면 켬), 필요하면 render_template 을 감싸 ctx 의
``customer_send`` 를 덮는다. 같은 응답에 숨은 PC 마크업이 함께 오므로 모바일 표면은 파서로 잘라 본다.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup
from werkzeug.security import generate_password_hash

import foms.web.drawing.workbench as workbench_mod
from db import db_session
from foms.services.datetime_kst import get_today_kst
from models import Order, User


def bar_items(items, slots=None):
    slots = slots or {}
    return [{"key": k, "label": label, "tone": tone, "slot": slots.get(k, "main")} for k, label, tone in items]


# ── 픽스처 조각 ────────────────────────────────────────────────────────────────


def make_user(username: str, *, role: str, team: str) -> dict:
    # 영업 쪽 판정(_can_modify_sales_domain)은 주문 담당 이름으로 맞춘다 — SALES 팀은 주문 담당 "영업담당".
    name = "영업담당" if team == "SALES" else username
    user = User(username=username, password=generate_password_hash("pw"), role=role,
                team=team, name=name, is_active=True)
    db_session.add(user)
    db_session.commit()
    return {"id": user.id, "username": user.username, "role": user.role}


def login(client, who: dict) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = who["id"]
        sess["username"] = who["username"]
        sess["role"] = who["role"]


def make_order(drafter_id: int, *, status: str = "TRANSFERRED", files: int = 2, revision: bool = False) -> int:
    order = Order(received_date=get_today_kst().strftime("%Y-%m-%d"), customer_name="S3 고객",
                  phone="010-0000-0033", address="서울", product="붙박이장", status="DRAWING",
                  manager_name="영업담당", is_erp_order=True, structured_data={})
    db_session.add(order)
    db_session.flush()
    keys = [f"orders/{order.id}/drawing/plan-{i}.png" for i in range(1, files + 1)]
    history = [
        {"action": "TRANSFER", "by_user_id": drafter_id, "by_user_name": "도면담당", "at": "2026-09-20 01:00:00",
         "note": "1차 전달", "files": [{"key": k, "filename": k.rsplit("/", 1)[-1]} for k in keys]},
    ]
    if revision:
        history.append({
            "action": "REQUEST_REVISION", "by_user_id": 1, "by_user_name": "영업담당", "at": "2026-09-21 01:00:00",
            "note": "오른쪽 문짝 폭 줄여 주세요", "target_drawing_number": files, "files": [],
        })
    order.structured_data = {
        "parties": {"customer": {"name": "S3 고객"}, "manager": {"name": "영업담당"}},
        "workflow": {"stage": "DRAWING"},
        "drawing_status": status,
        "assignments": {"drawing_assignee_user_ids": [drafter_id]},
        "drawing_current_files": [
            {"key": k, "filename": k.rsplit("/", 1)[-1], "view_url": f"/api/files/view/{k}"} for k in keys
        ],
        "drawing_transfer_history": history,
    }
    db_session.commit()
    return order.id


def inject(monkeypatch, *, cs: dict | None = None, thread=None) -> None:
    """상세 ctx 를 직접 채운다 — customer_send 를 덮고, 필요하면 스레드 항목을 고친다."""
    # 한 테스트에서 여러 번 불러도 겹겹이 감싸지 않는다 — 늘 원래 함수를 부른다.
    real = getattr(workbench_mod.render_template, "_s3_real", workbench_mod.render_template)

    def fake(template_name, **ctx):
        if cs is not None and "customer_send" in ctx:
            view = dict(ctx["customer_send"])
            view.update(cs)
            ctx["customer_send"] = view
        if thread is not None and "mobile_handoff_thread" in ctx:
            thread(ctx["mobile_handoff_thread"])
        return real(template_name, **ctx)

    fake._s3_real = real
    monkeypatch.setattr(workbench_mod, "render_template", fake)


def fetch_page(client, monkeypatch, who: dict, oid: int, query: str = "") -> BeautifulSoup:
    login(client, who)
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(who["id"]))
    res = client.get(f"/erp/drawing-workbench/{oid}{query}")
    assert res.status_code == 200, res.status_code
    return BeautifulSoup(res.get_data(as_text=True), "html.parser")


def mobile_surface(soup: BeautifulSoup):
    handoff = soup.select_one(".erp-mobile-shell.foms-drawing-handoff")
    assert handoff is not None, "v2 모바일 표면이 렌더되지 않았다"
    return handoff


def mobile_bar_keys(handoff) -> list[str]:
    return [el["data-bar-key"] for el in handoff.select(".foms-drawing-action-bar [data-bar-key]")]


def direct_bar_buttons(handoff) -> list:
    bar = handoff.select_one(".foms-drawing-action-bar")
    return [el for el in bar.find_all(recursive=False) if el.name in ("button", "a")]


def urgent_buttons(handoff) -> list:
    return handoff.select(".foms-drawing-action-bar [data-foms-urgent-call]")


_BRACKET = re.compile(r"\[([^\]]+)\]")


def assert_sheet_names_only_its_own_buttons(sheet) -> None:
    """시트 안내가 [버튼]을 부르면 그 이름의 버튼이 시트에 있어야 한다 — 확인창용 '[취소]를 누르세요'가
    [그래도 취소] 옆에 오면 영업에게 알리는 대신 도면을 거두게 된다(S3 리뷰 P2). 합친 뒤 테스트도 쓴다."""
    body = sheet.select_one(".modal-body").get_text(" ", strip=True)
    labels = [b.get_text(" ", strip=True) for b in sheet.select(".modal-footer button")]
    named = _BRACKET.findall(body)
    assert named, body
    for name in named:
        assert any(label.startswith(name) for label in labels), (name, labels, body)
    assert "[취소]" not in body
