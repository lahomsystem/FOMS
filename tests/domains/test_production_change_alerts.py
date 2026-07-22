"""생산 변경 감지·묘비 서비스 계약 (foms/services/production_change_alerts.py).

- 변경 윈도: 생산 진입(erp_stage_updated_at/STAGE_CHANGED) 이후 변경만 감지.
- ack: PRODUCTION_CHANGE_ACK 이후로 윈도 리셋(이전 변경 해제).
- 도면: TRANSFER='도면 재전달', REQUEST_REVISION='도면 수정요청' (entry at 파싱).
- 묘비: 최근 14일 취소 주문 포함, 삭제 후 ack 있으면 제외, 14일 초과 제외.
"""

from __future__ import annotations

import datetime

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, User
from foms.services.datetime_kst import get_today_kst
from foms.services.production_change_alerts import (
    collect_production_change_alerts,
    collect_production_tombstones,
    compute_window_start,
)

_T0 = datetime.datetime(2026, 7, 1, 0, 0, 0)


def _make_order(
    *,
    stage: str = "PRODUCTION",
    status: str = "PRODUCTION",
    sd: dict | None = None,
    stage_updated_at: datetime.datetime | None = _T0,
    deleted_at: str | None = None,
    construction_date: str | None = None,
) -> Order:
    order = Order(
        received_date="2026-07-01",
        customer_name="변경 고객",
        phone="010-1111-2222",
        address="Seoul",
        product="붙박이장",
        status=status,
        manager_name="담당",
        is_erp_order=True,
        structured_data=sd if sd is not None else {"workflow": {"stage": stage}},
        erp_stage_code=stage,
        erp_stage_updated_at=stage_updated_at,
        erp_construction_date=construction_date,
        deleted_at=deleted_at,
    )
    db_session.add(order)
    db_session.commit()
    return order


def _add_event(order_id: int, event_type: str, payload: dict, created_at: datetime.datetime) -> None:
    ev = OrderEvent(
        order_id=order_id,
        event_type=event_type,
        payload=payload,
        created_at=created_at,
    )
    db_session.add(ev)
    db_session.commit()


# --- 변경 윈도 계산 ---------------------------------------------------------


def test_window_start_prefers_latest_ack(app):
    order = _make_order()
    _add_event(order.id, "STAGE_CHANGED", {"from": "MEASURE", "to": "PRODUCTION"}, _T0 + datetime.timedelta(days=1))
    _add_event(order.id, "PRODUCTION_CHANGE_ACK", {"source": "tablet_kanban"}, _T0 + datetime.timedelta(days=5))
    events = db_session.query(OrderEvent).filter(OrderEvent.order_id == order.id).all()
    assert compute_window_start(order, events) == _T0 + datetime.timedelta(days=5)


def test_window_start_uses_production_entry_stage_change(app):
    order = _make_order(stage_updated_at=None)
    # from ∉ PROD, to ∈ PROD → 생산 진입
    _add_event(order.id, "STAGE_CHANGED", {"from": "MEASURE", "to": "PRODUCTION"}, _T0 + datetime.timedelta(days=2))
    events = db_session.query(OrderEvent).filter(OrderEvent.order_id == order.id).all()
    assert compute_window_start(order, events) == _T0 + datetime.timedelta(days=2)


def test_window_start_falls_back_to_stage_updated_at(app):
    order = _make_order(stage_updated_at=_T0)
    events: list[OrderEvent] = []
    assert compute_window_start(order, events) == _T0


# --- 시공일 변경 감지 -------------------------------------------------------


def test_construction_change_after_window_detected(app):
    order = _make_order(stage_updated_at=_T0)
    _add_event(
        order.id,
        "CONSTRUCTION_DATE_CHANGED",
        {"from": "2026-07-20", "to": "2026-07-28"},
        _T0 + datetime.timedelta(days=3),
    )
    result = collect_production_change_alerts(db_session, [order])
    alerts = result[order.id]
    assert len(alerts) == 1
    assert alerts[0]["kind"] == "construction_date"
    assert alerts[0]["label"] == "시공일 변경"
    assert alerts[0]["detail"] == "7/20 → 7/28"


def test_construction_change_alert_has_from_md_to_md(app):
    order = _make_order(stage_updated_at=_T0)
    _add_event(
        order.id,
        "CONSTRUCTION_DATE_CHANGED",
        {"from": "2026-07-06", "to": "2026-07-04"},
        _T0 + datetime.timedelta(days=3),
    )
    alert = collect_production_change_alerts(db_session, [order])[order.id][0]
    # B2: 빨간 일자 렌더용 구조화 키(detail 은 하위호환 유지).
    assert alert["from_md"] == "7/6"
    assert alert["to_md"] == "7/4"
    assert alert["detail"] == "7/6 → 7/4"


def test_construction_change_before_window_ignored(app):
    order = _make_order(stage_updated_at=_T0 + datetime.timedelta(days=10))
    _add_event(
        order.id,
        "CONSTRUCTION_DATE_CHANGED",
        {"from": "2026-07-20", "to": "2026-07-28"},
        _T0,  # 윈도 이전
    )
    result = collect_production_change_alerts(db_session, [order])
    assert result[order.id] == []


def test_ack_resets_window(app):
    order = _make_order(stage_updated_at=_T0)
    _add_event(order.id, "CONSTRUCTION_DATE_CHANGED", {"from": "2026-07-20", "to": "2026-07-28"}, _T0 + datetime.timedelta(days=2))
    _add_event(order.id, "PRODUCTION_CHANGE_ACK", {"source": "tablet_kanban"}, _T0 + datetime.timedelta(days=4))
    # ack 이후엔 이전 변경이 해제됨
    assert collect_production_change_alerts(db_session, [order])[order.id] == []
    # ack 이후 새 변경은 다시 감지
    _add_event(order.id, "CONSTRUCTION_DATE_CHANGED", {"from": "2026-07-28", "to": "2026-08-02"}, _T0 + datetime.timedelta(days=6))
    alerts = collect_production_change_alerts(db_session, [order])[order.id]
    assert len(alerts) == 1
    assert alerts[0]["detail"] == "7/28 → 8/2"


# --- 도면 이력 감지 ---------------------------------------------------------


def test_drawing_transfer_and_revision_detected(app):
    sd = {
        "workflow": {"stage": "PRODUCTION"},
        "drawing_transfer_history": [
            {"action": "TRANSFER", "transferred_at": "2026-07-05 09:00:00", "note": "1차 전달"},
            {"action": "REQUEST_REVISION", "at": "2026-07-06 10:00:00", "note": "치수 오류"},
        ],
    }
    order = _make_order(sd=sd, stage_updated_at=_T0)
    alerts = collect_production_change_alerts(db_session, [order])[order.id]
    labels = {a["label"] for a in alerts}
    assert labels == {"도면 재전달", "도면 수정요청"}
    assert all(a["kind"] == "drawing" for a in alerts)


def test_drawing_before_window_ignored(app):
    sd = {
        "workflow": {"stage": "PRODUCTION"},
        "drawing_transfer_history": [
            {"action": "TRANSFER", "transferred_at": "2026-06-20 09:00:00", "note": "초기 전달"},
        ],
    }
    order = _make_order(sd=sd, stage_updated_at=_T0)  # 2026-07-01 이후만 감지
    assert collect_production_change_alerts(db_session, [order])[order.id] == []


# --- 묘비 ------------------------------------------------------------------


def test_tombstone_included(app):
    today = get_today_kst()
    deleted_at = today.strftime("%Y-%m-%d 12:00:00")
    sd = {"workflow": {"stage": "생산"}, "parties": {"customer": {"name": "홍길동"}}, "items": [{"product_name": "장롱"}]}
    order = _make_order(stage="생산", status="DELETED", sd=sd, deleted_at=deleted_at)
    tombs = collect_production_tombstones(db_session, None, False)
    match = [t for t in tombs if t["id"] == order.id]
    assert len(match) == 1
    t = match[0]
    assert t["customer_name"] == "홍길동"
    assert t["bucket"] == "제작중"
    assert t["product_label"] == "장롱"
    assert t["deleted_md"] == f"{today.month}/{today.day}"


def test_tombstone_excluded_by_marker_ack(app):
    today = get_today_kst()
    deleted_at = today.strftime("%Y-%m-%d 12:00:00")
    order = _make_order(stage="생산", status="DELETED", deleted_at=deleted_at)
    # 묘비 확인 ack: payload에 deleted_at 마커(=str(order.deleted_at)) → 제외.
    _add_event(
        order.id,
        "PRODUCTION_CHANGE_ACK",
        {"source": "tablet_kanban", "deleted_at": deleted_at},
        _T0,
    )
    tombs = collect_production_tombstones(db_session, None, False)
    assert all(t["id"] != order.id for t in tombs)


def test_tombstone_not_dismissed_by_pre_deletion_ack(app):
    today = get_today_kst()
    deleted_at = today.strftime("%Y-%m-%d 12:00:00")
    order = _make_order(stage="생산", status="DELETED", deleted_at=deleted_at)
    # 삭제 전 라이브 카드에서 눌린 ack(마커 없음)는 시계상 아무리 '미래'여도 묘비를 못 지운다.
    _add_event(order.id, "PRODUCTION_CHANGE_ACK", {"source": "tablet_kanban"}, datetime.datetime(2030, 1, 1))
    tombs = collect_production_tombstones(db_session, None, False)
    assert any(t["id"] == order.id for t in tombs)


def test_tombstone_dismissed_by_marker_despite_clock_skew(app):
    today = get_today_kst()
    deleted_dt = datetime.datetime.combine(today, datetime.time(12, 0, 0))
    deleted_at = deleted_dt.strftime("%Y-%m-%d %H:%M:%S")
    order = _make_order(stage="생산", status="DELETED", deleted_at=deleted_at)
    # 운영 UTC 서버 시뮬: ack created_at 이 deleted_at(KST)보다 9h '과거'로 보여도,
    # 마커가 있으면 묘비는 제거된다(시계 비교 제거 검증 — 구 버그의 회귀 가드).
    _add_event(
        order.id,
        "PRODUCTION_CHANGE_ACK",
        {"source": "tablet_kanban", "deleted_at": deleted_at},
        deleted_dt - datetime.timedelta(hours=9),
    )
    tombs = collect_production_tombstones(db_session, None, False)
    assert all(t["id"] != order.id for t in tombs)


def test_tombstone_excluded_when_older_than_14_days(app):
    old = get_today_kst() - datetime.timedelta(days=20)
    order = _make_order(stage="시공", status="DELETED", deleted_at=old.strftime("%Y-%m-%d 12:00:00"))
    tombs = collect_production_tombstones(db_session, None, False)
    assert all(t["id"] != order.id for t in tombs)


def test_tombstone_mine_filter_excludes_unrelated(app):
    user = User(
        username="tomb_sales",
        password=generate_password_hash("pw"),
        role="STAFF",
        team="SALES",
        name="영업원",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    today = get_today_kst()
    # 담당자가 다른 주문 → mine 필터에서 제외
    order = _make_order(stage="생산", status="DELETED", deleted_at=today.strftime("%Y-%m-%d 12:00:00"))
    tombs = collect_production_tombstones(db_session, user, True)
    assert all(t["id"] != order.id for t in tombs)
