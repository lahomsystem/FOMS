"""파트 카드 표시 → 주문 공정 칸 동기화 · 파트 계정 공정 칸 직접 쓰기 막기 — 설계서 §15.5 · §15.4 끝 · §15.7(P15-6).

되돌리면 실패: 동기화 빼기(칸이 안 켜짐) · 모든 장 대신 한 장만 보기(2/3 에서 켜짐) · '안 고름'을 끝으로 치기(D57) ·
표시 없는 주문도 맞추기(손 값이 꺼짐) · 칸이 안 바뀌어도 버전 올리기 · 파트 계정 403 빼기 · 시트 단추 잠금 빼기.
대조군: 표시 줄 없는 주문의 손 값 · 칸이 안 바뀌는 쓰기의 버전 · 파트 없는 생산 · 관리자 · CS 의 공정 API 200 ·
대조군 계정의 시트 단추.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from itertools import count
from types import SimpleNamespace

import pytest
from bs4 import BeautifulSoup
from sqlalchemy import event
from werkzeug.security import generate_password_hash

import foms.api.drawing.erp_orders_drawing as drawing_routes
from db import db_session, engine
from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.production.part_steps_sync import part_steps_after, plan_part_step_changes
from models import Order, OrderEvent, ProductionPartMark, User

ONE = "/api/production/part-marks"
BULK = "/api/production/part-marks/basic"
UID_A = "aaaaaaaa-0000-4000-8000-0000000000a1"
UID_B = "bbbbbbbb-0000-4000-8000-0000000000b2"
_seq = count(1)


@pytest.fixture(autouse=True)
def _quiet_push(monkeypatch):
    """도면 쓰기 길의 폰 · 실시간 알림을 끈다(실제 발송 없음)."""
    monkeypatch.setattr(drawing_routes, "emit_erp_notification_to_users", lambda *a, **k: None)
    monkeypatch.setattr("foms.services.notifications.realtime_notifications.emit_erp_notification_to_users",
                        lambda *a, **k: None)
    monkeypatch.setattr("foms.services.notifications.push_sender.enqueue_push_for_notification",
                        lambda *a, **k: None)


@dataclass(frozen=True)
class Person:
    id: int
    username: str
    role: str


def _user(name: str, *, team: str | None = "PRODUCTION", role: str = "STAFF", part: str | None = None) -> Person:
    user = User(username=f"ps_{next(_seq)}", password=generate_password_hash("x"), role=role, team=team, name=name,
                is_active=True, production_part=part)
    db_session.add(user)
    db_session.commit()
    return Person(user.id, user.username, user.role)


def _login(client, user: Person) -> None:
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = user.id, user.username, user.role


def _order(n: int = 3, *, steps_done: tuple[str, ...] = (), extra: dict | None = None) -> int:
    prefix = f"s{next(_seq)}"
    files = [{"key": f"{prefix}/d{j}.png", "filename": f"d{j}.png", "sheet_id": f"{prefix}-s{j}"} for j in range(n)]
    steps = [{"key": k, "label": k, "done": k in steps_done, "at": None, "by_name": "손" if k in steps_done else None}
             for k in ("cut", "edge", "assemble", "inspect")]
    sd = {"workflow": {"stage": "PRODUCTION"}, "parties": {"customer": {"name": "동기화고객"}},
          "drawing_current_files": files, "production": {"steps": steps}, **(extra or {})}
    order = Order(received_date=get_today_kst().isoformat(), customer_name="동기화고객", phone="010-0000-0000",
                  address="서울", product="거실장", status="PRODUCTION", is_erp_order=True, erp_stage_code="PRODUCTION",
                  structured_data=sd)
    db_session.add(order)
    db_session.commit()
    return order.id


def _fresh(oid: int) -> Order:
    db_session.expire_all()
    return db_session.get(Order, oid)


def _keys(oid: int) -> list[str]:
    return [f["key"] for f in _fresh(oid).structured_data["drawing_current_files"]]


def _step(oid: int, key: str) -> dict:
    return next(s for s in _fresh(oid).structured_data["production"]["steps"] if s["key"] == key)


def _mark(client, oid: int, j: int, part: str, action: str, seen: str):
    return client.post(ONE, json={"order_id": oid, "drawing_key": _keys(oid)[j], "part": part, "action": action,
                                  "seen": seen})


def _finish(client, oid: int, j: int, part: str):
    assert _mark(client, oid, j, part, "take", "none").status_code == 200
    return _mark(client, oid, j, part, "done", "need")


def _step_events(oid: int) -> list[OrderEvent]:
    return (db_session.query(OrderEvent).filter_by(order_id=oid, event_type="PRODUCTION_STEP_CHECKED")
            .order_by(OrderEvent.id).all())


def _seed_mark(oid: int, key: str, part: str, state: str, name: str = "김재단") -> None:
    now = now_utc_naive()
    db_session.add(ProductionPartMark(order_id=oid, drawing_key=key, part=part, state=state, done_by_name=name,
                                      done_at=now, updated_at=now))
    db_session.commit()


# --------------------------------------------------------------------------- #
# 순수 계산
# --------------------------------------------------------------------------- #
def test_pure_rules_only_parts_with_rows_and_never_on_zero_drawings():
    sd = {"drawing_current_files": [{"key": "a"}, {"key": "b"}]}
    row = lambda key, part, state: SimpleNamespace(drawing_key=key, part=part, state=state, done_by_name="x",
                                                   done_at=None)
    assert part_steps_after(sd, []) == {}  # 카드로 안 일한 주문은 건드리지 않는다
    assert part_steps_after(sd, [row("old", "edge", "NONE")]) == {"edge": False}  # 옛 key · NONE 줄도 표지
    assert part_steps_after(sd, [row("a", "cut", "BASIC"), row("b", "cut", "DONE")]) == {"cut": True}
    assert part_steps_after(sd, [row("a", "edge", "BASIC"), row("b", "edge", "DONE")]) == {"edge": False}
    assert part_steps_after({"drawing_current_files": []}, [row("a", "cut", "DONE")]) == {}
    on = {"production": {"steps": [{"key": "cut", "done": True}]}, **sd}
    assert plan_part_step_changes(on, [row("a", "cut", "DONE"), row("b", "cut", "DONE")]) == []  # 이미 켜짐 → 바꿈 0


# --------------------------------------------------------------------------- #
# 표시 API 길
# --------------------------------------------------------------------------- #
def test_all_drawings_done_turns_step_on_once_with_last_person(client):
    oid = _order(3)
    _login(client, _user("박재단", part="cut"))
    for j in range(2):
        resp = _finish(client, oid, j, "cut")
        assert resp.status_code == 200 and resp.get_json()["data"]["order_step"] is None
    assert _step(oid, "cut")["done"] is False and _fresh(oid).mutation_version == 1  # 2/3 — 칸 · 버전 그대로
    _login(client, _user("김재단", part="cut"))
    resp = _finish(client, oid, 2, "cut")
    assert resp.get_json()["data"]["order_step"] == {"order_id": oid, "key": "cut", "done": True}
    cut = _step(oid, "cut")
    assert cut["done"] is True and cut["by_name"] == "김재단" and cut["at"]
    assert _fresh(oid).mutation_version == 2  # 한 번만 +1
    events = _step_events(oid)
    assert len(events) == 1 and events[0].payload["via"] == "part_marks" and events[0].payload["key"] == "cut"
    assert _step(oid, "edge")["done"] is False  # 다른 파트 칸은 그대로


def test_cut_basic_two_plus_done_one_turns_on_and_undo_turns_off(client):
    oid = _order(3)
    _login(client, _user("김재단", part="cut"))
    data = client.post(BULK, json={"part": "cut", "seen": "none", "items": [
        {"order_id": oid, "drawing_key": k} for k in _keys(oid)[:2]]}).get_json()["data"]
    assert data["order_steps"] == []
    assert _finish(client, oid, 2, "cut").get_json()["data"]["order_step"]["done"] is True
    assert _step(oid, "cut")["done"] is True
    undo = _mark(client, oid, 0, "cut", "undo", "basic")
    assert undo.get_json()["data"]["order_step"] == {"order_id": oid, "key": "cut", "done": False}
    cut = _step(oid, "cut")
    assert (cut["done"], cut["at"], cut["by_name"]) == (False, None, None)
    assert _fresh(oid).mutation_version == 3 and [e.payload["done"] for e in _step_events(oid)] == [True, False]


def test_bulk_turns_on_only_orders_whose_all_drawings_finished(client):
    full, partial = _order(2), _order(3)
    _login(client, _user("김재단", part="cut"))
    items = [{"order_id": full, "drawing_key": k} for k in _keys(full)]
    items += [{"order_id": partial, "drawing_key": k} for k in _keys(partial)[:2]]
    data = client.post(BULK, json={"part": "cut", "seen": "none", "items": items}).get_json()["data"]
    assert data["order_steps"] == [{"order_id": full, "key": "cut", "done": True}]
    assert _step(full, "cut")["done"] is True and _fresh(full).mutation_version == 2
    assert _step(partial, "cut")["done"] is False and _fresh(partial).mutation_version == 1


def test_edge_unpicked_drawing_keeps_step_off_d57(client):
    oid = _order(3, steps_done=("edge",))  # 사무실이 손으로 켜 둔 칸
    _login(client, _user("최엣지", part="edge"))
    take = _mark(client, oid, 0, "edge", "take", "none")  # 첫 줄 = 카드로 일한 파트 · 2장은 아무도 안 고름 = '아직'
    assert take.get_json()["data"]["order_step"] == {"order_id": oid, "key": "edge", "done": False}
    assert _step(oid, "edge")["done"] is False
    assert _mark(client, oid, 0, "edge", "done", "need").get_json()["data"]["order_step"] is None  # 1/3 끝 — 그대로
    _finish(client, oid, 1, "edge")
    assert _step(oid, "edge")["done"] is False  # 아직 1장 남음 — 바꿈 없음
    assert len(_step_events(oid)) == 1


def test_control_no_marks_manual_step_stays_and_version_unchanged(client):
    manual = _order(2, steps_done=("cut", "edge"))
    other = _order(2)
    _login(client, _user("이조립", part="assemble"))
    _finish(client, other, 0, "assemble")  # 남의 주문 · 칸이 안 바뀌는 쓰기
    assert _fresh(other).mutation_version == 1
    sd = _fresh(manual).structured_data
    assert [s["done"] for s in sd["production"]["steps"]] == [True, True, False, False]
    assert _fresh(manual).mutation_version == 1


# --------------------------------------------------------------------------- #
# 도면 쓰기 셋
# --------------------------------------------------------------------------- #
def _drawing_order(*, assignee: int, current: int = 1, status: str = "CONFIRMED", history=None,
                   items: list | None = None, file_items: list | None = None) -> int:
    oid = _order(current, extra={
        "drawing_status": status,
        "assignments": {"drawing_assignee_user_ids": [assignee]},
        "parties": {"customer": {"name": "동기화고객"}, "manager": {"name": "영업동기"}},
    })
    order = db_session.get(Order, oid)
    sd = copy.deepcopy(order.structured_data)
    if file_items:
        for f, uids in zip(sd["drawing_current_files"], file_items):
            f["item_uids"] = uids
    if items is not None:
        sd["items"] = items
    sd["drawing_transfer_history"] = history if history is not None else [
        {"action": "TRANSFER", "by_user_id": assignee, "transferred_at": "2026-11-01 00:00:00",
         "files": sd["drawing_current_files"]}]
    order.structured_data = sd
    db_session.commit()
    return oid


def test_hotfix_transfer_new_key_turns_part_step_off(client):
    drawer = _user("도면", team="DRAWING")
    oid = _drawing_order(assignee=drawer.id)
    _login(client, _user("김재단", part="cut"))
    _finish(client, oid, 0, "cut")
    assert _step(oid, "cut")["done"] is True
    version = _fresh(oid).mutation_version
    _login(client, drawer)
    resp = client.post(f"/api/orders/{oid}/transfer-drawing", json={
        "files": [{"key": f"orders/{oid}/drawing_wizard/exports/fix.png", "filename": "fix.png"}]})
    assert resp.status_code == 200, resp.get_json()
    assert _keys(oid) == [f"orders/{oid}/drawing_wizard/exports/fix.png"]  # 한 장 교체(바로 반영)
    cut = _step(oid, "cut")
    assert (cut["done"], cut["by_name"]) == (False, None)
    assert _fresh(oid).mutation_version == version + 1  # 전달 쓰기 한 번 — 동기화가 따로 올리지 않는다
    last = _step_events(oid)[-1]
    assert last.payload["trigger"] == "drawing_transfer" and last.payload["done"] is False


def test_control_hotfix_transfer_without_marks_keeps_manual_step(client):
    drawer = _user("도면", team="DRAWING")
    oid = _drawing_order(assignee=drawer.id)
    order = db_session.get(Order, oid)
    sd = copy.deepcopy(order.structured_data)
    sd["production"]["steps"][0].update(done=True, by_name="사무실")
    order.structured_data = sd
    db_session.commit()
    _login(client, drawer)
    assert client.post(f"/api/orders/{oid}/transfer-drawing", json={
        "files": [{"key": f"orders/{oid}/drawing_wizard/exports/fix.png", "filename": "fix.png"}]}).status_code == 200
    assert _step(oid, "cut")["done"] is True and _step(oid, "cut")["by_name"] == "사무실"
    assert _step_events(oid) == []


def test_item_cancel_after_confirm_leaves_all_finished_turns_on(client):
    sales = _user("영업동기", team="SALES", role="MANAGER")
    oid = _drawing_order(assignee=sales.id, current=2, items=[
        {"uid": UID_A, "product_name": "여닫이장"}, {"uid": UID_B, "product_name": "슬라이딩장"}],
        file_items=[[UID_A], [UID_B]])
    _login(client, _user("김재단", part="cut"))
    _finish(client, oid, 0, "cut")
    assert _step(oid, "cut")["done"] is False  # 2장 중 1장
    _login(client, sales)
    resp = client.post(f"/api/orders/{oid}/items/{UID_B}/cancel", json={"reason": "customer_change"})
    assert resp.status_code == 200, resp.get_json()
    assert len(_keys(oid)) == 1
    cut = _step(oid, "cut")
    assert (cut["done"], cut["by_name"]) == (True, "김재단")
    assert _step_events(oid)[-1].payload["trigger"] == "item_cancel_after_confirm"


def test_cancel_transfer_restores_finished_drawings_turns_on(client):
    admin = _user("관리", team="CS", role="ADMIN")
    oid = _order(1)
    old_key = _keys(oid)[0]
    order = db_session.get(Order, oid)
    sd = copy.deepcopy(order.structured_data)
    old_files = list(sd["drawing_current_files"])
    sd["drawing_current_files"] = [{"key": f"orders/{oid}/drawing_wizard/exports/new.png", "filename": "new.png"}]
    sd["drawing_status"] = "TRANSFERRED"
    sd["drawing_transfer_history"] = [{"action": "TRANSFER", "by_user_id": admin.id, "files":
                                       sd["drawing_current_files"], "previous_current_files": old_files}]
    order.structured_data = sd
    db_session.commit()
    _seed_mark(oid, old_key, "cut", "DONE")
    _login(client, admin)
    resp = client.post(f"/api/orders/{oid}/cancel-transfer", json={})
    assert resp.status_code == 200, resp.get_json()
    assert _keys(oid) == [old_key]
    assert _step(oid, "cut")["done"] is True and _step(oid, "cut")["by_name"] == "김재단"
    assert _step_events(oid)[-1].payload["trigger"] == "drawing_transfer_cancel"


# --------------------------------------------------------------------------- #
# 권한 — 파트 계정의 공정 칸 직접 쓰기
# --------------------------------------------------------------------------- #
def test_part_account_cannot_write_order_steps(client):
    oid = _order(1)
    _login(client, _user("김재단", part="cut"))
    resp = client.post(f"/api/orders/{oid}/production/steps", json={"key": "edge", "done": True})
    body = resp.get_json()
    assert resp.status_code == 403 and body["data"]["code"] == "PART_ACCOUNT_USE_CARDS"
    assert body["error"] == "공정은 도면 카드에서 체크해요"
    assert _step(oid, "edge")["done"] is False and _fresh(oid).mutation_version == 1
    got = client.get(f"/api/orders/{oid}/production/steps").get_json()["data"]
    assert got["locked"] is True and got["locked_note"] == "공정은 도면 카드에서 체크해요"


@pytest.mark.parametrize("team,role,part", [("PRODUCTION", "STAFF", None), ("CS", "ADMIN", "cut"),
                                            ("PRODUCTION", "ADMIN", "cut"), ("CS", "STAFF", None)])
def test_control_non_part_accounts_still_write_steps(client, team, role, part):
    oid = _order(1)
    _login(client, _user("대조", team=team, role=role, part=part))
    resp = client.post(f"/api/orders/{oid}/production/steps", json={"key": "edge", "done": True})
    assert resp.status_code == 200, resp.get_json()
    assert _step(oid, "edge")["done"] is True
    assert client.get(f"/api/orders/{oid}/production/steps").get_json()["data"]["locked"] is False


# --------------------------------------------------------------------------- #
# 시트 렌더 — 전체 화면 · 옆 시트
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("url", ["/erp/production/sheet/{oid}", "/erp/production/tablet-sheet/{oid}"])
def test_sheet_step_buttons_read_only_for_part_account(client, url):
    oid = _order(1, steps_done=("cut",))
    _login(client, _user("김재단", part="cut"))
    soup = BeautifulSoup(client.get(url.format(oid=oid)).get_data(as_text=True), "html.parser")
    buttons = soup.select("[data-foms-sheet-step]")
    assert len(buttons) == 4 and all(b.has_attr("disabled") and "is-locked" in b["class"] for b in buttons)
    note = soup.select("[data-foms-sheet-steps-locked]")
    assert len(note) == 1 and note[0].get_text(strip=True) == "공정은 도면 카드에서 체크해요"
    assert soup.select('[data-tablet-sheet-action="production-hold"]')  # 보류 단추는 그대로


@pytest.mark.parametrize("url", ["/erp/production/sheet/{oid}", "/erp/production/tablet-sheet/{oid}"])
@pytest.mark.parametrize("team,role", [("PRODUCTION", "STAFF"), ("CS", "ADMIN")])
def test_control_sheet_step_buttons_unchanged(client, url, team, role):
    oid = _order(1)
    _login(client, _user("대조", team=team, role=role, part="cut" if role == "ADMIN" else None))
    soup = BeautifulSoup(client.get(url.format(oid=oid)).get_data(as_text=True), "html.parser")
    buttons = soup.select("[data-foms-sheet-step]")
    assert len(buttons) == 4 and not any(b.has_attr("disabled") for b in buttons)
    assert not soup.select("[data-foms-sheet-steps-locked]") and "is-locked" not in str(soup)


# --------------------------------------------------------------------------- #
# 칸이 바뀌는 쓰기의 쿼리 수(안 바뀌는 쓰기는 test_production_part_marks_api.py 의 기존 상한 그대로)
# --------------------------------------------------------------------------- #
def _count(fn):
    seen = {"n": 0}

    def _before(conn, cursor, statement, params, context, executemany):
        seen["n"] += 1

    event.listen(engine, "before_cursor_execute", _before)
    try:
        result = fn()
    finally:
        event.remove(engine, "before_cursor_execute", _before)
    return result, seen["n"]


#: 실측(2026-11-13, SQLite 레인): 칸을 켜는 한 장 쓰기 = 15 — 안 바뀌는 쓰기 6 + 동기화 9(주문 다시 잠금 · 공정 이벤트 ·
#: structured_data 저장 훅 3(일정 날짜 · 설정 · 주문 다시 읽기 — 지금 공정 API 도 같다) · 주문 UPDATE · 영수증 · 읽기 자원).
STEP_CHANGE_ONE_CAP = 16
#: 실측: 칸을 켜는 일괄 — 주문 1 = 14, 주문 10 = 23. 주문 잠금 · 주문 UPDATE · 공정 이벤트는 한 번이고, 바뀐 주문마다
#: 영수증 읽기 자원 1줄(엔진 ``execute_order_mutation`` 몫)만 는다 → 차이 ≤ 바뀐 주문 수 - 1 + 2 · 절대 ≤ 26.
STEP_CHANGE_BULK_SLACK = 2
STEP_CHANGE_BULK_ABS_CAP = 26


def test_step_changing_write_query_counts(client):
    _login(client, _user("김재단", part="cut"))
    one = _order(1)
    assert _mark(client, one, 0, "cut", "take", "none").status_code == 200
    resp, n_one = _count(lambda: _mark(client, one, 0, "cut", "done", "need"))
    assert resp.get_json()["data"]["order_step"]["done"] is True and n_one <= STEP_CHANGE_ONE_CAP, n_one

    small, big = [_order(5)], [_order(5) for _ in range(10)]

    def _items(orders):
        return [{"order_id": o, "drawing_key": k} for o in orders for k in _keys(o)]

    items_small, items_big = _items(small), _items(big)
    resp_s, q_small = _count(lambda: client.post(BULK, json={"part": "cut", "seen": "none", "items": items_small}))
    resp_b, q_big = _count(lambda: client.post(BULK, json={"part": "cut", "seen": "none", "items": items_big}))
    assert len(resp_s.get_json()["data"]["order_steps"]) == 1 and len(resp_b.get_json()["data"]["order_steps"]) == 10
    assert q_big - q_small <= 9 + STEP_CHANGE_BULK_SLACK and q_big <= STEP_CHANGE_BULK_ABS_CAP, (q_small, q_big)
