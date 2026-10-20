"""관리자 화면 — 발송은 했는데 주문 등록이 안 된 마법사 초안 (2026-10-20 사용자 요청).

마법사 초안에서 알림톡·실측 PUSH 를 보낸 뒤 [주문 등록] 을 안 누르면 고객·실측방은 안내를
받았는데 ERP 에 주문이 없다. 초안은 작성자 본인만 보므로 관리자가 알 길이 없었고, 7일 뒤
정리 cron 이 조용히 지웠다. 이제 그런 초안은 지우지 않고(``tools/cron/cleanup_order_drafts.py``)
이 화면에 모은다. 작성자에게는 30분 뒤, 관리자에게는 2시간 뒤 알림이 간다
(:mod:`foms.services.notifications.draft_send_reminder`).

등록은 여기서 하지 않는다 — 초안은 작성자 소유라 작성자가 홈 화면 '작성 중' 줄에서 이어서
등록한다. 관리자는 버려도 되는 초안(중복·취소된 상담)을 정리만 한다.
설계서: ``docs/plans/2026-10-20-wizard-push-register-safety-spec.md`` §3.2.
"""

from __future__ import annotations

from typing import Any

from flask import flash, redirect, render_template, request, session, url_for

from db import get_db
from foms.services.audit_message_display import describe_action
from foms.api.erp_order_draft import _enqueue_draft_attachment_cleanup
from foms.services.datetime_kst import format_datetime_kst
from foms.services.notifications.draft_send_reminder import last_successful_send
from foms.services.order_draft_service import has_send_history_clause
from foms.web.admin.routes import admin_bp
from foms.web.auth import log_access, login_required, role_required
from models import OrderDraft, User

# 한 화면 상한 — 정상이면 몇 건 안 된다. 넘치면 화면이 말한다.
_LIMIT = 200


def _row(draft: OrderDraft, users: dict[int, User]) -> dict[str, Any] | None:
    """초안 1건을 화면 한 줄로(성공 발송이 없으면 None — 실패 기록만 있는 초안은 뺀다)."""
    last = last_successful_send(draft.send_history)
    if last is None:
        return None
    label, sent_at = last
    payload = draft.payload if isinstance(draft.payload, dict) else {}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    author = users.get(int(draft.user_id)) if draft.user_id is not None else None
    return {
        "id": draft.id,
        "customer_name": str(data.get("customer_name") or "").strip() or "(이름 없음)",
        "phone": str(data.get("phone") or "").strip(),
        "address": str(data.get("address") or "").strip(),
        "kind": label,
        "sent_at": format_datetime_kst(sent_at, "%m-%d %H:%M"),
        "author": getattr(author, "name", None) or f"#{draft.user_id}",
        "updated_at": format_datetime_kst(draft.updated_at, "%m-%d %H:%M"),
        "_sent_at": sent_at,
    }


@admin_bp.route("/admin/sent-unregistered-drafts")
@login_required
@role_required(["ADMIN"])
def sent_unregistered_drafts():
    """발송 후 미등록 초안 목록(관리자 전용).

    Returns:
        ``admin/sent_unregistered_drafts.html`` 렌더 결과.
    """
    db = get_db()
    drafts = (
        db.query(OrderDraft)
        .filter(OrderDraft.order_id.is_(None), has_send_history_clause())
        .order_by(OrderDraft.id.desc())
        .limit(_LIMIT)
        .all()  # perf-ok: order_id IS NULL + send_history 있음 — 정상이면 몇 건, 상한 200
    )
    user_ids = sorted({int(d.user_id) for d in drafts if d.user_id is not None})
    users = (
        {int(u.id): u for u in db.query(User).filter(User.id.in_(user_ids)).all()}
        if user_ids else {}
    )
    rows = [r for r in (_row(d, users) for d in drafts) if r is not None]
    rows.sort(key=lambda r: r["_sent_at"], reverse=True)
    return render_template(
        "admin/sent_unregistered_drafts.html",
        rows=rows,
        truncated=len(drafts) >= _LIMIT,
    )


@admin_bp.route("/admin/sent-unregistered-drafts/<int:draft_id>/discard", methods=["POST"])
@login_required
@role_required(["ADMIN"])
def discard_sent_unregistered_draft(draft_id: int):
    """버려도 되는 초안을 지운다(첨부 임시 파일 삭제 예약 + 감사 기록).

    Args:
        draft_id: ``OrderDraft.id``.

    Returns:
        목록으로 redirect.
    """
    db = get_db()
    row = (
        db.query(OrderDraft)
        .filter(OrderDraft.id == int(draft_id), OrderDraft.order_id.is_(None))
        .one_or_none()
    )
    if row is None:
        flash("초안을 찾을 수 없습니다. 이미 등록됐거나 지워졌을 수 있습니다.", "warning")
        return redirect(url_for("admin.sent_unregistered_drafts"))
    payload = row.payload if isinstance(row.payload, dict) else {}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    name = str(data.get("customer_name") or "").strip() or "이름 없음"
    if row.user_id is not None:
        _enqueue_draft_attachment_cleanup(db, int(row.user_id), row.draft_key, row)
    uid = session.get("user_id")
    log_access(
        describe_action("ORDER_DRAFT_DISCARDED", target_label=f"주문 초안 #{row.id} ({name})"),
        uid,
        auto_commit=False,
        action="ORDER_DRAFT_DISCARDED",
        target_type="order_draft",
        target_id=int(row.id),
        detail={"draft_key": row.draft_key, "owner_user_id": row.user_id},
    )
    db.delete(row)
    db.commit()
    flash(f"{name} 고객 초안을 버렸습니다.", "success")
    return redirect(url_for("admin.sent_unregistered_drafts"))
