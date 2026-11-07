"""프리랜서 화면 묶음 — 출고 · 시공 판(foms/services/auth/freelancer_screens/shipment.py).

사용자 결정(2026-11-07): 프리랜서도 회사 영업 때 쓰던 화면을 쓰되 보이는 주문은 모두 자기 것이다.

* 연 화면 · 조각 · 읽기 API 마다 켜진 프리랜서는 200 이고, 내 고객은 있고 남의 고객 · 남의 주문 번호는 없다.
* 회사 전체로 세는 칸(날짜별 잔여 시공 · 잔여 자수 띠 · 태블릿 시트의 시공팀 잔여) · 협력사 희망일 판 · AS 일정 추천 ·
  출고 설정 링크는 프리랜서에게 없다.
* 주문 번호가 실린 문은 남의 주문이면 404(문지기 겹 2). 출고 설정은 이 묶음이 열지 않는다(쓰기 API 는 이 묶음 밖).
* 대조군(같은 모집단): 프리랜서 아닌 영업 직원은 같은 요청에서 내 것 · 남의 것을 모두 보고, 숨긴 칸도 본다.
* 캐시 층: 직원 → 프리랜서 → 직원 순서로 번갈아 그려도 섞이지 않는다.

모든 이름 · 번호는 가짜 값이다.
"""
from __future__ import annotations

import datetime
import itertools
from types import SimpleNamespace

import pytest

from db import db_session
from foms.api.shipment.recommendations import SHREC_SOURCE
from foms.services.common import dashboard_cache
from foms.services.datetime_kst import get_today_kst
from foms.services.sales_commission.settings import load_settings, save_freelancer
from foms.web.shipment import dashboard as shipment_dashboard
from models import Order, OrderFreelancerLink, OrderScheduleDate, PartnerOrg
from tests.domains.test_auth_finance import _login, _make_user
from tests.support.fragver_fake_redis import FakeRedis

_seq = itertools.count(1)
OWN = "출고본인고객"
OWN_AS = "출고본인에이에스"
OTHER = "출고남고객"
OTHER_FAR = "출고먼남고객"        # 14일 패널 밖(오늘+20) — 검색 날짜 고르기 · 기간 조회(별도 쿼리) 경로
PARTNER_OTHER = "출고협력남고객"  # 협력사 희망일 판(확정 대기) — 회사 전체 목록
PHONE = "02-0000-0000"
_SHELL = {"X-FOMS-ERP-SHELL": "1"}


def _day(n: int = 0) -> str:
    return (get_today_kst() + datetime.timedelta(days=n)).isoformat()


def _order(customer: str, *, manager: str, day: str | None, status: str = "CONSTRUCTION",
           extra: dict | None = None, partner_org_id: int | None = None, stage: str = "CONSTRUCTION") -> int:
    """시공 단계 ERP 주문 1건(시공 판 범위) + 그날 시공 일정 행(출고 판 범위)."""
    sd = {
        "parties": {"manager": {"name": manager}, "customer": {"name": customer}, "orderer": {"name": "라홈"}},
        "workflow": {"stage": stage},
        "items": [{"product_name": "가짜장", "spec_width": "1200", "quantity": 1}],
        "site": {"address_full": "가짜시 가짜구 출고로 1"},
        **(extra or {}),
    }
    order = Order(
        received_date=_day(), customer_name=customer, phone=PHONE, address="가짜시 가짜구 출고로 1",
        product="가짜장", status=status, manager_name=manager, is_erp_order=True, structured_data=sd,
        erp_stage_code=stage, partner_org_id=partner_org_id,
    )
    db_session.add(order)
    db_session.flush()
    if day:
        kind = "as_visit" if status.startswith("AS") else "construction"
        db_session.add(OrderScheduleDate(order_id=order.id, kind=kind, date=day, source="beta_schedule"))
    db_session.commit()
    return order.id


def _ensure_link(order_id: int, user_id: int) -> None:
    if not db_session.query(OrderFreelancerLink).filter_by(order_id=order_id, user_id=user_id).count():
        db_session.add(OrderFreelancerLink(order_id=order_id, user_id=user_id, relation="MANAGER_PRIMARY"))
        db_session.commit()


def _user(role: str, team: str) -> SimpleNamespace:
    user = _make_user(role, team)
    return SimpleNamespace(id=user.id, username=user.username, role=role, team=team)


@pytest.fixture()
def w(app):
    """프리랜서 1 · 대조군 영업 직원 1 + 내 주문 2(시공 · AS) · 남의 주문 3(오늘 시공 · 먼 날 시공 · 협력사 확정 대기)."""
    fl = _user("STAFF", "SALES")
    match = f"출고프리{next(_seq)}"
    save_freelancer(db_session, fl.id, {"match_name": match, "start_month": "2020-01", "tax_type": "NONE",
                                        "active": True},
                    base_version=load_settings(db_session)[0], actor_user_id=None)
    db_session.commit()
    staff = _user("STAFF", "SALES")

    other = _order(OTHER, manager="남의담당", day=_day())
    far = _order(OTHER_FAR, manager="남의담당", day=_day(20))
    org = PartnerOrg(name=f"가짜협력사{next(_seq)}")
    db_session.add(org)
    db_session.commit()
    partner = _order(PARTNER_OTHER, manager="남의담당", day=None, status="MEASURE", stage="MEASURE",
                     partner_org_id=org.id,
                     extra={"partner_intake": {"requested_construction": {"date": _day(3), "time": "오전"}}})
    own = _order(OWN, manager=match, day=_day())
    # 내 AS 주문 — 남의 출고 주문을 기준으로 AS 추천이 붙어 있다(추천 취소 단추가 남의 주문 번호를 싣는다).
    own_as = _order(OWN_AS, manager=match, day=_day(), status="AS_RECEIVED", stage="AS", extra={
        "schedule": {"as_visit": {"date": _day(), "shipment_recommendation": {
            "source": SHREC_SOURCE, "shipment_order_id": other, "applied_date": _day()}}},
    })
    for order_id in (own, own_as):
        _ensure_link(order_id, fl.id)
    return SimpleNamespace(fl=fl, staff=staff, own=own, own_as=own_as, other=other, far=far, partner=partner,
                           others=(other, far, partner))


def _client(app, user):
    client = app.test_client()
    _login(client, user)
    return client


def _get(app, user, path: str, *, status: int = 200, headers: dict | None = None) -> str:
    resp = _client(app, user).get(path, headers=headers or {})
    assert resp.status_code == status, (path, resp.status_code, resp.headers.get("Location"))
    return resp.get_data(as_text=True)


def _id_marks(order_id: int) -> tuple[str, ...]:
    """화면이 주문 번호를 싣는 자리(행 · 링크 · 시트 · 추천 단추)."""
    return (f'data-order-id="{order_id}"', f"/edit/{order_id}", f"/erp/orders/{order_id}/",
            f"tablet-sheet/{order_id}", f'data-shipment-order-id="{order_id}"')


def _assert_only_own(body: str, w, own_names=(OWN,), other_names=(OTHER, OTHER_FAR, PARTNER_OTHER)) -> None:
    missing = [n for n in own_names if n not in body]
    leaked = [n for n in other_names if n in body]
    leaked_ids = [m for oid in w.others for m in _id_marks(oid) if m in body]
    assert not missing and not leaked and not leaked_ids, {"missing": missing, "leaked": leaked, "ids": leaked_ids}


def _v2(monkeypatch, *users) -> None:
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", ",".join(str(u.id) for u in users))


# --------------------------------------------------------------------------
# 출고 판
# --------------------------------------------------------------------------
@pytest.mark.parametrize("query", ["", "?mine=0", "?mine=", f"?date={_day()}"])
def test_shipment_board_lists_only_own_orders(w, app, query):
    body = _get(app, w.fl, f"/erp/shipment{query}")
    _assert_only_own(body, w, own_names=(OWN, OWN_AS))
    assert f'data-order-id="{w.own}"' in body  # 번호 표식이 실제로 찍히는 자리를 본다는 증거(양성 대조)
    control = _get(app, w.staff, f"/erp/shipment{query or '?mine=0'}")
    assert OWN in control and OTHER in control and f'data-order-id="{w.other}"' in control


def test_shipment_fragment_is_scoped(w, app):
    body = _get(app, w.fl, "/erp/shipment?view=fragment", headers=_SHELL)
    _assert_only_own(body, w, own_names=(OWN, OWN_AS))
    assert OTHER in _get(app, w.staff, "/erp/shipment?view=fragment", headers=_SHELL)


def test_shipment_search_and_out_of_panel_range_are_scoped(w, app):
    """검색어로 날짜를 고르는 쿼리 · 14일 밖 기간 조회(별도 쿼리)도 남의 주문을 싣지 않는다."""
    term = OTHER_FAR[:3]  # 검색창 · 칩이 검색어를 되돌려 싣으므로 고객명 앞부분으로 찾는다
    body = _get(app, w.fl, f"/erp/shipment?q={term}")
    assert OTHER_FAR not in body and f'data-order-id="{w.far}"' not in body
    assert _day(20) not in body  # 남의 주문 날짜로 기준일이 옮겨 가지 않는다
    control = _get(app, w.staff, f"/erp/shipment?q={term}")
    assert f'data-order-id="{w.far}"' in control and _day(20) in control

    span = f"?date_from={_day(15)}&date_to={_day(25)}"
    assert f'data-order-id="{w.far}"' not in _get(app, w.fl, f"/erp/shipment{span}")
    assert f'data-order-id="{w.far}"' in _get(app, w.staff, f"/erp/shipment{span}")


def test_shipment_mobile_queue_is_scoped(w, app, monkeypatch):
    _v2(monkeypatch, w.fl, w.staff)
    body = _get(app, w.fl, "/erp/shipment?mine=0")
    _assert_only_own(body, w, own_names=(OWN, OWN_AS))
    assert "erp-shipment-mobile-card" in body
    assert OTHER in _get(app, w.staff, "/erp/shipment?mine=0")


def test_shipment_company_wide_panels_and_tools_are_hidden(w, app):
    """잔여 시공 · 잔여 자수 띠 · 협력사 희망일 판 · AS 추천 · 설정 링크: 직원은 보고 프리랜서는 없다."""
    company_marks = ("날짜별 잔여 시공", "foms-ship-cap-strip", "협력사 희망 시공일", "shipmentAsRecommendModal",
                     "data-shipment-as-recommend-open", "/erp/shipment-settings", "data-kakao-js-key=",
                     'data-can-edit="true"')
    control = _get(app, w.staff, "/erp/shipment")
    assert [m for m in company_marks if m not in control] == []
    assert PARTNER_OTHER in control and f'data-shipment-order-id="{w.other}"' in control
    body = _get(app, w.fl, "/erp/shipment")
    assert [m for m in company_marks if m in body] == []
    assert 'data-can-edit="false"' in body
    _assert_only_own(body, w, own_names=(OWN, OWN_AS))


def test_tablet_sheet_own_only_without_company_capacity(w, app, monkeypatch):
    roster = {"construction_workers": [{"name": "가짜시공1팀", "capacity": 40}]}
    monkeypatch.setattr(shipment_dashboard, "load_erp_shipment_settings", lambda: roster)
    body = _get(app, w.fl, f"/erp/shipment/tablet-sheet/{w.own}")
    assert OWN in body and "가짜시공1팀" in body and "foms-ship-sheet__team-remain" not in body
    _get(app, w.fl, f"/erp/shipment/tablet-sheet/{w.other}", status=404)
    control = _get(app, w.staff, f"/erp/shipment/tablet-sheet/{w.other}")
    assert OTHER in control and "foms-ship-sheet__team-remain" in control


# --------------------------------------------------------------------------
# 시공 판
# --------------------------------------------------------------------------
@pytest.mark.parametrize("query", ["", "?mine=0", "?mine=", "?q=출고", "?stage=시공대기"])
def test_construction_board_lists_only_own_orders(w, app, query):
    body = _get(app, w.fl, f"/erp/construction/dashboard{query}")
    _assert_only_own(body, w)
    control = _get(app, w.staff, f"/erp/construction/dashboard{query or '?mine=0'}")
    assert OWN in control and OTHER in control


def test_construction_mobile_queue_is_scoped(w, app, monkeypatch):
    _v2(monkeypatch, w.fl, w.staff)
    _assert_only_own(_get(app, w.fl, "/erp/construction/dashboard?mine=0"), w)
    assert OTHER in _get(app, w.staff, "/erp/construction/dashboard?mine=0")


def test_construction_focus_order(w, app):
    assert OWN in _get(app, w.fl, f"/erp/construction/dashboard?focus_order={w.own}")
    _get(app, w.fl, f"/erp/construction/dashboard?focus_order={w.other}", status=404)
    _get(app, w.fl, f"/erp/construction/dashboard?focus_order={w.own}&focus_order={w.other}", status=404)
    assert OTHER in _get(app, w.staff, f"/erp/construction/dashboard?focus_order={w.other}")


# --------------------------------------------------------------------------
# 읽기 API · 주문 1건 조각
# --------------------------------------------------------------------------
@pytest.mark.parametrize("path", [
    "/api/erp/shipment/packing/{oid}",
    "/api/orders/{oid}/detail-payload",
    "/erp/orders/{oid}/label",
    "/api/orders/{oid}/qr.svg",
])
def test_single_order_reads_own_200_other_404(w, app, path):
    client = _client(app, w.fl)
    assert client.get(path.format(oid=w.own)).status_code == 200
    theirs = client.get(path.format(oid=w.other))
    assert theirs.status_code == 404
    if "/api/" in path:
        assert theirs.get_json()["success"] is False
    assert _client(app, w.staff).get(path.format(oid=w.other)).status_code == 200  # 대조군


def test_label_shows_own_customer(w, app):
    assert OWN in _get(app, w.fl, f"/erp/orders/{w.own}/label")


# --------------------------------------------------------------------------
# 출고 설정(회사 전체 시공팀 · 용량)은 이 묶음이 열지 않는다
# --------------------------------------------------------------------------
def test_shipment_settings_stay_closed(w, app):
    client = _client(app, w.fl)
    page = client.get("/erp/shipment-settings")
    assert page.status_code == 302 and page.headers["Location"].endswith("/erp/dashboard")
    assert client.get("/api/erp/shipment-settings").status_code == 403
    assert _client(app, w.staff).get("/erp/shipment-settings").status_code == 200  # 대조군


# --------------------------------------------------------------------------
# 캐시 층
# --------------------------------------------------------------------------
@pytest.fixture()
def micro_cache(monkeypatch):
    """대시보드 조각 캐시(Redis)를 메모리 대역으로 켠다."""
    fake = FakeRedis()
    monkeypatch.setattr(dashboard_cache, "is_dashboard_micro_cache_enabled", lambda: True)
    monkeypatch.setattr(dashboard_cache, "get_dashboard_redis", lambda: fake)
    return fake


def test_dashboard_slice_cache_never_crosses_users(w, app, micro_cache):
    for _round in range(2):  # 두 번째 바퀴는 캐시에서 나온다
        assert OTHER in _get(app, w.staff, "/erp/shipment?mine=0")
        _assert_only_own(_get(app, w.fl, "/erp/shipment?mine=0"), w, own_names=(OWN, OWN_AS))
        assert OTHER in _get(app, w.staff, "/erp/construction/dashboard?mine=0")
        _assert_only_own(_get(app, w.fl, "/erp/construction/dashboard?mine=0"), w)
    assert any(":shipment:" in key for key in micro_cache.kv)
    assert any(":construction:" in key for key in micro_cache.kv)
