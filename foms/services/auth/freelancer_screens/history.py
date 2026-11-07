"""프리랜서 화면 묶음: 과거 이력 검색(``erp_history`` — /erp/history/).

사용자 결정(2026-11-07): 회사 소속 때 쓰던 화면을 그대로 쓰되 주문은 자기 것만. 이 묶음의 화면 두 개를 연다.

* ``erp_history.history_dashboard`` — 이력 화면(PC 표 · 태블릿 · 모바일 큐 카드 · 셸 조각 ``?view=fragment``).
  켜진 프리랜서는 "내 것만"이 늘 켜져 있다(``erp_mine_filter`` 강제 + 통합 검색 결과 ``from_search=1`` 도 끌 수
  없음 — :func:`foms.web.orders.history.history_dashboard`). 목록 · 건수 · 쪽 수 · 초성 검색이 모두 연결 표
  범위다. 대시보드로 되보내기는 "내 것만"일 때 돌지 않는다. 내보내기(CSV · XLSX)는 이 화면에 없다.
  ``?focus_order=`` 는 화면 JS(static/js/orders/history-mobile.js)가 그 카드를 강조하는 주문 번호라 주문 번호 표에
  둔다(대시보드 · 실측 판과 같게 남의 번호면 404).
* ``erp_history.history_tablet_sheet`` — 태블릿 가로에서 이력 줄을 누르면 여는 읽기전용 시트(주문 1건). URL 의
  ``order_id`` 를 문지기가 본다(남의 주문 · 없는 주문 404, 주소창으로 열면 편집 화면으로 보내기 전에 404).

화면이 부르는 나머지(편집 · 모바일 상세 · 첨부 사진 ``files.view`` · 새 주문)는 이미 열린 문이고 각자 주문 번호를
본다. 도면 작업실 링크 같은 닫힌 문은 그대로 닫혀 있다.

시험: tests/security/test_freelancer_screen_history.py
"""
from __future__ import annotations

ALLOWED_ENDPOINTS: frozenset[str] = frozenset({
    "erp_history.history_dashboard",
    "erp_history.history_tablet_sheet",
})

ORDER_VIEW_ARGS: dict[str, tuple[str, ...]] = {
    "erp_history.history_tablet_sheet": ("order_id",),
}

ORDER_QUERY_ARGS: dict[str, tuple[str, ...]] = {
    "erp_history.history_dashboard": ("focus_order",),
}
