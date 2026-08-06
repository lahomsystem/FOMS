"""ATTACH-LIFE-01(T4): 삭제된 첨부의 **전역 기본 제외** 필터.

:class:`~models.OrderAttachment` 는 hard delete 대신 tombstone(``deleted_at``)으로 삭제된다.
첨부를 읽는 코드는 저장소 전역에 84 파일·428 회 흩어져 있어 **호출부마다 수동 필터를 넣는
설계는 성립하지 않는다**(한 곳만 빠져도 유령 첨부가 노출된다). 그래서 이 모듈이 ORM
:class:`~sqlalchemy.orm.Session` 의 ``do_orm_execute`` 이벤트에서
:func:`~sqlalchemy.orm.with_loader_criteria` 로 ``deleted_at IS NULL`` 을 **모든 ORM SELECT
에 기본 주입**한다 — 기존 84 파일은 단 한 줄도 고치지 않는다.

계약(경계를 정확히 읽을 것):

* **적용 대상 = ORM SELECT 뿐이다.** ``INSERT/UPDATE/DELETE`` 와 column refresh
  (``session.refresh``)·relationship lazy load 는 건드리지 않는다. tombstone 을 세우는 쓰기
  자체와 ``user_deletion`` 의 bulk ``UPDATE`` 가 삭제 행을 계속 볼 수 있어야 하기 때문이다.
* **Session 밖 Core/raw SQL 은 필터가 걸리지 않는다(의도).** purge 스크립트
  (``foms/services/orders/delete_retention.py``)와 SIDEFX outbox worker 는 삭제 행 **전량**을
  봐야 정상 동작한다. 반대로 카운트 목적의 raw SQL 은 스스로 ``AND deleted_at IS NULL`` 을
  들고 있어야 하며, 새 우회가 생기지 않도록 계약 테스트
  (``tests/domains/test_attachment_lifecycle.py``)가 raw ``FROM order_attachments`` 사용처를
  allowlist 로 고정한다.
* **opt-in 해제**: 휴지통/복구처럼 삭제 행을 봐야 하는 소수 경로는
  ``query.execution_options(**{INCLUDE_DELETED_OPTION: True})`` 로 필터를 끈다
  (:func:`include_deleted`).

등록은 :func:`register_attachment_visibility_listener` 로 프로세스당 1회(멱등)이며,
``foms.services.app_init.run_auto_init`` 의 listener 슬롯(date_sync·payment_sync 옆)에서
호출된다 — 순수 wiring 이며 DB 를 건드리지 않는다.
"""
from __future__ import annotations

from typing import Any

__all__ = [
    "INCLUDE_DELETED_OPTION",
    "include_deleted",
    "register_attachment_visibility_listener",
]

#: 전역 필터를 끄는 execution option 키(휴지통/복구 전용 opt-out).
INCLUDE_DELETED_OPTION = "include_deleted_attachments"

_LISTENER_REGISTERED = False


def include_deleted(query: Any) -> Any:
    """삭제된 첨부까지 보이도록 전역 필터를 끈 query/statement 를 돌려준다.

    Args:
        query: :class:`~sqlalchemy.orm.Query` 또는 Core/ORM statement
            (``execution_options`` 를 가진 객체면 무엇이든).

    Returns:
        ``include_deleted_attachments=True`` execution option 이 붙은 새 query/statement.
    """
    return query.execution_options(**{INCLUDE_DELETED_OPTION: True})


def register_attachment_visibility_listener() -> None:
    """전역 ``Session`` 에 삭제 첨부 제외 필터를 **1회** 등록한다(멱등).

    ``do_orm_execute`` 에서 ORM SELECT 에만 ``with_loader_criteria(OrderAttachment,
    deleted_at IS NULL, include_aliases=True)`` 를 주입한다. column refresh·relationship
    lazy load 는 제외한다(이중 적용·refresh 파괴 방지), 쓰기(UPDATE/DELETE)도 제외한다
    (tombstone 쓰기와 user 삭제 detach 가 삭제 행을 계속 봐야 한다).

    Returns:
        None.
    """
    global _LISTENER_REGISTERED
    if _LISTENER_REGISTERED:
        return
    _LISTENER_REGISTERED = True

    from sqlalchemy import event
    from sqlalchemy.orm import Session, with_loader_criteria

    from models import OrderAttachment

    @event.listens_for(Session, "do_orm_execute")
    def _exclude_deleted_attachments(execute_state) -> None:
        if not execute_state.is_select:
            return
        if execute_state.is_column_load or execute_state.is_relationship_load:
            return
        if execute_state.execution_options.get(INCLUDE_DELETED_OPTION):
            return
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(
                OrderAttachment,
                lambda cls: cls.deleted_at.is_(None),
                include_aliases=True,
            )
        )
