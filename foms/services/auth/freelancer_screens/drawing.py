"""프리랜서 화면 묶음: 도면 작업실 — 판 화면(목록 · 상세 실행판 · 태블릿 관리 시트 · 도면 마법사)과 그 화면이 읽는 것.

사용자 결정(2026-11-07): 회사 영업 때 쓰던 화면을 그대로 쓰되 주문은 자기 것만. 자기 주문의 쓰기 API(수정 요청 ·
수령 확정 · 고객 보내기 등)는 이 묶음이 아니라 D27(자기 주문 쓰기는 회사 직원과 같게) 쪽이 연다. 이 묶음이 여는 것과 까닭:

* 목록(``erp_drawing_workbench_dashboard``) — "내 것만"이 강제로 켜진다(``erp_mine_only_from_request`` →
  ``build_mine_sql_filter`` 의 프리랜서 갈래 = 연결 표). 줄 · 칸 숫자 · '누적 완료' 숫자 모두 그 거른 모집단에서
  센다. 캐시 키에는 프리랜서 표시를 더했다(:mod:`foms.web.drawing.workbench`). ``?focus_order=`` 는 주문 번호.
* 주문 하나(상세 · 태블릿 시트 · 마법사 화면) — URL 주문 번호를 문지기가 본다(남의 주문 404). 화면이 읽는 것은
  모두 그 주문 하나(이력 · 첨부 · 고객 보내기 기록 · 제품)뿐이다.
* 마법사 읽기 — 상태 · 전달 대기 · 버전 목록 · 버전 내용 · 그림 원본(key 는 이 주문 접두어만 받는다), 협력사 주문
  로고(URL 주문 하나), 주문과 무관한 도면팀 설정 읽기 2개(프리셋 목록 · 자재표 계산 숫자 — GET 전용 endpoint).

열지 않는 읽기: AI 도면팀원 노트(도면팀 내부 · 여러 주문 그림을 견준다), 직원 목록(도면 담당 고르기 창), 협력사 옵션
확인(전달 창), 도면방 PUSH 미리보기(도면팀 PUSH).

시험: tests/security/test_freelancer_screen_drawing.py
"""
from __future__ import annotations

_ORDER = ("order_id",)

#: 주문 번호를 URL 에 싣는 것(남의 주문이면 문지기가 404).
_ORDER_URL_ENDPOINTS: tuple[str, ...] = (
    # 판 화면 — 상세 실행판 · 태블릿 관리 시트 · 도면 마법사
    "erp_drawing_workbench.erp_drawing_workbench_detail",
    "erp_drawing_workbench.erp_drawing_workbench_tablet_sheet",
    "erp_drawing_workbench.erp_drawing_workbench_wizard",
    # 마법사 읽기 — 상태 · 전달 대기 · 버전 목록 · 버전 내용 · 그림 원본 · 협력사 로고
    "erp_orders_drawing_wizard.api_get_drawing_wizard",
    "erp_orders_drawing_wizard.api_get_drawing_wizard_pending",
    "erp_orders_drawing_wizard.api_get_drawing_wizard_versions",
    "erp_orders_drawing_wizard.api_get_drawing_wizard_version_content",
    "erp_orders_drawing_wizard.api_get_drawing_wizard_asset_raw",
    "partner_api.order_logo",
)

#: 주문 번호를 받지 않는 것 — 주문과 무관한 도면팀 설정 읽기(GET 전용 endpoint, 저장은 다른 endpoint).
#: 주문 번호 분류 래칫(tests/security/test_freelancer_order_scope.py)의 "주문 번호 없음" 표에도 같은 두 이름이 있다.
NO_ORDER_ID_ENDPOINTS: frozenset[str] = frozenset({
    "erp_orders_drawing_wizard.api_get_drawing_wizard_presets",
    "erp_orders_drawing_wizard.api_get_drawing_wizard_bom_rules",
})

ALLOWED_ENDPOINTS: frozenset[str] = frozenset({
    # 목록 — 강제 "내 것만"(위 설명)
    "erp_drawing_workbench.erp_drawing_workbench_dashboard",
    *_ORDER_URL_ENDPOINTS,
    *NO_ORDER_ID_ENDPOINTS,
})

ORDER_VIEW_ARGS: dict[str, tuple[str, ...]] = {endpoint: _ORDER for endpoint in _ORDER_URL_ENDPOINTS}

ORDER_QUERY_ARGS: dict[str, tuple[str, ...]] = {
    # 검색 카드 딥링크 — seed 캡 · 필터와 무관하게 그 주문 줄을 끼워 넣는다.
    "erp_drawing_workbench.erp_drawing_workbench_dashboard": ("focus_order",),
}
