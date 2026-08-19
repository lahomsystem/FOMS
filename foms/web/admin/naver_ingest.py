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
import logging
from typing import Any, Optional

from flask import jsonify, render_template, request, session, url_for

from db import get_db
from foms.services.datetime_kst import format_datetime_kst, now_utc_naive
from foms.services.integrations.naver_commerce.order_candidates import find_order_candidates
from foms.services.integrations.naver_commerce.promotion import summarize_snapshot
from foms.services.jobs.queue import enqueue_naver_order_sync
from foms.web.admin.routes import admin_bp
from foms.web.auth import log_access, login_required, role_required
from models import ExternalOrderLink, Order

logger = logging.getLogger(__name__)

#: 한 페이지에 보여줄 수집 이력 행 수(관리자 cold path 라 페이지네이션으로 충분).
PAGE_SIZE = 50

#: 트리아지 큐가 한 번에 읽는 링크 수. 한 집이 상품주문 여러 건으로 오므로 묶음 PAGE_SIZE
#: 개를 채우려면 링크는 그보다 많이 필요하다(실측 평균 3건/집, 여유 배수 5).
QUEUE_LINK_FETCH_LIMIT = PAGE_SIZE * 5

#: 상태 필터 닫힌집합. 임의 문자열이 그대로 쿼리에 들어가지 않게 한다.
VALID_STATUSES = ("COLLECTED", "LINKED", "PENDING_REVIEW", "FAILED")

#: 발주확인이 끝난 것으로 보는 컬럼 값(mapping.CONFIRMED_PLACE_STATUSES 와 같은 집합).
#: 이 값이 아니면 전부 "아직"이다 — NULL(모름)도 아직으로 본다(놓치는 쪽보다 낫다).
CONFIRMED_PLACE_VALUES = ("OK",)


def order_has_spec_rows(order: Any) -> bool:
    """주문에 규격표가 한 행이라도 입력됐는지 (CS 완료 판정용).

    규격 SSOT 는 ``structured_data['items'][*]['spec_rows']`` 다(품목 안에 있다 —
    최상위 ``spec_rows`` 를 보면 항상 비어 있는 것으로 잘못 읽는다).

    Args:
        order: :class:`models.Order` 또는 None.

    Returns:
        규격 행이 하나라도 있으면 True.
    """
    data = getattr(order, "structured_data", None)
    if not isinstance(data, dict):
        return False
    items = data.get("items")
    if not isinstance(items, list):
        return False
    for item in items:
        rows = item.get("spec_rows") if isinstance(item, dict) else None
        if isinstance(rows, list) and rows:
            return True
    return False


def _payment_summary(raw_snapshot: Any) -> dict[str, Any]:
    """이력 표에 실을 결제 요약(결제일·수단·할인 합계).

    Args:
        raw_snapshot: ``ExternalOrderLink.raw_snapshot``.

    Returns:
        ``{"paid_at", "means", "discount"}`` — 원본이 없으면 빈 값.
    """
    from foms.services.integrations.naver_commerce.mapping import build_payment_info

    if not isinstance(raw_snapshot, dict) or not raw_snapshot:
        return {"paid_at": "", "means": "", "discount": 0}
    payment = build_payment_info(raw_snapshot)
    discount = payment["product_discount_amount"] + sum(
        coupon["discount_amount"] for coupon in payment["coupons"])
    return {"paid_at": payment["paid_at"][:16], "means": payment["means"],
            "discount": discount}


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


def _history_group_key(link: ExternalOrderLink) -> str:
    """이력 표의 페이지·묶음 키 — 네이버 주문번호(없으면 링크 단독).

    확인 화면(:func:`_group_queue`)은 분할배송까지 갈라내는 세밀한 키를 쓰지만, 이력은
    **페이지 경계에서 한 집이 쪼개지지 않는 것**이 목적이라 SQL 로 셀 수 있는 주문번호를 쓴다.
    """
    return (link.external_order_no or "").strip() or f"link:{link.id}"


def _group_key_col():
    """이력 표의 묶음 키 SQL 식 — 파이썬 :func:`_history_group_key` 와 같은 규칙.

    총계·상태별 건수·페이지 키가 **모두 같은 식**을 써야 숫자가 갈리지 않는다.

    Returns:
        네이버 주문번호(없으면 ``link:<id>``) 라벨 ``gk`` 컬럼 식.
    """
    from sqlalchemy import String, cast, func, literal

    return func.coalesce(
        func.nullif(ExternalOrderLink.external_order_no, ""),
        literal("link:") + cast(ExternalOrderLink.id, String),
    ).label("gk")


def _status_group_counts(db) -> dict[str, int]:
    """상태별 **묶음 수**를 센다 — 필터 버튼 숫자를 표 총계와 같은 단위로 맞춘다.

    링크 행으로 세면 "전체 36 · 수집됨(주문 전) 102" 처럼 부분이 전체보다 커 보인다
    (2026-08-19 스테이징 실화면). 필터는 "그 상태 링크가 하나라도 있는 집"을 고르므로
    (:func:`_link_rows`), 숫자도 같은 술어로 세야 한다 — ``(묶음키, 상태)`` 쌍을 한 번씩만
    세면 정확히 그 값이다.

    Args:
        db: 요청 스코프 DB 세션.

    Returns:
        ``{상태: 그 상태 링크를 하나 이상 가진 묶음 수}`` (VALID_STATUSES 전 키 포함).
    """
    key_col = _group_key_col()
    pairs = (
        db.query(key_col, ExternalOrderLink.sync_status)
        .filter(ExternalOrderLink.channel == "NAVER")
        .group_by(key_col, ExternalOrderLink.sync_status)
        .all()
    )
    counts = {name: 0 for name in VALID_STATUSES}
    for _key, link_status in pairs:
        if link_status in counts:
            counts[link_status] += 1
    return counts


def _place_pending_clause():
    """'발주확인 전' 조건 — 완료값이 아니거나 아직 모르는(NULL) 링크.

    ``raw_snapshot`` (JSONB) 대신 ``place_order_status`` 컬럼을 본다. JSONB 로 필터하면
    인덱스 없는 스캔이 되고, 그건 이 저장소의 hot path 금지 규칙이다(T16-B).
    """
    from sqlalchemy import or_

    return or_(ExternalOrderLink.place_order_status.is_(None),
               ExternalOrderLink.place_order_status.notin_(CONFIRMED_PLACE_VALUES))


def _place_pending_group_count(db) -> int:
    """'발주확인 전' 묶음 수 — 필터 버튼 숫자(다른 버튼과 같은 집 단위).

    Args:
        db: 요청 스코프 DB 세션.

    Returns:
        발주확인이 아직인 링크를 하나 이상 가진 묶음 수.
    """
    key_col = _group_key_col()
    return (
        db.query(key_col)
        .filter(ExternalOrderLink.channel == "NAVER", _place_pending_clause())
        .group_by(key_col)
        .count()
    )


def _link_rows(db, *, status: Optional[str], page: int,
               place_pending: bool = False) -> tuple[list[dict], int]:
    """수집 이력을 **한 집 = 한 줄**로 묶어 돌려준다(T14-H).

    페이지는 묶음(네이버 주문번호) 단위로 센다 — 상품주문 단위로 자르면 페이지 끝에서 한
    집의 일부만 보인다. 상태 필터는 **묶음 선정에만** 쓰고, 뽑힌 묶음의 상품주문은 상태와
    무관하게 전부 싣는다(2026-08-18 사용자 확정: "해당 줄이 하나라도 있으면 보이기" —
    문제가 어느 집에서 났는지 맥락까지 보여야 한다).

    Returns:
        ``(묶음 목록, 묶음 총 개수)``.
    """
    from sqlalchemy import func

    key_col = _group_key_col()

    key_query = (
        db.query(key_col, func.max(ExternalOrderLink.created_at).label("last_at"))
        .filter(ExternalOrderLink.channel == "NAVER")
    )
    if status in VALID_STATUSES:
        key_query = key_query.filter(ExternalOrderLink.sync_status == status)
    if place_pending:
        # 상태 필터와 같은 규약: "해당 링크가 하나라도 있는 집"을 고른다.
        key_query = key_query.filter(_place_pending_clause())
    key_query = key_query.group_by(key_col)

    total = key_query.count()
    page_keys = [
        row[0] for row in key_query.order_by(func.max(ExternalOrderLink.created_at).desc(),
                                             key_col.desc())
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
        .all()
    ]
    if not page_keys:
        return ([], total)

    links = (
        db.query(ExternalOrderLink)
        .filter(ExternalOrderLink.channel == "NAVER",
                key_col.in_(page_keys))  # perf-ok: 페이지 키 batch(최대 PAGE_SIZE)
        .order_by(ExternalOrderLink.created_at.desc(), ExternalOrderLink.id.desc())
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
    # 같은 네이버 주문번호로 함께 묶일 미생성 건수(사람이 버튼 누르기 전에 알아야 한다).
    pending_group_counts: dict[str, int] = {}
    order_nos = [link.external_order_no for link in links
                 if link.external_order_no and not link.order_id]
    if order_nos:
        from sqlalchemy import func as _func
        rows_group = (
            db.query(ExternalOrderLink.external_order_no, _func.count(ExternalOrderLink.id))
            .filter(ExternalOrderLink.channel == "NAVER",
                    ExternalOrderLink.external_order_no.in_(order_nos),  # perf-ok: 페이지 주문번호 batch
                    ExternalOrderLink.order_id.is_(None))
            .group_by(ExternalOrderLink.external_order_no)
            .all()
        )
        pending_group_counts = {no: int(cnt) for no, cnt in rows_group}

    members: dict[str, list[dict]] = {}
    order_of_key: list[str] = []
    for link in links:
        order = orders.get(int(link.order_id)) if link.order_id else None
        # 주문이 아직 없는 수집분(COLLECTED)은 원본 스냅샷에서 표시값을 뽑는다 —
        # 사람이 무엇을 받았는지 보고 "주문 만들기"를 누를지 판단해야 하기 때문이다.
        summary = summarize_snapshot(link.raw_snapshot)
        key = _history_group_key(link)
        if key not in members:
            members[key] = []
            order_of_key.append(key)
        members[key].append({
            "id": link.id,
            "external_id": link.external_id,
            "external_order_no": link.external_order_no,
            "sync_status": link.sync_status,
            "failure_reason": link.failure_reason,
            "created_at": format_datetime_kst(link.created_at),
            "order_id": link.order_id,
            "customer_name": getattr(order, "customer_name", None) or summary["customer_name"],
            "product": getattr(order, "product", None) or summary["product"],
            "options": summary["options"],
            "quantity": summary["quantity"],
            "amount": summary["amount"],
            "order_date": summary["order_date"],
            "payment": _payment_summary(link.raw_snapshot),
            "claim_label": summary["claim_label"],
            "claim_blocking": summary["claim_blocking"],
            "place_confirmed": summary["place_confirmed"],
            "place_label": summary["place_label"],
            "_order": order,
        })

    rows = []
    for key in order_of_key:
        group = members[key]
        # 대표(본품) = 금액 최대. 0원 구성이 제목이 되면 무슨 주문인지 알 수 없다.
        lead = max(group, key=lambda row: (row["amount"] or 0, -row["id"]))
        rest = [row for row in group if row["id"] != lead["id"]]
        amounts = [row["amount"] for row in group if row["amount"] is not None]
        quantities = [row["quantity"] for row in group if row["quantity"] is not None]
        pending = [row for row in group if not row["order_id"]
                   and row["sync_status"] in ("COLLECTED", "PENDING_REVIEW")]
        lead_order = lead["_order"]
        rows.append({
            "id": lead["id"],
            "external_id": lead["external_id"],
            "external_order_no": lead["external_order_no"],
            "sync_status": lead["sync_status"],
            "created_at": lead["created_at"],
            "order_id": lead["order_id"],
            "customer_name": lead["customer_name"],
            "product": lead["product"],
            "quantity": sum(quantities) if quantities else None,
            "amount": sum(amounts) if amounts else None,
            "payment": lead["payment"],
            "discount_total": sum(row["payment"]["discount"] for row in group),
            "claim_label": next((row["claim_label"] for row in group if row["claim_label"]), ""),
            # 승격은 집 단위다 — 한 건이라도 취소·반품이면 promote_link_to_order 가 막는다
            # (promotion.py). 화면도 같은 판정으로 버튼을 잠가야 헛클릭이 안 난다.
            "claim_blocking": any(row["claim_blocking"] for row in group),
            # 발주확인은 상품주문 단위라 한 건만 남아도 그 집은 아직 끝난 게 아니다(T16-A).
            "place_pending": any(not row["place_confirmed"] for row in group),
            "failure_reason": next((row["failure_reason"] for row in group
                                    if row["failure_reason"]), ""),
            "count": len(group),
            "extra_count": len(rest),
            # 묶음 안 상태를 중복 없이(표시 순서 유지) — 한 집에 성공/실패가 섞일 수 있다.
            "statuses": list(dict.fromkeys(row["sync_status"] for row in group)),
            "pending_link_id": pending[0]["id"] if pending else None,
            "pending_count": len(pending),
            "next_step": ("주문 만들기" if pending
                          else ("규격 입력" if lead["order_id"]
                                and not order_has_spec_rows(lead_order) else "")),
            # 펼침 목록도 대표 먼저(map_group·도크·확인 화면과 같은 순서 규칙).
            "members": [lead, *rest],
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

    place_pending = (request.args.get("place") or "").strip().upper() == "PENDING"
    rows, total = _link_rows(db, status=status if status in VALID_STATUSES else None,
                             page=page, place_pending=place_pending)
    counts = _status_group_counts(db)
    place_pending_count = _place_pending_group_count(db)
    return render_template(
        "admin/naver_ingest.html",
        rows=rows,
        total=total,
        page=page,
        page_size=PAGE_SIZE,
        status=status if status in VALID_STATUSES else "",
        counts=counts,
        place_pending=place_pending,
        place_pending_count=place_pending_count,
        watermark=_watermark_view(db),
        expiry=_expiry_view(db),
    )


def _triage_pane(db, link: ExternalOrderLink) -> dict[str, Any]:
    """한 건의 원본 ↔ FOMS 현재 값 대조 데이터를 만든다.

    옵션 원문을 크게 보여주는 것이 이 화면의 존재 이유다 — v1 은 규격을 파싱하지 않으므로
    사람이 이 문자열을 읽고 편집기에서 채운다.
    """
    from foms.services.integrations.naver_commerce.mapping import (
        build_payment_info,
        extract_claim,
        extract_place_status,
        extract_shipping_memo,
        unwrap_detail,
    )

    order = db.get(Order, int(link.order_id)) if link.order_id else None
    naver_order, product_order, shipping = unwrap_detail(link.raw_snapshot or {})
    return {
        "link_id": link.id,
        "external_id": link.external_id,
        "created_at": format_datetime_kst(link.created_at),
        "order_id": link.order_id,
        "sync_status": link.sync_status,
        "naver": {
            "product_name": product_order.get("productName"),
            "option": product_order.get("productOption"),
            "quantity": product_order.get("quantity"),
            "amount": product_order.get("totalPaymentAmount"),
            "seller_product_code": product_order.get("sellerProductCode"),
            "shipping_due_date": product_order.get("shippingDueDate"),
            "orderer_name": naver_order.get("ordererName"),
            "orderer_tel": naver_order.get("ordererTel"),
            "recipient_name": shipping.get("name"),
            "recipient_tel": shipping.get("tel1"),
            "address": " ".join(
                part for part in (shipping.get("baseAddress"), shipping.get("detailedAddress"))
                if part
            ).strip(),
            # 실위치는 productOrder.shippingMemo (mapping.extract_shipping_memo 참조).
            # 원본 스냅샷에서 읽으므로 과거 수집분도 재처리 없이 그대로 보인다.
            "shipping_memo": extract_shipping_memo(link.raw_snapshot or {}),
            "recipient_tel2": shipping.get("tel2"),
            "product_id": product_order.get("productId"),
            "inflow_path": product_order.get("inflowPath"),
        },
        # CS 흐름은 ① 주문 만들기 ② ERP 규격 입력까지다. 담당자 지정은 이 단계가 아니라
        # 고객 통화 → 실측일 지정 → 실측 스케줄링 시점에 한다(2026-08-17 사용자 확정).
        "steps": {
            "order_created": bool(link.order_id),
            "spec_filled": order_has_spec_rows(order),
        },
        "edit_url": (url_for("order_edit.edit_order", order_id=int(link.order_id),
                             open="erp-order") if link.order_id else ""),
        # 취소·반품은 productOrderStatus 로는 안 보인다 — 별도 축으로 싣는다.
        "claim": extract_claim(link.raw_snapshot or {}),
        # 발주확인 여부(네이버 판매자센터 처리 상태). 수집 원본에 이미 들어온다 — T16-A.
        "place": extract_place_status(link.raw_snapshot or {}),
        # 이 수집분이 붙을 만한 기존 주문 후보 — 재결제·차액 결제 판별용(T16-C/D).
        # **자동으로 붙이지 않는다.** 근거와 함께 늘어놓고 사람이 고른다.
        "relation": link.relation,
        "candidates": find_order_candidates(db, link),
        "payment": build_payment_info(link.raw_snapshot or {}),
        "foms": {
            "customer_name": getattr(order, "customer_name", None),
            "phone": getattr(order, "phone", None),
            "address": getattr(order, "address", None),
            "product": getattr(order, "product", None),
            "options": getattr(order, "options", None),
            "payment_amount": getattr(order, "payment_amount", None),
        },
    }


@admin_bp.route("/admin/naver-ingest/triage")
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def naver_ingest_triage():
    """수집 주문 트리아지 작업대 (스펙 §8.2).

    좌=확인 대기 큐, 우=네이버 원본 ↔ FOMS 현재 값 대조. **규격 입력은 여기서 하지 않는다** —
    ``spec_rows`` 는 폭(W)이 출고가·시공비와 결합돼 있어 두 번째 입력 UI 를 만들면 계산
    규칙이 갈라진다. 편집기가 규격 입력의 SSOT 로 남고 여기서는 링크만 건넨다.

    T14-A: 규격을 실제로 입력하는 사람이 CS 접수 담당이라 전 직원(STAFF 이상)에게
    개방한다. 수집 운영 화면(``naver_ingest_dashboard``)·"지금 수집"·raw 스냅샷은
    관리자 전용으로 남는다.
    """
    db = get_db()
    # 큐에는 두 종류가 같이 온다: 아직 주문이 없는 수집분(COLLECTED — 여기서 "주문 만들기")과
    # 주문은 생겼지만 사람이 아직 안 본 건(LINKED + reviewed_at NULL).
    pending = (
        db.query(ExternalOrderLink)
        .filter(
            ExternalOrderLink.channel == "NAVER",
            ExternalOrderLink.sync_status.in_(("COLLECTED", "LINKED")),
            ExternalOrderLink.reviewed_at.is_(None),
        )
        .order_by(ExternalOrderLink.created_at.desc(), ExternalOrderLink.id.desc())
        .limit(QUEUE_LINK_FETCH_LIMIT)
        .all()
    )
    truncated = len(pending) == QUEUE_LINK_FETCH_LIMIT
    selected_id = request.args.get("link_id", type=int)
    selected = next((row for row in pending if row.id == selected_id), None)
    if selected is None and pending:
        selected = pending[0]

    order_ids = [int(row.order_id) for row in pending if row.order_id]
    orders = {}
    if order_ids:
        orders = {o.id: o for o in db.query(Order).filter(Order.id.in_(order_ids)).all()}
    queue = _group_queue(pending, orders, truncated=truncated)
    selected_group = next(
        (group for group in queue if selected is not None and selected.id in group["link_ids"]),
        None,
    )

    return render_template(
        "admin/naver_triage.html",
        queue=queue,
        pending_count=sum(len(group["link_ids"]) for group in queue),
        group_count=len(queue),
        selected=_triage_pane(db, selected) if selected is not None else None,
        selected_group=selected_group,
        sales_users=_active_sales_users(db),
    )


def _group_queue(links: list[ExternalOrderLink], orders: dict,
                 *, truncated: bool) -> list[dict[str, Any]]:
    """확인 대기 링크를 **한 집 = 한 줄**로 묶는다 (T14-C).

    네이버는 본품과 구성 옵션을 각각 다른 상품주문으로 준다. 링크 1건 = 1행으로 두면
    같은 사람 이름이 3~4번 반복돼 몇 집이 밀렸는지 세지 못한다. 묶음 판정은 주문 생성과
    **같은 키**(:func:`mapping.group_key`)를 쓴다 — 화면과 실제 생성 결과가 갈리면
    "한 줄인데 주문 2건" 같은 사고가 난다.

    대표(본품)는 금액 최대 건이다(``map_group`` 규칙과 동일 — 0원 구성이 대표가 되면
    목록에 길이추가 옵션이 제목으로 뜬다).

    Args:
        links: 확인 대기 링크(최신순).
        orders: ``{order_id: Order}`` — FOMS 현재 값 우선 표시용.
        truncated: 조회 상한에 걸렸는지. 걸렸으면 마지막 묶음은 잘렸을 수 있어 버린다.

    Returns:
        묶음 목록(최신 수집순). 각 항목은 대표 정보 + 구성 링크 목록.
    """
    from foms.services.integrations.naver_commerce.mapping import group_key

    groups: dict[tuple, list[ExternalOrderLink]] = {}
    order_of_key: list[tuple] = []
    for link in links:
        try:
            key = group_key(link.raw_snapshot or {})
        except (ValueError, TypeError, AttributeError, KeyError) as exc:
            # 원본이 깨진 건은 묶지 않고 홀로 남긴다(큐에서 사라지면 사람이 못 본다).
            logger.warning("[NAVER] 큐 묶음 키 계산 실패(link %s): %s", link.id, exc)
            key = ("__ungrouped__", str(link.id), "")
        if key not in groups:
            groups[key] = []
            order_of_key.append(key)
        groups[key].append(link)

    if truncated and order_of_key:
        # 상한에 걸리면 마지막 묶음은 구성 일부만 실려 왔을 수 있다 — 반쪽을 보여주느니 뺀다.
        order_of_key.pop()

    queue: list[dict[str, Any]] = []
    for key in order_of_key[:PAGE_SIZE]:
        members = groups[key]
        lead = max(members, key=lambda row: (summarize_snapshot(row.raw_snapshot)["amount"] or 0,
                                             -row.id))
        order = orders.get(int(lead.order_id or 0))
        lead_summary = summarize_snapshot(lead.raw_snapshot)
        rest = [row for row in members if row.id != lead.id]
        # summarize_snapshot 은 원본 JSON 을 푸는 일이라 공짜가 아니다 — 멤버당 1회만 부르고
        # 아래 표식(클레임·발주)들이 같은 결과를 나눠 쓴다.
        ordered_summaries = [summarize_snapshot(row.raw_snapshot) for row in [lead, *rest]]
        member_summaries = ordered_summaries
        queue.append({
            "id": lead.id,
            "external_id": lead.external_id,
            "created_at": format_datetime_kst(lead.created_at),
            "customer_name": (getattr(order, "customer_name", None)
                              or lead_summary["customer_name"]),
            "product": lead_summary["product"],
            "order_id": lead.order_id,
            "sync_status": lead.sync_status,
            "count": len(members),
            "extra_count": len(rest),
            # 묶음 안 어느 한 건이라도 취소·반품이면 줄 전체에 표식을 단다.
            "claim_label": next((s["claim_label"] for s in member_summaries if s["claim_label"]), ""),
            "claim_blocking": any(s["claim_blocking"] for s in member_summaries),
            # 발주확인은 상품주문 단위다 — 하나라도 남아 있으면 그 집은 "발주확인 전"이다(T16-A).
            "place_pending": any(not s["place_confirmed"] for s in member_summaries),
            "shipping_due": next((s["shipping_due"] for s in member_summaries if s["shipping_due"]), ""),
            # CS 가 다음에 할 일을 목록에서 바로 알아보게 한다.
            "next_step": ("주문 만들기" if not lead.order_id
                          else ("규격 입력" if not order_has_spec_rows(order) else "")),
            "link_ids": [row.id for row in members],
            # 펼침 목록도 **대표 먼저** — 사람이 처음 보는 줄이 0원 구성 옵션이면 본품을
            # 찾아 헤맨다(map_group·도크와 같은 순서 규칙).
            "members": [
                {"id": row.id,
                 "product": summary["product"],
                 "place_confirmed": summary["place_confirmed"],
                 "is_lead": row.id == lead.id}
                for row, summary in zip([lead, *rest], ordered_summaries)
            ],
        })
    return queue


def _active_sales_users(db) -> list[dict[str, Any]]:
    """담당자로 지정 가능한 활성 SALES 사용자(보류함 계정 제외)."""
    from foms.services.integrations.naver_commerce.constants import OWNER_USERNAME
    from foms.services.orders.order_mutation_policy import normalize_team
    from models import User

    rows = db.query(User).filter(User.is_active.is_(True)).all()
    return [
        {"id": u.id, "name": u.name or u.username}
        for u in rows
        if normalize_team(u.team) == "SALES" and u.username != OWNER_USERNAME
    ]


@admin_bp.route("/admin/naver-ingest/<int:link_id>/create-order", methods=["POST"])
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def naver_ingest_create_order(link_id: int):
    """수집분 1건을 FOMS 주문으로 만든다 (T12 — 수집과 생성 분리).

    수집은 자동이지만 생성은 사람의 판단이다. 이 버튼이 그 판단 지점이다.
    ``promote_link_to_order`` 는 ``create_order()`` 만 경유하므로 owner 배정·quest seed·
    ``ORDER_CREATED`` 이벤트·GEOCODE outbox 예약이 기존 주문과 동일하게 붙는다.

    멱등: 이미 주문이 붙은 링크는 새로 만들지 않고 그 주문 id 를 그대로 돌려준다
    (버튼 두 번 클릭·새로고침 재전송 방어).
    """
    from foms.services.integrations.naver_commerce.promotion import (
        PromotionError,
        promote_link_to_order,
    )

    db = get_db()
    try:
        from foms.services.integrations.naver_commerce.accounts import resolve_ingest_account_ids

        actor_user_id, owner_user_id = resolve_ingest_account_ids(db)
    except Exception as exc:  # noqa: BLE001 - 계정 문제는 사용자에게 사유를 그대로 보여준다
        logger.warning("[NAVER] 수집 계정 확인 실패 link=%s: %s", link_id, exc)
        return jsonify({"success": False, "data": None, "error": str(exc)}), 400

    try:
        order_id, created = promote_link_to_order(
            db, link_id=link_id, actor_user_id=actor_user_id, owner_user_id=owner_user_id,
        )
        db.commit()
    except PromotionError as exc:
        db.commit()  # 매핑 실패 시 PENDING_REVIEW 기록은 남긴다(원인 추적).
        return jsonify({"success": False, "data": None, "error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001 - 생성 실패 전체를 tx 되돌리고 사유 반환
        db.rollback()
        logger.warning("[NAVER] 수집분 주문 생성 실패 link=%s: %s", link_id, exc, exc_info=True)
        return jsonify({"success": False, "data": None, "error": str(exc)}), 400

    log_access(
        f"네이버 수집분 주문 생성 (link {link_id} → order {order_id})",
        action="NAVER_INGEST_CREATE_ORDER",
        target_type="order", target_id=order_id,
        detail={"link_id": link_id, "order_id": order_id, "created": created},
    )
    return jsonify({"success": True,
                    "data": {"link_id": link_id, "order_id": order_id, "created": created,
                             # CS 는 만들자마자 규격을 넣으러 간다 — 화면이 새 탭으로 열어준다.
                             "edit_url": url_for("order_edit.edit_order",
                                                 order_id=order_id, open="erp-order")},
                    "error": None})


@admin_bp.route("/admin/naver-ingest/<int:link_id>/attach", methods=["POST"])
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def naver_ingest_attach_order(link_id: int):
    """수집분을 **기존 주문에 붙인다** (T16-E) — 차액 결제·재결제.

    새 주문을 만들지 않는다. 수집 판정이 결제완료 하나뿐이라 재결제·차액 결제도 새 집으로
    들어오는데, 그대로 "주문 만들기"를 누르면 같은 고객의 시공 건이 둘로 갈린다.

    관계 판정은 **사람이** 한다(후보 제시는 :mod:`order_candidates`). 이 라우트는 사람이
    고른 결과를 받아 적을 뿐이다.
    """
    from foms.services.integrations.naver_commerce.promotion import (
        PromotionError,
        attach_link_to_order,
    )

    payload = request.get_json(silent=True) or {}
    try:
        order_id = int(payload.get("order_id") or 0)
    except (TypeError, ValueError):
        order_id = 0
    relation = str(payload.get("relation") or "").strip().upper()
    if order_id <= 0:
        return jsonify({"success": False, "data": None, "error": "붙일 주문을 지정하세요."}), 400

    db = get_db()
    try:
        attached, target_order_id = attach_link_to_order(
            db, link_id=link_id, order_id=order_id, relation=relation)
        db.commit()
    except PromotionError as exc:
        db.rollback()
        return jsonify({"success": False, "data": None, "error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001 - 실패 사유를 사람에게 그대로 보여준다
        db.rollback()
        logger.warning("[NAVER] 기존 주문 연결 실패 link=%s order=%s: %s",
                       link_id, order_id, exc, exc_info=True)
        return jsonify({"success": False, "data": None, "error": str(exc)}), 400

    log_access(
        f"네이버 수집분 기존 주문 연결 (link {link_id} → order {target_order_id}, {relation})",
        action="NAVER_INGEST_ATTACH_ORDER",
        target_type="order", target_id=target_order_id,
        detail={"link_id": link_id, "order_id": target_order_id,
                "relation": relation, "attached": attached},
    )
    return jsonify({"success": True,
                    "data": {"link_id": link_id, "order_id": target_order_id,
                             "relation": relation, "attached": attached,
                             "edit_url": url_for("order_edit.edit_order",
                                                 order_id=target_order_id, open="erp-order")},
                    "error": None})


@admin_bp.route("/admin/naver-ingest/<int:link_id>/detach", methods=["POST"])
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def naver_ingest_detach_order(link_id: int):
    """붙이기를 되돌린다 (T16-E) — 관계를 잘못 골랐을 때.

    주문 생성분(``NEW``)은 되돌릴 수 없다. 그건 주문 삭제 문제라 이 경로의 일이 아니다.
    """
    from foms.services.integrations.naver_commerce.promotion import (
        PromotionError,
        detach_link_from_order,
    )

    db = get_db()
    try:
        detached, previous_order_id = detach_link_from_order(db, link_id=link_id)
        db.commit()
    except PromotionError as exc:
        db.rollback()
        return jsonify({"success": False, "data": None, "error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("[NAVER] 연결 되돌리기 실패 link=%s: %s", link_id, exc, exc_info=True)
        return jsonify({"success": False, "data": None, "error": str(exc)}), 400

    log_access(
        f"네이버 수집분 연결 되돌림 (link {link_id} ← order {previous_order_id})",
        action="NAVER_INGEST_DETACH_ORDER",
        target_type="order", target_id=previous_order_id,
        detail={"link_id": link_id, "order_id": previous_order_id, "detached": detached},
    )
    return jsonify({"success": True,
                    "data": {"link_id": link_id, "order_id": previous_order_id,
                             "detached": detached},
                    "error": None})


@admin_bp.route("/admin/naver-ingest/<int:link_id>/review", methods=["POST"])
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def naver_ingest_mark_reviewed(link_id: int):
    """"확인 완료" — 사람이 처리했다고 표시해 큐에서 뺀다 (스펙 §8.3).

    시스템이 "다 채웠는지"를 추측하지 않는다. 추측 규칙을 코드로 정하면 오판 여지가 생기고
    업무 기준이 바뀔 때마다 규칙을 고쳐야 한다. 사람이 누른 사실만 기록한다.
    """
    db = get_db()
    link = (
        db.query(ExternalOrderLink)
        .filter(ExternalOrderLink.id == link_id, ExternalOrderLink.channel == "NAVER")
        .first()
    )
    if link is None:
        return jsonify({"success": False, "data": None, "error": "수집 이력을 찾을 수 없습니다."}), 404
    if link.reviewed_at is None:  # 이미 확인된 건은 시각을 덮지 않는다(첫 확인이 기록이다).
        link.reviewed_at = now_utc_naive()
        link.reviewed_by_user_id = session.get("user_id")
        db.commit()
    log_access(
        f"네이버 수집 확인 완료 (link {link_id})",
        action="NAVER_INGEST_MARK_REVIEWED",
        detail={"link_id": link_id, "external_id": link.external_id},
    )
    return jsonify({"success": True, "data": {"link_id": link_id}, "error": None})


@admin_bp.route("/admin/naver-ingest/<int:link_id>/dock-state", methods=["POST"])
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def naver_ingest_dock_state(link_id: int):
    """도크 항목의 체크(반영 표시)·귀속(추가옵션→본품)을 저장한다 (T14-B).

    체크는 즉시 저장(팀 공유)이며 토글 가능하다 — ``reviewed_at`` 과 다른 축이다
    (저건 큐 이탈·첫 확인 시각 불변). 귀속은 **표시/체크리스트용**일 뿐 주문 데이터
    (items·spec_rows)는 절대 건드리지 않는다(폼 불가침 계약).

    Body(JSON, 부분 갱신): ``checked``(bool) / ``assigned_main``(str|null —
    형제 본품 external_id, ``"COMMON"``(주문 전체), 또는 null=미정).
    """
    import copy as copy_module

    from sqlalchemy.orm.attributes import flag_modified

    from foms.services.integrations.naver_commerce.dock import ASSIGN_COMMON

    db = get_db()
    link = (
        db.query(ExternalOrderLink)
        .filter(ExternalOrderLink.id == link_id, ExternalOrderLink.channel == "NAVER")
        .first()
    )
    if link is None:
        return jsonify({"success": False, "data": None, "error": "수집 이력을 찾을 수 없습니다."}), 404

    body = request.get_json(silent=True) or {}
    if "checked" not in body and "assigned_main" not in body:
        return jsonify({"success": False, "data": None,
                        "error": "checked 또는 assigned_main 이 필요합니다."}), 400

    state = copy_module.deepcopy(link.triage_state) if isinstance(link.triage_state, dict) else {}
    user_id = session.get("user_id")
    now_str = now_utc_naive().strftime("%Y-%m-%d %H:%M:%S")

    if "checked" in body:
        if not isinstance(body["checked"], bool):
            return jsonify({"success": False, "data": None,
                            "error": "checked 는 true/false 여야 합니다."}), 400
        state["checked"] = body["checked"]
        state["checked_by"] = user_id
        state["checked_at"] = now_str

    if "assigned_main" in body:
        assigned = body["assigned_main"]
        if assigned is not None:
            assigned = str(assigned).strip()
            if assigned != ASSIGN_COMMON:
                # 같은 주문의 형제 링크 external_id 만 허용 — 임의 문자열 저장 금지.
                sibling_ids = {
                    row.external_id
                    for row in db.query(ExternalOrderLink.external_id)
                    .filter(ExternalOrderLink.channel == "NAVER",
                            ExternalOrderLink.order_id == link.order_id)
                    .all()
                } if link.order_id else set()
                if assigned not in sibling_ids:
                    return jsonify({"success": False, "data": None,
                                    "error": "귀속 대상이 이 주문의 본품이 아닙니다."}), 400
        state["assigned_main"] = assigned
        state["assigned_by"] = user_id
        state["assigned_at"] = now_str

    link.triage_state = state
    flag_modified(link, "triage_state")
    db.commit()
    log_access(
        f"네이버 도크 상태 저장 (link {link_id})",
        action="NAVER_DOCK_STATE_SET",
        detail={"link_id": link_id, "external_id": link.external_id,
                "checked": state.get("checked"), "assigned_main": state.get("assigned_main")},
    )
    return jsonify({"success": True,
                    "data": {"link_id": link_id,
                             "checked": bool(state.get("checked")),
                             "assigned_main": state.get("assigned_main")},
                    "error": None})


@admin_bp.route("/admin/naver-ingest/<int:order_id>/assignee", methods=["POST"])
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def naver_ingest_set_assignee(order_id: int):
    """수집 주문의 SALES 담당자를 지정한다 (스펙 §8.4).

    ``OrderAssignment`` 를 직접 만들지 않고 canonical
    :func:`~foms.services.orders.assignment.set_sales_assignee` 를 부른다 — 그래야 REV-00
    version bump·receipt·``SALES_ASSIGNEE_SET`` 이벤트·주문당 active owner 1명 제약이
    전부 따라온다.

    보류함(``naver_unassigned``)에서 실제 담당자로 옮기는 것도 **교체**라 사유가 필수다.
    화면이 사유를 보내지 않으므로 여기서 기본 사유를 채운다.
    """
    import hashlib
    import json as _json

    from foms.services.orders.assignment import set_sales_assignee
    from foms.services.orders.revision import RevisionError

    body = request.get_json(silent=True) or {}
    try:
        user_id = int(body.get("user_id"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "data": None,
                        "error": "담당자(user_id)가 필요합니다."}), 400

    db = get_db()
    scope_hash = hashlib.sha256(f"SET_SALES_ASSIGNEE:{order_id}".encode("utf-8")).hexdigest()
    request_hash = hashlib.sha256(
        _json.dumps({"user_id": user_id}, sort_keys=True).encode("utf-8")
    ).hexdigest()
    try:
        set_sales_assignee(
            db, actor_user_id=int(session.get("user_id")), order_id=order_id,
            user_id=user_id, reason="네이버 수집 주문 담당자 지정",
            scope_hash=scope_hash, request_hash=request_hash,
        )
        db.commit()
    except RevisionError as exc:
        db.rollback()
        return jsonify({"success": False, "data": None, "error": str(exc)}), exc.status_code
    except Exception as exc:  # noqa: BLE001 - 사용자에게 사유를 돌려주고 tx 는 되돌린다
        db.rollback()
        logger.warning("[NAVER] 담당자 지정 실패 order=%s: %s", order_id, exc, exc_info=True)
        return jsonify({"success": False, "data": None, "error": str(exc)}), 400

    log_access(
        f"네이버 수집 주문 담당자 지정 (order {order_id})",
        action="NAVER_INGEST_SET_ASSIGNEE",
        target_type="order", target_id=order_id,
        detail={"order_id": order_id, "user_id": user_id},
    )
    return jsonify({"success": True, "data": {"order_id": order_id, "user_id": user_id},
                    "error": None})


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
    "naver_ingest_dock_state",
    "naver_ingest_mark_reviewed",
    "naver_ingest_set_assignee",
    "naver_ingest_triage",
    "naver_ingest_run_now",
    "naver_ingest_snapshot",
    "PAGE_SIZE",
    "VALID_STATUSES",
]
