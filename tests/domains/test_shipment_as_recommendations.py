"""Shipment dashboard AS schedule recommendation API contracts."""

import copy
from datetime import date
from pathlib import Path

from sqlalchemy.orm.attributes import flag_modified
from werkzeug.security import generate_password_hash

from db import db_session
from models import InstallationWorker, Order, OrderEvent, OrderScheduleDate, User

import foms.api.shipment.recommendations as shipment_rec_api
import foms.services.shipment_as_recommendation_cache as shipment_rec_cache
from foms.services.crew.assignments import active_worker_ids, assign_worker
from foms.services.datetime_kst import now_utc_naive
from foms.services.orders.as_cycle_service import (
    project_current_as_cycle,
    register_as_cycle,
    schedule_as_cycle,
)
from foms.services.orders.as_schedule_link import SOURCE_SHIPMENT, read_link, write_link
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


def test_shipment_as_recommendation_map_delegates_to_shared_kakao_module() -> None:
    """출고 지도 = 공용 카카오 모듈 위임(Leaflet/OSM 자체 렌더러는 퇴역).

    AS 대시보드와 같은 `#scheduleMapModal` 을 쓰므로 렌더러가 갈라지면 안 된다.
    modalEl 은 adoptModalFromMain 이 body 로 재부모화한 노드를 넘겨야 한다 —
    모듈이 document.getElementById 로 찾으면 프래그먼트 스왑 후 옛 노드를 잡는다.
    """
    root = Path(__file__).resolve().parents[2]
    js = (root / "static/js/shipment/shipment-dashboard.js").read_text(encoding="utf-8")

    assert "leaflet" not in js.lower()
    assert "window.FOMS_SCHEDULE_MAP.open(" in js
    assert "modalEl: mapModalEl" in js
    assert "function getMapModal()" in js


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


_H64 = "a" * 64


def _make_installation_worker(ext: str, name: str) -> InstallationWorker:
    """활성 설치 작업자 마스터 1명 생성."""
    worker = InstallationWorker(external_worker_id=ext, display_name=name, is_active=True)
    db_session.add(worker)
    db_session.commit()
    return worker


def _make_ship_with_crew(worker_names: list[str]):
    """시공일 + 활성 crew 배정(ID)을 가진 출고 기준 주문을 만든다.

    Returns:
        ``(ship_id, sorted_worker_ids, construction_date)`` — id 로 반환해 client 요청 후
        detached instance 접근을 피한다.
    """
    today = date.today().strftime("%Y-%m-%d")
    ship = Order(
        received_date=today, customer_name="출고 기준", phone="010-3333-4444",
        address="Seoul Gangnam", product="장", status="IN_CONSTRUCTION", is_erp_order=True,
        structured_data={"schedule": {"construction": {"date": today}}, "shipment": {}},
    )
    db_session.add(ship)
    db_session.commit()
    ship_id = ship.id
    worker_ids = []
    for i, name in enumerate(worker_names):
        worker = _make_installation_worker(f"W{ship_id}-{i}", name)
        assign_worker(db_session, order_id=ship_id, worker_id=worker.id)
        worker_ids.append(worker.id)
    db_session.commit()
    return ship_id, sorted(worker_ids), today


def _make_as_order_with_cycle(actor_id: int) -> int:
    """RECEIVED AS cycle 을 연 AS 주문을 만들고 id 를 돌려준다(canonical as_lifecycle)."""
    today = date.today().strftime("%Y-%m-%d")
    order = Order(
        received_date=today, customer_name="AS 추천 대상", phone="010-1111-2222",
        address="Seoul AS", product="AS", status="AS_RECEIVED", is_erp_order=True,
        structured_data={"workflow": {"stage": "CS"}, "shipment": {}},
    )
    db_session.add(order)
    db_session.commit()
    order_id = order.id
    register_as_cycle(
        db_session, order_id=order_id, actor_user_id=actor_id, as_content="문 파손",
        received_date=today, scope_hash=_H64, request_hash=_H64,
    )
    db_session.commit()
    return order_id


def _current_cycle_id(order_id: int) -> str:
    db_session.expire_all()
    return project_current_as_cycle(db_session.get(Order, order_id))["cycle_id"]


def _ship_recommendations(ship_id: int) -> list:
    db_session.expire_all()
    sd = db_session.get(Order, ship_id).structured_data or {}
    return (sd.get("shipment") or {}).get("recommendations") or []


def test_apply_schedules_as_cycle_and_replaces_crew_via_command(client) -> None:
    """추천 적용: AS cycle schedule + crew replace(ID command) + 출고 snapshot 한 tx."""
    user = _login_cs_staff(client, "shipment-rec-apply-canon")
    ship_id, ship_crew, ship_date = _make_ship_with_crew(["철수", "영희"])
    as_id = _make_as_order_with_cycle(user.id)

    response = client.post(
        "/api/erp/shipment/as-recommendations/apply",
        json={"shipment_order_id": ship_id, "as_order_id": as_id},
    )
    assert response.status_code == 200
    assert response.get_json()["success"] is True

    db_session.expire_all()
    refreshed = db_session.get(Order, as_id)
    # AS 방문일은 as_cycle_service 가 canonical 하게 기록(직접 blob write 아님)
    assert project_current_as_cycle(refreshed)["visit_date"] == ship_date
    as_visit = (refreshed.structured_data.get("schedule") or {}).get("as_visit") or {}
    assert "shipment_recommendation" not in as_visit  # legacy 직접쓰기 흔적 없음
    # crew IDs via command: AS 배정이 출고 crew 로 replace 됨(name-array 아님)
    assert active_worker_ids(db_session, as_id) == ship_crew
    # snapshot 은 출고 Order 에 보존(AS info direct write 아님)
    recs = _ship_recommendations(ship_id)
    assert len(recs) == 1 and recs[0]["as_order_id"] == as_id
    assert recs[0]["applied_crew_ids"] == ship_crew
    events = [
        e.event_type
        for e in db_session.query(OrderEvent).filter_by(order_id=as_id).all()
    ]
    assert "AS_SCHEDULED" in events  # as_cycle_service version/receipt/event 한 tx


def test_apply_conflict_without_force_returns_409(client) -> None:
    user = _login_cs_staff(client, "shipment-rec-apply-409")
    ship_id, _, _ = _make_ship_with_crew(["철수"])
    as_id = _make_as_order_with_cycle(user.id)
    schedule_as_cycle(
        db_session, order_id=as_id, visit_date="2099-12-31",
        cycle_id=_current_cycle_id(as_id), actor_user_id=user.id,
        scope_hash=_H64, request_hash=_H64,
    )
    db_session.commit()

    response = client.post(
        "/api/erp/shipment/as-recommendations/apply",
        json={"shipment_order_id": ship_id, "as_order_id": as_id, "force": False},
    )
    assert response.status_code == 409
    assert "force" in response.get_json().get("message", "")


def test_apply_force_overwrites_and_snapshots_previous(client) -> None:
    """force 는 덮되 덮인 값을 snapshot 에 보존한다(현재 값 무시 통째 덮어쓰기 아님)."""
    user = _login_cs_staff(client, "shipment-rec-apply-force")
    ship_id, _, ship_date = _make_ship_with_crew(["철수"])
    as_id = _make_as_order_with_cycle(user.id)
    schedule_as_cycle(
        db_session, order_id=as_id, visit_date="2099-12-31",
        cycle_id=_current_cycle_id(as_id), actor_user_id=user.id,
        scope_hash=_H64, request_hash=_H64,
    )
    db_session.commit()

    response = client.post(
        "/api/erp/shipment/as-recommendations/apply",
        json={"shipment_order_id": ship_id, "as_order_id": as_id, "force": True},
    )
    assert response.status_code == 200
    db_session.expire_all()
    assert project_current_as_cycle(db_session.get(Order, as_id))["visit_date"] == ship_date
    rec = _ship_recommendations(ship_id)[0]
    assert rec["forced"] is True
    assert rec["previous_visit_date"] == "2099-12-31"


def test_apply_if_match_stale_returns_409(client) -> None:
    """as_version If-Match stale → 409(blind overwrite 방지)."""
    user = _login_cs_staff(client, "shipment-rec-apply-ifmatch")
    ship_id, _, _ = _make_ship_with_crew(["철수"])
    as_id = _make_as_order_with_cycle(user.id)
    response = client.post(
        "/api/erp/shipment/as-recommendations/apply",
        json={"shipment_order_id": ship_id, "as_order_id": as_id, "as_version": 999},
    )
    assert response.status_code == 409


def test_cancel_restores_previous_visit_and_crew(client) -> None:
    """취소는 이전 방문일/작업자 snapshot 을 typed compensation 으로 복원한다.

    (이전 crew 가 비어 있는 케이스 — 이전 crew 로의 재배정(released worker 재삽입)은
    partial-unique 가 필요해 PG lane ``tests/postgres/test_shipment_writer.py`` 가 검증한다.)
    """
    user = _login_cs_staff(client, "shipment-rec-cancel-restore")
    user_id = user.id
    ship_id, ship_crew, _ = _make_ship_with_crew(["철수", "영희"])
    as_id = _make_as_order_with_cycle(user_id)
    # AS 원래: 방문일 2099-01-01, crew 없음
    schedule_as_cycle(
        db_session, order_id=as_id, visit_date="2099-01-01",
        cycle_id=_current_cycle_id(as_id), actor_user_id=user_id,
        scope_hash=_H64, request_hash=_H64,
    )
    db_session.commit()

    apply_response = client.post(
        "/api/erp/shipment/as-recommendations/apply",
        json={"shipment_order_id": ship_id, "as_order_id": as_id, "force": True},
    )
    assert apply_response.status_code == 200
    db_session.expire_all()
    assert active_worker_ids(db_session, as_id) == ship_crew  # 적용: crew=출고 crew

    cancel_response = client.post(
        "/api/erp/shipment/as-recommendations/cancel",
        json={"shipment_order_id": ship_id, "as_order_id": as_id},
    )
    assert cancel_response.status_code == 200
    db_session.expire_all()
    assert project_current_as_cycle(db_session.get(Order, as_id))["visit_date"] == "2099-01-01"
    assert active_worker_ids(db_session, as_id) == []  # 이전(빈) crew 복원
    assert _ship_recommendations(ship_id) == []  # snapshot 제거


def test_cancel_wrong_shipment_returns_409(client) -> None:
    user = _login_cs_staff(client, "shipment-rec-cancel-ship")
    ship_id, _, _ = _make_ship_with_crew(["철수"])
    other_ship_id, _, _ = _make_ship_with_crew(["영희"])
    as_id = _make_as_order_with_cycle(user.id)
    client.post(
        "/api/erp/shipment/as-recommendations/apply",
        json={"shipment_order_id": ship_id, "as_order_id": as_id},
    )
    response = client.post(
        "/api/erp/shipment/as-recommendations/cancel",
        json={"shipment_order_id": other_ship_id, "as_order_id": as_id},
    )
    assert response.status_code == 409
    assert "추천" in response.get_json().get("message", "")


def test_cancel_after_manual_date_change_returns_409(client) -> None:
    user = _login_cs_staff(client, "shipment-rec-cancel-manual")
    user_id = user.id
    ship_id, _, _ = _make_ship_with_crew(["철수"])
    as_id = _make_as_order_with_cycle(user_id)
    client.post(
        "/api/erp/shipment/as-recommendations/apply",
        json={"shipment_order_id": ship_id, "as_order_id": as_id},
    )
    # 사용자가 canonical command 로 방문일을 수동 변경
    schedule_as_cycle(
        db_session, order_id=as_id, visit_date="2099-06-01",
        cycle_id=_current_cycle_id(as_id), actor_user_id=user_id,
        scope_hash=_H64, request_hash=_H64,
    )
    db_session.commit()

    response = client.post(
        "/api/erp/shipment/as-recommendations/cancel",
        json={"shipment_order_id": ship_id, "as_order_id": as_id},
    )
    assert response.status_code == 409
    assert "수동" in response.get_json().get("message", "")


def _as_schedule_link(as_id: int):
    """AS 주문의 현재 schedule_link 를 새로 읽어온다(세션 캐시 회피)."""
    db_session.expire_all()
    sd = db_session.get(Order, as_id).structured_data or {}
    return read_link(sd)


def test_apply_writes_as_side_schedule_link(client) -> None:
    """T6: 출고 추천 적용은 AS 주문 쪽에도 schedule_link 를 남긴다(경로 A 동기화, §3.2)."""
    user = _login_cs_staff(client, "shipment-rec-apply-link")
    ship_id, _, ship_date = _make_ship_with_crew(["철수"])
    as_id = _make_as_order_with_cycle(user.id)

    response = client.post(
        "/api/erp/shipment/as-recommendations/apply",
        json={"shipment_order_id": ship_id, "as_order_id": as_id},
    )
    assert response.status_code == 200

    link = _as_schedule_link(as_id)
    assert link is not None
    assert link["source"] == SOURCE_SHIPMENT
    assert link["ref_order_id"] == ship_id
    assert link["ref_date"] == ship_date


def test_cancel_removes_as_side_schedule_link(client) -> None:
    """T6: 취소는 이 출고건이 만든 schedule_link 를 해제한다."""
    user = _login_cs_staff(client, "shipment-rec-cancel-link")
    ship_id, _, _ = _make_ship_with_crew(["철수"])
    as_id = _make_as_order_with_cycle(user.id)
    client.post(
        "/api/erp/shipment/as-recommendations/apply",
        json={"shipment_order_id": ship_id, "as_order_id": as_id},
    )
    assert _as_schedule_link(as_id) is not None

    response = client.post(
        "/api/erp/shipment/as-recommendations/cancel",
        json={"shipment_order_id": ship_id, "as_order_id": as_id},
    )
    assert response.status_code == 200
    assert _as_schedule_link(as_id) is None


def test_cancel_does_not_clobber_link_to_different_ref_order(client) -> None:
    """T6: 취소 시점에 링크의 ref_order_id 가 이 출고건과 다르면 건드리지 않는다.

    사용자가 취소 전에 AS 대시보드 "가까운 일정 찾기"(또는 다른 출고건)로 손으로
    재매칭했을 수 있다 — clobber 는 데이터 유실 버그(스펙 §3.2/플랜 T6).
    """
    user = _login_cs_staff(client, "shipment-rec-cancel-link-guard")
    user_id = user.id
    ship_id, _, _ = _make_ship_with_crew(["철수"])
    other_ship_id, _, other_ship_date = _make_ship_with_crew(["영희"])
    as_id = _make_as_order_with_cycle(user_id)
    client.post(
        "/api/erp/shipment/as-recommendations/apply",
        json={"shipment_order_id": ship_id, "as_order_id": as_id},
    )
    assert _as_schedule_link(as_id)["ref_order_id"] == ship_id

    # 취소 전에 다른 기준 주문으로 재매칭된 상태를 재현.
    as_order = db_session.get(Order, as_id)
    sd = copy.deepcopy(as_order.structured_data or {})
    write_link(
        sd, ref_order_id=other_ship_id, ref_date=other_ship_date,
        source=SOURCE_SHIPMENT, user_id=user_id, user_name="", now=now_utc_naive(),
    )
    as_order.structured_data = sd
    flag_modified(as_order, "structured_data")
    db_session.commit()

    response = client.post(
        "/api/erp/shipment/as-recommendations/cancel",
        json={"shipment_order_id": ship_id, "as_order_id": as_id},
    )
    assert response.status_code == 200

    link = _as_schedule_link(as_id)
    assert link is not None
    assert link["ref_order_id"] == other_ship_id


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



# ---------------------------------------------------------------------------
# 설계서 §14.9 (D35, P14-7) — AS 넣기 때 시공자 이름도 같이
# ---------------------------------------------------------------------------


def _make_ship_kst_today() -> tuple:
    """한국 날짜 오늘 시공일을 가진 출고 줄(번호 배정 없음 · 이름 없음). ``(ship_id, date)``."""
    from foms.services.datetime_kst import get_today_kst

    today = get_today_kst().strftime("%Y-%m-%d")
    ship = Order(
        received_date=today, customer_name="출고 이름판", phone="010-3333-5555",
        address="Seoul Gangnam", product="장", status="IN_CONSTRUCTION", is_erp_order=True,
        structured_data={"schedule": {"construction": {"date": today}}, "shipment": {}},
    )
    db_session.add(ship)
    db_session.commit()
    return ship.id, today


def _set_ship_names_via_api(client, ship_id: int, names: list) -> None:
    """실제 흐름(이름판 · PC 칸)대로 출고 설정 API 로 시공자 이름을 넣는다."""
    resp = client.post(f"/api/erp/shipment/update/{ship_id}", json={"construction_workers": names})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["success"] is True


def _as_names(as_id: int):
    """AS 주문의 시공자 이름 배열(키가 없으면 None)을 새로 읽는다."""
    db_session.expire_all()
    sd = db_session.get(Order, as_id).structured_data or {}
    return (sd.get("shipment") or {}).get("construction_workers")


def _set_as_names_direct(as_id: int, names) -> None:
    """준비물: AS 주문 이름 배열을 직접 둔다(이미 다른 이름이 있던 상황 · 손으로 바꾼 상황)."""
    db_session.expire_all()
    as_order = db_session.get(Order, as_id)
    sd = copy.deepcopy(as_order.structured_data or {})
    sd.setdefault("shipment", {})["construction_workers"] = names
    as_order.structured_data = sd
    flag_modified(as_order, "structured_data")
    db_session.commit()


def _apply(client, ship_id: int, as_id: int) -> dict:
    resp = client.post(
        "/api/erp/shipment/as-recommendations/apply",
        json={"shipment_order_id": ship_id, "as_order_id": as_id},
    )
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def _cancel(client, ship_id: int, as_id: int) -> dict:
    resp = client.post(
        "/api/erp/shipment/as-recommendations/cancel",
        json={"shipment_order_id": ship_id, "as_order_id": as_id},
    )
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def _applied_workers(body: dict):
    data = body.get("data") if isinstance(body.get("data"), dict) else body
    return data.get("applied_workers")


def test_d35_real_flow_apply_copies_ship_names_to_as(client) -> None:
    """실제 흐름: 이름판 API 로 출고 줄에 철수 → 넣기 → AS 이름 = 출고 이름, 응답도 이름."""
    user = _login_cs_staff(client, "shipment-rec-d35-flow")
    user_id = user.id
    ship_id, _ = _make_ship_kst_today()
    as_id = _make_as_order_with_cycle(user_id)
    _set_ship_names_via_api(client, ship_id, ["  철수 ", "민수", "철수"])  # writer 정규화 그대로

    body = _apply(client, ship_id, as_id)
    assert _applied_workers(body) == ["철수", "민수"]
    assert _as_names(as_id) == ["철수", "민수"]
    assert active_worker_ids(db_session, as_id) == []  # 번호 배정은 그대로(비어 있음)
    rec = _ship_recommendations(ship_id)[0]
    assert rec["applied_names"] == ["철수", "민수"]
    assert rec["previous_names"] is None
    # 같은 AS 쓰기 안의 schedule_link 도 그대로 남는다(다른 키 보존)
    assert _as_schedule_link(as_id)["ref_order_id"] == ship_id


def test_d35_apply_overwrites_existing_as_names(client) -> None:
    """AS 에 원래 영희 → 넣기 뒤 철수, snapshot previous_names = 영희."""
    user = _login_cs_staff(client, "shipment-rec-d35-over")
    user_id = user.id
    ship_id, _ = _make_ship_kst_today()
    as_id = _make_as_order_with_cycle(user_id)
    _set_as_names_direct(as_id, ["영희"])
    _set_ship_names_via_api(client, ship_id, ["철수"])

    _apply(client, ship_id, as_id)
    assert _as_names(as_id) == ["철수"]
    rec = _ship_recommendations(ship_id)[0]
    assert rec["previous_names"] == ["영희"]
    assert rec["applied_names"] == ["철수"]


def test_d35_no_ship_names_leaves_as_names(client) -> None:
    """출고 이름 없음 → AS 이름 그대로, applied_names null."""
    user = _login_cs_staff(client, "shipment-rec-d35-none")
    user_id = user.id
    ship_id, _ = _make_ship_kst_today()
    as_id = _make_as_order_with_cycle(user_id)
    _set_as_names_direct(as_id, ["영희"])
    _set_ship_names_via_api(client, ship_id, [])

    body = _apply(client, ship_id, as_id)
    assert _applied_workers(body) == []  # 번호 배정 이름(빈 값) 그대로
    assert _as_names(as_id) == ["영희"]
    rec = _ship_recommendations(ship_id)[0]
    assert rec["applied_names"] is None
    assert rec["previous_names"] == ["영희"]


def test_d35_cancel_restores_previous_names(client) -> None:
    """취소: AS 이름이 넣은 그대로면 넣기 전 이름(영희)으로 되돌린다."""
    user = _login_cs_staff(client, "shipment-rec-d35-cancel-prev")
    user_id = user.id
    ship_id, _ = _make_ship_kst_today()
    as_id = _make_as_order_with_cycle(user_id)
    _set_as_names_direct(as_id, ["영희"])
    _set_ship_names_via_api(client, ship_id, ["철수"])
    _apply(client, ship_id, as_id)
    assert _as_names(as_id) == ["철수"]

    _cancel(client, ship_id, as_id)
    assert _as_names(as_id) == ["영희"]
    assert _ship_recommendations(ship_id) == []


def test_d35_cancel_removes_names_when_none_before(client) -> None:
    """취소: 넣기 전 이름이 없었으면(null) 이름 키를 지운다."""
    user = _login_cs_staff(client, "shipment-rec-d35-cancel-none")
    user_id = user.id
    ship_id, _ = _make_ship_kst_today()
    as_id = _make_as_order_with_cycle(user_id)
    _set_ship_names_via_api(client, ship_id, ["철수"])
    _apply(client, ship_id, as_id)
    assert _as_names(as_id) == ["철수"]

    _cancel(client, ship_id, as_id)
    db_session.expire_all()
    shipment = (db_session.get(Order, as_id).structured_data or {}).get("shipment") or {}
    assert "construction_workers" not in shipment
    assert _as_schedule_link(as_id) is None  # 링크 해제도 같이


def test_d35_cancel_keeps_manually_changed_names(client) -> None:
    """취소 전에 손으로 바꾼 이름은 그대로 두고 취소는 200 으로 계속한다."""
    user = _login_cs_staff(client, "shipment-rec-d35-cancel-manual")
    user_id = user.id
    ship_id, ship_date = _make_ship_kst_today()
    as_id = _make_as_order_with_cycle(user_id)
    _set_as_names_direct(as_id, ["영희"])
    _set_ship_names_via_api(client, ship_id, ["철수"])
    _apply(client, ship_id, as_id)
    _set_as_names_direct(as_id, ["민수"])

    _cancel(client, ship_id, as_id)
    assert _as_names(as_id) == ["민수"]
    assert _ship_recommendations(ship_id) == []
    db_session.expire_all()
    assert project_current_as_cycle(db_session.get(Order, as_id))["visit_date"] != ship_date


def test_d35_cancel_legacy_snapshot_leaves_names(client) -> None:
    """옛 snapshot(applied_names 키 없음) 취소 → 이름 그대로."""
    user = _login_cs_staff(client, "shipment-rec-d35-cancel-legacy")
    user_id = user.id
    ship_id, _ = _make_ship_kst_today()
    as_id = _make_as_order_with_cycle(user_id)
    _set_ship_names_via_api(client, ship_id, ["철수"])
    _apply(client, ship_id, as_id)
    assert _as_names(as_id) == ["철수"]

    # 넣기 snapshot 을 이 기능 전 모양으로 되돌린다(이름 키 없음).
    db_session.expire_all()
    ship = db_session.get(Order, ship_id)
    sd = copy.deepcopy(ship.structured_data or {})
    for rec in sd["shipment"]["recommendations"]:
        rec.pop("applied_names", None)
        rec.pop("previous_names", None)
    ship.structured_data = sd
    flag_modified(ship, "structured_data")
    db_session.commit()

    _cancel(client, ship_id, as_id)
    assert _as_names(as_id) == ["철수"]
    assert _ship_recommendations(ship_id) == []


def test_d35_tablet_sheet_groups_as_row_with_ship_worker(client) -> None:
    """넣기 뒤 태블릿 하루치 출고표에서 AS 줄이 출고 시공자(철수) 묶음에 들어간다."""
    from foms.services.shipment.tablet_day_sheet import build_tablet_day_sheet

    user = _login_cs_staff(client, "shipment-rec-d35-sheet")
    user_id = user.id
    ship_id, ship_date = _make_ship_kst_today()
    as_id = _make_as_order_with_cycle(user_id)
    _set_ship_names_via_api(client, ship_id, ["철수"])
    _apply(client, ship_id, as_id)

    db_session.expire_all()
    rows = [db_session.get(Order, ship_id), db_session.get(Order, as_id)]
    sheet = build_tablet_day_sheet(rows, [], ship_date)
    assert sheet["unassigned"] == 0
    assert len(sheet["groups"]) == 1
    group = sheet["groups"][0]
    assert group["unassigned"] is False
    assert [r["order"].id for r in group["rows"]] == [ship_id, as_id]
    assert [r["is_as"] for r in group["rows"]] == [False, True]
    assert [w["name"] for w in group["rows"][1]["workers"]] == ["철수"]

# ---------------------------------------------------------------------------
# D35-b (사용자 11-12 '바뀐 칸 기록도 남기기') — 넣기 · 취소로 AS 이름이 바뀌면 변경 원장에도
# ---------------------------------------------------------------------------

_NAMES_PATH = "shipment.construction_workers"


def _ledger_rows(order_id: int) -> list:
    """주문의 변경 원장 행(id 순)을 새로 읽어 값만 떠 둔다(요청 뒤 세션이 닫혀도 읽히게)."""
    from types import SimpleNamespace

    from models import OrderFieldChange

    db_session.expire_all()
    cols = ("id", "change_set_id", "path", "path_template", "item_index", "op",
            "before_value", "after_value", "actor_user_id")
    rows = (
        db_session.query(OrderFieldChange)
        .filter(OrderFieldChange.order_id == order_id)
        .order_by(OrderFieldChange.id)
        .all()
    )
    return [SimpleNamespace(**{c: getattr(r, c) for c in cols}) for r in rows]


def _name_rows(order_id: int) -> list:
    return [r for r in _ledger_rows(order_id) if r.path == _NAMES_PATH]


def _latest_asrec_log(prefix: str):
    """가장 최근 AS 추천 감사 헤더(``message`` 앞머리로 고른다)."""
    from types import SimpleNamespace

    from models import SecurityLog

    db_session.expire_all()
    log = (
        db_session.query(SecurityLog)
        .filter(SecurityLog.message.like(f"{prefix}%"))
        .order_by(SecurityLog.id.desc())
        .first()
    )
    return SimpleNamespace(detail=dict(log.detail or {}))


def _history_entries(client, order_id: int) -> list:
    """주문 화면 '변경 이력' 탭 API 가 내주는 변경 줄(묶음 순서대로 펼침)."""
    body = client.get(f"/api/orders/{order_id}/field-changes").get_json()
    assert body["success"] is True, body
    out = []
    for change_set in body["data"]["change_sets"]:
        for entry in change_set["changes"]:
            out.append({**entry, "actor": change_set["actor"], "change_set": change_set["change_set"]})
    return out


def test_d35b_apply_records_name_ledger_row_same_shape_as_name_board(client) -> None:
    """넣기로 AS 이름이 영희 → 철수: AS 원장에 이름판 저장과 같은 경로 행 1개, 감사 헤더와 이어짐."""
    user = _login_cs_staff(client, "shipment-rec-d35b-apply")
    user_id = user.id
    ship_id, _ = _make_ship_kst_today()
    as_id = _make_as_order_with_cycle(user_id)
    _set_as_names_direct(as_id, ["영희"])
    _set_ship_names_via_api(client, ship_id, ["철수", "민수"])
    board_rows = _name_rows(ship_id)  # 이름판 저장이 출고 주문에 남긴 행(견줄 기준)
    assert len(board_rows) == 1
    board = board_rows[0]
    assert _name_rows(as_id) == []

    _apply(client, ship_id, as_id)
    as_rows = _name_rows(as_id)
    assert len(as_rows) == 1
    row = as_rows[0]
    # 경로 모양 · 값 표현이 이름판 저장과 같다
    assert (row.path, row.path_template, row.item_index) == (
        board.path, board.path_template, board.item_index)
    assert row.after_value == board.after_value
    assert row.before_value is not None and "영희" in row.before_value
    assert row.op == "set"
    assert row.actor_user_id == user_id == board.actor_user_id
    # 원장에는 이름 경로만(같은 쓰기 안의 schedule_link 는 넣지 않는다)
    assert [r.path for r in _ledger_rows(as_id)] == [_NAMES_PATH]
    # 감사 헤더 detail['change_set'] 이 원장 행과 이어진다
    log = _latest_asrec_log("출고 대시보드 AS 추천 적용")
    assert log.detail["change_set"] == row.change_set_id
    assert log.detail["change_count"] == 1

    # 화면(주문 변경 이력 탭)에 이름판 저장 줄과 같은 라벨 · 행위자로 나온다
    ship_entry = next(e for e in _history_entries(client, ship_id) if e["id"] == board.id)
    as_entry = next(e for e in _history_entries(client, as_id) if e["id"] == row.id)
    assert as_entry["label"] == ship_entry["label"]
    assert as_entry["actor"] == ship_entry["actor"] is not None
    assert "철수" in as_entry["text"] and "영희" in as_entry["text"]


def test_d35b_apply_without_ship_names_records_no_row(client) -> None:
    """출고 이름이 없어 AS 이름이 그대로면 원장 행 0(감사 헤더 열쇠는 있고 개수 0)."""
    user = _login_cs_staff(client, "shipment-rec-d35b-none")
    user_id = user.id
    ship_id, _ = _make_ship_kst_today()
    as_id = _make_as_order_with_cycle(user_id)
    _set_as_names_direct(as_id, ["영희"])
    _set_ship_names_via_api(client, ship_id, [])

    _apply(client, ship_id, as_id)
    assert _as_names(as_id) == ["영희"]
    assert _ledger_rows(as_id) == []
    log = _latest_asrec_log("출고 대시보드 AS 추천 적용")
    assert log.detail["change_set"]
    assert log.detail["change_count"] == 0


def test_d35b_apply_same_names_records_no_row(client) -> None:
    """AS 이름이 이미 출고 이름과 같으면 바뀐 게 없으니 행 0."""
    user = _login_cs_staff(client, "shipment-rec-d35b-same")
    user_id = user.id
    ship_id, _ = _make_ship_kst_today()
    as_id = _make_as_order_with_cycle(user_id)
    _set_as_names_direct(as_id, ["철수"])
    _set_ship_names_via_api(client, ship_id, ["철수"])

    _apply(client, ship_id, as_id)
    assert _ledger_rows(as_id) == []


def test_d35b_cancel_restore_records_reverse_row(client) -> None:
    """취소로 철수 → 영희 되돌림: 넣기 행의 거꾸로인 행이 하나 더(경로 같음), 헤더와 이어짐."""
    user = _login_cs_staff(client, "shipment-rec-d35b-cancel")
    user_id = user.id
    ship_id, _ = _make_ship_kst_today()
    as_id = _make_as_order_with_cycle(user_id)
    _set_as_names_direct(as_id, ["영희"])
    _set_ship_names_via_api(client, ship_id, ["철수"])
    _apply(client, ship_id, as_id)
    applied = _name_rows(as_id)
    assert len(applied) == 1

    _cancel(client, ship_id, as_id)
    assert _as_names(as_id) == ["영희"]
    rows = _name_rows(as_id)
    assert len(rows) == 2
    undo = rows[1]
    assert undo.path == applied[0].path
    assert undo.before_value == applied[0].after_value
    assert undo.after_value == applied[0].before_value
    assert undo.actor_user_id == user_id
    assert undo.change_set_id != applied[0].change_set_id
    log = _latest_asrec_log("출고 대시보드 AS 추천 취소")
    assert log.detail["change_set"] == undo.change_set_id
    assert log.detail["change_count"] == 1


def test_d35b_cancel_to_no_names_records_clear_row(client) -> None:
    """넣기 전 이름이 없었으면 취소 행은 '지움'(op clear)."""
    user = _login_cs_staff(client, "shipment-rec-d35b-cancel-clear")
    user_id = user.id
    ship_id, _ = _make_ship_kst_today()
    as_id = _make_as_order_with_cycle(user_id)
    _set_ship_names_via_api(client, ship_id, ["철수"])
    _apply(client, ship_id, as_id)
    first = _name_rows(as_id)
    assert [r.op for r in first] == ["add"]

    _cancel(client, ship_id, as_id)
    rows = _name_rows(as_id)
    assert [r.op for r in rows] == ["add", "clear"]
    assert rows[1].after_value is None


def test_d35b_cancel_keeps_manual_names_records_no_new_row(client) -> None:
    """취소 전에 손으로 민수로 바꿨으면 이름을 안 되돌리니 취소로 새 행 0."""
    user = _login_cs_staff(client, "shipment-rec-d35b-cancel-manual")
    user_id = user.id
    ship_id, _ = _make_ship_kst_today()
    as_id = _make_as_order_with_cycle(user_id)
    _set_as_names_direct(as_id, ["영희"])
    _set_ship_names_via_api(client, ship_id, ["철수"])
    _apply(client, ship_id, as_id)
    _set_as_names_direct(as_id, ["민수"])  # 원장을 거치지 않는 손 변경(준비물)
    before = [r.id for r in _ledger_rows(as_id)]

    _cancel(client, ship_id, as_id)
    assert _as_names(as_id) == ["민수"]
    assert [r.id for r in _ledger_rows(as_id)] == before
    log = _latest_asrec_log("출고 대시보드 AS 추천 취소")
    assert log.detail["change_count"] == 0
