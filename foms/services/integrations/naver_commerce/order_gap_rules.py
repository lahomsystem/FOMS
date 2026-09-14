"""네이버 수집분 ↔ ERP 주문 대조 — 분류 규칙 (GAP-01, DB 비의존).

이 모듈은 **순수하다**. DB 도 SQLAlchemy 도 모르고, 스칼라 다섯 개
(상품 구분·상품명·주문 상태·클레임 상태·결제 금액)와 "ERP 에 같은 전화의
주문이 있나" 한 비트만 받아 칸을 정한다. 질의는 :mod:`order_gap` 이 맡는다.

가른 이유는 테스트다. 분류가 SQL 안에 있으면 SQLite 레인에서 방언 차이에
막혀 전 분기를 못 덮는다. 순수 함수로 두면 분기 전수를 값으로 찍어 볼 수 있다.

순진한 답(``order_id IS NULL AND relation='NEW'``)이 틀리는 이유도 여기 있다 —
``relation`` 은 추가·재결제 축을 전부 가르지 못한다. 상품명이 그대로
``추가결제`` 인 행이 ``NEW`` 로 들어와 있어서, 상품 구분과 상품명을 함께 봐야 한다.
"""

from __future__ import annotations

from typing import Any, Iterator, Sequence

from foms.services.integrations.naver_commerce.constants import ADDON_PRODUCT_CLASS
from foms.services.integrations.naver_commerce.mapping import (
    CLAIM_PHASE_DONE,
    CLAIM_PHASES,
    CLAIM_STATUS_LABELS,
)



# --------------------------------------------------------------------------- #
# 버킷 상수
# --------------------------------------------------------------------------- #

GAP_MISSING = "missing"
GAP_ATTACHABLE = "attachable"
GAP_EXTRA = "extra"
GAP_CLOSED = "closed"
GAP_UNDECIDED = "undecided"

#: 화면이 도는 순서이자 테스트가 세는 전수. 이 순서대로 칩이 뜬다.
GAP_BUCKETS = (GAP_MISSING, GAP_ATTACHABLE, GAP_EXTRA, GAP_CLOSED,
               GAP_UNDECIDED)

#: 칸 이름과 설명의 SSOT. 템플릿에 한글을 박지 않는다 —
#: 문구 계약 테스트가 여기 하나만 보면 되게.
GAP_LABELS: dict[str, dict[str, str]] = {
    GAP_MISSING: {
        "label": "주문 없음(확인 필요)",
        "note": "같은 전화의 ERP 주문을 못 찾았습니다. 전화가 다르게 적힌 주문은 여기로 옵니다.",
    },
    GAP_ATTACHABLE: {
        "label": "주문 있음 · 링크만 없음",
        "note": "같은 전화의 ERP 주문이 있습니다. 같은 주문인지는 사람이 확인합니다.",
    },
    GAP_EXTRA: {
        "label": "부가·재결제 라인",
        "note": "추가구성상품·추가결제·재결제입니다. 새 주문이 아닙니다.",
    },
    GAP_CLOSED: {
        "label": "취소·반품 확정",
        "note": "네이버가 확정했습니다. 붙일 짝이 아닙니다.",
    },
    GAP_UNDECIDED: {
        "label": "판정 보류",
        "note": "아직 진행 중이거나 우리가 모르는 모양입니다. 사람이 봐야 합니다.",
    },
}

#: 본품으로 인정하는 네이버 ``productClass`` 값. 두 값의 출처가 다르다 —
#: ``조합형옵션상품`` 은 2026-08-14 실측(constants 의 ``ADDON_PRODUCT_CLASS``
#: 주석이 같은 날을 적는다), ``단일상품`` 은 2026-09-14 대조 실측에서 나왔다.
MAIN_PRODUCT_CLASSES = frozenset({"조합형옵션상품", "단일상품"})

#: 상품명만으로 부가 라인임이 드러나는 값. ``relation`` 이 ``NEW`` 인 채로
#: 들어오는 추가결제 라인을 여기서 잡는다.
EXTRA_PRODUCT_NAMES = frozenset({"추가결제"})

#: 네이버 ``productOrderStatus`` 자체가 종결인 값.
CLOSED_ORDER_STATUSES = frozenset({"CANCELED", "RETURNED"})

#: 모집단 상한. 운영 미연결 1,899행 기준 여유 2.6배다.
GAP_SCAN_CAP = 5000

#: 한 화면에 그리는 행 수.
GAP_PAGE_SIZE = 200

#: 전화 대조 ``IN`` 절 한 묶음 크기.
_PHONE_CHUNK = 500

#: 행 dict 의 키 전수. 여기 없는 키를 더하면 개인정보가 새는 자리가 된다.
GAP_ROW_KEYS = ("link_id", "external_order_no", "collected_date", "product_name",
                "payment_amount", "recipient_name_masked", "naver_status",
                "claim_label", "bucket")




# --------------------------------------------------------------------------- #
# 작은 도우미
# --------------------------------------------------------------------------- #

def _text(value: Any) -> str:
    """스칼라를 문자열로. ``None`` 은 빈 문자열."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _to_int(value: Any) -> int:
    """결제 금액을 정수로. 못 읽으면 0(화면이 죽지 않게)."""
    if value is None:
        return 0
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = _text(value).strip().replace(",", "")
    if not text:
        return 0
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return 0


def _chunks(values: Sequence[str], size: int) -> Iterator[Sequence[str]]:
    for start in range(0, len(values), size):
        yield values[start:start + size]


def mask_name(name: str | None) -> str:
    """수취인 이름 마스킹. 빈 값이면 빈 문자열.

    1자 ``*`` · 2자 ``홍*`` · 3자 이상 ``홍*동``(가운데 전부 ``*``).
    """
    text = _text(name).strip()
    if not text:
        return ""
    if len(text) == 1:
        return "*"
    if len(text) == 2:
        return text[0] + "*"
    return text[0] + "*" * (len(text) - 2) + text[-1]


# --------------------------------------------------------------------------- #
# 분류 — DB 를 안 만지는 순수 함수
# --------------------------------------------------------------------------- #

def classify_gap_row(fields: dict, *, has_erp_order: bool) -> str:
    """행 하나를 버킷 이름으로 가른다 — DB 를 안 만지는 순수 함수.

    위에서부터 첫 일치다. 순서가 뜻이다: 종결이 먼저, 부가가 그다음,
    그러고도 살아 있는 본품만 붙이기 축(전화 대조)을 탄다.

    "claimStatus 가 비어 있지 않은가" 한 비트 판정은 쓰지 않는다. 그 판정이
    2026-08-28 운영 사고(link 79 / 주문 #4998 — 승인 전 취소가 '취소 완료' 로
    표기되고 그게 폐기 버튼의 허가증이 됐다)의 원인이라고 ``mapping`` 이
    못박아 두었다. 종결은 ``CLAIM_PHASES`` 가 ``done`` 이라고 말할 때만이다.

    Args:
        fields: ``product_class``·``product_name``·``order_status``·
            ``claim_status``·``amount``·``relation``·``phone_digits`` 키를
            가진 dict. 값은 전부 이미 뽑힌 스칼라다(문자열/정수).
        has_erp_order: 같은 전화의 ERP 주문이 있는가.

    Returns:
        :data:`GAP_BUCKETS` 중 하나.
    """
    order_status = _text(fields.get("order_status")).strip().upper()
    claim_status = _text(fields.get("claim_status")).strip()
    claim_upper = claim_status.upper()
    product_class = _text(fields.get("product_class")).strip()
    product_name = _text(fields.get("product_name")).strip()
    relation = _text(fields.get("relation")).strip().upper()
    amount = _to_int(fields.get("amount"))
    phone_digits = _text(fields.get("phone_digits")).strip()

    # 1. 종결 — 네이버가 확정한 것만.
    if order_status in CLOSED_ORDER_STATUSES:
        return GAP_CLOSED
    if claim_upper and CLAIM_PHASES.get(claim_upper) == CLAIM_PHASE_DONE:
        return GAP_CLOSED

    # 2. 부가·재결제. relation 은 이 축을 **전부**는 못 가르지만, 값이
    #    ADDON/REPAY 인 행은 정의상 부가다. 이 조건은 EXTRA 만 넓히고
    #    MISSING 을 절대 부풀리지 않는다.
    if (product_class == ADDON_PRODUCT_CLASS
            or product_name in EXTRA_PRODUCT_NAMES
            or relation in ("ADDON", "REPAY")):
        return GAP_EXTRA

    # 3. 살아있는 본품 — 네 조건을 전부 만족할 때만.
    if (order_status == "PURCHASE_DECIDED"
            and claim_status == ""
            and product_class in MAIN_PRODUCT_CLASSES
            and amount > 0):
        if not phone_digits:
            # 짚을 축이 아예 없다. 조용히 attachable 로 보내면 거짓말이 된다.
            return GAP_MISSING
        return GAP_ATTACHABLE if has_erp_order else GAP_MISSING

    # 4. 나머지 전부. 이 칸이 없으면 행이 조용히 사라진다 —
    #    배송 중(DELIVERING)·요청 단계 클레임(CANCEL_REQUEST)·거부된
    #    클레임(CANCEL_REJECT)·금액 0·모르는 productClass 가 여기로 온다.
    return GAP_UNDECIDED
