"""패킹 자료는 패킹 API 만 쓴다 — 폼 저장 · 초안 자동 저장 · 주문 만들기가 덮지 못한다(2026-11-24, 3단계 ⑦).

``structured_data.shipment.packing`` = 줄 체크(items) · 출발 보고(departed_at · departed_by_name) · 공장 꼴(layout) ·
공장 상차 완료(factory_loaded). 예전엔 주문 폼 저장(PUT structured)이 ``shipment`` 를 깊이 합치면서(_merge_preserving_missing)
폼이 실어 온 ``shipment.packing`` 이 서버 값을 덮었다 — 폼은 연 순간의 스냅샷을 되실어 보내므로, 그사이 현장에서 체크 · 출발 보고한
기록이 옛 값으로 돌아갔다. 생산 쪽 ``production.factory_done`` 과 같은 꼴로 하위 열쇠를 잠근다(old-wins), 만들기 · 초안 자동
저장은 손님 쪽 값을 버린다(``strip_client_packing_state`` — ``drawing_factory.strip_client_factory_state`` 와 같은 꼴).
"""
from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.erp_display import get_today_kst
from foms.services.orders.order_create import _prepare_structured
from foms.services.orders.structured_form_projection import SERVER_LOCKED_SUBKEYS, lock_server_owned_keys
from foms.services.shipment.packing_factory import strip_client_packing_state
from models import Order, User

SERVER = {"items": [{"key": "sheet:a-s0", "label": "도면 1", "qty": 1, "checked": True, "by_name": "김시공"}],
          "layout": "factory", "departed_at": "2026-11-24T05:48:00+00:00", "departed_by_name": "김시공",
          "factory_loaded": {"1": {"at": "2026-11-24T05:40:00+00:00", "by_name": "김시공", "keys": ["sheet:a-s0"]}}}


def test_lock_keeps_server_packing_whole():
    assert SERVER_LOCKED_SUBKEYS["shipment"] == ("packing",)
    old = {"shipment": {"construction_workers": ["김시공"], "packing": SERVER}}
    stale = {"shipment": {"construction_workers": ["박시공"],
                          "packing": {"items": [], "departed_at": None, "layout": None, "factory_loaded": {}}}}
    assert lock_server_owned_keys(old, stale) == ["shipment.packing"]
    assert stale["shipment"] == {"construction_workers": ["박시공"], "packing": SERVER}  # 다른 출고 칸은 폼 값 그대로
    bare = {"shipment": {"construction_workers": []}}
    lock_server_owned_keys(old, bare)
    assert bare["shipment"]["packing"] == SERVER  # 폼이 안 보내도 서버 값
    planted = {"shipment": {"packing": {"items": [], "departed_at": "2026-01-01T00:00:00+00:00"}}}
    assert lock_server_owned_keys({"shipment": {}}, planted) == ["shipment.packing"]
    assert "packing" not in planted["shipment"]  # 서버에 없는 패킹을 폼이 새로 심지 못함


def test_structured_put_cannot_rewrite_packing(client):
    u = User(username="pso-admin", password=generate_password_hash("x"), role="ADMIN", team="CS", name="가짜관리",
             is_active=True)
    db_session.add(u)
    today = get_today_kst().isoformat()
    o = Order(received_date=today, customer_name="가짜", phone="010-0000-0000", address="가짜시 1", product="장",
              status="CONSTRUCTION", is_erp_order=True,
              structured_data={"workflow": {"stage": "CONSTRUCTION"}, "parties": {"customer": {"name": "가짜", "phone": "010-0000-0000"}},
                               "site": {"address_full": "가짜시 1"}, "items": [{"product_name": "가짜장", "spec_width": "2400"}],
                               "shipment": {"construction_workers": ["김시공"], "packing": SERVER}})
    db_session.add(o)
    db_session.commit()
    with client.session_transaction() as s:
        s["user_id"], s["username"], s["role"] = u.id, u.username, u.role
    snap = client.get(f"/api/orders/{o.id}/structured").get_json()["structured_data"]
    snap["shipment"]["packing"] = {"items": [{"key": "sheet:a-s0", "checked": False}], "departed_at": None,
                                   "departed_by_name": None, "layout": None, "factory_loaded": {}}
    snap["shipment"]["construction_time"] = "오후 2시"
    res = client.put(f"/api/orders/{o.id}/structured", json={"structured_data": snap})
    assert res.status_code == 200, res.get_json()
    db_session.remove()
    shipment = db_session.get(Order, o.id).structured_data["shipment"]
    assert shipment["packing"] == SERVER and shipment["construction_time"] == "오후 2시"


def test_create_and_autosave_drop_client_packing():
    sd = {"shipment": {"construction_workers": ["김시공"], "packing": SERVER}}
    assert strip_client_packing_state(sd) == ["shipment.packing"] and sd == {"shipment": {"construction_workers": ["김시공"]}}
    assert strip_client_packing_state({"items": []}) == [] and strip_client_packing_state(None) == []
    import datetime

    made = _prepare_structured({"shipment": {"packing": SERVER}}, 1, datetime.datetime(2026, 11, 24))
    assert "packing" not in (made.get("shipment") or {})


def test_autosave_path_strips_packing(client):
    u = User(username="pso-cs", password=generate_password_hash("x"), role="STAFF", team="CS", name="가짜상담", is_active=True)
    db_session.add(u)
    db_session.commit()
    with client.session_transaction() as s:
        s["user_id"], s["username"], s["role"] = u.id, u.username, u.role
    res = client.post("/api/orders/erp/draft/autosave", json={
        "structured_data": {"parties": {"customer": {"name": "가짜초안", "phone": "010-1111-2222"}},
                            "items": [{"product_name": "가짜장"}], "shipment": {"packing": SERVER}}})
    body = res.get_json()
    assert res.status_code == 200 and body.get("order_id"), body
    db_session.remove()
    sd = db_session.get(Order, body["order_id"]).structured_data
    assert "packing" not in (sd.get("shipment") or {})
