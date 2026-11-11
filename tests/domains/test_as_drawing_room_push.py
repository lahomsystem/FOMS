"""완료 주문 AS 도면 → 채널톡 도면방 [AS] PUSH (설계서 2026-11-11-as-drawing-after-completion D4).

같은 도면방 길(push_kind='drawing_room')에 ``as_drawing: true`` 를 실으면 본문 앞에 [AS], 첨부는 AS 차수
파일(첨부 행 없음 — R2 key), 이력은 ``channeltalk_push_as_drawing_room`` 에 따로 남는다. 원래 도면방 이력은
건드리지 않는다.
"""

from __future__ import annotations

import copy

import foms.api.channel.channel_integration as channel_integration
from db import db_session
from models import Order
from tests.domains.test_as_drawing_round import (  # noqa: F401 - 픽스처도 함께 가져온다
    _as,
    _order,
    _put,
    _reset_cache_runtime,
    _sheet_png,
    _start,
    _user,
    storage,
)


class _FakeStorage:
    def get_download_url(self, storage_key, expires_in=3600, response_content_disposition=None):
        return f"https://cdn.example.com/{storage_key}"


def _capture(monkeypatch):
    monkeypatch.setenv("CHANNEL_GROUP_DRAWING_ROOM", "group-drawing-room")
    monkeypatch.setattr(channel_integration, "is_configured", lambda: True)
    monkeypatch.setattr(channel_integration, "get_storage", lambda: _FakeStorage())
    captured = {"calls": []}

    def _fake_dispatch(event_type, data, raise_on_error=False):
        captured["calls"].append(data)
        return {"success": True, "message_id": f"msg-{len(captured['calls'])}"}

    monkeypatch.setattr(channel_integration, "dispatch_order_event", _fake_dispatch)
    return captured


def _sd(oid):
    db_session.expire_all()
    return copy.deepcopy(db_session.get(Order, oid).structured_data or {})


def _sent_as_drawing(client, oid):
    drafter = _user(f"asr_draw_{oid}")
    order = db_session.get(Order, oid)
    sd = copy.deepcopy(order.structured_data)
    sd["assignments"]["drawing_assignee_user_ids"] = [drafter.id]
    order.structured_data = sd
    db_session.commit()
    _as(client, drafter)
    assert _start(client, oid, memo="오른쪽 문짝", as_register={"content": "문 처짐"}).status_code == 200
    assert _put(client, oid, [{"id": "s-1", "name": "냉장고장", "form": {}, "objects": []},
                              {"id": "s-2", "name": "AS 문짝", "form": {}, "objects": []}]).status_code == 200
    assert _sheet_png(client, oid, "s-2", "as1.png").status_code == 200
    assert client.post(f"/api/orders/{oid}/drawing/as/transfer", json={}).status_code == 200
    return drafter


def _push(client, oid, **extra):
    body = {"order_id": oid, "push_kind": "drawing_room", "as_drawing": True, "allow_without_manager_room": True}
    body.update(extra)
    return client.post("/api/channel/push-manual", json=body)


def test_as_room_push_sends_round_files_with_as_prefix(client, storage, monkeypatch):
    captured = _capture(monkeypatch)
    oid = _order(name="도면방에이에스")
    _sent_as_drawing(client, oid)
    before = _sd(oid)

    res = _push(client, oid)

    assert res.status_code == 200, res.get_json()
    data = captured["calls"][0]
    assert data["text"].startswith("[AS] 도면방에이에스 · AS 도면 1차") and "오른쪽 문짝" in data["text"]
    assert [f["url"].rsplit("/", 1)[-1] for f in data["files"]] == ["as1.png"]
    sd = _sd(oid)
    assert sd["channeltalk_push_as_drawing_room"]["pushed"] is True
    assert sd.get("channeltalk_push_drawing_room") == before.get("channeltalk_push_drawing_room")
    assert sd["drawing_current_files"] == before["drawing_current_files"]


def test_as_room_push_resend_needs_reason(client, storage, monkeypatch):
    _capture(monkeypatch)
    oid = _order(name="도면방재전송")
    _sent_as_drawing(client, oid)
    assert _push(client, oid).status_code == 200

    again = _push(client, oid)
    assert again.status_code == 400 and "재전송" in again.get_json()["message"]
    assert _push(client, oid, change_note="손잡이 위치 고침").status_code == 200


def test_as_room_push_without_as_drawing_is_refused(client, storage, monkeypatch):
    captured = _capture(monkeypatch)
    drafter = _user("asr_draw_none")
    oid = _order(name="도면방없음", drawing_ids=[drafter.id])
    _as(client, drafter)

    res = _push(client, oid)

    assert res.status_code == 400 and "AS 도면" in res.get_json()["message"]
    assert captured["calls"] == []


def test_card_and_wizard_offer_room_push(client, storage, monkeypatch):
    _capture(monkeypatch)
    oid = _order(name="도면방단추")
    _sent_as_drawing(client, oid)

    detail = client.get(f"/erp/drawing-workbench/{oid}").get_data(as_text=True)
    assert 'data-dw-as-act="room"' in detail and "js/drawing/as-room-push.js" in detail
    wizard = client.get(f"/erp/drawing-workbench/{oid}/wizard").get_data(as_text=True)
    assert "js/drawing/as-room-push.js" in wizard
