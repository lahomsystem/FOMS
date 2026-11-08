"""FCOMM-01 D31 — "내 수수료" 명세서 줄을 펼치면 보이는 주문 세부내역 + 확정 도면.

설계서 docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §6.6 D31 · 목업
docs/design/mockups/freelancer-commission-statement-detail.html 안 A.

- 품목(취소 품목도 남긴다) · 추가 금액 · 할인 · 수수료용 출고가(:func:`calc.commission_shipping_price`).
  품목 ``price`` 는 그 줄 금액이고, 저장 품목합(``totals.items_total``)도 이 값의 합이라 화면 합이 계산 줄과 맞는다.
- 확정 도면(:func:`resolve_final_drawing_files` — 생산 시트 썸네일과 같은 답). 그림이면 작은 그림 → 전역 모달,
  그 밖(PDF 등)은 새 탭으로 연다.
- 읽기 권한은 주문 화면과 같은 판정(:func:`user_can_read_order`). 프리랜서는 연결 줄을 한 번에 읽어 요청 캐시에
  채운 뒤(:func:`prime_freelancer_access`) 줄마다 같은 함수로 본다 — 볼 수 없는 주문은 세부내역을 싣지 않는다.
- ``structured_data`` 는 필요한 칸만 얇게 읽는다(:func:`fetch_settlement_rows` — JSONB 통째 읽기 금지).
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Iterable, Optional

from foms.services.auth.freelancer_orders import prime_freelancer_access
from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.erp_display import _erp_coerce_item_price_krw
from foms.services.estimate_service import (
    _extract_discount_amount,
    _extract_free_input_amount,
    _extract_free_input_text,
    _format_spec_rows,
)
from foms.services.orders.drawing_confirm_partial import is_item_cancelled
from foms.services.orders.order_mutation_policy import user_can_read_order
from foms.services.sales_commission import calc
from foms.services.sales_commission.read_model import scope_filters
from foms.services.settlement_source import ARRAY_ITEMS, fetch_settlement_rows
from models import Order

__all__ = ["DETAIL_SD_SPEC", "build_order_detail", "order_details", "shipping_changed"]

#: 세부내역이 읽는 ``structured_data`` 경로만 남긴 나무(:mod:`foms.services.settlement_source` 규약).
DETAIL_SD_SPEC: dict[str, Any] = {
    "items": {ARRAY_ITEMS: {
        "price": None, "product_name": None, "cancel": None,
        "spec": None, "spec_rows": None, "color": None, "quantity": None,
    }},
    "totals": None,
    "payment": None,
    "payments": None,
    "drawing_current_files": None,
}

_IMAGE_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")


def _spec_text(item: dict) -> str:
    """규격 · 색 · 수량을 한 줄로("2400 × 2300 · 화이트 · 1개"). 빈 칸은 뺀다."""
    spec = " / ".join(part.strip() for part in str(_format_spec_rows(item) or "").splitlines() if part.strip())
    color = str(item.get("color") or "").strip()
    quantity = calc._as_int(item.get("quantity"))
    bits = [spec, color, f"{quantity}개" if quantity and quantity > 0 else ""]
    return " · ".join(bit for bit in bits if bit)


def _has_words(text: str) -> bool:
    """숫자 · 기호만이 아닌 글인가(자유 입력 글을 금액 옆 설명으로 쓸지)."""
    return any(ch.isalpha() for ch in text)


def build_order_detail(sd: Any) -> dict[str, Any]:
    """주문 하나의 세부내역.

    Args:
        sd: 주문 ``structured_data``(얇게 읽은 것도 됨). dict 가 아니면 빈 세부내역.

    Returns:
        ``{items: [{name, spec, price, cancelled}], free_amount, free_text, discount, shipping_price,
        drawings: [{view_url, download_url, filename, key, is_image}]}``. 금액은 원 단위 정수(출고가는 못 내면 None).
    """
    sd = sd if isinstance(sd, dict) else {}
    items = []
    raw_items = sd.get("items")
    for item in raw_items if isinstance(raw_items, list) else []:
        if not isinstance(item, dict):
            continue
        items.append({
            "name": str(item.get("product_name") or "").strip() or "품목",
            "spec": _spec_text(item),
            "price": _erp_coerce_item_price_krw(item),
            "cancelled": is_item_cancelled(item),
        })
    free_text = _extract_free_input_text(sd)
    drawings = []
    for entry in resolve_final_drawing_files(sd):
        view = (entry.get("view_url") or "").strip()
        if not view:
            continue
        filename = entry.get("filename") or "도면"
        drawings.append({
            "view_url": view,
            "download_url": (entry.get("download_url") or view).strip(),
            "filename": filename,
            "key": entry.get("key") or "",
            "is_image": filename.lower().endswith(_IMAGE_EXT),
        })
    return {
        "items": items,
        "free_amount": int(_extract_free_input_amount(sd) or 0),
        "free_text": free_text if _has_words(free_text) else "",
        "discount": int(_extract_discount_amount(sd) or 0),
        "shipping_price": calc.commission_shipping_price(sd),
        "drawings": drawings,
    }


def order_details(db: Any, viewer: Any, order_ids: Iterable[Any]) -> dict[int, dict[str, Any]]:
    """명세서 줄의 주문들 세부내역 — 읽을 수 있는 주문만, 조회 한 번(+ 프리랜서 연결 한 번).

    Args:
        db: SQLAlchemy 세션.
        viewer: 화면을 보는 계정(프리랜서 본인 또는 대신 보는 회계 · 관리자).
        order_ids: 줄의 주문 번호들(정수로 못 바꾸는 값 · 중복은 버린다).

    Returns:
        ``{order_id: build_order_detail 결과}``. 지워졌거나 초안 · 협력사 주문, 볼 수 없는 주문은 없다.
    """
    ids: list[int] = sorted({oid for oid in (calc._as_int(i) for i in order_ids) if oid and oid > 0})
    if not ids:
        return {}
    rows = fetch_settlement_rows(db, (Order.id,), scope_filters() + (Order.id.in_(ids),), DETAIL_SD_SPEC)
    prime_freelancer_access(db, viewer, [row.id for row in rows])
    out: dict[int, dict[str, Any]] = {}
    for row in rows:
        oid = int(row.id)
        # 주문 화면과 같은 판정(협력사 주문은 scope_filters 가 이미 뺐다).
        if not user_can_read_order(viewer, SimpleNamespace(id=oid, partner_org_id=None)):
            continue
        out[oid] = build_order_detail(row.structured_data)
    return out


def shipping_changed(detail: Optional[dict[str, Any]], frozen_shipping: Any) -> bool:
    """마감 때 굳힌 출고가와 지금 출고가가 다른가(둘 다 있을 때만)."""
    if not detail:
        return False
    now = detail.get("shipping_price")
    frozen = calc._as_int(frozen_shipping)
    return now is not None and frozen is not None and int(now) != frozen
