"""네이버 상품주문 상세 → FOMS Order 필드 매핑 (NAVER-INGEST-01 §3.6).

**순수 함수만** 둔다(DB·네트워크 없음). 주문 생성은 :mod:`~foms.services.integrations.naver_commerce.ingest`
가 :func:`~foms.services.orders.order_create.create_order` 를 통해 한다.

설계 메모:

* **좌표를 `Order.lat/lng` 에 넣지 않는다.** 네이버 좌표는 주문서에 적힌 주소 기준이고 실제
  고객(시공) 주소와 다른 경우가 많다. 넣으면 ``geocode_status='success'`` 라 재지오코딩에서도
  빠져 틀린 값이 조용히 굳는다. 수집 주문도 기존 주문과 똑같이 지오코딩한다.
  네이버 좌표는 참고용으로 ``structured_data['naver']`` 에만 남긴다.
* **주문자 ≠ 수취인** 케이스가 실재한다(대리주문). 배송지 이름/전화를 고객으로 쓰고,
  주문한 사람은 ``parties.buyer`` 에 따로 보존한다. ``parties.orderer`` 는 **발주사**
  자리라 여기에 사람 이름을 넣으면 안 된다 — 넣었더니 알림톡이 하우드 프로필로 나가고
  도면에 하우드 로고가 찍혔다(ORDERER-AXIS-01). 발주사는 항상 ``DEFAULT_ORDERER_NAME``.
* ``takingAddress`` 는 반품 수거지(자사 주소)다. 고객 정보가 아니라서 버린다.
* ``productOption`` 은 **원문 그대로** 보관한다(v1 자동 파싱 없음 — 스펙 §7 Q2).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from foms.services.integrations.naver_commerce.constants import (
    ADDON_PRODUCT_CLASS,
    DEFAULT_ORDERER_NAME,
    SOURCE_MARKER,
)

KST = timezone(timedelta(hours=9))

#: 주문 생성에 반드시 있어야 하는 값(없으면 쓰레기 주문 대신 PENDING_REVIEW).
REQUIRED_FIELDS = ("external_id", "customer_name", "phone", "address", "product")

#: 신규 수집 대상 상태. 결제완료만 가져온다(스펙 §3.3 — 상품 필터는 없다).
COLLECTIBLE_STATUS = "PAYED"


class NaverMappingError(ValueError):
    """필수 값 누락·형식 불일치 — 주문을 만들지 않고 보류(PENDING_REVIEW) 로 남긴다."""


def _text(value: Any) -> str:
    """None/공백을 빈 문자열로 정규화한 문자열."""
    if value is None:
        return ""
    return str(value).strip()


def _int(value: Any) -> int:
    """금액류를 정수로. 콤마·소수점·빈 값을 견딘다(파싱 실패는 0)."""
    raw = _text(value).replace(",", "")
    if not raw:
        return 0
    try:
        return int(float(raw))
    except ValueError:
        return 0


def _bool(value: Any) -> bool:
    """참/거짓 값 정규화. 문자열 ``"false"``·``"0"`` 을 참으로 읽지 않는다.

    원본은 JSONB 를 왕복하면서 불리언이 문자열로 굳는 경우가 있다. ``bool("false")`` 는
    True 라서 그대로 쓰면 **송장 오류가 아닌 건이 오류로 뜬다**.
    """
    if isinstance(value, str):
        return value.strip().lower() not in ("", "false", "0", "no", "n")
    return bool(value)


def _known_int(source: dict, key: str) -> Optional[int]:
    """값이 **실제로 온 경우에만** 정수를 준다(키가 없거나 빈 값이면 None).

    "0 이 왔다"와 "안 왔다"를 가르기 위한 헬퍼다. 둘을 같이 0 으로 뭉개면 값이 없는
    원본이 "초기값 0"으로 읽혀 없는 부분취소가 생긴다.

    Args:
        source: 읽을 dict.
        key: 원본 필드명.

    Returns:
        정수(파싱 실패는 0), 값이 아예 없으면 None.
    """
    if not isinstance(source, dict) or key not in source:
        return None
    if _text(source.get(key)) == "":
        return None
    return _int(source.get(key))


def unwrap_detail(detail: dict) -> tuple[dict, dict, dict]:
    """상세 응답 1건을 ``(order, product_order, shipping_address)`` 로 푼다.

    네이버 응답은 ``{"order": {...}, "productOrder": {...}}`` 중첩이지만, 배치 조회 형태에
    따라 평평하게 오는 경우도 있어 양쪽을 모두 받아준다.

    Args:
        detail: ``product-orders/query`` 응답의 항목 1개.

    Returns:
        ``(order, productOrder, shippingAddress)`` — 없으면 빈 dict.
    """
    if not isinstance(detail, dict):
        return ({}, {}, {})
    order = detail.get("order") if isinstance(detail.get("order"), dict) else {}
    product_order = (
        detail.get("productOrder") if isinstance(detail.get("productOrder"), dict) else detail
    )
    shipping = product_order.get("shippingAddress")
    if not isinstance(shipping, dict):
        shipping = detail.get("shippingAddress") if isinstance(detail.get("shippingAddress"), dict) else {}
    return (order, product_order, shipping)


def extract_external_id(detail: dict) -> str:
    """멱등 키(``productOrderId``)를 뽑는다. 없으면 빈 문자열."""
    _order, product_order, _shipping = unwrap_detail(detail)
    return _text(product_order.get("productOrderId"))


def is_collectible(status_entry: dict) -> bool:
    """변경분 항목이 신규 수집 대상(결제완료)인지 판정한다.

    ``last-changed-statuses`` 는 상태 변경 이벤트를 전부 준다(3일에 163건). 그중
    ``PAYED`` 만 신규 주문 후보다. 상품 필터는 없다(전 상품 수집 — 스펙 §7 Q4).
    """
    if not isinstance(status_entry, dict):
        return False
    return _text(status_entry.get("productOrderStatus")).upper() == COLLECTIBLE_STATUS


def parse_order_datetime(value: Any) -> tuple[str, Optional[str]]:
    """네이버 ISO 시각을 KST 기준 ``(YYYY-MM-DD, HH:MM)`` 으로 바꾼다.

    파싱 실패 시 날짜는 빈 문자열, 시각은 None 을 준다(호출자가 오늘 날짜로 대체).

    Args:
        value: ``2026-08-12T14:23:11.000+09:00`` 형태의 문자열.

    Returns:
        ``(날짜문자열, 시각문자열|None)``.
    """
    raw = _text(value)
    if not raw:
        return ("", None)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        # 날짜만 온 경우(YYYY-MM-DD)는 그대로 쓴다.
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            return (raw, None)
        return ("", None)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=KST)
    kst = parsed.astimezone(KST)
    return (kst.strftime("%Y-%m-%d"), kst.strftime("%H:%M"))


def build_address(shipping: dict) -> str:
    """``baseAddress`` + ``detailedAddress`` 를 하나의 주소 문자열로 결합한다."""
    base = _text(shipping.get("baseAddress"))
    detail = _text(shipping.get("detailedAddress"))
    return " ".join(part for part in (base, detail) if part).strip()


def extract_shipping_memo(detail: dict) -> str:
    """배송 요청사항(배송메모) 원문을 뽑는다.

    **실위치는 ``productOrder.shippingMemo`` 다** — 2026-08-14 스테이징 실수집 42건 전수
    조사로 확인했다(13건 비어 있지 않음). 초기 구현은 ``shippingAddress.shippingMemo`` 를
    읽었는데 그 키는 응답에 아예 없어서 **항상 빈 값**이었다(조용한 유실). 폴백 2개는
    응답이 평평하게 오는 경로와 주문 단위로 오는 변형 대비로 남긴다.

    Args:
        detail: 상품주문 상세 1건.

    Returns:
        메모 원문(없으면 빈 문자열).
    """
    order, product_order, shipping = unwrap_detail(detail)
    return (
        _text(product_order.get("shippingMemo"))
        or _text(shipping.get("shippingMemo"))
        or _text(order.get("shippingMemo"))
    )


#: 사람이 읽는 클레임 상태 라벨. 없는 값은 원문 그대로 보여준다(모르는 상태를 숨기지 않는다).
CLAIM_STATUS_LABELS = {
    "CANCEL_REQUEST": "취소 요청",
    "CANCEL_REQUESTED": "취소 요청",
    "CANCELING": "취소 처리중",
    "CANCEL_DONE": "취소 완료",
    "CANCEL_REJECT": "취소 거부",
    "RETURN_REQUEST": "반품 요청",
    "RETURN_REQUESTED": "반품 요청",
    # 수거는 반품·교환 **양쪽**에서 온다. `반품 수거중` 이라고 적으면 교환 건에서
    # 화면이 틀린 이름을 말한다 — 어느 쪽인지는 `type`(claimType)이 말한다.
    "COLLECTING": "수거중",
    "COLLECT_DONE": "수거 완료",
    "RETURN_DONE": "반품 완료",
    # 거부 3종은 대칭이어야 한다. 지금까지 `CANCEL_REJECT` 만 있어서 반품·교환 거부는
    # 배지에 영문 상수가 그대로 떴다(T8-S0).
    "RETURN_REJECT": "반품 거부",
    "EXCHANGE_REQUEST": "교환 요청",
    "EXCHANGE_DONE": "교환 완료",
    "EXCHANGE_REJECT": "교환 거부",
    "PURCHASE_DECISION_HOLDBACK": "구매확정 보류",
}

#: 사람이 읽는 클레임 **사유** 라벨. 네이버는 사유를 영문 상수로 준다(``MISTAKE_ORDER`` 등).
#: 알림 본문에 원문 그대로 실으면 받는 사람이 해독해야 한다 — 아는 값만 한국어로 바꾸고
#: 모르는 값은 원문을 그대로 남긴다(상태 라벨과 같은 정책: 모르는 값을 숨기지 않는다).
CLAIM_REASON_LABELS = {
    "MISTAKE_ORDER": "주문 실수",
    "SIMPLE_INTENT_CHANGED": "단순 변심",
    # 2026-08-27 정정: 이 둘은 다른 코드다. `INTENT_CHANGED` 는 **우리가 보내는** 반품
    # 사유이기도 해서(변심·주문취소·재결제 — `fulfillment.RETURN_REASONS`), "단순 변심"
    # 으로 라벨을 붙이면 재결제 대기 건이 5분 뒤 담당자 알림에 **고객 변심**으로 뜬다.
    # 네이버 범례 원문 그대로 "구매 의사 취소" 로 둔다.
    "INTENT_CHANGED": "구매 의사 취소",
    # 2026-08-27 운영 실물로 확인한 코드다(id=422 본문에 원문 노출됐다) — 추측 철자
    # ``COLOR_SIZE_CHANGE`` 만 있어서 라벨이 안 붙었다. 실측 코드를 정본으로 둔다.
    "COLOR_AND_SIZE": "색상·사이즈 변경",
    "COLOR_SIZE_CHANGE": "색상·사이즈 변경",
    "WRONG_PRODUCT": "다른 상품 잘못 주문",
    "SOLD_OUT": "품절",
    "DELAYED_DELIVERY": "배송 지연",
    "PRODUCT_UNSATISFIED": "상품 불만족",
    "PRODUCT_DEFECT": "상품 하자",
    "WRONG_DELIVERY": "오배송",
    "WRONG_DELIVERY_INFO": "배송지 정보 오류",
    # 2026-08-27 보강. 위 목록에 없어서 화면·알림에 영문 상수가 그대로 뜨던 코드들이다.
    # 앞 5개는 네이버 반품 사유 범례 11종(#639) 중 빠져 있던 것, 뒤 6개는 **읽기 전용**
    # 코드다(#1137: 실제 주문 데이터의 사유 코드가 보낼 수 있는 코드보다 많다).
    # `WRONG_DELAYED_DELIVERY` 는 스테이징 실측값인데(392행 전수: 등장 18회 / 링크 9건)
    # 라벨이 없어 화면에 영문 상수가 그대로 떴다.
    "WRONG_ORDER": "다른 상품 잘못 주문",
    "DROPPED_DELIVERY": "배송 누락",
    "BROKEN": "상품 파손",
    "INCORRECT_INFO": "상품 정보 상이",
    "WRONG_OPTION": "다른 상품 잘못 배송",
    "WRONG_DELAYED_DELIVERY": "배송 오류·지연",
    "DELAYED_DELIVERY_BY_PURCHASER": "배송 지연(구매자 사유)",
    "PRODUCT_UNSATISFIED_BY_PURCHASER": "상품 불만족(구매자 사유)",
    "BROKEN_AND_BAD": "파손·불량",
    "UNDER_QUANTITY": "수량 부족",
    "ETC": "기타",
}


def claim_reason_text(code: str) -> str:
    """클레임 사유 코드를 사람이 읽는 문구로. 모르는 코드는 원문 그대로.

    Args:
        code: 네이버가 준 사유 코드(``cancelReason``·``returnReason``).

    Returns:
        한국어 라벨. 매핑에 없으면 입력 원문(빈 값이면 빈 문자열).
    """
    raw = (code or "").strip()
    return CLAIM_REASON_LABELS.get(raw.upper(), raw)


#: 클레임 상세가 실려 오는 **부모 블록 이름 후보**(우선순위 순).
#:
#: 실물로 관측된 것은 ``cancel`` 뿐이다 — F-1(고객이 쓴 사유 원문)이 그 경로로 읽고 있고,
#: 스테이징 실데이터에서 확인된 반품은 전부 이미 끝난 것(``RETURN_DONE``)이라 반품 상세가
#: 어느 이름으로 실려 오는지는 **아직 관측되지 않았다**. 나머지 이름은 반품·교환이 별도
#: 블록으로 오는 변형 대비 폴백이다 — 없으면 빈 값이 되고 예외는 나지 않는다
#: (모르는 모양을 추측해서 채우지 않는다).
CLAIM_BLOCK_KEYS = ("cancel", "returnInfo", "return", "exchange")

#: **반품 축 전용** 블록 이름 — ``cancel`` 이 없다 (2026-08-27 CEO A1).
#: 취소 블록에도 ``refundExpectedDate``·``refundStandbyStatus`` 가 실려 온다. 그것을
#: 반품 축으로 읽으면 **취소만 된 건이 "반품 진행" 이라고 말한다** — 스테이징 실데이터
#: 344 링크 중 **50건**이 그랬다(머리의 배지는 `취소 완료` 인데 몸통은 `반품 진행`).
#: 환불 시각은 취소에도 반품에도 있지만 **축이 다르다**: 취소 환불은 취소 줄이 맡는다.
#: ``exchange`` 는 남긴다 — 수거는 반품·교환 **양쪽**에서 온다(N1 라벨 규칙과 같다).
RETURN_BLOCK_KEYS = ("returnInfo", "return", "exchange")


def _claim_holders(detail: Any) -> tuple[dict, ...]:
    """클레임 블록이 실려 올 수 있는 **바깥 그릇**들을 우선순위 순으로 준다.

    ``(detail, currentClaim, beforeClaim)`` 순이다. 앞선 그릇이 이긴다 — 지금 도는
    클레임(``currentClaim``)이 지나간 클레임(``beforeClaim``)보다 먼저다.

    **``beforeClaim`` 은 2026-09-02 에 넣은 안전장치다.** 커머스API 공지
    "구.클레임 필드 지원 종료 예정 안내 (10/28)"(Discussion #3608)는 **2026년 10월 28일**
    부터 우리가 쓰는 바로 그 조회 API(``POST /v1/pay-order/seller/product-orders/query``)
    응답에서 ``data[n].cancel``·``return``·``exchange`` 를 **반환하지 않는다**고 적고,
    대체 노드로 ``currentClaim.*`` 과 **``beforeClaim.exchange``** 를 든다.

    우리는 이미 ``detail`` 과 ``currentClaim`` 을 함께 읽어 취소·반품은 그날을 넘긴다.
    문제는 ``beforeClaim`` 을 **한 번도 읽지 않던 것**이었다 — 거기 실려 오는 클레임을
    "클레임 없음"으로 읽으면 :func:`blocks_irreversible` 이 열리고, 이미 환불된 집에
    발송처리가 나간다(불가역·오발송).

    공지 표가 ``beforeClaim`` 을 **교환에만** 적었다는 점은 그대로 남긴다 — 취소·반품도
    그리로 가는지는 **문서에 없다**. 그래서 추정으로 판정을 바꾸지 않고, **읽는 그릇만**
    늘렸다. 거기 아무것도 안 오면 지금과 똑같이 동작하고, 오면 안 놓친다.

    Args:
        detail: 상품주문 상세 1건.

    Returns:
        비어 있지 않은 dict 그릇들(우선순위 순).
    """
    if not isinstance(detail, dict):
        return ()
    holders: list[dict] = [detail]
    for key in ("currentClaim", "beforeClaim"):
        block = detail.get(key)
        if isinstance(block, dict) and block:
            holders.append(block)
    return tuple(holders)


def _claim_blocks(detail: Any) -> list[dict]:
    """클레임 상세가 들어 있을 수 있는 블록들을 **우선순위 순**으로 모은다.

    ``cancel`` 이 먼저다 — 지금 값을 실제로 주고 있는 경로라 기존 동작이 그대로 유지된다.
    그 다음이 반품·교환 블록, 마지막이 ``currentClaim`` 자체다.

    Args:
        detail: 상품주문 상세 1건(dict 가 아니면 빈 목록).

    Returns:
        비어 있지 않은 dict 블록 목록(중복 이름은 그대로 둔다 — 앞선 것이 이긴다).
    """
    if not isinstance(detail, dict):
        return []
    holders = _claim_holders(detail)
    blocks: list[dict] = []
    for holder in holders:
        for key in CLAIM_BLOCK_KEYS:
            block = holder.get(key)
            if isinstance(block, dict) and block:
                blocks.append(block)
    # 그릇 자체가 **평평한 클레임**으로 오는 모양도 있다(실데이터로 확인된
    # ``currentClaim`` 이 그렇다). ``detail`` 은 제외한다 — 그건 상세 전체지
    # 클레임이 아니다. 2026-09-02: ``beforeClaim`` 도 같은 대접을 받는다,
    # 안 그러면 평평하게 실려 온 지나간 클레임을 통째로 놓친다(#3608 안전장치).
    blocks.extend(holders[1:])
    return blocks


#: 취소 축 전용 블록. 반품 축(:data:`RETURN_BLOCK_KEYS`)과 **겹치지 않게** 갈라 둔다 —
#: 한 목록으로 합치면 취소 블록의 환불 필드가 반품 진행으로 새어 취소만 된 건에
#: "반품 진행" 줄이 뜬다(2026-08-27 CEO A1 이 고친 그 결함).
CANCEL_BLOCK_KEYS = ("cancel",)


def _cancel_blocks(detail: Any) -> list[dict]:
    """**취소 축**이 읽을 블록만 모은다 — 반품 블록은 넣지 않는다.

    ``currentClaim`` 은 실데이터에서 ``{"cancel": …}`` 래퍼라 그 안의 ``cancel`` 까지 본다
    (2026-08-27 스테이징 83건 관측). 래퍼 자체는 넣지 않는다 — 평평한 클레임이 아니다.

    Args:
        detail: 상품주문 상세 1건(dict 가 아니면 빈 목록).

    Returns:
        비어 있지 않은 dict 블록 목록. 앞선 것이 이긴다.
    """
    if not isinstance(detail, dict):
        return []
    current = detail.get("currentClaim") if isinstance(detail.get("currentClaim"), dict) else {}
    blocks: list[dict] = []
    for holder in _claim_holders(detail):
        for key in CANCEL_BLOCK_KEYS:
            block = holder.get(key)
            if isinstance(block, dict) and block:
                blocks.append(block)
    return blocks


def extract_cancel_axis(detail: Any) -> dict:
    """취소 **확정** 축 — 언제 끝났나 · 환불이 끝났나 (2026-08-30).

    반품 축(:func:`extract_return_axis`)이 취소 블록을 일부러 빼기 때문에, 순수 취소 건은
    확정 시각도 환불 상태도 화면에 **영영 빈 값**이었다. 목업 확정본이 요구하는
    ``취소 완료 08-27`` · ``취소 완료 08-26 · 환불 완료`` 가 그래서 안 나왔다.

    반품 축에 ``cancel`` 을 도로 넣어 고치지 않는다 — 그건 2026-08-27 에 고친 누출을
    되살리는 짓이다(취소 블록의 환불 필드가 반품 진행으로 샌다). **축을 따로 둔다.**
    읽는 쪽은 클레임 종류가 취소일 때만 이 축을 본다.

    ``cancelCompletedDate`` 는 실데이터에 있는 값이다(운영 ``CANCEL_DONE`` 15건 ·
    ``docs/specs/2026-08-28-naver-claim-phase-labeling_SPEC.md`` §1.1) — 읽는 코드가 0곳이었다.
    승인 전 요청 건은 그 값이 없어서 빈 문자열이 되고, 화면은 날짜 조각을 통째로 안 낸다.

    Args:
        detail: 상품주문 상세 1건(dict 가 아니면 전부 빈 값으로 준다).

    Returns:
        ``{"cancel_completed_at", "cancel_approved_at", "refund_standby_status",
        "refund_done", "known"}``. 시각은 **원문 문자열 그대로**(형식 변환은 화면 몫).
        ``known`` 이 False 면 화면은 그 조각을 안 낸다.
    """
    blocks = _cancel_blocks(detail)
    standby_status = _first_text(blocks, "refundStandbyStatus")
    completed_at = _first_text(blocks, "cancelCompletedDate")
    approved_at = _first_text(blocks, "cancelApprovalDate")
    return {
        "cancel_completed_at": completed_at,
        "cancel_approved_at": approved_at,
        "refund_standby_status": standby_status,
        # 환불이 끝났다고 **말해도 되는가**. 모르는 값은 완료로 읽지 않는다(반품 축과 같은 규율).
        "refund_done": standby_status in REFUND_DONE_STANDBY_STATUSES,
        "known": bool(completed_at or approved_at or standby_status),
    }


def _return_blocks(detail: Any) -> list[dict]:
    """**반품 축**이 읽을 블록만 우선순위 순으로 모은다 (2026-08-27 CEO A1).

    :func:`_claim_blocks` 와 갈라 둔 이유: 그쪽은 ``cancel`` 이 첫 번째다(사유 원문을
    실제로 주는 경로라 옳다). 반품 축이 같은 목록을 쓰면 **취소 블록의 환불 필드가
    반품 진행으로 새어** 취소만 된 건에 "반품 진행" 줄이 뜬다.

    ``currentClaim`` 자체는 넣지 않는다 — 실데이터에서 그것은 평평한 클레임이 아니라
    ``{"return": …}``/``{"cancel": …}`` **래퍼**였다(2026-08-27 스테이징 83건 관측).
    넣으면 래퍼 안의 ``cancel`` 이 다시 새는 길이 된다.

    Args:
        detail: 상품주문 상세 1건(dict 가 아니면 빈 목록).

    Returns:
        비어 있지 않은 dict 블록 목록. 앞선 것이 이긴다.
    """
    if not isinstance(detail, dict):
        return []
    current = detail.get("currentClaim") if isinstance(detail.get("currentClaim"), dict) else {}
    blocks: list[dict] = []
    for holder in _claim_holders(detail):
        for key in RETURN_BLOCK_KEYS:
            block = holder.get(key)
            if isinstance(block, dict) and block:
                blocks.append(block)
    return blocks


def _first_text(blocks: list[dict], *keys: str) -> str:
    """블록 목록에서 주어진 키 중 **처음 만나는 비어 있지 않은 값**을 문자열로 준다.

    Args:
        blocks: :func:`_claim_blocks` 결과.
        keys: 같은 뜻으로 쓰이는 키 이름들(취소·반품 이름이 다른 자리).

    Returns:
        찾은 값(없으면 빈 문자열).
    """
    for block in blocks:
        for key in keys:
            value = _text(block.get(key))
            if value:
                return value
    return ""


#: 주문을 만들면 안 되는 클레임 상태(취소·반품 진행/완료). 거부·철회는 정상 진행이라 뺀다.
#: **여기 넣는 값은 반드시 ``CLAIM_STATUS_LABELS`` 에도 넣는다** — 차단은 되는데 라벨이
#: 없으면 배지에 영문 상수가 뜨고, 담당자가 왜 잠겼는지 화면에서 못 읽는다(T8-S0).
BLOCKING_CLAIM_STATUSES = frozenset({
    "CANCEL_REQUEST", "CANCEL_REQUESTED", "CANCELING", "CANCEL_DONE",
    "RETURN_REQUEST", "RETURN_REQUESTED", "RETURN_DONE", "COLLECTING", "COLLECT_DONE",
})

#: 클레임 **단계**. 라벨(무엇이 일어났나)·잠금(막을까)에 이은 세 번째 축이다 —
#: "네이버가 이미 확정했나, 아직 요청 상태인가".
#:
#: 이 축이 없던 시절 화면 두 곳(`order_candidates`·`ghost_orders`)이 "claimStatus 가
#: 비어 있지 않은가" 한 비트로 판정했고, 승인 전 취소가 `취소 완료` 로 표기됐다. 표기만
#: 틀린 게 아니라 그 판정이 **주문 폐기(soft delete) 버튼의 허가증**이었다 — 아직 살아 있을
#: 수 있는 주문이 휴지통으로 갈 수 있었다(2026-08-28, 운영 `link 79` / 주문 `#4998`).
CLAIM_PHASE_REQUESTED = "requested"      # 접수됐고 네이버가 아직 확정하지 않았다
CLAIM_PHASE_PROGRESS = "in_progress"     # 처리 중(수거 등) — 아직 확정이 아니다
CLAIM_PHASE_DONE = "done"                # 네이버가 확정했다
CLAIM_PHASE_REJECTED = "rejected"        # 거부·철회 = 주문은 살아 있다
CLAIM_PHASE_OTHER = "other"              # 클레임이지만 위 넷 어디도 아니다

#: 상태 → 단계. 키는 ``CLAIM_STATUS_LABELS`` 와 **1:1로 같아야 한다**(계약 테스트가 잠근다) —
#: 라벨은 있는데 단계가 없으면 화면은 "취소 요청"이라 적으면서 판정은 모름으로 떨어진다.
#: **모르는 상태는 여기 없다 = 빈 문자열**이고, 빈 문자열은 절대 ``done`` 취급하지 않는다
#: (모르면 파괴적 동작을 열지 않는다).
CLAIM_PHASES = {
    "CANCEL_REQUEST": CLAIM_PHASE_REQUESTED,
    "CANCEL_REQUESTED": CLAIM_PHASE_REQUESTED,
    "RETURN_REQUEST": CLAIM_PHASE_REQUESTED,
    "RETURN_REQUESTED": CLAIM_PHASE_REQUESTED,
    "EXCHANGE_REQUEST": CLAIM_PHASE_REQUESTED,
    "CANCELING": CLAIM_PHASE_PROGRESS,
    # 수거가 끝난 것이지 반품이 확정된 게 아니다 — ``COLLECT_DONE`` 을 ``done`` 에 넣으면
    # 환불 전 주문이 유령으로 접힌다.
    "COLLECTING": CLAIM_PHASE_PROGRESS,
    "COLLECT_DONE": CLAIM_PHASE_PROGRESS,
    "CANCEL_DONE": CLAIM_PHASE_DONE,
    "RETURN_DONE": CLAIM_PHASE_DONE,
    "EXCHANGE_DONE": CLAIM_PHASE_DONE,
    "CANCEL_REJECT": CLAIM_PHASE_REJECTED,
    "RETURN_REJECT": CLAIM_PHASE_REJECTED,
    "EXCHANGE_REJECT": CLAIM_PHASE_REJECTED,
    "PURCHASE_DECISION_HOLDBACK": CLAIM_PHASE_OTHER,
}


#: 상태 이름 앞머리 → 클레임 종류. ``claimType`` 이 없을 때만 쓰는 폴백이다.
#: ``COLLECTING``·``COLLECT_DONE`` 은 ``RETURN`` 으로 시작하지 않는다 — 접두어만 보면
#: 수거 단계 반품이 종류 미상으로 떨어진다(그 실수가 유령 목록에 아직 남아 있다).
_CLAIM_KIND_PREFIXES = (
    ("CANCEL", "CANCEL"),
    ("RETURN", "RETURN"),
    ("COLLECT", "RETURN"),
    ("EXCHANGE", "EXCHANGE"),
)


def claim_kind(claim: dict) -> str:
    """이 클레임이 **취소인가 반품인가 교환인가**.

    정답 축은 ``claimType`` 이다. 없을 때만 상태 이름으로 되짚는다 — 접두어 판정을
    **먼저** 쓰면 ``COLLECTING``/``COLLECT_DONE`` 이 종류 미상이 된다.

    쓰는 곳: 자기 접수 알림 억제(:mod:`claim_watch`)가 "우리가 낸 것과 같은 종류의
    클레임인가"를 물을 때. 종류를 안 보면 표식 하나가 모든 클레임을 덮어, 반품을 한 번
    접수한 링크는 그 뒤 진짜 고객 취소가 나도 영영 조용해진다.

    Args:
        claim: :func:`extract_claim` 결과.

    Returns:
        ``"CANCEL"``·``"RETURN"``·``"EXCHANGE"`` 중 하나. 모르면 빈 문자열
        (**모르는 것을 아는 종류로 우기지 않는다** — 억제는 빈 문자열에서 열리지 않는다).
    """
    kind = (claim.get("type") or "").strip().upper()
    if kind in ("CANCEL", "RETURN", "EXCHANGE"):
        return kind
    status = (claim.get("status") or "").strip().upper()
    for prefix, resolved in _CLAIM_KIND_PREFIXES:
        if status.startswith(prefix):
            return resolved
    return ""


def is_money_back_claim(claim: dict) -> bool:
    """이 클레임 때문에 **돈이 되돌아가는가(또는 갔는가)**.

    화면 세 곳이 "라벨이 비어 있지 않은가" 한 비트로 이것을 판정했다. 그래서
    ``RETURN_REJECT``("반품 거부")에 도크가 "환불액은 아직 빠지지 않은 금액입니다"라고
    적고, ⚠ 경고 배지를 **살아 있는 주문**에 붙였다 — 환불이 영영 없는 건이다
    (R-8, 2026-08-28).

    :func:`blocks_irreversible` 과 다른 질문이다. 그쪽은 "불가역 호출을 보내도 되는가"라
    **진행 중인 교환도 막는다**. 여기는 돈의 축이라 교환은 아니다(대체품을 받는다).

    ``done`` 도 참이다 — 환불이 이미 나갔어도 ``totalPaymentAmount`` 는 결제 시점 값이라
    "그 금액에서 아직 안 빠졌다"는 설명이 그대로 맞다.

    Args:
        claim: :func:`extract_claim` 결과.

    Returns:
        bool: 취소·반품이 요청·처리중·완료 중 하나면 True. 거부·모르는 상태는 False.
    """
    if (claim.get("phase") or "") not in (CLAIM_PHASE_REQUESTED, CLAIM_PHASE_PROGRESS,
                                          CLAIM_PHASE_DONE):
        return False
    return claim_kind(claim) in MONEY_BACK_CLAIM_KINDS


def blocks_irreversible(claim: dict) -> bool:
    """이 클레임이 걸린 집에 **되돌릴 수 없는 호출**(발주확인·발송처리·취소·반품 접수)을
    보내면 안 되는가.

    :data:`BLOCKING_CLAIM_STATUSES` 와 **다른 축**이다. 그쪽은 "주문을 만들면 안 되는가"라
    돈이 되돌아간 클레임(취소·반품)만 담는다 — 교환은 고객이 대체품을 받으므로 ERP 주문이
    **있어야** 하고, 거기에 넣으면 교환 건이 주문 만들기에서 막힌다.

    이 함수의 규칙은 둘이다:

    * **진행 중인 클레임은 종류 불문 막는다.** 불가역 호출 앞에서는 안전한 쪽으로 튼다.
      ``request_return`` 은 주석에 "이미 클레임(취소·반품·**교환**)이 도는 집에 반품을 또
      걸지 않는다"고 적어 놓고 교환을 안 막았다 — 그 약속을 코드로 만든다(R-4, 2026-08-28).
    * **끝난 클레임은 돈이 되돌아간 종류만 막는다.** 취소·반품 완료는 주문이 죽었다.
      교환 완료는 대체품 발송이 남아 있을 수 있어 막지 않는다(막으면 보낼 길이 없어진다).

    모르는 상태는 단계가 빈 문자열이라 막지 않는다 — 예전 ``blocking`` 판정과 같다.

    Args:
        claim: :func:`extract_claim` 결과.

    Returns:
        bool: 막아야 하면 True.
    """
    phase = claim.get("phase") or ""
    if phase in (CLAIM_PHASE_REQUESTED, CLAIM_PHASE_PROGRESS):
        return True
    if phase == CLAIM_PHASE_DONE:
        return claim_kind(claim) in MONEY_BACK_CLAIM_KINDS
    return False


def extract_claim(detail: dict) -> dict:
    """취소·반품·교환(클레임) 상태를 뽑는다.

    **``productOrderStatus`` 만 봐서는 취소를 알 수 없다** — 2026-08-14 스테이징 실측:
    상태가 ``PAYED`` 인데 ``claimStatus = CANCEL_REQUEST`` 인 건이 실재했다(수집 필터가
    PAYED 하나뿐이라 취소 요청 건도 그대로 수집된다). 그 값을 아무도 읽지 않아 화면에
    표시되지 않았고, 사람이 "주문 만들기"를 누르면 취소 건이 정상 주문이 됐다.

    ``detailed_reason`` 은 **고객이 직접 쓴 사유 원문**이다(인벤토리 §2.5 — 실데이터
    ``"일시불 재결제 예정"``). 코드값(``reason``)만 봐서는 취소가 "재결제하려고 무른 것"인지
    "안 사겠다는 것"인지 갈리지 않아, 지금까지 사람이 네이버를 따로 열어 확인했다.
    **둘을 합치지 않는다** — ``reason`` 은 집계·판정에 쓰는 코드고 ``detailed_reason`` 은
    사람이 읽는 문장이라 축이 다르다.

    Args:
        detail: 상품주문 상세 1건.

    Returns:
        ``{"status", "type", "reason", "requested_at", "label", "blocking", "phase",
        "detailed_reason"}``.
        클레임이 없으면 ``status``·``phase``·``detailed_reason`` 이 빈 문자열이고
        ``blocking`` 은 False.
    """
    order, product_order, _shipping = unwrap_detail(detail)
    blocks = _claim_blocks(detail)

    status = (_text(product_order.get("claimStatus"))
              or _first_text(blocks, "claimStatus")
              or _text(order.get("claimStatus")))
    upper = status.upper()
    return {
        "status": status,
        "type": _text(product_order.get("claimType")) or _first_text(blocks, "claimType"),
        "reason": _first_text(blocks, "cancelReason", "returnReason"),
        "requested_at": _first_text(blocks, "claimRequestDate"),
        "label": CLAIM_STATUS_LABELS.get(upper, status),
        "blocking": upper in BLOCKING_CLAIM_STATUSES,
        # 확정됐나 아직인가. 모르는 상태는 빈 문자열이고, 빈 문자열은 ``done`` 이 아니다.
        "phase": CLAIM_PHASES.get(upper, ""),
        # 고객이 쓴 사유 원문. ``reason`` 과 **같은 블록 규칙**(:func:`_claim_blocks`)을 쓰고,
        # 취소·반품 어느 이름으로 와도 잡는다. 없으면 빈 문자열(화면이 줄을 안 낸다).
        # 반품이 별도 블록으로 오면 예전 규칙(``cancel`` 만 보던 시절)에서는 이 값이 영영
        # 빈 문자열이었다 — 배송메모와 같은 모양의 조용한 유실이다(T8-S0).
        "detailed_reason": _first_text(blocks, "cancelDetailedReason", "returnDetailedReason"),
    }


def extract_claim_holdback(detail: Any) -> dict:
    """반품 **보류**(``holdbackStatus``)와 **반품 배송비 귀책**(``claimDeliveryFeePayMethod``)
    을 뽑는다 — 관측용(화면 없음).

    이 두 값은 반품 **승인** 분기의 입력이다: 보류가 걸려 있으면 승인 결과가 달라지고,
    배송비를 누가 무는지에 따라 돈의 방향이 갈린다. 그런데 스테이징 실데이터 392행에
    이 두 값이 **0건**이라 우리는 진짜 반품의 모양을 본 적이 없다 — 어느 블록에 실려
    오는지조차 모른다.

    그래서 :func:`_claim_blocks` 의 블록 탐색 규약을 그대로 따라 훑고(``cancel`` →
    ``returnInfo``/``return``/``exchange`` → ``currentClaim``), 마지막으로 상품주문·주문
    본체까지 본 뒤 **없으면 ``None``** 을 준다. 값이 없다고 예외를 내면 실물 반품 1건이
    들어온 바로 그 스윕이 통째로 실패해 관측 기회 자체가 사라진다 — 이 함수의 존재
    이유를 스스로 부수는 셈이다.

    표시 축이 아니라 **기록 축**이라 :data:`RETURN_BLOCK_KEYS` 로 좁히지 않는다. 취소
    블록에 실려 온 보류도 그때 우리가 본 사실 그대로 남겨야 나중에 모양을 읽을 수 있다.

    **그래서 값이 어느 블록에서 나왔는지도 함께 준다**(``*_block``). 좁히지 않은 대가로
    ``cancel`` 블록 값이 반품 보류처럼 보일 수 있는데(:data:`RETURN_BLOCK_KEYS` 가
    갈라져 나온 바로 그 누출), 출처 이름을 안 남기면 사후에 구분할 방법이 없다. 게다가
    "어느 블록에 실려 오는지 모른다"가 이 함수의 관측 목표라 **출처가 곧 답**이다.

    Args:
        detail: 상품주문 상세 1건(dict 가 아니면 전부 ``None``).

    Returns:
        ``{"holdback_status", "holdback_block", "fee_pay_method", "fee_block"}`` —
        값은 찾은 원문 문자열, 출처는 블록 이름(``cancel``·``returnInfo``·
        ``productOrder`` 등). 못 찾으면 둘 다 ``None``.
    """
    order, product_order, _shipping = unwrap_detail(detail)
    named: list[tuple[str, dict]] = []
    if isinstance(detail, dict):
        current = detail.get("currentClaim")
        for prefix, holder in (("", detail),
                               ("currentClaim.", current if isinstance(current, dict) else {})):
            for key in CLAIM_BLOCK_KEYS:
                block = holder.get(key) if isinstance(holder, dict) else None
                if isinstance(block, dict) and block:
                    named.append((prefix + key, block))
        if isinstance(detail.get("currentClaim"), dict) and detail["currentClaim"]:
            named.append(("currentClaim", detail["currentClaim"]))
    named += [("productOrder", product_order or {}), ("order", order or {})]

    def _pick(field: str) -> tuple[Optional[str], Optional[str]]:
        """``named`` 를 우선순위 순으로 훑어 (값, 출처 블록 이름)을 준다."""
        for name, block in named:
            text = _text(block.get(field))
            if text:
                return text, name
        return None, None

    holdback_status, holdback_block = _pick("holdbackStatus")
    fee_pay_method, fee_block = _pick("claimDeliveryFeePayMethod")
    return {
        "holdback_status": holdback_status,
        "holdback_block": holdback_block,
        "fee_pay_method": fee_pay_method,
        "fee_block": fee_block,
    }


#: 사람이 읽는 **회수 방법** 라벨. 모르는 값은 원문 그대로(다른 라벨 맵과 같은 규율).
#:
#: 실질적으로 값은 ``RETURN_INDIVIDUAL`` 하나다 — 우리가 내보내는 반품 접수는
#: :data:`fulfillment.RETURN_COLLECT_METHOD` 로 그 값에 고정돼 있고(다른 코드를 보내면
#: 네이버가 값을 무시하고 자동 수거를 보낸다), 운영 반품 25건도 전부 이 값이다.
#: 그런데 라벨 맵이 없어서 **화면에 영문 상수가 그대로 떴다**(R-5 ④, 2026-08-28).
#: ``CLAIM_STATUS_LABELS`` 가 배지에서 고친 것과 같은 결함이다.
COLLECT_METHOD_LABELS = {
    "RETURN_INDIVIDUAL": "자사 회수",
}

#: 클레임 **종류** 의 사람 말. 화면이 "취소"와 "반품"과 "교환"을 뭉치면 담당자가 다른
#: 사실을 같은 낱말로 읽는다.
#:
#: 반품 축 줄 제목에도 이것을 쓴다. :data:`RETURN_BLOCK_KEYS` 가 ``exchange`` 를 싣는 것은
#: 옳지만(수거는 반품·교환 양쪽에서 온다) 줄 제목이 고정 문자열 `반품 진행` 이라 교환 건의
#: 수거 값이 "반품"이라는 이름으로 떴다 — ``cancel`` 을 뺀 이유(취소 50건이 "반품 진행"으로
#: 뜬 사고)와 같은 형태의 누출이 교환 방향으로 남아 있었다(R-6, 2026-08-28).
CLAIM_KIND_LABELS = {
    "CANCEL": "취소",
    "RETURN": "반품",
    "EXCHANGE": "교환",
}

#: 관계 축 낱말 — ``ExternalOrderLink.relation`` 의 세 값. 이력 표(웹 계층)가 들고 있던
#: 목록을 여기로 올린다: 서비스 계층(:mod:`ghost_orders`)도 같은 낱말을 써야 하는데,
#: 서비스가 웹을 import 하는 방향은 없다. 목록이 두 벌이 되면 같은 집이 화면마다 다른
#: 이름으로 불린다.
RELATION_LABELS = {"NEW": "신규 결제", "ADDON": "추가결제", "REPAY": "재결제"}

#: **돈이 되돌아가는** 클레임 종류. 교환은 아니다 — 고객이 대체품을 받고 우리 주문은
#: 살아서 생산·배송을 기다린다.
#:
#: 이 구분이 없어서 ``EXCHANGE_DONE`` 이 `done` 단계라는 이유만으로 유령(폐기 대상) 목록에
#: 들어갔고, 살아 있는 주문에 **폐기 버튼이 열렸다**(R-2, 2026-08-28). ``CANCEL_REJECT`` 를
#: 뺀 것과 같은 판단이다 — 주문이 살아 있으면 유령이 아니다.
MONEY_BACK_CLAIM_KINDS = frozenset({"CANCEL", "RETURN"})

#: 반품 축 줄 제목의 **단계** 부분. 여기 없는 단계(요청·처리중·모름)는 `진행` 이다 —
#: 모르는 상태를 완료라고 말하지 않는 쪽으로 틀린다.
RETURN_AXIS_PHASE_WORDS = {
    CLAIM_PHASE_DONE: "완료",
    CLAIM_PHASE_REJECTED: "거부",
}

#: ``refundStandbyStatus`` 중 **환불이 끝났다**고 읽어도 되는 값.
#:
#: 운영 반품 25건이 전부 `환불처리완료` 단일값인데 화면이 `환불 대기 환불처리완료` 라고
#: 적어 왔다 — 라벨은 "대기", 값은 "완료"인 자기모순이다(R-5 ②). 단계로 분기해 고치되
#: **아는 값일 때만** 완료라 말한다(``CONFIRMED_PLACE_STATUSES`` 와 같은 규율).
REFUND_DONE_STANDBY_STATUSES = frozenset({"환불처리완료"})


def extract_return_axis(detail: Any) -> dict:
    """반품 **진행** 축(수거·환불·단계)을 뽑는다 — T8-S0.

    클레임 배지는 "반품 요청"까지만 말한다. 그 다음에 사람이 실제로 묻는 것은
    **언제 회수됐나 · 어디로 가야 하나 · 환불이 언제 나가나** 셋이다. 세 답은
    원본 스냅샷에 이미 들어 있는데(인벤토리 §2.5 — 회수지 15/281) 화면이 안 읽었다.
    F-1~F-3 와 같은 성질이라 **네이버로 나가는 호출은 0**이다.

    회수지(``collectAddress``)만 싣고 반품 수취지(``returnReceiveAddress``)는 안 싣는다 —
    앞은 "네이버가 회수 출발지로 준 곳", 뒤는 "받는 곳"이라 축이 다르다. 둘을 한 칸에
    합치면 화면이 틀린 주소를 말한다.

    2026-08-27 정정: 여기 있던 "우리 차가 물건을 가지러 갈 곳"이라는 설명은 **사실이
    아니었다**. 시공 제품이라 시공 전에는 물건이 고객 집에 갈 수 없고, 우리 반품은
    주문(금액)만 움직인다. 이 축은 배차 근거가 아니라 **네이버가 준 값의 반영**이다.

    2026-08-28 (R-5): 이 축이 ``claimStatus`` 를 **한 번도 읽지 않았다.** 그래서 화면은
    사실의 존재 여부로 단계를 암시할 수밖에 없었고, 끝난 반품 25건(운영, 예외 0)이
    ``반품 진행 … 환불 예정 … 환불 대기 환불처리완료`` 라는 **틀린 말 네 개**를 달고 떴다.
    단계(:data:`CLAIM_PHASES`)와 완료 시각(``returnCompletedDate`` — 읽는 코드가
    저장소에 0곳이었다)을 함께 싣는다. 단계는 :func:`extract_claim` 과 **같은 입력·같은
    함수**에서 오므로 배지와 본문이 다른 말을 할 수 없다.

    Args:
        detail: 상품주문 상세 1건(dict 가 아니면 전부 빈 값으로 준다).

    Returns:
        ``{"collect_method", "collect_method_label", "collect_completed_at",
        "return_completed_at", "refund_expected_at", "refund_expected_pending",
        "refund_standby_status", "refund_standby_reason", "refund_done",
        "collect_address", "phase", "kind_label", "progress_title", "known"}``.
        시각은 **원문 문자열 그대로** 준다(사람이 읽는 형식 변환은 화면 몫).
        원문 값은 라벨을 붙여도 **지우지 않는다** — 판정은 원문으로 한다.
        ``known`` 이 False 면 화면은 줄 자체를 내지 않는다 — 빈 칸이나 ``-`` 로 채우면
        "값이 없다"와 "우리가 모른다"가 같은 모양이 된다.
    """
    blocks = _return_blocks(detail)
    raw_address: dict = {}
    for block in blocks:
        candidate = block.get("collectAddress")
        if isinstance(candidate, dict) and candidate:
            raw_address = candidate
            break
    address = {
        "name": _text(raw_address.get("name")),
        "tel": _text(raw_address.get("tel1")) or _text(raw_address.get("tel2")),
        # 배송지와 **같은 규칙**으로 합친다 — 두 주소가 다른 모양이면 눈이 비교를 못 한다.
        "address": build_address(raw_address),
        "zip_code": _text(raw_address.get("zipCode")),
    }
    claim = extract_claim(detail)
    phase = claim["phase"]
    # 종류 판정은 :func:`claim_kind` 한 곳에만 둔다(``claimType`` 우선, 없으면 상태 이름).
    kind = CLAIM_KIND_LABELS.get(claim_kind(claim), "반품")
    collect_method = _first_text(blocks, "collectDeliveryMethod")
    standby_status = _first_text(blocks, "refundStandbyStatus")
    axis = {
        "collect_method": collect_method,
        "collect_method_label": COLLECT_METHOD_LABELS.get(collect_method.upper(), collect_method),
        "collect_completed_at": _first_text(blocks, "collectCompletedDate"),
        # 끝났음을 말할 수 있는 유일한 값. 운영 25건 전부 갖고 있는데 소비처가 0곳이었다.
        "return_completed_at": _first_text(blocks, "returnCompletedDate"),
        "refund_expected_at": _first_text(blocks, "refundExpectedDate"),
        "refund_standby_status": standby_status,
        "refund_standby_reason": _first_text(blocks, "refundStandbyReason"),
        # 환불이 끝났다고 **말해도 되는가**. 모르는 값은 완료로 읽지 않는다.
        "refund_done": standby_status in REFUND_DONE_STANDBY_STATUSES,
        "collect_address": address,
        "phase": phase,
        "kind_label": kind,
        "progress_title": f"{kind} {RETURN_AXIS_PHASE_WORDS.get(phase, '진행')}",
    }
    # 끝난 뒤의 "환불 예정"은 미래형 거짓말이다 — 값은 남기고 **화면이 안 낼 근거**만 준다.
    axis["refund_expected_pending"] = bool(axis["refund_expected_at"]) and phase != CLAIM_PHASE_DONE
    axis["known"] = any(axis[key] for key in (
        "collect_method", "collect_completed_at", "return_completed_at", "refund_expected_at",
        "refund_standby_status", "refund_standby_reason",
    )) or any(address.values())
    return axis


#: 사람이 읽는 발주 상태 라벨. 모르는 값은 원문을 그대로 보여준다(숨기지 않는다).
PLACE_STATUS_LABELS = {
    "NOT_YET": "발주확인 전",
    "OK": "발주확인 완료",
}

#: 발주확인이 끝난 것으로 보는 값. 여기 없으면 "아직"으로 취급한다 —
#: 모르는 값을 완료로 읽으면 처리해야 할 건이 화면에서 사라진다(안전한 쪽으로 틀린다).
CONFIRMED_PLACE_STATUSES = frozenset({"OK"})


def place_status_view(status: str) -> dict:
    """발주 상태 문자열 하나를 표시용 dict 로 편다.

    ``ExternalOrderLink.place_order_status`` 컬럼(수집·스윕·우리 발주확인이 갱신)과
    원본 스냅샷을 **같은 규칙**으로 읽기 위한 공용 변환이다. 컬럼이 표시 SSOT 이고
    스냅샷은 컬럼이 비었을 때의 폴백이다 — 둘이 갈리면 버튼이 사라지지 않는다.

    Args:
        status: 원문 상태값(빈 문자열 허용).

    Returns:
        ``{"status", "label", "confirmed"}``.
    """
    text = _text(status)
    upper = text.upper()
    return {
        "status": text,
        "label": PLACE_STATUS_LABELS.get(upper, text),
        "confirmed": upper in CONFIRMED_PLACE_STATUSES,
    }


def extract_place_status(detail: dict) -> dict:
    """발주(발주확인) 상태를 뽑는다 — NAVER-INGEST-02 T16-A.

    ``placeOrderStatus`` 는 수집 시점 원본에 이미 들어온다(2026-08-19 스테이징 실측:
    ``"NOT_YET"``). 네이버에 아무것도 쓰지 않고 "발주확인이 아직인 건"을 화면에서 가려낼 수
    있다는 뜻이다. 판매자센터나 API 로 발주확인을 하면 이 값이 바뀐다.

    ``shipping_due`` 를 같이 싣는 이유: 발송기한이 곧인데 발주확인 전이면 그게 급한 건이다.

    Args:
        detail: 상품주문 상세 1건(``{"order":…, "productOrder":…}`` 또는 평평한 형태).

    Returns:
        ``{"status", "label", "confirmed", "placed_at", "shipping_due"}``.
        값이 없으면 ``status`` 는 빈 문자열이고 ``confirmed`` 는 False(=아직으로 취급).
    """
    order, product_order, _shipping = unwrap_detail(detail)
    status = (_text(product_order.get("placeOrderStatus"))
              or _text(order.get("placeOrderStatus")))
    upper = status.upper()
    return {
        "status": status,
        "label": PLACE_STATUS_LABELS.get(upper, status),
        "confirmed": upper in CONFIRMED_PLACE_STATUSES,
        "placed_at": _text(product_order.get("placeOrderDate")),
        "shipping_due": _text(product_order.get("shippingDueDate")),
    }


#: 사람이 읽는 **배송 상태** 라벨. 모르는 값은 원문 그대로 보여준다
#: (``PLACE_STATUS_LABELS``·``CLAIM_STATUS_LABELS`` 와 같은 규율 — 모르는 상태를 숨기지 않는다).
#: 스테이징 실데이터 281건에서 실제로 온 값은 ``NOT_TRACKING``(자사 배송이라 추적이 없다)과
#: 배송수단 ``DIRECT_DELIVERY`` 다. 가구는 자사 배송·시공이라 택배 추적이 붙지 않는다.
DELIVERY_STATUS_LABELS = {
    "NOT_TRACKING": "배송추적 없음",
    "DIRECT_DELIVERY": "자사 직접 전달",
    "DELIVERING": "배송중",
    "DELIVERED": "배송완료",
}


def extract_delivery(detail: dict) -> dict:
    """발송(배송) 축을 뽑는다 — 인벤토리 §2.4 (281건 중 108건에 ``delivery`` 블록이 있다).

    **발송처리는 우리가 눌러 놓고 그 결과를 화면이 안 읽었다.** "언제 발송처리가 나갔나"를
    지금은 FOMS 쪽 기록(``fulfillment``)으로만 알아서, 네이버 쪽에 안 찍혔거나 시각이
    어긋난 건을 사람이 판매자센터를 열어야 알 수 있었다. 네이버가 말하는 값을 그대로
    되읽어 우리 기록 옆에 세우면 어긋남이 눈에 보인다.

    Args:
        detail: 상품주문 상세 1건(``delivery`` 는 ``order``·``productOrder`` 와 나란한
            최상위 블록이다. 응답이 평평하게 오는 변형도 받아준다).

    Returns:
        ``{"method", "status", "status_label", "send_date", "wrong_tracking"}``.
        ``delivery`` 블록이 없으면 전부 빈 값/False 다 — **예외를 던지지 않는다**
        (표시용 보조라 여기서 터지면 멀쩡한 화면이 통째로 죽는다).
        ``send_date`` 는 **원문 문자열 그대로** 준다. 사람이 읽는 형식 변환은 화면 몫이다.
    """
    if not isinstance(detail, dict):
        detail = {}
    order, product_order, _shipping = unwrap_detail(detail)
    delivery = detail.get("delivery") if isinstance(detail.get("delivery"), dict) else {}
    if not delivery:
        # 평평한 응답·주문 단위로 접혀 오는 변형 대비(``unwrap_detail`` 과 같은 규율).
        for holder in (product_order, order):
            candidate = holder.get("delivery") if isinstance(holder, dict) else None
            if isinstance(candidate, dict) and candidate:
                delivery = candidate
                break
    status = _text(delivery.get("deliveryStatus"))
    return {
        "method": _text(delivery.get("deliveryMethod")),
        "status": status,
        "status_label": DELIVERY_STATUS_LABELS.get(status.upper(), status),
        "send_date": _text(delivery.get("sendDate")),
        "wrong_tracking": _bool(delivery.get("isWrongTrackingNumber")),
    }


def _axis_partial(initial: Optional[int], remain: Optional[int]) -> bool:
    """한 축(수량 또는 금액)이 **부분**취소인가 — 일부는 사라지고 일부는 남았는가.

    2026-08-26 스테이징 실데이터 100건이 이 판정을 다시 쓰게 했다: ``initial != remain``
    으로 보면 **전부취소(``remain == 0``)까지 부분취소로 잡힌다**. 실제로 그 100건에서
    "부분취소"로 표시된 18건은 전부 ``RETURN_DONE``·``CANCEL_DONE`` 인 **전부**취소였고,
    진짜 부분취소는 **0건**이었다. 전부취소는 클레임 배지가 이미 말하므로 여기서 또
    말하면 화면이 같은 사실을 두 번, 그것도 **틀린 이름으로** 말한다.

    Args:
        initial: 최초 값(안 왔으면 None).
        remain: 잔여 값(안 왔으면 None).

    Returns:
        ``0 < remain < initial`` 일 때만 True. 한쪽이라도 안 온 원본은 "모른다"로 두고
        False — 없는 값을 0 으로 채우면 화면이 "원래 0개였다"고 거짓말한다.
    """
    if initial is None or remain is None:
        return False
    return 0 < remain < initial


def extract_partial_cancel(detail: dict) -> dict:
    """부분취소 잔여(``remain*``)·최초(``initial*``) 값을 뽑는다 — 인벤토리 §2.3.

    **함정 1: 이 필드들은 281/281 전 건에 온다.** 부분취소가 있든 없든 온다는 뜻이라,
    *필드가 있느냐* 로 판정하면 **모든 집이 부분취소로 보인다**.

    **함정 2: ``initial != remain`` 도 부족하다.** 전부취소면 ``remain`` 이 0 이라 그
    조건에 걸린다 — 판정은 :func:`_axis_partial` 이 하고, 부분취소는 **일부가 남았을
    때**(``0 < remain < initial``)만이다.

    Args:
        detail: 상품주문 상세 1건(``initial*``·``remain*`` 는 ``productOrder`` 필드다).

    Returns:
        ``{"is_partial", "quantity_partial", "amount_partial", "initial_quantity",
        "remain_quantity", "initial_amount", "remain_amount"}``.
        축별 플래그를 함께 주는 이유는 화면이 **바뀐 축에만** 잔여를 붙이기 때문이다
        (금액만 깎인 취소에서 안 바뀐 수량에 잔여를 달면 거짓말이다).
        숫자는 정수, 읽을 수 없으면 0.
    """
    _order, product_order, _shipping = unwrap_detail(detail if isinstance(detail, dict) else {})
    initial_quantity = _known_int(product_order, "initialQuantity")
    remain_quantity = _known_int(product_order, "remainQuantity")
    initial_amount = _known_int(product_order, "initialPaymentAmount")
    remain_amount = _known_int(product_order, "remainPaymentAmount")
    quantity_partial = _axis_partial(initial_quantity, remain_quantity)
    amount_partial = _axis_partial(initial_amount, remain_amount)
    return {
        "is_partial": quantity_partial or amount_partial,
        "quantity_partial": quantity_partial,
        "amount_partial": amount_partial,
        "initial_quantity": initial_quantity if initial_quantity is not None else 0,
        "remain_quantity": remain_quantity if remain_quantity is not None else 0,
        "initial_amount": initial_amount if initial_amount is not None else 0,
        "remain_amount": remain_amount if remain_amount is not None else 0,
    }


def build_payment_info(detail: dict) -> dict:
    """결제·금액 상세. 지금까지 ``totalPaymentAmount`` 하나만 쓰고 나머지를 버렸다.

    Args:
        detail: 상품주문 상세 1건.

    Returns:
        결제 시각·수단·단가·할인·쿠폰·정산예정액 dict(없으면 빈 값/0).
    """
    order, product_order, _shipping = unwrap_detail(detail)
    coupons = product_order.get("appliedCoupons")
    coupon_rows = []
    if isinstance(coupons, list):
        for coupon in coupons:
            if not isinstance(coupon, dict):
                continue
            discount = _int(coupon.get("couponDiscountAmount"))
            # 네이버 부담 비율(%). **이 값이 실무의 핵심**이다 — 같은 "쿠폰 1만원"이라도
            # 100 이면 네이버가 물고(정산액 그대로), 0 이면 우리가 문다(정산액이 깎인다).
            # 스테이징 실데이터에서 두 종류가 실제로 섞여 온다(NMP_PRD_DCNT=100 ·
            # NMP_PRD_DUP_DCNT=0). 값이 없으면 **모른다**로 두고 부담액을 만들지 않는다.
            raw_ratio = coupon.get("naverBurdenRatio")
            ratio = _int(raw_ratio) if raw_ratio is not None else None
            seller_burden = None
            if ratio is not None:
                seller_burden = int(round(discount * (100 - ratio) / 100))
            coupon_rows.append({
                "class_code": _text(coupon.get("couponClassCode")),
                "discount_amount": discount,
                # 발행번호 — 같은 쿠폰이 형제 상품주문마다 반복될 때 한 장인지 여러 장인지
                # 가리는 유일한 값이다.
                "publish_number": _text(coupon.get("couponPublishNumber")),
                "naver_burden_ratio": ratio,
                "seller_burden_amount": seller_burden,
            })
    # 카드사 프로모션(예: "멤버십데이 삼성카드 3% 할인"). 쿠폰과 다른 축이다 —
    # 카드사가 부담하고 상품 금액은 안 깎이지만, 담당자가 "왜 이 금액인가"를 물을 때
    # 쿠폰만 보여 주면 답이 안 나온다.
    promotion = product_order.get("appliedCardPromotion")
    card_promotion = None
    if isinstance(promotion, dict):
        card_promotion = {
            "name": _text(promotion.get("promotionName")),
            "card_company": _text(promotion.get("cardCompanyName")),
            "apply_amount": _int(promotion.get("promotionApplyAmount")),
        }

    return {
        "paid_at": _text(order.get("paymentDate")),
        "means": _text(order.get("paymentMeans")),
        "location_type": _text(order.get("payLocationType")),
        "card_promotion": card_promotion,
        "unit_price": _int(product_order.get("unitPrice")),
        "option_price": _int(product_order.get("optionPrice")),
        "product_discount_amount": _int(product_order.get("productDiscountAmount")),
        "expected_settlement_amount": _int(product_order.get("expectedSettlementAmount")),
        "coupons": coupon_rows,
    }


def build_structured_data(detail: dict) -> dict:
    """ERP structured_data 를 만든다(canonical 키 위치 사용).

    ERP 대시보드·통합검색이 읽는 자리에 맞춘다: 고객은 ``parties.customer``, 발주사는
    ``parties.orderer``(항상 라홈), 주문한 사람은 ``parties.buyer``, 주소는 ``site``,
    품목은 ``items[]``. 네이버 고유 값은 ``naver`` 아래로 몰아 다른 채널이 생겨도
    충돌하지 않게 한다.
    """
    order, product_order, shipping = unwrap_detail(detail)
    address = build_address(shipping)
    quantity = _int(product_order.get("quantity")) or 1
    return {
        "source": SOURCE_MARKER,
        "parties": {
            "customer": {
                "name": _text(shipping.get("name")) or _text(order.get("ordererName")),
                "phone": _text(shipping.get("tel1")) or _text(order.get("ordererTel")),
                # 보조 연락처(실측 47건 중 6건). 첫 번호로 연락이 안 될 때 쓰는 값이라
                # 버리면 다시 구할 방법이 없다. Order.phone 은 그대로 tel1 이다.
                "phone2": _text(shipping.get("tel2")),
            },
            # 발주사. ERP 에서 이 자리는 라홈/하우드 같은 발주처를 뜻하고, 알림톡 브랜드
            # 프로필·도면 로고·퀘스트 CS 팀·견적서 양식이 이 값으로 갈린다.
            "orderer": {"name": DEFAULT_ORDERER_NAME},
            # 주문한 사람. 대리주문이면 수취인과 다르다 — 해피콜 대상 판단에 필요해 보존한다.
            "buyer": {
                "name": _text(order.get("ordererName")),
                "phone": _text(order.get("ordererTel")),
            },
        },
        # FOMS 정본 주소 형태: full == main(합본 문자열) · detail 은 빈 값.
        # ``order_geocode.sync_site_address`` 가 모든 저장에서 그렇게 맞추고, ERP 편집 폼은
        # 로드할 때 full 뒤에 detail 을 이어 붙여 한 칸에 보여준다. 수집이 detail 을 따로
        # 남기면 이미 detail 을 품은 full 뒤에 detail 이 한 번 더 붙어 저장된다
        # (2026-08-14 운영 실측: ``… 103동 605호 103동 605호``).
        # 상세주소 원문이 필요하면 아래 ``naver`` 원본 필드가 아니라 주소 문자열을 쓴다.
        "site": {
            "address_full": address,
            "address_main": address,
            "address_detail": "",
            "zip_code": _text(shipping.get("zipCode")),
        },
        "items": [
            {
                "product_name": _text(product_order.get("productName")),
                "name": _text(product_order.get("productName")),
                # v1 은 파싱하지 않는다. 사람이 ERP 에서 규격/색상을 채운다.
                "options": _text(product_order.get("productOption")),
                "quantity": quantity,
                "price": _int(product_order.get("totalPaymentAmount")),
            }
        ],
        "naver": {
            "product_order_id": _text(product_order.get("productOrderId")),
            "order_no": _text(order.get("orderId")),
            "product_order_status": _text(product_order.get("productOrderStatus")),
            "shipping_due_date": _text(product_order.get("shippingDueDate")),
            "seller_product_code": _text(product_order.get("sellerProductCode")),
            "shipping_memo": extract_shipping_memo(detail),
            # 상품 식별자 — 나중에 "이 상품은 규격이 이렇다"를 자동화할 때 기초가 된다.
            "product_id": _text(product_order.get("productId")),
            "original_product_id": _text(product_order.get("originalProductId")),
            "item_no": _text(product_order.get("itemNo")),
            "inflow_path": _text(product_order.get("inflowPath")),
            # 취소·반품 상태. 없으면 status 가 빈 문자열이다(정상 주문).
            "claim": extract_claim(detail),
            "payment": build_payment_info(detail),
            # 참고용 좌표. Order.lat/lng 에 넣지 않는다(모듈 docstring 참조).
            "longitude": shipping.get("longitude"),
            "latitude": shipping.get("latitude"),
        },
    }


def build_order_fields(detail: dict, *, today: str) -> dict[str, Any]:
    """create_order 에 넘길 ``Order`` scalar 필드 dict 를 만든다.

    Args:
        detail: 상품주문 상세 1건.
        today: ``orderDate`` 파싱 실패 시 쓸 접수일(``YYYY-MM-DD``).

    Returns:
        ``Order`` scalar kwargs. 좌표 필드는 넣지 않는다(지오코딩이 채운다).
    """
    order, product_order, shipping = unwrap_detail(detail)
    received_date, received_time = parse_order_datetime(order.get("orderDate"))
    return {
        "received_date": received_date or today,
        "received_time": received_time,
        "customer_name": _text(shipping.get("name")) or _text(order.get("ordererName")),
        "phone": _text(shipping.get("tel1")) or _text(order.get("ordererTel")),
        "address": build_address(shipping),
        "product": _text(product_order.get("productName")),
        "options": _text(product_order.get("productOption")) or None,
        "payment_amount": _int(product_order.get("totalPaymentAmount")),
        "status": "RECEIVED",
        "is_regional": False,
    }


def map_detail(detail: dict, *, today: str) -> tuple[str, dict[str, Any], dict]:
    """상세 1건을 ``(external_id, order_fields, structured_data)`` 로 매핑한다.

    Args:
        detail: 상품주문 상세 1건.
        today: 접수일 대체값(``YYYY-MM-DD``).

    Returns:
        ``(external_id, order_fields, structured_data)``.

    Raises:
        NaverMappingError: 필수 값이 없을 때. 호출자는 주문을 만들지 않고
            ``PENDING_REVIEW`` 링크만 남긴다.
    """
    external_id = extract_external_id(detail)
    order_fields = build_order_fields(detail, today=today)
    candidates = {"external_id": external_id, **order_fields}
    missing = [name for name in REQUIRED_FIELDS if not _text(candidates.get(name))]
    if missing:
        raise NaverMappingError(f"필수 값 누락: {', '.join(missing)}")
    return (external_id, order_fields, build_structured_data(detail))



def group_key(detail: dict) -> tuple[str, str, str]:
    """묶음 판정 키 — ``(네이버 주문번호, 수취인 전화, 주소)``.

    같은 주문번호라도 **분할배송**이면 수취인·주소가 다를 수 있다. 그때 하나로 합치면
    남의 주소로 시공을 나가는 사고가 된다. 주문번호만으로 묶지 않는 이유다.

    Args:
        detail: 상품주문 상세 1건.

    Returns:
        같은 값이면 한 주문으로 묶어도 되는 키.
    """
    order, _product_order, shipping = unwrap_detail(detail)
    return (
        _text(order.get("orderId")),
        _text(shipping.get("tel1")),
        build_address(shipping),
    )


#: 묶음키 문자열의 구분자. 주소·이름에 나올 수 없는 제어문자를 쓴다 — 구분자가 값 안에
#: 섞이면 서로 다른 집이 같은 키로 접힌다.
GROUP_KEY_SEP = "\x1f"

#: 컬럼(String(200)) 길이 예산. 주문번호·전화가 짧으므로 주소를 잘라 맞춘다.
#: 자르는 지점이 같으면 같은 집은 여전히 같은 키다(앞에서부터 자르므로 접두사가 보존된다).
GROUP_KEY_MAX_LEN = 200


def group_key_text(detail: dict) -> str:
    """:func:`group_key` 의 3-튜플을 **컬럼에 저장할 문자열**로 정규화한다.

    화면 두 곳이 같은 정의를 쓰려면 세밀한 키를 SQL 로도 셀 수 있어야 하고, 그러려면
    값이 컬럼에 있어야 한다(주소는 ``raw_snapshot`` 안에서 파이썬으로 조립해야 나온다).

    Args:
        detail: 상품주문 상세 1건.

    Returns:
        같은 집이면 같은 문자열. 원본이 비어 키를 못 만들면 빈 문자열(호출자가 폴백한다).
    """
    order_no, tel, address = group_key(detail)
    if not (order_no or tel or address):
        return ""
    raw = GROUP_KEY_SEP.join((order_no, tel, address))
    return raw[:GROUP_KEY_MAX_LEN]


def _join_options(main_option: str, addon_options: list[str]) -> str:
    """본품 옵션 원문 + 추가옵션 원문들을 한 칸에 이어 붙인다(줄바꿈 구분)."""
    parts = [line for line in ([main_option] + list(addon_options)) if line]
    return "\n".join(parts)


def is_addon_detail(detail: dict) -> bool:
    """이 상품주문이 **추가옵션**인가(``productClass`` 정본).

    Args:
        detail: 상품주문 상세 1건.

    Returns:
        추가옵션이면 True. 값이 없는 옛 원본은 본품으로 본다(모르면 항목을 남긴다).
    """
    _order, product_order, _shipping = unwrap_detail(detail)
    return _text(product_order.get("productClass")) == ADDON_PRODUCT_CLASS


def split_main_groups(details: list[dict], *,
                      fallback_index: int = 0) -> list[tuple[dict, list[dict]]]:
    """상세 목록을 **본품 → 그 본품의 추가옵션** 으로 묶는다.

    귀속 판정은 :func:`attribution.attribute_addons` 가 한다(수집 순서 우선, 본품이 앞에
    몰려 온 배치는 사양 축 일치). 화면(도크)과 **같은 함수**를 쓴다 — 한쪽만 바뀌면 품목
    금액과 화면 귀속이 어긋난다.

    Args:
        details: 같은 묶음의 상세 목록(수집 순서 그대로).
        fallback_index: 귀속이 미정인 옵션을 붙일 본품의 인덱스(기본 = 첫 본품).
            금액을 잃지 않으려면 어딘가에는 붙여야 한다. 화면에서는 여전히 "선택 필요"로 뜬다.

    Returns:
        ``[(본품 detail, [추가옵션 detail, ...]), ...]`` — 본품 등장 순서 보존.
        본품이 하나도 없으면 첫 건을 본품으로 삼는다(빈 묶음 방지).
    """
    from foms.services.integrations.naver_commerce.attribution import attribute_addons

    rows = []
    for detail in details:
        _order, product_order, _shipping = unwrap_detail(detail)
        rows.append({
            "is_main": not is_addon_detail(detail),
            "product_name": _text(product_order.get("productName")),
            "option_text": _text(product_order.get("productOption")),
        })
    main_indexes = [i for i, row in enumerate(rows) if row["is_main"]]
    if not main_indexes:
        # 전부 추가옵션으로 온 비정상 원본 — 첫 건을 본품으로 세운다.
        return [(details[0], list(details[1:]))] if details else []

    owners = attribute_addons(rows)
    buckets: dict[int, list[dict]] = {index: [] for index in main_indexes}
    default_main = main_indexes[min(fallback_index, len(main_indexes) - 1)]
    for index, detail in enumerate(details):
        if rows[index]["is_main"]:
            continue
        owner, _reason = owners[index]
        buckets[owner if owner in buckets else default_main].append(detail)
    return [(details[index], buckets[index]) for index in main_indexes]


def map_group(details: list[dict], *, today: str) -> tuple[dict[str, Any], dict]:
    """같은 묶음의 상품주문 여러 건을 **주문 1건**으로 매핑한다 (T13).

    네이버는 붙박이장 본품과 구성 옵션(반옷장·긴옷장 등, 금액 0원 포함)을 각각 다른
    ``productOrderId`` 로 준다. 상품주문 1건 = FOMS 주문 1건으로 두면 한 집 시공이
    주문 3~4건으로 쪼개져 일정·정산이 어긋난다(2026-08-14 실데이터: 12개 주문번호 → 34건).

    대표값 규칙:

    * 고객·주소·접수일시 — **금액이 가장 큰** 상품주문 기준(본품이 대표가 된다).
      금액이 같으면 입력 순서를 유지해 안정적으로 고른다.
    * ``product`` — 대표 제품명, 2건 이상이면 ``외 N건`` 을 덧붙인다.
    * ``payment_amount`` — 묶음 **합계**.
    * ``items[]`` — 상품주문마다 1행(0원 구성도 그대로 남긴다 — 뭘 받았는지가 정보다).

    Args:
        details: 같은 :func:`group_key` 를 가진 상세 목록(1건 이상).
        today: 접수일 대체값.

    Returns:
        ``(order_fields, structured_data)``.

    Raises:
        NaverMappingError: 비어 있거나 대표 건의 필수 값이 없을 때.
    """
    if not details:
        raise NaverMappingError("묶을 상세가 없다")

    ordered = sorted(
        enumerate(details),
        key=lambda pair: (-_int(unwrap_detail(pair[1])[1].get("totalPaymentAmount")), pair[0]),
    )
    lead_index, lead = ordered[0]
    _external_id, order_fields, structured = map_detail(lead, today=today)

    total = sum(_int(unwrap_detail(d)[1].get("totalPaymentAmount")) for d in details)
    order_fields["payment_amount"] = total
    if len(details) > 1:
        order_fields["product"] = f"{order_fields['product']} 외 {len(details) - 1}건"

    # **품목은 본품만 만든다** (2026-08-18 사용자 확정). 추가옵션(수납구성·EP마감·서랍·
    # 제로조인트·길이추가)까지 항목으로 만들면 한 집이 14행이 되어 규격을 채울 행을 찾기가
    # 어렵다. 옵션은 항목이 아니라 **그 본품 항목의 부속 정보**로 싣는다(도크에도 원문 그대로).
    # 금액은 잃지 않는다 — 본품 항목 금액 = 본품 + 그 본품에 귀속된 옵션 합계라서
    # ``items_total`` 이 묶음 합계와 정확히 같다.
    groups = split_main_groups(details)
    lead_first = sorted(
        groups,
        key=lambda pair: 0 if pair[0] is lead else 1,
    )
    items = []
    option_lines = []
    for main, addons in lead_first:
        _order, product_order, _shipping = unwrap_detail(main)
        name = _text(product_order.get("productName"))
        option = _text(product_order.get("productOption"))
        price = _int(product_order.get("totalPaymentAmount"))
        addon_rows = []
        addon_options = []
        for addon in addons:
            _o, addon_po, _s = unwrap_detail(addon)
            addon_name = _text(addon_po.get("productName"))
            addon_option = _text(addon_po.get("productOption"))
            addon_price = _int(addon_po.get("totalPaymentAmount"))
            price += addon_price
            addon_rows.append({
                "product_name": addon_name,
                "options": addon_option,
                "quantity": _int(addon_po.get("quantity")) or 1,
                "price": addon_price,
                "naver_product_order_id": _text(addon_po.get("productOrderId")),
            })
            if addon_option:
                addon_options.append(f"{addon_name}: {addon_option}")
        items.append({
            "product_name": name,
            "name": name,
            # 규격을 채우는 사람이 한 칸에서 본품·옵션 원문을 다 보게 이어 붙인다.
            "options": _join_options(option, addon_options),
            "quantity": _int(product_order.get("quantity")) or 1,
            "price": price,
            "naver_product_order_id": _text(product_order.get("productOrderId")),
            "naver_role": "main",
            # 항목으로 만들지 않은 추가옵션 원본 — 추적·역산용(화면 표시는 도크가 한다).
            "naver_addons": addon_rows,
        })
        if option:
            option_lines.append(f"{name}: {option}" if len(details) > 1 else option)
        option_lines.extend(addon_options)

    structured["items"] = items
    structured["totals"] = {"items_total": total}
    # 옵션 원문은 사람이 규격을 채우는 근거다 — 묶으면 건별로 구분해 이어 붙인다.
    order_fields["options"] = "\n".join(option_lines) or None
    structured["naver"]["product_order_ids"] = [
        _text(unwrap_detail(d)[1].get("productOrderId")) for d in details
    ]
    structured["naver"]["grouped_count"] = len(details)
    # 배송메모는 상품주문마다 따로 달린다. 대표 것만 쓰면 다른 줄에 적힌 요청이 조용히
    # 사라지므로 **서로 다른 값은 전부** 남긴다(중복은 제거, 표시 순서는 대표 먼저).
    memo_order = [lead] + [d for i, d in enumerate(details) if i != lead_index]
    memos: list[str] = []
    for detail in memo_order:
        memo = extract_shipping_memo(detail)
        if memo and memo not in memos:
            memos.append(memo)
    structured["naver"]["shipping_memo"] = "\n".join(memos)
    return (order_fields, structured)


__all__ = [
    "COLLECTIBLE_STATUS",
    "GROUP_KEY_MAX_LEN",
    "GROUP_KEY_SEP",
    "group_key",
    "group_key_text",
    "map_group",
    "KST",
    "NaverMappingError",
    "REQUIRED_FIELDS",
    "SOURCE_MARKER",
    "build_address",
    "build_order_fields",
    "build_structured_data",
    "BLOCKING_CLAIM_STATUSES",
    "CLAIM_STATUS_LABELS",
    "CLAIM_PHASES",
    "CLAIM_PHASE_REQUESTED",
    "CLAIM_PHASE_PROGRESS",
    "CLAIM_PHASE_DONE",
    "CLAIM_PHASE_REJECTED",
    "CLAIM_PHASE_OTHER",
    "CLAIM_REASON_LABELS",
    "COLLECT_METHOD_LABELS",
    "CLAIM_KIND_LABELS",
    "RELATION_LABELS",
    "MONEY_BACK_CLAIM_KINDS",
    "RETURN_AXIS_PHASE_WORDS",
    "REFUND_DONE_STANDBY_STATUSES",
    "claim_reason_text",
    "claim_kind",
    "blocks_irreversible",
    "is_money_back_claim",
    "build_payment_info",
    "extract_claim",
    "extract_claim_holdback",
    "extract_delivery",
    "extract_partial_cancel",
    "extract_cancel_axis",
    "extract_return_axis",
    "extract_place_status",
    "place_status_view",
    "PLACE_STATUS_LABELS",
    "CONFIRMED_PLACE_STATUSES",
    "DELIVERY_STATUS_LABELS",
    "extract_external_id",
    "extract_shipping_memo",
    "is_collectible",
    "map_detail",
    "parse_order_datetime",
    "unwrap_detail",
]
