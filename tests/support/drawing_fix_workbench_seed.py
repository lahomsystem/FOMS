"""생산 넘어간 주문의 도면 수정 D3(도면 작업실 '생산 중' 칸 · 상세 '공장 진행' · [수정 시작]/[수정 취소]) 시험 준비물.

이름 · 번호는 모두 지어낸 값이다. 날짜는 오늘(KST)에서 센다(:func:`day`). 주문은 확정 도면 ``n`` 장(마법사 시트 ``s0`` … — 시트 신원 있음) ·
전달 이력(TRANSFER + CONFIRM_RECEIPT) · 공정 칸을 갖는다. 공장 요청은 D4 가 만들 길이 없어 ``drawing_fix.requests`` JSON 을 직접 넣는다
(요청 ``state`` = ``open`` · ``done`` · ``rejected`` — 막힘 · 맨 위는 ``open`` 만).
"""
from __future__ import annotations

import copy
import datetime
from itertools import count
from types import SimpleNamespace
from typing import Any, Iterable, Optional

from sqlalchemy.orm.attributes import flag_modified
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.datetime_kst import get_today_kst, now_utc_naive
from models import Order, OrderConstructionAttempt, ProductionPartMark, User

_seq = count(1)


def day(offset: int) -> str:
    """오늘(KST)에서 ``offset`` 날 뒤 'YYYY-MM-DD'(음수 = 지남)."""
    return (get_today_kst() + datetime.timedelta(days=offset)).isoformat()


def make_user(name: str, *, team: Optional[str], role: str = "STAFF", part: Optional[str] = None,
              lead: Optional[bool] = None, partner_org_id: Optional[int] = None) -> SimpleNamespace:
    """가짜 계정(이름 = ``name``)."""
    user = User(username=f"dfw_{next(_seq)}", password=generate_password_hash("x"), role=role, team=team, name=name,
                is_active=True, production_part=part, production_lead=lead, partner_org_id=partner_org_id)
    db_session.add(user)
    db_session.commit()
    return SimpleNamespace(id=user.id, username=user.username, role=role, name=name, team=team)


def login(client, user: SimpleNamespace) -> None:
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = user.id, user.username, user.role


def key(oid: int, name: str) -> str:
    return f"orders/{oid}/drawing_wizard/exports/{name}.png"


def make_order(n: int = 3, *, stage: str = "PRODUCTION", cdate: Optional[str] = None, customer: str = "정하늘",
               status: str = "CONFIRMED", assignees: Iterable[int] = (), factory2: Iterable[str] = (),
               extra: Optional[dict[str, Any]] = None, history: Optional[list[dict[str, Any]]] = None) -> int:
    """생산 · 시공(또는 그 밖) 단계 가짜 주문 — 확정 도면 ``n`` 장, 시공일 ``cdate``(미러 · JSON 둘 다)."""
    order = Order(received_date=day(-30), customer_name=customer, phone="010-0000-0000", address="가짜시", product="가짜장",
                  status=stage, is_erp_order=True, erp_stage_code=stage, erp_construction_date=cdate, structured_data={},
                  # '바뀐 것' 창 시작(UTC) — 만든 시각(지역 시계)에 기대지 않게
                  erp_stage_updated_at=now_utc_naive() - datetime.timedelta(days=1))
    db_session.add(order)
    db_session.commit()
    oid = order.id
    files = [{"key": key(oid, f"s{j}"), "filename": f"s{j}.png", "sheet_id": f"s{j}"} for j in range(n)]
    steps = [{"key": k, "label": k, "done": False, "at": None, "by_name": None} for k in ("cut", "edge", "assemble", "inspect")]
    sd = {
        "parties": {"customer": {"name": customer}, "manager": {"name": "영업가짜"}},
        "workflow": {"stage": stage},
        "schedule": {"construction": {"date": cdate}} if cdate else {},
        "drawing_status": status,
        "assignments": {"drawing_assignee_user_ids": list(assignees)},
        "drawing_current_files": files,
        "drawing_transfer_history": [
            {"action": "TRANSFER", "by_user_id": None, "transferred_at": "2026-11-20 00:00:00", "files": files},
            {"action": "CONFIRM_RECEIPT", "by_user_id": None, "at": "2026-11-20 01:00:00", "files": files},
        ] + list(history or []),
        "drawing_wizard": {"v": 1, "sheets": [{"id": f"s{j}", "name": f"시트{j}", "form": {}, "objects": []} for j in range(n)],
                           "pending": {}},
        "production": {"steps": steps},
        **({"drawing_factory": {"sheets": {s: 2 for s in factory2}, "files": {}}} if factory2 else {}),
        **(extra or {}),
    }
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()
    return oid


def patch(oid: int, **fields: Any) -> None:
    """주문 JSON 최상위 칸을 고친다(deepcopy → 재대입 → flag_modified)."""
    order = db_session.get(Order, oid)
    sd = copy.deepcopy(order.structured_data)
    sd.update(fields)
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()


def sd_of(oid: int) -> dict[str, Any]:
    db_session.expire_all()
    return db_session.get(Order, oid).structured_data


def sales_request(at: str, *, name: str = "이영업", targets: Iterable[str] = ()) -> dict[str, Any]:
    """영업 수정 요청 이력 줄(RETURNED 와 같이 넣는다)."""
    return {"action": "REQUEST_REVISION", "by_user_id": None, "by_user_name": name, "at": at, "note": "상판 깊이 600 → 580",
            "target_drawing_keys": list(targets)}


def factory_request(at: str, targets: Iterable[str], numbers: Iterable[int], *, state: str = "open",
                    name: str = "박반장") -> dict[str, Any]:
    """공장 요청 한 건(D4 가 만들 모양 — 시험은 JSON 을 직접 넣는다)."""
    return {"id": f"fr_{next(_seq)}", "from": "factory", "targets": list(targets), "numbers": list(numbers),
            "note": "측판 길이가 실측과 달라요", "photos": [], "factory": 1, "by_user_id": None, "by_name": name, "at": at,
            "state": state, "done_at": None}


def start_construction(oid: int) -> None:
    """시공 방문을 연다(``order_construction_attempts.is_current``)."""
    db_session.add(OrderConstructionAttempt(order_id=oid, status="IN_PROGRESS", is_current=True))
    db_session.commit()


def put_mark(oid: int, drawing_key: str, part: str, state: str, *, name: str = "김재단", picked: bool = True) -> None:
    """표시 줄 하나(완료 · 기본 · 맡음 — 맡은 사람은 가짜 생산팀 계정)."""
    finished = state in ("DONE", "BASIC")
    holder = make_user(name, team="PRODUCTION") if picked and state != "BASIC" else None
    db_session.add(ProductionPartMark(
        order_id=oid, drawing_key=drawing_key, part=part, state=state,
        picked_by_user_id=holder.id if holder else None, picked_by_name=name if holder else None,
        done_by_user_id=holder.id if holder and finished else None, done_by_name=name if finished else None))
    db_session.commit()


def people() -> SimpleNamespace:
    """권한 표(§4-1)의 사람들 — 도면팀 STAFF · MANAGER · 지정 담당 · 관리자 · 영업 · 반장 · 파트 계정 · 보기만 · 생산팀 MANAGER."""
    return SimpleNamespace(
        staff=make_user("김도면", team="DRAWING"), manager=make_user("오도면", team="DRAWING", role="MANAGER"),
        assignee=make_user("서도면", team="DRAWING"), admin=make_user("한관리", team=None, role="ADMIN"),
        sales=make_user("이영업", team="SALES"), lead=make_user("박반장", team="PRODUCTION", lead=True),
        part=make_user("최재단", team="PRODUCTION", part="cut"), viewer=make_user("문보기", team="DRAWING", role="VIEWER"),
        prod_manager=make_user("남생산", team="PRODUCTION", role="MANAGER"),
    )
