"""생산 도면 펜 기록 API(``GET · PUT · DELETE /api/production/drawing-notes``) — 설계서 2026-11-28 생산 도면 펜 기록 §8 · §6-5 · §9-3.

문 넷(스위치 꺼짐 404 · 칸 꺼진 반장 403 · 다른 팀 403 · 켠 사람 200) · 버전 견줌 409 · 동시 첫 저장 · 바뀐 도면 409 · 그림 아닌 도면 400 ·
큰 기록 413 · 저장 뒤 첨부 한 줄 + 앞 그림 지운 표시 · 지우기 · 이벤트 payload · 합친 그림(원본 크기 · 흰 바탕 · 빈 칸이 검정 아님).
판 · 시트 · 첨부 목록 읽기와 바뀌기 전 판정은 ``test_production_drawing_notes_read.py``, 쿼리 수는 ``test_production_home_query_count.py``.

되돌리면 실패: 스위치 꺼짐에 저장됨 · 반장이 칸 없이 씀 · 낡은 버전이 덮어씀 · 동시 첫 저장이 500 · 옛 key 에 씀 · PDF 에 씀 ·
301개 · 2,001점 · 400KB 를 받음 · 앞 그림이 남음 · 지운 뒤 그림이 남음 · 이벤트에 기록 원본이 실림 · 투명 칸이 검정.
대조군: 켠 사람 200 · 맞는 버전은 덮어씀 · 같은 주문 다른 장은 그대로 · 읽기는 다른 팀 직원도 됨.
이름은 모두 지어낸 값이다(김재단 · 오재단 · 박반장 · 한검수 · 고객 정하늘).
"""
from __future__ import annotations

import io
import json
import time
from dataclasses import dataclass
from itertools import count

import pytest
from PIL import Image, ImageDraw
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.datetime_kst import get_today_kst
from foms.services.production import drawing_note_write as writer
from foms.services.production import pen_record
from models import DomainSideEffectOutbox, Order, OrderAttachment, OrderEvent, ProductionDrawingNote, SecurityLog, User

URL = "/api/production/drawing-notes"
SWITCH = pen_record.SWITCH_ENV
_seq = count(1)
RED = "#e11d1d"


class FakeStorage:
    """저장소 대역 — 바이트를 사전에 둔다(디스크 · R2 를 건드리지 않는다)."""

    storage_type = "local"

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []

    def read_file_bytes(self, key: str):
        return self.objects.get(key)

    def upload_file(self, file_obj, filename, folder="uploads"):
        key = f"{folder}/{next(_seq):04d}_{filename}"
        file_obj.seek(0)
        self.objects[key] = file_obj.read()
        return {"success": True, "key": key}

    def delete_file(self, key: str) -> bool:
        self.deleted.append(key)
        self.objects.pop(key, None)
        return True


@pytest.fixture(autouse=True)
def _switch_off_by_default(monkeypatch):
    monkeypatch.delenv(SWITCH, raising=False)


@pytest.fixture
def switch_on(monkeypatch):
    monkeypatch.setenv(SWITCH, "on")


@pytest.fixture
def storage(monkeypatch):
    fake = FakeStorage()
    monkeypatch.setattr(writer, "get_storage", lambda: fake)
    return fake


@pytest.fixture
def policy_on(app):
    """이 시험 동안만 정책 가드(매니페스트)를 켠다."""
    sentinel = object()
    prev = app.config.get("AUTH_POLICY_ENABLED", sentinel)
    app.config["AUTH_POLICY_ENABLED"] = True
    yield
    if prev is sentinel:
        app.config.pop("AUTH_POLICY_ENABLED", None)
    else:
        app.config["AUTH_POLICY_ENABLED"] = prev


@dataclass(frozen=True)
class Person:
    id: int
    username: str
    role: str
    name: str


def _person(name: str, *, team: str = "PRODUCTION", role: str = "STAFF", write: bool | None = True,
            first: bool | None = None, lead: bool | None = None) -> Person:
    user = User(username=f"pen_{next(_seq)}", password=generate_password_hash("x"), role=role, team=team, name=name,
                is_active=True, production_lead=lead, production_pen_write=write, production_pen_first=first)
    db_session.add(user)
    db_session.commit()
    return Person(user.id, user.username, user.role, name)


def _login(client, person: Person) -> None:
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = person.id, person.username, person.role


def png(size=(200, 140), *, transparent_left: bool = True, color=(30, 60, 200, 255)) -> bytes:
    """원본 도면 대역 — 왼쪽 반은 투명(합칠 때 검정이 되면 안 되는 칸), 오른쪽 반은 파랑."""
    image = Image.new("RGBA", size, (0, 0, 0, 0) if transparent_left else (255, 255, 255, 255))
    ImageDraw.Draw(image).rectangle([size[0] // 2, 0, size[0], size[1]], fill=color)
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def ink(size=(200, 140)) -> bytes:
    """펜 기록 투명 PNG — 맨 위 한 줄만 빨강."""
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle([0, 0, size[0], max(1, size[1] // 20)], fill=(225, 29, 29, 255))
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def order_with_drawings(storage: FakeStorage | None = None, *, name: str = "정하늘") -> tuple[int, list[str]]:
    """생산 단계 주문 — 그림 도면 둘(시트 신원 있음) + PDF 하나. 원본 바이트는 저장소 대역에."""
    prefix = f"orders/pen{next(_seq)}/drawing"
    files = [{"key": f"{prefix}/a.png", "filename": "a.png", "sheet_id": "sheet-a"},
             {"key": f"{prefix}/b.png", "filename": "b.png", "sheet_id": "sheet-b"},
             {"key": f"{prefix}/plan.pdf", "filename": "plan.pdf"}]
    sd = {"workflow": {"stage": "PRODUCTION"}, "parties": {"customer": {"name": name}}, "drawing_current_files": files}
    order = Order(received_date=get_today_kst().isoformat(), customer_name=name, phone="010-0000-0000", address="가짜시",
                  product="붙박이장", status="PRODUCTION", is_erp_order=True, erp_stage_code="PRODUCTION", structured_data=sd)
    db_session.add(order)
    db_session.commit()
    if storage is not None:
        for f in files[:2]:
            storage.objects[f["key"]] = png()
    return order.id, [f["key"] for f in files]


def pen(points=(10, 10, 60, 40), stroke=RED, width=5, **extra) -> dict:
    return {"type": "pen", "points": list(points), "stroke": stroke, "strokeWidth": width, **extra}


def body(order_id: int, key: str, seen: int = 0, objects=None, **extra) -> dict:
    return {"order_id": order_id, "drawing_key": key, "seen_version": seen,
            "objects": objects if objects is not None else [pen()], "base_w": 1478, "base_h": 1035, **extra}


def put(client, payload: dict, ink_bytes: bytes | None = None):
    data = {"payload": json.dumps(payload)}
    data["ink"] = (io.BytesIO(ink() if ink_bytes is None else ink_bytes), "ink.png")
    return client.put(URL, data=data, content_type="multipart/form-data")


def code(resp) -> str:
    return ((resp.get_json() or {}).get("data") or {}).get("code")


def note_row(order_id: int, key: str):
    db_session.expire_all()
    return db_session.query(ProductionDrawingNote).filter_by(order_id=order_id, drawing_key=key).one_or_none()


def pictures(order_id: int) -> list[OrderAttachment]:
    db_session.expire_all()
    from foms.services.attachment_visibility import include_deleted
    return include_deleted(db_session.query(OrderAttachment).filter_by(order_id=order_id)).order_by(OrderAttachment.id).all()


# --------------------------------------------------------------------------- #
# 문 넷
# --------------------------------------------------------------------------- #
def test_switch_off_makes_all_three_404(client, storage):
    order_id, keys = order_with_drawings(storage)
    _login(client, _person("김재단"))
    assert client.get(f"{URL}?order_id={order_id}&drawing_key={keys[0]}").status_code == 404
    assert put(client, body(order_id, keys[0])).status_code == 404
    assert client.delete(URL, json={"order_id": order_id, "drawing_key": keys[0], "seen_version": 0}).status_code == 404
    assert note_row(order_id, keys[0]) is None and pictures(order_id) == [] and storage.objects.keys() == set(keys[:2])


def test_lead_without_box_and_other_team_get_pen_forbidden(client, storage, switch_on):
    order_id, keys = order_with_drawings(storage)
    for person in (_person("박반장", lead=True, write=None), _person("한검수", team="CS", write=True),
                   _person("정하늘", team="DRAWING", write=True)):
        _login(client, person)
        resp = put(client, body(order_id, keys[0]))
        assert resp.status_code == 403 and code(resp) == "PEN_FORBIDDEN", person.name
        assert resp.get_json() == {"success": False, "data": {"code": "PEN_FORBIDDEN"},
                                   "error": "펜 기록은 정해진 사람만 쓸 수 있어요."}
        gone = client.delete(URL, json={"order_id": order_id, "drawing_key": keys[0], "seen_version": 0})
        assert gone.status_code == 403 and code(gone) == "PEN_FORBIDDEN"
    assert note_row(order_id, keys[0]) is None and pictures(order_id) == []
    _login(client, _person("김재단"))  # 대조군: 켠 사람은 된다
    ok = put(client, body(order_id, keys[0]))
    assert ok.status_code == 200, ok.get_data(as_text=True)[:300]
    assert ok.get_json()["data"]["note"]["version"] == 1


def test_admin_needs_the_box_and_policy_guard_lets_box_holders_through(client, storage, switch_on, policy_on):
    order_id, keys = order_with_drawings(storage)
    _login(client, _person("관리자", role="ADMIN", team="CS", write=None))
    assert code(put(client, body(order_id, keys[0]))) == "PEN_FORBIDDEN"  # 13번 답 "관리자도 칸을 켜야 씀"
    _login(client, _person("한검수", team="CS", write=True))
    guarded = put(client, body(order_id, keys[0]))  # 정책 PRODUCTION_EDIT 가 핸들러 전에 막는다
    assert guarded.status_code == 403 and guarded.headers.get("X-Auth-Policy") == "denied"
    _login(client, _person("관리자둘", role="ADMIN", team="CS", write=True))
    assert put(client, body(order_id, keys[0])).status_code == 200


def test_read_door_is_production_home_viewers(client, storage, switch_on):
    order_id, keys = order_with_drawings(storage)
    _login(client, _person("김재단"))
    assert put(client, body(order_id, keys[0])).status_code == 200
    _login(client, _person("한검수", team="CS", write=None))  # 보기 팀(CS) 직원은 쓰기 칸 없이도 읽는다
    got = client.get(f"{URL}?order_id={order_id}&drawing_key={keys[0]}")
    assert got.status_code == 200 and got.headers["Cache-Control"] == "private, no-store"
    note = got.get_json()["data"]["note"]
    assert note["objects"] == [pen()] and (note["base_w"], note["base_h"], note["version"], note["by"]) == (1478, 1035, 1, "김재단")
    assert note["at"] and set(note) == {"objects", "base_w", "base_h", "version", "by", "at"}
    other = client.get(f"{URL}?order_id={order_id}&drawing_key={keys[1]}")
    assert other.get_json()["data"] == {"note": None}
    _login(client, _person("윤봄", team="NOPE", write=None))  # 생산 첫 화면을 못 보는 팀 글자
    denied = client.get(f"{URL}?order_id={order_id}&drawing_key={keys[0]}")
    assert denied.status_code == 403 and code(denied) == "FORBIDDEN"
    with client.session_transaction() as sess:  # 로그인 없음
        sess.clear()
    assert client.get(f"{URL}?order_id={order_id}&drawing_key={keys[0]}").status_code == 401


# --------------------------------------------------------------------------- #
# 버전 견줌 · 동시 첫 저장
# --------------------------------------------------------------------------- #
def test_stale_version_gets_note_changed_with_last_writer_name(client, storage, switch_on):
    order_id, keys = order_with_drawings(storage)
    _login(client, _person("김재단"))
    assert put(client, body(order_id, keys[0])).status_code == 200
    _login(client, _person("오재단"))
    stale = put(client, body(order_id, keys[0], seen=0, objects=[pen(stroke="#1c62d6")]))
    assert stale.status_code == 409 and stale.get_json()["error"] == "그사이 김재단이 기록을 고쳤어요. 닫고 다시 열어 주세요."
    assert note_row(order_id, keys[0]).objects == [pen()] and len(pictures(order_id)) == 1
    fresh = put(client, body(order_id, keys[0], seen=1, objects=[pen(stroke="#1c62d6")]))
    assert fresh.status_code == 200 and fresh.get_json()["data"]["note"]["version"] == 2
    _login(client, _person("한검수"))
    again = put(client, body(order_id, keys[0], seen=1))
    assert again.get_json()["error"] == "그사이 오재단이 기록을 고쳤어요. 닫고 다시 열어 주세요."  # 이름 = 마지막에 고친 사람
    assert put(client, body(order_id, keys[1], seen=3)).status_code == 409  # 없는 기록인데 본 버전이 있음


def test_concurrent_first_save_is_note_changed_and_drops_the_new_picture(client, storage, switch_on, monkeypatch):
    order_id, keys = order_with_drawings(storage)
    _login(client, _person("김재단"))
    assert put(client, body(order_id, keys[0])).status_code == 200
    stored = set(storage.objects)
    monkeypatch.setattr(writer, "_note_row", lambda db, oid, key: None)  # 잠금 없는 레인 — 버전 견줌 뒤 남이 먼저 넣은 꼴
    _login(client, _person("오재단"))
    lost = put(client, body(order_id, keys[0], seen=0))
    assert lost.status_code == 409 and code(lost) == "NOTE_CHANGED"
    assert lost.get_json()["error"] == "그사이 김재단이 기록을 고쳤어요. 닫고 다시 열어 주세요."
    assert set(storage.objects) == stored and len(storage.deleted) == 1  # 올린 새 그림은 바로 지웠다
    assert len(pictures(order_id)) == 1 and note_row(order_id, keys[0]).version == 1


# --------------------------------------------------------------------------- #
# 도면 · 값 검사
# --------------------------------------------------------------------------- #
def test_replaced_drawing_and_file_drawing_are_refused(client, storage, switch_on):
    order_id, keys = order_with_drawings(storage)
    _login(client, _person("김재단"))
    gone = put(client, body(order_id, "orders/1/drawing/old.png"))
    assert gone.status_code == 409 and code(gone) == "DRAWING_NOT_CURRENT"
    assert gone.get_json()["error"] == "도면이 바뀌었어요. [다시 받기]를 눌러 주세요."
    assert client.get(f"{URL}?order_id={order_id}&drawing_key=orders/1/drawing/old.png").status_code == 409
    pdf = put(client, body(order_id, keys[2]))
    assert pdf.status_code == 400 and pdf.get_json()["error"] == "그림 도면에만 적을 수 있어요."
    assert code(client.get(f"{URL}?order_id={order_id}&drawing_key={keys[2]}")) == "NOT_AN_IMAGE"
    assert put(client, body(999_999, keys[0])).status_code == 404
    assert pictures(order_id) == []


@pytest.mark.parametrize("objects", [
    [pen() for _ in range(writer.MAX_OBJECTS + 1)],                           # 301개
    [pen(points=[1, 2] * (writer.MAX_POINTS + 1))],                            # 한 선 2,001점
    [pen(points=[1234.567, 891.234] * 1000) for _ in range(30)],               # 전체 400KB 넘음(폼 칸 1 MiB 안)
])
def test_too_large_note_is_413(client, storage, switch_on, objects):
    order_id, keys = order_with_drawings(storage)
    _login(client, _person("김재단"))
    resp = put(client, body(order_id, keys[0], objects=objects))
    assert resp.status_code == 413 and code(resp) == "NOTE_TOO_LARGE"
    assert resp.get_json()["error"] == "기록이 너무 많아요. 조금 지우고 다시 저장해 주세요."
    assert note_row(order_id, keys[0]) is None and pictures(order_id) == []


def test_limits_themselves_are_accepted(client, storage, switch_on):
    """대조군: 300개 · 한 선 2,000점은 받는다."""
    order_id, keys = order_with_drawings(storage)
    _login(client, _person("김재단"))
    objects = [pen(points=[1, 2] * writer.MAX_POINTS)] + [pen() for _ in range(writer.MAX_OBJECTS - 1)]
    assert put(client, body(order_id, keys[0], objects=objects)).status_code == 200


@pytest.mark.parametrize("bad", [
    [],                                                                         # 빈 기록(지우기는 DELETE)
    [{"type": "rect", "points": [1, 2, 3, 4]}],                                 # 종류 셋 밖
    [pen(stroke="#00ff00")],                                                    # 색 넷 밖
    [pen(width=7)],                                                             # 굵기 넷 밖
    [pen(stroke="#ffd400", width=5)],                                           # 형광펜은 굵기 24 만
    [pen(stroke="#ffd400", width=24, opacity=0.9)],                             # 형광펜은 0.4 만
    [pen(points=[1, 2, 3])],                                                    # x, y 짝이 안 맞음
    [pen(points=[1, "2"])],                                                     # 숫자 아님
    [{"type": "arrow", "points": [1, 2, 3, 4, 5, 6], "stroke": RED, "strokeWidth": 3}],  # 화살표는 네 값
    [{"type": "text", "x": 1, "y": 2, "text": "가" * 41, "fill": RED, "fontSize": 20}],   # 40자 넘음
    [{"type": "text", "x": 1, "y": 2, "text": "  ", "fill": RED, "fontSize": 20}],       # 빈 글
])
def test_bad_values_are_400(client, storage, switch_on, bad):
    order_id, keys = order_with_drawings(storage)
    _login(client, _person("김재단"))
    resp = put(client, body(order_id, keys[0], objects=bad))
    assert resp.status_code == 400 and resp.get_json()["error"] == "보낸 값이 올바르지 않아요."


def test_bad_body_and_ink_are_400(client, storage, switch_on):
    order_id, keys = order_with_drawings(storage)
    _login(client, _person("김재단"))
    assert code(put(client, body(order_id, keys[0], base_w=0))) == "BAD_REQUEST"
    assert code(put(client, body(order_id, keys[0], seen=-1))) == "BAD_REQUEST"
    assert code(put(client, body(order_id, keys[0]), ink_bytes=b"not-a-png")) == "BAD_REQUEST"
    jpeg = io.BytesIO()
    Image.new("RGB", (20, 20)).save(jpeg, "JPEG")
    assert code(put(client, body(order_id, keys[0]), ink_bytes=jpeg.getvalue())) == "BAD_REQUEST"
    no_payload = client.put(URL, data={"ink": (io.BytesIO(ink()), "ink.png")}, content_type="multipart/form-data")
    assert code(no_payload) == "BAD_REQUEST"
    assert pictures(order_id) == []


def test_kept_fields_only_and_highlighter_shape(client, storage, switch_on):
    order_id, keys = order_with_drawings(storage)
    _login(client, _person("김재단"))
    objects = [pen(stroke="#FFD400", width=24, opacity=0.4, id="x1", tension=0.5),
               {"type": "arrow", "points": [1, 2, 3, 4], "stroke": "#000000", "strokeWidth": 9},
               {"type": "text", "x": 5, "y": 6.5, "text": " 620 깊이 ", "fill": "#1c62d6", "fontSize": 28, "extra": 1}]
    assert put(client, body(order_id, keys[0], objects=objects)).status_code == 200
    assert note_row(order_id, keys[0]).objects == [
        {"type": "pen", "points": [10, 10, 60, 40], "stroke": "#ffd400", "strokeWidth": 24, "opacity": 0.4},
        {"type": "arrow", "points": [1, 2, 3, 4], "stroke": "#000000", "strokeWidth": 9},
        {"type": "text", "x": 5, "y": 6.5, "text": "620 깊이", "fill": "#1c62d6", "fontSize": 28}]


# --------------------------------------------------------------------------- #
# 저장 · 지우기 · 이벤트
# --------------------------------------------------------------------------- #
def test_save_adds_one_production_picture_and_retires_the_previous(client, storage, switch_on):
    order_id, keys = order_with_drawings(storage)
    writer_person = _person("김재단")
    _login(client, writer_person)
    first = put(client, body(order_id, keys[1])).get_json()["data"]["note"]
    [one] = pictures(order_id)
    assert (one.category, one.file_type, one.filename, one.user_id, one.deleted_at) == (
        "production", "image", "도면2_생산기록.png", writer_person.id, None)
    assert one.storage_key.startswith(f"orders/{order_id}/production/") and one.storage_key in storage.objects
    assert first == {"version": 1, "view_url": f"/api/files/view/{one.storage_key}", "by": "김재단", "at": first["at"]}
    one_id = one.id
    second = put(client, body(order_id, keys[1], seen=1, objects=[pen(), pen(stroke="#000000", width=9)]))
    assert second.status_code == 200
    old, new = pictures(order_id)
    assert old.id == one_id and old.deleted_at is not None and old.deleted_by_user_id == writer_person.id
    assert new.deleted_at is None and new.filename == "도면2_생산기록.png"
    row = note_row(order_id, keys[1])
    assert (row.version, row.attachment_id, row.drawing_no, row.sheet_id, row.updated_by_name) == (2, new.id, 2, "sheet-b", "김재단")
    purge = db_session.query(DomainSideEffectOutbox).filter_by(effect_type="STORAGE_DELETE").all()
    assert [p.dedupe_key for p in purge] == [f"attachment:{old.id}:{old.storage_key}"]  # 첨부 삭제와 같은 열쇠 — 복구 API 가 찾는다
    assert purge[0].available_at > purge[0].created_at  # 유예(7일) 뒤
    assert note_row(order_id, keys[0]) is None  # 대조군: 같은 주문 다른 장은 그대로


def test_events_and_audit_carry_no_note_body(client, storage, switch_on):
    order_id, keys = order_with_drawings(storage)
    person = _person("김재단")
    _login(client, person)
    put(client, body(order_id, keys[0], objects=[pen(), pen()]))
    put(client, body(order_id, keys[0], seen=1))
    resp = client.delete(URL, json={"order_id": order_id, "drawing_key": keys[0], "seen_version": 2})
    assert resp.status_code == 200
    db_session.expire_all()
    events = db_session.query(OrderEvent).filter(OrderEvent.order_id == order_id,
                                                 OrderEvent.event_type.like("PRODUCTION_DRAWING_NOTE_%")).order_by(OrderEvent.id).all()
    pics = pictures(order_id)
    assert [(e.event_type, e.payload) for e in events] == [
        ("PRODUCTION_DRAWING_NOTE_SAVED", {"drawing_key": keys[0], "drawing_no": 1, "version": 1, "count": 2, "attachment_id": pics[0].id}),
        ("PRODUCTION_DRAWING_NOTE_SAVED", {"drawing_key": keys[0], "drawing_no": 1, "version": 2, "count": 1, "attachment_id": pics[1].id}),
        ("PRODUCTION_DRAWING_NOTE_DELETED", {"drawing_key": keys[0], "drawing_no": 1, "version": 2, "count": 1,
                                             "attachment_id": pics[1].id}),
    ]
    assert all(e.created_by_user_id == person.id for e in events)
    logs = db_session.query(SecurityLog).filter(SecurityLog.action.like("PRODUCTION_DRAWING_NOTE_%")).order_by(SecurityLog.id).all()
    assert [log.action for log in logs] == ["PRODUCTION_DRAWING_NOTE_SAVED"] * 2 + ["PRODUCTION_DRAWING_NOTE_DELETED"]
    assert "생산 기록 저장" in logs[0].message and "생산 기록 지움" in logs[2].message
    assert all("objects" not in (log.detail or {}) for log in logs)


def test_delete_removes_row_and_picture(client, storage, switch_on):
    order_id, keys = order_with_drawings(storage)
    _login(client, _person("김재단"))
    put(client, body(order_id, keys[0]))
    stale = client.delete(URL, json={"order_id": order_id, "drawing_key": keys[0], "seen_version": 0})
    assert stale.status_code == 409 and code(stale) == "NOTE_CHANGED"
    done = client.delete(URL, json={"order_id": order_id, "drawing_key": keys[0], "seen_version": 1})
    assert done.status_code == 200 and done.get_json() == {"success": True, "data": {"note": None}, "error": None}
    assert note_row(order_id, keys[0]) is None
    [picture] = pictures(order_id)
    assert picture.deleted_at is not None  # 15번 답 "그림도 지움" — 파일은 유예 뒤 지우기 예약
    assert db_session.query(DomainSideEffectOutbox).filter_by(dedupe_key=f"attachment:{picture.id}:{picture.storage_key}").count() == 1
    again = client.delete(URL, json={"order_id": order_id, "drawing_key": keys[0], "seen_version": 0})
    assert again.status_code == 200  # 지울 것이 없고 본 버전 0 — 할 일 없음
    assert db_session.query(OrderEvent).filter_by(order_id=order_id, event_type="PRODUCTION_DRAWING_NOTE_DELETED").count() == 1
    assert client.get(f"{URL}?order_id={order_id}&drawing_key={keys[0]}").get_json()["data"] == {"note": None}


# --------------------------------------------------------------------------- #
# 합친 그림(§3-3)
# --------------------------------------------------------------------------- #
def test_composed_picture_is_original_size_on_white(client, storage, switch_on):
    order_id, keys = order_with_drawings(storage)
    _login(client, _person("김재단"))
    assert put(client, body(order_id, keys[0]), ink_bytes=ink((100, 70))).status_code == 200  # 펜 기록이 반 크기여도
    [picture] = pictures(order_id)
    with Image.open(io.BytesIO(storage.objects[picture.storage_key])) as out:
        assert out.format == "PNG" and out.size == (200, 140) and out.mode == "RGB"
        assert out.getpixel((40, 100)) == (255, 255, 255)  # 원본 투명 칸 · 기록 없음 = 흰색(검정 아님)
        assert out.getpixel((150, 100)) == (30, 60, 200)  # 원본 파랑 그대로
        assert out.getpixel((40, 2)) == (225, 29, 29)  # 펜 기록(원본 크기로 늘렸다)


def test_compose_highlighter_blends_and_large_drawing_time():
    """형광펜(투명 0.4)은 원본이 비친다. 큰 원본(2,956×2,080) 합치기 시간을 잰다(설계서 §11)."""
    layer = Image.new("RGBA", (200, 140), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rectangle([0, 0, 200, 140], fill=(255, 212, 0, 102))
    buf = io.BytesIO()
    layer.save(buf, "PNG")
    with Image.open(io.BytesIO(writer.compose_note_png(png(transparent_left=False), buf.getvalue()))) as out:
        r, g, b = out.getpixel((150, 100))
        assert 30 < r < 255 and 60 < g < 212 and 0 < b < 200  # 파랑과 노랑이 섞임
    big = Image.new("RGBA", (2956, 2080), (0, 0, 0, 0))
    draw = ImageDraw.Draw(big)
    for x in range(0, 2956, 40):
        draw.line([(x, 0), (x, 2079)], fill=(20, 20, 20, 255), width=3)
    raw = io.BytesIO()
    big.save(raw, "PNG")
    pen_layer = Image.new("RGBA", (2956, 2080), (0, 0, 0, 0))
    ImageDraw.Draw(pen_layer).line([(10, 10), (2900, 2000)], fill=(225, 29, 29, 255), width=9)
    pen_png = io.BytesIO()
    pen_layer.save(pen_png, "PNG")
    started = time.perf_counter()
    result = writer.compose_note_png(raw.getvalue(), pen_png.getvalue())
    seconds = time.perf_counter() - started
    print(f"[pen-compose] 2956x2080 compose {seconds:.2f}s, out {len(result) // 1024}KB")
    with Image.open(io.BytesIO(result)) as out:
        assert out.size == (2956, 2080)
    assert seconds < 20
