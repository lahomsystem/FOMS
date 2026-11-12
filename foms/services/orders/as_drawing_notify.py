"""완료 주문 AS 도면 차수 알림(벨) — 호출자 트랜잭션 안에서 row 를 만들고 commit 은 하지 않는다.

설계서 ``docs/specs/2026-11-11-as-drawing-after-completion_SPEC.md`` §4.

- ``request``      AS 담당이 접수 창에서 부탁 → 원래 도면 담당(없으면 도면팀 전체).
- ``registered``   도면팀이 AS 접수까지 하고 시작 → CS 팀.
- ``transfer``     도면팀이 AS 도면을 보냄 → 영업 담당 + CS 팀.
- ``revision``     영업·AS 담당이 고쳐 달라고 함 → 차수를 연 사람 + 도면 담당.
- ``confirm``      영업·AS 담당이 확인 → 차수를 연 사람.

폰 push 는 원래 도면 알림 규칙을 따른다(2026-11-12): 부탁 · 도착 · 고쳐 달라고 함은 폰에도,
접수(CS 팀 전체) · 확인은 벨만. 폰으로 가는 종류는 알림 유형을 따로 둔다(``PUSH_TYPES``) —
push 게이트(``push_sender``)가 유형으로 판정하기 때문이다. 줄 세우기는 커밋 뒤
(:func:`enqueue_as_drawing_push`)에 부르는 쪽이 한다.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

from foms.services.notifications.push_sender import enqueue_push_for_notification
from foms.services.notifications.recipients import fan_out_new_notification
from foms.services.orders.erp_policy_permissions import get_assignee_ids
from models import Notification

logger = logging.getLogger(__name__)

NOTIFICATION_TYPE = "AS_DRAWING"   # 벨만(접수 · 확인)

#: 폰에도 가는 종류의 알림 유형 — ``push_sender`` P1 · 높은 긴급도 · 바로가기 · 배너 글에 등록돼 있다.
PUSH_TYPES = {
    "request": "AS_DRAWING_REQUEST",
    "transfer": "AS_DRAWING_TRANSFERRED",
    "revision": "AS_DRAWING_REVISION",
}

_TITLES = {
    "request": "AS 도면 부탁",
    "registered": "도면팀이 AS를 접수했어요",
    "transfer": "AS 도면 왔어요",
    "revision": "AS 도면 고쳐 달라고 해요",
    "confirm": "AS 도면 확인했어요",
}


def _customer_name(order: Any) -> str:
    sd = order.structured_data if isinstance(getattr(order, "structured_data", None), dict) else {}
    parties = sd.get("parties") if isinstance(sd.get("parties"), dict) else {}
    customer = parties.get("customer") if isinstance(parties.get("customer"), dict) else {}
    return str(customer.get("name") or getattr(order, "customer_name", "") or "").strip()


def _one_line(text: Any) -> str:
    """여러 줄 부탁 글을 알림 한 줄로(종 · 폰 배너는 줄바꿈을 못 보여 준다)."""
    return " / ".join(line.strip() for line in str(text or "").splitlines() if line.strip())


def _message(order: Any, kind: str, round_no: int, text: str) -> str:
    head = f"주문 #{order.id}"
    name = _customer_name(order)
    if name:
        head += f" ({name})"
    body = {
        "request": f" AS 도면 {round_no}차를 부탁했어요.",
        "registered": f" 도면팀이 AS 접수를 하고 AS 도면 {round_no}차를 시작했어요. 방문 날짜와 유상·무상을 정해 주세요.",
        "transfer": f" AS 도면 {round_no}차가 왔어요. 확인하거나 고쳐 달라고 해 주세요.",
        "revision": f" AS 도면 {round_no}차를 고쳐 달라고 했어요.",
        "confirm": f" AS 도면 {round_no}차를 확인했어요.",
    }[kind]
    return head + body + (f" {text}" if text else "")


def _users(ids: Iterable[Any]) -> list[int]:
    out: list[int] = []
    for raw in ids:
        try:
            uid = int(raw)
        except (TypeError, ValueError):
            continue
        if uid > 0 and uid not in out:
            out.append(uid)
    return out


def notify_as_drawing(db: Any, order: Any, kind: str, *, round_no: int, actor: Any,
                      text: str = "", opener_id: Optional[int] = None,
                      sales_target: Optional[tuple] = None) -> list:
    """알림 row 를 만들고 수신자 상태까지 같은 트랜잭션에 싣는다. 실패는 로그만 남긴다.

    Args:
        db: 요청 세션(호출자가 commit).
        order: 대상 주문.
        kind: ``request``·``registered``·``transfer``·``revision``·``confirm``.
        round_no: 화면에 쓰는 차수 번호.
        actor: 누른 사람(``id``·``name``).
        text: 덧붙일 한 줄(메모·사유).
        opener_id: 차수를 연 사람 id(revision·confirm 수신자).
        sales_target: ``transfer`` 의 영업 쪽 수신 ``(target_team, target_manager_name, target_role)``.
            도면 전달 알림과 같은 규칙(``erp_orders_drawing._drawing_notice_target``)을 API 층이 계산해
            넘긴다(서비스 층은 API 를 부르지 않는다). 없으면 CS 팀만 받는다.

    Returns:
        만든 Notification 목록.
    """
    if kind not in _TITLES:
        raise ValueError(f"unknown AS drawing notice kind: {kind}")
    actor_id = getattr(actor, "id", None)
    actor_name = getattr(actor, "name", None) or ""
    targets: list[dict] = []
    drawing_ids = _users(get_assignee_ids(order, "DRAWING_DOMAIN") or [])
    if kind == "request":
        targets = [{"target_type": "USER", "target_user_id": uid} for uid in drawing_ids] or [
            {"target_team": "DRAWING"}]
    elif kind == "registered":
        targets = [{"target_team": "CS"}]
    elif kind == "transfer":
        team, manager_name, role = sales_target or ("CS", None, None)
        targets = [{"target_team": team, "target_manager_name": manager_name, "target_role": role}]
        if team != "CS":
            targets.append({"target_team": "CS"})
    elif kind == "revision":
        ids = _users(([opener_id] if opener_id else []) + drawing_ids)
        targets = [{"target_type": "USER", "target_user_id": uid} for uid in ids] or [{"target_team": "DRAWING"}]
    elif kind == "confirm":
        ids = _users([opener_id] if opener_id else [])
        targets = [{"target_type": "USER", "target_user_id": uid} for uid in ids]

    # DB 쓰기 실패는 삼키지 않는다 — flush 가 깨진 세션으로 호출자가 commit 하면 더 나쁘다.
    # 도면 전달 알림(erp_orders_drawing.perform_drawing_transfer)과 같은 규칙이다.
    created = []
    for target in targets:
        if target.get("target_user_id") and target["target_user_id"] == actor_id:
            continue  # 내가 한 일은 나에게 알리지 않는다
        notif = Notification(
            order_id=order.id,
            notification_type=PUSH_TYPES.get(kind, NOTIFICATION_TYPE),
            target_type=target.get("target_type") or "ORDER",
            target_team=target.get("target_team"),
            target_manager_name=target.get("target_manager_name"),
            target_role=target.get("target_role"),
            target_user_id=target.get("target_user_id"),
            title=_TITLES[kind],
            message=_message(order, kind, round_no, _one_line(text)[:200]),
            created_by_user_id=actor_id,
            created_by_name=actor_name,
            is_read=False,
        )
        db.add(notif)
        db.flush()
        fan_out_new_notification(db, notif, actor_user_id=actor_id)
        created.append(notif)
    if not created:
        logger.info("[AS_DRAWING] notice %s had no recipients (order %s)", kind, order.id)
    return created


def enqueue_as_drawing_push(db: Any, notifications: Iterable[Any]) -> None:
    """커밋 뒤 폰 알림을 줄 세운다 — 폰으로 가는 유형만. 실패는 로그만(벨 알림은 이미 저장됐다)."""
    push_types = set(PUSH_TYPES.values())
    for notif in notifications or []:
        if getattr(notif, "notification_type", None) not in push_types or not getattr(notif, "id", None):
            continue
        try:
            enqueue_push_for_notification(int(notif.id), db=db)
        except Exception as exc:  # noqa: BLE001 - 폰 알림 실패가 저장 결과를 바꾸지 않는다
            logger.warning("[AS_DRAWING] push enqueue failed (notification %s): %s", notif.id, exc)
