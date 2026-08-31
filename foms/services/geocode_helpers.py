"""
지오코딩 관련 공유 로직 (Phase C).
주소 추출, address_hash 계산, **주문 좌표 반영 SSOT**.

:func:`apply_geocode_to_order` 는 "주문 1건을 좌표로 채우는" 판정·저장 규칙의 단일 정본이다.
RQ 태스크(:func:`foms.services.jobs.tasks.geocode_order_address`)와 SIDEFX GEOCODE handler
(:mod:`foms.services.geocode_delivery_handler`)가 **같은 함수**를 호출한다 — 두 소비 경로가
서로 다른 판정을 갖지 않게 하기 위함이다(로직 2벌 금지). 세션 소유(commit/close)는 호출자
몫이라 SIDEFX worker 계약(handler 는 자기 commit 을 하지 않는다)과 충돌하지 않는다.
"""
from __future__ import annotations

import datetime
import hashlib
import re
from typing import Any, Optional

from foms.services.datetime_kst import now_utc_naive
from foms.services.erp_order_flags import is_erp_order_record

__all__ = [
    "compute_address_hash",
    "extract_address_from_structured_data",
    "extract_address_from_order",
    "get_order_display_address",
    "apply_geocode_to_order",
    "GEOCODE_OUTCOME_SKIPPED",
    "GEOCODE_OUTCOME_SUCCESS",
    "GEOCODE_OUTCOME_FAILED",
    "GEOCODE_OUTCOME_NO_ADDRESS",
]

#: 주소 해시·좌표가 이미 최신이라 외부 변환을 건너뛴 경우(주문 미변경).
GEOCODE_OUTCOME_SKIPPED = "skipped"
#: 좌표 획득 성공(``geocode_status='success'`` 기록).
GEOCODE_OUTCOME_SUCCESS = "success"
#: 변환 실패(``geocode_status='failed'`` 기록 — 재시도 대상 아님, 주소 자체가 문제).
GEOCODE_OUTCOME_FAILED = "failed"
#: 주소가 비어 변환할 것이 없음(``geocode_status='failed'`` 기록).
GEOCODE_OUTCOME_NO_ADDRESS = "no_address"


def compute_address_hash(address: str) -> str:
    """
    주소 정규화 후 SHA256 해시 반환 (64자 hex).
    주소 변경 감지용. 해시가 같으면 geocode 재요청 스킵.
    """
    if not address or not isinstance(address, str):
        return ''
    s = address.strip()
    s = re.sub(r'\s+', ' ', s)
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def extract_address_from_structured_data(sd: dict[str, Any]) -> str:
    """
    structured_data dict에서 주소 추출 (site.address_full or address_main+detail).
    extract_address_from_order와 동일 로직. API payload 검증용.
    """
    if not sd or not isinstance(sd, dict):
        return ''
    site = sd.get('site') or {}
    erp_full = site.get('address_full')
    if erp_full and str(erp_full).strip() and str(erp_full).strip() != '-':
        return str(erp_full).strip()
    main = site.get('address_main')
    if main and str(main).strip():
        detail = site.get('address_detail')
        if detail and str(detail).strip() and str(detail).strip() != '-':
            return f"{str(main).strip()} {str(detail).strip()}"
        return str(main).strip()
    return ''


def extract_address_from_order(order: Any) -> str:
    """
    Order에서 사용할 주소 문자열 추출.
    ERP Order: site.address_full or (address_main + address_detail) 우선.
    일반 주문: order.address.
    """
    if is_erp_order_record(order) and order.structured_data:
        sd = order.structured_data
        site = sd.get('site') or {}
        erp_full = site.get('address_full')
        if erp_full and str(erp_full).strip() and str(erp_full).strip() != '-':
            return str(erp_full).strip()
        main = site.get('address_main')
        if main and str(main).strip():
            detail = site.get('address_detail')
            if detail and str(detail).strip() and str(detail).strip() != '-':
                return f"{str(main).strip()} {str(detail).strip()}"
            return str(main).strip()
    return (order.address or '').strip()


def get_order_display_address(order: Any) -> str:
    """
    출고/AS batch 추천·nearby와 동일한 표시·지오코딩용 주소 (spec §2.7).
    structured_data.site 우선, 없으면 order.address.
    """
    if not order:
        return ""
    structured_data = getattr(order, "structured_data", None)
    if isinstance(structured_data, dict):
        site = structured_data.get("site") or {}
        address_full = site.get("address_full")
        address_main = site.get("address_main")
        address_detail = site.get("address_detail")
        if address_full:
            return str(address_full).strip()
        if address_main:
            detail = (address_detail or "").strip()
            return f"{address_main.strip()} {detail}".strip() if detail else address_main.strip()
    return (getattr(order, "address", None) or "").strip()


def apply_geocode_to_order(
    order: Any,
    *,
    converter: Optional[Any] = None,
    now: Optional[datetime.datetime] = None,
) -> str:
    """주문 1건의 주소를 좌표로 변환해 Order 지오코드 필드를 갱신한다(판정·저장 SSOT).

    RQ 태스크와 SIDEFX ``GEOCODE`` handler 가 공유하는 유일한 구현이다. **세션을 열지도,
    commit/close 하지도 않는다** — 호출자가 트랜잭션을 소유한다(SIDEFX handler 계약).

    판정 순서(기존 RQ 태스크와 동일):

    1. 주소가 비면 좌표를 지우고 ``geocode_status='failed'`` + ``geocoded_at`` 를 기록한다
       (변환할 것이 없음 — 재시도 대상 아님).
    2. ``address_hash`` 가 현재 주소와 같고 좌표가 이미 있으면 **아무것도 하지 않는다**
       (멱등: 같은 job/outbox 행이 재전달돼도 외부 API 를 다시 부르지 않는다).
    3. 그 밖에는 변환을 시도해 ``geocoded_at``·``address_hash`` 를 갱신하고, 좌표를 얻으면
       ``success``, 못 얻으면 좌표를 비우고 ``failed`` 를 기록한다.

    Args:
        order: 대상 :class:`~models.Order`(호출자 세션에 attach 된 상태).
        converter: 주소 변환기(테스트 주입용). None 이면 :class:`FOMSAddressConverter` 를
            그 자리에서 만든다(무거운 import 를 호출 시점까지 미룬다).
        now: ``geocoded_at`` 에 기록할 시각. 기본은 :func:`now_utc_naive` — 저장 컬럼이
            naive UTC 규약이라 로컬 시각(``datetime.now()``)을 쓰지 않는다.

    Returns:
        :data:`GEOCODE_OUTCOME_SKIPPED` / :data:`GEOCODE_OUTCOME_SUCCESS` /
        :data:`GEOCODE_OUTCOME_FAILED` / :data:`GEOCODE_OUTCOME_NO_ADDRESS` 중 하나.
    """
    stamp = now or now_utc_naive()

    address = extract_address_from_order(order)
    if not address:
        order.lat = None
        order.lng = None
        order.geocode_status = 'failed'
        order.geocoded_at = stamp
        return GEOCODE_OUTCOME_NO_ADDRESS

    new_hash = compute_address_hash(address)
    if order.address_hash == new_hash and order.lat is not None and order.lng is not None:
        return GEOCODE_OUTCOME_SKIPPED

    if converter is None:
        from foms.services.common.address_converter import FOMSAddressConverter

        converter = FOMSAddressConverter()
    lat, lng, _status = converter.convert_address(address)

    order.geocoded_at = stamp
    order.address_hash = new_hash

    if lat is not None and lng is not None:
        order.lat = float(lat)
        order.lng = float(lng)
        order.geocode_status = 'success'
        return GEOCODE_OUTCOME_SUCCESS

    order.lat = None
    order.lng = None
    order.geocode_status = 'failed'
    return GEOCODE_OUTCOME_FAILED
