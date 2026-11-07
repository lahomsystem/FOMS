"""FCOMM-01 화면 묶음: 완료 판 · AS 판을 프리랜서에게 연다 — 보이는 주문은 모두 자기 것.

묶음 파일: foms/services/auth/freelancer_screens/completion.py. 사용자 결정(2026-11-07): 회사 소속 때 쓰던 화면을
그대로 쓰되 보이는 주문은 모두 내 주문이어야 한다.

* 연 화면 · 조각 · 읽기 API 마다 프리랜서는 200, 내 고객명은 있고 남의 고객명 · 번호는 없다(``?mine=0`` 이어도).
* 숫자(완료 판 건수 · AS 탭 건수 · 일정 변경 배너)도 내 주문에서만 센다.
* AS 행이 가리키는 다른 주문(기준 일정 · 전달 배정의 기준 실측 주문)은 ``user_can_read_order`` 가 참일 때만 그린다 —
  내 주문을 가리키면 보이고, 남의 주문을 가리키면 이름 · 번호 · 담당 · 날짜가 빠진다.
* 주문 한 건 조각(정산 시트 · AS 카드 상세 · 회차 차트)과 ``?focus_order=`` 는 남의 번호면 404.
* 이 묶음은 판 화면과 읽기만 연다(쓰기 API 는 D27 변경이 맡는다 — 여기서 단언하지 않는다).
* 대조군(같은 모집단): 프리랜서 아닌 영업 직원은 전부 본다. 표시 함수는 프리랜서가 아니면 거르지 않는다.

모든 이름 · 번호는 가짜 값이다.
"""
from __future__ import annotations

import itertools
import re
from types import SimpleNamespace

import pytest

from db import db_session
from foms.services import as_dashboard_display as display
from foms.services.auth import freelancer_screens
from foms.services.auth.freelancer_scope import FREELANCER_ALLOWED_ENDPOINTS
from foms.services.datetime_kst import get_today_kst
from foms.services.erp_display import _ensure_dict
from foms.services.sales_commission.settings import load_settings, save_freelancer
from models import Order, OrderFreelancerLink, OrderScheduleDate, User
from tests.domains.test_auth_finance import _login, _make_user

_seq = itertools.count(1)
PHONE = "02-0000-0000"

OWN_DONE, OTHER_DONE = "본인완료손님", "남완료손님"
OWN_AS_A, OWN_AS_B, OTHER_AS = "본인에이손님", "본인비손님", "남에이손님"
OWN_SD_A, OWN_SD_B, OWN_SD_C, OTHER_SD = "본인전달갑손님", "본인전달을손님", "본인전달병손님", "남전달손님"
OWN_REF, OTHER_REF = "본인기준손님", "남기준손님"            # 기준 일정 링크가 가리키는 주문(AS 목록 밖)
OWN_MEAS, OTHER_MEAS = "본인실측손님", "남실측손님"          # 전달 배정이 가리키는 실측 주문(AS 목록 밖)
OWN_MEAS_MGR, OTHER_MEAS_MGR = "본인실측담당자", "남실측담당자"

OWN_COMPLETION = (OWN_DONE, OWN_AS_A, OWN_AS_B, OWN_SD_A, OWN_SD_B, OWN_SD_C)
OTHER_COMPLETION = (OTHER_DONE, OTHER_AS, OTHER_SD)

OPENED = {
    "erp_completion_page.erp_completion_dashboard",
    "erp_completion_page.erp_completion_export",
    "erp_completion_page.erp_completion_tablet_sheet",
    "erp_orders_completion.api_orders_completion",
    "erp_as_page.erp_as_dashboard",
    "erp_as_page.erp_as_card_detail",
    "erp_as_page.erp_as_timeline",
}


# --------------------------------------------------------------------------
# 시드(가짜 값)
# --------------------------------------------------------------------------
def _freelancer() -> SimpleNamespace:
    user = _make_user("STAFF", "SALES")
    match = f"가짜완료담당{next(_seq)}"
    save_freelancer(db_session, user.id, {"match_name": match, "start_month": "2020-01", "tax_type": "NONE",
                                          "active": True},
                    base_version=load_settings(db_session)[0], actor_user_id=None)
    db_session.commit()
    return SimpleNamespace(id=user.id, username=user.username, role="STAFF", team="SALES", match=match)


def _staff() -> SimpleNamespace:
    user = _make_user("STAFF", "SALES")
    return SimpleNamespace(id=user.id, username=user.username, role="STAFF", team="SALES")


def _order(customer: str, *, status: str, manager: str = "아무개", extra_sd: dict | None = None,
           construction_date: str | None = None) -> int:
    today = get_today_kst().isoformat()
    sd = {"parties": {"manager": {"name": manager}, "customer": {"name": customer}, "orderer": {"name": "라홈"}},
          "items": [{"product_name": "가짜장", "price": 1_000_000}], **(extra_sd or {})}
    if construction_date:
        sd.setdefault("schedule", {})["construction"] = {"date": construction_date}
    is_as = status.startswith("AS")
    order = Order(
        received_date=today, customer_name=customer, phone=PHONE, address="가짜시 가짜구", product="가짜장",
        status=status, manager_name=manager, is_erp_order=True, structured_data=sd,
        erp_construction_date=construction_date, as_received_date=today if is_as else None,
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _link(order_id: int, fl: SimpleNamespace) -> None:
    exists = db_session.query(OrderFreelancerLink.id).filter_by(order_id=order_id, user_id=fl.id).first()
    if exists is None:
        db_session.add(OrderFreelancerLink(order_id=order_id, user_id=fl.id, relation="MANAGER_PRIMARY"))
        db_session.commit()


def _own(fl: SimpleNamespace, customer: str, **kwargs) -> int:
    order_id = _order(customer, manager=fl.match, **kwargs)
    _link(order_id, fl)
    return order_id


def _schedule_link(ref_order_id: int) -> dict:
    """AS 방문 기준 일정 링크(write_link 출력 모양) — 기준 시공일이 08-05 → 08-12 로 움직였다(ref_moved)."""
    return {"as_visit": {"date": "2030-08-05", "schedule_link": {
        "ref_order_id": ref_order_id, "ref_kind": "construction", "ref_date": "2030-08-05",
        "linked_at": "2030-07-30T00:00:00", "linked_by_user_id": None, "linked_by": "가짜", "source": "as_nearby_modal",
        "ack_ref_date": None}}}


def _sales_delivery(ref_order_id: int, manager: str, status: str) -> dict:
    """영업 전달 배정(sales_delivery_link.write_link 출력 모양)."""
    return {"as_content": "<div>전달 건</div>", "sales_delivery": True, "sales_delivery_link": {
        "ref_order_id": ref_order_id, "ref_kind": "measurement", "ref_date": "2030-09-11", "ref_manager": manager,
        "assigned_at": "2030-09-01T00:00:00", "assigned_by_user_id": None, "assigned_by": "가짜",
        "source": "as_sales_delivery_modal", "ack_ref_date": None, "status": status,
        "delivered_at": "2030-09-11T01:00:00" if status == "delivered" else None,
        "delivered_by": "가짜" if status == "delivered" else None}}


def _measurement(customer: str, *, manager: str) -> int:
    order_id = _order(customer, status="MEASURE", manager=manager)
    db_session.add(OrderScheduleDate(order_id=order_id, kind="measurement", date="2030-09-11", source="test_seed"))
    db_session.commit()
    return order_id


@pytest.fixture()
def world(app):
    fl = _freelancer()
    staff = _staff()
    today = get_today_kst().isoformat()
    own_ref = _own(fl, OWN_REF, status="CONSTRUCTION", construction_date="2030-08-12")
    other_ref = _order(OTHER_REF, status="CONSTRUCTION", construction_date="2030-08-12")
    own_meas = _measurement(OWN_MEAS, manager=fl.match)
    _link(own_meas, fl)
    other_meas = _measurement(OTHER_MEAS, manager="아무개")
    ids = SimpleNamespace(
        own_done=_own(fl, OWN_DONE, status="COMPLETED", construction_date=today),
        other_done=_order(OTHER_DONE, status="COMPLETED", construction_date=today),
        own_as_a=_own(fl, OWN_AS_A, status="AS_RECEIVED",
                      extra_sd={"shipment": {"as_content": "<div>가</div>"}, "schedule": _schedule_link(other_ref)}),
        own_as_b=_own(fl, OWN_AS_B, status="AS_RECEIVED",
                      extra_sd={"shipment": {"as_content": "<div>나</div>"}, "schedule": _schedule_link(own_ref)}),
        other_as=_order(OTHER_AS, status="AS_RECEIVED",
                        extra_sd={"shipment": {"as_content": "<div>다</div>"}, "schedule": _schedule_link(other_ref)}),
        own_sd_a=_own(fl, OWN_SD_A, status="AS_RECEIVED",
                      extra_sd={"shipment": _sales_delivery(other_meas, OTHER_MEAS_MGR, "assigned")}),
        own_sd_b=_own(fl, OWN_SD_B, status="AS_RECEIVED",
                      extra_sd={"shipment": _sales_delivery(own_meas, OWN_MEAS_MGR, "delivered")}),
        own_sd_c=_own(fl, OWN_SD_C, status="AS_RECEIVED",
                      extra_sd={"shipment": _sales_delivery(other_meas, OTHER_MEAS_MGR, "delivered")}),
        other_sd=_order(OTHER_SD, status="AS_RECEIVED",
                        extra_sd={"shipment": _sales_delivery(other_meas, OTHER_MEAS_MGR, "delivered")}),
        own_ref=own_ref, other_ref=other_ref, own_meas=own_meas, other_meas=other_meas,
    )
    return SimpleNamespace(fl=fl, staff=staff, ids=ids)


def _client(app, user):
    client = app.test_client()
    _login(client, user)
    return client


def _get(app, user, path: str, *, status: int = 200) -> str:
    resp = _client(app, user).get(path)
    assert resp.status_code == status, (path, resp.status_code, resp.headers.get("Location"))
    return resp.get_data(as_text=True)


def _assert_only(text: str, own, others) -> None:
    missing = [name for name in own if name not in text]
    leaked = [name for name in others if name in text]
    assert not missing and not leaked, {"missing_own": missing, "leaked_others": leaked}


def _assert_all(text: str, names) -> None:
    assert [name for name in names if name not in text] == []


def _v2(monkeypatch, *users) -> None:
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", ",".join(str(u.id) for u in users))


def _tab_count(body: str, key: str) -> int:
    match = re.search(rf'data-as-tab-key="{key}"\s+data-as-tab-count="(\d+)"', body)
    assert match, key
    return int(match.group(1))


# --------------------------------------------------------------------------
# 묶음 파일이 문지기에 실렸다
# --------------------------------------------------------------------------
def test_screen_file_is_merged_into_gate():
    assert "completion" in freelancer_screens.MODULES
    assert OPENED <= FREELANCER_ALLOWED_ENDPOINTS


# --------------------------------------------------------------------------
# 완료 판
# --------------------------------------------------------------------------
@pytest.mark.parametrize("query", ["?mine=0", "?mine=", ""])
def test_completion_grid_and_counts_are_own_only(world, app, monkeypatch, query):
    _v2(monkeypatch, world.fl, world.staff)
    body = _get(app, world.fl, f"/erp/completion{query}")
    _assert_only(body, OWN_COMPLETION, OTHER_COMPLETION)
    assert "전체 · 6건" in body
    control = _get(app, world.staff, "/erp/completion?mine=0")
    _assert_all(control, OWN_COMPLETION + OTHER_COMPLETION)
    assert "전체 · 9건" in control


def test_completion_list_api_and_export_are_own_only(world, app):
    resp = _client(app, world.fl).get("/api/orders/completion?mine=0")
    assert resp.status_code == 200 and resp.get_json()["success"]
    ids = {row["id"] for row in resp.get_json()["orders"]}
    own_ids = {world.ids.own_done, world.ids.own_as_a, world.ids.own_as_b,
               world.ids.own_sd_a, world.ids.own_sd_b, world.ids.own_sd_c}
    assert ids == own_ids
    csv_text = _get(app, world.fl, "/erp/completion/export.csv?mine=0&as_include=1&fbar=1")
    _assert_only(csv_text, OWN_COMPLETION, OTHER_COMPLETION)

    control = _client(app, world.staff).get("/api/orders/completion?mine=0").get_json()
    other_ids = {world.ids.other_done, world.ids.other_as, world.ids.other_sd}
    assert {r["id"] for r in control["orders"]} == own_ids | other_ids
    _assert_all(_get(app, world.staff, "/erp/completion/export.csv?mine=0"), OWN_COMPLETION + OTHER_COMPLETION)


def test_completion_sheet_and_focus_are_order_scoped(world, app):
    ids = world.ids
    assert OWN_DONE in _get(app, world.fl, f"/erp/completion/tablet-sheet/{ids.own_done}")
    _get(app, world.fl, f"/erp/completion/tablet-sheet/{ids.other_done}", status=404)
    _get(app, world.fl, f"/erp/completion?focus_order={ids.other_done}", status=404)
    _get(app, world.fl, f"/erp/completion/export.csv?focus_order={ids.other_done}", status=404)
    resp = _client(app, world.fl).get(f"/api/orders/completion?focus_order={ids.other_done}")
    assert resp.status_code == 404
    focus = _client(app, world.fl).get(f"/api/orders/completion?focus_order={ids.own_done}").get_json()
    assert [row["id"] for row in focus["orders"]] == [ids.own_done]
    # 대조군: 보통 영업 직원은 남의 주문도 연다.
    assert OTHER_DONE in _get(app, world.staff, f"/erp/completion/tablet-sheet/{ids.other_done}")
    _get(app, world.staff, f"/erp/completion?focus_order={ids.other_done}")


# --------------------------------------------------------------------------
# AS 판
# --------------------------------------------------------------------------
@pytest.mark.parametrize("v2", [False, True])
def test_as_incomplete_tab_rows_counts_and_linked_refs(world, app, monkeypatch, v2):
    if v2:
        _v2(monkeypatch, world.fl, world.staff)
    body = _get(app, world.fl, "/erp/as?tab=incomplete&mine=0")
    _assert_only(body, (OWN_AS_A, OWN_AS_B), (OTHER_AS, OTHER_REF, OTHER_DONE))
    assert (_tab_count(body, "incomplete"), _tab_count(body, "sales_delivery")) == (2, 3)
    # 내 기준 주문은 읽을 수 있어 그대로, 남의 기준 주문을 가리키는 행은 링크가 없는 것처럼(배너도 1건).
    assert f"기준 {OWN_REF}" in body
    assert "현재 목록에서 기준 일정이 변경된 AS 1건" in body
    assert f'data-linked-ref-order-id="{world.ids.other_ref}"' not in body
    assert f'data-linked-ref-order-id="{world.ids.own_ref}"' in body

    control = _get(app, world.staff, "/erp/as?tab=incomplete&mine=0")
    _assert_all(control, (OWN_AS_A, OWN_AS_B, OTHER_AS, f"기준 {OWN_REF}", f"기준 {OTHER_REF}"))
    assert (_tab_count(control, "incomplete"), _tab_count(control, "sales_delivery")) == (3, 4)
    assert "현재 목록에서 기준 일정이 변경된 AS 3건" in control


def test_as_sales_delivery_tab_hides_unreadable_measurement_refs(world, app):
    ids = world.ids
    body = _get(app, world.fl, "/erp/as?tab=sales_delivery")
    _assert_only(body, (OWN_SD_A, OWN_SD_B, OWN_SD_C, OWN_MEAS),
                 (OTHER_SD, OTHER_MEAS, OTHER_MEAS_MGR, OTHER_AS))
    assert f"실측 #{ids.own_meas} {OWN_MEAS}" in body
    assert f"실측 #{ids.other_meas}" not in body

    control = _get(app, world.staff, "/erp/as?tab=sales_delivery&mine=0")
    _assert_all(control, (OWN_SD_A, OWN_SD_B, OWN_SD_C, OTHER_SD, OTHER_MEAS_MGR,
                          f"실측 #{ids.other_meas} {OTHER_MEAS}", f"실측 #{ids.own_meas} {OWN_MEAS}"))


def test_as_search_and_focus_stay_inside_own_orders(world, app):
    ids = world.ids
    _get(app, world.fl, f"/erp/as?focus_order={ids.other_as}&mine=0", status=404)
    # 남의 고객명으로 찾아도 내 범위 안에서만 찾는다 — 결과 0건(자동 이동 없음).
    body = _get(app, world.fl, f"/erp/as?tab=incomplete&mine=0&q={OTHER_AS}")
    assert (_tab_count(body, "incomplete"), _tab_count(body, "sales_delivery")) == (0, 0)
    assert f'data-order-id="{ids.other_as}"' not in body
    resp = _client(app, world.fl).get(f"/erp/as?focus_order={ids.own_as_b}&mine=0")
    assert resp.status_code == 200 and OWN_AS_B in resp.get_data(as_text=True)
    # 대조군: 보통 영업 직원은 같은 검색이 그 한 건으로 바로 간다 · 남의 번호 딥링크도 연다.
    control = _client(app, world.staff).get(f"/erp/as?tab=incomplete&mine=0&q={OTHER_AS}")
    assert control.status_code == 302 and f"focus_order={ids.other_as}" in control.headers["Location"]
    _get(app, world.staff, f"/erp/as?focus_order={ids.other_as}&mine=0")


@pytest.mark.parametrize("fragment", ["card-detail", "timeline"])
def test_as_order_fragments_are_order_scoped(world, app, fragment):
    ids = world.ids
    _get(app, world.fl, f"/erp/as/{fragment}/{ids.own_as_a}")
    _get(app, world.fl, f"/erp/as/{fragment}/{ids.other_as}", status=404)
    _get(app, world.staff, f"/erp/as/{fragment}/{ids.other_as}")


# --------------------------------------------------------------------------
# 표시 함수: 프리랜서가 아니면 거르지 않는다(직원 화면 그대로)
# --------------------------------------------------------------------------
def _display_snapshot(rows) -> list[tuple]:
    return [(r.id, r.schedule_link_drift, r.sales_delivery_link, r.sales_delivery_drift, r.sales_delivery_state)
            for r in rows]


def _as_rows(ids) -> list[Order]:
    wanted = [ids.own_as_a, ids.own_as_b, ids.other_as, ids.own_sd_a, ids.own_sd_b, ids.own_sd_c, ids.other_sd]
    rows = db_session.query(Order).filter(Order.id.in_(wanted)).order_by(Order.id).all()
    for r in rows:
        r.structured_data = _ensure_dict(r.structured_data)
    return rows


def test_display_filter_is_a_no_op_for_non_freelancers(world, app):
    with app.app_context():
        staff = db_session.get(User, world.staff.id)
        assert display._freelancer_ref_reader(None) is None
        assert display._freelancer_ref_reader(staff) is None
        rows = _as_rows(world.ids)
        base_banner = display.apply_schedule_link_drift_fields(rows, db_session)
        base_summary = display.apply_sales_delivery_display_fields(rows, db_session)
        before = _display_snapshot(rows)
        staff_banner = display.apply_schedule_link_drift_fields(rows, db_session, viewer=staff)
        staff_summary = display.apply_sales_delivery_display_fields(rows, db_session, viewer=staff)
        assert (staff_banner, staff_summary, _display_snapshot(rows)) == (base_banner, base_summary, before)
        assert base_banner["count"] == 3 and base_summary["delivered"] == 3


def test_display_filter_hides_only_unreadable_refs_for_freelancer(world, app):
    with app.app_context():
        fl_user = db_session.get(User, world.fl.id)
        rows = {r.id: r for r in _as_rows(world.ids)}
        banner = display.apply_schedule_link_drift_fields(list(rows.values()), db_session, viewer=fl_user)
        summary = display.apply_sales_delivery_display_fields(list(rows.values()), db_session, viewer=fl_user)
        ids = world.ids
        assert rows[ids.own_as_a].schedule_link_drift["state"] == "none"      # 남의 기준 주문 → 링크 없음처럼
        assert rows[ids.own_as_b].schedule_link_drift["ref_label"] == OWN_REF  # 내 기준 주문 → 그대로
        assert rows[ids.own_sd_a].sales_delivery_link is None
        assert rows[ids.own_sd_a].sales_delivery_state == "assigned"           # 내 AS 건의 배정 상태는 그대로
        assert rows[ids.own_sd_b].sales_delivery_link["ref_customer_name"] == OWN_MEAS
        # 이 단위 시험은 남의 AS 행도 직접 넘긴다 — 남의 기준 주문을 가리키는 링크는 모두 빠지고 내 것 1건만 남는다.
        assert banner["count"] == 1
        assert rows[ids.own_sd_c].sales_delivery_link is None and rows[ids.own_sd_c].sales_delivery_state == "delivered"
        assert summary["delivered"] == 3 and summary["drift"] == 0
