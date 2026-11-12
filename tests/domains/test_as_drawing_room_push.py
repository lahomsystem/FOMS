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


def test_as_dashboard_blueprint_cell_shows_round_status(client, storage, monkeypatch):
    """AS 화면 'AS도면' 칸 아래 짧은 글(설계서 §4.3-5) — 체크 칸 뜻은 그대로, 상태 글과 주문 화면 링크만."""
    admin = _user("asr_admin_dash", role="ADMIN", team="CS")
    drafter = _user("asr_draw_dash")
    oid = _order(name="에이에스화면고객", drawing_ids=[drafter.id])
    _as(client, admin)
    assert client.post(f"/api/orders/{oid}/as/register",
                       json={"as_content": "문 처짐", "drawing_request": {"memo": "문짝"}}).status_code == 200

    html = client.get("/erp/as?tab=incomplete", headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/130"}).get_data(as_text=True)

    assert 'title="AS 도면 1차 · 도면팀 대기중"' in html and f'href="/edit/{oid}"' in html
    # 칸 폭이 54px 이라 짧은 낱말만, 낱말마다 줄바꿈 없이(옆 칸으로 넘치던 것 — 스테이징 실화면 11-12).
    assert '<span class="text-nowrap">1차</span> <span class="text-nowrap">대기중</span>' in html


def _upload(client, oid, as_log_id):
    import io as _io

    data = {"file": (_io.BytesIO(b"\x89PNG\r\n\x1a\nFAKE"), "photo.png"), "category": "as"}
    if as_log_id:
        data["as_log_id"] = as_log_id
    return client.post(f"/api/orders/{oid}/attachments", data=data, content_type="multipart/form-data")


def test_drawing_starter_may_upload_as_photo_only_from_start_window(client, monkeypatch):
    """사용자 결정 2026-11-11 "AS 도면 시작 창에서만" — 그 밖의 도면팀 AS 사진은 지금처럼 403."""
    import foms.api.files.order_routes as order_routes

    class _S:
        def upload_file(self, f, name, folder):
            return {"success": True, "key": f"{folder}/{name}"}

        def get_file_type(self, name):
            return "image"

    monkeypatch.setattr(order_routes, "get_storage", lambda: _S())
    starter = _user("asr_photo_starter")
    other = _user("asr_photo_other")
    oid = _order(name="사진시작고객")
    plain = _order(name="사진다른고객")
    _as(client, starter)
    res = _start(client, oid, memo="m", as_register={"content": "문 처짐"})
    log_id = res.get_json()["data"]["reception_log_id"]
    assert log_id

    assert _upload(client, oid, log_id).status_code == 200      # 본인이 접수까지 하고 연 차수
    assert _upload(client, oid, "").status_code == 403          # 접수 기록에 안 묶으면 막힘
    assert _upload(client, plain, log_id).status_code == 403    # 차수 없는 다른 주문
    _as(client, other)
    assert _upload(client, oid, log_id).status_code == 403      # 시작한 사람이 아닌 도면팀


def test_customer_share_link_never_shows_as_drawing(client, storage, monkeypatch):
    """고객 공유 링크는 원래 최종 도면만 보인다(설계서 §8) — AS 차수 파일은 첨부 행도 현재본도 아니다."""
    import foms.api.share as share_routes
    from foms.services import order_share as osvc

    _capture(monkeypatch)
    oid = _order(name="공유링크고객")
    _sent_as_drawing(client, oid)
    sd = _sd(oid)
    as_keys = {f["key"] for rnd in sd["as_drawing"]["rounds"] for f in (rnd.get("files") or [])}
    assert as_keys and all(k.endswith("as1.png") for k in as_keys)

    collected = {f["key"] for f in share_routes._collect_drawing_files(db_session.get(Order, oid))}
    assert collected == {f["key"] for f in sd["drawing_current_files"]}
    assert collected.isdisjoint(as_keys)

    class _R2(_FakeStorage):
        storage_type = "r2"

        def get_download_url(self, storage_key, expires_in=3600, response_content_disposition=None):
            return f"https://cdn.example.com/{storage_key}"

    monkeypatch.setattr(share_routes, "get_storage", lambda: _R2())
    _row, token = osvc.create_share_token(db_session, oid, "drawing")
    db_session.commit()
    res = client.get(f"/s/{token}")
    assert res.status_code == 200
    body = res.get_data(as_text=True)
    assert "as1.png" not in body
    assert all(f["filename"] in body for f in sd["drawing_current_files"])


# --------------------------------------------------------------------------
# 폰 알림(2026-11-12) — 원래 도면 규칙: 부탁 · 도착 · 수정 요청은 폰에도, 접수 · 확인은 벨만
# --------------------------------------------------------------------------

def test_phone_push_only_for_request_transfer_revision(client, storage, monkeypatch):
    import foms.services.orders.as_drawing_notify as notify_mod
    from models import Notification

    pushed: list = []
    monkeypatch.setattr(notify_mod, "enqueue_push_for_notification",
                        lambda nid, db=None: pushed.append(db_session.get(Notification, nid).notification_type))
    drafter = _user("asr_push_draw")
    sales = _user("asr_push_sales", team="SALES")
    admin = _user("asr_push_admin", role="ADMIN", team="CS")
    oid = _order(name="폰알림고객", drawing_ids=[drafter.id])

    _as(client, admin)   # 흐름 1: AS 담당이 도면팀에 부탁 → 도면 담당 폰
    assert client.post(f"/api/orders/{oid}/as/register",
                       json={"as_content": "문 처짐", "drawing_request": {"memo": "문짝"}}).status_code == 200
    assert pushed == ["AS_DRAWING_REQUEST"]

    _as(client, drafter)
    assert _put(client, oid, [{"id": "s-1", "name": "냉장고장", "form": {}, "objects": []},
                              {"id": "s-2", "name": "AS 문짝", "form": {}, "objects": []}]).status_code == 200
    assert _sheet_png(client, oid, "s-2", "as1.png").status_code == 200
    pushed.clear()
    assert client.post(f"/api/orders/{oid}/drawing/as/transfer", json={}).status_code == 200
    assert pushed and set(pushed) == {"AS_DRAWING_TRANSFERRED"}

    _as(client, sales)
    pushed.clear()
    assert client.post(f"/api/orders/{oid}/drawing/as/request-revision",
                       json={"reason": "손잡이"}).status_code == 200
    assert pushed and set(pushed) == {"AS_DRAWING_REVISION"}

    _as(client, drafter)
    assert _sheet_png(client, oid, "s-2", "as2.png").status_code == 200
    assert client.post(f"/api/orders/{oid}/drawing/as/transfer", json={}).status_code == 200
    _as(client, sales)
    pushed.clear()
    assert client.post(f"/api/orders/{oid}/drawing/as/confirm").status_code == 200
    assert pushed == []   # 확인은 벨만
    kinds = {n.notification_type for n in db_session.query(Notification).filter_by(order_id=oid)}
    assert "AS_DRAWING" in kinds   # 확인 알림(벨)은 그대로 만든다


def test_flow2_registration_notice_stays_bell_only(client, storage, monkeypatch):
    import foms.services.orders.as_drawing_notify as notify_mod

    pushed: list = []
    monkeypatch.setattr(notify_mod, "enqueue_push_for_notification", lambda nid, db=None: pushed.append(nid))
    drafter = _user("asr_push_draw2")
    oid = _order(name="폰알림흐름2")
    _as(client, drafter)
    assert _start(client, oid, memo="m", as_register={"content": "문 처짐"}).status_code == 200
    assert pushed == []   # CS 팀 전체에 가는 접수 알림은 폰으로 보내지 않는다


def test_push_sender_knows_as_drawing_types():
    from types import SimpleNamespace

    from foms.services.notifications import push_sender as ps

    for ntype, link in (("AS_DRAWING_REQUEST", "/erp/drawing-workbench/7"),
                        ("AS_DRAWING_REVISION", "/erp/drawing-workbench/7"),
                        ("AS_DRAWING_TRANSFERRED", "/erp/orders/7")):
        notif = SimpleNamespace(notification_type=ntype, is_urgent=False, order_id=7, message="")
        assert ps._should_push(notif), ntype
        assert ps._urgency(notif) == "high", ntype
        assert ps._deep_link(notif) == link, ntype
        title, body = ps._order_bound_text(False, ntype, 7, "이영광")
        assert title.startswith("AS 도면") and "이영광" in title and "주문 #7" in body
    bell = SimpleNamespace(notification_type="AS_DRAWING", is_urgent=False, order_id=7, message="")
    assert not ps._should_push(bell)


def test_bell_click_opens_workbench_for_drawing_team_as_notices():
    from types import SimpleNamespace

    from foms.api.notifications import _resolve_notification_deep_link as deep

    for ntype in ("AS_DRAWING_REQUEST", "AS_DRAWING_REVISION"):
        link = deep(SimpleNamespace(notification_type=ntype, order_id=9), {})
        assert link["deep_link_url"] == "/erp/drawing-workbench/9", ntype
    assert deep(SimpleNamespace(notification_type="AS_DRAWING_TRANSFERRED", order_id=9), {})["deep_link_url"] is None
