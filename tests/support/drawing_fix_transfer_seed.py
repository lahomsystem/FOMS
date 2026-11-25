"""생산 넘어간 주문의 도면 수정 D2(수정본 보내기) 시험 준비물 — 가짜 계정 · 생산 · 시공 단계 주문 · 두 길 보내기.

이름은 모두 지어낸 값이다. 주문은 확정 도면 ``n`` 장(마법사 시트 ``s0`` … — 시트 신원 있음, ``manual`` 번째는 직접 올린 파일) ·
전달 이력(TRANSFER + CONFIRM_RECEIPT) · 마법사 시트 목록 · 공정 칸을 갖는다. 날짜는 오늘(KST)에서 센다.
"""
from __future__ import annotations

import copy
from itertools import count
from types import SimpleNamespace
from typing import Any, Iterable, Optional

import pytest
from sqlalchemy.orm.attributes import flag_modified
from werkzeug.security import generate_password_hash

import foms.api.drawing.erp_orders_drawing as drawing_routes
from db import db_session
from foms.services.datetime_kst import get_today_kst
from foms.services.orders.drawing_fix import fix_ident
from models import Order, ProductionPartMark, User

_seq = count(1)
STEP_AT = "2026-11-24T01:30:00+00:00"


def make_user(name: str, *, team: Optional[str], role: str = "STAFF") -> SimpleNamespace:
    """가짜 계정(이름 = ``name``)."""
    user = User(username=f"dfx_{next(_seq)}", password=generate_password_hash("x"), role=role, team=team, name=name,
                is_active=True)
    db_session.add(user)
    db_session.commit()
    return SimpleNamespace(id=user.id, username=user.username, role=role, name=name, team=team)


def login(client, user: SimpleNamespace) -> None:
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = user.id, user.username, user.role


def key(oid: int, name: str) -> str:
    return f"orders/{oid}/drawing_wizard/exports/{name}.png"


def manual_key(oid: int, name: str) -> str:
    return f"orders/{oid}/drawing/{name}.pdf"


def make_order(n: int = 3, *, stage: str = "PRODUCTION", assignees: Iterable[int] = (), manual: Iterable[int] = (),
               steps_done: Iterable[str] = (), step_by: str = "박반장", extra: Optional[dict[str, Any]] = None) -> int:
    """생산 · 시공(또는 그 밖) 단계 가짜 주문 — 확정 도면 ``n`` 장. ``manual`` 번째(0부터)는 직접 올린 파일(시트 신원 없음)."""
    order = Order(received_date=get_today_kst().isoformat(), customer_name="정하늘", phone="010-0000-0000", address="가짜시",
                  product="가짜장", status=stage, is_erp_order=True, erp_stage_code=stage, structured_data={})
    db_session.add(order)
    db_session.commit()
    oid, manual = order.id, set(manual)
    files = [{"key": manual_key(oid, f"up{j}"), "filename": f"up{j}.pdf"} if j in manual
             else {"key": key(oid, f"s{j}"), "filename": f"s{j}.png", "sheet_id": f"s{j}"} for j in range(n)]
    steps = [{"key": k, "label": k, "done": k in set(steps_done), "at": STEP_AT if k in set(steps_done) else None,
              "by_name": step_by if k in set(steps_done) else None} for k in ("cut", "edge", "assemble", "inspect")]
    sd = {
        "parties": {"customer": {"name": "정하늘"}, "manager": {"name": "영업가짜"}},
        "workflow": {"stage": stage},
        "drawing_status": "CONFIRMED",
        "assignments": {"drawing_assignee_user_ids": list(assignees)},
        "drawing_current_files": files,
        "drawing_transfer_history": [
            {"action": "TRANSFER", "by_user_id": None, "transferred_at": "2026-11-20 00:00:00", "files": files},
            {"action": "CONFIRM_RECEIPT", "by_user_id": None, "at": "2026-11-20 01:00:00", "files": files},
        ],
        "drawing_wizard": {"v": 1, "sheets": [{"id": f"s{j}", "name": f"시트{j}", "form": {}, "objects": []}
                                              for j in range(n) if j not in manual], "pending": {}},
        "production": {"steps": steps},
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


def put_mark(oid: int, drawing_key: str, part: str, state: str, *, name: str = "김재단", sheet_id: Optional[str] = None,
             picked: bool = True) -> None:
    """표시 줄 하나를 직접 심는다(완료 · 기본 · 맡음 — 맡은 사람은 가짜 생산팀 계정)."""
    finished = state in ("DONE", "BASIC")
    holder = make_user(name, team="PRODUCTION") if picked and state != "BASIC" else None
    db_session.add(ProductionPartMark(
        order_id=oid, drawing_key=drawing_key, part=part, state=state, sheet_id=sheet_id,
        picked_by_user_id=holder.id if holder else None, picked_by_name=name if holder else None,
        done_by_user_id=holder.id if holder and finished else None, done_by_name=name if finished else None))
    db_session.commit()


def marks(oid: int) -> dict[tuple[str, str], ProductionPartMark]:
    db_session.expire_all()
    return {(m.drawing_key, m.part): m for m in db_session.query(ProductionPartMark).filter_by(order_id=oid)}


def seed_pending(oid: int, *sheets: str, version: str = "v2") -> None:
    """마법사 전달 대기함에 시트 새 판을 넣는다(작업실 일괄 · 태블릿 ``transfer-pending`` 길)."""
    order = db_session.get(Order, oid)
    sd = copy.deepcopy(order.structured_data)
    sd["drawing_wizard"]["pending"] = {
        s: {"key": key(oid, f"{s}-{version}"), "filename": f"{s}-{version}.png", "at": "2026-11-25 10:00", "sheet_name": s}
        for s in sheets}
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()


def send(client, path: str, oid: int, *sheets: str, note: str = "상판 깊이 600 → 580", manual: Iterable[dict] = (),
         **body: Any):
    """두 길 — ``drawing`` = 작업실 [전달]/마법사 [저장] 창(``transfer-drawing``), ``pending`` = 일괄(``transfer-pending``)."""
    if path == "pending":
        seed_pending(oid, *sheets)
        return client.post(f"/api/orders/{oid}/drawing-wizard/transfer-pending", json={"note": note, **body})
    files = [{"key": key(oid, f"{s}-v2"), "filename": f"{s}-v2.png", "sheet_id": s} for s in sheets] + list(manual)
    return client.post(f"/api/orders/{oid}/transfer-drawing", json={"note": note, "files": files, "mode": "APPEND", **body})


class CapturingStorage:
    """버전 스냅샷 · 옛 판 지우기를 받아만 두는 가짜 저장소."""

    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}

    def upload_file(self, file_obj, filename, folder):
        self.store[f"{folder}/{filename}"] = file_obj.read()
        return {"success": True, "key": f"{folder}/{filename}"}

    def read_file_bytes(self, k):
        return self.store.get(k)

    def delete_file(self, k):
        self.store.pop(k, None)
        return True


@pytest.fixture
def quiet(monkeypatch):
    """폰 · 실시간 알림은 끄고(실제 발송 없음) 버전 스냅샷은 가짜 저장소로."""
    monkeypatch.setattr(drawing_routes, "emit_erp_notification_to_users", lambda *a, **k: None)
    monkeypatch.setattr("foms.services.notifications.realtime_notifications.emit_erp_notification_to_users",
                        lambda *a, **k: None)
    monkeypatch.setattr("foms.services.notifications.push_sender.enqueue_push_for_notification", lambda *a, **k: None)
    monkeypatch.setattr("foms.api.drawing.wizard.get_storage", lambda: CapturingStorage())


@pytest.fixture
def team():
    """도면팀 둘(담당 · 비담당) · 영업 · 관리자."""
    return SimpleNamespace(drawer=make_user("김도면", team="DRAWING"), other=make_user("오도면", team="DRAWING"),
                           sales=make_user("이영업", team="SALES"), admin=make_user("한관리", team=None, role="ADMIN"))


def last_transfer(sd: dict) -> dict:
    """전달 이력의 마지막 ``TRANSFER`` 줄."""
    return next(h for h in reversed(sd["drawing_transfer_history"]) if h.get("action") == "TRANSFER")


def acked_idents(oid: int) -> list[str]:
    """그 주문 지금 확정 도면 열쇠 전부 — 보내기 전 확인 창에서 모두 물어본 것처럼 싣는 ``ack_worked``(시험 도우미)."""
    db_session.expire_all()
    return [fix_ident(f) for f in db_session.get(Order, oid).structured_data.get("drawing_current_files") or []]


def names(sd: dict) -> list[str]:
    """지금 확정 도면 파일 이름(도면 번호 순)."""
    return [f["key"].rsplit("/", 1)[-1] for f in sd["drawing_current_files"]]
