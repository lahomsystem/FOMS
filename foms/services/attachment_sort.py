"""AS 첨부 표시·전송 순서 (AS-SORT-01).

``OrderAttachment.id`` 는 병렬 업로드 완료 순이라 사용자가 정한 순서와 어긋난다.
정본은 ``sort_order``(작을수록 앞) 이고, NULL 은 레거시라 ``id ASC`` 폴백이다.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func

__all__ = [
    "SORT_ORDER_MAX",
    "attachment_sort_key",
    "next_attachment_sort_order",
    "parse_attachment_sort_order",
    "sorted_attachments",
]

SORT_ORDER_MAX = 9999
_NULL_SORT_SENTINEL = 10 ** 9


def _attachment_id(attachment: Any) -> int:
    """첨부 id 를 int 로 읽는다(없거나 비정상이면 0)."""
    try:
        return int(getattr(attachment, "id", 0) or 0)
    except (TypeError, ValueError):
        return 0


def attachment_sort_key(attachment: Any) -> tuple[int, int]:
    """오름차순 정렬 키: ``(sort_order ASC NULLS LAST, id ASC)``.

    Args:
        attachment: ``sort_order`` / ``id`` 속성을 가진 객체.

    Returns:
        비교 가능한 튜플. NULL·비정상 ``sort_order`` 는 숫자보다 뒤로 간다.
    """
    raw = getattr(attachment, "sort_order", None)
    if raw is None or raw == "":
        order_part = _NULL_SORT_SENTINEL
    else:
        try:
            order_part = int(raw)
        except (TypeError, ValueError):
            order_part = _NULL_SORT_SENTINEL
    return (order_part, _attachment_id(attachment))


def sorted_attachments(items: list[Any]) -> list[Any]:
    """첨부 리스트를 표시·전송 기본 순서로 복사 정렬한다."""
    return sorted(list(items or []), key=attachment_sort_key)


def parse_attachment_sort_order(raw: Any) -> tuple[bool, int | None, str | None]:
    """요청의 ``sort_order`` 를 검증한다.

    Args:
        raw: form/JSON 원값. 없음·빈 값·null 은 서버가 다음 번호를 부여하도록 None.

    Returns:
        ``(ok, value|None, 오류문구|None)``.
    """
    if raw is None:
        return True, None, None
    if isinstance(raw, bool):
        return False, None, "sort_order 는 0 이상 정수여야 합니다."
    if isinstance(raw, int):
        value = raw
    else:
        text = str(raw).strip().lower()
        if text in ("", "null", "none"):
            return True, None, None
        try:
            value = int(text)
        except (TypeError, ValueError):
            return False, None, "sort_order 는 0 이상 정수여야 합니다."
    if value < 0 or value > SORT_ORDER_MAX:
        return False, None, f"sort_order 는 0 이상 {SORT_ORDER_MAX} 이하여야 합니다."
    return True, value, None


def next_attachment_sort_order(db: Any, order_id: int, as_log_id: str | None) -> int:
    """같은 주문·기록 그룹에서 다음에 쓸 ``sort_order``.

    생략된 단건 업로드(클립 1장 등)가 기존 사진 뒤에 붙게 한다. 배치가 0..n-1 을
    명시하면 이 함수는 타지 않는다.

    Args:
        db: 세션.
        order_id: 주문 PK.
        as_log_id: 기록 id. None 이면 미결합 AS 첨부 그룹.

    Returns:
        0(그룹 비어 있음) 또는 max+1 (상한에서 멈춤).
    """
    from models import OrderAttachment

    query = db.query(func.max(OrderAttachment.sort_order)).filter(
        OrderAttachment.order_id == order_id,
        OrderAttachment.category == "as",
    )
    if as_log_id is None:
        query = query.filter(OrderAttachment.as_log_id.is_(None))
    else:
        query = query.filter(OrderAttachment.as_log_id == as_log_id)
    current = query.scalar()
    if current is None:
        return 0
    try:
        return min(int(current) + 1, SORT_ORDER_MAX)
    except (TypeError, ValueError):
        return 0
