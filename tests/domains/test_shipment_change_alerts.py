"""출고 시공일 변경 수집 서비스 계약 (foms/services/shipment_change_alerts.py — T2).

여기서 고정하는 계약:

* **개인 윈도**: 본인 최근 ``SHIPMENT_CHANGE_ACK`` 이후의 ``CONSTRUCTION_DATE_CHANGED`` 만
  ``alerts``. 동료 ack 는 내 화면에 무영향. ``history`` 는 ack 무관 전체 이력.
* **시간 상한 없음**: 생산 선례의 entry 윈도·14일 컷오프를 답습하지 않는다 — 2년 전 변경도
  확인 전이면 계속 alert 다(사용자 결정).
* **다중값 표기**: 콤마 연결 시공일은 ``"7/20, 7/22"``, 3개 초과는 ``"... 외 N"``.
* **최초 지정 제외**: ``from`` 이 비었거나 못 읽으면(표시상 ``미정``) alert/history/배너
  모두 제외. ``8/20 → 8/22`` 만 알림. 지정일을 지우는 ``8/14 → 미정`` 은 변경이므로 포함.
* **손상 payload 내성**: dict 아님 / 키 없음 / 정규화 안 된 ``2026/07/20`` / 숫자·리스트에도
  예외 없이 degrade.
* **배너**: ``{count, chips, overflow}`` (AS 배너와 동일 계약), 칩 상한 5.
* **쿼리 1회**: 주문 수와 무관하게 배치 1쿼리(N+1 가드).
"""

from __future__ import annotations

import datetime

from sqlalchemy import event
from werkzeug.security import generate_password_hash

from db import db_session, engine
from foms.services.shipment_change_alerts import (
    build_shipment_change_banner,
    collect_shipment_change_alerts,
    compute_shipment_ack_window,
)
from models import Order, OrderEvent, User

_T0 = datetime.datetime(2026, 7, 1, 0, 0, 0)
_UID = 4242  # User row 불필요(정수 비교만) — 개인 ack 가 없는 사용자 대역.
_CHANGE = "CONSTRUCTION_DATE_CHANGED"
_ACK = "SHIPMENT_CHANGE_ACK"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _make_user(username: str, *, team: str = "SHIPMENT") -> User:
    """테스트 사용자 1명 생성(커밋 포함)."""
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role="STAFF",
        team=team,
        name=username,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _make_order(customer_name: str = "출고 고객") -> Order:
    """출고 대상 주문 1건 생성(커밋 포함)."""
    order = Order(
        received_date="2026-07-01",
        customer_name=customer_name,
        phone="010-3333-4444",
        address="서울 출고로 1",
        product="붙박이장",
        status="IN_CONSTRUCTION",
        manager_name="담당",
        is_erp_order=True,
        structured_data={
            "workflow": {"stage": "SHIPMENT"},
            "parties": {"customer": {"name": customer_name}},
            "schedule": {"construction": {"date": "2026-07-20"}},
        },
        erp_stage_code="SHIPMENT",
    )
    db_session.add(order)
    db_session.commit()
    return order


def _add_event(
    order_id: int,
    event_type: str,
    payload,
    created_at: datetime.datetime,
    created_by_user_id: int | None = None,
) -> None:
    """OrderEvent 1건 삽입(커밋 포함). payload 는 dict 가 아니어도 허용(내성 테스트용)."""
    db_session.add(
        OrderEvent(
            order_id=order_id,
            event_type=event_type,
            payload=payload,
            created_at=created_at,
            created_by_user_id=created_by_user_id,
        )
    )
    db_session.commit()


def _change(order_id: int, from_: str, to: str, days: int) -> None:
    """시공일 변경 이벤트 1건(정상 payload)."""
    _add_event(
        order_id, _CHANGE, {"from": from_, "to": to, "source": "erp.api_put_structured"},
        _T0 + datetime.timedelta(days=days),
    )


def _cc(order: Order, user_id: int | None) -> dict:
    """collect 반환에서 단일 주문의 ``{'alerts','history'}`` 추출."""
    return collect_shipment_change_alerts(db_session, [order], user_id)[order.id]


def _count_queries(fn):
    """fn 실행 중 발생한 SQL 실행 횟수를 센다(N+1 가드 — 기존 큐 테스트와 동일 패턴)."""
    counter = {"n": 0}

    def _before(conn, cursor, statement, params, context, executemany):
        counter["n"] += 1

    event.listen(engine, "before_cursor_execute", _before)
    try:
        result = fn()
    finally:
        event.remove(engine, "before_cursor_execute", _before)
    return result, counter["n"]


# --------------------------------------------------------------------------- #
# 1. 개인 윈도 (ack 전/후)
# --------------------------------------------------------------------------- #
def test_change_without_any_ack_is_alert(app):
    """확인한 적이 없으면 변경은 alert 이자 history 다."""
    order = _make_order()
    _change(order.id, "2026-07-20", "2026-07-28", days=3)

    cc = _cc(order, _UID)
    assert len(cc["alerts"]) == 1
    assert cc["alerts"][0]["kind"] == "construction_date"
    assert cc["alerts"][0]["label"] == "시공일 변경"
    assert cc["alerts"][0]["from_md"] == "7/20"
    assert cc["alerts"][0]["to_md"] == "7/28"
    assert cc["alerts"] == cc["history"]


def test_my_ack_clears_alert_but_keeps_history(app):
    """내 ack 이전 변경은 alert 에서 빠지고 history 에는 남는다."""
    me = _make_user("ship_ack_me")
    order = _make_order()
    _change(order.id, "2026-07-20", "2026-07-28", days=2)
    _add_event(order.id, _ACK, {"source": "shipment_dashboard"},
               _T0 + datetime.timedelta(days=4), created_by_user_id=me.id)

    cc = _cc(order, me.id)
    assert cc["alerts"] == []
    assert [h["detail"] for h in cc["history"]] == ["7/20 → 7/28"]


def test_change_after_my_ack_is_alert_again(app):
    """ack 이후 새 변경은 다시 alert(윈도가 최신 ack 기준)."""
    me = _make_user("ship_ack_after")
    order = _make_order()
    _change(order.id, "2026-07-20", "2026-07-28", days=2)
    _add_event(order.id, _ACK, {"source": "shipment_dashboard"},
               _T0 + datetime.timedelta(days=4), created_by_user_id=me.id)
    _change(order.id, "2026-07-28", "2026-08-02", days=6)

    cc = _cc(order, me.id)
    assert [a["detail"] for a in cc["alerts"]] == ["7/28 → 8/2"]
    assert len(cc["history"]) == 2


def test_other_users_ack_does_not_clear_mine(app):
    """동료가 확인해도 내 alert 는 그대로다(개인별 ack)."""
    me = _make_user("ship_me")
    other = _make_user("ship_other")
    order = _make_order()
    _change(order.id, "2026-07-20", "2026-07-28", days=2)
    _add_event(order.id, _ACK, {"source": "shipment_dashboard"},
               _T0 + datetime.timedelta(days=4), created_by_user_id=other.id)

    assert len(_cc(order, me.id)["alerts"]) == 1
    assert _cc(order, other.id)["alerts"] == []
    assert len(_cc(order, other.id)["history"]) == 1


def test_ack_window_is_latest_ack_only(app):
    """윈도 = 본인 최근 ack. 남의 ack·다른 event_type 은 윈도를 만들지 않는다."""
    me = _make_user("ship_window_me")
    other = _make_user("ship_window_other")
    order = _make_order()
    _add_event(order.id, _ACK, {}, _T0 + datetime.timedelta(days=1), created_by_user_id=me.id)
    _add_event(order.id, _ACK, {}, _T0 + datetime.timedelta(days=5), created_by_user_id=me.id)
    _add_event(order.id, _ACK, {}, _T0 + datetime.timedelta(days=9), created_by_user_id=other.id)
    events = db_session.query(OrderEvent).filter(OrderEvent.order_id == order.id).all()

    assert compute_shipment_ack_window(events, me.id) == _T0 + datetime.timedelta(days=5)
    assert compute_shipment_ack_window(events, other.id) == _T0 + datetime.timedelta(days=9)
    # 확인 이력이 없는 사용자·익명은 폴백 윈도 없이 None(= 전부 미확인).
    assert compute_shipment_ack_window(events, _UID) is None
    assert compute_shipment_ack_window(events, None) is None


def test_old_unacked_change_has_no_time_cap(app):
    """2년 전 변경도 확인 전이면 계속 alert 다(생산의 14일 컷오프 미답습)."""
    order = _make_order()
    _add_event(order.id, _CHANGE, {"from": "2024-05-01", "to": "2024-05-09"},
               datetime.datetime(2024, 5, 1, 9, 0, 0))

    assert len(_cc(order, _UID)["alerts"]) == 1


# --------------------------------------------------------------------------- #
# 2. 한 주문에 변경 여러 건
# --------------------------------------------------------------------------- #
def test_multiple_changes_are_ordered_by_time(app):
    """한 주문의 변경 다건은 시간 오름차순으로 alerts·history 양쪽에 담긴다."""
    order = _make_order()
    _change(order.id, "2026-07-28", "2026-08-02", days=6)  # 나중 것을 먼저 삽입
    _change(order.id, "2026-07-20", "2026-07-28", days=2)

    cc = _cc(order, _UID)
    assert [a["detail"] for a in cc["alerts"]] == ["7/20 → 7/28", "7/28 → 8/2"]
    assert cc["alerts"] == cc["history"]


# --------------------------------------------------------------------------- #
# 3. 다중값 날짜 표기
# --------------------------------------------------------------------------- #
def test_multi_value_dates_render_readably(app):
    """콤마 연결 다중 시공일은 ``"7/20, 7/22"`` 로 읽히게 편다."""
    order = _make_order()
    _change(order.id, "2026-07-20,2026-07-22", "2026-07-20,2026-07-29", days=3)

    alert = _cc(order, _UID)["alerts"][0]
    assert alert["from_md"] == "7/20, 7/22"
    assert alert["to_md"] == "7/20, 7/29"


def test_multi_value_dates_over_cap_are_truncated(app):
    """3개를 넘는 다중값은 앞 3개 + ``외 N`` 으로 줄인다(배지 길이 방어)."""
    order = _make_order()
    _change(
        order.id,
        "2026-07-20,2026-07-22,2026-07-25,2026-07-27,2026-07-30",
        "2026-08-01",
        days=3,
    )

    alert = _cc(order, _UID)["alerts"][0]
    assert alert["from_md"] == "7/20, 7/22, 7/25 외 2"
    assert alert["to_md"] == "8/1"


# --------------------------------------------------------------------------- #
# 4. 손상·레거시 payload 내성 (절대 raise 금지)
# --------------------------------------------------------------------------- #
def test_legacy_unnormalized_payload_still_renders(app):
    """T1 이전 raw 표기(``2026/07/20``)와 source 누락에도 표시가 살아난다."""
    order = _make_order()
    _add_event(order.id, _CHANGE, {"from": "2026/07/20", "to": "2026.07.28"},
               _T0 + datetime.timedelta(days=2))

    alert = _cc(order, _UID)["alerts"][0]
    assert (alert["from_md"], alert["to_md"]) == ("7/20", "7/28")


def test_malformed_payloads_are_tolerated(app):
    """dict 아님 / 키 없음 / 숫자 / 파싱 불가 문자열이 섞여도 예외 없이 살릴 것만 살린다."""
    order = _make_order()
    _add_event(order.id, _CHANGE, None, _T0 + datetime.timedelta(days=1))
    _add_event(order.id, _CHANGE, "완전히 깨진 payload", _T0 + datetime.timedelta(days=2))
    _add_event(order.id, _CHANGE, {}, _T0 + datetime.timedelta(days=3))
    _add_event(order.id, _CHANGE, {"from": "내일", "to": "모레"}, _T0 + datetime.timedelta(days=4))
    _add_event(order.id, _CHANGE, {"from": "", "to": "2026-08-05"}, _T0 + datetime.timedelta(days=5))
    _add_event(order.id, _CHANGE, {"from": ["2026-08-05"], "to": ["2026-08-09", "bad"]},
               _T0 + datetime.timedelta(days=6))

    cc = _cc(order, _UID)  # 정보가 0인 건·최초 지정(from 공란)은 제외, 날짜→날짜만 남긴다.
    assert [(a["from_md"], a["to_md"]) for a in cc["alerts"]] == [
        ("8/5", "8/9"),
    ]


def test_unrelated_event_types_are_ignored(app):
    """다른 event_type(예: PRODUCTION_CHANGE_ACK)은 윈도·표시 어디에도 영향 없다."""
    me = _make_user("ship_unrelated")
    order = _make_order()
    _change(order.id, "2026-07-20", "2026-07-28", days=2)
    _add_event(order.id, "PRODUCTION_CHANGE_ACK", {"source": "tablet_kanban"},
               _T0 + datetime.timedelta(days=4), created_by_user_id=me.id)

    assert len(_cc(order, me.id)["alerts"]) == 1


# --------------------------------------------------------------------------- #
# 5. 배너 요약 (칩 상한 + overflow)
# --------------------------------------------------------------------------- #
def test_banner_chip_has_customer_and_span(app):
    """칩은 고객명·#id·(최초 from → 최신 to)·건수를 담는다."""
    order = _make_order("김출고")
    _change(order.id, "2026-07-20", "2026-07-28", days=2)
    _change(order.id, "2026-07-28", "2026-08-02", days=3)

    banner = build_shipment_change_banner(
        [order], collect_shipment_change_alerts(db_session, [order], _UID)
    )
    assert banner["count"] == 1
    assert banner["overflow"] == 0
    assert banner["chips"][0] == {
        "order_id": order.id,
        "customer_name": "김출고",
        "from_md": "7/20",   # 최초 변경의 출발
        "to_md": "8/2",      # 최신 변경의 도착
        "count": 2,
    }


def test_banner_chip_cap_and_overflow(app):
    """대상 주문 7건 → count 7, chips 5, overflow 2 (AS 배너와 동일 계약)."""
    orders = []
    for i in range(7):
        o = _make_order(f"배너고객{i}")
        _change(o.id, "2026-07-20", "2026-07-28", days=2)
        orders.append(o)

    banner = build_shipment_change_banner(
        orders, collect_shipment_change_alerts(db_session, orders, _UID)
    )
    assert banner["count"] == 7
    assert len(banner["chips"]) == 5
    assert banner["overflow"] == 2


def test_first_date_assignment_is_not_an_alert(app):
    """미정 → 날짜 지정은 정상 최초 배정이라 배지·배너에 올리지 않는다."""
    order = _make_order()
    _change(order.id, "", "2026-08-14", days=1)
    _add_event(
        order.id, _CHANGE, {"to": "2026-08-20"},
        _T0 + datetime.timedelta(days=2),
    )

    cc = _cc(order, _UID)
    assert cc["alerts"] == []
    assert cc["history"] == []

    banner = build_shipment_change_banner(
        [order], collect_shipment_change_alerts(db_session, [order], _UID)
    )
    assert banner["count"] == 0
    assert banner["chips"] == []


def test_assigned_date_change_is_an_alert(app):
    """이미 지정된 시공일이 다른 날짜로 바뀌면 알림이다."""
    order = _make_order()
    _change(order.id, "2026-08-20", "2026-08-22", days=1)

    cc = _cc(order, _UID)
    assert [(a["from_md"], a["to_md"]) for a in cc["alerts"]] == [("8/20", "8/22")]


def test_clearing_assigned_date_is_an_alert(app):
    """지정된 시공일을 지우는 것(날짜 → 미정)은 변경이므로 알림이다."""
    order = _make_order()
    _change(order.id, "2026-08-14", "", days=1)

    cc = _cc(order, _UID)
    assert [(a["from_md"], a["to_md"]) for a in cc["alerts"]] == [("8/14", "미정")]


def test_banner_skips_acked_and_clean_orders(app):
    """확인한 주문·변경 없는 주문은 배너 대상이 아니다."""
    me = _make_user("ship_banner_me")
    acked = _make_order("확인함")
    clean = _make_order("변경없음")
    noisy = _make_order("미확인")
    _change(acked.id, "2026-07-20", "2026-07-28", days=2)
    _add_event(acked.id, _ACK, {"source": "shipment_dashboard"},
               _T0 + datetime.timedelta(days=3), created_by_user_id=me.id)
    _change(noisy.id, "2026-07-20", "2026-07-28", days=2)

    orders = [acked, clean, noisy]
    banner = build_shipment_change_banner(
        orders, collect_shipment_change_alerts(db_session, orders, me.id)
    )
    assert banner["count"] == 1
    assert [c["order_id"] for c in banner["chips"]] == [noisy.id]


# --------------------------------------------------------------------------- #
# 6. 쿼리 1회 (N+1 가드)
# --------------------------------------------------------------------------- #
def test_collect_issues_exactly_one_query(app):
    """주문 8건 + 이벤트 다수여도 배치 1쿼리(추가 쿼리 0). 배너 파생은 쿼리 0."""
    orders = []
    for i in range(8):
        o = _make_order(f"쿼리고객{i}")
        _change(o.id, "2026-07-20", "2026-07-28", days=2)
        _change(o.id, "2026-07-28", "2026-08-02", days=4)
        orders.append(o)

    # 측정 전 1회 조회로 행을 적재한다(expire_on_commit reload 잡음 제거).
    loaded = db_session.query(Order).filter(
        Order.id.in_([o.id for o in orders])
    ).order_by(Order.id.asc()).all()

    collected, n_collect = _count_queries(
        lambda: collect_shipment_change_alerts(db_session, loaded, _UID)
    )
    assert n_collect == 1, f"배치 1쿼리 계약 위반: {n_collect}쿼리"
    assert all(len(v["alerts"]) == 2 for v in collected.values())

    _, n_banner = _count_queries(lambda: build_shipment_change_banner(loaded, collected))
    assert n_banner == 0, f"배너는 추가 쿼리 0이어야 한다: {n_banner}쿼리"


def test_collect_with_no_orders_issues_no_query(app):
    """빈 목록은 쿼리 0으로 조기 반환."""
    result, n = _count_queries(lambda: collect_shipment_change_alerts(db_session, [], _UID))
    assert result == {}
    assert n == 0
