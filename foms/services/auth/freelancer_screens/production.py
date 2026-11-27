"""프리랜서 화면 묶음: 생산 첫 화면(``/erp/production/home``) · 작업 시트 · 작업지시서 인쇄 — 보기만, 주문은 자기 것만.

사장님 결정(2026-11-27): "새 화면에 '내 주문만' 만들어 보내기" — 옛 생산 보드를 없애며 프리랜서를 새 첫 화면으로 들인다.
옛 보드 · 옛 옆 시트 주소는 넘겨주지 않고 닫는다("이것도 지우기"). "내 주문" 규칙은 옛 보드와 같은 연결 표 하나다
(:mod:`foms.services.auth.freelancer_lists`).

여는 문은 셋뿐이다(모두 GET 전용 라우트).

* ``erp_production_page.erp_production_home`` — 첫 화면. 탭(날짜 · 내 공정 · 바뀐 것 · 찾기) · 셸 조각(``view=fragment``) ·
  날 조각(``view=day``) · 판 조각(``view=panel``)이 모두 한 endpoint 이고, 행 · 건수 · 묘비 두 들머리가 '내 주문만'으로 읽는다
  (:func:`foms.services.production.home_scope.production_home_mine_only`). 그래서 띠 숫자 · 탭 건수 · '전체 N건' ·
  받은함도 내 주문만 센다. 주소의 주문 번호(``?order=`` · 옛 ``?focus_order=``)는 아래 query 표로 문지기가 본다.
* ``erp_production_page.erp_production_sheet_page`` — 작업 시트(주문 1건). URL 주문 번호 + 핸들러 ``user_can_read_order``.
* ``erp_production_page.erp_production_print_sheet`` — 작업지시서 인쇄(주문 1건). 같은 두 겹.

열지 않는 것(허용 목록 밖 = 문지기 기본 거부):

* 도면 카드 — 작은 그림(``erp_production_part_thumb``) · 표시 받아 오기 · PC 도면 창 · 바뀐 기록. 도면 카드 판은 그 날 회사 전체
  주문을 싣는다. 화면도 ``part_view_mode`` 가 프리랜서에게 ``none`` 이라 판 · [도면 카드로 보기] · [바뀐 기록 보기 ›]를 안 그린다.
* 옛 생산 보드 · 옛 옆 시트 · 공정 읽기 GET — 지우는 길이다.
* 상세 묶음 · QR 라벨 · QR 그림은 옛 보드만 쓰던 것이라 이 묶음에서 뺐다. 다른 화면 묶음과 "내 주문 일 API"
  (:mod:`foms.services.auth.freelancer_order_rights`)가 그대로 연다.

쓰기: 화면에는 바뀐 것 [확인했어요]만 있다(사장님 2026-11-27 "회사 영업처럼 보이게" — ``api_production_change_ack`` 는 "내 주문
일 API" 에 남는다). 그 밖 생산 쓰기 여덟은 내 주문이어도 문지기가 막는다
(:data:`foms.services.auth.freelancer_order_rights.CLOSED_ORDER_ENDPOINTS`).

시험: tests/security/test_freelancer_production_home.py
"""
from __future__ import annotations

ALLOWED_ENDPOINTS: frozenset[str] = frozenset({
    "erp_production_page.erp_production_home",
    "erp_production_page.erp_production_sheet_page",
    "erp_production_page.erp_production_print_sheet",
})

#: 셋 다 GET 전용 라우트라 방법 제한이 없다(시험이 라우트 방법을 고정한다 — POST 가 붙으면 여기 제한을 넣어야 한다).
METHOD_LIMITS: dict[str, frozenset[str]] = {}

ORDER_VIEW_ARGS: dict[str, tuple[str, ...]] = {
    "erp_production_page.erp_production_sheet_page": ("order_id",),
    "erp_production_page.erp_production_print_sheet": ("order_id",),
}

ORDER_QUERY_ARGS: dict[str, tuple[str, ...]] = {
    # ?order= — 그 주문의 날 장을 고르고 줄에 테두리(바로가기 · 알림 · 검색), '내 공정' 판 조각(view=panel)의 고른 줄.
    # ?focus_order= — 같은 뜻의 옛 이름(핸들러가 order 가 없을 때 읽는다).
    "erp_production_page.erp_production_home": ("order", "focus_order"),
}
