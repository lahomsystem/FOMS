"""FCOMM-01 J8: 켜진 프리랜서는 내 정보 화면에서 이름을 바꿀 수 없다(이름 = 수수료 맞출 이름과 같은 사람 표시).

예전에는 여기서 프리랜서의 발주사 · 담당자 바꾸기(D21), 채널톡 PUSH 종류(D22), 퀘스트 승인 단계(D23 · D25)도
막았다. 사용자 결정 D27(2026-11-07 — "주문건만 자기 것만 보이고 이전 회사 소속일 때랑 동일한 사용")로 그 막기는
모두 걷었다 — 자기 주문에서는 회사 영업 직원과 같고, 남의 주문은 문지기 · 주문 단위 판정이 막는다
(:mod:`foms.services.auth.freelancer_order_rights`). 수수료에 닿는 바꾸기(발주사 · 담당자 · 실측일)는 수수료 탭
"본인 수정" 표시와 변경 기록으로 회계팀이 본다.

스펙: docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §1.2 J8 · §6.6 (D27)
시험: tests/security/test_freelancer_edit_guards.py
"""
from __future__ import annotations

from typing import Any, Optional

from flask import flash

from foms.services.auth.freelancer_scope import is_freelancer_user

PROFILE_NAME_LOCKED_MSG = "이름은 관리자에게 바꿔 달라고 해 주세요."


def freelancer_profile_name(user: Any, posted_name: Optional[str]) -> Optional[str]:
    """내 정보 저장에 쓸 이름 — 켜진 프리랜서면 언제나 지금 이름(바꾸려 했으면 안내 한 줄), 아니면 보낸 이름.

    Args:
        user: 저장할 사용자 행.
        posted_name: 폼이 보낸 이름.

    Returns:
        ``user.name`` 에 넣을 이름.
    """
    if not is_freelancer_user(user):
        return posted_name
    current = getattr(user, "name", None)
    if (posted_name or "").strip() and (posted_name or "").strip() != (current or "").strip():
        flash(PROFILE_NAME_LOCKED_MSG, "warning")
    return current


__all__ = ["PROFILE_NAME_LOCKED_MSG", "freelancer_profile_name"]
