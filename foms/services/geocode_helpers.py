"""
지오코딩 관련 공유 로직 (Phase C).
주소 추출, address_hash 계산 등.
"""
import hashlib
import re
from typing import Any

from foms.services.erp_order_flags import is_erp_order_record

__all__ = [
    "compute_address_hash",
    "extract_address_from_structured_data",
    "extract_address_from_order",
    "get_order_display_address",
]


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
