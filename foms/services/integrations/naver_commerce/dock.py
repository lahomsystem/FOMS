"""네이버 원본 도크 데이터 (T14-B — 주문 편집 화면 우측 패널).

주문 편집기에서 규격을 입력하는 사람이 네이버 원문을 다른 화면으로 오가며 보지 않도록,
그 주문의 수집 원본을 편집 셸 옆에 나란히 보여준다. **폼 불가침 계약**: 이 모듈은 표시용
데이터만 만들고 주문(items·spec_rows)은 절대 건드리지 않는다 — 값 전달은 사람이
복사 버튼으로만 한다.

본품/추가옵션 판정은 네이버 원본의 ``productClass`` 가 정본이다(실측 2026-08-14):
``조합형옵션상품`` = 본품, ``추가구성상품`` = 추가옵션. 이름 휴리스틱은 **귀속 추정**
(어느 본품의 옵션인가)에만 쓴다 — 네이버 API 는 부모 링크를 주지 않으므로 추정은
표시까지, 확정은 사람이 한다(귀속 드롭다운).

DB 만 읽는다 — 네이버 HTTP 는 여기서 절대 내지 않는다(WORKER 단일 출구 계약).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from foms.services.integrations.naver_commerce.constants import CHANNEL

logger = logging.getLogger(__name__)

#: 네이버 productClass 값 — 추가옵션(부모 없는 독립 productOrder).
ADDON_PRODUCT_CLASS = "추가구성상품"

#: 귀속 값으로 허용되는 특수 토큰 — "주문 전체 공통" (특정 본품 소속이 아님).
ASSIGN_COMMON = "COMMON"

_TOKEN_SPLIT = re.compile(r"[\s/()\[\]（）:,+×x·-]+")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _tokens(text: str) -> set[str]:
    """이름 매칭용 토큰(2글자 이상, 숫자 단독 제외)."""
    out = set()
    for tok in _TOKEN_SPLIT.split(text):
        tok = tok.strip()
        if len(tok) >= 2 and not tok.isdigit():
            out.add(tok)
    return out


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


def _row_source(link: Any) -> dict[str, Any]:
    """링크의 원본에서 도크 표시에 필요한 필드만 뽑는다(실패 시 빈 값)."""
    from foms.services.integrations.naver_commerce.mapping import (
        NaverMappingError,
        extract_claim,
        extract_shipping_memo,
        unwrap_detail,
    )

    empty = {"product_name": "", "option_text": "", "quantity": None,
             "amount": None, "product_class": "", "seller_product_code": "",
             "recipient_name": "", "orderer_name": "", "shipping_memo": "",
             "claim_label": ""}
    snapshot = link.raw_snapshot
    if not isinstance(snapshot, dict) or not snapshot:
        return empty
    try:
        order, product_order, shipping = unwrap_detail(snapshot)
        shipping_memo = extract_shipping_memo(snapshot)
        claim = extract_claim(snapshot)
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
    }


def _guess_main(addon: dict[str, Any], mains: list[dict[str, Any]]) -> tuple[Optional[str], str]:
    """추가옵션이 어느 본품 것인지 추정한다.

    Args:
        addon: 추가옵션 행(dict).
        mains: 본품 행 목록.

    Returns:
        ``(추정 본품 external_id 또는 None, 사람이 읽는 근거)``.
    """
    if not mains:
        return (None, "본품 없음")
    if len(mains) == 1:
        return (mains[0]["external_id"], "단일 본품 — 자동 귀속")
    addon_tokens = _tokens(f"{addon['product_name']} {addon['option_text']}")
    scored = []
    for main in mains:
        overlap = len(_tokens(main["product_name"]) & addon_tokens)
        scored.append((overlap, main))
    scored.sort(key=lambda pair: -pair[0])
    best_score, best = scored[0]
    runner_up = scored[1][0] if len(scored) > 1 else 0
    if best_score > 0 and best_score > runner_up:
        return (best["external_id"], f"원문 단서로 '{best['product_name'][:20]}' 추정")
    return (None, "단서 없음 — 어느 본품의 구성인지 선택 필요")


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
    memos: list[str] = []
    for link in links:
        source = _row_source(link)
        recipient_name = recipient_name or source["recipient_name"]
        orderer_name = orderer_name or source["orderer_name"]
        claim_label = claim_label or source["claim_label"]
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

    for row in rows:
        if row["role"] != "addon":
            row["guess_main"], row["guess_reason"] = (None, "")
            continue
        row["guess_main"], row["guess_reason"] = _guess_main(row, mains)

    order_no = next((_text(link.external_order_no) for link in links
                     if _text(link.external_order_no)), "")
    return {
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
    }


__all__ = [
    "ADDON_PRODUCT_CLASS",
    "ASSIGN_COMMON",
    "build_dock_payload",
    "split_option_copies",
]
