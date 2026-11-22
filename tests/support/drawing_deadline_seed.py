"""도면 마감 알림 시험 준비물 — 지어낸 이름만 쓴다(저장소 공개).

날은 2026-11 고정(월 11/23 · 수 11/25). 시각은 KST 로 넣는다(CI 는 UTC — 알림 단계는 ``now`` 를 받는다).
"""
from __future__ import annotations

import contextlib
import datetime
from typing import Any, Iterator

from sqlalchemy import event
from sqlalchemy.orm.attributes import flag_modified
from werkzeug.security import generate_password_hash

from db import db_session, engine
from foms.services.notifications import drawing_deadline_alert as alert
from models import Notification, Order, SystemSetting, User

KST = datetime.timezone(datetime.timedelta(hours=9))
_SEQ = [0]


def at(day: str, hour: int, minute: int = 0) -> datetime.datetime:
    """'2026-11-23', 8, 2 → KST 시각."""
    d = datetime.date.fromisoformat(day)
    return datetime.datetime(d.year, d.month, d.day, hour, minute, tzinfo=KST)


def make_user(name: str, team: str | None, role: str = "STAFF", *, active: bool = True,
              partner_org_id: int | None = None) -> int:
    """켜진(또는 꺼진) 계정 하나 — 번호를 준다(협력사 계정은 ``role='PARTNER'`` + 소속)."""
    _SEQ[0] += 1
    user = User(username=f"dda_{_SEQ[0]}", password=generate_password_hash("pw"), role=role, team=team,
                name=name, is_active=active, partner_org_id=partner_org_id)
    db_session.add(user)
    db_session.commit()
    return int(user.id)


def make_order(customer: str, construction: str | None, *, stage: str = "DRAWING", assignees: tuple = (),
               status: str = "RETURNED", manager: str = "이가짜", partner: bool = False,
               product: str = "붙박이장") -> int:
    """도면 · 컨펌 기다림 주문(전화 · 주소는 지어낸 값 — 알림 글에 나오면 안 된다).

    Args:
        assignees: ``(id, 이름)`` 쌍들 — 도면 담당(id 칸과 이름 칸을 함께 남기는 실제 쓰기와 같은 꼴).
    """
    sd: dict[str, Any] = {
        "workflow": {"stage": stage},
        "parties": {"customer": {"name": customer, "phone": "010-1234-5678"}, "manager": {"name": manager}},
        "site": {"address_full": "가짜시 가짜구 1"},
        "schedule": {"construction": {"date": construction}} if construction else {},
        "items": [{"product_name": product}],
        "drawing_status": status,
    }
    if assignees:
        sd["assignments"] = {"drawing_assignee_user_ids": [uid for uid, _n in assignees]}
        sd["drawing_assignees"] = [{"id": uid, "name": name} for uid, name in assignees]
    if partner:
        sd["source"] = "PARTNER"
    order = Order(received_date="2026-11-01", customer_name=customer, phone="010-1234-5678", address="가짜시 가짜구 1",
                  product=product, status=stage, is_erp_order=True, erp_stage_code=stage,
                  erp_construction_date=construction, structured_data=sd)
    db_session.add(order)
    db_session.commit()
    return int(order.id)


def change_order(order_id: int, *, stage: str | None = None, construction: str | None = None) -> None:
    """단계 · 시공일을 바꾼다 — sd 와 납작 칸을 함께(실제 쓰기 경로의 ``sync_erp_flat_columns`` 와 같은 결과)."""
    order = db_session.get(Order, order_id)
    sd = dict(order.structured_data)
    if stage is not None:
        sd["workflow"] = {"stage": stage}
        order.erp_stage_code = stage
    if construction is not None:
        sd["schedule"] = {"construction": {"date": construction}}
        order.erp_construction_date = construction
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()


def enable(monkeypatch, only: str | None = None) -> None:
    """스위치 켬(+ 허용 목록). 기억(창 놓침 확인)도 비운다."""
    monkeypatch.setenv(alert.ENABLED_ENV, "1")
    if only is None:
        monkeypatch.delenv(alert.ONLY_USERS_ENV, raising=False)
    else:
        monkeypatch.setenv(alert.ONLY_USERS_ENV, only)
    alert.reset_process_memory()


def run(now: datetime.datetime) -> dict:
    """한 바퀴(루프처럼 단계 뒤 커밋)."""
    result = alert.run_drawing_deadline_alerts(db_session, now=now)
    db_session.commit()
    return result


def rows(order_id: int | None = None) -> list[Notification]:
    """만든 도면 마감 알림 줄(번호 순)."""
    q = db_session.query(Notification).filter(Notification.notification_type == alert.NOTIFICATION_TYPE)
    if order_id is not None:
        q = q.filter(Notification.order_id == order_id)
    return q.order_by(Notification.id).all()


def to_ids(order_id: int | None = None) -> list[int]:
    """받은 사람 번호(정렬)."""
    return sorted(int(n.target_user_id) for n in rows(order_id))


def state() -> dict:
    """기록 줄 값의 ``sent``."""
    db_session.expire_all()
    row = db_session.get(SystemSetting, alert.STATE_KEY)
    return dict((row.setting_value or {}).get("sent") or {}) if row is not None else {}


@contextlib.contextmanager
def statements() -> Iterator[list[str]]:
    """그 안에서 나간 SQL 문(앞 글자만 볼 수 있게 대문자로)."""
    seen: list[str] = []

    def _before(_conn, _cursor, statement, *_a, **_k):
        seen.append(" ".join(str(statement).split()).upper())

    event.listen(engine, "before_cursor_execute", _before)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", _before)


def seed_world() -> dict:
    """도면팀 둘(+ 꺼진 하나) · 영업 둘 · CS 하나 · 관리자 하나(+ 꺼진 하나) · 같은 이름 협력사 계정 하나 → 이름표 → 번호."""
    from models import PartnerOrg

    org = PartnerOrg(name="가짜협력")
    db_session.add(org)
    db_session.commit()
    ids = {
        "draw": make_user("장가짜", "DRAWING"), "draw2": make_user("도가짜", "DRAWING"),
        "draw_off": make_user("꺼진도면", "DRAWING", active=False),
        "sales": make_user("이가짜", "SALES"), "sales2": make_user("영가짜", "SALES"),
        "cs": make_user("씨가짜", "CS"), "admin": make_user("관가짜", None, role="ADMIN"),
        "admin_off": make_user("꺼진관리", None, role="ADMIN", active=False),
        # 같은 이름 · 같은 팀이어도 협력사 계정은 넓은 길(도면팀 전원)로 받지 않는다
        "partner_user": make_user("도가짜", "DRAWING", role="PARTNER", partner_org_id=org.id),
    }
    return ids
