"""생산팀 첫 화면 날짜 출처 한 벌(R6 2026-11-11 → 출고일 2026-11-25).

첫 화면은 주문을 두 번 가른다 — SQL 로 "7일 넘게 지난 것"을 골라 개수 제한을 걸고, 파이썬으로 날짜 장·묶음을 나눈다.
예전(R6)에는 둘 다 납작 열(``Order.erp_construction_date``)을 썼다. 이제 장 · 묶음은 출고일(``ship_dates`` — 시공일 전부는
``structured_data`` 의 ``all_construction_dates``, 출고 화면 일정 표와 같은 출처, 사장님 2026-11-25)로 나누고, SQL 경계는
납작 열에 더해 일정 표 · 지방 상차 예정일도 본다(``ship_dates.live_condition``). 그래서 납작 열과 JSONB 가 어긋난 옛 데이터도
"앞날 출고가 있는 주문"은 캡에 밀리지 않고, 장은 JSONB 날로 선다.
"""

from __future__ import annotations

import datetime

from werkzeug.security import generate_password_hash

from db import db_session
from foms.api.production.orders import _PRODUCTION_STEP_DEFS
from foms.services import production_home_read_model as home_read_model
from foms.services.datetime_kst import get_today_kst
from foms.services.production_home_days import production_home_days
from foms.services.production_home_read_model import build_production_home, production_home_groups
from models import Order, User


def _make_user(name: str) -> User:
    user = User(username=name, password=generate_password_hash("pw"), role="STAFF", team="PRODUCTION",
                name=name, is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _iso(offset: int) -> str:
    return (get_today_kst() + datetime.timedelta(days=offset)).isoformat()


def _add_order(name: str, flat_offset: int, sd_offset: int) -> Order:
    """납작 열(``erp_construction_date``)과 JSONB 시공일을 따로 정한 주문 — 같으면 정상, 다르면 어긋난 옛 데이터."""
    today = get_today_kst()
    sd = {
        "workflow": {"stage": "PRODUCTION"},
        "parties": {"customer": {"name": name, "phone": "010-0000-0000"}},
        "site": {"address_full": f"{name} 사는 곳"},
        "schedule": {"construction": {"date": _iso(sd_offset)}},
        "items": [{"product_name": "거실장", "spec_width": "3100", "quantity": 1}],
        "production": {"steps": [{"key": k, "label": l, "done": False} for k, l in _PRODUCTION_STEP_DEFS]},
    }
    order = Order(
        received_date=today.isoformat(), customer_name=name, phone="010-0000-0000", address=f"{name} 사는 곳",
        product="거실장", manager_name="관리", status="PRODUCTION", is_erp_order=True,
        structured_data=sd, erp_stage_code="PRODUCTION", erp_construction_date=_iso(flat_offset),
    )
    db_session.add(order)
    db_session.commit()
    return order


def _names(rows) -> list[str]:
    return sorted(r["customer_name"] for r in rows)


def test_어긋난_옛_주문도_출고일로_읽고_그_장에_선다(client, monkeypatch) -> None:
    user = _make_user("home_date_src_staff")
    _add_order("앞날", 3, 3)
    _add_order("납작은앞날", 2, -60)    # 납작 열: 앞날(전부 읽음) · 출고일(JSONB): 60일 지남
    _add_order("납작은옛날", -50, 1)    # 납작 열: 지난 것 · 출고일(JSONB · 일정 표): 내일 → 캡에 안 밀린다
    _add_order("옛주문", -30, -30)
    monkeypatch.setattr(home_read_model, "PRODUCTION_KANBAN_MAX_ROWS", 3)

    rows, stats = build_production_home(db_session, user)
    # 출고일이 7일 안 · 앞날일 수 있는 3건 전부 — 출고일이 모두 지난 옛주문(-30)만 캡에 밀린다
    assert _names(rows) == ["납작은앞날", "납작은옛날", "앞날"]
    assert stats == {"past_hidden": 1, "total": 4}

    days = production_home_days(rows, get_today_kst(), past_hidden=stats["past_hidden"])
    panes = {p["key"]: p for p in days["panes"]}
    # 장은 출고일(JSONB) — 납작 열이 옛날이어도 내일 출고면 내일 장, 납작 열이 앞날이어도 출고일이 지났으면 지난 출고일 장
    assert _names(panes[_iso(1)]["make_rows"]) == ["납작은옛날"]
    assert _names(panes[_iso(3)]["make_rows"]) == ["앞날"]
    assert _names(panes["past"]["make_rows"]) == ["납작은앞날"]
    assert panes["past"]["hidden"] == 1
    assert panes[_iso(2)]["total"] == 0

    groups = production_home_groups(rows, get_today_kst(), past_hidden=stats["past_hidden"])
    assert [g["key"] for g in groups] == [_iso(1), _iso(3), "past"]
    assert _names(groups[-1]["rows"]) == ["납작은앞날"]
    assert len({g["key"] for g in groups}) == len(groups)  # 같은 날 묶음이 두 번 서지 않는다


def test_출처가_같은_주문은_그대로(client) -> None:
    user = _make_user("home_date_src_same")
    _add_order("내일", 1, 1)
    rows, _ = build_production_home(db_session, user)
    assert rows[0]["construction_date"] == _iso(1)
    assert rows[0]["day_label"].startswith("내일")
