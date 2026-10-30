"""협력사 주문 화면 영발 · 발주 PUSH(사용자 결정 2026-10-29).

본사는 채널톡 영발방 · 발주방을 보고 시공 스케줄을 짠다 — 협력사 주문도 같은 방에 같은 모양으로 들어가야 한다.
영발은 처음 저장 때 묻고 그 뒤엔 버튼, 발주는 "이대로 만들어 주세요" 뒤 자동 한 번 + 다시 보내기 버튼.
발주방에는 우리 최종 도면만(협력사 초안 빼기 — ERP 발주 PUSH 도 같이). 채널톡 전송은 가짜로 바꿔 끼운다.
대조군: 다른 회사 주문 · 우리 직원 계정 · 승인 전 발주 · 우리 도면(초안과 같은 'drawing' 분류).
"""
from __future__ import annotations

from pathlib import Path

import pytest

import foms.api.channel.channel_integration as channel_integration
from db import db_session
from models import Order, OrderAttachment, User
from tests.security.partner_fixtures import (  # noqa: F401 — pytest fixture 재노출
    _PAYLOAD,
    _client,
    _create,
    _to_confirm,
    world,
)


class _PushStorage:
    def get_download_url(self, storage_key, expires_in=3600, **_kwargs):
        return f"https://r2.example/{storage_key}"


@pytest.fixture
def channel(monkeypatch):
    """채널톡 설정 · 스토리지 · 전송을 가짜로 — 보낸 것을 sent 에 모은다."""
    monkeypatch.setenv("CHANNEL_GROUP_MEASUREMENT", "group-measure")
    monkeypatch.setenv("CHANNEL_GROUP_DRAWING", "group-draw")
    monkeypatch.setattr(channel_integration, "is_configured", lambda: True)
    monkeypatch.setattr(channel_integration, "get_storage", lambda: _PushStorage())
    sent: list[dict] = []

    def _fake_dispatch(event_type, data, raise_on_error=False):
        sent.append(data)
        return {"success": True, "message_id": f"msg-{len(sent)}"}

    monkeypatch.setattr(channel_integration, "dispatch_order_event", _fake_dispatch)
    return sent


def _order(app, world, **extra) -> int:
    resp = _create(app, world["partner_a"], {**_PAYLOAD, **extra})
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["data"]["order_id"]


def _attach(order_id, folder, category, name) -> None:
    db_session.add(OrderAttachment(order_id=order_id, filename=name, file_type="image", category=category,
                                   file_size=10, storage_key=f"orders/{order_id}/{folder}/{name}"))
    db_session.commit()


def _sent_names(data) -> set[str]:
    return {f["url"].rsplit("/", 1)[-1] for f in data["files"]}


def _push(client, order_id, kind, note=None):
    body = {"kind": kind, **({"change_note": note} if note else {})}
    return client.post(f"/api/partner/orders/{order_id}/channel-push", json=body)


def test_preview_text_matches_erp_push_shape_with_partner_wish_date(app, world):
    order_id = _order(app, world, requested_construction_date="2026-11-03", requested_construction_time="오후")
    client = _client(app, db_session.get(User, world["partner_a"]))
    data = client.get(f"/api/partner/orders/{order_id}/channel-push").get_json()["data"]
    lines = data["text"].split("\n")
    assert "고객명 : 홍길동" in lines and "발주사 : 가나가구" in lines
    assert "시공일 : 협력사 희망 11월 3일 오후 · 확정 대기" in lines
    assert not any(line.startswith(("실측일", "시   간")) for line in lines)  # 영발 · 발주방엔 실측 일정이 안 나간다
    assert data["state"]["measurement"]["open"] is True and data["state"]["drawing"]["open"] is False


def test_measurement_push_sends_partner_photos_and_resend_needs_note(app, world, channel):
    order_id = _order(app, world)
    _attach(order_id, "partner_measurement", "measurement", "site.jpg")
    _attach(order_id, "partner_draft", "drawing", "draft.jpg")
    client = _client(app, db_session.get(User, world["partner_a"]))
    preview = client.get(f"/api/partner/orders/{order_id}/channel-push").get_json()["data"]["text"]

    resp = _push(client, order_id, "measurement")
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["data"]["state"]["measurement"]["pushed"] is True
    first = channel[-1]
    assert first["push_kind"] == "measurement" and first["text"] == preview and first["is_retry"] is False
    assert _sent_names(first) == {"site.jpg"} and first["pushed_by_name"] == "가나 직원 (협력사)"
    sd = db_session.get(Order, order_id).structured_data
    assert sd["channeltalk_push"]["pushed"] is True  # ERP 와 같은 이력 칸 — ERP 에서 누르면 재전송이 된다

    assert _push(client, order_id, "measurement").status_code == 400  # 두 번째는 바뀐 내용 없이 못 보낸다
    assert len(channel) == 1
    resp = _push(client, order_id, "measurement", note="품목 너비 수정")
    assert resp.status_code == 200 and channel[-1]["is_retry"] is True and channel[-1]["change_note"] == "품목 너비 수정"


def test_push_refused_for_other_company_staff_and_before_approve(app, world, channel):
    order_id = _order(app, world)
    other = _client(app, db_session.get(User, world["partner_b"]))
    assert _push(other, order_id, "measurement").status_code == 404
    assert other.get(f"/api/partner/orders/{order_id}/channel-push").status_code == 404
    staff = _client(app, db_session.get(User, world["staff"]))
    assert _push(staff, order_id, "measurement").status_code == 403
    own = _client(app, db_session.get(User, world["partner_a"]))
    resp = _push(own, order_id, "drawing")
    assert resp.status_code == 409 and "도면 승인" in resp.get_json()["error"]
    assert _push(own, order_id, "as").status_code == 400
    assert channel == []


def test_approve_sends_drawing_push_once_with_our_final_drawing_only(app, world, channel):
    order_id = _order(app, world)
    _attach(order_id, "partner_draft", "drawing", "draft.jpg")
    _attach(order_id, "drawing", "drawing", "final.jpg")
    _to_confirm(order_id)
    client = _client(app, db_session.get(User, world["partner_a"]))
    resp = client.post(f"/api/partner/orders/{order_id}/approve-drawing", json={"idempotency_key": "k-push"})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["data"]["push_note"] == "발주방에 도면을 보냈습니다."
    assert len(channel) == 1 and channel[0]["push_kind"] == "drawing"
    assert _sent_names(channel[0]) == {"final.jpg"}  # 협력사 초안은 발주방에 안 나간다
    page = client.get(f"/partner/orders/{order_id}").get_data(as_text=True)
    assert "발주 보냄" in page
    # 다시 보내기는 버튼(바뀐 내용 필요)
    resp = _push(client, order_id, "drawing", note="도면 2차 반영")
    assert resp.status_code == 200 and len(channel) == 2 and channel[-1]["is_retry"] is True


def test_approve_still_succeeds_when_channel_push_fails(app, world, channel, monkeypatch):
    order_id = _order(app, world)
    _to_confirm(order_id)
    monkeypatch.setattr(channel_integration, "is_configured", lambda: False)
    client = _client(app, db_session.get(User, world["partner_a"]))
    resp = client.post(f"/api/partner/orders/{order_id}/approve-drawing", json={"idempotency_key": "k-fail"})
    assert resp.status_code == 200
    assert "다시 보내 주세요" in resp.get_json()["data"]["push_note"]
    assert db_session.get(Order, order_id).structured_data["blueprint"]["customer_confirmed"] is True
    # 설정 오류 문구(환경변수 이름)는 협력사에게 보이지 않는다
    resp = _push(client, order_id, "drawing")
    assert resp.status_code == 502 and "환경변수" not in resp.get_json()["error"]


def test_erp_order_push_also_skips_partner_draft(app, world, channel):
    order_id = _order(app, world)
    _attach(order_id, "partner_draft", "drawing", "draft.jpg")
    _attach(order_id, "drawing", "drawing", "final.jpg")
    admin = _client(app, db_session.get(User, world["admin"]))
    resp = admin.post("/api/channel/push-manual", json={"order_id": order_id, "text": "발주", "push_kind": "drawing"})
    assert resp.status_code == 200, resp.get_json()
    assert _sent_names(channel[-1]) == {"final.jpg"}


def test_new_order_page_and_detail_page_carry_push_controls(app, world):
    client = _client(app, db_session.get(User, world["partner_a"]))
    assert "/api/partner/orders/0/channel-push" in client.get("/partner/orders/new").get_data(as_text=True)
    order_id = _order(app, world)
    page = client.get(f"/partner/orders/{order_id}").get_data(as_text=True)
    assert 'data-pp-push="measurement"' in page and 'data-pp-push="drawing"' in page and "영발 아직 안 보냄" in page
    assert "실측 사진이 없습니다. 글만 영발방으로 갑니다." in page
    assert "pp-push-text" in page
    assert "보낼 글 + 실측 사진을 영발방으로" not in page


def test_detail_page_counts_measure_photos_for_this_site(app, world):
    """실측 첨부가 있는 현장만 장수를 적는다. 도면 파일은 세지 않는다."""
    client = _client(app, db_session.get(User, world["partner_a"]))
    order_id = _order(app, world)
    _attach(order_id, "partner_measurement", "measurement", "site.jpg")
    _attach(order_id, "drawing", "drawing", "final.jpg")
    page = client.get(f"/partner/orders/{order_id}").get_data(as_text=True)
    assert "실측 사진 1장이 글과 함께 영발방으로 갑니다." in page


def test_push_textarea_opens_tall() -> None:
    """보낼 글 칸은 변환 전에도 기본 높이가 높다."""
    css = Path("static/css/contexts/partner/partner-portal.css").read_text(encoding="utf-8")
    assert ".pp-push-text" in css and "min-height: 425px" in css
