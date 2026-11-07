"""프리랜서 화면 묶음: 출고 · 시공 판(사용자 결정 2026-11-07 — 회사 영업 때 쓰던 화면, 주문은 자기 것만).

여는 것은 판 화면 셋(출고 판 · 태블릿 출고 배정 시트 · 시공 판)과 그 화면이 부르는 **읽기**다. 자기 주문의 쓰기(출고 정보
저장 · 패킹 저장 · 시공일 정하기 · 시공 시작/완료 등)는 이 파일이 다루지 않는다 — 쓰기 결정(D27)은 다른 변경이 맡는다.

"자기 주문만" 거르기는 화면 쪽에 있다.

* 출고 판(:mod:`foms.web.shipment.dashboard`) — 켜진 프리랜서면 모든 조회의 바닥(``base_query``)에 연결 표 조건을 건다
  (검색 날짜 고르기 · 14일 패널 · 목록 · 협력사 희망일 주문까지). mine 강제(``erp_mine_filter``)도 그대로 겹친다.
  회사 전체로 세는 것 — 날짜별 잔여 시공 · 잔여 자수 띠 · 협력사 희망일 판(남의 협력사 주문 · 최근 정한 기록) ·
  AS 일정 추천(근처 남의 AS 주문을 찾는다) · 출고 설정 — 은 숨긴다.
* 태블릿 출고 배정 시트 — 시공팀별 잔여 자수는 그날 회사 전체 주문으로 세므로 프리랜서에게는 빼고 팀 이름만 보인다.
* 시공 판(:mod:`foms.web.construction.dashboard`) — mine 강제 + ``build_mine_sql_filter`` 의 프리랜서 갈래(연결 표).
  숫자판(긴급 · D-3 · 단계별 건수)도 같은 거른 조회에서 센다.

이 묶음이 열지 않는 것(주문 범위로 좁힐 수 없다): 출고 설정 화면 · 설정 읽기/저장 API(회사 시공팀 · 용량), AS 일정 추천
4종(근처 남의 AS 주문을 찾는다), 경로 계산(추천 지도 전용).

시험: tests/security/test_freelancer_screen_shipment.py
"""
from __future__ import annotations

ALLOWED_ENDPOINTS: frozenset[str] = frozenset({
    # 출고 판(PC · 태블릿 · 모바일 큐) — 주문 번호를 받지 않는다(날짜 · 검색어만).
    "erp_shipment_page.erp_shipment_dashboard",
    # 태블릿 출고 배정 시트(주문 1건 조각).
    "erp_shipment_page.erp_shipment_tablet_sheet",
    # 시공 판(PC · 태블릿 작업 모드 · 모바일 큐). ?focus_order= 는 아래 표.
    "erp_construction_page.erp_construction_dashboard",
    # 출고 패킹 체크리스트 읽기(주문 1건). GET 전용 endpoint — 저장(POST)은 다른 endpoint 라 닫혀 있다.
    "erp_shipment.api_shipment_packing_get",
    # 시공 판 상세 패널이 처음 열 때 부르는 주문 1건 묶음(structured GET 과 같은 읽기).
    "erp_orders_structured.api_get_order_detail_payload",
    # 모바일 큐 카드의 QR 라벨 인쇄(주문 1건 — 고객명 · 주문 번호 · 품목 1줄)와 그 안의 QR 그림.
    "erp_dashboard.erp_order_label",
    "orders.api_order_qr_svg",
})

ORDER_VIEW_ARGS: dict[str, tuple[str, ...]] = {
    "erp_shipment_page.erp_shipment_tablet_sheet": ("order_id",),
    "erp_shipment.api_shipment_packing_get": ("order_id",),
    "erp_orders_structured.api_get_order_detail_payload": ("order_id",),
    "erp_dashboard.erp_order_label": ("order_id",),
    "orders.api_order_qr_svg": ("order_id",),
}

ORDER_QUERY_ARGS: dict[str, tuple[str, ...]] = {
    # 시공 판 딥링크 — 60일 창 · 단계와 무관하게 그 주문 줄 하나를 보여 준다.
    "erp_construction_page.erp_construction_dashboard": ("focus_order",),
}
