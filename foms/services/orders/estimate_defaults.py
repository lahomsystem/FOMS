"""Estimate document defaults, ERP draft placeholders, and related literals."""

import copy

# ERP draft/placeholder (실제 운영 로직에서 사용)
ERP_DRAFT_PLACEHOLDER_CUSTOMER = "ERP Order"
ERP_DRAFT_PLACEHOLDER_PHONE = "000-0000-0000"
ERP_DRAFT_PLACEHOLDER_PRODUCT = "ERP Order"

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

_ESTIMATE_PAYMENT_NOTICE = '* 입금 시 예약금을 제외한 잔금만 납부 바랍니다.'

_ESTIMATE_PAYMENT_ACCOUNTS_DEFAULT = [
    {
        'bank': '기업은행',
        'account': '461-082990-04-011',
        'holder': '주식회사 하우드시스템',
    },
    {
        'bank': '국민은행',
        'account': '818737-00-002568',
        'holder': '주식회사 하우드시스템',
    },
]

_ESTIMATE_PAYMENT_ACCOUNTS_FACTORY2 = [
    {
        'bank': '기업은행',
        'account': '461-091619-01-010',
        'holder': '김은지 라홈시스템',
    },
]


def _build_estimate_payment_info(accounts: list[dict]) -> dict:
    """다중 계좌 목록과 레거시 단일 bank/account/holder 필드를 함께 구성한다."""
    primary = accounts[0] if accounts else {}
    return {
        'notice': _ESTIMATE_PAYMENT_NOTICE,
        'accounts': list(accounts),
        'bank': primary.get('bank', ''),
        'account': primary.get('account', ''),
        'holder': primary.get('holder', ''),
    }


ESTIMATE_PAYMENT_INFO = _build_estimate_payment_info(_ESTIMATE_PAYMENT_ACCOUNTS_DEFAULT)

ESTIMATE_PAYMENT_INFO_FACTORY2 = _build_estimate_payment_info(_ESTIMATE_PAYMENT_ACCOUNTS_FACTORY2)


def resolve_estimate_payment_info(factory2: bool = False) -> dict:
    """견적/계약 결제정보. factory2=True이면 2공장 전용 계좌를 반환한다."""
    template = ESTIMATE_PAYMENT_INFO_FACTORY2 if factory2 else ESTIMATE_PAYMENT_INFO
    return copy.deepcopy(template)

ESTIMATE_STATUS = {
    'DRAFT': '작성중',
    'ISSUED': '발급완료',
    'SENT': '발송완료',
    'CONFIRMED': '계약확정',
    'CANCELLED': '취소',
}

ESTIMATE_LEGAL_NOTICE = '본 계약서는 공급자와 계약자간에 법적 효력을 지니고 있습니다.'
