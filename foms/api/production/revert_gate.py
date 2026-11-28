"""제작 완료한 주문 되돌리기 둘([완료 취소] · [수정 제작])의 문 — 반장 · 관리자만(사장님 2026-11-28 "파트 계정은 제작 완료 · 보류까지").

``POST /api/orders/<id>/production/uncomplete`` · ``…/production/rework`` 가 생산 쓰기 문(``_production_steps_edit_required`` — 관리자 +
생산팀) **뒤에** 한 번 더 건다. 판정은 한 곳(:func:`foms.services.production.part_access.can_revert_completed` — PC [완료 처리]와 같은
술어)이고 작업 시트도 같은 함수로 두 단추를 그릴지 정한다. 거절은 그 두 길의 다른 거절과 같은 꼴(``{success, code, message}``)이다 —
주문을 읽기 전에 막아 아무것도 안 바뀐다. API 층은 웹 층을 부르지 않는다(레이어 래칫) — 로그인은 ``g.current_user``.
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from flask import g, jsonify

from foms.services.production.part_access import LEAD_ONLY_STEPS_CODE, can_revert_completed


def lead_or_admin_required(message: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """반장 · 관리자만 지나는 데코레이터 — 그 밖(파트 계정 · 파트도 반장도 아닌 생산팀)은 403 ``LEAD_REQUIRED`` + ``message``.

    Args:
        message: 거절 글(해요체 한 문장 — 단추 이름이 든 글).
    """

    def decorate(f: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(f)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            if can_revert_completed(getattr(g, "current_user", None)):
                return f(*args, **kwargs)
            return jsonify({"success": False, "code": LEAD_ONLY_STEPS_CODE, "message": message}), 403

        return wrapped

    return decorate


__all__ = ["lead_or_admin_required"]
