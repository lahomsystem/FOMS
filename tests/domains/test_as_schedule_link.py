"""AS 일정 매칭 링크 + 드리프트 판정(as_schedule_link) 순수 서비스 테스트.

스펙: docs/specs/2026-07-30-as-schedule-link-drift-design.md (§3, §4).
DB/Flask 불필요 — dict fixture 만으로 검증한다.
"""
from datetime import datetime

from foms.services.orders.as_schedule_link import (
    LINK_PATH,
    SOURCE_NEARBY,
    SOURCE_SHIPMENT,
    ack_link,
    clear_link,
    evaluate_drift,
    read_link,
    relink,
    write_link,
)

_NOW = datetime(2026, 7, 30, 2, 11, 0)


def test_read_link_missing_returns_none():
    assert read_link({}) is None
    assert read_link({"schedule": {}}) is None
    assert read_link({"schedule": {"as_visit": {}}}) is None


def test_write_link_creates_nested_path_with_exact_shape():
    sd = {}
    link = write_link(
        sd,
        ref_order_id=3694,
        ref_date="2026-08-05",
        source=SOURCE_NEARBY,
        user_id=12,
        user_name="홍길동",
        now=_NOW,
    )
    assert link == {
        "ref_order_id": 3694,
        "ref_kind": "construction",
        "ref_date": "2026-08-05",
        "linked_at": "2026-07-30T02:11:00",
        "linked_by_user_id": 12,
        "linked_by": "홍길동",
        "source": SOURCE_NEARBY,
        "ack_ref_date": None,
    }
    # LINK_PATH 그대로 중첩되어 저장되었는지 확인.
    node = sd
    for key in LINK_PATH[:-1]:
        node = node[key]
    assert node[LINK_PATH[-1]] == link
    assert read_link(sd) == link


def test_write_link_overwrite_resets_ack():
    sd = {}
    write_link(sd, ref_order_id=1, ref_date="2026-08-05", source=SOURCE_NEARBY,
               user_id=1, user_name="A", now=_NOW)
    assert ack_link(sd, "2026-08-12") is True
    assert read_link(sd)["ack_ref_date"] == "2026-08-12"

    write_link(sd, ref_order_id=2, ref_date="2026-08-20", source=SOURCE_SHIPMENT,
               user_id=2, user_name="B", now=_NOW)
    link = read_link(sd)
    assert link["ref_order_id"] == 2
    assert link["ack_ref_date"] is None


def test_clear_link_missing_returns_false():
    assert clear_link({}) is False
    sd = {"schedule": {"as_visit": {"date": "2026-08-05"}}}
    assert clear_link(sd) is False


def test_clear_link_removes_key():
    sd = {}
    write_link(sd, ref_order_id=1, ref_date="2026-08-05", source=SOURCE_NEARBY,
               user_id=1, user_name="A", now=_NOW)
    assert clear_link(sd) is True
    assert read_link(sd) is None
    assert clear_link(sd) is False


def test_ack_and_relink_no_link_return_false():
    assert ack_link({}, "2026-08-05") is False
    assert relink({}, "2026-08-05") is False


def test_relink_updates_ref_date_and_clears_ack():
    sd = {}
    write_link(sd, ref_order_id=1, ref_date="2026-08-05", source=SOURCE_NEARBY,
               user_id=1, user_name="A", now=_NOW)
    ack_link(sd, "2026-08-12")
    assert relink(sd, "2026-08-12") is True
    link = read_link(sd)
    assert link["ref_date"] == "2026-08-12"
    assert link["ack_ref_date"] is None


def test_drift_none_when_no_link():
    result = evaluate_drift(None, ref_current_date="2026-08-05", as_visit_date="2026-08-05",
                             ref_missing=False)
    assert result["state"] == "none"
    assert result["ref_order_id"] is None
    assert result["ref_date"] is None


def test_drift_ok_when_ref_unchanged():
    link = {"ref_order_id": 1, "ref_date": "2026-08-05"}
    result = evaluate_drift(link, ref_current_date="2026-08-05", as_visit_date="2026-08-05",
                             ref_missing=False)
    assert result["state"] == "ok"


def test_drift_ref_moved_main_case():
    """Ds != D0, Da == D0(AS 는 옛 기준일에 그대로 남음) → ref_moved."""
    link = {"ref_order_id": 1, "ref_date": "2026-08-05"}
    result = evaluate_drift(link, ref_current_date="2026-08-12", as_visit_date="2026-08-05",
                             ref_missing=False)
    assert result["state"] == "ref_moved"
    assert result["ref_date"] == "2026-08-05"
    assert result["ref_current_date"] == "2026-08-12"


def test_drift_both_moved():
    """Ds != D0, Da != D0, Da != Ds → both_moved."""
    link = {"ref_order_id": 1, "ref_date": "2026-08-05"}
    result = evaluate_drift(link, ref_current_date="2026-08-12", as_visit_date="2026-08-15",
                             ref_missing=False)
    assert result["state"] == "both_moved"


def test_drift_resolved_when_user_already_matched_new_date():
    """Ds != D0, Da == Ds(사람이 이미 새 기준일에 맞춰 놓음) → resolved."""
    link = {"ref_order_id": 1, "ref_date": "2026-08-05"}
    result = evaluate_drift(link, ref_current_date="2026-08-12", as_visit_date="2026-08-12",
                             ref_missing=False)
    assert result["state"] == "resolved"


def test_drift_acked_suppresses_warning():
    """ack_ref_date == 현재 Ds 면 Da 가 옛 기준일 그대로여도 acked 로 억제."""
    link = {"ref_order_id": 1, "ref_date": "2026-08-05", "ack_ref_date": "2026-08-12"}
    result = evaluate_drift(link, ref_current_date="2026-08-12", as_visit_date="2026-08-05",
                             ref_missing=False)
    assert result["state"] == "acked"


def test_drift_ack_stale_after_ref_moves_again_returns_ref_moved():
    """ack 이후 기준일이 또 바뀌면(ack_ref_date != 새 Ds) acked 가 아니라 ref_moved."""
    link = {"ref_order_id": 1, "ref_date": "2026-08-05", "ack_ref_date": "2026-08-12"}
    result = evaluate_drift(link, ref_current_date="2026-08-20", as_visit_date="2026-08-05",
                             ref_missing=False)
    assert result["state"] == "ref_moved"


def test_drift_ref_gone_takes_precedence():
    """기준 주문 삭제/조회불가는 날짜 상태와 무관하게 항상 ref_gone."""
    link = {"ref_order_id": 1, "ref_date": "2026-08-05", "ack_ref_date": "2026-08-05"}
    result = evaluate_drift(link, ref_current_date="2026-08-05", as_visit_date="2026-08-05",
                             ref_missing=True)
    assert result["state"] == "ref_gone"


def test_drift_date_format_normalization():
    """'2026-8-5' 와 '2026-08-05' 는 동일 날짜로 비교되어야 한다."""
    link = {"ref_order_id": 1, "ref_date": "2026-08-05"}
    result = evaluate_drift(link, ref_current_date="2026-8-5", as_visit_date="2026-8-5",
                             ref_missing=False)
    assert result["state"] == "ok"
    assert result["ref_current_date"] == "2026-08-05"
    assert result["as_visit_date"] == "2026-08-05"
