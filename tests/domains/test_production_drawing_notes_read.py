"""생산 도면 펜 기록 읽기 — 판 카드 ``note`` · ``note_old`` · 판 설정 ``pen`` · 작업 시트 · 주문 첨부 목록 '생산 · 바뀌기 전'
(설계서 2026-11-28 생산 도면 펜 기록 §3-4 · §5-3 · §8 '쿼리' · §9-5 약속 1 ~ 3 · 5).

되돌리면 실패: 꺼짐인데 기록 표를 읽음 · 꺼짐인데 판 설정에 ``pen`` 이 생김 · 바뀌기 전 기록을 못 찾음 · 다른 시트의 옛 기록을 바뀌기 전으로 봄 ·
먼저 보기를 켠 사람에게 원본을 줌 · '생산' 그림이 없는데도 기록 표를 읽음 · 지금 기록 그림을 '바뀌기 전'으로 적음.
대조군: 다른 시트 · 시트 없는 장의 다른 번호는 ``note_old`` 거짓 · 먼저 보기를 안 켠 사람은 원본 · 인쇄는 기록을 안 실음.
이름은 모두 지어낸 값이다(김재단 · 박반장 · 한검수 · 고객 정하늘 · 윤봄).
"""
from __future__ import annotations

import datetime
from itertools import count

import pytest
from sqlalchemy import event
from werkzeug.security import generate_password_hash

from db import db_session, engine
from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.production import pen_record
from foms.services.production.drawing_notes_read import note_at, pen_config
from foms.services.production.part_board import build_part_board
from foms.services.production_home_days import production_home_days
from foms.services.production_home_read_model import build_production_home
from foms.services.production_sheet_view import build_production_sheet_view
from models import Order, OrderAttachment, ProductionDrawingNote, User

SWITCH = pen_record.SWITCH_ENV
_seq = count(1)


@pytest.fixture(autouse=True)
def _switch_off_by_default(monkeypatch):
    monkeypatch.delenv(SWITCH, raising=False)


def _user(name: str, *, team: str = "PRODUCTION", role: str = "STAFF", write: bool | None = None,
          first: bool | None = None) -> User:
    user = User(username=f"pr_{next(_seq)}", password=generate_password_hash("x"), role=role, team=team, name=name,
                is_active=True, production_pen_write=write, production_pen_first=first)
    db_session.add(user)
    db_session.commit()
    return user


def _order(name: str, files: list[dict]) -> Order:
    when = (get_today_kst() + datetime.timedelta(days=1)).isoformat()
    sd = {"workflow": {"stage": "PRODUCTION"}, "parties": {"customer": {"name": name}}, "schedule": {"construction": {"date": when}},
          "items": [{"product_name": "거실장", "spec_width": "3100"}], "drawing_current_files": files}
    order = Order(received_date=when, customer_name=name, phone="010-0000-0000", address="가짜시", product="거실장",
                  status="PRODUCTION", is_erp_order=True, erp_stage_code="PRODUCTION", erp_construction_date=when, structured_data=sd)
    db_session.add(order)
    db_session.commit()
    return order


def _picture(order: Order, key: str, *, deleted: bool = False) -> OrderAttachment:
    att = OrderAttachment(order_id=order.id, filename="도면1_생산기록.png", file_type="image", category="production", file_size=10,
                          storage_key=key, deleted_at=now_utc_naive() if deleted else None)
    db_session.add(att)
    db_session.commit()
    return att


def _note(order: Order, key: str, *, sheet: str | None, no: int, attachment: OrderAttachment | None = None,
          version: int = 1, by: str = "김재단") -> None:
    db_session.add(ProductionDrawingNote(order_id=order.id, drawing_key=key, sheet_id=sheet, drawing_no=no, objects=[{"type": "pen"}],
                                         base_w=1478, base_h=1040, version=version, updated_by_name=by,
                                         attachment_id=attachment.id if attachment else None,
                                         updated_at=datetime.datetime(2026, 11, 27, 7, 40)))
    db_session.commit()


def _world():
    """주문 하나: 지금 장 A(시트 s-a · 기록 있음) · B(시트 s-b · 옛 key 에 기록 = 바뀌기 전) · C(시트 없음 · 옛 3번 장 기록).
    대조군 주문: D(시트 s-d) 옆에 다른 시트(s-x)의 옛 1번 기록 — 바뀌기 전이 아니다."""
    files = [{"key": "orders/7/drawing/a2.png", "filename": "a2.png", "sheet_id": "s-a"},
             {"key": "orders/7/drawing/b2.png", "filename": "b2.png", "sheet_id": "s-b"},
             {"key": "orders/7/drawing/c2.png", "filename": "c2.png"}]
    order = _order("정하늘", files)
    current = _picture(order, f"orders/{order.id}/production/a_now.png")
    old_b = _picture(order, f"orders/{order.id}/production/b_old.png")
    _note(order, files[0]["key"], sheet="s-a", no=1, attachment=current, version=3)
    _note(order, "orders/7/drawing/b1.png", sheet="s-b", no=2, attachment=old_b)
    _note(order, "orders/7/drawing/c1.png", sheet=None, no=3)
    other = _order("윤봄", [{"key": "orders/8/drawing/d2.png", "filename": "d2.png", "sheet_id": "s-d"}])
    _note(other, "orders/8/drawing/d1.png", sheet="s-x", no=1)
    return order, other, current, old_b


def _cards(user: User) -> dict[str, dict]:
    rows, stats = build_production_home(db_session, user)
    days = production_home_days(rows, get_today_kst(), None, past_hidden=stats["past_hidden"])
    board = build_part_board(db_session, user, days)
    pane = board["panes"][(get_today_kst() + datetime.timedelta(days=1)).isoformat()]
    return {c["key"]: c for c in pane["cards"]}


def _counting(fn):
    seen = {"notes": 0}

    def _before(conn, cursor, statement, params, context, executemany):
        seen["notes"] += "production_drawing_notes" in statement

    event.listen(engine, "before_cursor_execute", _before)
    try:
        return fn(), seen["notes"]
    finally:
        event.remove(engine, "before_cursor_execute", _before)


# --------------------------------------------------------------------------- #
# 판 카드(약속 1)
# --------------------------------------------------------------------------- #
def test_board_cards_carry_note_and_old_twin(app, monkeypatch):
    order, _other, current, _old = _world()
    admin = _user("관리자", role="ADMIN", team="CS")
    off, reads_off = _counting(lambda: _cards(admin))
    assert reads_off == 0  # 꺼짐 = 기록 표를 읽지 않는다
    assert all(c["note"] is None and c["note_old"] is False for c in off.values())
    monkeypatch.setenv(SWITCH, "on")
    cards, reads_on = _counting(lambda: _cards(admin))
    assert reads_on == 1  # 켬 = 판 한 번에 한 번
    a, b, c, d = (cards[k] for k in ("orders/7/drawing/a2.png", "orders/7/drawing/b2.png", "orders/7/drawing/c2.png",
                                      "orders/8/drawing/d2.png"))
    assert a["note"] == {"version": 3, "by": "김재단", "at": "11/27 16:40", "view_url": f"/api/files/view/{current.storage_key}"}
    assert a["note_old"] is False
    assert (b["note"], b["note_old"]) == (None, True)  # 같은 시트(s-b)의 옛 key 기록
    assert (c["note"], c["note_old"]) == (None, True)  # 시트 없는 장 = 같은 번호(3)
    assert (d["note"], d["note_old"]) == (None, False)  # 대조군: 다른 시트(s-x)의 옛 1번 기록은 아니다


def test_note_without_live_picture_keeps_note_with_empty_url(app, monkeypatch):
    monkeypatch.setenv(SWITCH, "on")
    order = _order("정하늘", [{"key": "orders/9/drawing/a.png", "filename": "a.png", "sheet_id": "s1"}])
    gone = _picture(order, f"orders/{order.id}/production/gone.png", deleted=True)  # 첨부 탭에서 그림만 지움
    _note(order, "orders/9/drawing/a.png", sheet="s1", no=1, attachment=gone)
    card = _cards(_user("관리자", role="ADMIN", team="CS"))["orders/9/drawing/a.png"]
    assert card["note"]["version"] == 1 and card["note"]["view_url"] == ""


def test_pen_config_only_when_switch_on(app, monkeypatch):
    writer, reader = _user("김재단", write=True), _user("한검수", team="CS", first=True)
    lead_first = _user("박반장", write=True, first=True)
    assert pen_config(writer) == {} and pen_config(lead_first) == {}  # 꺼짐 = 키 자체가 없다
    monkeypatch.setenv(SWITCH, "on")
    assert pen_config(writer) == {"pen": {"on": True, "can_write": True, "first": False}}
    assert pen_config(reader) == {"pen": {"on": True, "can_write": False, "first": False}}  # 다른 팀은 칸이 있어도 아님
    assert pen_config(lead_first) == {"pen": {"on": True, "can_write": True, "first": True}}


def test_note_at_is_kst_minutes():
    assert note_at(datetime.datetime(2026, 11, 27, 7, 40)) == "11/27 16:40"
    assert note_at(datetime.datetime(2026, 1, 4, 15, 5)) == "1/5 00:05"
    assert note_at(None) == ""


# --------------------------------------------------------------------------- #
# 작업 시트(약속 3)
# --------------------------------------------------------------------------- #
def test_sheet_items_get_note_and_first_viewer_gets_composed_picture(app, monkeypatch):
    order, _other, current, _old = _world()
    first, plain = _user("박반장", first=True), _user("김재단")
    original = "/api/files/view/orders/7/drawing/a2.png"
    sheet_off, reads = _counting(lambda: build_production_sheet_view(db_session, order, first, full=True, notes=True))
    assert reads == 0 and [f["note"] for f in sheet_off["drawing_files"]] == [None, None, None]
    assert sheet_off["drawing_files"][0]["view"] == original
    monkeypatch.setenv(SWITCH, "on")
    sheet, reads = _counting(lambda: build_production_sheet_view(db_session, order, first, full=True, notes=True))
    assert reads == 1
    a, b, _c = sheet["drawing_files"]
    assert a["note"]["view_url"] == f"/api/files/view/{current.storage_key}" and a["view"] == a["note"]["view_url"]
    assert a["thumb"] != a["view"] and b["note"] is None  # 작은 그림은 원본(1차 — 딱지만), 기록 없는 장은 원본
    other = build_production_sheet_view(db_session, order, plain, full=True, notes=True)["drawing_files"][0]
    assert other["note"]["version"] == 3 and other["view"] == original  # 대조군: 먼저 보기를 안 켠 사람은 원본
    printed, reads = _counting(lambda: build_production_sheet_view(db_session, order, first, full=True))
    assert reads == 0 and "note" not in printed["drawing_files"][0]  # 인쇄는 기록을 안 싣는다


def test_sheet_page_shows_composed_picture_first_for_first_viewer(app, client, monkeypatch):
    monkeypatch.setenv(SWITCH, "on")
    order, _other, current, _old = _world()
    order_id, composed = order.id, f"/api/files/view/{current.storage_key}"
    viewer = _user("박반장", first=True)
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = viewer.id, viewer.username, viewer.role
    html = client.get(f"/erp/production/sheet/{order_id}").get_data(as_text=True)
    assert f'data-foms-sheet-dwg-main src="{composed}"' in html


# --------------------------------------------------------------------------- #
# 주문 첨부 목록 '생산 · 바뀌기 전'(§5-3)
# --------------------------------------------------------------------------- #
def _attachments(client, order_id: int):
    return _counting(lambda: client.get(f"/api/orders/{order_id}/attachments"))


def test_attachment_list_marks_old_production_pictures(app, client, monkeypatch):
    order, other, current, old_b = _world()
    order_id, other_id, current_id, old_id = order.id, other.id, current.id, old_b.id
    admin = _user("관리자", role="ADMIN", team="CS")
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = admin.id, admin.username, admin.role
    resp, reads = _attachments(client, order_id)
    items = {i["id"]: i for i in resp.get_json()["attachments"]}
    assert reads == 0 and all("production_old" not in i for i in items.values())  # 꺼짐 = 지금 그대로
    monkeypatch.setenv(SWITCH, "on")
    resp, reads = _attachments(client, order_id)
    items = {i["id"]: i for i in resp.get_json()["attachments"]}
    assert reads == 1
    assert (items[old_id]["production_old"], items[old_id]["production_label"]) == (True, "생산 · 바뀌기 전")
    assert "production_old" not in items[current_id]  # 지금 기록의 그림은 그냥 '생산'
    _resp, reads = _attachments(client, other_id)  # '생산' 그림이 없는 주문 — 기록 표를 읽지 않는다
    assert reads == 0
