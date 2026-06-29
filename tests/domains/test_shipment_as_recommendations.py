"""Shipment dashboard AS schedule recommendation API contracts."""

import copy
from datetime import date
from pathlib import Path

from sqlalchemy.orm.attributes import flag_modified
from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderScheduleDate, User

import foms.api.shipment.recommendations as shipment_rec_api
import foms.services.shipment_as_recommendation_cache as shipment_rec_cache
from foms.services.schedule_recommendations import recommend_nearby_schedules_for_targets


def _login_cs_staff(client, username: str) -> User:
    """STAFF + CS can call shipment recommendation APIs."""
    user = User(
        username=username,
        password=generate_password_hash("secret"),
        role="STAFF",
        team="CS",
        name="Shipment Rec Tester",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _login_construction_admin(client) -> User:
    """ADMIN + CONSTRUCTION hits the shipment-domain construction block."""
    user = User(
        username="shipment_as_rec_construction_admin",
        password=generate_password_hash("secret"),
        role="ADMIN",
        team="CONSTRUCTION",
        name="Constr Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _make_shipment_target_order() -> Order:
    today = date.today().strftime("%Y-%m-%d")
    order = Order(
        received_date=today,
        customer_name="출고 추천 대상",
        phone="010-3333-4444",
        address="Seoul Gangnam",
        product="장",
        status="IN_CONSTRUCTION",
        is_erp_order=True,
        structured_data={
            "schedule": {"construction": {"date": today}},
            "shipment": {"construction_workers": ["A"]},
        },
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(
        OrderScheduleDate(
            order_id=order.id,
            kind="construction",
            date=today,
            source="beta_schedule",
        )
    )
    db_session.commit()
    return order


def test_as_recommendations_batch_requires_order_ids(client) -> None:
    _login_cs_staff(client, "shipment-rec-empty")
    response = client.post("/api/erp/shipment/as-recommendations", json={})
    assert response.status_code == 400
    assert response.get_json()["success"] is False


def test_as_recommendations_forbidden_for_construction_admin(client) -> None:
    _login_construction_admin(client)
    response = client.post(
        "/api/erp/shipment/as-recommendations", json={"order_ids": [1]}
    )
    assert response.status_code == 403
    message = response.get_json().get("message", "")
    assert "시공팀" in message


def test_as_recommendations_batch_success_shape(client, monkeypatch) -> None:
    _login_cs_staff(client, "shipment-rec-batch")
    order = _make_shipment_target_order()

    def fake_recommend(**kwargs):
        targets_in = kwargs.get("targets") or []
        outs = []
        for t in targets_in:
            outs.append(
                {
                    "order_id": t["order_id"],
                    "customer_name": t.get("customer_name", ""),
                    "address": t.get("address", ""),
                    "target_date": t.get("target_date", ""),
                    "workers": t.get("workers") or [],
                    "recommendations": [],
                }
            )
        return {"targets": outs, "partial": False, "warnings": []}

    monkeypatch.setattr(
        shipment_rec_api, "recommend_nearby_schedules_for_targets", fake_recommend
    )

    response = client.post(
        "/api/erp/shipment/as-recommendations",
        json={"order_ids": [order.id]},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["per_target_limit"] == 2
    assert isinstance(payload["warnings"], list)
    assert "targets" in payload
    targets = payload["targets"]
    assert len(targets) == 1
    assert targets[0]["order_id"] == order.id
    assert "linked_as_schedules" in targets[0]


def test_as_recommendations_apply_requires_body_fields(client) -> None:
    _login_cs_staff(client, "shipment-rec-apply-val")
    response = client.post("/api/erp/shipment/as-recommendations/apply", json={})
    assert response.status_code == 400
    assert response.get_json()["success"] is False


def test_as_recommendations_cancel_requires_body_fields(client) -> None:
    _login_cs_staff(client, "shipment-rec-cancel-val")
    response = client.post("/api/erp/shipment/as-recommendations/cancel", json={})
    assert response.status_code == 400
    assert response.get_json()["success"] is False


class _StubRouteConverter:
    """Minimal FOMSAddressConverter stand-in for batch recommendation tests."""

    def __init__(self, route_payload: dict) -> None:
        self._route_payload = route_payload

    def analyze_address(self, address: str):
        a = str(address)
        if "SHIP_TGT_MARK" in a:
            return (37.0, 127.0, "ok", None)
        if "AS_CAND_MARK" in a:
            return (37.05, 127.05, "ok", None)
        return (37.0, 127.0, "ok", None)

    def calculate_route(self, slat, slng, elat, elng, timeout=None):
        return dict(self._route_payload)


def test_recommend_no_fallback_when_route_succeeds_but_over_duration_cap() -> None:
    """§2.4.15: successful routes that exceed 30min must not become token fallback rows."""
    conv = _StubRouteConverter(
        {"status": "success", "distance_km": 12.0, "duration_min": 45}
    )
    out = recommend_nearby_schedules_for_targets(
        converter=conv,
        targets=[
            {
                "order_id": 1,
                "customer_name": "S",
                "address": "서울 SHIP_TGT_MARK",
                "target_date": "2026-05-04",
                "workers": [],
            }
        ],
        candidates=[
            {
                "order_id": 200,
                "customer_name": "A",
                "address": "서울 AS_CAND_MARK",
                "current_visit_date": "",
                "sort_date": "2026-01-01",
                "as_info_id": 1,
            }
        ],
        per_target_limit=2,
        duration_limit_min=30,
        route_candidates_per_target=10,
        include_workers=True,
    )
    tgt = out["targets"][0]
    assert tgt["recommendations"] == []
    assert "30분" in tgt["message"]
    assert tgt["message"] != ""


def test_recommend_excludes_already_scheduled_as_candidates() -> None:
    conv = _StubRouteConverter({"status": "success", "distance_km": 4.0, "duration_min": 12})
    out = recommend_nearby_schedules_for_targets(
        converter=conv,
        targets=[
            {
                "order_id": 1,
                "customer_name": "S",
                "address": "서울 SHIP_TGT_MARK",
                "target_date": "2026-05-04",
                "workers": [],
            }
        ],
        candidates=[
            {
                "order_id": 200,
                "customer_name": "Already",
                "address": "서울 AS_CAND_MARK scheduled",
                "current_visit_date": "2026-05-06",
                "sort_date": "2026-01-01",
                "as_info_id": 1,
            },
            {
                "order_id": 201,
                "customer_name": "Open",
                "address": "서울 AS_CAND_MARK open",
                "current_visit_date": "",
                "sort_date": "2026-01-02",
                "as_info_id": 2,
            },
        ],
        per_target_limit=2,
        duration_limit_min=30,
        route_candidates_per_target=10,
        include_workers=True,
    )
    recs = out["targets"][0]["recommendations"]
    assert [r["as_order_id"] for r in recs] == [201]
    assert out["targets"][0]["lat"] == 37.0
    assert out["targets"][0]["lng"] == 127.0
    assert recs[0]["lat"] == 37.05
    assert recs[0]["lng"] == 127.05
    assert all(not r.get("already_scheduled") for r in recs)


def test_recommend_carries_as_content_text_to_result() -> None:
    conv = _StubRouteConverter({"status": "success", "distance_km": 4.0, "duration_min": 12})
    out = recommend_nearby_schedules_for_targets(
        converter=conv,
        targets=[
            {
                "order_id": 1,
                "customer_name": "S",
                "address": "서울 SHIP_TGT_MARK",
                "target_date": "2026-05-04",
                "workers": [],
            }
        ],
        candidates=[
            {
                "order_id": 201,
                "customer_name": "Open",
                "address": "서울 AS_CAND_MARK open",
                "current_visit_date": "",
                "sort_date": "2026-01-02",
                "as_info_id": 2,
                "as_content_text": "힌지 교체 필요\n문짝 처짐",
                "as_content_html": "<div><b>힌지 교체 필요</b><br><br>문짝 처짐</div>",
            },
        ],
        per_target_limit=2,
        duration_limit_min=30,
        route_candidates_per_target=10,
        include_workers=True,
    )
    rec = out["targets"][0]["recommendations"][0]
    assert rec["as_content_text"] == "힌지 교체 필요\n문짝 처짐"
    assert rec["as_content_html"] == "<div><b>힌지 교체 필요</b><br><br>문짝 처짐</div>"


def test_candidate_pool_extracts_safe_as_content_text(client) -> None:
    today = date.today().strftime("%Y-%m-%d")
    order = Order(
        received_date=today,
        customer_name="AS 내용 후보",
        phone="010-0000-0000",
        address="서울 AS_CAND_MARK 내용",
        product="AS",
        status="AS_RECEIVED",
        is_erp_order=True,
        structured_data={
            "shipment": {
                "as_content": "<div>상부 레일 불량<script>alert(1)</script></div>",
                "as_content_2": "<div>방문 전 연락 필요</div>",
            },
            "as_info": [{"id": 7, "status": "OPEN"}],
        },
    )
    db_session.add(order)
    db_session.commit()

    pool = shipment_rec_cache._build_candidate_pool_payload(
        db_session,
        _StubRouteConverter({"status": "success", "distance_km": 1.0, "duration_min": 5}),
        source_value=shipment_rec_api.SHREC_SOURCE,
        as_statuses=("AS_RECEIVED",),
        log_warning=None,
    )

    row = next(c for c in pool["candidates"] if c["order_id"] == order.id)
    assert "상부 레일 불량" in row["as_content_text"]
    assert "방문 전 연락 필요" in row["as_content_text"]
    assert "<script>" not in row["as_content_text"]
    assert "<script>" not in row["as_content_html"]
    assert "레일 불량" in row["as_content_html"]
    assert "연락 필요" in row["as_content_html"]
    assert row["as_info_id"] == 7


def test_candidate_pool_as_content_html_includes_notes_when_tab2_absent(client) -> None:
    """as_dashboard와 동일: shipment에 as_content_2 키가 없으면 notes를 탭2 소스로 sanitize."""
    today = date.today().strftime("%Y-%m-%d")
    order = Order(
        received_date=today,
        customer_name="notes tab2",
        phone="010-0000-0000",
        address="서울 AS_CAND_MARK notes2",
        product="AS",
        status="AS_RECEIVED",
        is_erp_order=True,
        notes="<font color='red'>노트내용</font>",
        structured_data={
            "shipment": {"as_content": "<b>본문</b>"},
            "as_info": [{"id": 9, "status": "OPEN"}],
        },
    )
    db_session.add(order)
    db_session.commit()

    pool = shipment_rec_cache._build_candidate_pool_payload(
        db_session,
        _StubRouteConverter({"status": "success", "distance_km": 1.0, "duration_min": 5}),
        source_value=shipment_rec_api.SHREC_SOURCE,
        as_statuses=("AS_RECEIVED",),
        log_warning=None,
    )
    row = next(c for c in pool["candidates"] if c["order_id"] == order.id)
    assert "본문" in row["as_content_html"]
    assert "노트내용" in row["as_content_html"]
    assert "<font color=\"red\">노트내용</font>" in row["as_content_html"] or "red" in row["as_content_html"]


def test_shipment_as_recommendation_map_reuses_global_leaflet_instance() -> None:
    # Batch 5: inline JS가 static/js/shipment/shipment-dashboard.js로 이동 → 표면 합본 검사
    root = Path(__file__).resolve().parents[2]
    src = (
        (root / "templates/shipment/partials/dashboard_main.html").read_text(encoding="utf-8")
        + "\n"
        + (root / "static/js/shipment/shipment-dashboard.js").read_text(encoding="utf-8")
    )

    assert "window.__shipmentAsRecMapLeaflet" in src
    assert "function getFreshScheduleMapContainer()" in src
    assert "container._leaflet_id" in src
    assert "replaceChild(clone, container)" in src


def test_recommend_token_fallback_only_when_no_route_success() -> None:
    conv = _StubRouteConverter({"status": "error", "message": "route_fail"})
    out = recommend_nearby_schedules_for_targets(
        converter=conv,
        targets=[
            {
                "order_id": 1,
                "customer_name": "S",
                "address": "서울 SHIP_TGT_MARK",
                "target_date": "2026-05-04",
                "workers": [],
            }
        ],
        candidates=[
            {
                "order_id": 200,
                "customer_name": "A",
                "address": "서울 AS_CAND_MARK",
                "current_visit_date": "",
                "sort_date": "2026-01-01",
                "as_info_id": 1,
            }
        ],
        per_target_limit=2,
        duration_limit_min=30,
        route_candidates_per_target=10,
        include_workers=True,
    )
    tgt = out["targets"][0]
    assert len(tgt["recommendations"]) >= 1
    assert all(r.get("fallback") is True for r in tgt["recommendations"])
    assert tgt.get("message") == ""


def test_recommend_reference_date_mismatch_warns() -> None:
    """§2.3: 화면 selected_date와 서버 시공일 불일치 시 경고."""
    conv = _StubRouteConverter({"status": "success", "distance_km": 1.0, "duration_min": 5})
    out = recommend_nearby_schedules_for_targets(
        converter=conv,
        targets=[
            {
                "order_id": 1,
                "customer_name": "S",
                "address": "서울 SHIP_TGT_MARK",
                "target_date": "2026-05-04",
                "workers": ["W1"],
            }
        ],
        candidates=[
            {
                "order_id": 200,
                "customer_name": "A",
                "address": "서울 AS_CAND_MARK",
                "current_visit_date": "",
                "sort_date": "2026-01-01",
                "as_info_id": 1,
            }
        ],
        per_target_limit=2,
        duration_limit_min=30,
        route_candidates_per_target=10,
        reference_date="2026-01-01",
        include_workers=True,
    )
    assert any("화면 기준일" in w for w in out["warnings"])
    assert out["targets"][0]["recommendations"][0]["will_apply_workers"] == ["W1"]


def test_recommend_include_workers_false_strips_worker_fields() -> None:
    """§2.2 include_workers=False 시 응답에서 시공자 목록 생략."""
    conv = _StubRouteConverter({"status": "success", "distance_km": 1.0, "duration_min": 5})
    out = recommend_nearby_schedules_for_targets(
        converter=conv,
        targets=[
            {
                "order_id": 1,
                "customer_name": "S",
                "address": "서울 SHIP_TGT_MARK",
                "target_date": "2026-05-04",
                "workers": ["W1"],
            }
        ],
        candidates=[
            {
                "order_id": 200,
                "customer_name": "A",
                "address": "서울 AS_CAND_MARK",
                "current_visit_date": "",
                "sort_date": "2026-01-01",
                "as_info_id": 1,
            }
        ],
        per_target_limit=2,
        duration_limit_min=30,
        route_candidates_per_target=10,
        include_workers=False,
    )
    tgt = out["targets"][0]
    assert tgt["workers"] == []
    assert tgt["recommendations"][0]["will_apply_workers"] == []


def test_geocode_helpers_get_order_display_address_uses_site_full() -> None:
    from types import SimpleNamespace

    from foms.services import geocode_helpers

    order = SimpleNamespace(
        structured_data={"site": {"address_full": "서울시 테스트로 1"}},
        address="폴백",
    )
    assert geocode_helpers.get_order_display_address(order) == "서울시 테스트로 1"


def test_as_recommendations_batch_forwards_selected_date(client, monkeypatch) -> None:
    _login_cs_staff(client, "shipment-rec-seldate")
    order = _make_shipment_target_order()
    captured: dict = {}

    def spy(**kwargs):
        captured["reference_date"] = kwargs.get("reference_date")
        captured["include_workers"] = kwargs.get("include_workers")
        return {
            "targets": [
                {
                    "order_id": order.id,
                    "customer_name": "",
                    "address": "",
                    "target_date": "",
                    "workers": [],
                    "recommendations": [],
                    "linked_as_schedules": [],
                    "message": "",
                }
            ],
            "partial": False,
            "warnings": [],
        }

    monkeypatch.setattr(shipment_rec_api, "recommend_nearby_schedules_for_targets", spy)
    monkeypatch.setattr(shipment_rec_api, "get_cached_target", lambda _ck: None)
    client.post(
        "/api/erp/shipment/as-recommendations",
        json={"order_ids": [order.id], "selected_date": "2099-12-31"},
    )
    assert captured.get("reference_date") == "2099-12-31"
    assert captured.get("include_workers") is True


def _make_as_order_for_apply(
    *,
    visit_date: str,
    as_info: list[dict],
) -> Order:
    today = date.today().strftime("%Y-%m-%d")
    order = Order(
        received_date=today,
        customer_name="AS 추천 대상",
        phone="010-1111-2222",
        address="Seoul AS",
        product="AS",
        status="AS_RECEIVED",
        is_erp_order=True,
        structured_data={
            "schedule": {
                "as_visit": {
                    "date": visit_date,
                    "time": "",
                    "type": "AS",
                }
            },
            "shipment": {"construction_workers": ["OldWorker"]},
            "as_info": as_info,
        },
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_as_recommendations_apply_conflict_without_force_returns_409(client) -> None:
    _login_cs_staff(client, "shipment-rec-apply-409")
    ship = _make_shipment_target_order()
    ship_id = ship.id
    as_order = _make_as_order_for_apply(
        visit_date="2099-12-31",
        as_info=[
            {
                "id": 1,
                "status": "OPEN",
                "visit_date": None,
                "visit_time": None,
            }
        ],
    )
    as_id = as_order.id
    response = client.post(
        "/api/erp/shipment/as-recommendations/apply",
        json={
            "shipment_order_id": ship_id,
            "as_order_id": as_id,
            "as_info_id": 1,
            "force": False,
        },
    )
    assert response.status_code == 409
    assert "force" in response.get_json().get("message", "")


def test_as_recommendations_apply_force_overwrites_visit(client) -> None:
    _login_cs_staff(client, "shipment-rec-apply-force")
    ship = _make_shipment_target_order()
    ship_id = ship.id
    as_order = _make_as_order_for_apply(
        visit_date="2099-12-31",
        as_info=[
            {
                "id": 1,
                "status": "OPEN",
                "visit_date": None,
                "visit_time": None,
            }
        ],
    )
    as_id = as_order.id
    ship_date = date.today().strftime("%Y-%m-%d")
    response = client.post(
        "/api/erp/shipment/as-recommendations/apply",
        json={
            "shipment_order_id": ship_id,
            "as_order_id": as_id,
            "as_info_id": 1,
            "force": True,
        },
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    db_session.expire_all()
    refreshed = db_session.get(Order, as_id)
    sd = refreshed.structured_data
    assert sd["schedule"]["as_visit"]["date"] == ship_date
    meta = sd["schedule"]["as_visit"]["shipment_recommendation"]
    assert meta["source"] == shipment_rec_api.SHREC_SOURCE
    assert meta["shipment_order_id"] == ship_id


def test_as_recommendations_cancel_clears_visit_even_when_previous_date_existed(client) -> None:
    """추천 취소는 출고에 추가한 AS 방문일 자체를 삭제한다."""
    _login_cs_staff(client, "shipment-rec-cancel-clears-prev")
    ship = _make_shipment_target_order()
    ship_id = ship.id
    as_order = _make_as_order_for_apply(
        visit_date="2099-12-31",
        as_info=[
            {
                "id": 1,
                "status": "OPEN",
                "visit_date": "2099-12-31",
                "visit_time": "",
            }
        ],
    )
    as_id = as_order.id
    apply_response = client.post(
        "/api/erp/shipment/as-recommendations/apply",
        json={
            "shipment_order_id": ship_id,
            "as_order_id": as_id,
            "as_info_id": 1,
            "force": True,
        },
    )
    assert apply_response.status_code == 200

    cancel_response = client.post(
        "/api/erp/shipment/as-recommendations/cancel",
        json={
            "shipment_order_id": ship_id,
            "as_order_id": as_id,
            "as_info_id": 1,
        },
    )
    assert cancel_response.status_code == 200
    db_session.expire_all()
    refreshed = db_session.get(Order, as_id)
    sd = refreshed.structured_data
    assert sd["schedule"]["as_visit"]["date"] == ""
    assert sd["schedule"]["as_visit"]["time"] == ""
    assert "shipment_recommendation" not in sd["schedule"]["as_visit"]
    assert sd["as_info"][0]["visit_date"] is None
    assert not [
        d
        for d in refreshed.schedule_dates
        if d.kind == "as_visit" and d.date
    ]


def test_as_recommendations_cancel_wrong_shipment_returns_409(client) -> None:
    _login_cs_staff(client, "shipment-rec-cancel-ship")
    ship = _make_shipment_target_order()
    ship_id = ship.id
    other_ship = _make_shipment_target_order()
    other_ship_id = other_ship.id
    as_order = _make_as_order_for_apply(
        visit_date="",
        as_info=[
            {"id": 1, "status": "OPEN", "visit_date": None, "visit_time": None},
        ],
    )
    as_id = as_order.id
    client.post(
        "/api/erp/shipment/as-recommendations/apply",
        json={
            "shipment_order_id": ship_id,
            "as_order_id": as_id,
            "as_info_id": 1,
            "force": False,
        },
    )
    response = client.post(
        "/api/erp/shipment/as-recommendations/cancel",
        json={
            "shipment_order_id": other_ship_id,
            "as_order_id": as_id,
            "as_info_id": 1,
        },
    )
    assert response.status_code == 409
    assert "출고" in response.get_json().get("message", "")


def test_as_recommendations_cancel_after_manual_date_change_returns_409(client) -> None:
    _login_cs_staff(client, "shipment-rec-cancel-manual")
    ship = _make_shipment_target_order()
    ship_id = ship.id
    as_order = _make_as_order_for_apply(
        visit_date="",
        as_info=[
            {"id": 1, "status": "OPEN", "visit_date": None, "visit_time": None},
        ],
    )
    as_id = as_order.id
    client.post(
        "/api/erp/shipment/as-recommendations/apply",
        json={
            "shipment_order_id": ship_id,
            "as_order_id": as_id,
            "as_info_id": 1,
            "force": False,
        },
    )
    db_session.expire_all()
    row = db_session.get(Order, as_id)
    sd = copy.deepcopy(row.structured_data)
    sd["schedule"]["as_visit"]["date"] = "2099-06-01"
    row.structured_data = sd
    flag_modified(row, "structured_data")
    db_session.commit()

    response = client.post(
        "/api/erp/shipment/as-recommendations/cancel",
        json={
            "shipment_order_id": ship_id,
            "as_order_id": as_id,
            "as_info_id": 1,
        },
    )
    assert response.status_code == 409
    assert "수동" in response.get_json().get("message", "")


def test_as_recommendations_cancel_as_info_id_mismatch_returns_409(client) -> None:
    _login_cs_staff(client, "shipment-rec-cancel-infoid")
    ship = _make_shipment_target_order()
    ship_id = ship.id
    as_order = _make_as_order_for_apply(
        visit_date="",
        as_info=[
            {"id": 1, "status": "OPEN", "visit_date": None, "visit_time": None},
        ],
    )
    as_id = as_order.id
    client.post(
        "/api/erp/shipment/as-recommendations/apply",
        json={
            "shipment_order_id": ship_id,
            "as_order_id": as_id,
            "as_info_id": 1,
            "force": False,
        },
    )
    response = client.post(
        "/api/erp/shipment/as-recommendations/cancel",
        json={
            "shipment_order_id": ship_id,
            "as_order_id": as_id,
            "as_info_id": 99,
        },
    )
    assert response.status_code == 409
    assert "일치" in response.get_json().get("message", "")


def test_prewarm_endpoint_requires_order_ids(client) -> None:
    _login_cs_staff(client, "shipment-rec-prewarm-empty")
    response = client.post("/api/erp/shipment/as-recommendations/prewarm", json={})
    assert response.status_code == 400
    assert response.get_json()["success"] is False


def test_prewarm_endpoint_returns_prewarmed_flag_and_stats(client, monkeypatch) -> None:
    """§5: prewarm은 targets 없이 warmed_targets + cache 메타를 반환한다."""
    _login_cs_staff(client, "shipment-rec-prewarm-ok")
    order = _make_shipment_target_order()

    def fake_compute(**kwargs):
        assert kwargs.get("return_targets") is False
        return {
            "targets": [],
            "targets_len": 1,
            "partial": False,
            "warnings": [],
            "cache": {
                "candidate_pool_hit": True,
                "candidate_count": 3,
                "target_hits": 0,
                "target_misses": 1,
                "route_hits": 0,
                "route_misses": 2,
                "prewarmed": False,
            },
        }

    monkeypatch.setattr(shipment_rec_api, "_compute_recommendation_payload", fake_compute)
    response = client.post(
        "/api/erp/shipment/as-recommendations/prewarm",
        json={"order_ids": [order.id]},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["warmed_targets"] == 1
    assert payload.get("prewarmed") is True
    assert payload.get("candidate_pool_hit") is True
