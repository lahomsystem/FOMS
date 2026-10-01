"""P1-2: 저장 경로의 대시보드 캐시 통째 비우기(broad)를 바뀐 탭만 비우게 좁힌 계약.

운영 30일 동안 캐시 무효화가 하루 500~1,300번 일어났고 적중률은 38~53% 에 머물렀다.
저장 경로 13곳 + 날짜 동기화 리스너가 저장 한 번마다 7 family 를 전부 비웠기 때문이다.

판정 기준은 하나다: **그 family 의 캐시된 slice DTO 가 이 저장의 바뀐 값을 담을 수 있는가.**
이 파일은 경로마다 "그 변경이 보이는 탭의 캐시는 비워지고, 무관한 탭은 남는다" 를 고정하고,
소속 자체가 바뀌는 전이(AS 접수·새 주문·status 변경·초안 승격)는 broad 그대로임을 고정한다.

비워진 family 는 ``invalidate_dashboard_family`` 를 가로채 센다 — 라우트의 손 호출, MUT-CACHE-01
리스너, 날짜 동기화 리스너가 모두 이 한 함수를 거치므로 요청 하나가 실제로 비운 전부가 잡힌다.
"""
from __future__ import annotations

import copy
import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy.orm.attributes import flag_modified
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.common import dashboard_cache as dc
from foms.services.datetime_kst import get_today_kst
from models import Order, User

ALL = set(dc.ALL_DASHBOARD_FAMILIES)
TODAY = datetime.date(2026, 10, 1)


def _iso(days: int, base: datetime.date | None = None) -> str:
    return ((base or get_today_kst()) + datetime.timedelta(days=days)).isoformat()


# =========================================================================== #
# 1) 순수 판정 — dashboard_families_for_order_save
# =========================================================================== #
def _order(stage="PRODUCTION", *, status=None, measurement=None, construction=None,
           customer="홍길동", items=None, drawing_status=None, draft=False, **flat):
    sd = {
        "workflow": {"stage": stage},
        "parties": {"customer": {"name": customer, "phone": "010-1234-5678"}},
        "schedule": {
            "measurement": {"date": measurement or ""},
            "construction": {"date": construction or ""},
        },
        "items": items if items is not None else [{"product_name": "붙박이장", "price": 100}],
    }
    if drawing_status:
        sd["drawing_status"] = drawing_status
    if draft:
        sd["meta"] = {"draft": True}
    base = dict(
        status=status or stage, deleted_at=None, is_erp_order=True, erp_stage_code=stage,
        customer_name=customer, phone="010-1234-5678", address="서울", product="붙박이장",
        manager_name="영업", measurement_date=None, erp_measurement_date=measurement,
        scheduled_date=None, erp_construction_date=construction, is_regional=False,
        is_self_measurement=False, measurement_completed=False,
        regional_sales_order_upload=False, regional_blueprint_sent=False,
        regional_order_upload=False, structured_data=sd,
    )
    base.update(flat)
    return SimpleNamespace(**base)


#: 검색 필드(첫 품목명)는 그대로 두고 금액만 바꾼 품목 — "내용만 바뀐 저장".
PRICE_ONLY = [{"product_name": "붙박이장", "price": 777}]


def _families(before, after) -> set[str]:
    return set(dc.dashboard_families_for_order_save(
        dc.order_dashboard_cache_axes(before), dc.order_dashboard_cache_axes(after), today=TODAY,
    ))


def test_save_without_dates_in_window_scopes_to_stage_family():
    """생산 단계·실측은 지난달·시공은 두 달 뒤: 품목 값만 바뀌면 orders + 생산 숫자판만."""
    before = _order("PRODUCTION", measurement=_iso(-40, TODAY), construction=_iso(60, TODAY))
    after = _order("PRODUCTION", measurement=_iso(-40, TODAY), construction=_iso(60, TODAY),
                   items=[{"product_name": "붙박이장", "price": 200}])
    assert _families(before, after) == {"orders", "production"}


def test_measurement_date_in_window_keeps_measurement_family():
    """실측일이 오늘~14일 창 안이면 단계와 무관하게 실측 캐시(품목 목록 DTO)를 비운다."""
    before = _order("DRAWING", measurement=_iso(0, TODAY))
    after = _order("DRAWING", measurement=_iso(0, TODAY),
                   items=[{"product_name": "붙박이장", "price": 999}])
    assert _families(before, after) == {"orders", "drawing", "measurement"}


def test_construction_date_in_window_keeps_shipment_family():
    """시공일이 출고 패널 창(오늘~14일) 안이면 출고 집계(자수·작업자)를 비운다."""
    before = _order("PRODUCTION", construction=_iso(3, TODAY))
    after = _order("PRODUCTION", construction=_iso(3, TODAY),
                   items=[{"product_name": "붙박이장", "price": 1}])
    assert _families(before, after) == {"orders", "production", "shipment"}


def test_measurement_date_change_outside_window_still_clears_measurement():
    """창 밖이라도 실측일이 바뀌면 지난 날짜 목록의 소속이 바뀐다 → 실측 family.
    실측일 문자열은 과거 이력 검색 대상이라 history 도."""
    before = _order("PRODUCTION", measurement=_iso(-40, TODAY))
    after = _order("PRODUCTION", measurement=_iso(-39, TODAY))
    assert {"measurement", "history"} <= _families(before, after)


def test_regional_flag_change_clears_measurement_panel():
    before = _order("PRODUCTION", measurement=_iso(-40, TODAY))
    after = _order("PRODUCTION", measurement=_iso(-40, TODAY), is_regional=True)
    assert "measurement" in _families(before, after)


def test_identity_change_clears_history_search():
    """이름이 바뀌면 과거 이력 검색 결과(단계 무관 전체 주문)의 소속이 바뀐다."""
    before = _order("PRODUCTION")
    after = _order("PRODUCTION", customer="김철수")
    assert _families(before, after) == {"orders", "production", "history"}


def test_completed_order_also_clears_construction_summary():
    """시공 숫자판은 완료 단계도 센다(시공완료) — 단계 family(history) + construction."""
    assert _families(_order("COMPLETED"), _order("COMPLETED", items=PRICE_ONLY)) == {
        "orders", "history", "construction",
    }


def test_construction_stage_also_clears_production_summary():
    """생산 숫자판은 시공 단계도 센다(제작완료 버킷) — construction + production."""
    assert _families(_order("CONSTRUCTION"), _order("CONSTRUCTION", items=PRICE_ONLY)) == {
        "orders", "construction", "production",
    }


def test_received_order_without_dates_clears_orders_only():
    assert _families(_order("RECEIVED"), _order("RECEIVED", items=PRICE_ONLY)) == {"orders"}


def test_drawing_status_change_clears_drawing_queue():
    before = _order("PRODUCTION", drawing_status="CONFIRMED")
    after = _order("PRODUCTION", drawing_status="RETURNED")
    assert "drawing" in _families(before, after)


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (_order("RECEIVED", draft=True, status="DRAFT"), _order("RECEIVED")),  # 초안 승격
        (_order("PRODUCTION"), _order("PRODUCTION", status="AS_RECEIVED")),  # status 변경
        (_order("PRODUCTION"), _order("PRODUCTION", deleted_at=datetime.datetime(2026, 10, 1))),
        (_order("실측중"), _order("실측중", items=[])),  # 모르는 단계
        (_order("RECEIVED"), _order("DRAWING")),  # 도메인 탭 없는 단계에서 이동
    ],
)
def test_membership_transitions_stay_broad(before, after):
    assert _families(before, after) == ALL


def test_missing_before_snapshot_is_broad():
    after = dc.order_dashboard_cache_axes(_order("PRODUCTION"))
    assert set(dc.dashboard_families_for_order_save(None, after, today=TODAY)) == ALL


def test_before_snapshot_is_frozen_against_in_place_edits():
    """저장 도중 structured_data 를 제자리에서 고쳐도 전 스냅샷은 그대로여야 비교가 된다."""
    order = _order("PRODUCTION")
    before = dc.order_dashboard_cache_axes(order)
    order.structured_data["parties"]["customer"]["name"] = "바뀐 이름"
    order.customer_name = "바뀐 이름"
    assert "history" in dc.dashboard_families_for_order_save(
        before, dc.order_dashboard_cache_axes(order), today=TODAY
    )


# --- 정본 상수와 같은지(드리프트 = 과소무효화) --------------------------------
def test_summary_stage_sets_match_read_models():
    from foms.services.construction_read_model import CONSTRUCTION_ALL_STAGE_CODES
    from foms.services.production_read_model import PRODUCTION_BASE_STAGE_CODES

    assert dc.CONSTRUCTION_SUMMARY_STAGE_CODES == frozenset(CONSTRUCTION_ALL_STAGE_CODES)
    assert dc.PRODUCTION_SUMMARY_STAGE_CODES == frozenset(PRODUCTION_BASE_STAGE_CODES)


def test_date_window_matches_measurement_panel_range(monkeypatch):
    import foms.services.measurement_dashboard_filters as mdf

    monkeypatch.setattr(mdf, "get_search_query_arg", lambda *a, **k: "")
    f = mdf.parse_measurement_dashboard_filters(SimpleNamespace(args={}), TODAY)

    assert f.range_start == TODAY
    assert (f.range_end - f.range_start).days == dc.DASHBOARD_DATE_WINDOW_DAYS


# --- 일정 종류 → family -------------------------------------------------------
def test_schedule_kind_scopes():
    assert set(dc.dashboard_families_for_schedule_change({"measurement"})) == {
        "orders", "measurement", "construction", "history", "production",
    }
    assert set(dc.dashboard_families_for_schedule_change({"construction"})) == {
        "orders", "shipment", "construction", "history", "production",
    }
    assert set(dc.dashboard_families_for_schedule_change({"as_visit"})) == {
        "orders", "shipment", "construction",
    }
    # 품목 날짜는 품목 dict 안에 있다 → 실측 제품 목록 DTO 도.
    assert "measurement" in dc.dashboard_families_for_schedule_change(
        {"construction"}, item_level=True
    )
    assert set(dc.dashboard_families_for_schedule_change({"completion"})) == ALL


# =========================================================================== #
# 2) 라우트 계약 — 실제 요청이 비우는 family
# =========================================================================== #
@pytest.fixture
def family_spy(monkeypatch):
    seen: list[str] = []

    def _spy(family):
        seen.append(family)
        return 0

    monkeypatch.setattr(dc, "invalidate_dashboard_family", _spy)
    return seen


def _login(client, username, *, role="ADMIN", team="CS") -> int:
    user = User(username=username, password=generate_password_hash("pw"), role=role,
                team=team, name=f"{username} 이름", is_active=True)
    db_session.add(user)
    db_session.commit()
    uid = user.id
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["username"] = username
        sess["role"] = role
    return uid


def _seed(stage, *, measurement="", construction="", status=None, quests=None, **sd_extra) -> int:
    sd = {
        "workflow": {"stage": stage},
        "flags": {"urgent": False},
        "assignments": {},
        "parties": {"customer": {"name": "홍길동", "phone": "010-1234-5678"},
                    "manager": {"name": "영업"}},
        "items": [{"product_name": "붙박이장"}],
        "site": {"address_full": "서울 테헤란로 1", "address_main": "서울 테헤란로 1",
                 "address_detail": ""},
        "schedule": {"measurement": {"date": measurement}, "construction": {"date": construction}},
        "shipment": {},
    }
    if quests is not None:
        sd["quests"] = quests
    sd.update(sd_extra)
    order = Order(
        received_date="2026-09-01", customer_name="홍길동", phone="010-1234-5678",
        address="서울 테헤란로 1", product="붙박이장", status=status or stage,
        manager_name="영업", is_erp_order=True, erp_stage_code=stage, structured_data=sd,
    )
    db_session.add(order)
    db_session.commit()
    return int(order.id)


def _put_form(client, oid, mutate) -> None:
    sd = copy.deepcopy(client.get(f"/api/orders/{oid}/structured").get_json()["structured_data"])
    mutate(sd)
    resp = client.put(f"/api/orders/{oid}/structured",
                      json={"structured_data": sd, "structured_schema_version": 1})
    assert resp.status_code == 200, resp.get_json()


def test_put_structured_on_production_order_keeps_unrelated_tabs(client, family_spy):
    """생산 주문(실측 지난달·시공 두 달 뒤)의 품목 메모 저장 → orders + 생산만. 실측 패널(miss
    1.2초)·출고·시공·이력·도면 캐시는 남는다. 수정 전 코드는 7 family 를 전부 비웠다."""
    _login(client, "p12_put_prod")
    oid = _seed("PRODUCTION", measurement=_iso(-40), construction=_iso(60))
    family_spy.clear()

    _put_form(client, oid, lambda sd: sd["items"][0].update({"memo": "색상 확인"}))

    assert set(family_spy) == {"orders", "production"}


def test_put_structured_on_measure_order_clears_measurement(client, family_spy):
    """내일 실측 주문 저장 → 실측 탭 캐시는 비워진다(보이는 탭), 나머지는 남는다."""
    _login(client, "p12_put_measure")
    oid = _seed("MEASURE", measurement=_iso(1))
    family_spy.clear()

    _put_form(client, oid, lambda sd: sd["items"][0].update({"memo": "치수 재확인"}))

    assert set(family_spy) == {"orders", "measurement"}


def test_put_structured_customer_rename_clears_history(client, family_spy):
    _login(client, "p12_put_rename")
    oid = _seed("PRODUCTION", measurement=_iso(-40), construction=_iso(60))
    family_spy.clear()

    _put_form(client, oid, lambda sd: sd["parties"]["customer"].update({"name": "김철수"}))

    assert "history" in family_spy
    assert not {"measurement", "shipment", "drawing"} & set(family_spy)


def test_put_structured_construction_date_change_clears_shipment(client, family_spy):
    """시공일 변경 → 출고 패널·시공/생산 숫자판(날짜 동기화 리스너 종류별 범위 포함)."""
    _login(client, "p12_put_cons")
    oid = _seed("PRODUCTION", measurement=_iso(-40), construction=_iso(60))
    family_spy.clear()

    _put_form(client, oid, lambda sd: sd["schedule"]["construction"].update({"date": _iso(5)}))

    assert {"orders", "shipment", "production", "history"} <= set(family_spy)
    assert not {"measurement", "drawing"} & set(family_spy)


def test_inline_patch_scopes_like_put(client, family_spy, monkeypatch):
    monkeypatch.setenv("FOMS_INLINE_EDIT_ENABLED", "true")
    _login(client, "p12_patch")
    oid = _seed("PRODUCTION", measurement=_iso(-40), construction=_iso(60))
    family_spy.clear()

    resp = client.patch(f"/api/orders/{oid}/structured/fields",
                        json={"field": "items.0.color", "value": "크림"})

    assert resp.status_code == 200, resp.get_json()
    assert set(family_spy) == {"orders", "production"}


def test_payment_confirm_clears_orders_only(client, family_spy):
    """결제 확인 값은 어느 family 캐시 DTO 에도 없다 → orders 만(여유)."""
    _login(client, "p12_pay")
    oid = _seed("MEASURE", measurement=_iso(1))
    family_spy.clear()

    resp = client.post(f"/api/orders/{oid}/payment-confirm",
                       json={"type": "deposit", "confirmed": True})

    assert resp.status_code == 200, resp.get_json()
    assert family_spy == ["orders"]


def _team_quest(stage_code: str, teams: list[str]) -> dict:
    return {
        "stage": stage_code, "title": f"{stage_code} quest", "description": "",
        "owner_team": teams[0], "owner_person": "", "status": "OPEN",
        "required_approvals": list(teams),
        "team_approvals": {t: {"approved": False, "approved_by": None, "approved_at": None}
                           for t in teams},
        "approval_mode": "team", "assignee_approval": None,
        "created_at": "2026-07-24T00:00:00", "updated_at": "2026-07-24T00:00:00",
    }


def _assignee_quest(stage_code: str) -> dict:
    return {
        "stage": stage_code, "title": f"{stage_code} quest", "description": "",
        "owner_team": "SALES", "owner_person": "", "status": "OPEN",
        "required_approvals": ["SALES"], "team_approvals": {}, "approval_mode": "assignee",
        "assignee_approval": {"approved": False, "approved_by": None,
                              "approved_by_name": None, "approved_at": None},
        "created_at": "2026-07-24T00:00:00", "updated_at": "2026-07-24T00:00:00",
    }


def test_quest_create_and_status_clear_orders_only(client, family_spy):
    _login(client, "p12_quest")
    oid = _seed("MEASURE", measurement=_iso(1), quests=[])
    family_spy.clear()

    created = client.post(f"/api/orders/{oid}/quest", json={"stage": "MEASURE"})
    assert created.status_code == 200, created.get_json()
    assert family_spy == ["orders"]

    family_spy.clear()
    updated = client.put(f"/api/orders/{oid}/quest/status", json={"status": "IN_PROGRESS"})
    assert updated.status_code == 200, updated.get_json()
    assert family_spy == ["orders"]


def test_partial_quest_approval_clears_orders_only(client, family_spy):
    _login(client, "p12_quest_partial", role="STAFF", team="CS")
    oid = _seed("RECEIVED", quests=[_team_quest("RECEIVED", ["CS", "SALES"])])
    family_spy.clear()

    resp = client.post(f"/api/orders/{oid}/quest/approve", json={"team": "CS"})

    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["auto_transitioned"] is False
    assert family_spy == ["orders"]


def test_final_quest_approval_transition_clears_both_stage_tabs(client, family_spy):
    """실측→도면 전이: 리스너가 떠난 실측·도착한 도면 탭을 비운다. 출고·이력 등은 남는다."""
    _login(client, "p12_quest_final", role="STAFF", team="SALES")
    oid = _seed("MEASURE", measurement=_iso(-3), quests=[_assignee_quest("MEASURE")])
    family_spy.clear()

    resp = client.post(f"/api/orders/{oid}/quest/approve", json={})

    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["auto_transitioned"] is True
    assert set(family_spy) == {"orders", "measurement", "drawing"}


def test_call_log_without_date_relies_on_listener(client, family_spy):
    _login(client, "p12_call")
    oid = _seed("PRODUCTION", measurement=_iso(-40))
    family_spy.clear()

    resp = client.post(f"/api/orders/{oid}/call-log", json={"result": "connected", "memo": "확인"})

    assert resp.status_code == 200, resp.get_json()
    assert set(family_spy) == {"orders", "production"}


def test_call_log_with_measurement_date_clears_measurement(client, family_spy):
    _login(client, "p12_call_date")
    oid = _seed("MEASURE", measurement=_iso(2))
    family_spy.clear()

    resp = client.post(f"/api/orders/{oid}/call-log",
                       json={"result": "schedule_confirmed", "measurement_date": _iso(4)})

    assert resp.status_code == 200, resp.get_json()
    assert "measurement" in family_spy
    assert not {"shipment", "drawing"} & set(family_spy)


def test_confirm_drawing_receipt_scopes_like_revision(client, family_spy):
    """수령 확정: 도면 큐·생산/시공 첨부 개수(옛 도면 빼기)·orders. 실측·출고·이력은 남는다."""
    _login(client, "p12_receipt", team="SALES")
    oid = _seed(
        "DRAWING", measurement=_iso(-10), drawing_status="TRANSFERRED",
        drawing_current_files=[{"key": "orders/1/final.pdf", "name": "final.pdf"}],
        drawing_transfer_history=[{"action": "TRANSFER", "files": []}],
    )
    family_spy.clear()

    resp = client.post(f"/api/orders/{oid}/confirm-drawing-receipt", json={})

    assert resp.status_code == 200, resp.get_json()
    assert set(family_spy) == {"orders", "drawing", "production", "construction"}


def test_as_register_stays_broad_and_as_log_does_not(client, family_spy):
    """AS 접수는 status 투영이 바뀌는 전이 → broad 유지. 타임라인 기록은 리스너(orders+단계)만."""
    _login(client, "p12_as")
    oid = _seed("CS")
    family_spy.clear()

    reg = client.post(f"/api/orders/{oid}/as/register", json={"as_content": "문 경첩 파손"})
    assert reg.status_code == 200, reg.get_json()
    assert set(family_spy) == ALL

    family_spy.clear()
    log = client.post(f"/api/orders/{oid}/as/log", json={"type": "call", "text": "고객 통화"})
    assert log.status_code == 200, log.get_json()
    assert set(family_spy) == {"orders", "construction"}


def test_erp_draft_create_clears_nothing(client, family_spy):
    """초안은 어느 대시보드에도 없다 — 생성만으로 비울 캐시가 없다(날짜 동기화 포함)."""
    _login(client, "p12_draft")
    family_spy.clear()

    resp = client.post("/api/orders/erp/draft", json={})

    assert resp.status_code == 200, resp.get_json()
    assert family_spy == []


# =========================================================================== #
# 3) 날짜 동기화 리스너 — 바뀐 일정 종류만
# =========================================================================== #
def _reassign_sd(order: Order, mutate) -> None:
    sd = copy.deepcopy(order.structured_data)
    mutate(sd)
    order.structured_data = sd
    flag_modified(order, "structured_data")


def test_date_sync_measurement_change_scopes_to_measurement_axis(app, family_spy):
    oid = _seed("MEASURE", measurement=_iso(1))
    family_spy.clear()

    order = db_session.get(Order, oid)
    _reassign_sd(order, lambda sd: sd["schedule"]["measurement"].update({"date": _iso(2)}))
    db_session.commit()

    assert set(family_spy) == {"orders", "measurement", "construction", "history", "production"}


def test_date_sync_construction_change_scopes_to_shipment_axis(app, family_spy):
    oid = _seed("PRODUCTION", construction=_iso(30))
    family_spy.clear()

    order = db_session.get(Order, oid)
    _reassign_sd(order, lambda sd: sd["schedule"]["construction"].update({"date": _iso(5)}))
    db_session.commit()

    assert set(family_spy) == {"orders", "shipment", "construction", "history", "production"}


def test_date_sync_item_level_construction_date_also_clears_measurement(app, family_spy):
    oid = _seed("PRODUCTION", construction=_iso(30))
    family_spy.clear()

    order = db_session.get(Order, oid)
    _reassign_sd(order, lambda sd: sd["items"][0].update({"construction_date": _iso(6)}))
    db_session.commit()

    assert "measurement" in family_spy and "shipment" in family_spy


def test_date_sync_new_order_stays_broad(app, family_spy):
    _seed("RECEIVED", measurement=_iso(3))
    assert set(family_spy) == ALL


def test_date_sync_new_draft_clears_nothing(app, family_spy):
    order = Order(
        received_date="2026-10-01", customer_name="ERP Order", phone="000-0000-0000",
        address="-", product="ERP Order", status="DRAFT", is_erp_order=True,
        structured_data={"workflow": {"stage": "RECEIVED"}, "meta": {"draft": True},
                         "schedule": {"measurement": {"date": _iso(1)}}},
    )
    db_session.add(order)
    db_session.commit()
    assert family_spy == []


def test_date_sync_status_change_with_date_change_stays_broad(app, family_spy):
    """날짜와 소속(status) 변화가 한 트랜잭션에 섞이면 어느 탭이 바뀔지 모른다 → broad."""
    oid = _seed("PRODUCTION", construction=_iso(30))
    family_spy.clear()

    order = db_session.get(Order, oid)
    order.status = "AS_RECEIVED"
    _reassign_sd(order, lambda sd: sd["schedule"]["construction"].update({"date": _iso(4)}))
    db_session.commit()

    assert set(family_spy) == ALL
