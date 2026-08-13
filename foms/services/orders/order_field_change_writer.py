"""주문 필드 변경 원장 쓰기 (ORDER-DIFF-01).

ORDER-DIFF-00 의 :func:`~foms.services.orders.structured_diff.diff_structured` 결과를
:class:`~models.OrderFieldChange` 행으로 편다. **비교를 다시 하지 않는다** — 저장 경로가 이미
만든 diff 를 그대로 받는다(저장은 hot path 라 같은 계산을 두 번 하지 않는다).

화면용 ``security_logs.detail['changes']`` 는 40건 상한을 유지하고, 이 원장에는 **전량**을
남긴다. 상한은 표를 읽기 위한 것이지 기록을 줄이기 위한 것이 아니다.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Iterable, Mapping

from models import OrderFieldChange

logger = logging.getLogger(__name__)

__all__ = ["build_change_rows", "path_template_of", "record_field_changes"]

#: ``items.2.price`` / ``items.2`` 분해용(경로 문법은 structured_diff 가 만든 것과 같다).
_ITEM_PATH_RE = re.compile(r"^items\.(?P<index>\d+)(?:\.(?P<field>[A-Za-z0-9_]+))?$")

#: 컬럼 길이 상한(마이그레이션 ``orderdiff_01`` 과 같은 값). 여기서 잘라 두면 감사 쓰기가
#: 길이 초과로 실패해 **저장 트랜잭션을 죽이는 일**이 없다.
_PATH_LIMIT = 120
_NAME_LIMIT = 120
_UID_LIMIT = 36


def path_template_of(path: str) -> str:
    """품목 인덱스를 지운 질의 키를 만든다.

    ``items.2.price`` → ``items.*.price``. 품목 번호와 무관하게 "단가가 바뀐 것 전부"를
    인덱스 동등 비교로 물을 수 있게 하는 것이 목적이다(원본 경로는 ``path`` 에 남는다).

    :param path: 원본 점 경로.
    :return: 질의용 경로 템플릿(품목이 아니면 원본 그대로).
    """
    match = _ITEM_PATH_RE.match(path or "")
    if not match:
        return path or ""
    field = match.group("field")
    return f"items.*.{field}" if field else "items.*"


def _item_index_of(path: str) -> int | None:
    """품목 경로의 인덱스를 꺼낸다(스칼라 경로면 ``None``).

    :param path: 원본 점 경로.
    :return: 품목 인덱스 또는 ``None``.
    """
    match = _ITEM_PATH_RE.match(path or "")
    return int(match.group("index")) if match else None


def _text(value: Any) -> str | None:
    """원장에 담을 문자열 표현(비어 있으면 ``None``).

    :param value: diff 가 만든 정규 값(문자열·불리언·``None``).
    :return: 문자열 또는 ``None``.
    """
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)


def build_change_rows(
    changes: Iterable[Mapping[str, Any]],
    *,
    order_id: int,
    actor_user_id: int | None,
    change_set_id: str,
) -> list[OrderFieldChange]:
    """변경 dict 목록을 원장 행으로 만든다(DB 접근 없음 — 순수 변환).

    :param changes: ``diff_structured`` 결과의 ``changes`` 목록.
    :param order_id: 대상 주문 id.
    :param actor_user_id: 행위자 user id(없으면 ``None``).
    :param change_set_id: 저장 1회 묶음 id(헤더 ``detail['change_set']`` 과 같은 값).
    :return: 저장 대기 ``OrderFieldChange`` 목록.
    """
    rows: list[OrderFieldChange] = []
    for change in changes:
        if not isinstance(change, Mapping):
            continue
        path = str(change.get("path") or "")[:_PATH_LIMIT]
        if not path:
            continue
        item_name = change.get("item")
        item_uid = change.get("uid")
        rows.append(OrderFieldChange(
            change_set_id=change_set_id,
            order_id=int(order_id),
            path=path,
            path_template=path_template_of(path)[:_PATH_LIMIT],
            item_index=_item_index_of(path),
            # 인덱스는 저장마다 밀리므로, 품목 축 이력의 열쇠는 이 값이다(ORDER-ITEM-UID).
            item_uid=(str(item_uid)[:_UID_LIMIT] if item_uid else None),
            item_name=(str(item_name)[:_NAME_LIMIT] if item_name else None),
            op=str(change.get("op") or "set")[:8],
            before_value=_text(change.get("before")),
            after_value=_text(change.get("after")),
            actor_user_id=actor_user_id,
        ))
    return rows


def record_field_changes(
    session: Any,
    changes: Iterable[Mapping[str, Any]],
    *,
    order_id: int,
    actor_user_id: int | None,
    change_set_id: str,
) -> int:
    """변경 원장 행을 **저장과 같은 트랜잭션에** 싣는다.

    감사 기록 실패가 원 저장을 죽이면 안 되므로 행 생성 단계는 fail-open 이다(실패는 반드시
    로그로 남긴다 — 조용한 무시 금지). 길이 초과 같은 예측 가능한 실패는 애초에 생기지 않도록
    :func:`build_change_rows` 가 컬럼 상한으로 잘라서 만든다.

    :param session: 저장 트랜잭션 세션(호출부가 커밋한다 — 여기서 commit 하지 않는다).
    :param changes: ``diff_structured`` 결과의 ``changes`` 목록(상한 없는 전량).
    :param order_id: 대상 주문 id.
    :param actor_user_id: 행위자 user id.
    :param change_set_id: 저장 1회 묶음 id.
    :return: 실린 행 수(실패 시 0).
    """
    try:
        rows = build_change_rows(
            changes,
            order_id=order_id,
            actor_user_id=actor_user_id,
            change_set_id=change_set_id,
        )
        if not rows:
            return 0
        session.add_all(rows)
        return len(rows)
    except Exception:
        logger.warning(
            "[ORDER-DIFF] 변경 원장 기록 실패: order=%s change_set=%s",
            order_id, change_set_id, exc_info=True,
        )
        return 0
