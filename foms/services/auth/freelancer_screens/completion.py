"""프리랜서 화면 묶음: 완료 판 · AS 판(판 화면 · 조각 · 읽기 API).

목록은 모두 "자기 주문만"으로 강제된다 — 두 판 모두 :func:`foms.services.common.erp_mine_filter` 의 강제 켜짐
(완료 판은 ``erp_mine_only_for_construction``, AS 판은 ``erp_mine_only_from_request``)과
``build_mine_sql_filter`` / ``is_order_related_to_user`` 의 프리랜서 갈래(연결 표 하나)를 탄다. 숫자(완료 판 KPI ·
AS 탭 건수 · 버킷 요약)도 같은 거른 모집단에서 센다. AS 행이 가리키는 **다른 주문**(기준 일정 링크 · 영업 전달
배정의 기준 실측 주문)은 ``user_can_read_order`` 가 참일 때만 그린다
(:mod:`foms.services.as_dashboard_display` 의 ``viewer`` 인자).

여는 것(한 줄 이유):

* ``erp_completion_page.erp_completion_dashboard`` — 완료 판. 목록 · KPI 는 강제 거른 로더(``_load_completion_orders``).
* ``erp_completion_page.erp_completion_export`` — 완료 판 CSV. 판과 같은 로더 · 같은 거르기(내 줄만).
* ``erp_completion_page.erp_completion_tablet_sheet`` — 완료 판 행을 누르면 여는 정산 조각(주문 1건, URL 번호 판정).
* ``erp_orders_completion.api_orders_completion`` — 완료 판 PC 목록 JSON. 판과 같은 로더.
* ``erp_as_page.erp_as_dashboard`` — AS 판. 목록 · 탭 건수는 강제 거른 base 쿼리, 기준 주문은 읽기 판정.
* ``erp_as_page.erp_as_card_detail`` · ``erp_as_page.erp_as_timeline`` — AS 카드 상세 · 회차 차트 조각(주문 1건).

이 파일은 판 화면과 읽기만 연다. 판에서 부르는 주문 쓰기 API(정산 청구 · 현금영수증 · AS 등록/기록/판정/비용/일정
링크/전달 배정 · 첨부 순서 · ``update_order_field``)는 D27 변경(자기 주문 쓰기는 회사 직원과 같게)이 맡는다.

여기서 열지 않는 읽기(전역 — 자기 주문만으로 좁힐 수 없다): 근처 주문 찾기(``orders.api_orders_nearby`` — 남의 주문을
위치로 찾는다, 일정 링크 · 전달 배정 쓰기 창 전용), 시공자 목록 설정(``erp_shipment.api_erp_shipment_settings_get`` —
전역 설정, 시공자 편집기 전용), 부서 직원 목록(``erp_map.api_erp_users_list`` — 정산 청구 폼 전용), AS PUSH
미리보기(``channel_integration.api_channel_push_preview`` — AS PUSH 보내기 흐름 전용, 이 시점 프리랜서 PUSH 는 영발 ·
실측만, D22), AS 지도(``erp_map.map_view`` — 전체 주문 지도).

시험: tests/security/test_freelancer_screen_completion.py
"""
from __future__ import annotations

ALLOWED_ENDPOINTS: frozenset[str] = frozenset({
    "erp_completion_page.erp_completion_dashboard",
    "erp_completion_page.erp_completion_export",
    "erp_completion_page.erp_completion_tablet_sheet",
    "erp_orders_completion.api_orders_completion",
    "erp_as_page.erp_as_dashboard",
    "erp_as_page.erp_as_card_detail",
    "erp_as_page.erp_as_timeline",
})

#: 모두 GET 전용 라우트라 방법 제한이 없다.
METHOD_LIMITS: dict[str, frozenset[str]] = {}

ORDER_VIEW_ARGS: dict[str, tuple[str, ...]] = {
    "erp_completion_page.erp_completion_tablet_sheet": ("order_id",),
    "erp_as_page.erp_as_card_detail": ("order_id",),
    "erp_as_page.erp_as_timeline": ("order_id",),
}

#: 검색 딥링크 ``?focus_order=`` — 로더가 거른 범위 안에서만 찾지만, 남의 번호는 문지기에서 404 로 끝낸다
#: (모바일 홈 · 실측 판과 같은 규칙).
ORDER_QUERY_ARGS: dict[str, tuple[str, ...]] = {
    "erp_completion_page.erp_completion_dashboard": ("focus_order",),
    "erp_completion_page.erp_completion_export": ("focus_order",),
    "erp_orders_completion.api_orders_completion": ("focus_order",),
    "erp_as_page.erp_as_dashboard": ("focus_order",),
}
