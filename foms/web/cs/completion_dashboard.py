"""
시공 완료 대시보드 (Construction Completion Dashboard) — canonical page owner.

계획서: docs/plans/2026-03-02-construction-completion-dashboard-plan.md
- 시공 완료·AS 접수 건의 사진 리뷰 및 비용 청구/정산 거점.
"""
from flask import Blueprint, g, make_response, render_template, request
from db import get_db
from foms.web.auth import login_required
from foms.services.common.erp_mine_filter import erp_mine_only_for_construction
from foms.services.common.erp_shell_http import apply_erp_shell_fragment_headers, wants_erp_shell_tab_body
from foms.services.erp_display import (
    _ensure_dict,
    erp_deposit_amount_from_structured,
    erp_shipping_price_from_structured,
)
from foms.services.feature_flags import is_mobile_v2_shell, resolve_shell_variant_cached
from foms.services.request_utils import get_search_query_arg

erp_completion_page_bp = Blueprint(
    'erp_completion_page',
    __name__,
    url_prefix='/erp',
)


def _format_krw(value: int | None) -> str:
    """원화 금액을 콤마 3자리 문자열로 포맷한다(None → em dash)."""
    if value is None:
        return "—"
    return f"{value:,}"


def _build_tablet_completion_rows(orders: list) -> list[dict]:
    """태블릿 가로 금액 그리드용 행 dict 리스트를 구성한다.

    출고가/예약금은 erp_display SSOT 헬퍼로 **이미 로드된** structured_data 에서
    파생한다(신규 쿼리·N+1 없음). 잔금 = 출고가 − 예약금(불변식, 예약금 미기입=0).
    금액은 콤마 포맷 문자열로 1회 파생(셀에서 재파싱 금지).

    Args:
        orders: 완료 큐 Order 목록(structured_data 로드됨).

    Returns:
        그리드 렌더용 dict 리스트(완료일·고객·제품·금액 3종·현금영수증·정산상태).
    """
    rows: list[dict] = []
    for order in orders:
        sd = _ensure_dict(order.structured_data)
        completion_date = ((sd.get("schedule") or {}).get("construction") or {}).get("date")
        parties = sd.get("parties") or {}
        customer_name = (
            (parties.get("customer") or {}).get("name")
            or getattr(order, "customer_name", None)
            or "-"
        )
        items = sd.get("items") or []
        product_summary = ", ".join(
            str((item.get("product_name") or "").strip())
            for item in items
            if isinstance(item, dict) and (item.get("product_name") or "").strip()
        )[:80] or "-"
        shipping_price = erp_shipping_price_from_structured(sd)
        deposit = erp_deposit_amount_from_structured(sd)
        balance = None if shipping_price is None else shipping_price - (deposit or 0)
        payment = sd.get("payment")
        cash_receipt = (
            str(payment.get("cash_receipt") or "").strip()
            if isinstance(payment, dict) else ""
        )
        settlement = sd.get("settlement")
        settlement_issued = bool(
            isinstance(settlement, dict) and settlement.get("deductions")
        )
        rows.append({
            "id": order.id,
            "completion_date": completion_date,
            "customer_name": customer_name,
            "product_summary": product_summary,
            "shipping_price_display": _format_krw(shipping_price),
            "deposit_display": _format_krw(deposit),
            "balance_display": _format_krw(balance),
            "cash_receipt": cash_receipt,
            "settlement_issued": settlement_issued,
        })
    return rows


@erp_completion_page_bp.route('/completion')
@login_required
def erp_completion_dashboard():
    """시공 완료 대시보드: 완료·AS 건 목록 + 시공 사진 갤러리."""
    user = getattr(g, "current_user", None)
    is_construction_team = bool(user and getattr(user, "team", None) == "CONSTRUCTION")
    erp_mine_only = erp_mine_only_for_construction(request, user)
    search_q = get_search_query_arg("q", "search")
    focus_order_id = request.args.get("focus_order", type=int)

    # 태블릿 가로 금액 그리드(서버 렌더)는 모바일 코호트(v2∪v3)에서만 데이터를 적재한다.
    # PC/legacy 는 기존 클라이언트 사진 리뷰 리스트만 사용하므로 서버 쿼리 추가가 없다.
    # 완료 큐는 사진 리뷰 리스트와 동일한 SSOT 로더로 뽑아(검색·focus·mine 파리티) 금액을
    # 파생한다(_load_completion_orders 는 api 순환 회피 위해 함수-지역 import).
    tablet_completion_rows = None
    shell_variant = resolve_shell_variant_cached(user.id if user else None, request)
    if is_mobile_v2_shell(shell_variant):
        from foms.api.cs.dashboard import _load_completion_orders
        orders = _load_completion_orders(
            get_db(),
            search_q=search_q,
            focus_order_id=focus_order_id,
            current_user=user,
            mine_only=erp_mine_only,
        )
        tablet_completion_rows = _build_tablet_completion_rows(orders)

    template_name = (
        'cs/partials/completion_dashboard_fragment.html'
        if wants_erp_shell_tab_body(request)
        else 'cs/completion_dashboard.html'
    )
    response = make_response(
        render_template(
            template_name,
            erp_sub_nav_active='completion',
            is_construction_team=is_construction_team,
            erp_mine_only=erp_mine_only,
            search_q=search_q,
            focus_order_id=focus_order_id,
            tablet_completion_rows=tablet_completion_rows,
        )
    )
    apply_erp_shell_fragment_headers(response, request)
    return response
