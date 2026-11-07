"""프리랜서 화면 묶음: 생산 판(PC 목록 · 휴대폰 큐 · 태블릿 칸반)과 그 화면이 부르는 읽기 문.

사용자 결정(2026-11-07): 회사 소속 영업 때 쓰던 화면은 그대로 쓰되 주문은 자기 것만. 생산 판은 주문 목록 ·
숫자판(단계 수 · 긴급/D-n 배지) · 칸반 · 취소 묘비가 모두 같은 쿼리(``build_production_orders_query``)와
같은 "내 것" 판정(``is_order_related_to_user``)에서 나온다. 켜진 프리랜서는 ``erp_mine_only_from_request`` 가
늘 True 이고, 그 "내 것" 은 연결 표 하나다(:mod:`foms.services.auth.freelancer_lists`) — 그래서 이 판에서
보이는 주문 · 세는 숫자는 모두 내 주문뿐이다. 숫자판 조각 캐시 열쇠에는 프리랜서 표시가 붙는다
(:func:`foms.services.production_read_model.production_summary_slice_key`).

여는 문(한 줄 이유):

* ``erp_production_page.erp_production_dashboard`` — 생산 판. 목록 · 숫자 · 칸반 · 묘비 모두 내 주문만(위).
  검색 딥링크 ``?focus_order=`` 는 아래 query 표로 문지기가 내 주문인지 본다(핸들러도 한 번 더 본다).
* ``erp_production_page.erp_production_tablet_sheet`` — 태블릿 칸반 카드 옆 시트(주문 1건 읽기). URL 주문 번호.
* ``erp_orders_production.api_production_steps_get`` — 공정 체크 시트 읽기(GET 전용 endpoint, 쓰기 POST 는
  다른 endpoint 라 닫혀 있다). URL 주문 번호.
* ``erp_orders_structured.api_get_order_detail_payload`` — PC 목록 상세 패널 lazy 읽기(이미 연 structured GET
  보다 적게 싣는다). URL 주문 번호.
* ``erp_dashboard.erp_order_label`` — 휴대폰 큐 카드의 QR 라벨 인쇄 화면(주문 1건 읽기). URL 주문 번호.
* ``orders.api_order_qr_svg`` — 그 라벨이 싣는 QR 그림(그 주문 모바일 상세 주소만 담는다). URL 주문 번호.

닫아 둔 것(쓰기 — 다른 변경이 맡는다): 제작 시작 · 완료 · 수정 제작 · 제작 취소 · 완료 취소 · 변경 확인 ·
보류 · 공정 체크 쓰기 · 불량 보고 · 물류 상태, 출고 배정. 판 안의 단추는 그대로 그려지지만 누르면 문지기가 403 이다.

시험: tests/security/test_freelancer_screen_production.py
"""
from __future__ import annotations

ALLOWED_ENDPOINTS: frozenset[str] = frozenset({
    "erp_production_page.erp_production_dashboard",
    "erp_production_page.erp_production_tablet_sheet",
    "erp_orders_production.api_production_steps_get",
    "erp_orders_structured.api_get_order_detail_payload",
    "erp_dashboard.erp_order_label",
    "orders.api_order_qr_svg",
})

ORDER_VIEW_ARGS: dict[str, tuple[str, ...]] = {
    "erp_production_page.erp_production_tablet_sheet": ("order_id",),
    "erp_orders_production.api_production_steps_get": ("order_id",),
    "erp_orders_structured.api_get_order_detail_payload": ("order_id",),
    "erp_dashboard.erp_order_label": ("order_id",),
    "orders.api_order_qr_svg": ("order_id",),
}

ORDER_QUERY_ARGS: dict[str, tuple[str, ...]] = {
    # 검색 카드 딥링크 — 단계 버킷 · 페이지와 무관하게 그 주문 줄을 끼워 넣는다.
    "erp_production_page.erp_production_dashboard": ("focus_order",),
}
