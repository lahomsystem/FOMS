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
        # 쿠폰(2026-08-25) — 위 `discount` 는 상품할인과 쿠폰을 **합친** 값이라 그것만으로는
        # "쿠폰을 썼나"를 알 수 없다. 장수·할인액·판매자 부담분을 따로 낸다.
        "coupon_count": len(payment["coupons"]),
        "coupon_discount": sum(coupon["discount_amount"] for coupon in payment["coupons"]),
        "coupon_seller_burden": sum(
            coupon["seller_burden_amount"] for coupon in payment["coupons"]
            if coupon.get("seller_burden_amount") is not None),
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


def _extra_payment_bucket(entry: dict[str, Any]) -> str:
    """기록 항목 하나가 어느 관계 칸에 들어가는지 고른다 (R1).

    ``relation`` 은 붙이기 때 찍힌다(``promotion.py`` ``_extra_payment_entry``). 값이
    ``REPAY`` 일 때만 재결제 칸이고, **나머지는 전부 추가결제 칸**이다 — 백필 이전에
    기록돼 ``relation`` 이 아예 없는 옛 항목도 여기로 온다. 근거: 지금까지 도크가 관계와
    무관하게 "추가결제"라고 말해 왔으므로(2026-08-24 이전 라벨 하드코딩), 옛 항목을
    추가결제로 두면 사람이 보던 표기가 한 글자도 바뀌지 않는다. 재결제로 추정해 옮기면
    근거 없이 "출고가에 더하지 마세요"를 띄우게 된다.

    Args:
        entry: ``pricing.extra_payments`` 항목 하나.

    Returns:
        ``"repay"`` 또는 ``"addon"``.
    """
    relation = entry.get("relation")
    if isinstance(relation, str) and relation.strip().upper() == "REPAY":
        return "repay"
    return "addon"


def _extra_payment_summary(order: Any) -> dict[str, Any]:
    """주문에 기록된 추가결제(차액·재결제) 건수와 합계 — 관계별로도 가른다.

    출고가·잔금을 바꾸지 않고 기록만 하기로 했으므로(2026-08-19 사용자 확정), 사람이
    "얼마가 더 들어왔는지"를 볼 자리가 필요하다.

    관계를 가르는 이유(R1 · 2026-08-24 스펙 §4.4): ``ADDON`` 에서 이 금액은 원 주문에
    **더** 낸 차액이지만, ``REPAY`` 에서는 원 결제가 환불된 뒤 **다시** 낸 같은 물건값이다.
    한 숫자로 합쳐 "추가결제"라 부르면 담당자가 예약금·입금에 더해 주문 하나 값만큼
    총액을 부풀린다.

    Args:
        order: :class:`models.Order`.

    Returns:
        ``{"count", "total", "addon": {"count","total"}, "repay": {"count","total"}}``.
        ``count``/``total`` 은 **관계 무시 합계**로 그대로 둔다(하위호환 — 도크 payload
        의 ``extra_payment_count``/``extra_payment_total`` 이 이 값을 그대로 싣는다).
    """
    data = getattr(order, "structured_data", None)
    pricing = data.get("pricing") if isinstance(data, dict) else None
    rows = pricing.get("extra_payments") if isinstance(pricing, dict) else None
    by_relation = {"addon": {"count": 0, "total": 0}, "repay": {"count": 0, "total": 0}}
    if not isinstance(rows, list):
        return {"count": 0, "total": 0, **by_relation}
    total = 0
    count = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        bucket = by_relation[_extra_payment_bucket(row)]
        count += 1
        bucket["count"] += 1
        amount = row.get("amount")
        if isinstance(amount, int):
            total += amount
            bucket["total"] += amount
    return {"count": count, "total": total, **by_relation}


#: 재결제로 대체된 옛 집 행에 붙는 설명 — 화면이 그대로 읽는다.
_SUPERSEDED_NOTE = "재결제로 대체된 이전 주문 — 옛 결제는 환불됐습니다"


def _household_relations(links: list[Any]) -> dict[str, str]:
    """집(``external_order_no``)마다 관계 하나 — ``NEW`` 가 아닌 값이 이긴다.

    한 집의 형제 링크가 관계를 섞어 갖는 경우가 있다: 붙이기는 집 전체를 함께 찍지만
    **붙인 뒤에 수집된 형제**는 ``server_default='NEW'`` 로 들어온다(같은 사실을
    ``fulfillment.py`` 의 ``close_now`` 판정도 다룬다). 표시용으로는 "이 집이 왜 붙었나"가
    사실이므로 비-``NEW`` 값을 그 집의 관계로 본다.

    Args:
        links: 이 주문의 :class:`models.ExternalOrderLink` 들(``id`` 오름차순).

    Returns:
        ``{집 주문번호: 관계}``. 관계는 ``NEW``/``ADDON``/``REPAY`` 대문자.
    """
    relations: dict[str, str] = {}
    for link in links:
        key = _text(link.external_order_no)
        value = _text(link.relation).upper() or "NEW"
        if relations.get(key) in (None, "NEW"):
            relations[key] = value
    return relations


def _household_facts(links: list[Any], order_nos: list[str]) -> list[dict[str, Any]]:
    """집마다 관계·대체 여부·화면 라벨을 판정한다 (N2 · 2026-08-26).

    왜 필요한가: 재결제로 집이 둘 붙은 주문에서 화면이 두 집을 **같은 톤으로** 세워,
    담당자가 이미 취소된 옛 집의 옵션 원문을 이번 규격으로 읽을 수 있었다. 반대로
    추가결제는 옛 집이 살아 있다 — ``repay_reconcile.deposit_guidance`` 가 근거다
    (재결제는 예약금을 **바꾸고**, 추가결제는 **더한다**). 두 관계를 같게 다루면 살아
    있는 원 주문을 죽은 것으로 그리게 된다.

    집이 하나뿐이면 라벨을 만들지 않는다 — 보통 주문 화면에 무게를 더하지 않는다.
    관계가 전부 ``NEW`` 인 옛 데이터도 라벨이 없다(재결제로 **추정**하지 않는다).

    Args:
        links: 이 주문의 :class:`models.ExternalOrderLink` 들(``id`` 오름차순).
        order_nos: 수집 순서의 집 주문번호 목록(중복 접음).

    Returns:
        ``[{"order_no", "relation", "superseded", "label", "note"}]`` — ``order_nos`` 와
        같은 순서.
    """
    relations = _household_relations(links)
    values = [relations.get(order_no, "NEW") for order_no in order_nos]
    multi = len(order_nos) > 1
    has_repay = "REPAY" in values
    has_addon = "ADDON" in values
    facts: list[dict[str, Any]] = []
    for order_no, relation in zip(order_nos, values):
        superseded = has_repay and relation == "NEW"
        label = ""
        if multi:
            label = _household_label(relation, superseded=superseded, has_addon=has_addon)
        facts.append({"order_no": order_no, "relation": relation,
                      "superseded": superseded, "label": label,
                      "note": _SUPERSEDED_NOTE if superseded else ""})
    return facts


def _household_label(relation: str, *, superseded: bool, has_addon: bool) -> str:
    """집 하나가 화면에서 불릴 이름 — 관계마다 문구가 다르다.

    Args:
        relation: 그 집의 관계(``NEW``/``ADDON``/``REPAY``).
        superseded: 재결제로 대체된 옛 집인가.
        has_addon: 이 주문에 추가결제 집이 있는가(그때만 원 주문을 굳이 이름 붙인다).

    Returns:
        화면 라벨. 이름 붙일 근거가 없으면 빈 문자열.
    """
    if relation == "REPAY":
        return "이번 주문(재결제)"
    if relation == "ADDON":
        return "추가결제분"
    if superseded:
        return "이전 주문"
    return "원 주문" if has_addon else ""


def _household_amounts(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """집(``external_order_no``)마다 상품주문 결제액 합계와 **못 읽은 건수** (D3).

    ``amount`` 는 원본 ``totalPaymentAmount`` 가 int 일 때만 실린다(:func:`_row_source` —
    원본 파손이면 그 행 전체가 빈 값으로 온다). 못 읽은 행을 0 으로 더하면 합계가 **조용히
    작아지고**, 그 숫자가 예약금(선금)을 타고 ``잔금 = 출고가 − 예약금`` 으로 흘러가
    고객에게 과다 청구된다. 그래서 더하지 않고 **센다** — 화면·안내가 "모름 N건"을
    말할 수 있으면 사람이 원본을 열어 본다.

    Args:
        rows: :func:`build_dock_payload` 가 만든 행 목록.

    Returns:
        ``{집 주문번호: {"amount_total": int, "amount_unknown": int}}``.
    """
    totals: dict[str, dict[str, int]] = {}
    for row in rows:
        key = _text(row.get("external_order_no"))
        bucket = totals.setdefault(key, {"amount_total": 0, "amount_unknown": 0})
        amount = row.get("amount")
        if isinstance(amount, int):
            bucket["amount_total"] += amount
        else:
            bucket["amount_unknown"] += 1
    return totals


#: 예약금(선금) 안내 상태 4종 — 화면은 이 값으로만 분기한다.
DEPOSIT_HINT_STATES = ("match", "differs", "over", "unknown")

#: 재결제로 대체된 집이 섞여 있을 때 합계에 붙는 단서.
_DEPOSIT_SUPERSEDED_NOTE = "환불된 이전 주문은 뺀 금액입니다"


def _deposit_note(*, has_superseded: bool, claim_label: str) -> str:
    """예약금 합계가 **무엇을 빼고 무엇을 안 뺐는지** 말하는 단서 (D3).

    Args:
        has_superseded: 재결제로 대체된 옛 집이 있는가(그 집 금액은 합계에서 뺐다).
        claim_label: 취소·반품 라벨(:func:`mapping.extract_claim` 의 ``label``).

    Returns:
        단서 문장. 붙일 근거가 없으면 빈 문자열.
    """
    parts: list[str] = []
    if has_superseded:
        parts.append(_DEPOSIT_SUPERSEDED_NOTE)
    label = _text(claim_label)
    if label:
        # 클레임 환불액은 ``totalPaymentAmount`` 에서 아직 빠지지 않는다(결제 시점 값).
        parts.append(f"{label} 건이 있어 환불액은 아직 빠지지 않은 금액입니다")
    return " · ".join(parts)


def _deposit_target(households: list[dict[str, Any]]) -> tuple[int, int]:
    """살아 있는 집(대체되지 않은 집)들의 결제액 합계와 못 읽은 건수.

    Args:
        households: :func:`_household_facts` 결과에 :func:`_household_amounts` 가 병합된 목록.

    Returns:
        ``(합계, 모름 건수)``.
    """
    live = [fact for fact in households if not fact.get("superseded")]
    return (sum(int(fact.get("amount_total") or 0) for fact in live),
            sum(int(fact.get("amount_unknown") or 0) for fact in live))


def _deposit_hint(order: Any, households: list[dict[str, Any]], *,
                  claim_label: str = "") -> dict[str, Any]:
    """예약금(선금)에 넣을 금액을 **문장으로** 말한다 — 넣지는 않는다 (D3).

    도크는 붙인 뒤 **며칠 뒤** 화면이라 재결제 카드의 상대값(``current + amount``)을 쓰면
    사람이 이미 고쳐 놓은 값에 한 번 더 더하게 된다. 그래서 **절대 target**(살아 있는 집들의
    결제액 합)을 먼저 정하고 문장만 :func:`repay_reconcile.deposit_guidance` 에 위임한다.
    ``over`` 에서 "낮추라"고 말하지 않는 이유: 네이버 밖 입금이 정당할 수 있고 그 지시가
    ``잔금 = 출고가 − 예약금`` 을 타고 고객 청구로 나간다.

    Args:
        order: 도크가 실린 :class:`models.Order` (예약금 현재값을 읽는다).
        households: ``amount_total``·``amount_unknown`` 이 병합된 집 사실 목록.
        claim_label: 이 주문의 취소·반품 라벨(없으면 빈 문자열).

    Returns:
        ``{"state", "current", "target", "target_display", "diff", "sentence",
        "copy_value", "unknown_count", "note"}``. ``copy_value`` 는 쉼표·단위 없는 정수
        문자열이고 ``over``·``unknown`` 에서는 빈 문자열이다(복사할 정답이 없다).
        ``target_display`` 는 사람이 읽는 표기(``"872,200원"``) — 화면이 돈을 다시
        포맷하지 않게 서버가 문장과 **같은 자리에서** 만든다.
    """
    from foms.services.erp_display import erp_deposit_amount_from_structured
    from foms.services.integrations.naver_commerce.repay_reconcile import deposit_guidance

    current = int(erp_deposit_amount_from_structured(
        getattr(order, "structured_data", None) or {}) or 0)
    superseded = any(fact.get("superseded") for fact in households)
    target, unknown = _deposit_target(households)
    hint: dict[str, Any] = {
        "state": "unknown", "current": current, "target": None, "diff": None,
        "target_display": "", "sentence": "", "copy_value": "", "unknown_count": unknown,
        "note": _deposit_note(has_superseded=superseded, claim_label=claim_label)}
    if unknown:
        hint["sentence"] = (f"금액을 못 읽은 상품주문이 {unknown}건 있어 네이버 결제액"
                            " 합계를 내지 못했습니다 — 원본을 열어 확인하세요.")
        return hint
    diff = target - current
    hint.update({"target": target, "diff": diff, "copy_value": str(target),
                 "target_display": f"{target:,}원"})
    if diff == 0:
        hint["state"] = "match"
        hint["sentence"] = f"예약금(선금) {current:,}원 — 네이버 결제액과 같습니다."
    elif diff < 0:
        hint.update({"state": "over", "copy_value": ""})
        hint["sentence"] = (f"예약금(선금) {current:,}원이 네이버 결제액 {target:,}원보다"
                            f" {-diff:,}원 많습니다 — 네이버 밖 입금이면 그대로 두세요.")
    else:
        hint["state"] = "differs"
        hint["sentence"] = deposit_guidance(
            order, new_amount=target if superseded else diff,
            relation="REPAY" if superseded else "ADDON")["sentence"]
    return hint



def _main_qualifier(row: dict[str, Any], fact: dict[str, Any]) -> str:
    """이름이 겹치는 본품을 갈라 말하는 짧은 꼬리표.

    집 라벨이 있으면 그것부터, 그 뒤에 **실제로 있는 번호**의 뒤 4자리를 붙인다. 값을
    지어내지 않는다 — 집 번호가 비면 상품주문번호 뒤 4자리로 떨어진다(둘 다 원본 값이다).

    Args:
        row: 본품 행.
        fact: 그 행이 속한 집의 사실(:func:`_household_facts` 항목). 없으면 빈 dict.

    Returns:
        ``"이전 주문 …4381"`` 같은 문자열. 붙일 근거가 없으면 빈 문자열.
    """
    tail = _text(row.get("external_order_no")) or _text(row.get("external_id"))
    parts = [part for part in (_text(fact.get("label")),
                               f"…{tail[-4:]}" if tail else "") if part]
    return " ".join(parts)


def _main_entries(mains: list[dict[str, Any]],
                  facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """귀속 드롭다운·머리말이 읽는 본품 항목 — 이름이 겹치면 갈라 말한다 (N2).

    실화면 결함(2026-08-26): 집이 둘인 주문에서 본품 선택지 두 개의 이름이 **글자 하나까지
    같아**, 고르는 사람이 어느 쪽인지 분간할 근거가 화면에 없었다. 이름은 원문 그대로 두고
    (복사·검색이 깨지면 안 된다) 꼬리표를 따로 실어 화면이 이름 **앞에** 붙여 읽게 한다 —
    뒤에 붙이면 좁은 select 에서 잘려 다시 같아진다.

    Args:
        mains: 본품 행 목록.
        facts: :func:`_household_facts` 결과.

    Returns:
        ``[{"external_id", "label", "order_no", "relation", "superseded", "qualifier"}]``.
    """
    by_no = {fact["order_no"]: fact for fact in facts}
    labels = [row["product_name"] or row["external_id"] for row in mains]
    entries: list[dict[str, Any]] = []
    for row, label in zip(mains, labels):
        fact = by_no.get(row.get("external_order_no", "")) or {}
        entries.append({
            "external_id": row["external_id"],
            "label": label,
            "order_no": row.get("external_order_no", ""),
            "relation": fact.get("relation", "NEW"),
            "superseded": bool(fact.get("superseded")),
            # 이름이 유일하면 덧붙이지 않는다 — 이미 이름이 구분한다.
            "qualifier": _main_qualifier(row, fact) if labels.count(label) > 1 else "",
        })
    return entries


#: 도크에서 워크벤치 **처리 pane** 으로 가는 링크를 낼 수 있는 역할 (R2).
#:
#: 도크가 실리는 ``/edit/<id>`` 는 ADMIN·MANAGER·STAFF 가 연다
#: (``foms/web/orders/edit.py`` ``edit_order`` 의 ``role_required``). 반면 그 링크가
#: 여는 워크벤치 처리 pane 은 발주확인·발송처리·취소처리 같은 **불가역** 버튼이 무장된
#: 화면이다. 링크를 무조건 내면 STAFF 가 자기가 여는 **모든** 네이버 주문에서 클릭 두
#: 번으로 거기 닿는다. 계약(2026-08-23 v3 §0-3)이 규제하는 것은 권한이 아니라 **통로**라,
#: 통로 자체를 두 역할에만 만든다 — 화면에서 숨기는 게 아니라 응답에 싣지 않는다(§0-4).
WORKBENCH_LINK_ROLES = ("ADMIN", "MANAGER")


def _workbench_link_url(viewer: Any, rows: list[dict[str, Any]]) -> Optional[str]:
    """도크 머리말에 낼 **워크벤치 처리 탭 링크** 주소 (R2 · 2026-08-24 스펙 §6).

    필요한 이유: 재결제 집은 발주확인과 발송처리 사이에 며칠이 뜬다. 그 사이 담당자가
    ``확인 완료 — 큐에서 빼기`` 를 먼저 누르면 그 집이 목록 두 원천에서 모두 빠져
    발송처리 버튼에 도달할 길이 주소 수기밖에 남지 않는다(스펙 §5 함정 1).

    어느 집을 여는가: **가장 나중에 수집된 링크**(``rows`` 는 ``link.id`` 오름차순)를
    가리킨다. 워크벤치 pane 은 링크가 속한 집을 ``external_order_no`` 로 되찾으므로
    (``naver_ingest.py`` ``_household_of_link``) 집 안에서는 어느 링크든 같다. 주문에
    집이 둘 이상 붙은 경우(재결제·추가결제로 나중에 붙인 집)에는 **나중에 온 집**이
    아직 처리가 남은 쪽이다 — 원 주문 집은 이미 주문으로 승격돼 있다.

    Args:
        viewer: 지금 편집 화면을 연 :class:`models.User` (미인증이면 None).
        rows: :func:`build_dock_payload` 가 만든 행 목록(``link.id`` 오름차순).

    Returns:
        ``/admin/naver-ingest/triage?tab=work&link_id=<N>``. 역할이 아니거나 워크벤치
        게이트가 꺼져 있으면 ``None`` (그러면 화면에 앵커가 아예 생기지 않는다).
    """
    if not rows or viewer is None:
        return None
    role = str(getattr(viewer, "role", "") or "").strip().upper()
    if role not in WORKBENCH_LINK_ROLES:
        return None
    from foms.services.feature_flags import is_naver_workbench_enabled

    # 게이트 off 인 사람에게 링크를 내면 옛 트리아지 화면으로 떨어진다 — 없는 길이다.
    if not is_naver_workbench_enabled(getattr(viewer, "id", None)):
        return None
    from flask import url_for

    return url_for("admin.naver_ingest_triage", tab="work", link_id=rows[-1]["link_id"])


def _workbench_order_no(links: list[Any], rows: list[dict[str, Any]]) -> Optional[str]:
    """``_workbench_link_url`` 이 여는 집의 주문번호(없으면 None).

    ``_workbench_link_url`` 과 **같은 행**(``rows[-1]``)에서 값을 끌어온다. 머리말이
    말하는 집과 링크가 여는 집이 갈리던 결함(2026-08-25)의 재발 방지다 — 한쪽만
    고치면 다음 사람이 반대쪽을 바꿔 다시 어긋난다.

    Args:
        links: 이 주문의 :class:`models.ExternalOrderLink` 들(``id`` 오름차순).
        rows: 그 링크들로 만든 행 목록(같은 순서).

    Returns:
        집 주문번호 문자열. 행이 없거나 값이 비면 None.
    """
    if not rows:
        return None
    target = rows[-1]["link_id"]
    for link in links:
        if link.id == target:
            return _text(link.external_order_no) or None
    return None


def build_dock_payload(db: Any, order: Any, *,
                       viewer: Any = None) -> Optional[dict[str, Any]]:
    """주문의 네이버 수집 링크들을 도크 표시용 payload 로 만든다.

    Args:
        db: 요청 스코프 DB 세션.
        order: 대상 :class:`models.Order`.
        viewer: 지금 화면을 연 :class:`models.User`. 워크벤치 링크를 낼지 판정하는 데만
            쓴다(R2) — 넘기지 않으면 링크는 ``None`` 이다.

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
            # 이 행이 **어느 집에서 왔는가**(N2). 예전에는 집 번호가 payload 최상위에만
            # 있어서, 집이 둘인 주문에서 화면은 행을 집별로 가를 근거가 없었다.
            "external_order_no": _text(link.external_order_no),
            # 관계 정본은 링크 컬럼이다(models.ExternalOrderLink.relation —
            # NEW/ADDON/REPAY). 행 단위로 실어 화면이 추측하지 않게 한다.
            "relation": _text(link.relation).upper() or "NEW",
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
            # 쿠폰은 상품주문(행)마다 붙는다 — 집 합계는 이 값들을 더해서 만든다.
            "coupon_count": source["coupon_count"],
            "coupon_discount": source["coupon_discount"],
            "coupon_seller_burden": source["coupon_seller_burden"],
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

    # 집 번호는 **여러 개일 수 있다**. 주문 하나에 재결제·추가결제 집이 나중에 붙으면
    # 도크는 두 집의 행을 함께 싣는데, 머리말은 그중 첫 집 번호만 말했다. 그런데
    # `워크벤치에서 열기` 는 **가장 나중 집**을 연다(위 _workbench_link_url) — 담당자가
    # 읽은 번호와 눌러서 열리는 집이 어긋나던 자리다(2026-08-25 수정). 순서는 링크
    # id 오름차순(= 수집 순서)이고 중복은 접는다.
    order_nos: list[str] = []
    for link in links:
        text = _text(link.external_order_no)
        if text and text not in order_nos:
            order_nos.append(text)
    order_no = order_nos[0] if order_nos else ""
    # 집마다 관계·대체 여부를 판정하고, 그 사실을 **행에도** 찍는다(N2). 행 단위로 찍는
    # 이유: 귀속(추가옵션이 어느 본품 소속인가)은 집 경계를 넘을 수 있어, 화면이 그룹
    # 머리말만 보고 흐리면 살아 있는 집의 행까지 함께 흐려진다.
    households = _household_facts(links, order_nos)
    superseded_nos = {fact["order_no"] for fact in households if fact["superseded"]}
    for row in rows:
        row["superseded"] = row["external_order_no"] in superseded_nos
    # 집 단위 결제액(D3). 못 읽은 금액은 0 으로 더하지 않고 센다 — 조용히 작아진 합계가
    # 예약금(선금)을 타고 잔금 과다 청구로 흘러가는 것을 막는다.
    amounts = _household_amounts(rows)
    for fact in households:
        fact.update(amounts.get(fact["order_no"],
                                {"amount_total": 0, "amount_unknown": 0}))
    extra = _extra_payment_summary(order)
    return {
        # 추가결제(차액)·재결제 기록 — 금액은 기록만 하고 출고가·잔금은 사람이 반영한다(T16-F).
        # 아래 둘은 **관계 무시 합계**다(하위호환 — 화면 게이트가 이 숫자를 본다).
        "extra_payment_count": extra["count"],
        "extra_payment_total": extra["total"],
        # 관계별 분해(R1) — 도크가 ADDON/REPAY 를 다른 문구로 말하기 위한 자리.
        "extra_payment_by_relation": {"addon": extra["addon"], "repay": extra["repay"]},
        # 집 전체 쿠폰 합계. 행마다 흩어 두면 사람이 암산해야 한다.
        "coupon_count": sum(int(row["coupon_count"] or 0) for row in rows),
        "coupon_discount": sum(int(row["coupon_discount"] or 0) for row in rows),
        "coupon_seller_burden": sum(int(row["coupon_seller_burden"] or 0) for row in rows),
        "order_no": order_no,
        # 집이 둘 이상인 주문에서 머리말이 사실을 말하게 하는 자리. 화면은 이 목록을
        # 쓰고, `order_no`(첫 집)는 하위호환으로만 남긴다.
        "order_nos": order_nos,
        # 집마다의 관계·라벨(N2). 화면은 이 목록으로 **이전 주문 / 이번 주문**을 가른다.
        # 집이 하나면 라벨이 전부 빈 문자열이라 화면이 오늘과 똑같이 그려진다.
        "households": households,
        # 예약금(선금) 안내(D3). 문장은 **서버가** 만든다 — 재결제 화면과 같은 말을 써야
        # 두 화면이 같은 규칙으로 읽힌다. 화면은 그리기와 복사까지고 **자동 기입은 없다**.
        "deposit_hint": _deposit_hint(order, households, claim_label=claim_label),
        # 위 `workbench_url` 이 실제로 여는 집의 번호. 머리말에서 그 집을 표시해
        # "읽은 번호 != 열리는 집" 을 없앤다. **주소와 같은 행에서 끌어온다** — 둘이
        # 갈리면 이 수정이 무의미해지므로 `rows[-1]` 을 공통 출처로 못박는다.
        "workbench_order_no": _workbench_order_no(links, rows),
        # 워크벤치 처리 탭으로 돌아가는 길(R2). 역할·게이트가 아니면 **None 이 실린다** —
        # 화면에서 숨기는 게 아니라 주소를 만들지 않는다(계약 §0-4).
        "workbench_url": _workbench_link_url(viewer, rows),
        "rows": rows,
        # 본품 항목 — 이름이 겹치는 것끼리는 꼬리표로 갈라 말한다(N2).
        "mains": _main_entries(mains, households),
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
