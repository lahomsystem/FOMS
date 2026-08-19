"""네이버 원본 도크 데이터 (T14-B — 주문 편집 화면 우측 패널).

주문 편집기에서 규격을 입력하는 사람이 네이버 원문을 다른 화면으로 오가며 보지 않도록,
그 주문의 수집 원본을 편집 셸 옆에 나란히 보여준다. **폼 불가침 계약**: 이 모듈은 표시용
데이터만 만들고 주문(items·spec_rows)은 절대 건드리지 않는다 — 값 전달은 사람이
복사 버튼으로만 한다.

본품/추가옵션 판정은 네이버 원본의 ``productClass`` 가 정본이다(실측 2026-08-14):
``조합형옵션상품`` = 본품, ``추가구성상품`` = 추가옵션. **귀속(어느 본품의 옵션인가)은
수집 순서**로 본다 — 네이버 응답은 본품 다음에 그 본품의 옵션들이 온다(2026-08-18 확정).
추정은 표시까지, 확정은 사람이 한다(귀속 드롭다운).

DB 만 읽는다 — 네이버 HTTP 는 여기서 절대 내지 않는다(WORKER 단일 출구 계약).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from foms.services.integrations.naver_commerce.attribution import (
    SPEC_AXES,
    attribute_addons,
    axis_values,
)
from foms.services.integrations.naver_commerce.constants import (
    ADDON_PRODUCT_CLASS,
    CHANNEL,
)

logger = logging.getLogger(__name__)

#: 귀속 값으로 허용되는 특수 토큰 — "주문 전체 공통" (특정 본품 소속이 아님).
ASSIGN_COMMON = "COMMON"

def _text(value: Any) -> str:
    return str(value or "").strip()


def split_option_copies(option_text: str) -> list[str]:
    """옵션 원문을 복사 칩 값 목록으로 쪼갠다.

    ``"사이즈: 150 / 색상: 클린 화이트"`` → ``["150", "클린 화이트"]``.
    콜론이 없는 조각은 통째로 하나의 칩이 된다. 파싱 실패해도 원문이 화면에 남으므로
    칩은 편의 기능일 뿐이다(자동 기입 금지 — 스펙 확정 결정 3).

    Args:
        option_text: 네이버 ``productOption`` 원문.

    Returns:
        복사 칩 값 목록(빈 값 제외).
    """
    copies: list[str] = []
    for segment in _text(option_text).split("/"):
        segment = segment.strip()
        if not segment:
            continue
        value = segment.split(":", 1)[1].strip() if ":" in segment else segment
        if value:
            copies.append(value)
    return copies


#: 원문에서 길이를 읽는다. ``30cm``·``2400mm``·``2.4m`` 를 모두 mm 로 환산한다.
_LENGTH_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(mm|cm|m)\b", re.I)
_LENGTH_UNIT_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0}

#: 길이추가(1cm 단위) 옵션 판별 힌트. 이 옵션만 총폭에 더한다 —
#: 수납구성(TYPE A 등)·거울도어 같은 구성 옵션은 폭과 무관하다.
_LENGTH_ADDON_HINTS = ("길이추가", "길이 추가")

def parse_length_mm(text: str) -> Optional[int]:
    """원문에서 첫 길이를 mm 정수로 뽑는다(없으면 None).

    Args:
        text: 상품명·옵션 원문.

    Returns:
        mm 값. ``240cm`` → 2400, ``1cm`` → 10, ``2400mm`` → 2400.
    """
    match = _LENGTH_RE.search(_text(text))
    if not match:
        return None
    value, unit = match.group(1), match.group(2).lower()
    return int(round(float(value) * _LENGTH_UNIT_MM[unit]))


def _row_axes(row: dict[str, Any]) -> dict[str, str]:
    """행의 사양 축 값 — 판정은 :func:`attribution.axis_values` 가 한다(옵션 원문 우선)."""
    return axis_values(row.get("product_name") or "", row.get("option_text") or "")


def build_width_hint(main: dict[str, Any], addons: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """본품 + 길이추가 옵션으로 **총폭 후보**를 계산한다 (T14-I).

    CS 는 지금 이 계산을 손으로 한다: 30cm 모듈 12개 + 1cm 추가 12개 = 3,600 + 120 = 3,720.
    자동 기입은 하지 않는다(규격 SSOT 보호) — 계산식과 복사 버튼까지가 이 기능의 끝이다.

    Args:
        main: 본품 행.
        addons: 그 본품에 귀속된 추가옵션 행 목록.

    Returns:
        ``{"total_mm", "formula", "parts", "mismatch"}``. 길이를 못 읽으면 None.
    """
    module_mm = parse_length_mm(f"{main['product_name']} {main['option_text']}")
    if not module_mm:
        return None
    main_qty = main["quantity"] or 1
    parts = [{"label": main["product_name"][:24] or "본품",
              "unit_mm": module_mm, "quantity": main_qty}]
    total = module_mm * main_qty

    mismatch: list[str] = []
    main_axes = _row_axes(main)
    for addon in addons:
        blob = f"{addon['product_name']} {addon['option_text']}"
        if not any(hint in blob for hint in _LENGTH_ADDON_HINTS):
            continue
        unit_mm = parse_length_mm(blob)
        if not unit_mm:
            continue
        quantity = addon["quantity"] or 1
        parts.append({"label": addon["product_name"][:24] or "길이추가",
                      "unit_mm": unit_mm, "quantity": quantity})
        total += unit_mm * quantity
        addon_axes = _row_axes(addon)
        for axis, main_value in main_axes.items():
            addon_value = addon_axes.get(axis)
            if addon_value and addon_value != main_value:
                mismatch.append(f"{axis}: 본품 {main_value} · 추가 {addon_value}")

    if len(parts) == 1:
        # 길이추가 옵션이 없으면 계산이랄 게 없다 — 단순 환산은 칩으로 따로 준다.
        return {"total_mm": total, "formula": f"{module_mm:,}mm × {main_qty}",
                "parts": parts, "mismatch": []}
    formula = " + ".join(f"{part['unit_mm']:,}mm × {part['quantity']}" for part in parts)
    return {"total_mm": total, "formula": formula, "parts": parts,
            "mismatch": list(dict.fromkeys(mismatch))}


def _row_source(link: Any) -> dict[str, Any]:
    """링크의 원본에서 도크 표시에 필요한 필드만 뽑는다(실패 시 빈 값)."""
    from foms.services.integrations.naver_commerce.mapping import (
        NaverMappingError,
        build_payment_info,
        extract_claim,
        extract_shipping_memo,
        unwrap_detail,
    )

    empty = {"product_name": "", "option_text": "", "quantity": None,
             "amount": None, "product_class": "", "seller_product_code": "",
             "recipient_name": "", "orderer_name": "", "shipping_memo": "",
             "claim_label": "", "recipient_tel2": "", "paid_at": "", "pay_means": "",
             "discount": 0}
    snapshot = link.raw_snapshot
    if not isinstance(snapshot, dict) or not snapshot:
        return empty
    try:
        order, product_order, shipping = unwrap_detail(snapshot)
        shipping_memo = extract_shipping_memo(snapshot)
        claim = extract_claim(snapshot)
        payment = build_payment_info(snapshot)
    except (NaverMappingError, ValueError, TypeError, AttributeError, KeyError) as exc:
        # 원본 파손은 행 하나의 문제 — 도크 전체를 죽이지 않는다(원문 없이 행만 남긴다).
        logger.warning("[NAVER] 도크 행 원본 파싱 실패(link %s): %s", link.id, exc)
        return empty
    product_order = product_order or {}
    quantity = product_order.get("quantity")
    amount = product_order.get("totalPaymentAmount")
    return {
        "product_name": _text(product_order.get("productName")),
        "option_text": _text(product_order.get("productOption")),
        "quantity": int(quantity) if isinstance(quantity, int) else None,
        "amount": int(amount) if isinstance(amount, int) else None,
        "product_class": _text(product_order.get("productClass")),
        "seller_product_code": _text(product_order.get("sellerProductCode")),
        # 주문 머리말용 — 수취인이 주문 대표 이름이고, 주문자는 다를 때만 보조로 띄운다
        # (실측 42건 중 9건이 대리주문). 배송메모는 상품주문마다 따로 달린다.
        "recipient_name": _text((shipping or {}).get("name")),
        "orderer_name": _text((order or {}).get("ordererName")),
        "shipping_memo": shipping_memo,
        # 주문을 만든 뒤 취소되는 건도 있다 — 규격을 채우기 전에 눈에 걸려야 한다.
        "claim_label": claim["label"],
        # 연락·정산 확인용(T14-F). 폼에 자동 기입하지 않는다 — 복사 버튼까지다.
        "recipient_tel2": _text((shipping or {}).get("tel2")),
        "paid_at": payment["paid_at"][:16],
        "pay_means": payment["means"],
        "discount": payment["product_discount_amount"] + sum(
            coupon["discount_amount"] for coupon in payment["coupons"]),
    }


def _apply_attribution(rows: list[dict[str, Any]]) -> None:
    """각 추가옵션 행에 ``guess_main``/``guess_reason`` 을 채운다(제자리 수정).

    판정은 :func:`attribution.attribute_addons` — 수집 순서가 본품/옵션을 섞어 주는 집은
    순서로, 본품이 앞에 몰려 온 집은 사양 축 일치로 본다. 사람이 고른 ``assigned_main`` 은
    언제나 이 추정을 이긴다(호출측에서 우선).

    Args:
        rows: 수집 순서(link.id 오름차순)로 정렬된 도크 행 목록.
    """
    signals = [{"is_main": row["role"] != "addon",
                "product_name": row["product_name"],
                "option_text": row["option_text"]} for row in rows]
    owners = attribute_addons(signals)
    for index, row in enumerate(rows):
        if row["role"] != "addon":
            row["guess_main"], row["guess_reason"] = (None, "")
            continue
        owner, reason = owners[index]
        row["guess_main"] = rows[owner]["external_id"] if owner is not None else None
        row["guess_reason"] = reason


def _extra_payment_summary(order: Any) -> dict[str, int]:
    """주문에 기록된 추가결제(차액·재결제) 건수와 합계.

    출고가·잔금을 바꾸지 않고 기록만 하기로 했으므로(2026-08-19 사용자 확정), 사람이
    "얼마가 더 들어왔는지"를 볼 자리가 필요하다.

    Args:
        order: :class:`models.Order`.

    Returns:
        ``{"count", "total"}`` — 기록이 없으면 둘 다 0.
    """
    data = getattr(order, "structured_data", None)
    pricing = data.get("pricing") if isinstance(data, dict) else None
    rows = pricing.get("extra_payments") if isinstance(pricing, dict) else None
    if not isinstance(rows, list):
        return {"count": 0, "total": 0}
    total = 0
    count = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        count += 1
        amount = row.get("amount")
        if isinstance(amount, int):
            total += amount
    return {"count": count, "total": total}


def build_dock_payload(db: Any, order: Any) -> Optional[dict[str, Any]]:
    """주문의 네이버 수집 링크들을 도크 표시용 payload 로 만든다.

    Args:
        db: 요청 스코프 DB 세션.
        order: 대상 :class:`models.Order`.

    Returns:
        도크 payload dict. 네이버 수집 링크가 없으면 ``None`` (도크 미렌더).
    """
    from models import ExternalOrderLink

    links = (
        db.query(ExternalOrderLink)
        .filter(
            ExternalOrderLink.channel == CHANNEL,
            ExternalOrderLink.order_id == order.id,
        )
        .order_by(ExternalOrderLink.id.asc())
        .all()
    )
    if not links:
        return None

    rows: list[dict[str, Any]] = []
    recipient_name = ""
    orderer_name = ""
    claim_label = ""
    recipient_tel2 = ""
    paid_at = ""
    pay_means = ""
    discount = 0
    memos: list[str] = []
    for link in links:
        source = _row_source(link)
        recipient_name = recipient_name or source["recipient_name"]
        orderer_name = orderer_name or source["orderer_name"]
        claim_label = claim_label or source["claim_label"]
        recipient_tel2 = recipient_tel2 or source["recipient_tel2"]
        paid_at = paid_at or source["paid_at"]
        pay_means = pay_means or source["pay_means"]
        discount += source["discount"]
        # 상품주문마다 메모가 다를 수 있다 — 다른 값은 전부 보존한다(중복만 제거).
        if source["shipping_memo"] and source["shipping_memo"] not in memos:
            memos.append(source["shipping_memo"])
        is_addon = source["product_class"] == ADDON_PRODUCT_CLASS
        state = link.triage_state if isinstance(link.triage_state, dict) else {}
        quantity = source["quantity"]
        name_chip = source["product_name"]
        if name_chip and quantity and quantity > 1:
            name_chip = f"{name_chip} ×{quantity}"
        rows.append({
            "link_id": link.id,
            "external_id": link.external_id,
            "role": "addon" if is_addon else "main",
            "product_name": source["product_name"],
            "option_text": source["option_text"],
            "quantity": quantity,
            "amount": source["amount"],
            "seller_product_code": source["seller_product_code"],
            # 본품 = 옵션 원문 값들, 추가옵션 = 이름(+수량) 칩 하나.
            "copies": (split_option_copies(source["option_text"])
                       if not is_addon else ([name_chip] if name_chip else [])),
            "checked": bool(state.get("checked")),
            "assigned_main": state.get("assigned_main"),
            "reviewed": link.reviewed_at is not None,
        })

    mains = [row for row in rows if row["role"] == "main"]
    if not mains and rows:
        # productClass 가 없거나 전부 추가옵션으로 온 비정상 원본 — 금액 최대를 본품으로
        # 간주한다(map_group 의 대표 선정 규칙과 동일한 폴백).
        lead = max(rows, key=lambda row: row["amount"] or 0)
        lead["role"] = "main"
        mains = [lead]

    _apply_attribution(rows)

    # 본품별 총폭 힌트(T14-I) — 귀속은 사람 지정 > 추정 순으로 본다(화면과 같은 규칙).
    width_hints: dict[str, Any] = {}
    for main in mains:
        addons = [row for row in rows
                  if row["role"] == "addon"
                  and (row["assigned_main"] or row.get("guess_main")) == main["external_id"]]
        hint = build_width_hint(main, addons)
        if hint:
            width_hints[main["external_id"]] = hint

    order_no = next((_text(link.external_order_no) for link in links
                     if _text(link.external_order_no)), "")
    extra = _extra_payment_summary(order)
    return {
        # 추가결제(차액)·재결제 기록 — 금액은 기록만 하고 출고가·잔금은 사람이 반영한다(T16-F).
        "extra_payment_count": extra["count"],
        "extra_payment_total": extra["total"],
        "order_no": order_no,
        "rows": rows,
        "mains": [{"external_id": row["external_id"],
                   "label": row["product_name"] or row["external_id"]} for row in mains],
        "assign_common": ASSIGN_COMMON,
        "recipient_name": recipient_name,
        "orderer_name": orderer_name,
        # 대리주문 표식. 둘 다 값이 있고 다를 때만 참 — 빈 값은 "다름"이 아니다.
        "orderer_differs": bool(recipient_name and orderer_name
                                and recipient_name != orderer_name),
        "shipping_memo": "\n".join(memos),
        "claim_label": claim_label,
        "width_hints": width_hints,
        "recipient_tel2": recipient_tel2,
        "paid_at": paid_at,
        "pay_means": pay_means,
        # 묶음이면 상품주문별 할인의 합이 그 집의 총 할인이다.
        "discount": discount,
    }


__all__ = [
    "ADDON_PRODUCT_CLASS",
    "ASSIGN_COMMON",
    "SPEC_AXES",
    "build_dock_payload",
    "build_width_hint",
    "parse_length_mm",
    "split_option_copies",
]
