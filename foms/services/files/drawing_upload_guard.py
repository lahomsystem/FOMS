"""도면팀 최종본이 있는 주문에 '도면' 분류 업로드를 받을 때의 확인 규칙(2026-10-04).

2026-09-28 실측 건부터 도면팀↔영업이 ERP 전달·수령 확인으로 도면을 주고받는다. 그 전에는
도면팀이 채널톡에 올린 도면을 영업이 내려받아 고객 컨펌 뒤 ERP 도면 칸에 직접 올렸다. 그
습관이 남아 전달본이 있는 주문에 같은 도면이 한 장 더 붙는다(주문 5407 ``김나리.png`` —
수령 확인 1분 뒤 업로드, 9초 뒤 발주 PUSH). 업로드를 막지는 않는다. 올리는 사람이 알고
올리도록 확인만 받는다.

규칙: 분류가 ``drawing`` 이고, 주문 ``drawing_current_files`` 가 비어 있지 않고, 올리는
사람이 도면팀이 아니면 요청에 ``ack_drawing_final`` 참값이 있어야 한다. 화면(주문 화면·태블릿
실측 폼)이 확인 창을 띄운 뒤 싣는다. 도면 전달 창은 올린 파일을 곧바로 전달하므로 늘 싣는다.
"""
from __future__ import annotations

from typing import Any, Optional

__all__ = [
    "ACK_FIELD",
    "DRAWING_FINAL_EXISTS",
    "drawing_final_ack_block",
    "drawing_final_count",
]

#: 확인을 마쳤다는 요청 필드(form·JSON 공용).
ACK_FIELD = "ack_drawing_final"

#: 확인 없이 올렸을 때 돌려주는 오류 코드.
DRAWING_FINAL_EXISTS = "DRAWING_FINAL_EXISTS"

_TRUTHY = {"1", "true", "yes", "on"}

#: 확인 없이 올려도 되는 팀 — 도면팀은 자기 도면을 올린다.
_EXEMPT_TEAMS = frozenset({"DRAWING"})


def drawing_final_count(structured_data: Any) -> int:
    """도면팀 전달본(``drawing_current_files``) 장수. key 가 없는 항목은 세지 않는다."""
    sd = structured_data if isinstance(structured_data, dict) else {}
    files = sd.get("drawing_current_files")
    if not isinstance(files, list):
        return 0
    return sum(1 for f in files if isinstance(f, dict) and str(f.get("key") or "").strip())


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in _TRUTHY


def drawing_final_ack_block(
    user: Any, order: Any, category: Optional[str], ack: Any,
) -> Optional[tuple[dict, int]]:
    """확인이 필요한데 없으면 ``(응답 dict, 409)``, 아니면 ``None``.

    Args:
        user: 올리는 사용자(``team`` 속성). 없으면 면제하지 않는다.
        order: 대상 주문(``structured_data`` 속성).
        category: 정규화된 첨부 분류.
        ack: 요청의 ``ack_drawing_final`` 값.
    """
    if str(category or "").strip().lower() != "drawing":
        return None
    team = str(getattr(user, "team", "") or "").strip().upper()
    if team in _EXEMPT_TEAMS:
        return None
    count = drawing_final_count(getattr(order, "structured_data", None))
    if count <= 0 or _is_truthy(ack):
        return None
    message = (
        f"도면팀 최종 도면이 이미 ERP 에 있습니다({count}장). "
        "고객 컨펌은 '도면 수령 확인'으로 끝나고, 발주 PUSH 에도 자동으로 들어갑니다. "
        "도면을 고쳐야 하면 '수정 요청'을 쓰세요."
    )
    return {
        "success": False,
        "data": {"count": count},
        "error": DRAWING_FINAL_EXISTS,
        "message": message,
    }, 409
