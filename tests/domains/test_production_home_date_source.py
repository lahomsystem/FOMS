"""생산팀 첫 화면 시공일 출처 한 벌(R6, 2026-11-11).

첫 화면은 주문을 시공일로 두 번 가른다 — SQL(``Order.erp_construction_date`` 납작 열)로 "7일 넘게 지난 것"을
골라 개수 제한을 걸고, 파이썬으로 날짜 장·묶음을 나눈다. 행의 ``construction_date`` 는
``structured_data.schedule.construction.date``(JSONB)에서 오므로, 저장 때 맞추는 ``sync_erp_flat_columns`` 를
거치지 않은 옛 데이터(직접 SQL 로 고친 것)에서 두 값이 어긋나면 SQL 은 "앞날 주문"이라고 가져온 주문을
화면은 "지난 시공일" 장에 넣었다(거꾸로도). 고침: 첫 화면 읽기 모델 안에서 장 나누기도 납작 열을 쓴다.
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


def test_어긋난_옛_주문도_SQL_이_가른_자리와_같은_장에_선다(client, monkeypatch) -> None:
    user = _make_user("home_date_src_staff")
    _add_order("앞날", 3, 3)
    _add_order("납작은앞날", 2, -60)    # SQL: 앞날(전부 읽음) · JSONB: 60일 지남
    _add_order("납작은옛날", -50, 1)    # SQL: 지난 것(캡 대상) · JSONB: 내일
    _add_order("옛주문", -30, -30)
    monkeypatch.setattr(home_read_model, "PRODUCTION_KANBAN_MAX_ROWS", 3)

    rows, stats = build_production_home(db_session, user)
    # 앞날 2건 전부 + 지난 것 중 최근 1건(옛주문 -30) — 납작은옛날(-50)은 캡에 밀린다
    assert _names(rows) == ["납작은앞날", "앞날", "옛주문"]
    assert stats == {"past_hidden": 1, "total": 4}

    days = production_home_days(rows, get_today_kst(), past_hidden=stats["past_hidden"])
    panes = {p["key"]: p for p in days["panes"]}
    # 장 나누기도 SQL 과 같은 출처 — 앞날로 읽힌 주문은 그 날 장에, 지난 장은 SQL 이 지난 것으로 가져온 것만
    assert _names(panes[_iso(2)]["make_rows"]) == ["납작은앞날"]
    assert _names(panes["past"]["make_rows"]) == ["옛주문"]
    assert panes["past"]["hidden"] == 1
    assert panes[_iso(1)]["total"] == 0

    groups = production_home_groups(rows, get_today_kst(), past_hidden=stats["past_hidden"])
    assert [g["key"] for g in groups] == [_iso(2), _iso(3), "past"]
    assert _names(groups[-1]["rows"]) == ["옛주문"]
    assert len({g["key"] for g in groups}) == len(groups)  # 같은 날 묶음이 두 번 서지 않는다


def test_출처가_같은_주문은_그대로(client) -> None:
    user = _make_user("home_date_src_same")
    _add_order("내일", 1, 1)
    rows, _ = build_production_home(db_session, user)
    assert rows[0]["construction_date"] == _iso(1)
    assert rows[0]["day_label"].startswith("내일")
