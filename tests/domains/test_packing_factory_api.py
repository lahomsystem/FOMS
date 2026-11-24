"""출고 패킹 공장마다 — API · 자료 규칙(설계서 2026-11-23 '승인 때 고친 것' 6 ② ③, 3단계 ⑦ B). 이름은 모두 지어낸 값이다.

* 2공장 장이 섞인 주문만 공장 꼴: 공장마다 [도면 한 장 = 한 줄 · "철물 · 기타" 한 줄 · 더한 줄], 열쇠 = 시트 신원(직접 올린 파일 = 저장 key).
* 공장마다 [N공장 상차 완료](그 공장 줄을 모두 체크해야), 둘째 공장이 되는 순간 출발 보고(departed_at) 처리.
* 생산팀 파트 계정 · 반장은 자기 공장 줄만, 시공 · 출고 · 관리자는 둘 다. 1공장뿐인 주문은 지금 목록 그대로(1공장 몫).
* 바뀌는 경우: 옛 꼴 패킹이 있는 주문에 2공장이 생김(안내 · 기록 남김) · 섞인 주문이 1공장만 됨(공장 꼴 그대로) · 장이 늘거나 줆.

되돌리면 실패: 남의 공장 줄을 받음 · 한 공장만 상차했는데 출발 보고 · 새 장이 와도 상차 완료가 살아 있음 · 옛 체크 기록을 지움 ·
1공장뿐인 주문 응답이 바뀜 · 생산팀 매니저 GET 403.
"""
from __future__ import annotations

import itertools

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.construction.tablet_first import _packing_fields
from foms.services.datetime_kst import format_datetime_kst
from foms.services.erp_display import get_today_kst
from foms.services.shipment import packing_factory as pf
from models import Order, OrderEvent, User

_seq = itertools.count(1)
URL = "/api/erp/shipment/packing/{}"


def _user(client, *, role="STAFF", team="CONSTRUCTION", name=None, parts=None, lead=False, factory=None) -> User:
    n = next(_seq)
    u = User(username=f"pf-{n}", password=generate_password_hash("x"), role=role, team=team, name=name or f"가짜{n}",
             is_active=True)
    if parts:
        u.production_part = parts[0]
        u.production_parts = list(parts)
    if lead:
        u.production_lead = True
    if factory == 2:
        u.production_factory = 2
    db_session.add(u)
    db_session.commit()
    with client.session_transaction() as s:
        s["user_id"], s["username"], s["role"] = u.id, u.username, u.role
    return u


def _sd(*, n=5, f2=(3, 4), packing=None, direct=0) -> dict:
    code = f"o{next(_seq)}"
    files = [{"key": f"orders/x/drawing/{code}_{j}.png", "filename": f"{code}-도면{j + 1}.png", "sheet_id": f"{code}-s{j}"}
             for j in range(n)]
    files += [{"key": f"orders/x/up/{code}_{j}.pdf", "filename": f"현장사진{j + 1}.pdf"} for j in range(direct)]
    sd = {"workflow": {"stage": "CONSTRUCTION"}, "items": [{"product_name": "붙박이장"}, {"product_name": "화장대"}],
          "drawing_current_files": files,
          "drawing_wizard": {"sheets": [{"id": f"{code}-s{j}", "name": f"방{j}", "product_index": 0 if j < 3 else 1}
                                        for j in range(n)]}}
    if f2:
        sd["drawing_factory"] = {"sheets": {f"{code}-s{j}": 2 for j in f2}, "files": {}}
    if packing is not None:
        sd["shipment"] = {"packing": packing}
    return sd


def _order(sd: dict) -> int:
    today = get_today_kst().isoformat()
    o = Order(received_date=today, customer_name="가짜고객", phone="010-0000-0000", address="가짜시", product="붙박이장",
              status="CONSTRUCTION", scheduled_date=today, is_erp_order=True, erp_stage_code="CONSTRUCTION", structured_data=sd)
    db_session.add(o)
    db_session.commit()
    return o.id


def _fresh(oid: int) -> dict:
    db_session.remove()
    return db_session.get(Order, oid).structured_data


def _keys(data: dict, factory: int, kind: str | None = None) -> list[str]:
    return [i["key"] for i in data["items"] if i["factory"] == factory and (kind is None or i["kind"] == kind)]


def _check(client, oid: int, keys: list[str], on: bool = True):
    return client.post(URL.format(oid), json={"updates": [{"key": k, "checked": on} for k in keys]})


# --------------------------------------------------------------------------- #
# 줄 모양
# --------------------------------------------------------------------------- #
def test_mixed_order_groups_sheet_lines_and_hardware(client):
    _user(client, role="ADMIN", team="CS")
    oid = _order(_sd(direct=1))
    res = client.get(URL.format(oid))
    data = res.get_json()["data"]
    assert data["layout"] == "factory" and data["persisted"] is False
    assert [g["factory"] for g in data["groups"]] == [1, 2] and data["can_check"] == [1, 2]
    labels = [(i["factory"], i["label"]) for i in data["items"]]
    assert labels == [(1, "도면 1 붙박이장"), (1, "도면 2 붙박이장"), (1, "도면 3 붙박이장"), (1, "도면 6 현장사진1.pdf"),
                      (1, "철물 · 기타"), (2, "도면 4 화장대"), (2, "도면 5 화장대"), (2, "철물 · 기타")]
    assert _keys(data, 1, "hardware") == ["hardware:1"] and _keys(data, 2, "hardware") == ["hardware:2"]
    assert _keys(data, 1, "sheet")[0].startswith("sheet:o") and _keys(data, 1, "sheet")[-1].startswith("file:orders/x/up/")
    assert [(g["checked"], g["total"], g["loaded"]) for g in data["groups"]] == [(0, 5, None), (0, 3, None)]


def test_plain_order_keeps_today_list_and_payload_keys(client):
    """1공장뿐 — 지금 목록(제품마다 3줄), 응답 칸도 지금 그대로(공장 칸 없음)."""
    _user(client, team="SHIPMENT")
    oid = _order(_sd(f2=()))
    data = client.get(URL.format(oid)).get_json()["data"]
    assert set(data) == {"items", "checked_count", "issues_count", "total", "persisted", "departed_at", "departed_by_name"}
    assert [i["key"] for i in data["items"]][:3] == ["item0_body", "item0_door", "item0_hardware"]


# --------------------------------------------------------------------------- #
# 공장마다 상차 완료 → 출발 보고 자동
# --------------------------------------------------------------------------- #
def test_two_factory_loads_then_departed_automatically(client):
    _user(client, team="CONSTRUCTION", name="김시공")
    oid = _order(_sd())
    data = client.get(URL.format(oid)).get_json()["data"]
    f1, f2 = _keys(data, 1), _keys(data, 2)
    early = client.post(URL.format(oid), json={"loaded": 1})
    assert early.status_code == 400 and early.get_json()["data"]["code"] == "PACKING_FACTORY_NOT_READY"
    assert early.get_json()["error"] == "1공장 줄을 모두 체크해야 상차 완료할 수 있어요."
    assert _check(client, oid, f1).status_code == 200
    one = client.post(URL.format(oid), json={"loaded": 1}).get_json()["data"]
    assert one["groups"][0]["loaded"]["by_name"] == "김시공" and one["groups"][1]["loaded"] is None
    assert one["departed_at"] is None  # 한 공장만 — 출발 보고 아님
    _check(client, oid, f2)
    two = client.post(URL.format(oid), json={"loaded": 2}).get_json()["data"]
    assert two["departed_at"] and two["departed_by_name"] == "김시공"
    events = [e.event_type for e in db_session.query(OrderEvent).filter_by(order_id=oid).order_by(OrderEvent.id)]
    assert events.count("PACKING_FACTORY_LOADED") == 1 and events[-1] == "PACKING_DEPARTED"
    sd = _fresh(oid)
    packing = sd["shipment"]["packing"]
    assert packing["layout"] == "factory" and set(packing["factory_loaded"]) == {"1", "2"}
    assert packing["factory_loaded"]["1"]["keys"] == f1
    # departed_at 을 읽는 시공 태블릿 '출고' 칸이 그대로 돈다(폰 카드 "출발 보고됨"은 test_packing_factory_screens.py)
    assert _packing_fields(sd) == (f"출발 {format_datetime_kst(packing['departed_at'], '%H:%M')}", "departed")  # 한국 시각


def test_uncheck_after_load_keeps_record_and_new_sheet_reopens_factory(client):
    """체크를 풀어도 상차 완료 기록은 그대로(지금 '출발 뒤 체크 풀기'와 같다). 새 장이 오면 그 공장 상차 완료가 풀린다."""
    _user(client, team="SHIPMENT")
    oid = _order(_sd())
    data = client.get(URL.format(oid)).get_json()["data"]
    _check(client, oid, _keys(data, 1))
    client.post(URL.format(oid), json={"loaded": 1})
    after = _check(client, oid, _keys(data, 1)[:1], on=False).get_json()["data"]
    assert after["groups"][0]["loaded"] is not None and after["groups"][0]["checked"] == 3
    o = db_session.get(Order, oid)
    sd = dict(o.structured_data)
    sd["drawing_current_files"] = sd["drawing_current_files"] + [{"key": "orders/x/new.png", "filename": "새도면.png"}]
    o.structured_data = sd
    db_session.commit()
    again = client.get(URL.format(oid)).get_json()["data"]
    assert again["groups"][0]["loaded"] is None and again["groups"][0]["total"] == 5


def test_old_depart_button_on_mixed_order_needs_all_and_loads_remaining(client):
    _user(client, team="SHIPMENT")
    oid = _order(_sd())
    data = client.get(URL.format(oid)).get_json()["data"]
    _check(client, oid, _keys(data, 1))
    half = client.post(URL.format(oid), json={"departed": True})
    assert half.status_code == 400 and half.get_json()["error"] == "전 항목 체크 후 출발 보고"
    _check(client, oid, _keys(data, 2))
    done = client.post(URL.format(oid), json={"departed": True}).get_json()["data"]
    assert done["departed_at"] and all(g["loaded"] for g in done["groups"])


# --------------------------------------------------------------------------- #
# 권한 — 생산팀은 자기 공장 줄만
# --------------------------------------------------------------------------- #
def test_factory2_lead_checks_only_own_factory(client):
    _user(client, team="PRODUCTION", name="강반장", lead=True, factory=2)
    oid = _order(_sd())
    data = client.get(URL.format(oid)).get_json()["data"]
    assert data["can_check"] == [2] and [g["can_check"] for g in data["groups"]] == [False, True]
    before = _fresh(oid)
    res = _check(client, oid, _keys(data, 1)[:1])
    assert res.status_code == 403 and res.get_json()["data"]["code"] == "PACKING_FACTORY_FORBIDDEN"
    assert res.get_json()["error"] == "1공장 줄은 1공장에서 체크해요. 내 공장(2공장) 줄만 체크할 수 있어요."
    assert _fresh(oid) == before  # 쓰기 0
    assert client.post(URL.format(oid), json={"loaded": 1}).status_code == 403
    assert _check(client, oid, _keys(data, 2)).status_code == 200
    loaded = client.post(URL.format(oid), json={"loaded": 2}).get_json()["data"]
    assert loaded["groups"][1]["loaded"]["by_name"] == "강반장" and loaded["departed_at"] is None
    # 더하기는 자기 공장으로(고르기 없음)
    added = client.post(URL.format(oid), json={"add": {"label": "상판 유리", "qty": 2}}).get_json()["data"]
    assert [i["factory"] for i in added["items"] if i["label"] == "상판 유리"] == [2]


def test_factory1_part_account_writes_plain_order_factory2_cannot(client):
    """1공장뿐인 주문 = 모든 줄이 1공장 몫 — 1공장 파트 계정은 체크(새 권한), 2공장 계정은 403."""
    oid = _order(_sd(f2=()))
    _user(client, team="PRODUCTION", parts=["cut"])
    assert _check(client, oid, ["item0_body"]).status_code == 200
    _user(client, team="PRODUCTION", parts=["cut"], factory=2)
    res = _check(client, oid, ["item0_door"])
    assert res.status_code == 403 and res.get_json()["data"]["code"] == "PACKING_FACTORY_FORBIDDEN"


def test_admin_add_needs_factory_choice_on_mixed_order(client):
    _user(client, role="ADMIN", team="CS")
    oid = _order(_sd())
    res = client.post(URL.format(oid), json={"add": {"label": "경첩"}})
    assert res.status_code == 400 and res.get_json()["data"]["code"] == "PACKING_FACTORY_REQUIRED"
    ok = client.post(URL.format(oid), json={"add": {"label": "경첩", "factory": 2}}).get_json()["data"]
    assert [(i["factory"], i["kind"]) for i in ok["items"] if i["label"] == "경첩"] == [(2, "custom")]
    assert client.post(URL.format(oid), json={"loaded": 3}).status_code == 400


def test_loaded_on_plain_order_is_refused(client):
    _user(client, team="SHIPMENT")
    oid = _order(_sd(f2=()))
    res = client.post(URL.format(oid), json={"loaded": 1})
    assert res.status_code == 400 and "packing" not in (_fresh(oid).get("shipment") or {})


@pytest.mark.parametrize("role,team,status", [
    ("MANAGER", "PRODUCTION", 200),  # 예전: POST 는 되는데 GET 403 — 이제 같이 됨
    ("MANAGER", "DRAWING", 200),
    ("VIEWER", "SHIPMENT", 200),  # 예전 읽기 문 그대로(조회 전용)
    ("STAFF", "PRODUCTION", 403),  # 파트도 반장도 아닌 생산팀(보기만)
    ("VIEWER", "PRODUCTION", 403),
])
def test_get_gate_matches_write_policy(client, role, team, status):
    _user(client, role=role, team=team)
    assert client.get(URL.format(_order(_sd()))).status_code == status


# --------------------------------------------------------------------------- #
# 바뀌는 경우 — 기록을 조용히 잃지 않는다
# --------------------------------------------------------------------------- #
def test_legacy_checks_get_notice_and_stay_stored(client):
    """옛 꼴(제품 3줄)로 2줄 체크한 주문에 2공장 장이 생김 → 공장 꼴 + "다시 체크" 안내, 옛 줄은 지우지 않는다."""
    legacy = [{"key": f"item0_{s}", "label": f"붙박이장 {s}", "qty": 1, "checked": s != "hardware", "at": None,
               "by_name": "박출고", "issue": None} for s in ("body", "door", "hardware")]
    legacy.append({"key": "custom_1_3", "label": "상판 유리", "qty": 1, "checked": True, "at": None, "by_name": "박출고",
                   "issue": None})
    _user(client, team="SHIPMENT")
    oid = _order(_sd(packing={"items": legacy, "updated_at": None}))
    data = client.get(URL.format(oid)).get_json()["data"]
    assert data["layout"] == "factory" and data["legacy_count"] == 2
    assert not [i for i in data["items"] if i["key"].startswith("item0_")]
    assert [(i["factory"], i["checked"]) for i in data["items"] if i["key"] == "custom_1_3"] == [(1, True)]  # 더한 줄은 1공장으로 살아남음
    _check(client, oid, _keys(data, 2)[:1])
    stored = {r["key"]: r for r in _fresh(oid)["shipment"]["packing"]["items"]}
    assert stored["item0_body"]["checked"] is True and stored["item0_door"]["checked"] is True  # 기록 그대로


def test_back_to_one_factory_keeps_factory_layout_and_checks(client):
    """섞인 주문이 다시 1공장만 됨 → 공장 꼴로 저장했으면 그대로(1공장 묶음 하나), 옮겨 온 장의 체크도 따라온다."""
    _user(client, team="SHIPMENT")
    oid = _order(_sd())
    data = client.get(URL.format(oid)).get_json()["data"]
    moved = _keys(data, 2, "sheet")[0]
    _check(client, oid, [moved])
    o = db_session.get(Order, oid)
    sd = dict(o.structured_data)
    sd["drawing_factory"] = {"sheets": {}, "files": {}}
    o.structured_data = sd
    db_session.commit()
    back = client.get(URL.format(oid)).get_json()["data"]
    assert back["layout"] == "factory" and [g["factory"] for g in back["groups"]] == [1]
    assert [i["checked"] for i in back["items"] if i["key"] == moved] == [True]
    assert pf.packing_glance(_fresh(oid))["text"] == "1/6"


def test_sheet_removed_hides_line_but_keeps_state_and_load(client):
    _user(client, team="SHIPMENT")
    oid = _order(_sd())
    data = client.get(URL.format(oid)).get_json()["data"]
    _check(client, oid, _keys(data, 2))
    client.post(URL.format(oid), json={"loaded": 2})
    o = db_session.get(Order, oid)
    sd = dict(o.structured_data)
    sd["drawing_current_files"] = sd["drawing_current_files"][:4]  # 2공장 장 하나 빠짐(품목 취소 등)
    o.structured_data = sd
    db_session.commit()
    after = client.get(URL.format(oid)).get_json()["data"]
    assert after["groups"][1]["total"] == 2 and after["groups"][1]["loaded"] is not None  # 빠짐은 상차 완료를 안 깸


def test_glance_texts():
    assert pf.packing_glance({"items": []}) is None
    sd = _sd()
    assert pf.packing_glance(sd) == {"text": "1공장 0/4 · 2공장 0/3", "present": False, "departed": False, "groups": 2}


@pytest.mark.parametrize("extra,status", [({"parts": ["cut"]}, 200), ({"lead": True}, 200), ({}, 403)])
def test_auth_guard_lets_production_writers_through(client, app, extra, status):
    """AUTH-01 앞문(정책 PACKING_WRITE 문지기)도 같은 함수 — 파트 계정 · 반장 통과, 보기만 생산팀은 앞문 403."""
    sentinel = object()
    prev = app.config.get("AUTH_POLICY_ENABLED", sentinel)
    app.config["AUTH_POLICY_ENABLED"] = True
    try:
        _user(client, team="PRODUCTION", **extra)
        res = _check(client, _order(_sd()), ["hardware:1"])
        assert res.status_code == status, res.get_data(as_text=True)
        assert res.headers.get("X-Auth-Policy") == (None if status == 200 else "denied")
    finally:
        if prev is sentinel:
            app.config.pop("AUTH_POLICY_ENABLED", None)
        else:
            app.config["AUTH_POLICY_ENABLED"] = prev
