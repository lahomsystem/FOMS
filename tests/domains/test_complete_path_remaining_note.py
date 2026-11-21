"""실측 보드 [완료] 확인 글의 "남은 시공" 한 줄 (묶음 B, 설계서 5.3 · 결정 M13).

글은 서버(``complete_path_policy._build_one``)가 만들고 매크로가 ``data-confirm`` 에 싣는다 —
JS · 핀 변경 없음. 누를 수 있는 단추이고 오늘보다 뒤 시공일이 남았을 때만 붙는다. 막지 않는다.
이름 · 주소는 지어낸 것.
"""
from __future__ import annotations

import datetime
import itertools

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.datetime_kst import get_today_kst
from foms.services.orders.complete_path_policy import COMPLETE_CONFIRM, build_complete_ctas
from models import Order, User

_seq = itertools.count(1)


def _day(offset: int) -> datetime.date:
    return get_today_kst() + datetime.timedelta(days=offset)


TODAY, LATER = _day(0), _day(12)
TWO_DATES = f"{TODAY.isoformat()}, {LATER.isoformat()}"
REMAIN_TEXT = f"{LATER.month}/{LATER.day} 시공이 남아 있어요"


def _user() -> User:
    user = User(username=f"remain_cta_{next(_seq)}", password=generate_password_hash("x"), role="ADMIN",
                team="CS", name="가짜관리", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _order(cons_text: str, *, stage: str, regional: bool = False, quest_ok: bool = False) -> Order:
    sd: dict = {"workflow": {"stage": stage}, "schedule": {"construction": {"date": cons_text}},
                "items": [{"product_name": "가짜장", "quantity": 1}]}
    if quest_ok:
        sd["quests"] = [{"stage": "CS", "status": "OPEN", "required_approvals": ["CS"],
                         "team_approvals": {"CS": {"approved": True, "approved_by": None, "approved_at": None}}}]
    order = Order(received_date=TODAY.isoformat(), customer_name="가짜고객", phone="010-0000-0000",
                  address="가짜시 가짜구 1", product="가짜장", status=stage, manager_name="가짜영업",
                  is_erp_order=True, is_regional=regional, structured_data=sd, erp_stage_code=stage)
    db_session.add(order)
    db_session.commit()
    return order


def test_regional_order_with_later_date_gets_the_line(app):
    """지방 주문은 어느 단계에서든 완료된다 — 뒤 시공일이 남았으면 확인 글 뒤에 한 줄."""
    user = _user()
    two = _order(TWO_DATES, stage="PRODUCTION", regional=True)
    one = _order(TODAY.isoformat(), stage="PRODUCTION", regional=True)
    past = _order(f"{_day(-12).isoformat()}, {_day(-5).isoformat()}", stage="PRODUCTION", regional=True)
    ctas = build_complete_ctas([two, one, past], user)

    assert ctas[two.id]["enabled"] is True
    assert ctas[two.id]["confirm"] == COMPLETE_CONFIRM + "\n\n" + REMAIN_TEXT
    # 대조군: 시공일 하나(오늘) · 시공일 둘이지만 모두 지남 — 글이 그대로다.
    assert ctas[one.id]["enabled"] is True and ctas[one.id]["confirm"] == COMPLETE_CONFIRM
    assert ctas[past.id]["enabled"] is True and ctas[past.id]["confirm"] == COMPLETE_CONFIRM


def test_cs_stage_order_with_later_date_gets_the_line(app):
    """첫 시공일에 [시공 완료]를 눌러 CS 로 넘어온 주문(5687 꼴) — CS [완료]에도 한 줄."""
    user = _user()
    order = _order(TWO_DATES, stage="CS", quest_ok=True)
    cta = build_complete_ctas([order], user)[order.id]
    assert cta["enabled"] is True and cta["endpoint"] == "cs_complete"
    assert cta["confirm"] == COMPLETE_CONFIRM + "\n\n" + REMAIN_TEXT


def test_blocked_button_gets_no_line(app):
    """막힌 단추(누를 수 없음)에는 붙이지 않는다 — 확인 창이 뜨지 않는다."""
    user = _user()
    blocked = _order(TWO_DATES, stage="PRODUCTION")              # 지방 아님 + CS 전
    cta = build_complete_ctas([blocked], user)[blocked.id]
    assert cta["enabled"] is False and REMAIN_TEXT not in cta["confirm"]


def test_macro_carries_the_line_into_data_confirm(app):
    """매크로가 서버 글을 ``data-confirm`` 에 그대로 싣는다(줄바꿈 포함)."""
    tmpl = app.jinja_env.get_template("partials/shared/status_select_options.html")
    cta = {"visible": True, "enabled": True, "endpoint": "cs_complete", "label": "완료",
           "confirm": COMPLETE_CONFIRM + "\n\n" + REMAIN_TEXT, "blocked_reason": "", "blocked_href": "",
           "blocked_link_label": ""}
    html = str(tmpl.module.complete_order_control(1, "PRODUCTION", cta))
    assert f'data-confirm="{COMPLETE_CONFIRM}\n\n{REMAIN_TEXT}"' in html
