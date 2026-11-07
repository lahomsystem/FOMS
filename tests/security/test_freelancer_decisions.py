"""FCOMM-01 사용자 결정 D21~D23 · 검수 R8 계약 (2026-11-07).

설계서 docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §6.3 겹 2 · 겹 4, 3단계 반증 재검수 원장 R8 · D21~D23.

* D21 담당자 뱃지: 켜진 프리랜서는 **등록된** 주문의 담당자 명단(사람 · 순서)을 못 바꾼다 — structured PUT 과 실측 판 칸
  고치기 두 길 모두 403. 초안 · 첫 등록은 된다. 같은 명단(띄어쓰기만 다름)은 바꾼 것이 아니다. 보통 직원은 그대로.
* D22 보내기: 내 주문의 알림톡 미리보기 · 보내기 · 채널 확인, 채널톡 PUSH(영발 · 실측)는 문지기를 지난다. 남의 주문은 404.
  발주 · AS PUSH 는 403. 바깥(Solapi · 채널톡)은 부르지 않는다 — 보내는 함수를 바꿔 둔다.
* D23 실측 일: 도면으로 넘기기(실측 단계 승인) · 방문 체크 · 첨부 지우기 · 제품 잇기 · 긴급 호출은 내 주문만.
  실측이 아닌 단계 승인은 403.
* R8: 정규형이 아닌 key(``..`` · ``//`` · ``./`` · 끝 ``/``)는 내 주문을 가리켜도 거부. 마법사 승격은 내 초안 폴더 key 만.
"""
from __future__ import annotations

import copy
import itertools

import pytest
from sqlalchemy.orm.attributes import flag_modified

import foms.api.channel.channel_integration as channel_api
import foms.api.kakao as kakao_api
import foms.services.order_draft_attachments as draft_attachments
from db import db_session
from foms.services.auth.freelancer_edit_guards import (
    MANAGER_LOCKED_MSG,
    PUSH_KIND_LOCKED_MSG,
    QUEST_STAGE_LOCKED_MSG,
    _UNCHANGED,
    _incoming_party,
    _managers_changed,
)
from foms.services.auth.freelancer_scope import (
    FREELANCER_ALLOWED_ENDPOINTS,
    FREELANCER_DENIED_MSG,
    FREELANCER_ORDER_NOT_FOUND_MSG,
    _key_order_ids,
)
from foms.services.order_draft_attachments import promote_draft_attachments
from models import Order, OrderAttachment
from tests.domains.test_auth_finance import _make_user
from tests.security.test_freelancer_edit_guards import _client, _ensure_link, _freelancer, _order

_seq = itertools.count(1)
_NOTIFY = {"X-FOMS-Notification-Write": "1"}


def _scope_404(resp) -> bool:
    return resp.status_code == 404 and (resp.get_json(silent=True) or {}).get("error") == FREELANCER_ORDER_NOT_FOUND_MSG


def _sd(order_id: int) -> dict:
    db_session.expire_all()
    return copy.deepcopy(db_session.get(Order, order_id).structured_data)


def _managers(order_id: int) -> dict:
    return _sd(order_id)["parties"]["manager"]


def _set_managers(order_id: int, names: list[str]) -> None:
    order = db_session.get(Order, order_id)
    sd = copy.deepcopy(order.structured_data)
    sd["parties"]["manager"] = {"name": names[0], "names": names}
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()


def _put_manager(client, order_id: int, manager) -> object:
    sd = _sd(order_id)
    sd["parties"]["manager"] = manager
    return client.put(f"/api/orders/{order_id}/structured", json={"structured_data": sd})


@pytest.fixture
def w(app):
    fl = _freelancer()
    own = _order(fl.match_name)
    draft = _order(fl.match_name, draft=True)
    other = _order("남의담당")
    for oid in (own, draft):
        _ensure_link(oid, fl)
    return {"fl": fl, "own": own, "draft": draft, "other": other, "client": _client(app, fl)}


# --------------------------------------------------------------------------
# D21 — structured PUT
# --------------------------------------------------------------------------
@pytest.mark.parametrize("change", ["swap", "add", "clear", "reorder", "non_dict"])
def test_freelancer_cannot_change_managers_of_registered_order(w, change):
    fl, oid, client = w["fl"], w["own"], w["client"]
    _set_managers(oid, [fl.match_name, "동료담당"])
    manager = {
        "swap": {"name": "다른담당", "names": ["다른담당"]},
        "add": {"name": fl.match_name, "names": [fl.match_name, "동료담당", "셋째담당"]},
        "clear": {"name": "", "names": []},
        "reorder": {"name": "동료담당", "names": ["동료담당", fl.match_name]},
        "non_dict": "다른담당",
    }[change]
    resp = _put_manager(client, oid, manager)
    assert resp.status_code == 403, resp.get_json()
    assert resp.get_json() == {"success": False, "data": None, "error": MANAGER_LOCKED_MSG}
    assert _managers(oid) == {"name": fl.match_name, "names": [fl.match_name, "동료담당"]}


def test_same_managers_are_not_a_change(w):
    fl, oid, client = w["fl"], w["own"], w["client"]
    _set_managers(oid, [fl.match_name, "동료담당"])
    assert _put_manager(client, oid, {"name": fl.match_name, "names": [fl.match_name, "동료담당"]}).status_code == 200
    # 대표만 다시 싣고 명단은 안 실음(합치기로 옛 명단이 남는다) · 앞뒤 공백만 다름
    assert _put_manager(client, oid, {"name": f"  {fl.match_name} "}).status_code == 200
    assert _put_manager(client, oid, {"name": fl.match_name, "names": [f" {fl.match_name}", "동료담당 "]}).status_code == 200
    # 담당자를 안 싣는 저장
    assert client.put(f"/api/orders/{oid}/structured", json={"notes": "메모만"}).status_code == 200


def test_freelancer_sets_managers_on_draft_and_first_registration(w):
    fl, oid, client = w["fl"], w["draft"], w["client"]
    resp = _put_manager(client, oid, {"name": fl.match_name, "names": [fl.match_name, "동료담당"]})
    assert resp.status_code == 200, resp.get_json()
    assert _sd(oid)["meta"]["draft"] is False  # 이 저장이 첫 등록이었다
    assert _put_manager(client, oid, {"name": "다른담당", "names": ["다른담당"]}).status_code == 403


def test_negative_control_without_guard_the_change_goes_through(w, monkeypatch):
    """음성 대조군: 판정을 끄면 같은 요청이 저장된다 — 위 403 시험이 실제로 이 판정을 본다는 증거."""
    import foms.api.measurement.routes as measurement_routes
    import foms.services.auth.freelancer_edit_guards as guards

    monkeypatch.setattr(guards, "_managers_changed", lambda order, sd: False)
    monkeypatch.setattr(measurement_routes, "freelancer_manager_change_denial", lambda order, names: None)
    second = _order(w["fl"].match_name)
    assert _put_manager(w["client"], w["own"], {"name": "다른담당", "names": ["다른담당"]}).status_code == 200
    assert _inline(w["client"], second, "manager", "또다른담당").status_code == 200
    # 뱃지에서 빠지면 연결 줄도 빠져 다음 요청부터 내 주문이 아니다 — D21 이 막는 까닭
    assert _scope_404(w["client"].get(f"/api/orders/{w['own']}/structured"))


@pytest.mark.parametrize("who", ["sales", "inactive"])
def test_non_freelancers_still_change_managers(app, who):
    user = _make_user("STAFF", "SALES") if who == "sales" else _freelancer(active=False)
    oid = _order("남의담당")
    resp = _put_manager(_client(app, user), oid, {"name": "새담당", "names": ["새담당", "남의담당"]})
    assert resp.status_code == 200, resp.get_json()
    assert _managers(oid)["names"] == ["새담당", "남의담당"]


class _Row:
    def __init__(self, sd, manager_name=None):
        self.structured_data, self.manager_name, self.id = sd, manager_name, 1


@pytest.mark.parametrize("payload,changed", [
    (None, False), ({}, False), ({"parties": None}, False), ({"parties": {"customer": {"name": "x"}}}, False),
    ({"parties": {"manager": {"phone": "010"}}}, False),
    ({"parties": {"manager": {"name": "가"}}}, False),
    ({"parties": {"manager": {"name": "나"}}}, True),
    ({"parties": {"manager": None}}, True),
    ({"parties": ["x"]}, True),
])
def test_manager_change_follows_put_merge_rules(payload, changed):
    row = _Row({"parties": {"manager": {"name": "가", "names": ["가", "나"]}}})
    assert _managers_changed(row, payload) is changed
    if not changed and "manager" not in str(payload):
        assert _incoming_party(payload, "manager") is _UNCHANGED


# --------------------------------------------------------------------------
# D21 — 실측 판 칸 고치기
# --------------------------------------------------------------------------
def _inline(client, order_id: int, field: str, value: str):
    return client.post(f"/api/erp/measurement/update/{order_id}", json={"field": field, "value": value})


def test_measurement_inline_manager_change_locked_for_freelancer(w):
    fl, oid, client = w["fl"], w["own"], w["client"]
    resp = _inline(client, oid, "manager", "다른담당")
    assert resp.status_code == 403 and resp.get_json()["error"] == MANAGER_LOCKED_MSG
    assert _inline(client, oid, "manager", f"{fl.match_name}, 동료담당").status_code == 403
    assert _managers(oid)["name"] == fl.match_name
    # 같은 명단 · 다른 칸(주소)은 된다(초안은 이 핸들러가 누구에게나 404 — active_filter 가 초안을 뺀다)
    assert _inline(client, oid, "manager", f" {fl.match_name} ").status_code == 200
    assert _inline(client, oid, "address", "가짜시 새로 2").status_code == 200
    assert _scope_404(_inline(client, w["other"], "manager", fl.match_name))


def test_measurement_inline_manager_change_for_staff_unchanged(app):
    oid = _order("남의담당")
    resp = _inline(_client(app, _make_user("STAFF", "SALES")), oid, "manager", "새담당, 남의담당")
    assert resp.status_code == 200, resp.get_json()
    assert _managers(oid)["names"] == ["새담당", "남의담당"]


# --------------------------------------------------------------------------
# D22 — 알림톡 · 채널톡 PUSH(바깥은 부르지 않는다)
# --------------------------------------------------------------------------
@pytest.fixture
def senders(monkeypatch):
    calls: dict[str, list] = {"alimtalk": [], "confirm": [], "push": []}
    monkeypatch.setattr(kakao_api, "is_configured", lambda *a, **k: True)
    monkeypatch.setattr(kakao_api, "send_alimtalk",
                        lambda order_id, **k: calls["alimtalk"].append(order_id) or {"sent": True, "error": None})
    monkeypatch.setattr(kakao_api, "confirm_channel",
                        lambda order_id: calls["confirm"].append(order_id) or {"error": "too_early", "checked": False})
    monkeypatch.setattr(channel_api, "run_manual_push",
                        lambda db, payload, actor, **k: calls["push"].append(dict(payload)) or ({"success": True}, 200))
    return calls


def test_alimtalk_own_order_reachable_other_404(w, senders):
    client, own, other = w["client"], w["own"], w["other"]
    assert client.get(f"/api/kakao/alimtalk/preview/{own}").status_code == 200
    assert client.post(f"/api/kakao/alimtalk/send-manual/{own}").status_code == 200
    assert client.post(f"/api/kakao/alimtalk/confirm-channel/{own}").status_code == 200
    assert senders["alimtalk"] == [own] and senders["confirm"] == [own]
    for method, path in (("GET", "preview"), ("POST", "send-manual"), ("POST", "confirm-channel")):
        assert _scope_404(client.open(f"/api/kakao/alimtalk/{path}/{other}", method=method)), path
    assert senders["alimtalk"] == [own] and senders["confirm"] == [own]


def test_channel_push_measurement_kinds_only_own_order(w, senders):
    client, own, other = w["client"], w["own"], w["other"]
    for kind in ("measurement", "measure_room", None):
        assert client.post("/api/channel/push-manual", json={"order_id": own, "push_kind": kind}).status_code == 200
    for kind in ("drawing", "as", "drawing_room", ["measurement"]):
        resp = client.post("/api/channel/push-manual", json={"order_id": own, "push_kind": kind})
        assert resp.status_code == 403 and resp.get_json()["error"] == PUSH_KIND_LOCKED_MSG, kind
    for raw in (other, str(other), float(other)):
        assert _scope_404(client.post("/api/channel/push-manual", json={"order_id": raw, "push_kind": "measurement"}))
    assert [p["order_id"] for p in senders["push"]] == [own, own, own]


def test_channel_push_for_staff_unchanged(app, senders):
    client = _client(app, _make_user("STAFF", "SALES"))
    oid = _order("남의담당")
    assert client.post("/api/channel/push-manual", json={"order_id": oid, "push_kind": "drawing"}).status_code == 200
    assert senders["push"] == [{"order_id": oid, "push_kind": "drawing"}]


def test_unopened_send_doors_stay_closed(w):
    """문서화: PUSH 미리보기(AS · 도면방 전용) · 견적서 PUSH 는 열지 않았다 — 문지기 403."""
    assert "channel_integration.api_channel_push_preview" not in FREELANCER_ALLOWED_ENDPOINTS
    resp = w["client"].get(f"/api/channel/push-preview?order_id={w['own']}&push_kind=as")
    assert resp.status_code == 403 and resp.get_json()["error"] == FREELANCER_DENIED_MSG
    resp = w["client"].post("/api/channel/push-estimate", data={"order_id": str(w["own"])})
    assert resp.status_code == 403 and resp.get_json()["error"] == FREELANCER_DENIED_MSG


# --------------------------------------------------------------------------
# D23 — 도면으로 넘기기 · 방문 체크 · 첨부 · 긴급 호출
# --------------------------------------------------------------------------
def test_quest_approve_measure_stage_own_order(w):
    client, own = w["client"], w["own"]
    assert _scope_404(client.post(f"/api/orders/{w['other']}/quest/approve", json={}))
    resp = client.post(f"/api/orders/{own}/quest/approve", json={})
    assert resp.status_code == 200 and resp.get_json()["auto_transitioned"] is True, resp.get_json()
    assert client.get(f"/api/orders/{own}/structured").status_code == 200  # 넘긴 뒤에도 내 주문


def _confirm_stage(order_id: int, stage: str = "CONFIRM") -> None:
    order = db_session.get(Order, order_id)
    sd = copy.deepcopy(order.structured_data)
    sd["workflow"]["stage"] = stage
    order.structured_data, order.erp_stage_code = sd, stage
    flag_modified(order, "structured_data")
    db_session.commit()


def test_quest_approve_confirm_stage_own_order_allowed(w):
    """D25(11-07): 자기 주문의 고객 컨펌 승인도 프리랜서가 누른다 — 단계 잠금에 걸리지 않는다."""
    _confirm_stage(w["own"])
    resp = w["client"].post(f"/api/orders/{w['own']}/quest/approve", json={})
    assert (resp.get_json() or {}).get("error") != QUEST_STAGE_LOCKED_MSG, resp.get_json()


def test_quest_approve_other_stage_locked_for_freelancer_only(app, w):
    _confirm_stage(w["own"], "PRODUCTION")
    resp = w["client"].post(f"/api/orders/{w['own']}/quest/approve", json={})
    assert resp.status_code == 403 and resp.get_json()["error"] == QUEST_STAGE_LOCKED_MSG
    staff_order = _order("남의담당")
    _confirm_stage(staff_order, "PRODUCTION")
    staff_resp = _client(app, _make_user("STAFF", "SALES")).post(f"/api/orders/{staff_order}/quest/approve", json={})
    assert (staff_resp.get_json() or {}).get("error") != QUEST_STAGE_LOCKED_MSG, staff_resp.get_json()


def test_measurement_visit_own_order(w):
    body = {"date": "2030-01-05", "done": True}
    resp = w["client"].post(f"/api/orders/{w['own']}/measurement-visit", json=body)
    assert resp.status_code == 200, resp.get_json()
    assert _scope_404(w["client"].post(f"/api/orders/{w['other']}/measurement-visit", json=body))


def _attachment(order_id: int, user_id: int | None) -> int:
    att = OrderAttachment(order_id=order_id, filename=f"x{next(_seq)}.jpg", file_type="image", category="measurement",
                          storage_key=f"orders/{order_id}/measurement/x{next(_seq)}.jpg", user_id=user_id, file_size=1)
    db_session.add(att)
    db_session.commit()
    return att.id


def test_attachment_delete_and_link_own_order(w):
    fl, client, own, other = w["fl"], w["client"], w["own"], w["other"]
    mine, theirs = _attachment(own, fl.id), _attachment(other, None)
    assert client.patch(f"/api/orders/{own}/attachments/{mine}", json={"item_index": 0}).status_code == 200
    assert client.delete(f"/api/orders/{own}/attachments/{mine}").status_code == 200
    assert _scope_404(client.patch(f"/api/orders/{other}/attachments/{theirs}", json={"item_index": 0}))
    assert _scope_404(client.delete(f"/api/orders/{other}/attachments/{theirs}"))
    # 내 주문 URL 에 남의 첨부 번호 — 핸들러가 (첨부, 주문) 둘 다로 찾아 없는 것으로 본다
    assert client.delete(f"/api/orders/{own}/attachments/{theirs}").status_code == 404
    db_session.expire_all()
    assert db_session.get(OrderAttachment, theirs).deleted_at is None


def test_urgent_call_own_order_or_none(w):
    client, staff = w["client"], _make_user("STAFF", "CS")
    assert client.get("/erp/api/urgent-targets").status_code == 200
    body = {"target_user_ids": [staff.id], "message": "확인 부탁해요"}
    assert client.post("/erp/api/urgent-call", json={**body, "order_id": w["own"]}, headers=_NOTIFY).status_code == 200
    assert client.post("/erp/api/urgent-call", json=body, headers=_NOTIFY).status_code == 200
    assert _scope_404(client.post("/erp/api/urgent-call", json={**body, "order_id": w["other"]}, headers=_NOTIFY))
    assert _scope_404(client.post("/erp/api/urgent-call", json={**body, "order_id": str(w["other"])}, headers=_NOTIFY))


# --------------------------------------------------------------------------
# R8 — 정규형 아닌 key · 마법사 승격
# --------------------------------------------------------------------------
def test_non_normal_keys_rejected_even_for_own_order(w):
    own, client = w["own"], w["client"]
    for folder in (f"orders/{own}/../{own}/attachments", f"orders//{own}/attachments", f"./orders/{own}/attachments",
                   f"orders/{own}/attachments/", f"orders/{own}/./attachments"):
        resp = client.post("/api/upload/session", json={"filename": "x.jpg", "size": 10, "folder": folder})
        assert _scope_404(resp), folder
    fid = w["fl"].id
    for key in (f"orders/{own}/../{w['other']}/x.jpg", f"order-drafts/{fid}//x.jpg", f"order-drafts/{fid}/./x.jpg"):
        body = {"draft_key": "new.r8", "step": 1,
                "payload": {"data": {"items": [{"attachments": [{"tmp_key": key, "filename": "x.jpg"}]}]}}}
        assert _scope_404(client.put("/api/erp/order-draft", json=body)), key


@pytest.mark.parametrize("value,expected", [
    ("orders/12/attachments/x.jpg", [12]), ("orders/12/../13/x.jpg", None), ("orders//12/x", None),
    ("orders/²/x.jpg", None), ("order-drafts/1/x.jpg", []), ("", []), (None, []),
])
def test_key_order_ids(value, expected):
    assert _key_order_ids(value) == expected


def test_wizard_promotion_only_takes_own_draft_folder(app, monkeypatch):
    class _Storage:
        storage_type = "r2"

        def object_exists(self, key):
            return True

        def get_file_type(self, filename):
            return "image"

    monkeypatch.setattr(draft_attachments, "get_storage", lambda: _Storage())
    user, other_user = _make_user("STAFF", "SALES"), _make_user("STAFF", "SALES")
    oid = _order("남의담당")
    keys = [f"order-drafts/{user.id}/new.a/ok.jpg", f"order-drafts/{other_user.id}/new.a/theirs.jpg",
            f"orders/{oid}/measurement/real.jpg", f"order-drafts/{user.id}/../{other_user.id}/x.jpg",
            f"order-drafts/{user.id}//x.jpg"]
    items = [{"attachments": [{"tmp_key": k, "filename": f"f{i}.jpg"} for i, k in enumerate(keys)]}]
    promote_draft_attachments(db_session, order_id=oid, items=items, user_id=user.id)
    promote_draft_attachments(db_session, order_id=oid, items=items, user_id=None)
    db_session.commit()
    rows = db_session.query(OrderAttachment.storage_key).filter(OrderAttachment.order_id == oid).all()
    assert [k for (k,) in rows] == [keys[0]]
