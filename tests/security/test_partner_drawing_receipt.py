"""협력사 도면 확인(받음) — FOMS 영업 "도면 수령 확인"과 같은 2단계(사용자 2026-10-28).

저희 도면팀이 보냄(TRANSFERRED) → 협력사 "도면 확인했어요"(→ 고객컨펌) 또는 수정 요청 → 고객과 확인 뒤
"이대로 만들어 주세요"(→ 생산). 직원 수령 확인과 같은 한 경로(``record_drawing_receipt``)를 탄다.
대조군: 다른 회사 404 · 보내기 전 409 · 우리 직원은 협력사 API 를 못 쓴다.
"""
from __future__ import annotations

import io

from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from models import Notification, Order, SecurityLog, User
from tests.security.partner_fixtures import (  # noqa: F401 — pytest fixture 재노출
    _client,
    _create,
    _to_stage,
    fake_storage,
    quiet_push,
    world,
)


def _send_drawing(order_id):
    """저희 도면팀이 도면을 보냄(도면 단계 · TRANSFERRED · 도면 key 파일 1개)."""
    order = db_session.get(Order, order_id)
    sd = dict(order.structured_data)
    key = f"orders/{order_id}/drawing/final.png"
    sd["drawing_status"] = "TRANSFERRED"
    sd["drawing_current_files"] = [{"key": key, "filename": "final.png"}]
    sd["drawing_transfer_history"] = [{"action": "TRANSFER", "at": "2026-10-28 10:00:00", "files": [{"key": key}]}]
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()


def _receipt(client, order_id):
    return client.post(f"/api/partner/orders/{order_id}/drawing-receipt", json={})


def test_partner_receipt_moves_to_confirm_then_approve_to_production(app, world, quiet_push):
    order_id = _create(app, world["partner_a"]).get_json()["data"]["order_id"]
    _send_drawing(order_id)
    client = _client(app, db_session.get(User, world["partner_a"]))
    page = client.get(f"/partner/orders/{order_id}").get_data(as_text=True)
    approve_btn = f'data-pp-approve-url="/api/partner/orders/{order_id}/approve-drawing"'
    receipt_btn = f'data-pp-approve-url="/api/partner/orders/{order_id}/drawing-receipt"'
    assert receipt_btn in page and approve_btn not in page and "수정 요청 보내기" in page
    board = client.get("/partner?turn=1").get_data(as_text=True)
    assert f'data-pp-order-id="{order_id}"' in board  # 보낸 도면은 협력사 차례

    resp = _receipt(client, order_id)
    assert resp.status_code == 200, resp.get_json()
    db_session.expire_all()
    order = db_session.get(Order, order_id)
    sd = order.structured_data
    assert order.erp_stage_code == "CONFIRM" and sd["drawing_status"] == "CONFIRMED"
    receipt = sd["drawing_transfer_history"][-1]
    assert receipt["action"] == "CONFIRM_RECEIPT" and receipt["by_user_name"].endswith("(협력사)")
    assert db_session.query(SecurityLog).filter_by(action="PARTNER_DRAWING_RECEIVED", target_id=order_id).count() == 1

    page = client.get(f"/partner/orders/{order_id}").get_data(as_text=True)
    assert approve_btn in page and receipt_btn not in page
    assert client.post(f"/api/partner/orders/{order_id}/approve-drawing", json={"idempotency_key": "r1"}).status_code == 200
    db_session.expire_all()
    assert db_session.get(Order, order_id).erp_stage_code == "PRODUCTION"


def test_partner_receipt_refused_before_send_other_company_and_staff(app, world, quiet_push):
    order_id = _create(app, world["partner_a"]).get_json()["data"]["order_id"]
    a = _client(app, db_session.get(User, world["partner_a"]))
    assert _receipt(a, order_id).status_code == 409  # 아직 보낸 도면이 없다
    assert "/drawing-receipt" not in a.get(f"/partner/orders/{order_id}").get_data(as_text=True)
    _send_drawing(order_id)
    assert _receipt(_client(app, db_session.get(User, world["partner_b"])), order_id).status_code == 404
    assert _receipt(_client(app, db_session.get(User, world["staff"])), order_id).status_code in (302, 403)
    db_session.expire_all()
    assert db_session.get(Order, order_id).erp_stage_code == "DRAWING"
    assert _receipt(a, order_id).status_code == 200
    assert _receipt(a, order_id).status_code == 409  # 두 번 누르면 이미 고객컨펌


def test_drawing_sent_is_partner_turn_for_notice(app, world):
    from foms.services.partners.notify import partner_drawing_turn

    order_id = _create(app, world["partner_a"]).get_json()["data"]["order_id"]
    order = db_session.get(Order, order_id)
    assert partner_drawing_turn(order) is False  # 도면 작업 중 — 아직 협력사 차례 아님
    _send_drawing(order_id)
    db_session.expire_all()
    assert partner_drawing_turn(db_session.get(Order, order_id)) is True


def test_partner_as_register_notifies_cs(app, world, fake_storage):
    order_id = _create(app, world["partner_a"]).get_json()["data"]["order_id"]
    _to_stage(order_id, "COMPLETED")
    client = _client(app, db_session.get(User, world["partner_a"]))
    resp = client.post(f"/api/partner/orders/{order_id}/as",
                       data={"content": "문짝 처짐", "photos": (io.BytesIO(b"img"), "as.jpg")},
                       content_type="multipart/form-data")
    assert resp.status_code == 200, resp.get_json()
    notes = db_session.query(Notification).filter_by(order_id=order_id, notification_type="PARTNER_AS_REGISTERED").all()
    assert [n.target_team for n in notes] == ["CS"] and "문짝 처짐" in notes[0].message


def test_sent_drawing_marks_turn_and_revision_wait_explains_itself(app, world, fake_storage, quiet_push):
    """운영 #5888(2026-10-30): 도면 단계에서 보낸 도면에 '내 차례'·'확인' 표시가 없었고, 수정 요청 뒤에는
    버튼 · 차례 목록에서 빠진 이유가 화면에 없어 "도면이 안 보인다"로 읽혔다."""
    from foms.services.partners.order_list import REVISION_WORK

    order_id = _create(app, world["partner_a"]).get_json()["data"]["order_id"]
    _send_drawing(order_id)
    client = _client(app, db_session.get(User, world["partner_a"]))
    page = client.get(f"/partner/orders/{order_id}").get_data(as_text=True)
    assert "내 차례</span>" in page and 'bg-danger">확인</span>' in page
    assert "data-pp-revision-wait" not in page

    resp = client.post(f"/api/partner/orders/{order_id}/revision", data={"note": "스마트바는 없나요"},
                       content_type="multipart/form-data")
    assert resp.status_code == 200, resp.get_json()
    page = client.get(f"/partner/orders/{order_id}").get_data(as_text=True)
    assert "data-pp-revision-wait" in page and "수정 요청을 보냈어요" in page and "스마트바는 없나요" in page
    assert "/drawing-receipt" not in page and "내 차례</span>" not in page
    assert "final.png" in page  # 지난번 도면은 그대로 보인다
    turn = client.get("/partner?turn=1").get_data(as_text=True)
    # 작업대 카드(내 차례)는 아니고, 아래 "도면팀이 고치는 중" 줄에 내 요청과 함께 남는다(2026-10-30 목업).
    assert f'<article class="pp-tcard" data-pp-order-id="{order_id}"' not in turn
    assert "도면팀이 고치는 중" in turn and f'#drawing" data-pp-order-id="{order_id}"' in turn and "스마트바는 없나요" in turn
    board = client.get("/partner").get_data(as_text=True)
    assert REVISION_WORK in board and "도면 수정 중</span>" in board  # 배지도 "도면 수정 중"(사용자 2026-10-30)
    assert "도면 수정 중</span>" in page and "도면 작업 중 1" in board  # 칸 셈은 도면 작업 중 그대로

    # 우리 쪽이 낸 수정 요청이면 메모는 숨긴다(history.py 와 같은 규칙).
    order = db_session.get(Order, order_id)
    sd = dict(order.structured_data)
    sd["drawing_transfer_history"] = [*sd["drawing_transfer_history"],
                                      {"action": "REQUEST_REVISION", "at": "2026-10-30 01:00:00", "note": "내부 메모"}]
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()
    page = client.get(f"/partner/orders/{order_id}").get_data(as_text=True)
    assert "저희 쪽에서 도면을 고치고 있어요" in page and "내부 메모" not in page


def test_drawing_tab_mirrors_workbench_layout_with_partner_safe_values(app, world, fake_storage, quiet_push):
    """사용자 2026-10-30 '도면 탭도 FOMS 와 같은 방식으로': 차례 띠 · 단계 · 번호 붙은 도면 · 주고받은 기록.
    우리 도면팀 전달 메모 · 직원 이름은 싣지 않고, 이 회사가 낸 요청은 메모까지 싣는다."""
    order_id = _create(app, world["partner_a"]).get_json()["data"]["order_id"]
    _send_drawing(order_id)
    order = db_session.get(Order, order_id)
    sd = dict(order.structured_data)
    sd["drawing_transfer_history"] = [{**sd["drawing_transfer_history"][0], "note": "내부 전달 메모",
                                       "by_user_name": "김도면", "files_count": 1}]
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()
    client = _client(app, db_session.get(User, world["partner_a"]))
    page = client.get(f"/partner/orders/{order_id}").get_data(as_text=True)
    assert 'data-pp-drawing-turn="mine"' in page and "내 차례 · 도면 확인" in page
    assert "1번 · final.png" in page and "1차 도면 올림" in page and "저희 도면팀" in page
    assert "내부 전달 메모" not in page and "김도면" not in page
    assert 'pp-dsteps__item is-done' in page and 'pp-dsteps__item is-now' in page

    client.post(f"/api/partner/orders/{order_id}/revision", data={"note": "서랍 3단으로"},
                content_type="multipart/form-data")
    page = client.get(f"/partner/orders/{order_id}").get_data(as_text=True)
    assert 'data-pp-drawing-turn="other"' in page and "고치는 중" in page
    partner_name = db_session.get(User, world["partner_a"]).name
    assert "pp-dthread__msg--right" in page and partner_name in page and "서랍 3단으로" in page


def test_drawing_tab_survives_old_history_shapes():
    """옛 이력 모양(files 가 개수 int · 시각 없음 · 모르는 action)에도 도면 탭이 깨지지 않는다(500 대조군)."""
    from types import SimpleNamespace

    from foms.services.partners.drawing_tab import build_partner_drawing_tab

    order = SimpleNamespace(id=1, partner_org_id=7, erp_stage_code="DRAWING", structured_data={
        "drawing_status": "TRANSFERRED",
        "drawing_transfer_history": [
            {"action": "TRANSFER", "files": 2}, {"action": "REQUEST_REVISION", "files": 3, "partner_org_id": 7},
            {"action": "REVISION_CANCELLED"}, "garbage",
        ]})
    tab = build_partner_drawing_tab(order, [{"key": "k"}], can_receive=True, can_approve=False)
    assert [e["tag"] for e in tab["thread"]] == ["1차 도면 올림", "수정 요청"]
    assert tab["thread"][0]["note"] == "도면 2장" and tab["turn"]["tone"] == "mine"
