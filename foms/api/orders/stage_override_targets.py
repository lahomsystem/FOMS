"""강제 단계 변경의 확장 목표 실행기 — AS 3종·삭제·완료 (ADMIN-OVERRIDE-01).

메인 8단계는 기존 :func:`~foms.services.orders.stage_override.apply_stage_override` 가
``execute_order_mutation`` 안에서 처리한다. 이 모듈이 맡는 세 목표는 **각자 자기
mutation 을 소유한 서비스**를 타므로 ``execute_order_mutation`` 으로 **감싸지 않는다** —
감싸면 mutation 이 이중으로 걸려 version 이 두 번 오르고 receipt 가 두 벌 생긴다.

* AS 3종 → :mod:`foms.services.orders.as_cycle_service` 명령(raw stage 쓰기 금지,
  본공정 ``workflow.stage`` 는 건드리지 않는다).
* ``DELETED`` → :func:`foms.services.orders.trash_mirror.soft_delete_with_trash_mirror`
  (휴지통 미러·감사·캐시 무효화까지가 한 계약).
* ``COMPLETED`` → :func:`foms.services.orders.cs_complete_service.complete_order_as_cs`
  (완료는 한 길만 — 상태만 COMPLETED 이고 뒤가 빈 주문을 만들지 않는다).

권한 축만 푼다. If-Match·잠금 재확인·``to_values``·동일 상태·삭제된 주문은 그대로다.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from typing import Any, Callable, Mapping, Optional

from flask import jsonify

from foms.services.orders.admin_override import (
    GATE_OVERRIDE_TARGET,
    record_admin_override_event,
)
from foms.services.orders.as_cycle_service import (
    AS_COMPLETED,
    AS_IN_PROGRESS,
    AS_RECEIVED,
    ASCycleError,
    complete_as_cycle,
    register_as_cycle,
    reopen_as_cycle,
    start_as_cycle,
)
from foms.services.error_logging import log_handled_exception
from foms.services.orders.cs_complete_service import complete_order_as_cs
from foms.services.orders.revision import RevisionError
from foms.services.orders.stage_override import (
    AS_TARGET_TO_AXIS,
    MAIN_PIPELINE_CODES,
    as_overlay_status,
    classify_stage_move,
    current_stage_for_order,
    normalize_override_target,
)
from foms.services.orders.state_axes import read_as_status, read_deleted, read_main_stage
from foms.services.orders.trash_mirror import soft_delete_with_trash_mirror

#: 목표 갈래.
KIND_MAIN = "MAIN"
KIND_AS = "AS"
KIND_DELETE = "DELETE"

OVERRIDE_TARGET_MESSAGE = (
    "AS·삭제로 강제 변경하려면 관리자 권한과 사유가 필요합니다."
)
BAD_TARGET_MESSAGE = (
    "메인 파이프라인 단계만 강제 변경할 수 있습니다. (AS·삭제는 관리자 권한이 필요합니다.)"
)
AS_NO_PATH_MESSAGE = (
    "진행 중인 AS 는 접수로 되돌릴 수 없습니다. AS 를 완료한 뒤 다시 접수하세요."
)
IF_MATCH_UNSUPPORTED_MESSAGE = (
    "AS 목표는 아직 If-Match 를 지킬 수 없습니다. If-Match 없이 다시 보내세요."
)
CS_COMPLETE_ADMIN_HINT = "강제 완료는 관리자 권한이 필요합니다."


class OverrideTargetError(Exception):
    """확장 목표 실행이 계약상 거부된 경우(HTTP 상태·코드를 함께 들고 다닌다)."""

    def __init__(self, message: str, *, status: int = 400, code: str = "OVERRIDE_TARGET"):
        super().__init__(message)
        self.status = status
        self.code = code

    def response(self):
        """라우트가 그대로 돌려줄 ``(json, status)``."""
        text = str(self)
        return (
            jsonify({"success": False, "code": self.code, "message": text, "error": text}),
            self.status,
        )


def classify_override_target(raw: Any) -> tuple[Optional[str], Optional[str]]:
    """``to_stage`` 를 (목표 코드, 갈래) 로 분류한다.

    Args:
        raw: 요청의 ``to_stage`` 원값.

    Returns:
        (코드, ``MAIN``/``AS``/``DELETE``). 알 수 없는 목표면 ``(None, None)``.
    """
    code = normalize_override_target(raw)
    if code is None:
        return None, None
    if code in MAIN_PIPELINE_CODES:
        return code, KIND_MAIN
    if code in AS_TARGET_TO_AXIS:
        return code, KIND_AS
    return code, KIND_DELETE


def as_axis_same(order: Any, to_code: Any) -> bool:
    """AS 목표가 지금 AS 축 값과 같은지 판정한다(동일 상태 = 400).

    메인 stage 기준 ``classify_stage_move`` 로 재면 stage 가 MEASURE 인 AS 접수 건이
    "동일 아님"이 되어 새 cycle 을 또 연다 — AS 목표의 동일 판정은 AS 축으로 한다.

    (services 계층이 ``state_axes`` 를 함수 안에서 늦게 부르지 않도록 이 계층에 둔다.)

    Args:
        order: 대상 주문.
        to_code: 목표 코드(``AS_RECEIVED``/``AS``/``AS_COMPLETED``).

    Returns:
        지금 AS 축 값과 목표가 같으면 True. AS 목표가 아니면 False.
    """
    wanted = AS_TARGET_TO_AXIS.get(str(to_code or "").strip().upper())
    if not wanted:
        return False
    return read_as_status(order) == wanted


def _body_hash(data: Mapping[str, Any]) -> str:
    """요청 본문의 sha256 hex(receipt 의 request_hash)."""
    canonical = json.dumps(dict(data or {}), sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _as_scope_hash(order_id: int, to_code: str) -> str:
    """AS 강제 변경 receipt 의 scope 해시."""
    return hashlib.sha256(
        f"ADMIN_OVERRIDE_AS:{order_id}:{to_code}".encode("utf-8")
    ).hexdigest()


def _as_commands_accept_expected_version() -> bool:
    """AS 명령 4종이 ``expected_version`` 을 받는지(가산 수정 반영 여부) 확인한다.

    아직 받지 않는 동안에는 If-Match 를 조용히 버리지 않고 명시 거부한다.
    """
    return all(
        "expected_version" in inspect.signature(fn).parameters
        for fn in (register_as_cycle, start_as_cycle, complete_as_cycle, reopen_as_cycle)
    )


def _as_plan(current: str, to_code: str, reason: str, from_stage: str) -> list[tuple[Callable, dict]]:
    """현재 AS 축 상태에서 목표까지 가는 명령 1~2개를 고른다(계약 C2 표).

    Args:
        current: 지금 AS 축 값(``NONE``/``RECEIVED``/``IN_PROGRESS``/``COMPLETED``).
        to_code: 목표 코드(``AS_RECEIVED``/``AS``/``AS_COMPLETED``).
        reason: 관리자 사유(명령 인자로 그대로 들어간다).
        from_stage: 지금 본공정 단계(설명문에만 쓴다).

    Returns:
        ``[(함수, kwargs), ...]`` 순차 실행 계획.

    Raises:
        OverrideTargetError: 동일 상태(400) 또는 모델에 길이 없는 전이(409 ``AS_NO_PATH``).
    """
    register = (register_as_cycle, {"as_content": f"[관리자 강제 단계 변경] {reason}"})
    start = (
        start_as_cycle,
        {"reason": reason, "description": f"관리자 강제 단계 변경({from_stage or '-'}→AS)"},
    )
    complete_any = (complete_as_cycle, {"note": reason, "allow_from": (AS_RECEIVED, AS_IN_PROGRESS)})
    complete = (complete_as_cycle, {"note": reason})
    reopen = (reopen_as_cycle, {"reason": reason})

    if AS_TARGET_TO_AXIS.get(to_code) == current:
        raise OverrideTargetError("현재와 동일한 AS 상태로는 변경할 수 없습니다.", status=400)

    if to_code == "AS_RECEIVED":
        if current == "NONE":
            return [register]
        if current == AS_COMPLETED:
            return [reopen]
        # IN_PROGRESS → 접수 되돌리기는 AS 상태기계에 명령이 없다(권한 문제가 아니다).
        raise OverrideTargetError(AS_NO_PATH_MESSAGE, status=409, code="AS_NO_PATH")
    if to_code == "AS":
        if current == "NONE":
            return [register, start]
        if current == AS_RECEIVED:
            return [start]
        return [reopen, start]
    # AS_COMPLETED
    if current == "NONE":
        return [register, complete_any]
    if current == AS_RECEIVED:
        return [complete_any]
    return [complete]


def apply_as_target(
    db: Any,
    order: Any,
    *,
    to_code: str,
    override: Any,
    expected_version: Optional[int],
    data: Mapping[str, Any],
) -> dict[str, Any]:
    """AS 3종 목표를 AS cycle 명령으로 실행한다(커밋은 호출부 소유).

    Args:
        db: 활성 DB 세션.
        order: 대상 주문.
        to_code: 목표 코드.
        override: 성립한 :class:`~foms.services.orders.admin_override.AdminOverride`.
        expected_version: If-Match ``mutation_version``(없으면 None).
        data: 요청 본문(receipt request_hash 재료).

    Returns:
        ``{"from", "to", "axis"}`` 변경 요약.

    Raises:
        OverrideTargetError: 동일 상태·경로 없음·If-Match 미지원.
        ASCycleError·RevisionError: 서비스 계약 위반(호출부가 매핑·롤백).
    """
    supports_version = _as_commands_accept_expected_version()
    if expected_version is not None and not supports_version:
        raise OverrideTargetError(
            IF_MATCH_UNSUPPORTED_MESSAGE, status=409, code="IF_MATCH_UNSUPPORTED_TARGET"
        )
    order_id = int(order.id)
    current = read_as_status(order)
    plan = _as_plan(current, to_code, override.reason, read_main_stage(order) or "")
    scope_hash = _as_scope_hash(order_id, to_code)
    request_hash = _body_hash(data)
    for index, (func, kwargs) in enumerate(plan):
        extra = {}
        if supports_version and index == 0 and expected_version is not None:
            extra["expected_version"] = expected_version
        func(
            db,
            order_id=order_id,
            actor_user_id=override.actor_id,
            scope_hash=scope_hash,
            request_hash=request_hash,
            **kwargs,
            **extra,
        )
    return {"from": current, "to": to_code, "axis": KIND_AS}


def apply_delete_target(
    db: Any,
    order: Any,
    *,
    override: Any,
    expected_version: Optional[int],
    bulk: bool = False,
    audit_sink: Optional[Callable[..., Any]] = None,
) -> dict[str, Any]:
    """``DELETED`` 목표를 휴지통 미러까지 포함해 실행한다(커밋은 호출부 소유).

    이미 삭제된 주문은 뚫지 않는다(404). ``RevisionError`` 는 그대로 올려 보내
    호출부가 전체 롤백을 결정한다.

    ``audit_sink`` 는 ``foms.web.auth.log_access`` 다 — api 층이 web 을 import 하면
    레이어 금지 방향(api→web)에 새 엣지가 생기므로, 라우트가 주입해 내려 준다.
    ``None`` 이면 접근 로그만 비고 canonical ``ORDER_SOFT_DELETED`` 이벤트는 남는다.
    """
    if read_deleted(order) != "NONE":
        raise OverrideTargetError("주문을 찾을 수 없습니다.", status=404, code="NOT_FOUND")
    before = read_main_stage(order) or str(getattr(order, "status", "") or "")
    soft_delete_with_trash_mirror(
        db,
        order_id=int(order.id),
        actor_user_id=override.actor_id,
        reason=override.reason,
        expected_version=expected_version,
        bulk=bulk,
        audit_sink=audit_sink,
    )
    return {"from": before, "to": "DELETED", "axis": KIND_DELETE}


def run_extended_target(
    db: Any,
    order: Any,
    *,
    kind: str,
    to_code: str,
    override: Any,
    expected_version: Optional[int],
    data: Mapping[str, Any],
    route: str,
    bulk: bool = False,
    audit_sink: Optional[Callable[..., Any]] = None,
) -> dict[str, Any]:
    """AS/삭제 목표 1건을 실행하고 ``ADMIN_OVERRIDE_USED`` 이벤트까지 남긴다.

    Returns:
        ``{"order_id", "from", "to", "axis"}``.
    """
    if kind == KIND_AS:
        summary = apply_as_target(
            db, order, to_code=to_code, override=override,
            expected_version=expected_version, data=data,
        )
    else:
        summary = apply_delete_target(
            db, order, override=override, expected_version=expected_version, bulk=bulk,
            audit_sink=audit_sink,
        )
    record_admin_override_event(
        db,
        order,
        override=override,
        gates=[GATE_OVERRIDE_TARGET],
        route=route,
        axis=summary["axis"],
        from_value=summary["from"],
        to_value=summary["to"],
        bulk=bulk,
    )
    return {"order_id": int(order.id), **summary}


def complete_via_cs(
    db: Any,
    order: Any,
    *,
    user: Any,
    user_id: Any,
    data: Mapping[str, Any],
    override: Any,
    expected_version: Optional[int],
    route: str,
    bulk: bool = False,
) -> tuple[Optional[dict[str, Any]], Optional[tuple]]:
    """``COMPLETED`` 목표를 CS 완료 서비스로 보낸다(완료는 한 길만).

    ``admin_override`` 가 없으면 CS 게이트가 그대로 걸리고, 그 거부 문구 끝에
    "강제 완료는 관리자 권한이 필요합니다." 를 붙여 무엇이 필요한지 알려 준다.

    Returns:
        (성공 요약, 실패 응답) — 한쪽은 항상 None.
    """
    punched: list = []
    from_stage = read_main_stage(order) or str(getattr(order, "status", "") or "")
    failed = complete_order_as_cs(
        db,
        order,
        actor_user=user,
        actor_user_id=user_id,
        body=dict(data or {}),
        idempotency_key=None,
        override=override,
        punched=punched,
        expected_version=expected_version,
    )
    if failed is not None:
        return None, _with_admin_hint(failed) if override is None else failed
    if override is not None and punched:
        record_admin_override_event(
            db, order, override=override, gates=punched, route=route,
            axis="MAIN", from_value=from_stage, to_value="COMPLETED", bulk=bulk,
        )
    return (
        {"order_id": int(order.id), "from": from_stage, "to": "COMPLETED", "axis": "MAIN",
         "punched": punched},
        None,
    )


def split_override_targets(
    orders: list, to_code: str, kind: str, *, include_as: bool = False
) -> tuple[list, list[int], list]:
    """일괄 요청에서 **이미 그 상태인 주문**과 AS overlay 제외분을 걸러낸다.

    동일 상태 판정은 **목표 축으로** 한다 — AS 목표는 AS 축(:func:`as_axis_same`), 삭제
    목표는 delete 축, 메인 목표는 기존 ``classify_stage_move``. 메인 축으로만 재면 stage 가
    MEASURE 인 AS 접수 건이 "동일 아님"이 되어 새 cycle 을 또 연다.

    AS overlay 제외 가드(2026-08-14 사고)는 **메인·삭제 목표에서만** 성립한다 — 제외 근거가
    "AS 표시가 사라진다" 인데 AS 목표는 AS 축 자체를 다루므로 그 사고가 성립하지 않는다.
    그래서 AS 목표면 ``include_as`` 와 무관하게 AS overlay 주문도 항상 포함한다.

    Args:
        orders: 요청 순서대로 정렬된 대상 주문 목록.
        to_code: 정규화된 목표 코드.
        kind: 목표 갈래(``MAIN``/``AS``/``DELETE``).
        include_as: 메인·삭제 목표에서 AS overlay 주문을 명시 포함할지 여부.

    Returns:
        (변경 대상, 동일 상태로 건너뛴 id, AS 로 제외한 ``{order_id, status}`` 목록).
    """
    change: list = []
    skipped: list[int] = []
    skipped_as: list[dict[str, Any]] = []
    for order in orders:
        if kind == KIND_AS:
            same = as_axis_same(order, to_code)
        elif kind == KIND_DELETE:
            same = read_deleted(order) != "NONE"
        else:
            same = classify_stage_move(current_stage_for_order(order), to_code) == "same"
        if same:
            skipped.append(int(order.id))
            continue
        overlay = as_overlay_status(order)
        if overlay and not include_as and kind != KIND_AS:
            skipped_as.append({"order_id": int(order.id), "status": overlay})
            continue
        change.append(order)
    return change, skipped, skipped_as


def map_target_exception(exc: Exception) -> Optional[tuple]:
    """확장 목표 실행에서 나온 예외를 라우트 응답으로 매핑한다.

    AS 명령 계약 위반은 400, REV-00 위반(If-Match 불일치·미존재)은 예외가 들고 있는
    상태 코드 그대로다 — 정합 축은 관리자도 뚫지 못한다.

    Returns:
        ``(json, status)``. 우리가 아는 예외가 아니면 None(호출부가 다시 올린다).
    """
    if isinstance(exc, OverrideTargetError):
        return exc.response()
    if isinstance(exc, ASCycleError):
        text = str(exc)
        return (
            jsonify({"success": False, "code": "AS_COMMAND_REJECTED",
                     "message": text, "error": text}),
            400,
        )
    if isinstance(exc, RevisionError):
        text = str(exc)
        return (
            jsonify({"success": False, "code": exc.error_code,
                     "message": text, "error": text}),
            exc.status_code,
        )
    return None


def _with_admin_hint(failed: tuple) -> tuple:
    """CS 완료 거부 응답의 문구 끝에 관리자 권한 안내를 덧붙인다(상태 코드 불변)."""
    response, status = failed[0], failed[1]
    try:
        body = dict(response.get_json() or {})
    except Exception:  # pragma: no cover - jsonify 응답이 아닌 경우
        log_handled_exception("stage_override 완료 거부 문구 보강")
        return failed
    text = str(body.get("message") or body.get("error") or "").strip()
    joined = f"{text} {CS_COMPLETE_ADMIN_HINT}".strip()
    body["message"] = joined
    body["error"] = joined
    return jsonify(body), status


__all__ = [
    "AS_NO_PATH_MESSAGE",
    "BAD_TARGET_MESSAGE",
    "CS_COMPLETE_ADMIN_HINT",
    "IF_MATCH_UNSUPPORTED_MESSAGE",
    "KIND_AS",
    "KIND_DELETE",
    "KIND_MAIN",
    "OVERRIDE_TARGET_MESSAGE",
    "OverrideTargetError",
    "apply_as_target",
    "as_axis_same",
    "apply_delete_target",
    "classify_override_target",
    "complete_via_cs",
    "map_target_exception",
    "run_extended_target",
    "split_override_targets",
]
