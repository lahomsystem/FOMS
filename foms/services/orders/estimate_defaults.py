"""Estimate document defaults, ERP draft placeholders, and related literals."""

# ERP draft/placeholder (실제 운영 로직에서 사용)
ERP_DRAFT_PLACEHOLDER_CUSTOMER = "ERP Beta"
ERP_DRAFT_PLACEHOLDER_PHONE = "000-0000-0000"
ERP_DRAFT_PLACEHOLDER_PRODUCT = "ERP Beta"

# ============================================
# 견적서/계약서 상수 (하우드시스템)
# ============================================
ESTIMATE_COMPANY_INFO = {
    'name': '주식회사 하우드시스템',
    'ceo': '김성일',
    'business_number': '503-88-02558',
    'address': '경기도 김포시 대곶면 오니산로 153번길 82',
    'industry': '제조 도소매 / 목재 가구',
    'phone': '031-985-4261',
    'customer_center': '1566-0703',
    'website': 'www.haudsystem.com',
}

ESTIMATE_PAYMENT_INFO = {
    'bank': '기업은행',
    'account': '461-082990-04-011',
    'holder': '주식회사 하우드시스템',
    'notice': '* 입금 시 예약금을 제외한 잔금만 납부 바랍니다.',
}

ESTIMATE_STATUS = {
    'DRAFT': '작성중',
    'ISSUED': '발급완료',
    'SENT': '발송완료',
    'CONFIRMED': '계약확정',
    'CANCELLED': '취소',
}

ESTIMATE_LEGAL_NOTICE = '본 계약서는 공급자와 계약자간에 법적 효력을 지니고 있습니다.'
