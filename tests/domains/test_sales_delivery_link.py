"""AS 영업 전달 배정 링크(sales_delivery_link) 순수 서비스 테스트.

스펙: docs/specs/2026-09-09-as-sales-delivery-measurement-assignment-design.md (§2, §3).
DB/Flask 불필요 — dict fixture 만으로 검증한다.
"""
from datetime import date, datetime

import pytest

from foms.services.orders.sales_delivery_link import (
    LINK_PATH,
    METHOD_KEY,
    PARCEL_KEY,
    SOURCE_MODAL,
    ack_link,
    clear_link,
    derive_display_state,
    evaluate_drift,
    mark_delivered,
    read_link,
    read_method,
    set_method,
    unmark_delivered,
    write_link,
)

_NOW = datetime(2026, 9, 9, 5, 30, 0)


def _assign(sd, *, ref_date="2026-09-15", ref_order_id=7788):
    """테스트 공용 배정 헬퍼 — 기본 인자로 링크 하나를 만든다."""
    return write_link(
        sd,
        ref_order_id=ref_order_id,
        ref_date=ref_date,
        ref_manager="김영업",
        actor_user_id=42,
        actor_name="홍길동",
        now=_NOW,
    )


# --- 스키마 / 경로 ---------------------------------------------------------


def test_read_link_missing_returns_none():
    assert read_link({}) is None
    assert read_link(None) is None
    assert read_link({"shipment": {}}) is None
    assert read_link({"shipment": {"sales_delivery_link": "nope"}}) is None


def test_write_link_creates_exact_schema_at_link_path():
    sd = {}
    link = _assign(sd)
    assert link == {
        "ref_order_id": 7788,
        "ref_kind": "measurement",
        "ref_date": "2026-09-15",
        "ref_manager": "김영업",
        "assigned_at": "2026-09-09T05:30:00",
        "assigned_by_user_id": 42,
        "assigned_by": "홍길동",
        "source": SOURCE_MODAL,
        "ack_ref_date": None,
        "status": "assigned",
        "delivered_at": None,
        "delivered_by": None,
    }
    assert sd[LINK_PATH[0]][LINK_PATH[-1]] == link
    assert read_link(sd) == link


def test_write_link_does_not_touch_as_visit_schedule_link_axis():
    """기존 AS 방문일 축(schedule.as_visit.schedule_link)을 침범하지 않는다."""
    other = {"ref_order_id": 1, "ref_kind": "construction"}
    sd = {"schedule": {"as_visit": {"date": "2026-09-20", "schedule_link": other}}}
    _assign(sd)
    assert sd["schedule"]["as_visit"]["schedule_link"] is other
    assert sd["schedule"]["as_visit"]["date"] == "2026-09-20"


# --- 재배정 / 해제 ---------------------------------------------------------


def test_reassign_resets_ack_and_delivery():
    sd = {}
    _assign(sd)
    ack_link(sd, "2026-09-18")
    mark_delivered(sd, at=_NOW, by="홍길동")
    _assign(sd, ref_date="2026-09-22", ref_order_id=9001)
    link = read_link(sd)
    assert link["ack_ref_date"] is None
    assert link["status"] == "assigned"
    assert link["delivered_at"] is None
    assert link["ref_order_id"] == 9001
    assert link["ref_date"] == "2026-09-22"


def test_clear_link_is_idempotent():
    sd = {}
    _assign(sd)
    assert clear_link(sd) is True
    assert clear_link(sd) is False
    assert clear_link({}) is False
    assert read_link(sd) is None


# --- 드리프트 6상태 --------------------------------------------------------


def test_drift_state_none_without_link():
    result = evaluate_drift({}, "2026-09-15")
    assert result == {
        "state": "none",
        "ref_order_id": None,
        "ref_date": None,
        "ref_current_date": "2026-09-15",
        "ref_manager": None,
    }


def test_drift_state_ok_and_payload_fields():
    sd = {}
    _assign(sd)
    result = evaluate_drift(sd, "2026-09-15")
    assert result == {
        "state": "ok",
        "ref_order_id": 7788,
        "ref_date": "2026-09-15",
        "ref_current_date": "2026-09-15",
        "ref_manager": "김영업",
    }


def test_drift_state_ref_moved():
    sd = {}
    _assign(sd)
    assert evaluate_drift(sd, "2026-09-18")["state"] == "ref_moved"


def test_drift_state_acked_only_matches_current_ref_date():
    sd = {}
    _assign(sd)
    ack_link(sd, "2026-09-18")
    assert evaluate_drift(sd, "2026-09-18")["state"] == "acked"


def test_drift_ack_auto_invalidated_when_ref_moves_again():
    sd = {}
    _assign(sd)
    ack_link(sd, "2026-09-18")
    assert evaluate_drift(sd, "2026-09-25")["state"] == "ref_moved"


def test_drift_state_resolved_when_ref_returns_to_original():
    sd = {}
    _assign(sd)
    ack_link(sd, "2026-09-18")
    assert evaluate_drift(sd, "2026-09-15")["state"] == "resolved"


def test_drift_state_ref_gone_when_current_date_missing():
    sd = {}
    _assign(sd)
    assert evaluate_drift(sd, None)["state"] == "ref_gone"
    assert evaluate_drift(sd, "")["state"] == "ref_gone"


# --- 전달 완료 왕복 --------------------------------------------------------


def test_mark_and_unmark_delivered_roundtrip():
    sd = {}
    _assign(sd)
    assert mark_delivered(sd, at=_NOW, by="홍길동") is True
    link = read_link(sd)
    assert link["status"] == "delivered"
    assert link["delivered_at"] == "2026-09-09T05:30:00"
    assert link["delivered_by"] == "홍길동"

    assert unmark_delivered(sd) is True
    link = read_link(sd)
    assert link["status"] == "assigned"
    assert link["delivered_at"] is None
    assert link["delivered_by"] is None

    # 이미 assigned 인데 또 되돌리면 False(멱등 판정), 링크가 없으면 둘 다 False.
    assert unmark_delivered(sd) is False
    assert mark_delivered({}, at=_NOW) is False
    assert unmark_delivered({}) is False


# --- 전달 수단 -------------------------------------------------------------


def test_read_method_defaults_to_sales():
    assert read_method({}) == "sales"
    assert read_method(None) == "sales"
    assert read_method({"shipment": {METHOD_KEY: "bogus"}}) == "sales"
    assert read_method({"shipment": {METHOD_KEY: "parcel"}}) == "parcel"


def test_set_method_parcel_clears_link_and_records_parcel_info():
    sd = {}
    _assign(sd)
    set_method(
        sd,
        "parcel",
        parcel={"carrier": "CJ대한통운", "tracking_no": "123456789012"},
        actor_name="홍길동",
        now=_NOW,
    )
    assert read_link(sd) is None
    assert read_method(sd) == "parcel"
    assert sd["shipment"][PARCEL_KEY] == {
        "carrier": "CJ대한통운",
        "tracking_no": "123456789012",
        "sent_at": "2026-09-09T05:30:00",
        "sent_by": "홍길동",
    }


def test_set_method_back_to_sales_drops_parcel_info():
    sd = {}
    set_method(sd, "parcel", parcel={"carrier": "CJ", "tracking_no": "1"}, now=_NOW)
    set_method(sd, "sales")
    assert read_method(sd) == "sales"
    assert PARCEL_KEY not in sd["shipment"]


def test_set_method_rejects_unknown_value():
    with pytest.raises(ValueError):
        set_method({}, "pickup")


# --- 표시 상태 -------------------------------------------------------------


def test_derive_display_state_four_states():
    assert derive_display_state({}) == "unassigned"

    sd = {}
    _assign(sd)
    assert derive_display_state(sd) == "assigned"

    mark_delivered(sd, at=_NOW, by="홍길동")
    assert derive_display_state(sd) == "delivered"

    set_method(sd, "parcel", parcel={"carrier": "CJ"}, now=_NOW)
    assert derive_display_state(sd) == "parcel"


# --- 날짜 정규화 -----------------------------------------------------------


def test_date_normalization_accepts_date_objects_and_datetimes():
    sd = {}
    _assign(sd, ref_date=date(2026, 9, 15))
    assert read_link(sd)["ref_date"] == "2026-09-15"
    assert evaluate_drift(sd, datetime(2026, 9, 15, 14, 30))["state"] == "ok"


def test_date_normalization_accepts_time_suffix_and_loose_separators():
    sd = {}
    _assign(sd, ref_date="2026-09-15 14:30")
    assert read_link(sd)["ref_date"] == "2026-09-15"
    assert evaluate_drift(sd, "2026/9/15")["state"] == "ok"

    ack_link(sd, "2026.09.18 09:00")
    assert read_link(sd)["ack_ref_date"] == "2026-09-18"
    assert evaluate_drift(sd, "2026-09-18")["state"] == "acked"
