"""생산 탭 렌더 전 304 시험 공용 준비 — 보드 시드·로그인·키 가로채기·변이·대조군 약화.

``tests/domains/test_production_prerender_key_contract.py``(키 계약)와
``tests/domains/test_production_prerender_shadow.py``(그림자 관측)가 같이 쓴다.
"""

from __future__ import annotations

import copy
import datetime
from typing import Any, Callable

import pytest
from sqlalchemy import func
from sqlalchemy.orm.attributes import flag_modified
from werkzeug.security import generate_password_hash

import foms.web.production.dashboard as pd
from db import db_session
from foms.services import context_processors, dashboard_counts
from foms.services import production_fragment_version as pfv
from foms.services import production_read_model
from foms.services.common import dashboard_cache
from foms.services.common import fragment_prerender as fp
from foms.services.datetime_kst import get_today_kst
from models import Order, OrderAttachment, OrderEvent, ProductionRun, SystemSetting, User
from tests.support.fragver_fake_redis import FakeRedis

PATH = "/erp/production/dashboard?view=fragment"
SHELL_HEADERS = {"X-FOMS-ERP-SHELL": "1", "If-None-Match": '"seed-validator"'}
KANBAN_COOKIES = {"foms_ptr": "coarse", "foms_vw": "narrow", "foms_scr": "1200"}
PC_COOKIES = {"foms_ptr": "fine", "foms_vw": "wide", "foms_scr": "1920"}


# --------------------------------------------------------------------------- 공용 준비


@pytest.fixture(autouse=True)
def _clean_process_caches():
    """프로세스 캐시가 앞 테스트의 값을 들고 있으면 읽기가 숨는다(기록 계약이 못 본다)."""
    dashboard_cache.reset_dashboard_cache_runtime_for_tests()
    dashboard_counts._cache.clear()
    context_processors._ADMIN_SWITCH_USERS_CACHE["ts"] = 0.0
    yield
    dashboard_counts._cache.clear()
    context_processors._ADMIN_SWITCH_USERS_CACHE["ts"] = 0.0


@pytest.fixture(autouse=True)
def _sqlite_attachment_counts(monkeypatch):
    """첨부 수 SQL 은 PostgreSQL 전용(``= ANY``)이라 SQLite 에서는 늘 0 이 된다 — 같은 뜻의 대역을 끼운다.

    대역이 없으면 첨부 변이가 본문을 못 바꿔 키 계약이 첨부 재료를 시험하지 못한다.
    """

    def _counts(db, rows):
        ids = [o.id for o in rows]
        if not ids:
            return {}
        q = (
            db.query(OrderAttachment.order_id, func.count(OrderAttachment.id))
            .filter(OrderAttachment.order_id.in_(ids), OrderAttachment.deleted_at.is_(None))
            .group_by(OrderAttachment.order_id)
        )
        return {int(oid): int(n) for oid, n in q}

    monkeypatch.setattr(production_read_model, "fetch_production_attachment_counts", _counts)


@pytest.fixture
def shadow(monkeypatch):
    """그림자 관측을 켜고 뷰가 만든 키를 가로챈다."""
    redis = FakeRedis()
    monkeypatch.setenv(fp.SHADOW_ENV_FLAG, "1")
    monkeypatch.setattr(dashboard_cache, "get_dashboard_redis", lambda: redis)
    monkeypatch.setattr(fp, "_now_s", lambda: 1_790_000_000.0)
    captured: dict[str, Any] = {}

    def _capture(**kwargs: Any) -> str:
        captured.update(kwargs)
        return ""

    monkeypatch.setattr(pd, "observe_shadow", _capture)
    return captured


def _v2_cohort(monkeypatch) -> None:
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")


def _order(stage: str, name: str, cdate: str, **sd_extra: Any) -> Order:
    sd = {
        "workflow": {"stage": stage},
        "parties": {"customer": {"name": name, "phone": "010-2222-3333"}, "manager": {"name": "김실측"}},
        "schedule": {"construction": {"date": cdate}},
        "items": [{"product_name": "붙박이장", "spec_width": "900"}],
    }
    sd.update(sd_extra)
    return Order(
        received_date=get_today_kst().isoformat(), customer_name=name, phone="010-2222-3333",
        address="서울", product="붙박이장", status=stage, manager_name="김실측", is_erp_order=True,
        erp_stage_code=stage, erp_construction_date=cdate, structured_data=sd,
    )


def _seed() -> dict[str, Any]:
    admin = User(username="fv_admin", password=generate_password_hash("x"), role="ADMIN", team="CS",
                 name="관리자갑", is_active=True)
    sales = User(username="fv_sales", password=generate_password_hash("x"), role="STAFF", team="SALES",
                 name="영업을", is_active=True)
    db_session.add_all([admin, sales])
    db_session.commit()
    today = get_today_kst()
    orders = [
        _order("CONFIRM", "컨펌고객", (today + datetime.timedelta(days=9)).isoformat(),
               quests=[{"stage": "CONFIRM", "status": "OPEN"}]),
        _order("PRODUCTION", "대기고객", (today + datetime.timedelta(days=3)).isoformat()),
        _order("PRODUCTION", "제작고객", (today + datetime.timedelta(days=5)).isoformat()),
        _order("CONSTRUCTION", "완료고객", (today + datetime.timedelta(days=1)).isoformat()),
    ]
    db_session.add_all(orders)
    db_session.commit()
    db_session.add(ProductionRun(order_id=orders[2].id, status="IN_PROGRESS", steps=[], defects=[], is_current=True))
    db_session.add(OrderAttachment(order_id=orders[1].id, filename="a.jpg", file_type="image", category="measurement",
                                   storage_key="uploads/a.jpg", thumbnail_key="uploads/a_t.jpg", file_size=10))
    db_session.add(SystemSetting(setting_key="erp_shipment_settings",
                                 setting_value={"measurement_manager": [{"name": "김실측", "phone": "010-1111-0000"}]}))
    db_session.commit()
    return {"admin": admin.id, "sales": sales.id, "orders": [o.id for o in orders]}


def _get(model: Any, ident: Any) -> Any:
    """요청이 끝나면 세션이 비워진다(teardown) — 변이는 늘 새로 읽은 행에 한다."""
    return db_session.get(model, ident)


def _login(client, user_id: int) -> None:
    user = _get(User, user_id)
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _set_cookies(client, cookies: dict[str, str]) -> None:
    for name, value in cookies.items():
        client.set_cookie(name, value)


def _render(client, captured: dict[str, Any], path: str = PATH) -> tuple[bytes, fp.PrerenderKey | None]:
    captured.clear()
    resp = client.get(path, headers=SHELL_HEADERS)
    assert resp.status_code == 200, resp.status_code
    return resp.data, captured.get("result")



def _run_mutation(client, monkeypatch, shadow, mutate, cookies, path=PATH, path_after=None):
    _v2_cohort(monkeypatch)
    ctx = _seed()
    _login(client, ctx["admin"])
    _set_cookies(client, cookies)
    body_a, key_a = _render(client, shadow, path)
    mutate(ctx, client, monkeypatch)
    body_b, key_b = _render(client, shadow, path_after or path)
    assert key_a is not None and key_b is not None, shadow.get("abandon")
    return body_a, key_a, body_b, key_b


def _sd_update(order: Order, fn: Callable[[dict], None]) -> None:
    sd = copy.deepcopy(order.structured_data)
    fn(sd)
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()


def _m_customer_name(ctx, client, monkeypatch):
    _sd_update(_get(Order, ctx["orders"][1]), lambda sd: sd["parties"]["customer"].update(name="바뀐고객"))


def _m_stage(ctx, client, monkeypatch):
    order = _get(Order, ctx["orders"][0])
    order.erp_stage_code = "PRODUCTION"
    order.status = "PRODUCTION"
    _sd_update(order, lambda sd: sd["workflow"].update(stage="PRODUCTION"))


def _m_schedule_date(ctx, client, monkeypatch):
    order = _get(Order, ctx["orders"][3])
    new_date = (get_today_kst() + datetime.timedelta(days=20)).isoformat()
    order.erp_construction_date = new_date
    _sd_update(order, lambda sd: sd["schedule"]["construction"].update(date=new_date))


def _m_attachment_add(ctx, client, monkeypatch):
    db_session.add(OrderAttachment(order_id=ctx["orders"][2], filename="b.jpg", file_type="image",
                                   category="measurement", storage_key="uploads/b.jpg",
                                   thumbnail_key="uploads/b_t.jpg", file_size=10))
    db_session.commit()


def _m_attachment_delete(ctx, client, monkeypatch):
    att = db_session.query(OrderAttachment).filter(OrderAttachment.order_id == ctx["orders"][1]).one()
    att.deleted_at = datetime.datetime.now()
    db_session.commit()


def _m_user_name(ctx, client, monkeypatch):
    _get(User, ctx["admin"]).name = "관리자병"
    db_session.commit()


def _m_role(ctx, client, monkeypatch):
    _get(User, ctx["admin"]).role = "MANAGER"
    db_session.commit()


def _m_setting(ctx, client, monkeypatch):
    row = db_session.get(SystemSetting, "erp_shipment_settings")
    row.setting_value = {"measurement_manager": [{"name": "김실측", "phone": "010-9999-8888"}]}
    db_session.commit()


def _m_run_add(ctx, client, monkeypatch):
    db_session.add(ProductionRun(order_id=ctx["orders"][1], status="IN_PROGRESS", steps=[], defects=[],
                                 is_current=True))
    db_session.commit()


def _m_event_only(ctx, client, monkeypatch):
    """시공일 변경 이벤트만 쌓인다(주문 행은 그대로) — 변경 알림이 생긴다(생산 진입 뒤 시각)."""
    entered = _get(Order, ctx["orders"][2]).created_at
    db_session.add(OrderEvent(order_id=ctx["orders"][2], event_type="CONSTRUCTION_DATE_CHANGED",
                              payload={"from": "2026-10-01", "to": "2026-10-09"},
                              created_at=entered + datetime.timedelta(minutes=5)))
    db_session.commit()


def _m_tombstone(ctx, client, monkeypatch):
    order = _get(Order, ctx["orders"][3])
    order.status = "DELETED"
    order.deleted_at = get_today_kst().isoformat() + " 10:00:00"
    db_session.commit()


def _m_tombstone_only(ctx, client, monkeypatch):
    """보드 밖에서 취소된 생산 주문 — 창의 행은 그대로이고 묘비 카드만 생긴다."""
    gone = _order("PRODUCTION", "취소고객", get_today_kst().isoformat())
    gone.status = "DELETED"
    gone.deleted_at = get_today_kst().isoformat() + " 09:00:00"
    db_session.add(gone)
    db_session.commit()


def _m_cookie(name: str, value: str):
    def _apply(ctx, client, monkeypatch):
        client.set_cookie(name, value)

    _apply.__name__ = f"_m_cookie_{name}_{value}"
    return _apply


def _m_env(name: str, value: str):
    def _apply(ctx, client, monkeypatch):
        monkeypatch.setenv(name, value)

    _apply.__name__ = f"_m_env_{name}"
    return _apply


def _m_impersonation(ctx, client, monkeypatch):
    with client.session_transaction() as sess:
        sess["impersonating_from"] = ctx["sales"]


def _m_nav_badge(ctx, client, monkeypatch):
    """생산 밖 주문 하나 — nav 배지 숫자만 바뀐다(프로세스 캐시를 비워 새 값을 그리게)."""
    db_session.add(_order("RECEIVED", "접수고객", get_today_kst().isoformat()))
    db_session.commit()
    dashboard_counts._cache.clear()


def _weaken(monkeypatch, paths: tuple[tuple[str, ...], ...]) -> None:
    """키 재료에서 한 재료(갈래 여럿일 수 있다)를 뺀다 — 실제 재료여야 한다(없는 갈래면 시험이 실패한다)."""
    original = pfv.finish_key

    def _weakened(material, controls):
        for path in paths:
            node = material
            for part in path[:-1]:
                node = node[part]
            assert path[-1] in node, f"없는 재료 {path} — 대조군이 실제 재료에서 골라지지 않았다"
            node.pop(path[-1])
        return original(material, controls)

    monkeypatch.setattr(pfv, "finish_key", _weakened)
