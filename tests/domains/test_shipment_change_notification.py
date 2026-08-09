"""출고 시공일 변경 벨 알림 + 푸시 계약 (T6).

여기서 고정하는 계약:

* 시공일이 바뀌면 ``SHIPMENT_ORDER_CHANGED`` 알림이 **정확히 1건** 나고 수신 팀은
  :data:`~foms.services.notifications.shipment_change.TARGET_TEAM` 이다.
  제목 ``[출고] 시공일 변경 — {고객명}`` / 본문 ``주문 #N — 시공일 8/5 → 8/12``.
* 60초 안의 두 번째 변경은 새 row 를 만들지 않고 **merge** 한다. 이때 최초 ``from`` 을
  보존하고 ``to`` 만 최신으로 올린다(생산 emitter 가 이전 ``from`` 을 덮어써 잃는 결함의
  회귀 방지).
* **주문 생성은 0건** — 생성에는 "이전 값"이 없다(T1 이 ``session.new`` 를 제외한다).
* ``SHIPMENT_ORDER_CHANGED`` 가 ``push_sender._DEFAULT_P1_TYPES`` 에 있다. 미등록이면
  enqueue 해도 조용히 발송되지 않는다 — 운영의 ``PRODUCTION_ORDER_CHANGED`` 가 그 상태다.
* 팬아웃은 대상 팀 사용자에게만 ``notification_user_states`` 를 만든다(무관 팀 제외).

호출부를 흉내내지 않고 **실제 배선**(``order_date_sync`` 전역 세션 훅)으로 검증한다 —
시공일을 바꾸고 커밋하는 것만으로 알림이 나야 T6 이 성립한다.
"""

from __future__ import annotations

from typing import Any

from flask import session as flask_session
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.notifications.push_sender import _DEFAULT_P1_TYPES, _generic_title
from foms.services.notifications.shipment_change import (
    NOTIFICATION_TYPE,
    TARGET_TEAM,
    shipment_change_deep_link,
)
from models import Notification, NotificationUserState, Order, User


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _make_user(username: str, *, team: str | None, role: str = "STAFF") -> User:
    """테스트 사용자 1명 생성(커밋 포함)."""
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team=team,
        name=f"{username} 이름",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _sd(construction_date: str, customer_name: str = "출고 고객") -> dict[str, Any]:
    """시공일을 가진 최소 ERP structured_data."""
    return {
        "workflow": {"stage": "SHIPMENT"},
        "parties": {"customer": {"name": customer_name}},
        "schedule": {"construction": {"date": construction_date}},
    }


def _make_order(construction_date: str = "2026-08-05", customer_name: str = "출고 고객") -> Order:
    """시공일을 가진 주문 1건 생성(커밋 포함). 생성은 알림 대상이 아니다."""
    order = Order(
        received_date="2026-07-01",
        customer_name=customer_name,
        phone="010-3333-4444",
        address="서울 출고로 1",
        product="붙박이장",
        status="IN_CONSTRUCTION",
        manager_name="담당",
        is_erp_order=True,
        structured_data=_sd(construction_date, customer_name),
        erp_stage_code="SHIPMENT",
        scheduled_date=construction_date,
    )
    db_session.add(order)
    db_session.commit()
    return order


def _move_construction_date(order: Order, new_date: str) -> None:
    """시공일을 옮기고 커밋한다 — 실제 쓰기와 같은 경로(전역 before_flush → before_commit)."""
    order.scheduled_date = new_date
    sd = dict(order.structured_data or {})
    sd["schedule"] = {"construction": {"date": new_date}}
    order.structured_data = sd
    db_session.commit()


def _notifs(order_id: int) -> list[Notification]:
    """해당 주문의 출고 변경 알림 목록(생성순)."""
    db_session.expire_all()
    return (
        db_session.query(Notification)
        .filter(
            Notification.order_id == order_id,
            Notification.notification_type == NOTIFICATION_TYPE,
        )
        .order_by(Notification.id.asc())
        .all()
    )


# --------------------------------------------------------------------------- #
# 1. 생성 — 1건 · 대상 팀 · 제목/본문
# --------------------------------------------------------------------------- #
def test_construction_date_change_creates_single_team_notification(app):
    """시공일 변경 1회 → 알림 정확히 1건(대상 팀 + 규정 제목/본문)."""
    order = _make_order("2026-08-05", customer_name="김출고")
    order_id = order.id

    _move_construction_date(order, "2026-08-12")

    notifs = _notifs(order_id)
    assert len(notifs) == 1
    notif = notifs[0]
    assert notif.notification_type == NOTIFICATION_TYPE
    assert notif.target_type == "TEAM"
    assert notif.target_team == TARGET_TEAM
    assert notif.title == "[출고] 시공일 변경 — 김출고"
    assert notif.message == f"주문 #{order_id} — 시공일 8/5 → 8/12"


def test_target_team_is_a_real_assignable_team_code(app):
    """대상 팀 코드는 사용자 관리 canonical enum 값이어야 한다(오타/유령 팀 방지)."""
    from foms.web.auth import TEAMS

    assert TARGET_TEAM in TEAMS


# --------------------------------------------------------------------------- #
# 2. debounce merge — row 1건 유지 · 최초 from 보존 · 최신 to
# --------------------------------------------------------------------------- #
def test_second_change_within_60s_merges_and_keeps_original_from(app):
    """60초 내 두 번째 변경은 새 row 없이 merge — ``8/5 → 8/20`` 한 줄로 남는다."""
    order = _make_order("2026-08-05")
    order_id = order.id

    _move_construction_date(order, "2026-08-12")
    _move_construction_date(order, "2026-08-20")

    notifs = _notifs(order_id)
    assert len(notifs) == 1, "60초 내 두 번째 변경이 새 알림 row 를 만들면 안 된다"
    # 최초 from(8/5)이 살아 있고 to 만 최신(8/20)으로 올라간다.
    assert notifs[0].message == f"주문 #{order_id} — 시공일 8/5 → 8/20"


def test_merge_does_not_duplicate_user_states(app):
    """merge 는 fan_out 을 다시 돌리지 않는다 — 수신자 state 는 1건 그대로."""
    user = _make_user("bell_merge_member", team=TARGET_TEAM)
    order = _make_order("2026-08-05")

    _move_construction_date(order, "2026-08-12")
    _move_construction_date(order, "2026-08-20")

    notif = _notifs(order.id)[0]
    states = (
        db_session.query(NotificationUserState)
        .filter(
            NotificationUserState.notification_id == notif.id,
            NotificationUserState.user_id == user.id,
        )
        .all()
    )
    assert len(states) == 1


# --------------------------------------------------------------------------- #
# 3. 주문 생성은 0건
# --------------------------------------------------------------------------- #
def test_order_creation_creates_no_notification(app):
    """생성에는 '이전 시공일'이 없으므로 알림 0건."""
    order = _make_order("2026-08-05")
    assert _notifs(order.id) == []


def test_unchanged_save_creates_no_notification(app):
    """시공일이 그대로면 저장을 반복해도 알림 0건(허위 알림 금지)."""
    order = _make_order("2026-08-05")
    _move_construction_date(order, "2026-08-05")
    assert _notifs(order.id) == []


# --------------------------------------------------------------------------- #
# 4. 푸시 타입 등록 (운영이 지금 틀린 바로 그 지점)
# --------------------------------------------------------------------------- #
def test_notification_type_is_registered_in_push_allowlist():
    """``_DEFAULT_P1_TYPES`` 미등록이면 enqueue 해도 push 가 나가지 않는다."""
    assert NOTIFICATION_TYPE in _DEFAULT_P1_TYPES


def test_should_push_accepts_the_type_without_urgent_flag(app):
    """is_urgent=False 여도 P1 게이트를 통과해야 실제 발송된다."""
    from foms.services.notifications.push_sender import _should_push

    notif = Notification(
        notification_type=NOTIFICATION_TYPE,
        target_type="TEAM",
        target_team=TARGET_TEAM,
        title="t",
        message="m",
        is_urgent=False,
    )
    assert _should_push(notif) is True
    assert _generic_title(False, NOTIFICATION_TYPE) == "출고 일정 변경"


# --------------------------------------------------------------------------- #
# 5. 팬아웃 — 대상 팀만
# --------------------------------------------------------------------------- #
def test_fan_out_reaches_target_team_user_only(app):
    """대상 팀 사용자에게만 state 가 생기고 무관 팀에는 생기지 않는다."""
    member = _make_user("bell_team_member", team=TARGET_TEAM)
    outsider = _make_user("bell_outsider", team="DRAWING")
    order = _make_order("2026-08-05")

    _move_construction_date(order, "2026-08-12")

    notif = _notifs(order.id)[0]
    user_ids = {
        uid
        for (uid,) in db_session.query(NotificationUserState.user_id).filter(
            NotificationUserState.notification_id == notif.id
        )
    }
    assert member.id in user_ids
    assert outsider.id not in user_ids


# --------------------------------------------------------------------------- #
# 6. 요청 컨텍스트 · finalize 안전성 · 딥링크
# --------------------------------------------------------------------------- #
def test_actor_is_recorded_and_finalize_is_safe_in_request_context(app):
    """요청 컨텍스트에서는 변경자가 기록되고, push/realtime 미구성이어도 예외가 없다."""
    actor = _make_user("bell_actor", team=TARGET_TEAM, role="ADMIN")
    order = _make_order("2026-08-05")
    order_id = order.id

    with app.test_request_context():
        flask_session["user_id"] = actor.id
        _move_construction_date(db_session.get(Order, order_id), "2026-08-12")

    notif = _notifs(order_id)[0]
    assert notif.created_by_user_id == actor.id
    assert notif.created_by_name == actor.name


def test_deep_link_opens_shipment_dashboard_on_the_changed_date(app):
    """벨 항목 딥링크는 옮겨간 시공일의 출고 대시보드를 연다(모델 필드 신설 없이 파생)."""
    from foms.api.notifications import _resolve_notification_deep_link

    order = _make_order("2026-08-05")
    order_id = order.id
    _move_construction_date(order, "2026-08-12")

    notif = _notifs(order_id)[0]
    link = _resolve_notification_deep_link(notif, _sd("2026-08-12"))
    assert link["deep_link_url"] == "/erp/shipment?date=2026-08-12"
    # 시공일을 못 읽으면 날짜 없는 대시보드로 degrade(예외 금지).
    assert shipment_change_deep_link(None) == "/erp/shipment"
