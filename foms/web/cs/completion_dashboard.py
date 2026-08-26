"""
시공 완료 대시보드 (Construction Completion Dashboard) — canonical page owner.

계획서: docs/plans/2026-03-02-construction-completion-dashboard-plan.md
- 시공 완료·AS 접수 건의 사진 리뷰 및 비용 청구/정산 거점.
- 태블릿 가로 코호트(v2∪v3): 사진 리뷰 리스트 대신 금액 그리드 + KPI + 기간/정산
  필터 + 정산 사이드 시트 + CSV 내보내기(목업 v8 P9, spec W17/T2 완료 프레임).
"""
import csv
import io

from flask import Blueprint, g, make_response, render_template, request, url_for
from db import get_db
from foms.api.files import build_file_view_url
from foms.web.auth import login_required
from foms.services.common.erp_mine_filter import erp_mine_only_for_construction
from foms.services.common.erp_shell_http import apply_erp_shell_fragment_headers, wants_erp_shell_tab_body
from foms.services.datetime_kst import get_today_kst
from foms.services.erp_display import (
    _ensure_dict,
    erp_deposit_amount_from_structured,
    erp_shipping_price_from_structured,
)
from foms.services.estimate_service import (
    _balance_after_payments,
    _overpaid_after_payments,
)
from foms.services.feature_flags import is_mobile_v2_shell, resolve_shell_variant_cached
from foms.services.request_utils import get_search_query_arg
from models import Order, OrderAttachment

erp_completion_page_bp = Blueprint(
    'erp_completion_page',
    __name__,
    url_prefix='/erp',
)

# 정산 비용 청구 폼 귀속 부서 옵션(코드, 라벨). API SETTLEMENT_DEPARTMENTS 와 정합.
SETTLEMENT_DEPARTMENT_OPTIONS = [
    ("SALES", "영업"),
    ("DRAWING", "도면"),
    ("PRODUCTION", "공장(생산)"),
    ("CONSTRUCTION", "시공팀"),
    ("CUSTOMER", "고객"),
]


def _format_krw(value: int | None) -> str:
    """원화 금액을 콤마 3자리 문자열로 포맷한다(None → em dash)."""
    if value is None:
        return "—"
    return f"{value:,}"


def _completion_month_key(completion_date: str | None) -> str:
    """완료일 문자열에서 월 키("YYYY-MM")를 파생한다.

    Args:
        completion_date: "YYYY-MM-DD" 문자열 또는 None(비-ISO/빈값 방어).

    Returns:
        앞 7자 "YYYY-MM", 파생 불가 시 빈 문자열.
    """
    if not completion_date or not isinstance(completion_date, str):
        return ""
    text = completion_date.strip()
    if len(text) < 7 or text[4] != "-":
        return ""
    return text[:7]


def _completion_md(completion_date: str | None) -> str:
    """완료일("YYYY-MM-DD") → "M/D"(zero-pad 없음), 파생 불가 시 "-"."""
    if not completion_date or not isinstance(completion_date, str):
        return "-"
    parts = completion_date.strip().split("-")
    if len(parts) != 3 or not (parts[1].isdigit() and parts[2].isdigit()):
        return "-"
    return f"{int(parts[1])}/{int(parts[2])}"


def _completion_period_label(period: str) -> str:
    """기간 코드("YYYY-MM")를 표시 라벨("{월}월")로 변환(빈값/비정상=전체)."""
    if not period or "-" not in period:
        return "전체"
    month_part = period.split("-", 1)[1]
    if not month_part.isdigit():
        return "전체"
    return f"{int(month_part)}월"


def _cash_receipt_issued(settlement: dict | None) -> bool:
    """정산 blob에서 현금영수증 발행 여부를 파생한다.

    발행 기록은 ``settlement.cash_receipt = {issued: True, ...}`` (cash-receipt/issue API).

    Args:
        settlement: sd["settlement"] dict 또는 None.

    Returns:
        발행 완료면 True.
    """
    if not isinstance(settlement, dict):
        return False
    cr = settlement.get("cash_receipt")
    return bool(isinstance(cr, dict) and cr.get("issued"))


def _cash_receipt_state(cash_receipt_text: str, issued: bool) -> str:
    """현금영수증 상태를 파생한다: 'issued' > 'requested' > 'none'.

    발행 기록(settlement.cash_receipt.issued)이 있으면 'issued', 없고 요청 자유텍스트
    (payment.cash_receipt)가 있으면 'requested', 둘 다 없으면 'none'.

    Args:
        cash_receipt_text: payment.cash_receipt 요청 자유텍스트(strip 완료).
        issued: 발행 완료 여부(_cash_receipt_issued).

    Returns:
        "issued" | "requested" | "none".
    """
    if issued:
        return "issued"
    if cash_receipt_text:
        return "requested"
    return "none"


def _completion_row(order) -> dict:
    """단일 완료 큐 Order → 태블릿 금액 그리드 행 dict.

    출고가/예약금은 erp_display SSOT 헬퍼로 **이미 로드된** structured_data 에서
    파생한다(신규 쿼리·N+1 없음). 잔금 = max(0, 출고가 − 예약금)(예약금 미기입=0).
    금액은 콤마 포맷 문자열로 1회 파생(셀에서 재파싱 금지). balance_amount 는 KPI 합산
    전용(미표시), month_key 는 기간 필터/집계 전용.

    Args:
        order: 완료 큐 Order(structured_data 로드됨).

    Returns:
        그리드·KPI 렌더용 dict.
    """
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
    # 잔금 = max(0, 출고가 − 예약금). 클램프 규칙의 정본은 서버 파생식
    # (orders/structured_form_projection.recompute_totals)이고, 그 식과 **같은 값**을 내는
    # _balance_after_payments 를 쓴다(erp_mobile_order_display 도 같은 헬퍼). 표면마다
    # 새 식을 쓰면 같은 주문의 잔금이 화면마다 갈린다.
    balance = (
        None
        if shipping_price is None
        else _balance_after_payments(shipping_price, deposit or 0)
    )
    # 잔금은 0 에서 잘린다 — 넘친 금액은 그 클램프가 삼킨다. 돌려줄 돈이 있다는 사실이
    # 화면에서 사라지지 않게 넘친 만큼을 따로 낸다(CEO L-1). 0 이면 화면은 줄을 안 낸다.
    overpaid = (
        0
        if shipping_price is None
        else _overpaid_after_payments(shipping_price, deposit or 0)
    )
    payment = sd.get("payment")
    cash_receipt = (
        str(payment.get("cash_receipt") or "").strip()
        if isinstance(payment, dict) else ""
    )
    paid = bool(isinstance(payment, dict) and payment.get("balance_confirmed"))
    settlement = sd.get("settlement")
    settlement_issued = bool(
        isinstance(settlement, dict) and settlement.get("deductions")
    )
    cash_receipt_issued = _cash_receipt_issued(settlement)
    return {
        "id": order.id,
        "status": order.status,
        "is_as": order.status in ("AS_RECEIVED", "AS_COMPLETED"),
        "completion_date": completion_date,
        "month_key": _completion_month_key(completion_date),
        "customer_name": customer_name,
        "product_summary": product_summary,
        "shipping_price_display": _format_krw(shipping_price),
        "deposit_display": _format_krw(deposit),
        "balance_display": _format_krw(balance),
        "balance_amount": balance,
        "overpaid_display": _format_krw(overpaid) if overpaid else "",
        "cash_receipt": cash_receipt,
        "cash_receipt_state": _cash_receipt_state(cash_receipt, cash_receipt_issued),
        "cash_receipt_issued": cash_receipt_issued,
        "paid": paid,
        "settlement_issued": settlement_issued,
    }


def _build_tablet_completion_rows(orders: list) -> list[dict]:
    """완료 큐 Order 목록 → 태블릿 금액 그리드 행 dict 리스트(신규 쿼리 없음).

    Args:
        orders: 완료 큐 Order 목록(structured_data 로드됨).

    Returns:
        _completion_row 로 파생한 행 dict 리스트.
    """
    return [_completion_row(order) for order in orders]


def _build_completion_period_options(rows: list[dict]) -> list[dict]:
    """행 목록에 존재하는 완료 월을 내림차순 옵션 리스트로 만든다.

    Args:
        rows: 태블릿 완료 행 dict 리스트(month_key 포함).

    Returns:
        [{"value": "YYYY-MM", "label": "{년}년 {월}월"}] 내림차순.
    """
    keys = sorted(
        {row.get("month_key") for row in rows if row.get("month_key")},
        reverse=True,
    )
    options: list[dict] = []
    for key in keys:
        year, month = key.split("-")
        options.append({"value": key, "label": f"{int(year)}년 {int(month)}월"})
    return options


def _compute_completion_kpis(rows: list[dict], today) -> dict:
    """작업 세트(AS 토글 후·기간/정산 필터 전) KPI 집계.

    Args:
        rows: 태블릿 완료 행 dict 리스트(작업 세트).
        today: KST 오늘 date(get_today_kst()).

    Returns:
        this_month/pending/unpaid_total(+display)/cash_receipt_requests dict.
    """
    this_month_key = f"{today.year:04d}-{today.month:02d}"
    this_month = pending = unpaid_total = cash_receipt_requests = 0
    for row in rows:
        if row.get("month_key") == this_month_key:
            this_month += 1
        if not row.get("settlement_issued"):
            pending += 1
        balance = row.get("balance_amount")
        if not row.get("paid") and isinstance(balance, int) and balance > 0:
            unpaid_total += balance
        if row.get("cash_receipt_state") == "requested":
            cash_receipt_requests += 1
    return {
        "this_month": this_month,
        "pending": pending,
        "unpaid_total": unpaid_total,
        "unpaid_total_display": f"{unpaid_total:,}",
        "cash_receipt_requests": cash_receipt_requests,
    }


def _filter_completion_rows(rows: list[dict], *, period: str, settlement: str) -> list[dict]:
    """기간(월)·정산 상태로 완료 행을 필터한다.

    Args:
        rows: 작업 세트 행 리스트.
        period: "" 이면 전체, 아니면 month_key == period 만.
        settlement: "" 전체 / "pending" 미청구 / "issued" 청구완료.

    Returns:
        필터된 행 리스트.
    """
    result = rows
    if period:
        result = [row for row in result if row.get("month_key") == period]
    if settlement == "pending":
        result = [row for row in result if not row.get("settlement_issued")]
    elif settlement == "issued":
        result = [row for row in result if row.get("settlement_issued")]
    return result


def _paginate(rows: list[dict], page: int, per_page: int = 60) -> tuple[list[dict], dict]:
    """행 리스트를 페이지네이션한다(페이지 [1, total_pages] 클램프).

    Args:
        rows: 필터된 행 리스트.
        page: 요청 페이지(1-base).
        per_page: 페이지당 행 수(기본 60, perf 상한).

    Returns:
        (page_rows, page_meta). total_pages 는 빈 결과라도 최소 1.
    """
    total_count = len(rows)
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    page_rows = rows[start:start + per_page]
    page_meta = {
        "page": page,
        "total_pages": total_pages,
        "total_count": total_count,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "per_page": per_page,
    }
    return page_rows, page_meta


def _completion_query_params() -> dict:
    """완료 대시보드/내보내기 공용 쿼리 파라미터 파싱.

    Returns:
        q/period/settlement/page/as_include dict. as_include: fbar 미존재=기본 ON,
        존재 시 as_include=='1' 만 ON(필터 바가 hidden fbar=1 을 함께 전송).
    """
    fbar = request.args.get("fbar")
    as_include = True if fbar is None else (request.args.get("as_include") == "1")
    return {
        "q": get_search_query_arg("q", "search"),
        "period": request.args.get("period", ""),
        "settlement": request.args.get("settlement", ""),
        "page": request.args.get("page", 1, type=int),
        "as_include": as_include,
    }


def _completion_working_and_filtered(user, params: dict) -> tuple[list[dict], list[dict]]:
    """완료 큐 로드 → 행 빌드 → AS 토글 → 기간/정산 필터(대시보드·CSV 공용 SSOT).

    로드는 사진 리뷰 리스트와 동일 SSOT 로더(_load_completion_orders)로 뽑아 검색·focus·
    mine 파리티를 유지한다(api 순환 회피 위해 함수-지역 import). AS 토글 OFF 면 AS 완료건
    (AS_COMPLETED)만 작업 세트에서 제외한다.

    Args:
        user: 로그인 사용자(mine 필터·로더용).
        params: _completion_query_params() 결과.

    Returns:
        (working_set, filtered). working_set = AS 토글 후·기간/정산 필터 전.
    """
    from foms.api.cs.dashboard import _load_completion_orders
    erp_mine_only = erp_mine_only_for_construction(request, user)
    focus_order_id = request.args.get("focus_order", type=int)
    orders = _load_completion_orders(
        get_db(),
        search_q=params["q"],
        focus_order_id=focus_order_id,
        current_user=user,
        mine_only=erp_mine_only,
    )
    rows = _build_tablet_completion_rows(orders)
    if not params["as_include"]:
        rows = [row for row in rows if row["status"] != "AS_COMPLETED"]
    filtered = _filter_completion_rows(
        rows, period=params["period"], settlement=params["settlement"]
    )
    return rows, filtered


def _build_completion_cohort_context(user, search_q: str) -> tuple[list[dict], dict]:
    """모바일 코호트(v2∪v3) 태블릿 완료 그리드 컨텍스트(행 + 메타) 구성.

    Args:
        user: 로그인 사용자.
        search_q: 검색어(메타 표시·export_url 보존용).

    Returns:
        (tablet_completion_rows, tablet_completion_meta).
    """
    params = _completion_query_params()
    working_set, filtered = _completion_working_and_filtered(user, params)
    kpis = _compute_completion_kpis(working_set, get_today_kst())
    period_options = _build_completion_period_options(working_set)
    page_rows, page_meta = _paginate(filtered, params["page"])
    export_url = url_for(
        'erp_completion_page.erp_completion_export',
        q=search_q or None,
        period=params["period"] or None,
        settlement=params["settlement"] or None,
        as_include=('1' if params["as_include"] else '0'),
        fbar='1',
    )
    meta = {
        "kpis": kpis,
        "filters": {
            "q": search_q or "",
            "period": params["period"],
            "period_options": period_options,
            "settlement": params["settlement"],
            "as_include": params["as_include"],
        },
        "page": {**page_meta, "period_label": _completion_period_label(params["period"])},
        "export_url": export_url,
    }
    return page_rows, meta


def _completion_construction_photos(db, order_id: int) -> list[dict]:
    """주문의 시공(category=construction) 사진을 단일 쿼리로 로드한다(N+1 없음).

    Args:
        db: DB 세션.
        order_id: 주문 PK.

    Returns:
        [{"view_url", "filename"}] (storage_key 빈 항목 제외, 생성순).
    """
    atts = (
        db.query(OrderAttachment)
        .filter(
            OrderAttachment.order_id == order_id,
            OrderAttachment.category == "construction",
        )
        .order_by(OrderAttachment.created_at.asc())
        .all()
    )
    photos: list[dict] = []
    for att in atts:
        if not att.storage_key:
            continue
        photos.append({
            "view_url": build_file_view_url(att.storage_key),
            "filename": att.filename,
        })
    return photos


def _completion_settlement_memo(settlement: dict | None) -> list[dict]:
    """정산 deductions → 시트 표시용 메모 리스트.

    Args:
        settlement: sd["settlement"] dict 또는 None.

    Returns:
        [{department, amount_display, reason, created_by}] 리스트(음수 콤마 포맷).
    """
    if not isinstance(settlement, dict):
        return []
    deductions = settlement.get("deductions")
    if not isinstance(deductions, list):
        return []
    memo: list[dict] = []
    for ded in deductions:
        if not isinstance(ded, dict):
            continue
        amount = ded.get("amount")
        memo.append({
            "department": ded.get("department") or "-",
            "amount_display": _format_krw(amount) if isinstance(amount, int) else "—",
            "reason": ded.get("reason") or "",
            "created_by": ded.get("created_by") or "-",
        })
    return memo


def _completion_sheet_context(db, order, user) -> dict:
    """완료 정산 시트 fragment 렌더 컨텍스트(단건).

    잔금 = max(0, 출고가 − 예약금). 금액은 _format_krw 로 1회 파생.

    Args:
        db: DB 세션.
        order: 완료 큐 Order.
        user: 로그인 사용자(시공팀 판정).

    Returns:
        tablet_completion_sheet.html 렌더 컨텍스트 dict.
    """
    sd = _ensure_dict(order.structured_data)
    completion_date = ((sd.get("schedule") or {}).get("construction") or {}).get("date")
    parties = sd.get("parties") or {}
    customer_name = (
        (parties.get("customer") or {}).get("name")
        or getattr(order, "customer_name", None) or "-"
    )
    shipping_price = erp_shipping_price_from_structured(sd)
    deposit = erp_deposit_amount_from_structured(sd)
    # 잔금 = max(0, 출고가 − 예약금). 클램프 규칙의 정본은 서버 파생식
    # (orders/structured_form_projection.recompute_totals)이고, 그 식과 **같은 값**을 내는
    # _balance_after_payments 를 쓴다(erp_mobile_order_display 도 같은 헬퍼). 표면마다
    # 새 식을 쓰면 같은 주문의 잔금이 화면마다 갈린다.
    balance = (
        None
        if shipping_price is None
        else _balance_after_payments(shipping_price, deposit or 0)
    )
    # 목록 행과 같은 규칙 — 잔금 클램프가 삼킨 과입금을 시트에서도 말한다(CEO L-1).
    overpaid = (
        0
        if shipping_price is None
        else _overpaid_after_payments(shipping_price, deposit or 0)
    )
    payment = sd.get("payment")
    cash_receipt = (
        str(payment.get("cash_receipt") or "").strip()
        if isinstance(payment, dict) else ""
    )
    settlement = sd.get("settlement")
    cash_receipt_issued = _cash_receipt_issued(settlement)
    cash_receipt_note = ""
    if cash_receipt_issued:
        cr = settlement.get("cash_receipt") if isinstance(settlement, dict) else None
        if isinstance(cr, dict):
            cash_receipt_note = str(cr.get("note") or "").strip()
    return {
        "order_id": order.id,
        "customer_name": customer_name,
        "completion_md": _completion_md(completion_date),
        "shipping_price_display": _format_krw(shipping_price),
        "deposit_display": _format_krw(deposit),
        "balance_display": _format_krw(balance),
        "overpaid_display": _format_krw(overpaid) if overpaid else "",
        "cash_receipt": cash_receipt,
        "cash_receipt_issued": cash_receipt_issued,
        "cash_receipt_note": cash_receipt_note,
        "settlement_issued": bool(
            isinstance(settlement, dict) and settlement.get("deductions")
        ),
        "settlement_memo": _completion_settlement_memo(settlement),
        "construction_photos": _completion_construction_photos(db, order.id),
        "is_construction_team": bool(
            user and getattr(user, "team", None) == "CONSTRUCTION"
        ),
        "department_options": SETTLEMENT_DEPARTMENT_OPTIONS,
    }


@erp_completion_page_bp.route('/completion')
@login_required
def erp_completion_dashboard():
    """시공 완료 대시보드: 완료·AS 건 목록 + 시공 사진 갤러리.

    태블릿 금액 그리드(서버 렌더)는 모바일 코호트(v2∪v3)에서만 데이터를 적재한다
    (PC/legacy 는 기존 클라이언트 사진 리뷰 리스트만 사용 — 서버 쿼리 추가 없음).
    """
    user = getattr(g, "current_user", None)
    is_construction_team = bool(user and getattr(user, "team", None) == "CONSTRUCTION")
    erp_mine_only = erp_mine_only_for_construction(request, user)
    search_q = get_search_query_arg("q", "search")
    focus_order_id = request.args.get("focus_order", type=int)

    tablet_completion_rows = None
    tablet_completion_meta = None
    shell_variant = resolve_shell_variant_cached(user.id if user else None, request)
    if is_mobile_v2_shell(shell_variant):
        tablet_completion_rows, tablet_completion_meta = _build_completion_cohort_context(
            user, search_q
        )

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
            tablet_completion_meta=tablet_completion_meta,
        )
    )
    apply_erp_shell_fragment_headers(response, request)
    return response


@erp_completion_page_bp.route('/completion/tablet-sheet/<int:order_id>')
@login_required
def erp_completion_tablet_sheet(order_id: int):
    """태블릿 완료 그리드 행 탭 → 우측 시트 주입용 정산 상세 fragment(raw HTML).

    셸 헤더·JSON 없이 순수 HTML 조각만 반환. 단건 조회 + 시공사진 단일 쿼리(N+1 없음).
    """
    db = get_db()
    order = db.query(Order).filter(Order.id == order_id, Order.active_filter()).first()
    if not order:
        return ("주문을 찾을 수 없습니다.", 404)
    user = getattr(g, "current_user", None)
    return render_template(
        'cs/partials/tablet_completion_sheet.html',
        **_completion_sheet_context(db, order, user),
    )


@erp_completion_page_bp.route('/completion/export.csv')
@login_required
def erp_completion_export():
    """완료 그리드 현재 필터(q/period/settlement/as_include)의 CSV 내보내기(UTF-8 BOM).

    대시보드 코호트 분기와 동일 load+build+AS-toggle+filter 파이프라인을 재사용한다
    (_completion_working_and_filtered SSOT). 페이지네이션 없이 필터 전체를 내보낸다.
    """
    user = getattr(g, "current_user", None)
    _working, filtered = _completion_working_and_filtered(user, _completion_query_params())
    output = io.StringIO()
    output.write("﻿")  # UTF-8 BOM: Excel 한글 정상 인식
    writer = csv.writer(output)
    writer.writerow(["완료일", "고객", "제품", "출고가", "예약금", "잔금", "현금영수증", "정산상태"])
    for row in filtered:
        completion = row.get("completion_date") or "-"
        if row.get("is_as"):
            completion = f"{completion} (AS)"
        writer.writerow([
            completion,
            row.get("customer_name") or "-",
            row.get("product_summary") or "-",
            row.get("shipping_price_display") or "—",
            row.get("deposit_display") or "—",
            row.get("balance_display") or "—",
            row.get("cash_receipt") or "",
            "완료" if row.get("settlement_issued") else "대기",
        ])
    filename = f"completion_{get_today_kst().strftime('%Y%m%d')}.csv"
    resp = make_response(output.getvalue())
    resp.mimetype = "text/csv"
    resp.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return resp
