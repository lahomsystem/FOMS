"""PARTNER-AS-02: 협력사 AS 접수 · 고치기 · 파일 · AS방 PUSH(설계서 docs/specs/2026-11-13-partner-as-intake-edit-push_SPEC.md).

허용 경로마다 거부 대조군(열린 건 없음 · 바뀐 내용 없음 · 다른 접수 줄 · 다른 회사 · 시공 전 단계)을 같이 둔다.
AS방 전송은 가짜 :func:`run_manual_push` 로 받은 값만 본다(실제 채널톡에 보내지 않는다).
"""
from __future__ import annotations

import copy
import datetime
import io
from types import SimpleNamespace

import pytest
from sqlalchemy.orm.attributes import flag_modified

import foms.api.partner.as_intake as partner_as_api
from db import db_session
from foms.services.partners import as_intake as svc
from models import Notification, Order, OrderAttachment, OrderFieldChange, SecurityLog, User
from tests.security.partner_fixtures import (  # noqa: F401 — pytest fixture 재노출
    _client,
    _create,
    _to_stage,
    fake_storage,
    world,
)


@pytest.fixture
def pushes(monkeypatch):
    """본사 AS PUSH 대신 받은 값을 모은다 — 성공하면 본사처럼 이력 칸(channeltalk_push_as)을 남긴다."""
    sent: list[dict] = []

    def _fake(db, payload, actor, *, pushed_by_name=None):
        sent.append({**payload, "pushed_by_name": pushed_by_name})
        order = db.get(Order, payload["order_id"])
        sd = copy.deepcopy(order.structured_data)
        ids = payload.get("attachment_ids") or []
        sd["channeltalk_push_as"] = {"pushed": True, "sent_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                     "max_attachment_id": max(ids + [int((sd.get("channeltalk_push_as") or {}).get("max_attachment_id") or 0)])}
        order.structured_data = sd
        flag_modified(order, "structured_data")
        db.commit()
        return {"success": True}, 200

    monkeypatch.setattr(partner_as_api, "run_manual_push", _fake)
    return sent


def _completed_order(app, world) -> tuple[int, object]:
    order_id = _create(app, world["partner_a"]).get_json()["data"]["order_id"]
    _to_stage(order_id, "COMPLETED")
    return order_id, _client(app, db_session.get(User, world["partner_a"]))


def _sd(order_id) -> dict:
    db_session.expire_all()
    return db_session.get(Order, order_id).structured_data


def _receptions(order_id) -> list[dict]:
    sd = _sd(order_id)
    cycle_id = sd["as_lifecycle"]["current_cycle_id"]
    return [e for e in sd["shipment"]["as_log"] if e.get("type") == "reception" and e.get("cycle_id") == cycle_id]


def _file(name: str, data: bytes = b"img"):
    return {"file": (io.BytesIO(data), name)}


# ── 접수: 본사 정본 그대로 ────────────────────────────────────────────────────


def test_register_runs_hq_core_with_partner_tail(app, world, fake_storage, pushes):
    order_id, client = _completed_order(app, world)
    resp = client.post(f"/api/partner/orders/{order_id}/as", data={"content": "문짝 처짐"})
    body = resp.get_json()
    assert resp.status_code == 200 and body["data"]["push_sent"] is True, body
    sd = _sd(order_id)
    assert len(sd["as_lifecycle"]["cycles"]) == 1
    [reception] = _receptions(order_id)
    assert reception["text"] == "문짝 처짐" and reception["by"].endswith("(협력사)")
    assert any(e.get("type") == "system" and e.get("text") == "AS 접수됨 (협력사)" for e in sd["shipment"]["as_log"])
    assert sd["shipment"]["as_billing"]["type"] == "undecided"  # 비용은 우리 몫(협력사 접수는 늘 미정)
    # 본사 접수 정본의 부수 기록 — 변경 원장(1판에는 없었다) · 협력사 감사 · CS 벨.
    assert db_session.query(OrderFieldChange).filter(OrderFieldChange.order_id == order_id).count() >= 1
    assert db_session.query(SecurityLog).filter(SecurityLog.action == "PARTNER_AS_REGISTERED",
                                                SecurityLog.target_id == order_id).count() == 1
    assert db_session.query(Notification).filter(Notification.order_id == order_id,
                                                 Notification.notification_type == "PARTNER_AS_REGISTERED").count() == 1
    [push] = pushes
    assert push["push_kind"] == "as" and push["text"] == "" and push["change_note"] == ""  # 글은 서버(본사 AS PUSH)가 만든다
    assert push["attachment_ids"] == [] and push["pushed_by_name"].endswith("(협력사)")


def test_register_refused_before_construction_and_while_open(app, world, pushes):
    order_id = _create(app, world["partner_a"]).get_json()["data"]["order_id"]
    client = _client(app, db_session.get(User, world["partner_a"]))
    assert client.post(f"/api/partner/orders/{order_id}/as", data={"content": "x"}).status_code == 409  # 시공 전
    _to_stage(order_id, "COMPLETED")
    assert client.post(f"/api/partner/orders/{order_id}/as", data={"content": "x"}).status_code == 200
    again = client.post(f"/api/partner/orders/{order_id}/as", data={"content": "또"})
    assert again.status_code == 409 and "AS 접수 수정" in again.get_json()["error"]  # 열린 건은 고치기 길로


def test_push_failure_keeps_registration(app, world, monkeypatch):
    order_id, client = _completed_order(app, world)
    monkeypatch.setattr(partner_as_api, "run_manual_push", lambda *a, **k: ({"success": False, "message": "x"}, 503))
    body = client.post(f"/api/partner/orders/{order_id}/as", data={"content": "문짝 처짐"}).get_json()
    assert body["success"] is True and body["data"]["push_sent"] is False
    assert _sd(order_id)["as_lifecycle"]["cycles"]  # 접수는 남는다
    form = client.get(f"/api/partner/orders/{order_id}/as").get_json()["data"]
    assert form["mode"] == "edit" and form["push"]["needs_push"] is True  # 화면이 [AS방 다시 보내기]를 보인다


# ── 고치기: 같은 건 갱신 ─────────────────────────────────────────────────────


def test_edit_updates_same_cycle_and_carries_photos(app, world, fake_storage, pushes):
    order_id, client = _completed_order(app, world)
    photo = OrderAttachment(order_id=order_id, filename="done.jpg", file_type="image", category="construction",
                            file_size=10, storage_key=f"orders/{order_id}/construction/done.jpg")
    db_session.add(photo)
    db_session.commit()
    photo_id = photo.id
    first = client.post(f"/api/partner/orders/{order_id}/as", content_type="multipart/form-data",
                        data={"content": "문 2짝 처짐", "construction_photo_ids": str(photo_id),
                              "photos": (io.BytesIO(b"img"), "before.jpg")}).get_json()["data"]
    edit = client.post(f"/api/partner/orders/{order_id}/as/edit",
                       data={"content": "문 3짝 처짐", "change_note": "문 2짝 → 3짝"}).get_json()
    assert edit["success"] is True, edit
    sd = _sd(order_id)
    assert len(sd["as_lifecycle"]["cycles"]) == 1  # AS 건 수 그대로
    receptions = _receptions(order_id)
    assert [r["text"].split("\n")[0] for r in receptions] == ["문 2짝 처짐", "문 3짝 처짐"]
    assert receptions[-1]["ref_attachment_ids"] == [photo_id] and "[완공 사진 참고] done.jpg" in receptions[-1]["text"]
    assert any(e.get("text") == "AS 접수 수정됨 (협력사)" for e in sd["shipment"]["as_log"])
    moved = db_session.query(OrderAttachment).filter(OrderAttachment.order_id == order_id,
                                                     OrderAttachment.category == "as").one()
    assert moved.as_log_id == receptions[-1]["id"] != first["reception_log_id"]  # 앞 접수 사진이 새 접수 줄로
    assert pushes[-1]["change_note"] == "문 2짝 → 3짝"
    assert pushes[-1]["attachment_ids"] == []  # 이미 보낸 사진은 다시 안 보낸다
    # 고치기 창은 끝의 완공 사진 줄을 빼고 채운다.
    assert client.get(f"/api/partner/orders/{order_id}/as").get_json()["data"]["content"] == "문 3짝 처짐"


def test_edit_refused_without_note_or_open_cycle(app, world, pushes):
    order_id, client = _completed_order(app, world)
    assert client.post(f"/api/partner/orders/{order_id}/as/edit",
                       data={"content": "x", "change_note": "y"}).status_code == 409  # 열린 건 없음
    client.post(f"/api/partner/orders/{order_id}/as", data={"content": "x"})
    resp = client.post(f"/api/partner/orders/{order_id}/as/edit", data={"content": "x2", "change_note": " "})
    assert resp.status_code == 400 and "바뀐 내용" in resp.get_json()["error"]
    assert len(_receptions(order_id)) == 1


# ── 파일 한 개씩 → AS방 ──────────────────────────────────────────────────────


def test_files_bind_only_to_current_reception_then_push_sends_unsent(app, world, fake_storage, pushes):
    order_id, client = _completed_order(app, world)
    rec = client.post(f"/api/partner/orders/{order_id}/as",
                      data={"content": "문짝 처짐", "defer_push": "1"}).get_json()["data"]["reception_log_id"]
    assert pushes == []  # 미뤘으면 아직 안 보낸다
    url = f"/api/partner/orders/{order_id}/as/files"
    assert client.post(url, data={"as_log_id": "al_other", **_file("a.jpg")}).status_code == 400  # 다른 줄
    assert client.post(url, data={"as_log_id": rec, **_file("bad.exe")}).status_code == 400  # 사진 · 동영상만
    ids = [client.post(url, data={"as_log_id": rec, "sort_order": str(i), **_file(name)}).get_json()["data"]["attachment_id"]
           for i, name in enumerate(("a.jpg", "clip.mp4"))]
    assert client.post(f"/api/partner/orders/{order_id}/as/push", json={}).status_code == 200
    assert pushes[-1]["attachment_ids"] == ids and pushes[-1]["change_note"] == ""
    # 고친 뒤 새 파일만 실린다.
    rec2 = client.post(f"/api/partner/orders/{order_id}/as/edit",
                       data={"content": "문짝 처짐 + 경첩", "change_note": "경첩도", "defer_push": "1"}).get_json()["data"]["reception_log_id"]
    new_id = client.post(url, data={"as_log_id": rec2, **_file("hinge.jpg")}).get_json()["data"]["attachment_id"]
    client.post(f"/api/partner/orders/{order_id}/as/push", json={"change_note": "경첩도"})
    assert pushes[-1]["attachment_ids"] == [new_id] and pushes[-1]["change_note"] == "경첩도"


def test_second_as_first_push_note_says_new_cycle():
    """2번째 AS 의 첫 PUSH — 이력 칸이 주문마다 하나라 본사처럼 재전송, 머리말로 새 건을 가른다(설계서 D7)."""
    old = "2026-10-01T00:00:00+00:00"
    sd = {"channeltalk_push_as": {"pushed": True, "sent_at": old},
          "as_lifecycle": {"current_cycle_id": "c2", "cycles": [
              {"cycle_id": "c1", "opened_at": "2026-09-30T00:00:00", "transitions": []},
              {"cycle_id": "c2", "opened_at": "2026-11-13T00:00:00", "transitions": []}]}}
    order = SimpleNamespace(structured_data=sd)
    assert svc.push_change_note(order, "무시") == "새 AS 접수 (2번째 AS)"
    sd["channeltalk_push_as"]["sent_at"] = "2026-11-13T01:00:00+00:00"  # 이 건에서 이미 보냄
    assert svc.push_change_note(order, "문 3짝") == "문 3짝"
    assert svc.push_change_note(SimpleNamespace(structured_data={}), "x") == ""  # 처음 보냄


# ── 창 값 · 목록 · 다른 회사 ─────────────────────────────────────────────────


def test_form_modes_and_other_company(app, world, pushes):
    order_id = _create(app, world["partner_a"]).get_json()["data"]["order_id"]
    client = _client(app, db_session.get(User, world["partner_a"]))
    assert client.get(f"/api/partner/orders/{order_id}/as").get_json()["data"]["mode"] is None  # 시공 전
    _to_stage(order_id, "COMPLETED")
    assert client.get(f"/api/partner/orders/{order_id}/as").get_json()["data"]["mode"] == "new"
    client.post(f"/api/partner/orders/{order_id}/as", data={"content": "거울 흔들림"})
    view = client.get(f"/api/partner/orders/{order_id}/as").get_json()["data"]
    assert view["mode"] == "edit" and view["content"] == "거울 흔들림" and view["push"]["pushed"] is True
    b = _client(app, db_session.get(User, world["partner_b"]))
    for method, path, kwargs in (("get", "", {}), ("post", "", {"data": {"content": "x"}}),
                                 ("post", "/edit", {"data": {"content": "x", "change_note": "y"}}),
                                 ("post", "/files", {"data": {"as_log_id": "x", **_file("a.jpg")}}),
                                 ("post", "/push", {"json": {}})):
        assert getattr(b, method)(f"/api/partner/orders/{order_id}/as{path}", **kwargs).status_code == 404, path


def test_aftercare_menu_lists_completed_and_open_as_with_buttons(app, world, pushes):
    done, client = _completed_order(app, world)
    open_as, _ = _completed_order(app, world)
    client.post(f"/api/partner/orders/{open_as}/as", data={"content": "x"})
    drawing = _create(app, world["partner_a"]).get_json()["data"]["order_id"]
    _to_stage(drawing, "DRAWING")  # 대조군: 진행 중 주문은 이 메뉴에 없다
    html = client.get("/partner?aftercare=1").get_data(as_text=True)
    table = html[html.index('class="table table-sm table-hover'):]
    assert f'data-pp-as-open="/api/partner/orders/{done}/as">AS 접수</button>' in table
    assert f'data-pp-as-open="/api/partner/orders/{open_as}/as">AS 접수 수정</button>' in table
    assert f"#{drawing}<" not in table and 'id="ppAsModal"' in html
    assert 'href="/partner?aftercare=1"' in html  # 메뉴 "완공 사진 · AS"
