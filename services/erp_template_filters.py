"""ERP 템플릿 필터: 출고/실측/생산 대시보드용."""
import re


def split_count_filter(s, sep=','):
    """문자열을 sep로 나눈 비어있지 않은 항목 개수 (출고 대시보드 제품 수 fallback용)"""
    if not s:
        return 0
    return max(1, len([x for x in str(s).split(sep) if str(x).strip()]))


def split_list_filter(s, sep=','):
    """문자열을 sep로 나눈 리스트 (공백 제거, 출고 대시보드 제품 가로 스태킹용)"""
    if not s:
        return []
    return [x.strip() for x in str(s).split(sep) if x.strip()]


def strip_product_w_filter(value):
    """제품 표시에서 뒤에 붙는 숫자(W) 및 넓이 추종 숫자 제거.
    예: '제품명 120W' -> '제품명', '몰딩여닫이 3600 3600' -> '몰딩여닫이 3600'
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return value
    s = str(value).strip()

    def process_part(p: str) -> str:
        p = re.sub(r'\s*\d+W\s*$', '', p).strip()
        p = re.sub(r'\s+(\d+)\s+\1\s*$', r' \1', p)
        return p.strip()

    parts = [process_part(p) for p in s.split(',')]
    result = ', '.join(p for p in parts if p)
    return result if result else s


def spec_w300_filter(value):
    """실제 길이(W)/300 숫자로 표시 (예: 3600 -> 12). 복합규격(3600x600)이면 첫 숫자 사용"""
    if value is None or value == '':
        return ''
    s = str(value).strip().replace(',', '')
    try:
        m = re.search(r'[\d.]+', s)
        if not m:
            return ''
        n = float(m.group())
        return round(n / 300, 1) if n else ''
    except (ValueError, TypeError):
        return ''


def format_phone_filter(value):
    """전화번호 포맷 (01012345678 -> 010-1234-5678)"""
    if not value:
        return '-'
    digits = re.sub(r'[^0-9]', '', str(value))
    if len(digits) == 11:
        return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
    if len(digits) == 10:
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    return value


def spec_w300_value(value):
    """규격(W)/300 수치 계산 (숫자 반환). 복합규격이면 첫 숫자 사용"""
    if value is None or value == '':
        return 0.0
    s = str(value).strip().replace(',', '')
    try:
        m = re.search(r'[\d.]+', s)
        if not m:
            return 0.0
        n = float(m.group())
        return round(n / 300, 1) if n else 0.0
    except (ValueError, TypeError):
        return 0.0


def register_erp_template_filters(bp):
    """Blueprint에 ERP 템플릿 필터 등록 (Blueprint.add_app_template_filter 사용)"""
    bp.add_app_template_filter(split_count_filter, 'split_count')
    bp.add_app_template_filter(split_list_filter, 'split_list')
    bp.add_app_template_filter(strip_product_w_filter, 'strip_product_w')
    bp.add_app_template_filter(spec_w300_filter, 'spec_w300')
    bp.add_app_template_filter(format_phone_filter, 'format_phone')
