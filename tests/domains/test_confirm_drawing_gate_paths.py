"""2a-2 C21 도면 게이트 — 일반 상태 쓰기(Q1)·M16·캐시 무효화·화면 payload·강제 변경 기록(Q5).

* 일반 상태 쓰기 3경로(단건·일괄·필드)는 DRAWING→CONFIRM·CONFIRM→PRODUCTION 인접 전진을 하지
  않는다(409 COMMAND_REQUIRED, 일괄은 차단 목록). 관리자 뚫기는 세 경로 모두 기록된다.
* M16: 수정요청이 고객확인을 무효로 하고, 그 요청을 취소하면 되살린다.
* 캐시: 수정요청·취소·전달이 CONFIRM/생산 패널과 첨부 개수 캐시를 비운다(화면 == 서버).
* 화면 payload: 막히면 비관리자에게는 버튼 대신 이유, 관리자에게는 버튼 유지.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from foms.services.common import dashboard_cache
from foms.services.erp_quest_display import build_current_quest_payload
from foms.services.order_event_display import generate_change_description
from foms.services.orders.confirm_drawing_gate import (
    confirm_exit_block,
    effective_drawing_status,
    production_drawing_badge,
    revision_in_flight_block,
    stage_override_drawing_warning,
)
from foms.services.orders.quest_approve_cta import build_approve_cta
from foms.services.orders.stage_override import requires_dedicated_command
from foms.services.notifications.drawing_order_change import _drawing_status as alert_drawing_status
from tests.support.confirm_seed import (
    confirmed_drawing_sd,
    login_as,
    order_events,
    reload_order,
    seed_erp_order,
    seed_user,
)
from tests.support.quest_seed import confirm_quest_completed, confirm_quest_open

_ROOT = Path(__file__).resolve().parents[2]
_OVERRIDE = {"admin_override": True, "override_reason": "현장 구두 컨펌 — 관리자 확인"}


# --------------------------------------------------------------------------- #
# 일반 상태 쓰기(Q1)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("from_stage", "to_stage", "expected"),
    [
        ("DRAWING", "CONFIRM", True), ("CONFIRM", "PRODUCTION", True),
        ("도면", "고객컨펌", True), ("고객컨펌", "PRODUCTION", True),
        ("PRODUCTION", "CONSTRUCTION", False), ("MEASURE", "DRAWING", False),
        ("CONFIRM", "CONSTRUCTION", False),  # 비인접은 OVERRIDE_BLOCK 몫
    ],
)
def test_requires_dedicated_command_normalizes_korean_stage(from_stage, to_stage, expected):
    assert requires_dedicated_command(from_stage, to_stage) is expected


_GENERIC = [
    ("single", "/api/update_order_status", lambda oid: {"order_id": oid, "status": "PRODUCTION"}),
    ("field", "/api/update_order_field", lambda oid: {"order_id": oid, "field": "status", "value": "PRODUCTION"}),
]


@pytest.mark.parametrize(("entry", "path", "body_for"), _GENERIC, ids=[g[0] for g in _GENERIC])
def test_generic_single_writes_refuse_confirm_to_production(client, entry, path, body_for):
    """도면이 CONFIRMED 여도 일반 쓰기로는 넘기지 않는다 — 전용 버튼 경로(퀘스트 게이트 포함)."""
    admin = seed_user(f"gp_a_{entry}", role="ADMIN")
    oid = seed_erp_order("CONFIRM", **confirmed_drawing_sd())
    login_as(client, admin)

    resp = client.post(path, json=body_for(oid))

    assert resp.status_code == 409, resp.get_json()
    assert resp.get_json()["code"] == "COMMAND_REQUIRED"
    assert "전용 버튼" in resp.get_json()["message"]
    assert reload_order(oid).erp_stage_code == "CONFIRM"


def test_generic_single_write_refuses_drawing_to_confirm_korean_stage(client):
    admin = seed_user("gp_a_ko", role="ADMIN")
    oid = seed_erp_order("도면", erp_stage="DRAWING")
    login_as(client, admin)

    resp = client.post("/api/update_order_status", json={"order_id": oid, "status": "CONFIRM"})

    assert resp.status_code == 409 and resp.get_json()["code"] == "COMMAND_REQUIRED"


@pytest.mark.parametrize(("entry", "path", "body_for"), _GENERIC + [
    ("bulk", "/api/bulk_update_order_status", lambda oid: {"order_ids": [oid], "status": "PRODUCTION"}),
], ids=["single", "field", "bulk"])
def test_admin_override_punches_command_required_on_all_three_paths(client, entry, path, body_for):
    admin = seed_user(f"gp_ao_{entry}", role="ADMIN")
    oid = seed_erp_order("CONFIRM", drawing_status="RETURNED")
    login_as(client, admin)

    resp = client.post(path, json={**body_for(oid), **_OVERRIDE})

    assert resp.status_code == 200, resp.get_json()
    assert reload_order(oid).erp_stage_code == "PRODUCTION"
    events = order_events(oid, "ADMIN_OVERRIDE_USED")
    assert len(events) == 1, [e.payload for e in events]
    assert "COMMAND_REQUIRED" in events[0].payload["gates"]
    assert events[0].payload["drawing_status"] == "RETURNED"  # 그 순간의 도면 상태


def test_bulk_all_blocked_reports_failure(client):
    admin = seed_user("gp_bulk_all", role="ADMIN")
    ids = [seed_erp_order("CONFIRM", **confirmed_drawing_sd()) for _ in range(2)]
    login_as(client, admin)

    resp = client.post("/api/bulk_update_order_status", json={"order_ids": ids, "status": "PRODUCTION"})

    body = resp.get_json()
    assert resp.status_code == 409, body
    assert body["success"] is False and body["updated"] == 0
    assert sorted(body["blocked_command_required"]) == sorted(ids)
    assert "2건은 전용 버튼으로만" in body["message"]
    assert all(reload_order(i).erp_stage_code == "CONFIRM" for i in ids)


def test_bulk_partially_blocked_succeeds_with_block_list(client):
    """ERP 주문은 막히고, 비ERP(레거시) 주문은 전용 버튼 대상이 아니라 그대로 바뀐다."""
    from db import db_session
    from models import Order

    admin = seed_user("gp_bulk_part", role="ADMIN")
    blocked = seed_erp_order("DRAWING")
    legacy = Order(received_date="2026-09-29", customer_name="레거시", phone="010-0", address="서울",
                   product="붙박이장", status="DRAWING", is_erp_order=False)
    db_session.add(legacy)
    db_session.commit()
    moved = int(legacy.id)
    login_as(client, admin)

    resp = client.post("/api/bulk_update_order_status", json={"order_ids": [blocked, moved], "status": "CONFIRM"})

    body = resp.get_json()
    assert resp.status_code == 200, body
    assert body["success"] is True
    assert body["blocked_command_required"] == [blocked] and body["updated"] == 1
    assert reload_order(blocked).erp_stage_code == "DRAWING"
    assert reload_order(moved).status == "CONFIRM"


# --------------------------------------------------------------------------- #
# M16 — 수정요청이 고객확인을 무효로, 취소가 되살림 · 캐시 무효화
# --------------------------------------------------------------------------- #
def _confirmed_production_order(tag: str):
    sales = seed_user(f"gp_s_{tag}", team="SALES")
    drafter = seed_user(f"gp_d_{tag}", team="DRAWING")
    oid = seed_erp_order(
        "PRODUCTION", sales=sales, drafter=drafter,
        blueprint={"customer_confirmed": True, "confirmed_at": "2026-09-20T10:00:00", "confirmed_by": "영업"},
        **confirmed_drawing_sd(drawing_current_files=[{"key": "orders/0/drawing_wizard/exports/v1.png"}]),
    )
    return oid, sales


def test_m16_revision_invalidates_and_cancel_restores_customer_confirmation(client):
    oid, sales = _confirmed_production_order("m16")
    login_as(client, sales)

    assert client.post(f"/api/orders/{oid}/request-revision", json={"note": "색"}).status_code == 200
    sd = reload_order(oid).structured_data
    blueprint = sd["blueprint"]
    request_entry = sd["drawing_transfer_history"][-1]
    assert blueprint["customer_confirmed"] is False
    assert blueprint["invalidated_by_request_at"] == request_entry["at"]
    assert blueprint["confirmed_at"] == "2026-09-20T10:00:00"  # 이력으로 남는다
    assert request_entry["customer_confirmation_invalidated"] is True

    assert client.post(f"/api/orders/{oid}/cancel-revision-request").status_code == 200
    blueprint = reload_order(oid).structured_data["blueprint"]
    assert blueprint["customer_confirmed"] is True
    assert "invalidated_at" not in blueprint and "invalidated_by_request_at" not in blueprint


def test_m16_revision_without_customer_confirmation_leaves_blueprint(client):
    oid, sales = _confirmed_production_order("m16n")
    order = reload_order(oid)
    sd = dict(order.structured_data)
    sd.pop("blueprint")
    order.structured_data = sd
    from db import db_session
    db_session.commit()
    login_as(client, sales)

    assert client.post(f"/api/orders/{oid}/request-revision", json={"note": "색"}).status_code == 200
    sd = reload_order(oid).structured_data
    assert "blueprint" not in sd
    assert "customer_confirmation_invalidated" not in sd["drawing_transfer_history"][-1]


@pytest.fixture
def family_spy(monkeypatch):
    seen: list[str] = []

    def _spy(family):
        seen.append(family)
        return 0

    monkeypatch.setattr(dashboard_cache, "invalidate_dashboard_family", _spy)
    return seen


def test_revision_and_cancel_invalidate_production_family(client, family_spy):
    oid, sales = _confirmed_production_order("cache")
    login_as(client, sales)

    assert client.post(f"/api/orders/{oid}/request-revision", json={"note": "색"}).status_code == 200
    assert dashboard_cache.DASHBOARD_FAMILY_PRODUCTION in family_spy
    assert dashboard_cache.DASHBOARD_FAMILY_CONSTRUCTION in family_spy
    family_spy.clear()
    assert client.post(f"/api/orders/{oid}/cancel-revision-request").status_code == 200
    assert dashboard_cache.DASHBOARD_FAMILY_PRODUCTION in family_spy


def test_transfer_invalidates_attachment_families(client, family_spy):
    sales = seed_user("gp_s_tr", team="SALES")
    drafter = seed_user("gp_d_tr", team="DRAWING")
    oid = seed_erp_order("DRAWING", sales=sales, drafter=drafter)
    login_as(client, drafter)

    resp = client.post(f"/api/orders/{oid}/transfer-drawing",
                       json={"files": [{"key": f"orders/{oid}/drawing_wizard/exports/v1.png"}]})

    assert resp.status_code == 200, resp.get_json()
    assert set(dashboard_cache.ATTACHMENT_DASHBOARD_FAMILIES) <= set(family_spy)


# --------------------------------------------------------------------------- #
# 화면 payload(서버와 같은 판정) · 생산 배지 · 판정 정본
# --------------------------------------------------------------------------- #
def _payload(sd, role: str, team: str = "SALES"):
    user = SimpleNamespace(id=7, role=role, team=team, name="검수", username="u7")
    order = SimpleNamespace(id=9, customer_name="고객", manager_name="검수", structured_data=sd, is_erp_order=True)
    return build_current_quest_payload(sd=sd, stage="CONFIRM", stage_code="CONFIRM", order=order,
                                       current_user=user, user_map={})


def test_blocked_cta_hides_buttons_for_staff_but_keeps_admin_button():
    sd = {"workflow": {"stage": "CONFIRM"}, "drawing_status": "RETURNED", "quests": [confirm_quest_open()]}
    staff = _payload(sd, "STAFF")
    admin = _payload(sd, "ADMIN")

    assert staff["approve_blocked"] is True and "수정 요청이 진행 중" in staff["approve_blocked_reason"]
    assert staff["can_assignee_approve"] is False
    assert staff["approvable_teams"] == [] and staff["can_retransition"] is False
    assert admin["approve_blocked"] is True and admin["can_assignee_approve"] is True


def test_blocked_retransition_is_hidden_for_staff():
    sd = {"workflow": {"stage": "CONFIRM"}, "drawing_status": "TRANSFERRED",
          "quests": [confirm_quest_completed()]}
    assert _payload(sd, "STAFF", team="CS")["can_retransition"] is False
    sd_ok = {**sd, **confirmed_drawing_sd()}
    assert _payload(sd_ok, "STAFF", team="CS")["can_retransition"] is True


def test_cta_without_sd_is_not_blocked_and_confirmed_is_not_blocked():
    order = SimpleNamespace(id=1, customer_name="고객")
    assert build_approve_cta("CONFIRM", order)["approve_blocked"] is False
    assert build_approve_cta("CONFIRM", order, sd=confirmed_drawing_sd())["approve_blocked"] is False
    assert build_approve_cta("고객컨펌", order, sd={"drawing_status": "RETURNED"})["approve_blocked"] is True
    assert build_approve_cta("MEASURE", order, sd={"drawing_status": "RETURNED"})["approve_blocked"] is False


@pytest.mark.parametrize(
    ("status", "label"),
    [("RETURNED", "도면 수정 중"), ("TRANSFERRED", "도면 수정 중 · 확정 대기"), ("CONFIRMED", None), (None, None)],
)
def test_production_badge_uses_the_run_start_gate_predicate(status, label):
    sd = {"drawing_status": status} if status else {}
    badge = production_drawing_badge(sd)
    assert (badge or {}).get("label") == label
    assert (badge is not None) == (revision_in_flight_block(sd) is not None)


def test_effective_status_prefers_top_level_and_every_reader_agrees():
    """최상위 CONFIRMED + 중첩 TRANSFERRED(옛 데이터) — 게이트·도면팀 알림·판정 정본이 같은 값."""
    sd = {"drawing_status": "CONFIRMED", "drawing": {"status": "TRANSFERRED"}}
    assert effective_drawing_status(sd) == "CONFIRMED"
    assert confirm_exit_block(sd) is None
    assert alert_drawing_status(sd) == "CONFIRMED"
    assert effective_drawing_status({"drawing_status": " ", "drawing": {"status": "returned"}}) == "RETURNED"
    assert effective_drawing_status({}) == "NONE"


def test_transfer_route_and_workbench_read_status_through_the_single_function():
    """전달 라우트·작업실 목록·상세가 중첩 우선 식을 버리고 판정 정본을 부른다(W2 ③)."""
    nested_first = "get('drawing') or {}).get('status')"
    for rel in ("foms/api/drawing/erp_orders_drawing.py", "foms/web/drawing/workbench.py"):
        src = (_ROOT / rel).read_text(encoding="utf-8")
        assert nested_first not in src, rel
        assert "effective_drawing_status(" in src, rel


# --------------------------------------------------------------------------- #
# 단계 강제 변경(Q5) — 허용하되 도면 상태를 기록
# --------------------------------------------------------------------------- #
def test_stage_override_to_production_records_drawing_status(client):
    manager = seed_user("gp_mgr_q5", role="MANAGER")
    oid = seed_erp_order("CONFIRM", drawing_status="RETURNED")
    login_as(client, manager)

    resp = client.post(f"/api/orders/{oid}/workflow/stage-override",
                       json={"to_stage": "PRODUCTION", "reason": "현장 구두 컨펌", "confirm": True})

    assert resp.status_code == 200, resp.get_json()
    event = order_events(oid, "STAGE_OVERRIDE")[-1]
    assert event.payload["drawing_status"] == "RETURNED"
    assert event.payload["drawing_unconfirmed"] is True
    assert reload_order(oid).erp_stage_code == "PRODUCTION"
    # 타임라인 한 줄에서도 사람이 눈으로 확인한다(리뷰 P3).
    line = generate_change_description("STAGE_OVERRIDE", "", "고객컨펌", "생산", event.payload)
    assert line.endswith("(도면: 수정 요청됨)"), line


def test_override_timeline_lines_show_drawing_status_only_when_unconfirmed():
    admin_line = generate_change_description(
        "ADMIN_OVERRIDE_USED", "", "", "", {"reason": "r", "drawing_status": "TRANSFERRED"})
    assert admin_line.endswith("(도면: 수령 확정 전)"), admin_line
    assert "도면:" not in generate_change_description(
        "ADMIN_OVERRIDE_USED", "", "", "", {"reason": "r", "drawing_status": "CONFIRMED"})
    assert "도면:" not in generate_change_description("ADMIN_OVERRIDE_USED", "", "", "", {"reason": "r"})
    assert "기록 없음" in generate_change_description(
        "ADMIN_OVERRIDE_USED", "", "", "", {"reason": "r", "drawing_status": "NONE"})
    # 역행 같은 강제 변경(drawing_unconfirmed 없음)에는 붙이지 않는다.
    assert "도면:" not in generate_change_description(
        "STAGE_OVERRIDE", "", "생산", "실측", {"reason": "r", "drawing_status": "RETURNED"})


def test_stage_override_warning_text():
    assert "수정 중" in stage_override_drawing_warning({"drawing_status": "RETURNED"}, "PRODUCTION")
    assert "기록 없음" in stage_override_drawing_warning({}, "생산")
    assert stage_override_drawing_warning(confirmed_drawing_sd(), "PRODUCTION") is None
    assert stage_override_drawing_warning({"drawing_status": "RETURNED"}, "CONFIRM") is None
