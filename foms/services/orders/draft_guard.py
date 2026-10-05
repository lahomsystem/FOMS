"""초안 표식 규칙 한 곳 — "``meta.draft`` 가 참인 ERP 주문의 status 는 DRAFT 또는 DELETED 뿐이다".

2026-10-05 숨은 초안 주문(운영 7건)의 원인은 두 갈래였다(``docs/specs/2026-10-05-hidden-draft-
orders-fix_SPEC.md`` §1). 버린 초안을 휴지통에서 복원하면 status 만 RECEIVED 로 바뀌고 표식은
남았고, 단계·상태를 쓰는 길들은 초안인지 보지 않았다. 표식이 참이면 모든 화면 술어
(:meth:`models.Order.active_filter`)가 그 행을 빼므로, 둘 다 "어디에도 안 보이는 주문"을 만든다.

초안이 실제 주문이 되는 길은 명시 저장(승격, ``_finalize_draft_state``) 하나뿐이다. 그 밖의 쓰기가
초안을 만나면 이 모듈의 판정으로 거절한다:

* 단계·상태 쓰기 5길(정본 전이 ``transition_order`` · 단계 강제 변경 · 일반 상태 변경 · 칸 수정의
  ``status`` · 퀘스트 승인) → 409 ``DRAFT_NOT_PROMOTED``. 관리자 뚫기로도 못 뚫는다 — 초안은 업무
  게이트가 아니라 "아직 주문이 아님"이다.
* 휴지통 복원 2길(``/restore_orders`` 일괄 · 모바일 되돌리기) → 초안은 복원하지 않는다(사용자 결정
  (다), 2026-10-05). 휴지통 목록은 그 행을 "작성 중 초안 — 복원 불가"로 보여 준다.
* 감시(읽기만) → :func:`hidden_draft_shape_filter` 를 ``tools/ops/check_draft_flag_invariant.py`` 가 쓴다.

판정은 :func:`foms.services.erp_order_flags.is_erp_order_draft` 하나를 쓴다(화면 술어와 같은 두 갈래).
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import and_, or_

from foms.services.erp_order_flags import (
    is_erp_draft_structured_data,
    is_erp_order_draft,
    is_erp_order_record,
)
from foms.services.orders.revision import RevisionError
from models import Order

DRAFT_NOT_PROMOTED_CODE = "DRAFT_NOT_PROMOTED"
DRAFT_NOT_PROMOTED_MESSAGE = (
    "아직 저장(등록)하지 않은 초안입니다. 먼저 주문을 저장한 뒤 단계를 바꿀 수 있습니다."
)
DRAFT_NOT_RESTORABLE_CODE = "DRAFT_NOT_RESTORABLE"
#: 휴지통 목록 칸·비활성 체크박스 설명에 같은 문구를 쓴다.
DRAFT_NOT_RESTORABLE_LABEL = "작성 중 초안 — 복원 불가"
DRAFT_NOT_RESTORABLE_MESSAGE = (
    "저장(등록)하지 않은 작성 중 초안이라 복원할 수 없습니다. 새 주문으로 다시 입력해 주세요."
)
#: 표식이 참인 행이 가질 수 있는 status 전부(규칙 본문).
DRAFT_FLAG_ALLOWED_STATUSES = ("DRAFT", "DELETED")


class DraftNotPromotedError(RevisionError):
    """잠금 아래 백스톱: 아직 승격하지 않은 초안에 단계·상태를 쓰려 했다(409).

    ``RevisionError`` 를 상속하는 이유: 단계 쓰기 라우트는 모두 이미 ``RevisionError`` 를
    ``(error_code, status_code)`` 로 응답에 옮긴다(``except (TransitionError, RevisionError)`` 또는
    ``except RevisionError``). ``TransitionError`` 를 상속하면 정본 전이 모듈과 이 모듈이 서로를
    import 하게 된다.
    """

    status_code = 409
    error_code = DRAFT_NOT_PROMOTED_CODE

    def __init__(self, order_id: Optional[int] = None):
        super().__init__(DRAFT_NOT_PROMOTED_MESSAGE)
        self.order_id = order_id


def is_unpromoted_draft(order: Any) -> bool:
    """단계·상태 쓰기를 거절할 초안인가(ERP 이고 status DRAFT 또는 표식 참).

    Args:
        order: ``Order`` 또는 같은 속성을 가진 행.

    Returns:
        아직 승격하지 않은 ERP 초안이면 True.
    """
    return is_erp_order_draft(order)


def ensure_order_promoted(order: Any) -> None:
    """초안이면 :class:`DraftNotPromotedError` 를 던진다(잠근 행에 부르는 백스톱).

    Args:
        order: 잠금 아래에서 다시 읽은 ``Order``.

    Raises:
        DraftNotPromotedError: 아직 승격하지 않은 ERP 초안.
    """
    if is_unpromoted_draft(order):
        raise DraftNotPromotedError(getattr(order, "id", None))


def draft_not_promoted_body(order_id: Any) -> dict[str, Any]:
    """라우트가 409 로 돌려줄 JSON 본문(각 라우트의 옛 키 ``message``·``error`` 를 함께 싣는다).

    Args:
        order_id: 거절한 주문 번호.

    Returns:
        ``{'success': False, 'code', 'error', 'message', 'data': {'order_id'}}``.
    """
    return {
        "success": False,
        "code": DRAFT_NOT_PROMOTED_CODE,
        "error": DRAFT_NOT_PROMOTED_MESSAGE,
        "message": DRAFT_NOT_PROMOTED_MESSAGE,
        "data": {"order_id": order_id},
    }


def is_unrestorable_trashed_draft(order: Any) -> bool:
    """휴지통에서 복원하면 안 되는 초안 행인가.

    버리기·정리 크론은 ``status='DELETED'`` 로 덮어 status 갈래가 사라지므로
    ``original_status == 'DRAFT'`` 도 본다(표식 없이 그 값만 남은 옛 행 포함). 이런 행을 복원하면
    status DRAFT(아무도 못 여는 초안) 또는 숨은 모양이 되므로 복원 대상에서 뺀다.

    Args:
        order: ``Order`` 또는 휴지통 표시 행(같은 컬럼 속성).

    Returns:
        ERP 초안(표식 참·status DRAFT·original_status DRAFT 중 하나)이면 True.
    """
    if is_unpromoted_draft(order):
        return True
    if not is_erp_order_record(order):
        return False
    return str(getattr(order, "original_status", "") or "").upper() == "DRAFT"


def violates_draft_flag_rule(order: Any) -> bool:
    """행 하나가 규칙을 어겼는가(표식 참인데 status 가 DRAFT·DELETED 가 아님 = 숨은 모양).

    Args:
        order: ``Order`` 또는 같은 속성을 가진 행.

    Returns:
        숨은 모양이면 True.
    """
    if not is_erp_order_record(order):
        return False
    if not is_erp_draft_structured_data(getattr(order, "structured_data", None)):
        return False
    return str(getattr(order, "status", "") or "") not in DRAFT_FLAG_ALLOWED_STATUSES


def hidden_draft_shape_filter():
    """:func:`violates_draft_flag_rule` 의 SQL 술어(휴지통 행 포함, 읽기 전용 감시용).

    표식 판정은 화면 술어와 같은 번호 목록 서브쿼리(:meth:`Order._meta_draft_order_ids`)라
    부분 인덱스 ``ix_orders_meta_draft_true`` 만 읽는다.

    Returns:
        SQLAlchemy 조건식.
    """
    return and_(
        Order.is_erp_order.is_(True),
        or_(Order.status.is_(None), Order.status.notin_(DRAFT_FLAG_ALLOWED_STATUSES)),
        Order.id.in_(Order._meta_draft_order_ids()),
    )


__all__ = [
    "DRAFT_FLAG_ALLOWED_STATUSES",
    "DRAFT_NOT_PROMOTED_CODE",
    "DRAFT_NOT_PROMOTED_MESSAGE",
    "DRAFT_NOT_RESTORABLE_CODE",
    "DRAFT_NOT_RESTORABLE_LABEL",
    "DRAFT_NOT_RESTORABLE_MESSAGE",
    "DraftNotPromotedError",
    "draft_not_promoted_body",
    "ensure_order_promoted",
    "hidden_draft_shape_filter",
    "is_unpromoted_draft",
    "is_unrestorable_trashed_draft",
    "violates_draft_flag_rule",
]
