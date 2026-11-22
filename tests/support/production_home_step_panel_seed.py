"""'내 공정' 탭 오른쪽 판 시험 준비물 — test_production_home_step_panel*.py 가 같이 쓴다(가짜 주문 · 로그인 · 기기 쿠키 · 조각 자르기)."""
from __future__ import annotations

import datetime
import re

from werkzeug.security import generate_password_hash

from db import db_session
from foms.api.production.orders import _PRODUCTION_STEP_DEFS
from foms.services.datetime_kst import get_today_kst
from models import Order, ProductionRun, User

HOME = "/erp/production/home"
#: 태블릿 가로(터치 + 넓은 창 + 화면 긴 변 1280)
TABLET = {"foms_ptr": "coarse", "foms_vw": "wide", "foms_scr": "1280"}
SHELL = {"X-FOMS-ERP-SHELL": "1"}
STEPS_JS = "js/production/foms-production-home-steps.js"


def login(client, name="이철호", *, part=None, team="PRODUCTION", role="STAFF") -> User:
    user = User(username=f"sp_{name}_{part or ''}_{role}", password=generate_password_hash("pw"), role=role, team=team,
                name=name, is_active=True, production_part=part)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = user.id, user.username, user.role
    return user


def set_cookies(client, values: dict | None) -> None:
    for k in ("foms_ptr", "foms_vw", "foms_scr"):
        client.delete_cookie(k, domain="localhost")
    for k, v in (values or {}).items():
        client.set_cookie(k, v, domain="localhost")


def add_order(name, off, *, done=(), run=True, hold=None, pngs=2, pdfs=0, handle=None, color="그레이",
           items=(("슬라이딩 붙박이장", "2740", "700", "2330"),), started=datetime.datetime(2026, 11, 20, 23, 40)) -> Order:
    today = get_today_kst()
    date = (today + datetime.timedelta(days=off)).isoformat()
    steps = [{"key": k, "label": l, "done": k in done, "at": "2026-11-21T00:12:00+00:00" if k in done else None,
              "by_name": "김재단" if k in done else None} for k, l in _PRODUCTION_STEP_DEFS]
    production = {"steps": steps}
    if hold is not None:
        production["hold"] = {"active": True, "reason": hold}
    its = []
    for p, w, d, h in items:
        it = {"product_name": p, "spec_width": w, "spec_depth": d, "spec_height": h, "color": color}
        if handle:
            it["handle"] = handle
        its.append(it)
    files = [{"key": f"orders/x/drawing/{name}_{j}.png", "filename": f"{name}-도면{j + 1}.png"} for j in range(pngs)]
    files += [{"key": f"orders/x/drawing/{name}_{j}.pdf", "filename": f"{name}-도면{pngs + j + 1}.pdf"} for j in range(pdfs)]
    sd = {"workflow": {"stage": "PRODUCTION"},
          "parties": {"customer": {"name": name, "phone": "010-0000-0000"}, "orderer": {"name": "가짜 인테리어"}},
          "site": {"address_full": "가짜시"}, "schedule": {"construction": {"date": date}}, "items": its,
          "production": production, "drawing_current_files": files}
    order = Order(received_date=today.isoformat(), customer_name=name, phone="010-0000-0000", address="가짜시", product="장",
                  manager_name="관리", status="PRODUCTION", is_erp_order=True, structured_data=sd, erp_stage_code="PRODUCTION",
                  erp_construction_date=date)
    db_session.add(order)
    db_session.commit()
    if run:
        db_session.add(ProductionRun(order_id=order.id, status="IN_PROGRESS", steps=[], defects=[], is_current=True,
                                     started_at=started))
        db_session.commit()
    return order


def seed_cut_queue():
    """목업 ③ 재단 줄: 박서준(그림 3장 · 손잡이 없음) · 김하늘 · 한지우(보류) · 오민재 + 엣지 1."""
    a = add_order("박서준", 1, pngs=3, handle="없음")
    b = add_order("김하늘", 2, color="화이트 오크")
    c = add_order("한지우", 3, hold="고객 연락 기다림", handle="블랙", color="화이트",
               items=(("키큰장", "600", "600", "2300"),), started=datetime.datetime(2026, 11, 20, 7, 10))
    d = add_order("오민재", 5, pngs=0)
    e = add_order("엣지집", 4, done=("cut",), pngs=0, pdfs=1)
    return a, b, c, d, e


def panel_url(step: str, oid: int) -> str:
    """판 하나 조각 주소(줄을 누르면 JS 가 받는 것 — ``?tab=steps&order=<id>`` + ``view=panel&step=``)."""
    return f"{HOME}?tab=steps&order={oid}&view=panel&step={step}"


def get_html(client, url, headers=None):
    resp = client.get(url, headers=headers or {})
    assert resp.status_code == 200, url
    return resp.get_data(as_text=True)


def queue_html(html: str, key: str) -> str:
    part = html.split(f'data-foms-home-stepq="{key}"', 1)[1]
    nxt = re.search(r'data-foms-home-stepq="|id="foms-step-confirm-modal"', part)
    return part[: nxt.start()] if nxt else part


def pane_html(html: str, oid: int) -> str:
    return html.split(f'data-foms-step-pane="{oid}"', 1)[1].split("</section>", 1)[0]
