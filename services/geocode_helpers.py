"""
지오코딩 관련 공유 로직 (Phase C).
주소 추출, address_hash 계산 등.
"""
import hashlib
import re


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


def extract_address_from_structured_data(sd: dict) -> str:
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


def extract_address_from_order(order) -> str:
    """
    Order에서 사용할 주소 문자열 추출.
    ERP Beta: site.address_full or (address_main + address_detail) 우선.
    일반 주문: order.address.
    """
    if order.is_erp_beta and order.structured_data:
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
