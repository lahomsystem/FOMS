"""발송은 했는데 주문 등록이 안 된 마법사 초안 알림 (WIZ-SEND 안전망, 2026-10-20).

마법사 초안에서 알림톡·실측 PUSH 를 보낸 뒤 [주문 등록] 을 누르지 않고 화면을 떠나면
고객·실측방은 안내를 받았는데 ERP 에는 주문이 없다(설계 D1 — 발송은 주문을 만들지 않는다).
닫기 확인창은 뒤로가기·탭 닫기·앱 전환을 못 잡아서 같은 일이 되풀이됐다
(2026-10-20 박미영 건은 PUSH 뒤 197분 만에 등록).

이 스윕이 그 초안을 찾아 알린다.

* 마지막 성공 발송 뒤 :data:`OWNER_AFTER_MINUTES` 가 지나면 작성자에게 1회.
* :data:`ADMIN_AFTER_MINUTES` 가 지나도 그대로면 ADMIN 전원에게 1회.

이미 알렸다는 표시는 ``OrderDraft.send_history`` 의 :data:`REMINDER_KEY` 에 남긴다. 발송
이력과 같은 열이지만 ``pushed``/``sent`` 가 없는 dict 라 "발송함" 판정·등록 승계
(``_inherit_draft_send_history`` 는 발송 종류 키만 옮긴다)에 섞이지 않는다.

배달(배지·실시간·웹푸시)은 커밋 뒤 호출자(``scripts/maintenance/run_notification_escalation.py``)
가 맡는다 — 서비스가 api 계층(배지 캐시)을 거꾸로 부르지 않게 한다.
설계서: ``docs/plans/2026-10-20-wizard-push-register-safety-spec.md`` §3.2.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List, Optional

from foms.services.datetime_kst import now_utc_naive
from foms.services.order_draft_service import (
    SEND_KIND_ALIMTALK,
    SEND_KIND_CHANNEL_MEASURE,
    has_send_history_clause,
    write_draft_send_history_meta,
)
from models import Notification, OrderDraft, User
from foms.services.notifications.recipients import fan_out_new_notification

NOTIFICATION_TYPE = "DRAFT_SENT_NOT_REGISTERED"
TITLE = "주문 등록이 안 됐어요"
REMINDER_KEY = "draft_send_reminder"
OWNER_AFTER_MINUTES = 30
ADMIN_AFTER_MINUTES = 120
_KIND_LABELS = {
    SEND_KIND_CHANNEL_MEASURE: "실측 PUSH",
    SEND_KIND_ALIMTALK: "알림톡",
}

__all__ = [
    "ADMIN_AFTER_MINUTES",
    "NOTIFICATION_TYPE",
    "OWNER_AFTER_MINUTES",
    "REMINDER_KEY",
    "TITLE",
    "last_successful_send",
    "remind_unregistered_sent_drafts",
]


def _parse_sent_at(raw: Any) -> Optional[_dt.datetime]:
    """이력의 ``sent_at`` ISO 문자열을 naive UTC 로 읽는다(못 읽으면 None)."""
    if not raw:
        return None
    try:
        value = _dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(_dt.timezone.utc).replace(tzinfo=None)
    return value


def last_successful_send(history: Any) -> Optional[tuple[str, _dt.datetime]]:
    """초안 발송 이력에서 마지막 **성공** 발송의 ``(종류 문구, 시각)`` 을 준다.

    실패 기록(``error`` 만 있고 ``sent``/``pushed`` 가 아닌 것)은 고객에게 나간 것이 없으므로
    세지 않는다.

    Args:
        history: ``OrderDraft.send_history``.

    Returns:
        성공 발송이 없으면 None.
    """
    if not isinstance(history, dict):
        return None
    latest: Optional[tuple[str, _dt.datetime]] = None
    for kind, label in _KIND_LABELS.items():
        entry = history.get(kind)
        if not isinstance(entry, dict):
            continue
        if not (entry.get("pushed") or entry.get("message_id")) or entry.get("error"):
            continue
        sent_at = _parse_sent_at(entry.get("sent_at"))
        if sent_at is None:
            continue
        if latest is None or sent_at > latest[1]:
            latest = (label, sent_at)
    return latest


def _customer_name(row: OrderDraft) -> str:
    """알림 문구용 고객명(초안이라 비어 있을 수 있다)."""
    payload = row.payload if isinstance(row.payload, dict) else {}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    # 등록 변환(``_draft_payload_to_structured``)과 같은 칸을 읽는다.
    name = str(data.get("customer_name") or "").strip()
    return name or "이름 없는"


def _create(db: Any, *, recipient_user_id: int, message: str, now: _dt.datetime) -> Notification:
    """한 사람에게 알림 1건(배달은 커밋 뒤 finalize)."""
    notif = Notification(
        order_id=None,
        notification_type=NOTIFICATION_TYPE,
        target_type="USER",
        target_user_id=int(recipient_user_id),
        is_urgent=False,
        title=TITLE,
        message=message,
        is_read=False,
        created_at=now,
    )
    db.add(notif)
    db.flush()
    fan_out_new_notification(db, notif, actor_user_id=None)
    return notif


def _admin_user_ids(db: Any) -> List[int]:
    """활성 ADMIN id 목록."""
    rows = db.query(User.id).filter(User.role == "ADMIN", User.is_active == True)  # noqa: E712
    return [int(r[0]) for r in rows]


def _author_name(db: Any, user_id: Optional[int]) -> str:
    """초안 작성자 표시명."""
    if user_id is None:
        return "알 수 없음"
    user = db.get(User, int(user_id))
    return (getattr(user, "name", None) or f"#{user_id}") if user else f"#{user_id}"


def remind_unregistered_sent_drafts(
    db: Any, *, now: Optional[_dt.datetime] = None
) -> Dict[str, Any]:
    """발송 후 미등록 초안을 찾아 알림을 만든다(커밋은 호출자).

    Args:
        db: 세션.
        now: 기준 시각(naive UTC). 생략하면 현재.

    Returns:
        ``{checked, owner_reminded, admin_reminded, created_notification_ids,
        recipient_user_ids}``.
    """
    now = now if now is not None else now_utc_naive()
    owner_cutoff = now - _dt.timedelta(minutes=OWNER_AFTER_MINUTES)
    admin_cutoff = now - _dt.timedelta(minutes=ADMIN_AFTER_MINUTES)
    rows = (
        db.query(OrderDraft)
        .filter(OrderDraft.order_id.is_(None), has_send_history_clause())
        .order_by(OrderDraft.id.asc())
        .all()
    )
    created: List[int] = []
    recipients: List[int] = []
    owner_reminded = 0
    admin_reminded = 0
    admin_ids: Optional[List[int]] = None
    for row in rows:
        last = last_successful_send(row.send_history)
        if last is None:
            continue
        label, sent_at = last
        meta = (row.send_history or {}).get(REMINDER_KEY)
        meta = dict(meta) if isinstance(meta, dict) else {}
        # 알린 뒤에 다시 보냈다면(재발송) 그 발송 기준으로 한 번 더 알린다.
        reminded_for = _parse_sent_at(meta.get("for_sent_at"))
        if reminded_for is None or reminded_for < sent_at:
            meta = {}
        name = _customer_name(row)
        changed = False
        if not meta.get("owner_at") and sent_at <= owner_cutoff and row.user_id is not None:
            notif = _create(
                db,
                recipient_user_id=int(row.user_id),
                message=(
                    f"{name} 고객 {label}은 나갔는데 주문 등록이 안 됐어요. "
                    "홈 화면 '작성 중' 줄에서 이어서 등록해 주세요."
                ),
                now=now,
            )
            created.append(int(notif.id))
            recipients.append(int(row.user_id))
            meta["owner_at"] = now.isoformat()
            owner_reminded += 1
            changed = True
        if not meta.get("admin_at") and sent_at <= admin_cutoff:
            if admin_ids is None:
                admin_ids = _admin_user_ids(db)
            author = _author_name(db, row.user_id)
            for admin_id in admin_ids:
                notif = _create(
                    db,
                    recipient_user_id=admin_id,
                    message=(
                        f"{author} 님이 {name} 고객 {label}을 보냈는데 2시간째 주문 등록이 "
                        "안 됐어요. 관리자 화면 '발송 후 미등록 초안'에서 확인해 주세요."
                    ),
                    now=now,
                )
                created.append(int(notif.id))
                recipients.append(admin_id)
            meta["admin_at"] = now.isoformat()
            admin_reminded += 1
            changed = True
        if changed:
            meta["for_sent_at"] = sent_at.isoformat()
            write_draft_send_history_meta(db, row, key=REMINDER_KEY, value=meta)
    return {
        "checked": len(rows),
        "owner_reminded": owner_reminded,
        "admin_reminded": admin_reminded,
        "created_notification_ids": created,
        "recipient_user_ids": sorted(set(recipients)),
    }
