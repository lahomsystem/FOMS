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
from foms.services.geocode_retry import (
    FAILURE_PERMANENT,
    FAILURE_TRANSIENT,
    STATUS_ADDRESS_ERROR,
    STATUS_PENDING,
    STATUS_SUCCESS,
)

__all__ = [
    "compute_address_hash",
    "extract_address_from_structured_data",
    "extract_address_from_order",
    "get_order_display_address",
    "apply_geocode_to_order",
    "GEOCODE_OUTCOME_SKIPPED",
    "GEOCODE_OUTCOME_SUCCESS",
    "GEOCODE_OUTCOME_FAILED",
    "GEOCODE_OUTCOME_TRANSIENT",
    "GEOCODE_OUTCOME_NO_ADDRESS",
]

#: 주소 해시·좌표가 이미 최신이라 외부 변환을 건너뛴 경우(주문 미변경).
GEOCODE_OUTCOME_SKIPPED = "skipped"
#: 좌표 획득 성공(``geocode_status='success'`` 기록).
GEOCODE_OUTCOME_SUCCESS = "success"
#: 주소가 조회되지 않음(``geocode_status='address_error'`` 기록 — 사람이 주소를 고쳐야 한다).
GEOCODE_OUTCOME_FAILED = "failed"
#: 일시 오류로 변환을 마치지 못함(``geocode_status='pending'`` 유지 — 백오프 뒤 재시도).
#:
#: 2026-09-01 사고: 키 부재·타임아웃·429·HTTP 비200 이 전부 ``failed`` 로 굳어 멀쩡한
#: 주소 11건에 "주소오류" 배지가 붙었다. 그 실패는 주소 탓이 아니므로 여기서 가른다.
GEOCODE_OUTCOME_TRANSIENT = "transient"
#: 주소가 비어 변환할 것이 없음(``geocode_status='address_error'`` 기록).
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

    판정 순서:

    1. 주소가 비면 좌표를 지우고 ``geocode_status='address_error'`` + ``geocoded_at`` 를
       기록한다(변환할 것이 없음 — 자동 재시도 대상 아님).
    2. ``address_hash`` 가 현재 주소와 같고 좌표가 이미 있으면 **아무것도 하지 않는다**
       (멱등: 같은 job/outbox 행이 재전달돼도 외부 API 를 다시 부르지 않는다).
    3. 좌표를 얻으면 ``success``.
    4. **일시 오류**(키 부재·타임아웃·429·HTTP 비200 — 변환기가
       :data:`~foms.services.common.address_converter.FAILURE_TRANSIENT` 로 보고)면
       ``geocode_status='pending'`` 을 유지하고 ``geocoded_at`` 만 찍는다. 좌표도
       ``address_hash`` 도 건드리지 않는다 — 이 주소는 아직 **판정된 적이 없다**.
       :mod:`foms.services.geocode_retry` 백오프가 다시 집어간다.
    5. **주소 오류**(카카오가 "그런 주소 없음"이라고 답함)면 좌표를 비우고
       ``address_error`` 를 기록한다. 사람이 주소를 고치면 write 경로가 ``pending`` 으로
       되돌리므로 자동으로 대상에 복귀한다.

    4·5 를 가르지 않던 시절의 결함(2026-09-01): 네트워크 사고가 ``failed`` 로 굳어
    멀쩡한 주소 11건에 "주소오류" 배지가 붙었고, 어느 읽기 경로도 그 건을 다시 시도하지
    않았다.

    Args:
        order: 대상 :class:`~models.Order`(호출자 세션에 attach 된 상태).
        converter: 주소 변환기(테스트 주입용). None 이면 :class:`FOMSAddressConverter` 를
            그 자리에서 만든다(무거운 import 를 호출 시점까지 미룬다).
        now: ``geocoded_at`` 에 기록할 시각. 기본은 :func:`now_utc_naive` — 저장 컬럼이
            naive UTC 규약이라 로컬 시각(``datetime.now()``)을 쓰지 않는다.

    Returns:
        :data:`GEOCODE_OUTCOME_SKIPPED` / :data:`GEOCODE_OUTCOME_SUCCESS` /
        :data:`GEOCODE_OUTCOME_TRANSIENT` / :data:`GEOCODE_OUTCOME_FAILED` /
        :data:`GEOCODE_OUTCOME_NO_ADDRESS` 중 하나.
    """
    stamp = now or now_utc_naive()

    address = extract_address_from_order(order)
    if not address:
        order.lat = None
        order.lng = None
        order.geocode_status = STATUS_ADDRESS_ERROR
        order.geocoded_at = stamp
        return GEOCODE_OUTCOME_NO_ADDRESS

    new_hash = compute_address_hash(address)
    if order.address_hash == new_hash and order.lat is not None and order.lng is not None:
        return GEOCODE_OUTCOME_SKIPPED

    if converter is None:
        from foms.services.common.address_converter import FOMSAddressConverter

        converter = FOMSAddressConverter()
    lat, lng, failure_kind = _convert_with_reason(converter, address)

    order.geocoded_at = stamp

    if lat is not None and lng is not None:
        order.address_hash = new_hash
        order.lat = float(lat)
        order.lng = float(lng)
        order.geocode_status = STATUS_SUCCESS
        return GEOCODE_OUTCOME_SUCCESS

    if failure_kind == FAILURE_TRANSIENT:
        # 판정 보류. 좌표·해시를 건드리지 않아 다음 시도가 처음부터 다시 한다.
        order.geocode_status = STATUS_PENDING
        return GEOCODE_OUTCOME_TRANSIENT

    order.address_hash = new_hash
    order.lat = None
    order.lng = None
    order.geocode_status = STATUS_ADDRESS_ERROR
    return GEOCODE_OUTCOME_FAILED


def _convert_with_reason(converter: Any, address: str) -> tuple[Any, Any, Optional[str]]:
    """변환기에서 ``(lat, lng, failure_kind)`` 를 꺼낸다.

    Args:
        converter: 주소 변환기.
        address: 변환할 주소.

    Returns:
        ``(lat, lng, failure_kind)``. 변환기가 사유를 돌려주지 않는 구형/테스트 대역이면
        실패를 :data:`~foms.services.common.address_converter.FAILURE_PERMANENT` 로 본다
        (사유 불명을 일시 오류로 올리면 재시도가 무한히 돈다).
    """
    with_reason = getattr(converter, "convert_address_with_reason", None)
    if callable(with_reason):
        lat, lng, _status, failure_kind = with_reason(address)
        return lat, lng, failure_kind
    lat, lng, _status = converter.convert_address(address)
    return lat, lng, None if (lat is not None and lng is not None) else FAILURE_PERMANENT
