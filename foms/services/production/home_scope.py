"""생산 첫 화면의 주문 범위 — 켜진 프리랜서는 '내 주문만'.

사장님 2026-11-27 "새 화면에 '내 주문만' 만들어 보내기". 옛 생산 보드가 쓰던 규칙을 그대로 쓴다(새 판정 함수를 만들지 않는다):

* 목록 · 건수 = :func:`foms.services.production_read_model.build_production_orders_query` 의 '내 것만' 갈래
  (``build_mine_sql_filter`` → 프리랜서는 연결 표 ``order_freelancer_links`` 하나).
* 묘비(취소된 주문) = :func:`foms.services.production_change_alerts.collect_production_tombstones` 의 '내 것만' 갈래
  (``is_order_related_to_user`` → 같은 연결 표).

첫 화면의 탭 · 띠 숫자 · 탭 건수 · 찾기 · 바뀐 것 · 받은함은 모두 그 행과 묘비에서 파생되므로, 두 들머리가 이 함수 값 하나를
같이 쓰면 숫자까지 내 주문만 센다. 주문 하나(작업 시트 · 인쇄)는 ``user_can_read_order`` 가, 주소에 실린 번호는 프리랜서
문지기(:mod:`foms.services.auth.freelancer_scope`)가 본다.

시험: tests/security/test_freelancer_production_home.py
"""

from __future__ import annotations

from typing import Any

from foms.services.auth.freelancer_lists import is_list_freelancer


def production_home_mine_only(user: Any) -> bool:
    """생산 첫 화면을 '내 주문만'으로 읽을 사람인가 — 켜진 프리랜서면 True, 그 밖(회사 직원 · 꺼진 프리랜서 · None)은 False.

    쿼리 0(요청 안에서는 프리랜서 설정을 문지기가 이미 읽어 ``g`` 에 둔다).
    """
    return is_list_freelancer(user)


__all__ = ["production_home_mine_only"]
