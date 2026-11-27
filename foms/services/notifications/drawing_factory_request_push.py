"""공장 도면 수정 요청 알림 두 종류 — 종류 이름 · 누르면 여는 곳 · 폰 배너 글(설계서 2026-11-25 §6 · §10, D4).

* ``DRAWING_FACTORY_REQUEST``(공장 [도면 수정 요청]) — 영업 수정 요청(``DRAWING_REVISION``)과 똑같은 꼴(사장님 답 Q11): 도면팀 전원 +
  관리자, 확인 창(실시간 ``interrupt``) + 폰(P1 · 높은 긴급도) + 종. 누르면 도면 작업실 그 주문의 요청사항 칸.
* ``DRAWING_FACTORY_REQUEST_REJECTED``(도면팀 [요청 반려]) — 요청한 사람 한 명에게 종 + 폰. 누르면 생산 첫 화면 '바뀐 것' 탭(반려 줄이
  거기 있다 — 받는 사람은 생산 쪽 사람이다).

알림을 만드는 곳은 라우트(``foms/api/production/drawing_request.py`` · ``foms/api/drawing/erp_orders_drawing_fix.py``). 이 파일은 폰
알림(``push_sender``)과 벨 목록 링크(``foms.api.notifications``)가 같이 읽는 작은 조각만 둔다. 폰 배너는 알림 글(사유)을 읽지 않는다 —
잠금 화면에 사유를 싣지 않는 지금 규칙 그대로, 제목 · 번호 · 고객 이름 · 고정 글만.
"""

from __future__ import annotations

from typing import Any, Tuple

from foms.services.production.nav_target import PRODUCTION_CHANGES_HREF

REQUEST_TYPE = "DRAWING_FACTORY_REQUEST"
REJECTED_TYPE = "DRAWING_FACTORY_REQUEST_REJECTED"
TYPES = (REQUEST_TYPE, REJECTED_TYPE)
#: 알림 제목(§10) — 폰 배너 제목 앞머리도 같은 글.
REQUEST_TITLE = "공장 도면 수정 요청"
REJECTED_TITLE = "도면 수정 요청 반려"
_TITLES = {REQUEST_TYPE: REQUEST_TITLE, REJECTED_TYPE: REJECTED_TITLE}
#: 배너 본문 — §10 알림 글의 앞 문장(대상 · 사유는 싣지 않는다).
_BODIES = {REQUEST_TYPE: "공장 도면 수정 요청이 접수됐어요.", REJECTED_TYPE: "도면 수정 요청이 반려됐어요."}


def _norm(notification_type: Any) -> str:
    return str(notification_type or "").strip().upper()


def is_factory_request_type(notification_type: Any) -> bool:
    """공장 도면 수정 요청 알림 두 종류 중 하나인가(대소문자 · 앞뒤 빈칸 무관)."""
    return _norm(notification_type) in TYPES


def factory_request_deep_link(notification_type: Any, order_id: Any) -> str:
    """누르면 여는 곳 — 요청은 도면 작업실 그 주문 요청사항 칸, 반려는 생산 첫 화면 '바뀐 것' 탭.

    Args:
        notification_type: 알림 종류. order_id: 주문 번호(요청 알림에 없으면 도면 작업실 목록).
    """
    if _norm(notification_type) == REJECTED_TYPE:
        return PRODUCTION_CHANGES_HREF
    try:
        oid = int(order_id) if order_id else 0
    except (TypeError, ValueError):
        oid = 0
    return f"/erp/drawing-workbench/{oid}?tab=requests" if oid > 0 else "/erp/drawing-workbench"


def factory_request_push_text(notification_type: Any, order_id: Any, customer_name: str) -> Tuple[str, str]:
    """폰 배너 (제목, 본문) — ``('공장 도면 수정 요청 · 김가짜', '주문 #12 (김가짜) 공장 도면 수정 요청이 접수됐어요.')`` 꼴.

    Args:
        notification_type: 알림 종류(두 종류 중 하나). order_id: 주문 번호. customer_name: 다듬은 고객 이름(비면 번호만).
    """
    kind = _norm(notification_type)
    head = _TITLES.get(kind, REQUEST_TITLE)
    body = _BODIES.get(kind, _BODIES[REQUEST_TYPE])
    name = str(customer_name or "").strip()
    label = f"주문 #{int(order_id)}" if order_id else "주문"
    if name:
        return f"{head} · {name}", f"{label} ({name}) {body}"
    return head, f"{label} {body}"


__all__ = [
    "REJECTED_TITLE", "REJECTED_TYPE", "REQUEST_TITLE", "REQUEST_TYPE", "TYPES", "factory_request_deep_link",
    "factory_request_push_text", "is_factory_request_type",
]
