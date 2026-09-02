"""네이버 정산 API enum 카탈로그 — 코드→한글 라벨 (NAVER-SETTLE-01 §2).

원문은 ``docs/research/2026-09-02-naver-settlement/raw/*.md`` 다(커머스API 공식 문서
발췌). **라벨은 원문 표기를 그대로 옮긴다** — 화면·CSV·회계 대사에서 네이버 판매자센터와
같은 낱말이 보여야 담당자가 두 화면을 대조할 수 있기 때문이다. 코드는 추측으로 늘리지
않는다: 스냅샷에서 처음 본 값을 임의로 넣으면 요청 enum 화이트리스트가 오염되고,
쓰기 코드는 읽기 코드의 부분집합이라 400 이 난다(2026-08 WRONG_DELAYED_DELIVERY 사고).

**의존성 없는 모듈**이다(``constants.py`` 와 같은 규율). 클라이언트는 요청 파라미터
검증에, 조회 커널·API 는 라벨 변환에 쓴다 — 양쪽이 각자 import 한다.

미등록 코드를 만나면 :func:`label` 이 코드를 그대로 돌려준다. 네이버가 값을 늘려도
화면이 빈칸이 되지 않게 하기 위해서다(라벨은 표시용, 판정용이 아니다).
"""

from __future__ import annotations

from typing import Mapping, Optional

#: 조회 기간 기준(``periodType`` 요청 파라미터). settle/case·commission-details 공용.
#: ``SETTLE_CASEBYCASE_PAY_DATE`` 일 때만 :data:`SETTLE_DECISION_TYPES` 가 뜻을 가진다.
PERIOD_TYPES: dict[str, str] = {
    "SETTLE_CASEBYCASE_SETTLE_SCHEDULE_DATE": "정산 예정일",
    "SETTLE_CASEBYCASE_SETTLE_BASIS_DATE": "정산 기준일",
    "SETTLE_CASEBYCASE_SETTLE_COMPLETE_DATE": "정산 완료일",
    "SETTLE_CASEBYCASE_PAY_DATE": "결제일",
    "SETTLE_CASEBYCASE_TAXRETURN_BASIS_DATE": "세금 신고 기준일",
}

#: 결제일 구분(``settleDecisionType``). periodType 이 결제일 기준일 때만 의미가 있다.
SETTLE_DECISION_TYPES: dict[str, str] = {
    "SETTLED": "정산 확정 건",
    "UNSETTLED": "정산 미확정 건",
    "BEFORE_CANCEL": "정산 전 취소 건",
}

#: 정산 상태 구분(``settleType``) — 요청 필터이자 응답 값.
#: 차감/환급 계열은 :data:`NEGATIVE_SETTLE_TYPES` 참고.
SETTLE_TYPES: dict[str, str] = {
    "NORMAL_SETTLE_ORIGINAL": "일반 정산",
    "NORMAL_SETTLE_AFTER_CANCEL": "정산 후 취소",
    "NORMAL_SETTLE_BEFORE_CANCEL": "정산 전 취소",
    "QUICK_SETTLE_ORIGINAL": "빠른정산",
    "QUICK_SETTLE_CANCEL": "빠른정산 회수",
    "QUANTITY_CANCEL_DEDUCTION": "수량 취소 정산(공제)",
    "QUANTITY_CANCEL_RESTORE": "수량 취소 정산(환급)",
}

#: 정산 대상 구분(``productOrderType`` 응답 값). 상품 주문 외에 배송비·기타 비용·리뷰 적립
#: 같은 비주문 행이 섞여 온다 — ERP 주문 매칭은 ``PROD_ORDER`` 행만 시도한다.
PRODUCT_ORDER_TYPES: dict[str, str] = {
    "PROD_ORDER": "상품 주문",
    "DELIVERY": "배송비",
    "EXTRAFEE": "기타 비용",
    "WITHDRAW": "결제 수단 출금",
    "REFUND": "구매자 환불",
    "PL_REFUND": "후불 결제 환불",
    "DEDUCTION_RESTORE": "기타 공제 환급",
    "PROD_PAY": "상품 결제",
    "PURCHASE_REVIEW": "텍스트 리뷰",
    "PREMIUM_PURCHASE_REVIEW": "포토/동영상 리뷰",
    "REGULAR_PURCHASE_REVIEW": "알림받기 동의 회원 리뷰 추가 적립",
    "ONE_MONTH_PURCHASE_REVIEW": "한 달 사용 텍스트 리뷰",
    "ONE_MONTH_PREMIUM_PURCHASE_REVIEW": "한 달 사용 포토/동영상 리뷰",
    "REVIEW": "리뷰 적립",
    "ETC_COUPON": "기타 할인",
    "QUICK_SETTLE": "빠른정산",
    "QUANTITY_CANCEL": "수량 취소",
    "DIFFERENCE_SETTLE": "차액 정산",
    "DEPOSIT_SETTLE": "보증금",
    "RENTAL_ORDER": "렌탈 주문",
    "MANUAL_ORDER": "수기 주문",
    "RENTAL_SCHEDULED_ORDER": "월 렌탈료 주문",
    "PREFERENTIAL_COMMISSION": "우대 수수료 환급",
    "POINT_ACCUMULATION": "포인트 적립",
    "POST_ORDER_ADJUSTMENT_AMOUNT": "주문 후 변동 금액",
    "CSF": "통관 대행료",
    "CONCESSION": "구매자 보상",
}

#: 수수료 타입(``commissionType`` 응답 값). 같은 상품 주문이 유형별로 여러 줄로 분해된다.
COMMISSION_TYPES: dict[str, str] = {
    "SALE_COMMISSION": "(구)판매 수수료",
    "PAY_COMMISSION": "Npay 수수료",
    "CHNL_COMMISSION": "채널 수수료",
    "ISTLM_COMMISSION": "무이자 할부 수수료",
    "PUBLISHING_COMMISSION": "퍼블리싱 수수료",
    "INFLOW_COMMISSION": "유입 수수료",
    "SERVICE_COMMISSION": "솔루션 사용료",
    "CONTRACT_COMMISSION": "계약 수수료",
    "PACKAGE_COMMISSION": "패키지 사용료",
    "PARTNER_COMMISSION": "제휴 사용료",
    "PLATFORM_COMMISSION": "판매 수수료",
    "VERTICAL_COMMISSION": "버티컬 사용료",
    "PURCHASER_COMMISSION": "구매자 수수료",
    "PRICE_COMPARISON_COMMISSION": "가격비교 수수료",
}

#: 결제 수단(``payMeansType`` 응답 값).
PAY_MEANS_TYPES: dict[str, str] = {
    "PAYMEANS_TYPE_ALL": "전체",
    "PAYMEANS_TYPE_BANK": "실시간 계좌 이체",
    "PAYMEANS_TYPE_CCARD": "신용카드",
    "PAYMEANS_TYPE_CHAMT": "(구)구매자충전금",
    "PAYMEANS_TYPE_CHKAC": "(구)체크아웃적립금",
    "PAYMEANS_TYPE_DON": "(구)네이버캐쉬",
    "PAYMEANS_TYPE_MOBIL": "휴대폰 결제",
    "PAYMEANS_TYPE_NCASH": "네이버페이 포인트·머니",
    "PAYMEANS_TYPE_POINT": "포인트 결제",
    "PAYMEANS_TYPE_VACCT": "무통장입금",
    "PAYMEANS_TYPE_SKIP": "나중에결제",
    "PAYMEANS_TYPE_PAYLATER": "후불 결제",
    "PAYMEANS_TYPE_GIFTCARD": "기프트 카드",
    "PAYMEANS_TYPE_NONE": "주결제 수단 없음",
    "PAYMEANS_TYPE_NMP_DISCOUNT": "네이버 할인지원금",
    "PAYMEANS_TYPE_OVERSEAS_CARD": "해외 카드",
}

#: 정산 방법(``settleMethodType`` 응답 값). ``CHARGE_AMT`` 는 통장에 찍히지 않는다 —
#: 입금 대사에서 계좌 이체와 반드시 갈라 봐야 한다.
SETTLE_METHOD_TYPES: dict[str, str] = {
    "ACCOUNT": "계좌 이체",
    "CHARGE_AMT": "충전금",
}

#: 은행·증권사(``bankType`` 응답 값). 원문 순서 그대로 옮겼다.
BANK_TYPES: dict[str, str] = {
    "KDB": "산업은행",
    "IBK": "기업은행",
    "KB": "KB국민은행",
    "KEB_OLD": "외환은행",
    "SUHYUP": "수협은행",
    "KOREAEXIM": "수출입은행",
    "NH": "NH농협은행",
    "LNH": "지역농.축협",
    "WOORI": "우리은행",
    "SC": "SC제일은행",
    "CITI": "한국씨티은행",
    "IM": "iM뱅크",
    "BUSAN": "부산은행",
    "KWANGJU": "광주은행",
    "JEJU": "제주은행",
    "JEONBUK": "전북은행",
    "KYONGNAM": "경남은행",
    "SAEMAUL": "새마을금고",
    "SHINHYUP": "신협",
    "FSB": "저축은행",
    "HSBC": "HSBC은행",
    "DEUTSCHE_BANK": "도이치은행",
    "JP_MORGAN": "제이피모간체이스",
    "BOA": "BOA은행",
    "BNP": "비엔피파리바은행",
    "ICBC": "중국공상은행",
    "NFCF": "산림조합중앙회",
    "POST": "우체국",
    "KEB_HANA": "하나은행",
    "SHINHAN": "신한은행",
    "KBANK": "케이뱅크",
    "KKOBANK": "카카오뱅크",
    "TOSS": "토스뱅크",
    "DAISHIN_BANK": "대신저축은행",
    "SBISB": "에스비아이저축은행",
    "HK_BANK": "에이치케이저축은행",
    "WELCOME_BANK": "웰컴저축은행",
    "SHINHAN_SAVING": "신한저축은행",
    "DONGYANG_SEC": "유안타증권",
    "HYNDAI_SEC": "KB증권",
    "IBK_IVST_SEC": "IBK투자증권",
    "MIRAEASSET": "미래에셋대우",
    "MIRAEASSET_DAEWOO": "미래에셋대우",
    "SANSUNG_SEC": "삼성증권",
    "HANGKOOK_IVST_SEC": "한국투자증권",
    "WOORI_IVST_SEC": "NH투자증권",
    "KYOBO_IVST_SEC": "교보증권",
    "HI_IVST_SEC": "하이투자증권",
    "HMC_IVST_SEC": "현대자증권",
    "KIWOOM_IVST_SEC": "키움증권",
    "EBEST_IVST_SEC": "이베스트투자증권",
    "SK_SEC": "SK증권",
    "DAESHIN_SEC": "대신증권",
    "HANWHA_SEC": "한화투자증권",
    "HANA_DAETOO_SEC": "하나금융투자",
    "SHINHAN_IVST": "신한금융투자",
    "DONGBU_SEC": "DB금융투자",
    "EUGENE_IVST_SEC": "유진투자증권",
    "MERITZ_SEC": "메리츠증권",
    "NH_NONGHYUP_SEC": "NH농협증권",
    "BOOKOOK_SEC": "부국증권",
    "SHINYOUNG_SEC": "신영증권",
    "LIG_IVST_SEC": "케이프투자증권",
    "KSFC": "한국증권금융",
}

#: 부가세 상세 유형(``detailType`` 응답 값) — 결제 대금 정산·혜택 정산·공제/환급.
VAT_DETAIL_TYPES: dict[str, str] = {
    "VOUCH_DETAIL_PAYMENT_SETL": "결제 대금 정산",
    "VOUCH_DETAIL_PRODUCT_COUPON_SETL": "혜택 정산(상품 할인)",
    "VOUCH_DETAIL_ORDER_COUPON_SETL": "혜택 정산(스토어 할인)",
    "VOUCH_DETAIL_DLVFEE_COUPON_SETL": "혜택 정산(배송비 할인)",
    "VOUCH_DETAIL_RTNDLV": "공제/환급(반품 배송비)",
    "VOUCH_DETAIL_ETCDLV": "공제/환급(기타)",
    "VOUCH_DETAIL_DCCNCL": "공제/환급(복수구매 할인 취소)",
    "VOUCH_DETAIL_DLVREC": "공제/환급(배송비 금액 변동)",
    "VOUCH_DETAIL_DLCNCL": "공제/환급(배송비 할인 금액 변동)",
    "VOUCH_DETAIL_COUPON_SETL": "혜택 정산",
    "VOUCH_DETAIL_DDTN_RSTOR": "공제/환급",
}

#: 부가세 증빙 상태(``status`` 응답 값).
VAT_STATUSES: dict[str, str] = {
    "VOUCH_PUBLICATION": "원주문 매출",
    "VOUCH_CANCEL": "주문 취소",
    "VOUCH_RSTOR_PUBLICATION": "공제/환급",
    "VOUCH_RSTOR_CANCEL": "환급 취소",
}

#: 차감/환급 계열 정산 구분 — 원거래와 부호가 반대다(문서 서술 근거).
#:
#: **부호 판정에 쓰지 않는다.** 금액의 부호는 네이버가 준 값을 그대로 믿는다(재계산 금지).
#: 이 집합은 라벨·필터·예외 큐 분류 같은 **표시 목적** 전용이다.
NEGATIVE_SETTLE_TYPES: frozenset[str] = frozenset({
    "NORMAL_SETTLE_AFTER_CANCEL",
    "NORMAL_SETTLE_BEFORE_CANCEL",
    "QUICK_SETTLE_CANCEL",
    "QUANTITY_CANCEL_RESTORE",
})


def label(mapping: Mapping[str, str], code: Optional[str]) -> str:
    """enum 코드를 한글 라벨로 바꾼다 — 모르는 코드는 코드 그대로 돌려준다.

    Args:
        mapping: 이 모듈의 카탈로그 dict 중 하나(예: :data:`SETTLE_TYPES`).
        code: 네이버 응답의 enum 코드. ``None``/빈 문자열이면 빈 문자열을 돌려준다.

    Returns:
        한글 라벨. 카탈로그에 없으면 입력 코드 문자열(화면이 빈칸이 되지 않게).
    """
    if not code:
        return ""
    text = str(code)
    return mapping.get(text, text)


__all__ = [
    "PERIOD_TYPES",
    "SETTLE_DECISION_TYPES",
    "SETTLE_TYPES",
    "PRODUCT_ORDER_TYPES",
    "COMMISSION_TYPES",
    "PAY_MEANS_TYPES",
    "SETTLE_METHOD_TYPES",
    "BANK_TYPES",
    "VAT_DETAIL_TYPES",
    "VAT_STATUSES",
    "NEGATIVE_SETTLE_TYPES",
    "label",
]
