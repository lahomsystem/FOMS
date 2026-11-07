"""화면 묶음: 견적 계산기(WDCalculator) — 계산기 화면과 그 화면이 부르는 견적 · 주문 찾기 · 잇기 API.

견적에는 만든 사람 칸이 없어 "내 견적"은 핸들러가 본다(:mod:`foms.services.wdcalculator.freelancer_estimates`):
내 주문에 이은 견적, 또는 이 로그인에서 내가 만든 안 이은 견적. 남의 견적 · 없는 견적 · 남의 주문은 404.
주문 찾기는 내 주문만 돌려준다. 견적 번호는 주문 번호가 아니라서 URL 표에 넣지 않는다(핸들러가 본다).

계속 막는 것: 제품 설정 화면과 설정 바꾸기(제품 · 추가 옵션 · 비고 · 규격 선택지 저장 · 지우기 — 관리자 일),
비고 묶음 읽기(설정 화면만 쓴다 — 계산기 화면은 템플릿으로 받는다).

시험: tests/security/test_freelancer_screen_wdcalculator.py
"""
from __future__ import annotations

ALLOWED_ENDPOINTS: frozenset[str] = frozenset({
    # 계산기 화면 — 추가 옵션 · 비고 묶음(설정 목록)만 그린다. ?order_id= 는 아래 query 표가 본다.
    "wdcalculator.wdcalculator",
    # 금액 계산 — 제품 단가표로 계산만 한다(저장 · 주문 없음).
    "wdcalculator.api_wdcalculator_calculate",
    # 저장된 견적 찾기 · 열기 · 지우기 · 저장 — 핸들러가 내 견적만(본문 order_id 도 내 주문만).
    "wdcalculator.api_wdcalculator_search_estimates",
    "wdcalculator.api_wdcalculator_estimate",
    "wdcalculator.api_wdcalculator_save_estimate",
    # 견적에 이을 주문 찾기 · 잇기 · 풀기 — 핸들러가 내 주문만.
    "wdcalculator.api_wdcalculator_search_orders",
    "wdcalculator.api_wdcalculator_match_order",
    "wdcalculator.api_wdcalculator_unmatch_order",
    # 주문 저장 뒤 견적 맞추기(옛 클라이언트 호환) — URL 주문은 아래 표, 본문 견적은 그 주문에 이은 것만(모두 고침).
    "wdcalculator.api_orders_wdc_estimate_sync",
})

ORDER_VIEW_ARGS: dict[str, tuple[str, ...]] = {
    "wdcalculator.api_orders_wdc_estimate_sync": ("order_id",),
}

ORDER_QUERY_ARGS: dict[str, tuple[str, ...]] = {
    # 주문 화면에서 여는 계산기(/wdcalculator?order_id=…&estimate_id=…) — 남의 주문 번호면 화면부터 404.
    "wdcalculator.wdcalculator": ("order_id",),
}
