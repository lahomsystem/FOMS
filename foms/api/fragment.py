"""HTMX HTML fragments for P1 new surfaces (P2-01). Does not alter erp-shell.js swap flow."""

from __future__ import annotations

from typing import Any

from flask import (
    Blueprint,
    abort,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from db import get_db
from models import Order
from foms.services.erp_order_flags import is_erp_order_record
from foms.services.order_timeline_v3 import load_order_timeline
from foms.services.erp_permissions import can_edit_erp
from foms.services.erp_mobile_order_display import (
    build_mobile_queue_batch_context,
    build_mobile_queue_order_row,
)
from foms.services.feature_flags import (
    is_enabled_for_user,
    is_mobile_v2_shell,
    resolve_shell_variant_cached,
)
from foms.services.order_edit_view_context import build_order_edit_get_context
from foms.services.request_utils import get_preserved_filter_args
from foms.web.auth import get_user_by_id, login_required, role_required

foms_fragment_bp = Blueprint("foms_fragment", __name__, url_prefix="/api/foms/fragment")


def _is_top_level_document_request() -> bool:
    """Return whether this is a top-level browser navigation (not a fetch/XHR/HTMX call).

    Browsers set ``Sec-Fetch-Dest: document`` on address-bar loads, link clicks
    and new-tab/middle-click navigations, but ``empty`` for ``fetch()``/XHR and
    ``htmx.ajax`` requests. When the header is absent (older browsers / non-
    conforming clients) we return ``False`` so fragment consumers keep receiving
    the partial body unchanged (fail-open — the fragment path is preserved).

    Returns:
        True only when ``Sec-Fetch-Dest`` is exactly ``"document"``.
    """
    return request.headers.get("Sec-Fetch-Dest") == "document"


def _order_edit_fragment_response(order_id: int) -> Any:
    """
    Render edit-order body HTML for tablet split HTMX swap.

    Args:
        order_id: Primary key of the order row.

    Returns:
        Flask response with HTML fragment and no-store cache headers.
    """
    db = get_db()
    order = db.query(Order).filter(Order.id == order_id, Order.not_deleted_filter()).first()
    if order is None:
        abort(404)

    user = get_user_by_id(session.get("user_id"))
    if is_erp_order_record(order):
        if not can_edit_erp(user):
            abort(403)

    ctx = build_order_edit_get_context(order, user=user)
    ctx["preserved_args"] = get_preserved_filter_args(request.args)
    uid = session.get("user_id")
    mobile_v2 = is_mobile_v2_shell(resolve_shell_variant_cached(uid))
    split_v2 = mobile_v2 and is_enabled_for_user(
        "FOMS_TABLET_SPLIT_VIEW_ENABLED",
        uid,
        cohort_key="FOMS_V3_SHELL_COHORT",
    )
    if split_v2:
        # 단건 상세라도 build_mobile_queue_order_row는 첨부 카운트/미리보기/타임라인/담당자를
        # 주문별 단건 조회(행당 ~5쿼리)로 해소한다. shipment/measurement 큐와 동일하게 batch_ctx를
        # 선행 생성해 고정 수 쿼리로 묶는다(N+1 가드 mobile-queue-row-no-batch 준수).
        _batch_ctx = build_mobile_queue_batch_context(db, [order])
        ctx["mobile_order_row"] = build_mobile_queue_order_row(db, order, user, batch_ctx=_batch_ctx)
        template = "orders/partials/order_detail_split_panel.html"
    else:
        template = "partials/shared/foms_order_detail_fragment.html"
    body = render_template(
        template,
        **ctx,
    )
    response = make_response(body)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-FOMS-Fragment"] = "1"
    return response


@foms_fragment_bp.route("/order/<int:order_id>/edit", methods=["GET"])
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def order_edit_fragment(order_id: int) -> Any:
    """HTMX fragment: order edit body for tablet split-view detail pane.

    Deep defense (W15): a direct browser navigation to this fragment URL — a
    new-tab / middle-click on a master card, or an HTMX-miss fallback — would
    otherwise render an unstyled partial document. When ``Sec-Fetch-Dest`` marks
    a top-level document request, redirect to the canonical full edit page
    (preserving query args such as ``open=erp-order``). fetch/XHR/HTMX consumers
    (``Sec-Fetch-Dest: empty``, or the header absent on older browsers) still
    receive the fragment body unchanged.

    Args:
        order_id: Primary key of the order row.

    Returns:
        302 redirect to the full edit page for top-level document navigations,
        otherwise the HTML fragment response.
    """
    if _is_top_level_document_request():
        return redirect(
            url_for("order_edit.edit_order", order_id=order_id, **request.args.to_dict())
        )
    return _order_edit_fragment_response(order_id)


@foms_fragment_bp.route("/order/<int:order_id>/timeline", methods=["GET"])
@login_required
def order_timeline_fragment(order_id: int) -> Any:
    """주문 360° 8단계 타임라인 fragment (FOMS Field OS v3 · 읽기 전용).

    로그인 사용자면 누구나 조회 가능(기존 erp_order_mobile_detail·events.py의
    주문 열람 계약과 동일). ERP 주문·미삭제 건이 아니면 404. 이벤트/생성자
    조회는 load_order_timeline(단일 쿼리+배치 조회, N+1 없음)으로 공용화됐다.

    Args:
        order_id: 주문 PK.

    Returns:
        타임라인 HTML fragment 응답(no-store, X-FOMS-Fragment).
    """
    db = get_db()
    order = (
        db.query(Order)
        .filter(Order.id == order_id, Order.is_erp_order.is_(True), Order.not_deleted_filter())
        .first()
    )
    if order is None:
        abort(404)

    timeline = load_order_timeline(db, order)
    body = render_template("partials/v3/persona_order360.html", timeline=timeline)
    response = make_response(body)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-FOMS-Fragment"] = "1"
    return response
