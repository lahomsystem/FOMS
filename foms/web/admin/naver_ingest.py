"""네이버 수집 관리 화면 (NAVER-INGEST-01 §3.7).

수집은 사람이 안 보는 데서 도는 배경 작업이라, **지금 잘 돌고 있는지**와 **사람 손이 필요한
건**을 한 화면에서 보여줘야 한다. 이 화면이 답하는 질문은 셋이다:

1. 마지막으로 언제까지 수집했나(워터마크), 마지막 실행이 실패했나.
2. 사람이 봐야 할 보류(``PENDING_REVIEW``)·실패 건이 있나.
3. 앱 인증이 언제 만료되나(만료되면 수집이 조용히 전면 중단된다).

"지금 수집" 은 **rq enqueue 만** 한다. 네이버 HTTP 는 WORKER 에서만 나가야 한다 —
커머스API센터 호출 IP 한도(3)와 Railway static outbound IP(3)가 같아 여유가 0이라,
web 에서 부르면 등록되지 않은 IP 라 차단된다. 취향이 아니라 제약이다.
"""

from __future__ import annotations

import datetime
from typing import Any, Optional

from flask import jsonify, render_template, request

from db import get_db
from foms.services.datetime_kst import format_datetime_kst
from foms.services.jobs.queue import enqueue_naver_order_sync
from foms.web.admin.routes import admin_bp
from foms.web.auth import log_access, login_required, role_required
from models import ExternalOrderLink, Order

#: 한 페이지에 보여줄 수집 이력 행 수(관리자 cold path 라 페이지네이션으로 충분).
PAGE_SIZE = 50

#: 상태 필터 닫힌집합. 임의 문자열이 그대로 쿼리에 들어가지 않게 한다.
VALID_STATUSES = ("LINKED", "PENDING_REVIEW", "FAILED")


def _watermark_view(db) -> dict[str, Any]:
    """워터마크 상태를 화면 표시용으로 편다."""
    from foms.services.integrations.naver_commerce import watermark as wm

    state = wm.read_state(db)
    return {
        "last_success_to": state.get("last_success_to"),
        "last_run_at": state.get("last_run_at"),
        "last_error": state.get("last_error"),
        "last_summary": state.get("last_summary") or {},
    }


def _expiry_view(db) -> dict[str, Any]:
    """앱 인증 만료 상태(남은 일수 포함)."""
    from foms.services.integrations.naver_commerce import app_expiry

    expires_on = app_expiry.read_expiry_date(db)
    if expires_on is None:
        return {"expires_on": None, "days_left": None}
    return {
        "expires_on": expires_on.strftime("%Y-%m-%d"),
        "days_left": (expires_on - datetime.date.today()).days,
    }


def _link_rows(db, *, status: Optional[str], page: int) -> tuple[list[dict], int]:
    """수집 이력 페이지와 전체 건수를 준다(주문 조인은 필요한 것만)."""
    query = db.query(ExternalOrderLink).filter(ExternalOrderLink.channel == "NAVER")
    if status in VALID_STATUSES:
        query = query.filter(ExternalOrderLink.sync_status == status)
    total = query.count()
    links = (
        query.order_by(ExternalOrderLink.created_at.desc(), ExternalOrderLink.id.desc())
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
        .all()
    )
    order_ids = [int(link.order_id) for link in links if link.order_id]
    orders = {}
    if order_ids:
        # N+1 금지 — 한 번에 당겨 dict 로 붙인다.
        orders = {
            order.id: order
            for order in db.query(Order).filter(Order.id.in_(order_ids)).all()
        }
    rows = []
    for link in links:
        order = orders.get(int(link.order_id)) if link.order_id else None
        rows.append({
            "id": link.id,
            "external_id": link.external_id,
            "external_order_no": link.external_order_no,
            "sync_status": link.sync_status,
            "failure_reason": link.failure_reason,
            "created_at": format_datetime_kst(link.created_at),
            "order_id": link.order_id,
            "customer_name": getattr(order, "customer_name", None),
            "product": getattr(order, "product", None),
        })
    return (rows, total)


@admin_bp.route("/admin/naver-ingest")
@login_required
@role_required(["ADMIN"])
def naver_ingest_dashboard():
    """수집 이력·워터마크·만료일을 한 화면에 보여준다(읽기 전용)."""
    db = get_db()
    status = (request.args.get("status") or "").strip().upper()
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1

    rows, total = _link_rows(db, status=status if status in VALID_STATUSES else None, page=page)
    counts = {
        name: db.query(ExternalOrderLink)
        .filter(ExternalOrderLink.channel == "NAVER",
                ExternalOrderLink.sync_status == name)
        .count()
        for name in VALID_STATUSES
    }
    return render_template(
        "admin/naver_ingest.html",
        rows=rows,
        total=total,
        page=page,
        page_size=PAGE_SIZE,
        status=status if status in VALID_STATUSES else "",
        counts=counts,
        watermark=_watermark_view(db),
        expiry=_expiry_view(db),
    )


@admin_bp.route("/admin/naver-ingest/<int:link_id>/snapshot")
@login_required
@role_required(["ADMIN"])
def naver_ingest_snapshot(link_id: int):
    """채널 원본 응답을 그대로 보여준다(**관리자 전용**).

    실번호·주소가 그대로 들어 있는 개인정보 덩어리라 열람 자체를 감사 원장에 남긴다.
    매핑을 고친 뒤 무엇이 잘못 들어왔는지 대조하는 것이 이 화면의 용도다.
    """
    db = get_db()
    link = (
        db.query(ExternalOrderLink)
        .filter(ExternalOrderLink.id == link_id, ExternalOrderLink.channel == "NAVER")
        .first()
    )
    if link is None:
        return jsonify({"success": False, "data": None, "error": "수집 이력을 찾을 수 없습니다."}), 404
    log_access(
        f"네이버 수집 원본 스냅샷 열람 (link {link_id})",
        action="NAVER_INGEST_SNAPSHOT_VIEW",
        detail={"link_id": link_id, "external_id": link.external_id},
    )
    return jsonify({
        "success": True,
        "data": {
            "external_id": link.external_id,
            "sync_status": link.sync_status,
            "failure_reason": link.failure_reason,
            "snapshot": link.raw_snapshot,
        },
        "error": None,
    })


@admin_bp.route("/admin/naver-ingest/run", methods=["POST"])
@login_required
@role_required(["ADMIN"])
def naver_ingest_run_now():
    """"지금 수집" — rq 큐에 넣기만 한다(네이버 HTTP 는 WORKER 몫).

    큐가 없으면(REDIS_URL 미설정) 조용히 성공한 척하지 않고 실패를 알린다. 여기서 직접
    HTTP 를 내면 IP 가 달라 차단되므로 폴백은 존재하지 않는다.
    """
    queued = enqueue_naver_order_sync(dry_run=False)
    log_access(
        "네이버 주문 수집 수동 실행" + ("" if queued else " 실패(큐 없음)"),
        action="NAVER_INGEST_RUN_NOW",
        detail={"queued": bool(queued)},
    )
    if not queued:
        return jsonify({
            "success": False,
            "error": "작업 큐에 넣지 못했습니다(REDIS_URL 미설정 또는 큐 장애). "
                     "네이버 호출은 WORKER 에서만 가능하므로 web 직접 실행은 없습니다.",
        }), 503
    return jsonify({"success": True, "data": {"queued": True}, "error": None})


__all__ = [
    "naver_ingest_dashboard",
    "naver_ingest_run_now",
    "naver_ingest_snapshot",
    "PAGE_SIZE",
    "VALID_STATUSES",
]
