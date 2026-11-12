"""완료 주문 AS 도면 차수 (설계서 docs/specs/2026-11-11-as-drawing-after-completion_SPEC.md §10).

흐름 1: AS 접수 창 '도면팀에 부탁' → 접수와 같은 mutation 에서 차수 WAITING.
흐름 2: 도면팀 [AS 도면 시작] → AS 접수가 없으면 접수까지 하고 차수 IN_PROGRESS.
함께: 원래 시트 잠금 · AS 전달 · 확인/고쳐 달라기 · 원래 최종 도면 불변 · 파일 key 보호.
"""

from __future__ import annotations

import copy
import io
from datetime import date
from types import SimpleNamespace

import pytest
from werkzeug.security import generate_password_hash

import foms.api.drawing.wizard as wizard_api
from db import db_session
from foms.services.common import dashboard_cache as dc
from foms.api.erp_orders_structured import _OPERATIONAL_TOP_LEVEL_KEYS
from foms.services.orders import as_drawing as asd
from foms.services.orders.drawing_key_safety import drawing_keys_in_use
from foms.services.orders.structured_form_projection import lock_server_owned_keys
from models import Notification, Order, User

ORIGINAL_FILES = [{"key": "orders/{oid}/drawing_wizard/exports/orig.png", "filename": "orig.png",
                   "sheet_id": "s-1"}]


class _Storage:
    def upload_file(self, file_obj, filename, folder="uploads"):
        return {"success": True, "key": f"{folder}/{filename}"}

    def delete_file(self, key):
        return True


@pytest.fixture(autouse=True)
def _reset_cache_runtime(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    dc.reset_dashboard_cache_runtime_for_tests()
    yield
    dc.reset_dashboard_cache_runtime_for_tests()


@pytest.fixture
def storage(monkeypatch):
    fake = _Storage()
    monkeypatch.setattr(wizard_api, "get_storage", lambda: fake)
    return fake


def _user(username, role="STAFF", team="DRAWING"):
    user = User(username=username, password=generate_password_hash("pw"), role=role,
                team=team, name=f"{username}-name", is_active=True)
    db_session.add(user)
    db_session.commit()
    return SimpleNamespace(id=user.id, username=user.username, role=user.role, name=user.name)


def _as(client, user):
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = user.id, user.username, user.role


def _order(stage="COMPLETED", *, drawing_ids=None, with_wizard=True, name="이고객",
           drawing_status="CONFIRMED"):
    sd = {
        "parties": {"customer": {"name": name, "phone": "010-1111-2222"},
                    "manager": {"name": "영업담당"}},
        "site": {"address_main": "성남", "address_full": "성남"},
        "items": [{"product_name": "냉장고장"}],
        "workflow": {"stage": stage},
        "drawing_status": drawing_status,
        "assignments": {"drawing_assignee_user_ids": list(drawing_ids or [])},
    }
    order = Order(received_date=date.today().strftime("%Y-%m-%d"), customer_name=name,
                  phone="010-1111-2222", address="성남", product="냉장고장", status=stage,
                  manager_name="영업담당", is_erp_order=True, erp_stage_code=stage, structured_data=sd)
    db_session.add(order)
    db_session.commit()
    files = [dict(f, key=f["key"].format(oid=order.id)) for f in ORIGINAL_FILES]
    sd = copy.deepcopy(order.structured_data)
    sd["drawing_current_files"] = files
    sd["drawing_transfer_history"] = [{"action": "TRANSFER", "files": files}]
    if with_wizard:
        sd["drawing_wizard"] = {"v": 1, "updated_at": "2026-10-14 10:00:00",
                                "sheets": [{"id": "s-1", "name": "냉장고장", "form": {}, "objects": []}]}
    order.structured_data = sd
    db_session.commit()
    return order.id


def _sd(oid):
    db_session.expire_all()
    return copy.deepcopy(db_session.get(Order, oid).structured_data or {})


def _notices(oid):
    db_session.expire_all()
    return (db_session.query(Notification)
            .filter(Notification.order_id == oid, Notification.notification_type.like("AS_DRAWING%"))
            .all())


def _start(client, oid, **body):
    return client.post(f"/api/orders/{oid}/drawing/as/start", json=body)


def _put(client, oid, sheets):
    base = _sd(oid).get("drawing_wizard", {}).get("updated_at")
    return client.put(f"/api/orders/{oid}/drawing-wizard",
                      json={"state": {"v": 1, "sheets": sheets}, "base_updated_at": base})


def _sheet_png(client, oid, sheet_id, filename):
    return client.post(
        f"/api/orders/{oid}/drawing-wizard/sheet-png",
        data={"file": (io.BytesIO(b"\x89PNG\r\n\x1a\nFAKE"), filename),
              "sheet_id": sheet_id, "sheet_name": f"AS {sheet_id}"},
        content_type="multipart/form-data",
    )


# --------------------------------------------------------------------------
# 흐름 1 — AS 접수 창에서 도면 부탁
# --------------------------------------------------------------------------

def test_flow1_register_with_drawing_request_opens_waiting_round(client):
    admin = _user("asd_admin1", role="ADMIN", team="CS")
    oid = _order()
    _as(client, admin)

    res = client.post(f"/api/orders/{oid}/as/register",
                      json={"as_content": "오른쪽 문 처짐", "drawing_request": {"memo": "문짝 1짝"}})

    body = res.get_json()
    assert res.status_code == 200, body
    assert body["as_drawing"] == "opened"
    sd = _sd(oid)
    rnd = asd.current_round(sd)
    assert rnd["status"] == asd.STATUS_WAITING and rnd["source"] == asd.SOURCE_AS_REQUEST
    assert rnd["memo"] == "문짝 1짝"
    assert rnd["cycle_id"] and rnd["cycle_id"] == asd.open_as_cycle_id(sd)
    assert sd[asd.AS_DRAWING_STATUS_KEY] == asd.STATUS_WAITING
    assert body["as_drawing_round"]["no"] == 1
    # 도면 담당이 없으면 도면팀 전체에 부탁 알림.
    notes = _notices(oid)
    assert [(n.title, n.target_team) for n in notes] == [("AS 도면 부탁", "DRAWING")]

    # 같은 AS 를 고쳐 다시 접수하며 또 부탁하면 이미 열려 있다.
    res2 = client.post(f"/api/orders/{oid}/as/register",
                       json={"as_content": "오른쪽 문 처짐(수정)", "drawing_request": {"memo": "x"}})
    assert res2.status_code == 200 and res2.get_json()["as_drawing"] == "already_open"
    assert len(asd.rounds(_sd(oid))) == 1


def test_flow1_request_goes_to_drawing_assignee(client):
    admin = _user("asd_admin2", role="ADMIN", team="CS")
    drafter = _user("asd_draw2")
    oid = _order(drawing_ids=[drafter.id])
    _as(client, admin)

    res = client.post(f"/api/orders/{oid}/as/register",
                      json={"as_content": "문 처짐", "drawing_request": {}})

    assert res.status_code == 200 and res.get_json()["as_drawing"] == "opened"
    notes = _notices(oid)
    assert [(n.target_type, n.target_user_id) for n in notes] == [("USER", drafter.id)]


def test_flow1_not_as_stage_registers_without_round(client):
    admin = _user("asd_admin3", role="ADMIN", team="CS")
    oid = _order(stage="CONSTRUCTION")
    _as(client, admin)

    res = client.post(f"/api/orders/{oid}/as/register",
                      json={"as_content": "문 처짐", "drawing_request": {"memo": "m"}})

    assert res.status_code == 200 and res.get_json()["as_drawing"] == "not_as_stage"
    assert asd.rounds(_sd(oid)) == []


def test_register_without_drawing_request_unchanged(client):
    admin = _user("asd_admin4", role="ADMIN", team="CS")
    oid = _order()
    _as(client, admin)

    res = client.post(f"/api/orders/{oid}/as/register", json={"as_content": "문 처짐"})

    assert res.status_code == 200 and res.get_json()["as_drawing"] is None
    assert asd.AS_DRAWING_KEY not in _sd(oid)
    assert _notices(oid) == []


# --------------------------------------------------------------------------
# 흐름 2 — 도면팀이 먼저 시작(AS 접수까지)
# --------------------------------------------------------------------------

def test_flow2_drawing_team_registers_as_and_starts(client):
    drafter = _user("asd_draw5")
    oid = _order()
    _as(client, drafter)

    res = _start(client, oid, memo="문짝 1짝", as_register={"content": "냉장고장 오른쪽 문 처짐"})

    body = res.get_json()
    assert res.status_code == 200, body
    assert body["data"]["registered_as"] is True and body["data"]["round"]["status"] == "IN_PROGRESS"
    sd = _sd(oid)
    cycle_id = asd.open_as_cycle_id(sd)
    assert cycle_id  # AS 접수가 생겼다
    assert "냉장고장 오른쪽 문 처짐" in (sd["shipment"]["as_content"] or "")
    rnd = asd.current_round(sd)
    assert rnd["source"] == asd.SOURCE_DRAWING_FIRST and rnd["registered_as"] is True
    assert rnd["cycle_id"] == cycle_id and rnd["opened_by"] == drafter.id
    db_session.expire_all()
    assert db_session.get(Order, oid).as_received_date  # 접수일 컬럼도 일반 접수와 같다
    # CS 팀에 "도면팀이 AS 를 접수했어요".
    assert [(n.title, n.target_team) for n in _notices(oid)] == [("도면팀이 AS를 접수했어요", "CS")]
    # 원래 최종 도면은 그대로.
    assert sd["drawing_current_files"][0]["key"].endswith("orig.png")
    assert sd["drawing_status"] == "CONFIRMED"


def test_flow2_binds_to_open_as_without_new_registration(client):
    admin = _user("asd_admin6", role="ADMIN", team="CS")
    drafter = _user("asd_draw6")
    oid = _order()
    _as(client, admin)
    assert client.post(f"/api/orders/{oid}/as/register", json={"as_content": "문 처짐"}).status_code == 200
    cycle_before = asd.open_as_cycle_id(_sd(oid))
    _as(client, drafter)

    res = _start(client, oid, memo="문짝")

    body = res.get_json()
    assert res.status_code == 200, body
    assert body["data"]["registered_as"] is False
    sd = _sd(oid)
    assert asd.open_as_cycle_id(sd) == cycle_before
    assert asd.current_round(sd)["cycle_id"] == cycle_before
    assert len(sd["as_lifecycle"]["cycles"]) == 1


def test_flow2_requires_content_when_no_as(client):
    drafter = _user("asd_draw7")
    oid = _order()
    _as(client, drafter)

    res = _start(client, oid, memo="m")

    assert res.status_code == 400 and res.get_json()["code"] == "AS_CONTENT_REQUIRED"
    assert asd.AS_DRAWING_KEY not in _sd(oid)


def test_start_guards(client):
    drafter = _user("asd_draw8")
    producer = _user("asd_prod8", team="PRODUCTION")
    oid_drawing_stage = _order(stage="DRAWING")
    oid = _order()

    _as(client, drafter)
    r1 = _start(client, oid_drawing_stage, memo="m", as_register={"content": "c"})
    assert r1.status_code == 409 and r1.get_json()["code"] == "NOT_AS_STAGE"

    _as(client, producer)
    assert _start(client, oid, memo="m", as_register={"content": "c"}).status_code == 403

    # 도면팀은 일반 AS 접수 API 로는 여전히 접수할 수 없다(이 시작 경로에서만).
    _as(client, drafter)
    assert client.post(f"/api/orders/{oid}/as/register", json={"as_content": "c"}).status_code == 403

    assert _start(client, oid, memo="m", as_register={"content": "c"}).status_code == 200
    r2 = _start(client, oid, memo="again")
    assert r2.status_code == 409 and r2.get_json()["code"] == "AS_DRAWING_OPEN"


# --------------------------------------------------------------------------
# 함께 — 시트 잠금 · 전달 · 확인
# --------------------------------------------------------------------------

def test_wizard_save_keeps_original_sheets_and_tags_new_ones(client, storage):
    drafter = _user("asd_draw9")
    oid = _order(drawing_ids=[drafter.id])
    _as(client, drafter)

    # 차수 없이: 원래 시트를 고쳐도 지키고, 새 시트는 버린다.
    r0 = _put(client, oid, [{"id": "s-1", "name": "바꾼 이름", "form": {}, "objects": []},
                            {"id": "s-x", "name": "새 시트", "form": {}, "objects": []}])
    assert r0.status_code == 200, r0.get_json()
    assert r0.get_json()["data"]["sheet_lock"] == {"kept": ["s-1"], "dropped": ["s-x"], "tagged": []}
    sheets = _sd(oid)["drawing_wizard"]["sheets"]
    assert [(s["id"], s["name"]) for s in sheets] == [("s-1", "냉장고장")]

    assert _start(client, oid, memo="문짝", as_register={"content": "문 처짐"}).status_code == 200
    round_id = asd.current_round(_sd(oid))["round_id"]

    # 차수가 열리면 새 시트에 차수 표시가 붙고, 원래 시트는 여전히 지킨다(빠뜨려도 되살린다).
    r1 = _put(client, oid, [{"id": "s-2", "name": "AS 문짝", "form": {}, "objects": []}])
    assert r1.status_code == 200, r1.get_json()
    assert r1.get_json()["data"]["sheet_lock"]["tagged"] == ["s-2"]
    sheets = _sd(oid)["drawing_wizard"]["sheets"]
    assert [s["id"] for s in sheets] == ["s-1", "s-2"]
    assert sheets[0].get(asd.SHEET_ROUND_KEY) is None and sheets[1][asd.SHEET_ROUND_KEY] == round_id


def test_waiting_round_moves_to_in_progress_on_first_as_sheet(client, storage):
    admin = _user("asd_admin10", role="ADMIN", team="CS")
    drafter = _user("asd_draw10")
    oid = _order(drawing_ids=[drafter.id])
    _as(client, admin)
    client.post(f"/api/orders/{oid}/as/register", json={"as_content": "문", "drawing_request": {}})
    assert asd.current_round(_sd(oid))["status"] == asd.STATUS_WAITING
    _as(client, drafter)

    r = _put(client, oid, [{"id": "s-1", "name": "냉장고장", "form": {}, "objects": []},
                           {"id": "s-2", "name": "AS", "form": {}, "objects": []}])

    assert r.status_code == 200, r.get_json()
    assert asd.current_round(_sd(oid))["status"] == asd.STATUS_IN_PROGRESS


def test_transfer_confirm_and_revision_keep_original_final_drawing(client, storage):
    drafter = _user("asd_draw11")
    sales = _user("asd_sales11", team="SALES")
    oid = _order(drawing_ids=[drafter.id])
    original = copy.deepcopy(_sd(oid))
    _as(client, drafter)
    assert _start(client, oid, memo="문짝", as_register={"content": "문 처짐"}).status_code == 200
    assert _put(client, oid, [{"id": "s-1", "name": "냉장고장", "form": {}, "objects": []},
                              {"id": "s-2", "name": "AS 문짝", "form": {}, "objects": []}]).status_code == 200

    # 아직 저장한 그림이 없으면 보낼 수 없다.
    r0 = client.post(f"/api/orders/{oid}/drawing/as/transfer", json={})
    assert r0.status_code == 400 and r0.get_json()["code"] == "NOTHING_TO_SEND"

    assert _sheet_png(client, oid, "s-2", "as1.png").status_code == 200
    r1 = client.post(f"/api/orders/{oid}/drawing/as/transfer", json={"note": "확인 부탁"})
    assert r1.status_code == 200, r1.get_json()
    sd = _sd(oid)
    rnd = asd.current_round(sd)
    assert rnd["status"] == asd.STATUS_TRANSFERRED
    assert [f["sheet_id"] for f in rnd["files"]] == ["s-2"] and rnd["files"][0]["key"].endswith("as1.png")
    assert "s-2" not in (sd["drawing_wizard"].get("pending") or {})
    for key in ("drawing_current_files", "drawing_status", "drawing_transfer_history"):
        assert sd[key] == original[key], key
    assert rnd["files"][0]["key"] in drawing_keys_in_use(sd)
    assert any(n.title == "AS 도면 왔어요" for n in _notices(oid))

    # 도면팀은 확인할 수 없다(영업 · CS 몫).
    assert client.post(f"/api/orders/{oid}/drawing/as/confirm").status_code == 403

    _as(client, sales)
    r_empty = client.post(f"/api/orders/{oid}/drawing/as/request-revision", json={"reason": " "})
    assert r_empty.status_code == 400 and r_empty.get_json()["code"] == "REASON_REQUIRED"
    r2 = client.post(f"/api/orders/{oid}/drawing/as/request-revision", json={"reason": "손잡이 위치"})
    assert r2.status_code == 200 and asd.current_round(_sd(oid))["status"] == asd.STATUS_RETURNED

    # 고친 판을 다시 보내면 같은 시트 자리를 바꾼다.
    _as(client, drafter)
    assert _sheet_png(client, oid, "s-2", "as2.png").status_code == 200
    r3 = client.post(f"/api/orders/{oid}/drawing/as/transfer", json={})
    assert r3.status_code == 200 and r3.get_json()["data"]["replaced"] == ["s-2"]
    sd = _sd(oid)
    files = asd.current_round(sd)["files"]
    assert len(files) == 1 and files[0]["key"].endswith("as2.png")
    # 옛 판 key 도 이력이 가리키므로 지우지 않는다.
    assert any(k.endswith("as1.png") for k in drawing_keys_in_use(sd))

    _as(client, sales)
    r4 = client.post(f"/api/orders/{oid}/drawing/as/confirm")
    assert r4.status_code == 200, r4.get_json()
    sd = _sd(oid)
    assert asd.current_round(sd) is None
    assert asd.rounds(sd)[0]["status"] == asd.STATUS_CONFIRMED
    assert sd[asd.AS_DRAWING_STATUS_KEY] == asd.STATUS_CONFIRMED
    for key in ("drawing_current_files", "drawing_status", "drawing_transfer_history"):
        assert sd[key] == original[key], key


def test_cancel_only_before_first_send(client, storage):
    drafter = _user("asd_draw13")
    oid = _order(drawing_ids=[drafter.id])
    _as(client, drafter)
    assert _start(client, oid, memo="m", as_register={"content": "c"}).status_code == 200

    res = client.post(f"/api/orders/{oid}/drawing/as/cancel", json={"reason": "잘못 눌렀어요"})

    assert res.status_code == 200, res.get_json()
    sd = _sd(oid)
    assert asd.current_round(sd) is None and asd.rounds(sd)[0]["status"] == asd.STATUS_CANCELLED
    assert asd.open_as_cycle_id(sd)  # 함께 만든 AS 접수는 남는다
    # 다시 시작하면 2차가 아니라 1차로 센다(그만둔 차수는 세지 않음).
    r2 = _start(client, oid, memo="다시")
    assert r2.status_code == 200 and r2.get_json()["data"]["round"]["no"] == 1


def test_get_view(client):
    drafter = _user("asd_draw14")
    oid = _order()
    _as(client, drafter)

    r0 = client.get(f"/api/orders/{oid}/drawing/as")
    d0 = r0.get_json()["data"]
    assert d0["as_stage"] is True and d0["can_start"] is True and d0["open_as"] is None

    _start(client, oid, memo="m", as_register={"content": "문 처짐"})
    d1 = client.get(f"/api/orders/{oid}/drawing/as").get_json()["data"]
    assert d1["can_start"] is False and d1["current"]["status"] == "IN_PROGRESS"
    assert "문 처짐" in d1["open_as"]["content"]


# --------------------------------------------------------------------------
# 순수 규칙 · 보존
# --------------------------------------------------------------------------

def test_form_save_keeps_as_drawing_keys():
    old_sd = {asd.AS_DRAWING_KEY: {"rounds": [{"round_id": "asd_1"}]}, asd.AS_DRAWING_STATUS_KEY: "WAITING"}
    new_sd = {"parties": {}}
    lock_server_owned_keys(old_sd, new_sd)
    assert new_sd[asd.AS_DRAWING_KEY] == old_sd[asd.AS_DRAWING_KEY]
    assert new_sd[asd.AS_DRAWING_STATUS_KEY] == "WAITING"
    assert "as_drawing" in _OPERATIONAL_TOP_LEVEL_KEYS and "as_drawing_status" in _OPERATIONAL_TOP_LEVEL_KEYS


def test_sheet_tags_are_server_owned_outside_as_stage():
    order = SimpleNamespace(structured_data={"workflow": {"stage": "DRAWING"}}, status="DRAWING",
                            is_erp_order=True)
    saved = [{"id": "a", "name": "a"}, {"id": "b", "name": "b", asd.SHEET_ROUND_KEY: "asd_x"}]
    incoming = [{"id": "a", "name": "a", asd.SHEET_ROUND_KEY: "forged"}, {"id": "b", "name": "b"},
                {"id": "c", "name": "c", asd.SHEET_ROUND_KEY: "forged"}]
    out, report = asd.apply_sheet_lock(order, {}, saved, incoming)
    assert [s.get(asd.SHEET_ROUND_KEY) for s in out] == [None, "asd_x", None]
    assert report == {"kept": [], "dropped": [], "tagged": []}


def test_drawing_keys_in_use_counts_as_drawing_history():
    sd = {asd.AS_DRAWING_KEY: {"rounds": [{
        "round_id": "asd_1", "files": [{"key": "k/now.png"}],
        "history": [{"action": "TRANSFER", "files": [{"key": "k/now.png"}],
                     "previous_files": [{"key": "k/old.png"}]}]}]}}
    keys = drawing_keys_in_use(sd)
    assert {"k/now.png", "k/old.png"} <= keys


def test_sheet_png_refuses_original_sheet_after_completion(client, storage):
    drafter = _user("asd_draw15")
    oid = _order(drawing_ids=[drafter.id])
    _as(client, drafter)

    r0 = _sheet_png(client, oid, "s-1", "x.png")  # 차수 없음
    assert r0.status_code == 409 and r0.get_json()["error"] == "SHEET_LOCKED"
    assert "AS 도면 시작" in r0.get_json()["message"]

    assert _start(client, oid, memo="m", as_register={"content": "c"}).status_code == 200
    r1 = _sheet_png(client, oid, "s-1", "x.png")  # 원래 시트
    assert r1.status_code == 409 and "AS 시트" in r1.get_json()["message"]
    assert _sheet_png(client, oid, "s-new", "y.png").status_code == 200  # 아직 저장 안 된 새 시트는 받는다
    assert "s-1" not in (_sd(oid)["drawing_wizard"].get("pending") or {})

