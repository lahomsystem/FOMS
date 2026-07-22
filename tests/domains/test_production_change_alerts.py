"""생산 변경 감지·묘비 서비스 계약 (foms/services/production_change_alerts.py).

- 변경 윈도: 생산 진입(erp_stage_updated_at/STAGE_CHANGED) 이후 변경만 감지.
- ack(개인별): 본인 PRODUCTION_CHANGE_ACK 이후로만 내 윈도 리셋(남의 ack 무관).
- 도면: TRANSFER='도면 재전달', REQUEST_REVISION='도면 수정요청' (entry at 파싱).
- 묘비: 최근 14일 취소 주문 포함, 본인이 확인(마커)한 묘비만 내 화면서 제외, 14일 초과 제외.
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
_UID = 7  # 변경 알림 테스트용 임의 사용자 id(User row 불필요, 정수 비교만)


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


def _add_event(
    order_id: int,
    event_type: str,
    payload: dict,
    created_at: datetime.datetime,
    created_by_user_id: int | None = None,
) -> None:
    ev = OrderEvent(
        order_id=order_id,
        event_type=event_type,
        payload=payload,
        created_at=created_at,
        created_by_user_id=created_by_user_id,
    )
    db_session.add(ev)
    db_session.commit()


def _make_user(username: str, *, team: str = "PRODUCTION") -> User:
    u = User(
        username=username,
        password=generate_password_hash("pw"),
        role="STAFF",
        team=team,
        name=username,
        is_active=True,
    )
    db_session.add(u)
    db_session.commit()
    return u


# --- 변경 윈도 계산 (개인별) -------------------------------------------------


def test_window_start_prefers_my_latest_ack(app):
    me = _make_user("win_me")
    other = _make_user("win_other")
    order = _make_order()
    _add_event(order.id, "STAGE_CHANGED", {"from": "MEASURE", "to": "PRODUCTION"}, _T0 + datetime.timedelta(days=1))
    _add_event(order.id, "PRODUCTION_CHANGE_ACK", {"source": "tablet_kanban"}, _T0 + datetime.timedelta(days=5), created_by_user_id=me.id)
    events = db_session.query(OrderEvent).filter(OrderEvent.order_id == order.id).all()
    # 내 ack → 내 윈도는 ack 시각.
    assert compute_window_start(order, events, me.id) == _T0 + datetime.timedelta(days=5)
    # 남(다른 uid)에겐 그 ack 가 안 보여 → 생산 진입(STAGE_CHANGED)로 폴백.
    assert compute_window_start(order, events, other.id) == _T0 + datetime.timedelta(days=1)


def test_window_start_uses_production_entry_stage_change(app):
    order = _make_order(stage_updated_at=None)
    _add_event(order.id, "STAGE_CHANGED", {"from": "MEASURE", "to": "PRODUCTION"}, _T0 + datetime.timedelta(days=2))
    events = db_session.query(OrderEvent).filter(OrderEvent.order_id == order.id).all()
    assert compute_window_start(order, events, _UID) == _T0 + datetime.timedelta(days=2)


def test_window_start_falls_back_to_stage_updated_at(app):
    order = _make_order(stage_updated_at=_T0)
    assert compute_window_start(order, [], _UID) == _T0


# --- 시공일 변경 감지 -------------------------------------------------------


def _cc(order, user_id) -> dict:
    """collect 반환에서 단일 주문의 {'alerts','history'} dict 추출."""
    return collect_production_change_alerts(db_session, [order], user_id)[order.id]


def test_construction_change_after_window_detected(app):
    order = _make_order(stage_updated_at=_T0)
    _add_event(order.id, "CONSTRUCTION_DATE_CHANGED", {"from": "2026-07-20", "to": "2026-07-28"}, _T0 + datetime.timedelta(days=3))
    alerts = _cc(order, _UID)["alerts"]
    assert len(alerts) == 1
    assert alerts[0]["kind"] == "construction_date"
    assert alerts[0]["label"] == "시공일 변경"
    assert alerts[0]["detail"] == "7/20 → 7/28"


def test_construction_change_alert_has_from_md_to_md(app):
    order = _make_order(stage_updated_at=_T0)
    _add_event(order.id, "CONSTRUCTION_DATE_CHANGED", {"from": "2026-07-06", "to": "2026-07-04"}, _T0 + datetime.timedelta(days=3))
    alert = _cc(order, _UID)["alerts"][0]
    # B2: 빨간 일자 렌더용 구조화 키(detail 은 하위호환 유지).
    assert alert["from_md"] == "7/6"
    assert alert["to_md"] == "7/4"
    assert alert["detail"] == "7/6 → 7/4"


def test_no_ack_alerts_equals_history(app):
    order = _make_order(stage_updated_at=_T0)
    _add_event(order.id, "CONSTRUCTION_DATE_CHANGED", {"from": "2026-07-20", "to": "2026-07-28"}, _T0 + datetime.timedelta(days=3))
    cc = _cc(order, _UID)  # 개인 ack 없음 → alerts == history
    assert len(cc["alerts"]) == 1
    assert cc["alerts"] == cc["history"]


def test_construction_change_before_window_ignored(app):
    order = _make_order(stage_updated_at=_T0 + datetime.timedelta(days=10))
    _add_event(order.id, "CONSTRUCTION_DATE_CHANGED", {"from": "2026-07-20", "to": "2026-07-28"}, _T0)
    cc = _cc(order, _UID)  # entry 이전이라 이력에도 안 남는다.
    assert cc["alerts"] == []
    assert cc["history"] == []


def test_my_ack_hides_alert_but_keeps_history(app):
    me = _make_user("reset_me")
    order = _make_order(stage_updated_at=_T0)
    _add_event(order.id, "CONSTRUCTION_DATE_CHANGED", {"from": "2026-07-20", "to": "2026-07-28"}, _T0 + datetime.timedelta(days=2))
    _add_event(order.id, "PRODUCTION_CHANGE_ACK", {"source": "tablet_kanban"}, _T0 + datetime.timedelta(days=4), created_by_user_id=me.id)
    # (a) 내 ack 이후: 미확인 alert 는 사라지되, 상설 이력엔 detail 유지.
    cc = _cc(order, me.id)
    assert cc["alerts"] == []
    assert len(cc["history"]) == 1
    assert cc["history"][0]["detail"] == "7/20 → 7/28"
    # 내 ack 이후 새 변경은 다시 alert + 이력 양쪽.
    _add_event(order.id, "CONSTRUCTION_DATE_CHANGED", {"from": "2026-07-28", "to": "2026-08-02"}, _T0 + datetime.timedelta(days=6))
    cc = _cc(order, me.id)
    assert [a["detail"] for a in cc["alerts"]] == ["7/28 → 8/2"]
    assert len(cc["history"]) == 2


def test_other_users_ack_personalizes_alerts_not_history(app):
    me = _make_user("clr_me")
    other = _make_user("clr_other")
    order = _make_order(stage_updated_at=_T0)
    _add_event(order.id, "CONSTRUCTION_DATE_CHANGED", {"from": "2026-07-20", "to": "2026-07-28"}, _T0 + datetime.timedelta(days=2))
    # 동료가 확인 → 동료만 조용, 나는 여전히 시끄러움. 이력은 둘 다 상설로 남음.
    _add_event(order.id, "PRODUCTION_CHANGE_ACK", {"source": "tablet_kanban"}, _T0 + datetime.timedelta(days=4), created_by_user_id=other.id)
    mine = _cc(order, me.id)
    theirs = _cc(order, other.id)
    assert len(mine["alerts"]) == 1 and len(mine["history"]) == 1     # 나: 시끄러움
    assert theirs["alerts"] == [] and len(theirs["history"]) == 1     # 동료: 조용, 이력은 유지


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
    alerts = _cc(order, _UID)["alerts"]
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
    order = _make_order(sd=sd, stage_updated_at=_T0)
    assert _cc(order, _UID)["alerts"] == []


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


def test_tombstone_excluded_by_my_marker_ack(app):
    me = _make_user("tomb_me")
    today = get_today_kst()
    deleted_at = today.strftime("%Y-%m-%d 12:00:00")
    order = _make_order(stage="생산", status="DELETED", deleted_at=deleted_at)
    # 내가 이 삭제 시점을 확인(마커) → 내 화면서 제외.
    _add_event(order.id, "PRODUCTION_CHANGE_ACK", {"source": "tablet_kanban", "deleted_at": deleted_at}, _T0, created_by_user_id=me.id)
    tombs = collect_production_tombstones(db_session, me, False)
    assert all(t["id"] != order.id for t in tombs)


def test_tombstone_other_user_ack_does_not_dismiss_for_me(app):
    me = _make_user("tomb_me2")
    other = _make_user("tomb_other")
    today = get_today_kst()
    deleted_at = today.strftime("%Y-%m-%d 12:00:00")
    order = _make_order(stage="생산", status="DELETED", deleted_at=deleted_at)
    # 동료가 확인 → 내 화면엔 묘비 유지, 동료 화면엔 제외.
    _add_event(order.id, "PRODUCTION_CHANGE_ACK", {"source": "tablet_kanban", "deleted_at": deleted_at}, _T0, created_by_user_id=other.id)
    assert any(t["id"] == order.id for t in collect_production_tombstones(db_session, me, False))
    assert all(t["id"] != order.id for t in collect_production_tombstones(db_session, other, False))


def test_tombstone_not_dismissed_by_pre_deletion_ack(app):
    me = _make_user("tomb_me3")
    today = get_today_kst()
    deleted_at = today.strftime("%Y-%m-%d 12:00:00")
    order = _make_order(stage="생산", status="DELETED", deleted_at=deleted_at)
    # 삭제 전 ack(마커 없음)는 시계상 아무리 '미래'여도 묘비를 못 지운다.
    _add_event(order.id, "PRODUCTION_CHANGE_ACK", {"source": "tablet_kanban"}, datetime.datetime(2030, 1, 1), created_by_user_id=me.id)
    assert any(t["id"] == order.id for t in collect_production_tombstones(db_session, me, False))


def test_tombstone_dismissed_by_marker_despite_clock_skew(app):
    me = _make_user("tomb_me4")
    today = get_today_kst()
    deleted_dt = datetime.datetime.combine(today, datetime.time(12, 0, 0))
    deleted_at = deleted_dt.strftime("%Y-%m-%d %H:%M:%S")
    order = _make_order(stage="생산", status="DELETED", deleted_at=deleted_at)
    # ack created_at 이 deleted_at(KST)보다 9h '과거'로 보여도 마커가 있으면 제거(시계 비교 없음).
    _add_event(order.id, "PRODUCTION_CHANGE_ACK", {"source": "tablet_kanban", "deleted_at": deleted_at}, deleted_dt - datetime.timedelta(hours=9), created_by_user_id=me.id)
    tombs = collect_production_tombstones(db_session, me, False)
    assert all(t["id"] != order.id for t in tombs)


def test_tombstone_excluded_when_older_than_14_days(app):
    old = get_today_kst() - datetime.timedelta(days=20)
    order = _make_order(stage="시공", status="DELETED", deleted_at=old.strftime("%Y-%m-%d 12:00:00"))
    tombs = collect_production_tombstones(db_session, None, False)
    assert all(t["id"] != order.id for t in tombs)


def test_tombstone_mine_filter_excludes_unrelated(app):
    user = _make_user("tomb_sales", team="SALES")
    today = get_today_kst()
    # 담당자가 다른 주문 → mine 필터에서 제외
    order = _make_order(stage="생산", status="DELETED", deleted_at=today.strftime("%Y-%m-%d 12:00:00"))
    tombs = collect_production_tombstones(db_session, user, True)
    assert all(t["id"] != order.id for t in tombs)
