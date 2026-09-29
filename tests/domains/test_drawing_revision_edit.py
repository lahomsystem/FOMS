"""도면팀 확인 전 영업의 '요청 고치기'(사용자 결정 Q5-③).

``POST /api/orders/<id>/request-revision/edit`` 본문 ``{note, files, source, received_via,
target_file_keys?}``. 조건: ``drawing_status == RETURNED`` 이고 마지막 ``REQUEST_REVISION`` 이
도면팀 반영 체크 전, 요청자 본인·배정 영업·관리자만. files 는 2b 계약(``drawing_revision_files``)
그대로, 잠금은 ``lock_order_row`` + ``execute_single_order_write``(버전 +1). 항목에 ``edited_at``·
``edited_by`` 를 더하고 고치기 전 내용은 항목 안 ``edits`` 목록에 남긴다. 도면팀에 수정요청
알림(제목에 '수정요청 고침'). 응답 ``{success, data: {request}}``.
"""
from __future__ import annotations

from datetime import date

import pytest
from werkzeug.security import generate_password_hash

import foms.api.drawing.erp_orders_revision as revision_api
from db import db_session
from foms.services.orders.drawing_key_safety import history_referenced_keys
from models import Notification, Order, User

SALES = "영업고침"


@pytest.fixture
def quiet(monkeypatch):
    sent = []
    monkeypatch.setattr(revision_api, "emit_erp_notification_to_users", lambda ids, payload: sent.append(payload))
    return sent


def _user(username, *, role="MANAGER", team="SALES", name=SALES):
    u = User(username=username, password=generate_password_hash("pw"), role=role, team=team,
             name=name, is_active=True)
    db_session.add(u)
    db_session.commit()
    return u


def _login(client, user):
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = user.id, user.username, user.role


def _order(files=2):
    order = Order(received_date=date.today().strftime("%Y-%m-%d"), customer_name="고침고객",
                  phone="010-9", address="서울", product="붙박이장", status="DRAWING",
                  manager_name=SALES, is_erp_order=True, erp_stage_code="DRAWING", structured_data={})
    db_session.add(order)
    db_session.commit()
    keys = [f"orders/{order.id}/drawing_wizard/exports/v{i + 1}.png" for i in range(files)]
    order.structured_data = {
        "parties": {"customer": {"name": "고침고객"}, "manager": {"name": SALES}},
        "workflow": {"stage": "DRAWING"},
        "drawing_status": "TRANSFERRED",
        "drawing_current_files": [{"key": k, "filename": k.rsplit("/", 1)[-1]} for k in keys],
        "drawing_transfer_history": [
            {"action": "TRANSFER", "at": "2026-09-29 01:00:00", "files": [{"key": k} for k in keys],
             "previous_current_files": []},
        ],
    }
    db_session.commit()
    return order.id, keys


def _gw(oid, name):
    return f"orders/{oid}/drawing_gateway/revisions/20260929_101010_ab12cd34_{name}"


def _sd(oid):
    db_session.expire_all()
    return dict(db_session.get(Order, oid).structured_data or {})


def _version(oid):
    db_session.expire_all()
    return db_session.get(Order, oid).mutation_version


def _last_request(sd):
    return [h for h in sd["drawing_transfer_history"] if h.get("action") == "REQUEST_REVISION"][-1]


def _request(client, oid, keys, **extra):
    body = {"note": "오른쪽 문짝 폭 줄여 주세요", "target_drawing_keys": [keys[0]], "source": "customer",
            "received_via": "kakao", "files": [{"key": _gw(oid, "a.jpg"), "filename": "a.jpg"}], **extra}
    res = client.post(f"/api/orders/{oid}/request-revision", json=body)
    assert res.status_code == 200, res.get_json()


def _edit(client, oid, **body):
    return client.post(f"/api/orders/{oid}/request-revision/edit", json=body)


def test_edit_replaces_content_keeps_old_in_edits(client, quiet):
    sales = _user("ed_a")
    _login(client, sales)
    oid, keys = _order()
    _request(client, oid, keys)
    original = _last_request(_sd(oid))
    before = _version(oid)
    res = _edit(client, oid, note="손잡이도 무광 블랙으로", source="customer", received_via="phone",
                files=[{"key": _gw(oid, "b.jpg"), "filename": "b.jpg"}], target_file_keys=[keys[1]])
    assert res.status_code == 200, res.get_json()
    body = res.get_json()
    assert body["success"] is True and body.get("error") is None
    req = body["data"]["request"]
    assert req["note"] == "손잡이도 무광 블랙으로"
    sd = _sd(oid)
    entry = _last_request(sd)
    assert sd["drawing_status"] == "RETURNED"
    assert entry["note"] == "손잡이도 무광 블랙으로"
    assert entry["received_via"] == "phone" and entry["source"] == "customer"
    assert [f["key"] for f in entry["files"]] == [_gw(oid, "b.jpg")]
    assert entry["files_count"] == 1
    assert entry["target_drawing_keys"] == [keys[1]] and entry["target_drawing_numbers"] == [2]
    assert entry["target_drawing_key"] == keys[1] and entry["target_drawing_number"] == 2
    assert entry["edited_at"] and entry["edited_by_user_id"] == sales.id and entry["edited_by"] == SALES
    assert len(entry["edits"]) == 1
    old = entry["edits"][0]
    assert old["note"] == "오른쪽 문짝 폭 줄여 주세요"
    assert [f["key"] for f in old["files"]] == [_gw(oid, "a.jpg")]
    assert old["received_via"] == "kakao" and old["target_drawing_keys"] == [keys[0]]
    assert old["replaced_by_user_id"] == sales.id and old["replaced_at"] == entry["edited_at"]
    # 원래 요청 식별값(반영 체크 토글이 보내는 at·by_user_id)은 그대로다.
    assert entry["at"] == original["at"] and entry["by_user_id"] == original["by_user_id"]
    assert _version(oid) == before + 1


def test_edit_notifies_drawing_team_with_edit_title(client, quiet):
    _login(client, _user("ed_b"))
    oid, keys = _order()
    _request(client, oid, keys)
    assert _edit(client, oid, note="고친 내용").status_code == 200
    notifs = (db_session.query(Notification).filter(Notification.order_id == oid)
              .order_by(Notification.id).all())
    last = notifs[-1]
    assert last.notification_type == "DRAWING_REVISION" and last.target_team == "DRAWING"
    assert "수정요청 고침" in last.title
    assert quiet[-1]["interrupt"] is True and "수정요청 고침" in quiet[-1]["title"]


def test_missing_keys_keep_original_values(client, quiet):
    _login(client, _user("ed_c"))
    oid, keys = _order()
    _request(client, oid, keys)
    assert _edit(client, oid, note="메모만 고침").status_code == 200
    entry = _last_request(_sd(oid))
    assert entry["note"] == "메모만 고침"
    assert [f["key"] for f in entry["files"]] == [_gw(oid, "a.jpg")]
    assert entry["source"] == "customer" and entry["received_via"] == "kakao"
    assert entry["target_drawing_keys"] == [keys[0]]


def test_second_edit_appends_edits(client, quiet):
    _login(client, _user("ed_d"))
    oid, keys = _order()
    _request(client, oid, keys)
    assert _edit(client, oid, note="둘째").status_code == 200
    assert _edit(client, oid, note="셋째", source="sales").status_code == 200
    entry = _last_request(_sd(oid))
    assert [e["note"] for e in entry["edits"]] == ["오른쪽 문짝 폭 줄여 주세요", "둘째"]
    assert entry["source"] == "sales" and "received_via" not in entry


def test_checked_request_cannot_be_edited(client, quiet):
    _login(client, _user("ed_e"))
    oid, keys = _order()
    _request(client, oid, keys)
    db_session.expire_all()
    order = db_session.get(Order, oid)
    sd = dict(order.structured_data)
    hist = [dict(h) for h in sd["drawing_transfer_history"]]
    hist[-1]["review_check"] = {"checked": True, "checked_by_name": "도면팀"}
    sd["drawing_transfer_history"] = hist
    order.structured_data = sd
    db_session.commit()
    before = _version(oid)
    res = _edit(client, oid, note="늦었다")
    assert res.status_code == 409
    assert res.get_json()["error"] == "REVISION_ALREADY_CHECKED"
    assert _last_request(_sd(oid))["note"] == "오른쪽 문짝 폭 줄여 주세요"
    assert _version(oid) == before


def test_not_returned_is_409(client, quiet):
    _login(client, _user("ed_f"))
    oid, _ = _order()
    res = _edit(client, oid, note="x")
    assert res.status_code == 409
    assert res.get_json()["error"] == "REVISION_NOT_EDITABLE"


def test_other_sales_is_403_admin_is_200(client, quiet):
    owner = _user("ed_g")
    _login(client, owner)
    oid, keys = _order()
    _request(client, oid, keys)
    _login(client, _user("ed_g_other", name="다른영업"))
    res = _edit(client, oid, note="남의 요청")
    assert res.status_code == 403
    _login(client, _user("ed_g_drawing", role="STAFF", team="DRAWING", name=SALES))
    assert _edit(client, oid, note="도면팀").status_code == 403
    _login(client, _user("ed_g_admin", role="ADMIN", team=None, name="관리자"))
    assert _edit(client, oid, note="관리자가 고침").status_code == 200


def test_requester_can_edit_after_manager_changed(client, quiet):
    requester = _user("ed_h")
    _login(client, requester)
    oid, keys = _order()
    _request(client, oid, keys)
    db_session.expire_all()
    order = db_session.get(Order, oid)
    sd = dict(order.structured_data)
    sd["parties"] = {"customer": {"name": "고침고객"}, "manager": {"name": "새담당"}}
    order.structured_data = sd
    order.manager_name = "새담당"
    db_session.commit()
    assert _edit(client, oid, note="요청자 본인이 고침").status_code == 200


def test_invalid_files_and_source_are_400_before_write(client, quiet):
    _login(client, _user("ed_i"))
    oid, keys = _order()
    _request(client, oid, keys)
    before = _version(oid)
    res = _edit(client, oid, note="x", files=[{"key": "orders/999999/drawing_gateway/revisions/other.png"}])
    assert res.status_code == 400 and res.get_json()["error"] == "INVALID_REVISION_FILE"
    res2 = _edit(client, oid, note="x", source="boss")
    assert res2.status_code == 400 and res2.get_json()["error"] == "INVALID_REVISION_SOURCE"
    res3 = _edit(client, oid, note="x", target_file_keys=["orders/999999/nope.png"])
    assert res3.status_code == 400 and res3.get_json()["error"] == "INVALID_REVISION_TARGET"
    res4 = _edit(client, oid, note=123)
    assert res4.status_code == 400 and res4.get_json()["error"] == "INVALID_REVISION_NOTE"
    assert _version(oid) == before
    assert _last_request(_sd(oid))["note"] == "오른쪽 문짝 폭 줄여 주세요"


def test_old_files_stay_referenced_for_retention(client, quiet):
    """고치기로 뺀 옛 참고 파일도 도면 기록이 가리키는 key 로 남는다(전달 취소 삭제 판정에서 보존)."""
    _login(client, _user("ed_j"))
    oid, keys = _order()
    _request(client, oid, keys)
    assert _edit(client, oid, files=[{"key": _gw(oid, "b.jpg"), "filename": "b.jpg"}]).status_code == 200
    refs = history_referenced_keys(_sd(oid))
    assert _gw(oid, "a.jpg") in refs and _gw(oid, "b.jpg") in refs


def test_cancel_after_edit_keeps_edits(client, quiet):
    _login(client, _user("ed_k"))
    oid, keys = _order()
    _request(client, oid, keys)
    assert _edit(client, oid, note="고침").status_code == 200
    assert client.post(f"/api/orders/{oid}/cancel-revision-request", json={}).status_code == 200
    sd = _sd(oid)
    cancelled = [h for h in sd["drawing_transfer_history"] if h.get("action") == "REVISION_CANCELLED"][-1]
    assert cancelled["request"]["edits"][0]["note"] == "오른쪽 문짝 폭 줄여 주세요"
    assert _gw(oid, "a.jpg") in history_referenced_keys(sd)
