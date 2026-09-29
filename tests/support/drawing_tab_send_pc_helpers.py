"""도면 작업실 PC 결정 바 렌더 테스트(S2) 공용 도우미 — 사용자·주문 만들기, 상세 렌더, ``customer_send`` 주입.

``_inject`` 는 상세 라우트가 렌더 직전에 만든 ctx 의 ``customer_send`` 를 **빈 값에서 시작해** 주어진
값만 채운다(S1 실제 값이 모양 테스트에 새지 않게). 테스트 파일 둘(test_drawing_tab_send_pc·_s1_link)이 같이 쓴다.
"""

from __future__ import annotations

from bs4 import BeautifulSoup
from werkzeug.security import generate_password_hash

import foms.web.drawing.workbench as workbench_module
from db import db_session
from foms.services.datetime_kst import get_today_kst
from foms.services.orders import drawing_customer_send as cs_module
from models import Order, User

SALES_NAME = "영업담당S2"


def _user(username: str, *, role: str, team: str, name: str) -> dict:
    user = User(
        username=username, password=generate_password_hash("pw"), role=role, team=team,
        name=name, is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return {"id": user.id, "username": user.username, "role": user.role}


def _login(client, who: dict) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = who["id"]
        sess["username"] = who["username"]
        sess["role"] = who["role"]


def _order(drafter_id: int, *, status: str = "TRANSFERRED", stage: str = "DRAWING", files: int = 2) -> int:
    history = [{
        "action": "TRANSFER", "by_user_id": drafter_id, "by_user_name": "도면담당S2",
        "at": "2026-09-20 01:00:00", "transferred_at": "2026-09-20 01:00:00", "note": "1차 전달", "files": [],
    }]
    if status == "RETURNED":
        history.append({
            "action": "REQUEST_REVISION", "by_user_name": SALES_NAME, "at": "2026-09-21 01:00:00",
            "note": "문짝 폭 줄여 주세요", "files": [],
        })
    current = [{"key": f"orders/s2/drawing/plan-{i}.png", "filename": f"plan-{i}.png"} for i in range(1, files + 1)]
    order = Order(
        received_date=get_today_kst().strftime("%Y-%m-%d"), customer_name="S2 고객", phone="010-0000-0022",
        address="서울 강동구", product="붙박이장", status="DRAWING", manager_name=SALES_NAME, is_erp_order=True,
        structured_data={
            "parties": {"customer": {"name": "S2 고객"}, "manager": {"name": SALES_NAME}},
            "workflow": {"stage": stage},
            "drawing_status": status,
            "assignments": {"drawing_assignee_user_ids": [drafter_id]},
            "drawing_current_files": current,
            "drawing_transfer_history": history,
        },
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _bar(*keys: str, tone: dict | None = None) -> list[dict]:
    tone = tone or {}
    return [{"key": k, "label": "", "tone": tone.get(k, ""), "slot": "main"} for k in keys]


def _inject(monkeypatch, cs: dict | None = None, ctx_patch=None) -> None:
    """상세 라우트가 렌더 직전에 만든 ctx 의 customer_send 를 덮어쓴다(판정은 S1 몫 — 모양만 본다)."""
    real = workbench_module.render_template

    def fake(template_name, **ctx):
        if template_name in ("drawing/workbench_detail.html", "drawing/workbench_detail_fragment.html"):
            if cs is not None:
                # 늘 빈 값에서 시작한다 — 실제 ctx(S1 값: can_change_phone 등)가 모양 테스트에 새지 않게.
                merged = cs_module.empty_customer_send_view()
                merged.update(cs)
                ctx["customer_send"] = merged
            if ctx_patch is not None:
                ctx_patch(ctx)
        return real(template_name, **ctx)

    monkeypatch.setattr(workbench_module, "render_template", fake)


def _page(client, who: dict, order_id: int) -> BeautifulSoup:
    _login(client, who)
    res = client.get(f"/erp/drawing-workbench/{order_id}")
    assert res.status_code == 200, res.get_data(as_text=True)[:500]
    return BeautifulSoup(res.get_data(as_text=True), "html.parser")


def _pc(soup: BeautifulSoup):
    pc = soup.select_one(".dw-legacy-detail .dw-sidebar-actions")
    assert pc is not None
    return pc


def _bar_keys(soup: BeautifulSoup) -> list[str]:
    return [el["data-bar-key"] for el in _pc(soup).select("[data-bar-key]")]


def _legacy(soup: BeautifulSoup) -> list[str]:
    """빈 bar 대체로 그린 옛 버튼(data-bar-legacy)의 키."""
    return [el["data-bar-key"] for el in _pc(soup).select("[data-bar-legacy]")]


def make_people() -> dict:
    return {
        "drafter": _user("s2_drafter", role="STAFF", team="DRAWING", name="도면담당S2"),
        "sales": _user("s2_sales", role="MANAGER", team="SALES", name=SALES_NAME),
    }


# S1 연결 판정: S1 의 상세 라우트는 ``from ...drawing_customer_send_view import build_customer_send_view`` 로 이 이름을
# workbench 모듈에 들인다. S1a(뼈대)만 있으면 이 이름이 없다 — 모듈 존재가 아니라 실제로 쓰는지를 본다.
S1_MERGED = callable(getattr(workbench_module, "build_customer_send_view", None))
