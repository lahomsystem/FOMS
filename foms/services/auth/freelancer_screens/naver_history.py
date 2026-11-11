"""프리랜서 화면 묶음: 네이버 수집 **이력** 탭(``admin.naver_ingest_triage``) — 보기만.

사용자 결정(2026-11-11): 프리랜서도 회사 영업과 같게 네이버 '이력'을 본다. '내 담당만'이 기본으로 켜지고(내 주문 =
연결 표), 끄면 다른 이름으로도 찾을 수 있다 — 고객이 주문자 아닌 다른 네이버 아이디로 추가 결제하는 일이 있어서다.

* ``admin.naver_ingest_triage`` — 워크벤치 화면. 켜진 프리랜서는 ``?tab=`` 과 상관없이 이력 탭만 그린다(처리 탭 ·
  처리 단추 · 실패 띠 · 수집 손잡이 없음 — :func:`foms.web.admin.naver_ingest._viewer_is_freelancer`).
  워크벤치 게이트가 꺼진 옛 화면(처리 큐)은 404.
* ``admin.naver_ingest_triage_detail`` — 이력 줄 '원본 보기'(읽기 전용 조각, 버튼 없음).

처리 pane(``triage/pane``) · 배지 수 · 발주확인 · 발송 · 취소 같은 쓰기 라우트는 열지 않는다(문지기 기본 거부).
이력 줄의 FOMS 주문 링크는 편집 화면 문이 주문 번호를 보므로 남의 주문이면 404 다.

시험: tests/security/test_freelancer_screen_naver_history.py
"""
from __future__ import annotations

ALLOWED_ENDPOINTS: frozenset[str] = frozenset({
    "admin.naver_ingest_triage",
    "admin.naver_ingest_triage_detail",
})
