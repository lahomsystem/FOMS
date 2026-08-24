"""주문 필드 단위 복원 (RESTORE-GUI-01 T1).

:class:`~models.OrderFieldChange` 원장 행 **하나**를 근거로 그 필드를 이전 값으로 되돌린다.

**왜 이렇게 좁은가**: 임의 ``structured_data`` 경로를 이름으로 받아 되돌리던 generic revert
라우트는 임의 write primitive 라는 이유로 이미 제거됐다(``foms/api/events.py`` 상단 주석).
그 기능을 되살리되 위험은 되살리지 않기 위해, 이 모듈의 입력은 **원장 행 id 하나**다 —
경로도 값도 요청이 정하지 못하고 서버가 기록에서 읽는다.

거부 조건 4개(하나라도 걸리면 쓰지 않는다):

1. ``path_template`` 이 :data:`RESTORABLE_PATHS` 밖 — 파생·연동·PII 축은 값 되쓰기로 다루면
   다른 축과 어긋난다(스펙 §3.4).
2. 원장 값이 **절단**됐다(``…``) — 원장은 120자에서 자른다. 잘린 값을 되쓰면 복원이 곧 훼손이다.
3. 현재 값이 문자열 축이 아니다 — 원장은 정규화 문자열만 담아서 bool/dict/list 는 원형을
   복원할 수 없다(``True`` 와 ``"True"`` 는 다르다).
4. 현재 값이 원장의 ``after_value`` 와 다르다 — 그 변경 이후 누군가 이미 고쳤다는 뜻이라
   덮지 않는다(``tools/ops/data_doctor.py`` 의 skip 규율과 같다).
"""

from __future__ import annotations

import copy
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.orders.order_field_change_writer import ledger_text, record_field_changes
from foms.services.orders.structured_diff import get_path
from models import OrderFieldChange

__all__ = [
    "RESTORABLE_PATHS",
    "RestoreRejected",
    "apply_restore",
    "describe_restorability",
    "plan_restore",
    "write_path",
]

#: 값 되쓰기로 복원해도 다른 축이 어긋나지 않는 경로(v1). 전부 문자열 축이다.
#:
#: 여기서 뺀 것과 이유(스펙 §3.4):
#: ``totals.*``·``payment.*`` = 파생·별도 확인 축, ``parties.*`` = PII,
#: ``site.address_*`` = full/detail 합본 규약, ``notes`` = 장문(대개 절단),
#: ``items.*`` = 인덱스 드리프트, ``workflow.stage`` = 전이 규칙·부수효과,
#: ``flags.urgent``·``shipment.as_pending`` = bool, ``shipment.as_billing`` = dict.
RESTORABLE_PATHS: frozenset[str] = frozenset({
    "schedule.measurement.date",
    "schedule.measurement.time",
    "schedule.construction.date",
    "schedule.construction.time",
    "schedule.as_visit.date",
    "schedule.as_visit.time",
    "flags.urgent_reason",
    "assignments.owner_team",
    "shipment.sales_delivery",
    "shipment.construction_time",
    "shipment.construction_workers",
    "shipment.trip",
})

#: 원장이 절단한 값에 붙이는 표시(``structured_diff._clip``).
TRUNCATION_MARK = "…"


class RestoreRejected(Exception):
    """이 원장 행은 안전하게 되돌릴 수 없다.

    Attributes:
        message: 사용자 표시 메시지.
        status_code: HTTP 상태(경로/값 문제는 400, 후속 변경 충돌은 409).
    """

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _is_truncated(value: str | None) -> bool:
    """원장 값이 절단됐는지 판정한다."""
    return isinstance(value, str) and value.endswith(TRUNCATION_MARK)


def write_path(sd: dict[str, Any], path: str, value: str | None) -> None:
    """점 경로에 문자열 값을 쓴다(중간 dict 는 만들어 준다).

    ``value`` 가 ``None`` 이면 빈 문자열을 쓴다 — 키를 지우지 않는 것은 diff 가 ``None``·``''``·
    키 부재를 같은 빈값으로 보기 때문이고, 모양을 흔들지 않는 쪽이 안전하기 때문이다.

    :param sd: 수정할 ``structured_data`` 사본.
    :param path: 점 경로.
    :param value: 쓸 문자열(빈값이면 ``None``).
    """
    parts = path.split(".")
    node: Any = sd
    for part in parts[:-1]:
        nxt = node.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            node[part] = nxt
        node = nxt
    node[parts[-1]] = "" if value is None else value


def plan_restore(row: OrderFieldChange, sd: dict[str, Any]) -> dict[str, Any]:
    """원장 행 하나에 대한 복원안을 만든다(쓰지 않는다 — 판정만).

    :param row: 되돌릴 원장 행.
    :param sd: 대상 주문의 현재 ``structured_data``.
    :return: ``{'path', 'before', 'after', 'current'}``.
    :raises RestoreRejected: 거부 조건 4개 중 하나라도 걸렸을 때.
    """
    path = row.path or ""
    if (row.path_template or path) not in RESTORABLE_PATHS:
        raise RestoreRejected("이 항목은 되돌리기를 지원하지 않습니다.", 400)
    if _is_truncated(row.before_value) or _is_truncated(row.after_value):
        raise RestoreRejected("기록된 값이 잘려 있어 되돌릴 수 없습니다.", 400)

    current = get_path(sd, path)
    if current is not None and not isinstance(current, str):
        raise RestoreRejected("문자열 항목만 되돌릴 수 있습니다.", 400)

    current_text = ledger_text(current, path)
    if current_text != row.after_value:
        raise RestoreRejected(
            "이 변경 이후 값이 또 바뀌어 되돌릴 수 없습니다. 최신 이력에서 다시 시도하세요.",
            409,
        )
    if current_text == row.before_value:
        raise RestoreRejected("이미 그 값입니다.", 409)

    return {
        "path": path,
        "before": row.before_value,
        "after": row.after_value,
        "current": current_text,
    }


def describe_restorability(row: OrderFieldChange, sd: dict[str, Any]) -> dict[str, Any]:
    """화면이 버튼을 켤지 끌지 판단할 정보를 만든다(예외를 던지지 않는다).

    :param row: 원장 행.
    :param sd: 현재 ``structured_data``.
    :return: ``{'restorable': bool, 'reason': str | None}``.
    """
    try:
        plan_restore(row, sd)
    except RestoreRejected as rejected:
        return {"restorable": False, "reason": rejected.message}
    return {"restorable": True, "reason": None}


def apply_restore(
    session: Any,
    order: Any,
    row: OrderFieldChange,
    *,
    actor_user_id: int,
    change_set_id: str,
) -> dict[str, Any]:
    """잠긴 주문에 복원을 적용한다(REV-00 mutation 콜백 안에서만 호출한다).

    쓰기가 이 모듈에 있는 이유는 mutation writer 인벤토리가 **파일 단위**로 분류하기
    때문이다 — 라우트 파일(``foms/api/events.py``)에 두면 그 파일의 기존 EXTERNAL 사이트와
    같은 등급으로 묶여 EXTERNAL 이 늘어난다. 정본 mutator 파일에 두고 CANONICAL 로 등재한다.

    lock 획득 뒤 :func:`plan_restore` 를 **다시** 부른다 — 대기 중 다른 트랜잭션이 같은
    필드를 고쳤을 수 있어 요청 시점 판정만 믿으면 lost update 가 된다.

    :param session: mutation 트랜잭션 세션(커밋은 호출자 소유).
    :param order: ``FOR UPDATE`` 로 잠긴 :class:`~models.Order`.
    :param row: 되돌릴 원장 행.
    :param actor_user_id: 행위자 user id.
    :param change_set_id: 이번 복원의 change set id.
    :return: 적용된 복원안(``plan_restore`` 반환값).
    :raises RestoreRejected: lock 뒤 재판정에서 거부됐을 때.
    """
    sd = copy.deepcopy(order.structured_data or {})
    confirmed = plan_restore(row, sd)
    write_path(sd, confirmed["path"], confirmed["before"])
    order.structured_data = sd
    flag_modified(order, "structured_data")
    sync_erp_flat_columns(order, sd)
    # 복원도 변경이다 — 같은 원장에 남겨야 다음 사람이 되짚을 수 있다.
    record_field_changes(
        session,
        [{
            "path": confirmed["path"],
            "before": confirmed["after"],
            "after": confirmed["before"],
            "op": "set" if confirmed["before"] is not None else "clear",
        }],
        order_id=order.id,
        actor_user_id=actor_user_id,
        change_set_id=change_set_id,
    )
    session.flush()
    return confirmed
