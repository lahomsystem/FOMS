"""휴지통/삭제 관련 Blueprint: delete_order(canonical soft delete), trash, restore.

web hard-delete 는 제거됐다(DELETE-TRASH-01): 물리 영구 삭제는 OPS-APPROVAL 게이트를
통과하는 DELETE-RETENTION-01 만 수행한다. 휴지통 목록/복구/purge **대상 선별**은 canonical
``deleted_at`` projection 을 SSOT 로 쓴다. 복구는 transition-aware hybrid 다: transition 기에
``status=='DELETED'`` 로 축을 덮은 주문(legacy web bulk·DELETE-BULK 전이기 미러·cron
cleanup_order_drafts)은 원상태(``original_status``)로 되돌리고, canonical
:func:`soft_delete_order` 로 삭제된(status 실상태 보존) 주문은 delete 축만 clear 한다 —
두 경로 모두 ``deleted_at`` 을 반드시 clear 해 ghost(active_filter 제외) 를 막는다.
"""

import copy
import logging

import uuid

from flask import Blueprint, flash, make_response, redirect, render_template, request, session, url_for
from sqlalchemy import String, text

from foms.web.auth import get_user_by_id, log_access, login_required, role_required
from db import get_db
from foms.services.common.table_version_counter import mark_tables_dirty
from foms.services.erp_display import _ensure_dict, apply_erp_display_fields
from foms.services.erp_order_flags import is_erp_order_record
from foms.services.order_display_utils import format_options_for_display
from foms.services.orders.change_reason import reason_label, record_action_reason
from foms.services.orders.soft_delete import restore_order, soft_delete_order
from foms.services.request_utils import get_preserved_filter_args
from foms.services.gnav_contract import gnav_orders_layout_parent, wants_gnav_fragment
from models import Order

order_trash_bp = Blueprint("order_trash", __name__, url_prefix="")

logger = logging.getLogger(__name__)


def _build_erp_order_options_summary(structured_data):
    """ERP Order item 옵션을 read-only 표시용 요약 문자열로 변환."""
    sd = _ensure_dict(structured_data)
    raw_items = sd.get("items") or []
    if isinstance(raw_items, dict):
        raw_items = [raw_items]
    if not isinstance(raw_items, list) or not raw_items:
        return ""

    first_item = raw_items[0]
    if not isinstance(first_item, dict):
        return ""

    label_map = {
        "standard": "Spec",
        "internal": "Internal",
        "color": "Color",
        "option_detail": "Option",
        "handle": "Handle",
        "misc": "Misc",
    }
    summary_parts = []
    for key, label in label_map.items():
        value = first_item.get(key)
        if isinstance(value, str):
            value = value.strip()
        if value:
            summary_parts.append(f"{label}: {value}")
    return ", ".join(summary_parts)


def _build_trash_display_orders(orders):
    """휴지통 목록 표시용 copy에 ERP Order display 정보를 덧입힌다."""
    display_orders = []
    for order in orders:
        order_display = copy.deepcopy(order)
        order_display.display_options = format_options_for_display(order.options)

        if is_erp_order_record(order) and getattr(order, "structured_data", None):
            order_display.structured_data = _ensure_dict(order.structured_data)
            apply_erp_display_fields(order_display)

            options_summary = _build_erp_order_options_summary(order_display.structured_data)
            if options_summary:
                order_display.display_options = options_summary
                order_display.options = options_summary
            elif str(getattr(order_display, "options", "") or "").strip() in {"''", '""', "-", "ERP Order"}:
                order_display.options = ""
        elif getattr(order_display, "display_options", None):
            order_display.options = order_display.display_options

        display_orders.append(order_display)
    return display_orders


def reset_order_ids(db):
    """주문 ID를 1부터 연속적으로 재정렬합니다."""
    try:
        db.execute(text("CREATE TEMPORARY TABLE temp_order_mapping (old_id INT, new_id INT)"))
        batch_size = 500
        offset = 0
        new_id = 0
        while True:
            orders = (
                db.query(Order)
                .filter(Order.active_filter())
                .order_by(Order.id)
                .offset(offset)
                .limit(batch_size)
                .all()
            )
            if not orders:
                break
            for order in orders:
                new_id += 1
                if order.id != new_id:
                    db.execute(
                        text("INSERT INTO temp_order_mapping (old_id, new_id) VALUES (:old_id, :new_id)"),
                        {"old_id": order.id, "new_id": new_id},
                    )
            offset += batch_size
        mapping_exists = db.execute(text("SELECT COUNT(*) FROM temp_order_mapping")).scalar() > 0
        max_id = new_id
        if mapping_exists:
            # HB-S1: raw UPDATE 라 ORM 세션 훅이 못 본다. 주문 id 전면 재번호는 모든
            # 화면의 본문을 바꾸므로 커밋 시점 카운터 증가 대상으로 직접 등재한다.
            mark_tables_dirty(db, "orders")
            db.execute(
                text(
                    """
                UPDATE orders
                SET id = (SELECT new_id FROM temp_order_mapping WHERE temp_order_mapping.old_id = orders.id)
                WHERE id IN (SELECT old_id FROM temp_order_mapping)
            """
                )
            )
        try:
            seq_query = "SELECT pg_get_serial_sequence('orders', 'id')"
            seq_name = db.execute(text(seq_query)).scalar()
            if seq_name:
                db.execute(text(f"ALTER SEQUENCE {seq_name} RESTART WITH {max_id + 1}"))
            else:
                db.execute(text(f"ALTER SEQUENCE orders_id_seq RESTART WITH {max_id + 1}"))
        except Exception:
            try:
                db.execute(text(f"ALTER SEQUENCE orders_id_seq RESTART WITH {max_id + 1}"))
            except Exception:
                pass  # failopen: intentional: 시퀀스 리셋 재시도 실패 무시 (best-effort)
        db.commit()
        db.execute(text("DROP TABLE IF EXISTS temp_order_mapping"))
    except Exception as exc:
        db.rollback()
        try:
            db.execute(text("DROP TABLE IF EXISTS temp_order_mapping"))
        except Exception:
            pass  # failopen: intentional: 임시테이블 정리 best-effort; 이후 원예외 재발생
        raise exc


def _invalidate_dashboard_caches_after_delete(reason: str) -> None:
    """삭제/복원 commit 뒤 대시보드 캐시를 무효화한다(실패는 로그만 남기고 무시).

    캐시 무효화 실패가 삭제 자체(이미 commit 됨)를 실패로 만들면 안 되므로 fail-open이며,
    묵시적 무시가 아니라 warning 로그로 남긴다.

    Args:
        reason: 무효화 사유(AS 추천 캐시 로그용).
    """
    try:
        from foms.services.common.dashboard_cache import (
            invalidate_dashboard_caches_after_delete_transition,
        )

        invalidate_dashboard_caches_after_delete_transition(reason)
    except Exception:
        logger.warning("post %s dashboard cache invalidate failed", reason, exc_info=True)


@order_trash_bp.route("/delete/<int:order_id>", methods=["POST"])
@login_required
@role_required(["ADMIN", "MANAGER"])
def delete_order(order_id):
    """주문을 휴지통으로 이동 (canonical soft delete).

    POST 전용(GET 405)·공용 CSRF/Origin write guard 소비. 삭제는 canonical
    :func:`soft_delete_order` 로 delete 축 projection(``deleted_at``)만 set 하고 main/
    overlay(logistics/hold/AS/construction) 축은 보존한다 — ``order.status`` 를 직접
    'DELETED' 로 덮어쓰지 않는다.
    """
    db = get_db()
    try:
        order = db.query(Order).filter(Order.id == order_id, Order.active_filter()).first()
        if not order:
            flash("주문을 찾을 수 없거나 이미 삭제되었습니다.", "error")
            return redirect(url_for("order_pages.index"))

        customer_name_for_log = order.customer_name
        user_for_log = get_user_by_id(session.get("user_id"))
        user_name_for_log = user_for_log.name if user_for_log else "Unknown user"

        prod_notif = None
        prod_notif_created = False
        try:
            from foms.services.notifications.production_change import apply_production_change_alert
            prod_notif, prod_notif_created = apply_production_change_alert(
                db, order, "cancelled", "",
                actor_user_id=session.get("user_id"), actor_name=user_name_for_log,
            )
        except Exception as exc_notif:
            logger.warning("production change alert (delete) failed: %s", exc_notif, exc_info=True)

        # canonical soft delete: deleted_at projection + version bump + ORDER_SOFT_DELETED
        # event(hard delete 없음·status/overlay 축 보존). commit 은 이 route 가 소유한다.
        soft_delete_order(db, order_id=order_id, actor_user_id=session.get("user_id"))

        # ORDER-REASON-00: 주문 취소(=휴지통 이동) 사유. 폼이 고른 코드를 같은 트랜잭션에
        # 싣는다. 사유가 비었거나 형식이 틀려도 삭제는 진행된다(unspecified 로 남는다) —
        # 사유 때문에 취소가 막히면 현장이 멈춘다.
        delete_change_set = str(uuid.uuid4())
        delete_reason_code, delete_reason_note = record_action_reason(
            db,
            order_id=order_id,
            change_set_id=delete_change_set,
            code=(request.form.get("reason_code") or "").strip(),
            note=(request.form.get("reason_note") or "").strip(),
            actor_user_id=session.get("user_id"),
        )
        db.commit()

        # 삭제 즉시 반영: 대시보드 read-slice 캐시(TTL 최대 300초)를 무효화하지 않으면
        # 삭제한 주문이 실측 날짜별 집계 등에 최대 5분 잔존한다(2026-08-10 운영 사고).
        _invalidate_dashboard_caches_after_delete("order_delete")

        try:
            from foms.services.notifications.production_change import finalize_production_change_alert
            finalize_production_change_alert(db, prod_notif, created_new=prod_notif_created)
        except Exception as exc_notif:
            logger.warning("production change finalize (delete) failed: %s", exc_notif, exc_info=True)
        log_access(
            f"주문 #{order_id} ({customer_name_for_log}) 삭제 - 담당자: {user_name_for_log}"
            f" · 사유: {reason_label(delete_reason_code)}",
            session.get("user_id"),
            action="ORDER_SOFT_DELETED", target_type="order", target_id=int(order_id),
            detail={
                "change_set": delete_change_set,
                "reason_code": delete_reason_code,
                "reason_note": delete_reason_note,
            },
        )
        flash("주문이 휴지통으로 이동되었습니다.", "success")
    except Exception as exc:
        db.rollback()
        flash(f"주문 삭제 중 오류가 발생했습니다: {str(exc)}", "error")

    redirect_args = get_preserved_filter_args(request.args)
    return redirect(url_for("order_pages.index", **redirect_args))


@order_trash_bp.route("/trash")
@login_required
@role_required(["ADMIN", "MANAGER"])
def trash():
    """휴지통 페이지."""
    search_term = request.args.get("search", "")
    db = get_db()
    # canonical delete 술어: deleted_at IS NOT NULL (DELETE-CORE projection). legacy
    # status=='DELETED' 미러(DELETE-BULK 전이기)에 의존하지 않는다.
    query = db.query(Order).filter(Order.deleted_at.isnot(None))
    if search_term:
        search_pattern = f"%{search_term}%"
        query = query.filter(
            (Order.customer_name.like(search_pattern))
            | (Order.phone.like(search_pattern))
            | (Order.address.like(search_pattern))
            | (Order.product.like(search_pattern))
            | (Order.options.like(search_pattern))
            | (Order.notes.like(search_pattern))
            | (Order.structured_data.cast(String).like(search_pattern))
        )
    orders = _build_trash_display_orders(query.order_by(Order.deleted_at.desc()).all())
    parent = gnav_orders_layout_parent()
    html = render_template(
        "orders/trash.html",
        orders=orders,
        search_term=search_term,
        parent_template=parent,
    )
    resp = make_response(html)
    if wants_gnav_fragment():
        resp.headers["X-FOMS-GNAV-FRAGMENT"] = "1"
    return resp


@order_trash_bp.route("/restore_orders", methods=["POST"])
@login_required
@role_required(["ADMIN", "MANAGER"])
def restore_orders():
    """선택한 주문 복원."""
    selected_ids = request.form.getlist("selected_order")
    if not selected_ids:
        flash("복원할 주문을 선택해주세요.", "warning")
        return redirect(url_for("order_trash.trash"))

    db = get_db()
    try:
        order_ids = [int(order_id) for order_id in selected_ids]
        # canonical delete 술어(deleted_at)로 실제 휴지통 항목만 선별한다.
        orders = (
            db.query(Order)
            .filter(Order.id.in_(order_ids), Order.deleted_at.isnot(None))
            .all()  # perf-ok
        )
        actor_user_id = session.get("user_id")
        for order in orders:
            if (order.status or "") == "DELETED":
                # transition: status 축을 'DELETED'로 덮은 주문(legacy web bulk·DELETE-BULK
                # 전이기 미러·cron cleanup). 원상태로 되돌린다 — restore_order 만으로는
                # status='DELETED' 가 잔존해 active_filter(status!='DELETED' AND deleted_at
                # IS NULL) 에서 제외되는 ghost 가 된다. DELETE-BULK 미러는 무접근(제거 안 함).
                order.status = order.original_status or "RECEIVED"
                order.original_status = None
                order.deleted_at = None
            else:
                # canonical soft_delete_order 로 삭제(status 실상태 보존) → delete 축만 clear,
                # main/logistics/hold/AS overlay 보존.
                restore_order(db, order_id=order.id, actor_user_id=actor_user_id)
        db.commit()
        # 복원도 주문이 모든 탭에 다시 나타나는 전이 → 삭제와 동일하게 즉시 무효화.
        _invalidate_dashboard_caches_after_delete("order_restore")
        log_access(f"주문 {len(orders)}개 복원", session.get("user_id"), {"count": len(orders)})
        flash(f"{len(orders)}개 주문이 성공적으로 복원되었습니다.", "success")
    except Exception as exc:
        db.rollback()
        flash(f"주문 복원 중 오류가 발생했습니다: {str(exc)}", "error")
    return redirect(url_for("order_trash.trash"))


# web hard-delete 제거(DELETE-TRASH-01): 물리 삭제(``db.delete``)는 web 에서 노출하지 않는다.
# retention 기간 경과분의 영구 삭제는 OPS-APPROVAL 게이트를 통과한 DELETE-RETENTION-01
# (:mod:`foms.services.orders.delete_retention`) 만이 수행한다. 휴지통에서는 복원만 제공한다.
