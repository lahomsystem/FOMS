"""강제 단계 변경 확장 목표의 HTTP 응답 조립 — AS·삭제·완료 (ADMIN-OVERRIDE-01).

실행기는 :mod:`foms.api.orders.stage_override_targets` 가, transaction 경계(커밋·롤백)와
응답 모양은 이 모듈이 소유한다. 라우트는 분류 결과를 넘겨 주기만 한다.

한 건이라도 실패하면 **전체 롤백**이다(부분 반영 0). 삭제 목표의 대시보드 캐시 무효화는
커밋 뒤 1회만 돈다.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Mapping, Optional

from flask import jsonify

from foms.api.orders.stage_override_targets import (
    KIND_DELETE,
    KIND_MAIN,
    OVERRIDE_TARGET_MESSAGE,
    OverrideTargetError,
    complete_via_cs,
    map_target_exception,
    run_extended_target,
)
from foms.services.orders.admin_override import GATE_OVERRIDE_TARGET
from foms.services.orders.stage_override import (
    AS_OVERLAY_BLOCK_MESSAGE,
    classify_stage_move,
    current_stage_for_order,
)
from foms.services.orders.trash_mirror import invalidate_trash_caches

logger = logging.getLogger(__name__)


def parse_if_match(raw: Optional[str]) -> tuple[Optional[int], bool]:
    """If-Match 헤더를 mutation_version(int) 로 파싱한다.

    Args:
        raw: ``If-Match`` 헤더 원문(따옴표 포함 가능) 또는 None.

    Returns:
        (version, ok) — 헤더가 없으면 (None, True), 형식 오류면 (None, False).
    """
    cleaned = (raw or "").strip().strip('"')
    if not cleaned:
        return None, True
    try:
        return int(cleaned), True
    except ValueError:
        return None, False


#: 빈 사유 거부 문구 — 메인 경로(:func:`foms.services.orders.stage_override.apply_stage_override`)와
#: 같은 글자·같은 상태코드를 쓴다. 화면이 두 경로를 구분하지 못하게 하면 안 된다.
REASON_REQUIRED_MESSAGE = "사유를 입력하세요."

#: 동일 단계 거부 문구 — 일괄 :func:`split_override_targets` 와 같은 술어·같은 글자.
SAME_STAGE_MESSAGE = "현재와 동일한 단계로는 변경할 수 없습니다."


def _plain_reject(message: str):
    """메인 경로와 같은 모양의 400 거부 — ``code`` 를 싣지 않아 화면이 재시도하지 않는다."""
    return jsonify({"success": False, "error": message, "message": message}), 400


def reason_missing_response(data: Mapping[str, Any]):
    """확장 목표 요청의 빈 사유를 **가장 먼저** 거른다(뚫기 여부와 무관).

    AS·삭제 목표는 ``admin_override`` 가 필수라 사유가 이미 보장되지만, ``COMPLETED``
    목표는 뚫기 없이도 들어올 수 있어 사유 검사가 비어 있었다. 검사를 한 자리에 둔다.

    Returns:
        사유가 비면 ``(json, 400)``, 아니면 None.
    """
    if not str(data.get("reason") or "").strip():
        return _plain_reject(REASON_REQUIRED_MESSAGE)
    return None


def _extended_single_payload(summary: dict[str, Any], *, kind: str, order: Any, reason: str) -> dict[str, Any]:
    """확장 목표 성공 응답의 ``data`` 블록(메인 경로 응답과 같은 키를 쓴다)."""
    mode = (
        classify_stage_move(summary["from"], summary["to"])
        if kind == KIND_MAIN
        else "admin_override"
    )
    return {
        "order_id": summary["order_id"],
        "from": summary["from"],
        "to": summary["to"],
        "mode": mode,
        "reason": reason,
        "status": str(getattr(order, "status", "") or ""),
        "mutation_version": getattr(order, "mutation_version", None),
        "mutation_receipt": None,
        "as_overlay_cleared": None,
    }


def extended_single_response(
    db: Any,
    order: Any,
    *,
    kind: str,
    to_code: str,
    override: Any,
    expected_version: Optional[int],
    data: Mapping[str, Any],
    user: Any,
    user_id: Any,
    route: str = "orders.stage_override",
    audit_sink: Optional[Callable[..., Any]] = None,
):
    """확장 목표(AS·삭제·완료) 단건 요청을 끝까지 처리해 응답을 만든다(커밋 포함).

    ``audit_sink`` 는 라우트가 주입하는 ``foms.web.auth.log_access`` 다(삭제 목표 접근 로그).
    """
    blocked = reason_missing_response(data)
    if blocked is not None:
        return blocked
    if to_code == "COMPLETED":
        # 동일 단계는 정합 축이다 — 뚫기로도 통과하지 않는다(일괄과 같은 술어).
        if classify_stage_move(current_stage_for_order(order), "COMPLETED") == "same":
            return _plain_reject(SAME_STAGE_MESSAGE)
        summary, failed = complete_via_cs(
            db, order, user=user, user_id=user_id, data=data, override=override,
            expected_version=expected_version, route=route,
        )
        if failed is not None:
            return failed
    elif override is None:
        return OverrideTargetError(
            OVERRIDE_TARGET_MESSAGE, status=400, code=GATE_OVERRIDE_TARGET
        ).response()
    else:
        try:
            summary = run_extended_target(
                db, order, kind=kind, to_code=to_code, override=override,
                expected_version=expected_version, data=data, route=route,
                audit_sink=audit_sink,
            )
        except Exception as exc:
            db.rollback()
            mapped = map_target_exception(exc)
            if mapped is None:
                raise
            # 계약 위반(동일 상태·경로 없음·REV 충돌)은 사용자 응답으로 바꾸되 스택은 남긴다.
            logger.warning(
                "확장 목표 강제 변경 거부: order=%s to=%s", getattr(order, "id", None),
                to_code, exc_info=True,
            )
            return mapped
    db.commit()
    if kind == KIND_DELETE:
        invalidate_trash_caches("stage_override_delete")
    reason = override.reason if override is not None else str(data.get("reason") or "").strip()
    return jsonify({
        "success": True,
        "data": _extended_single_payload(summary, kind=kind, order=order, reason=reason),
    })


def extended_bulk_response(
    db: Any,
    orders: list,
    *,
    kind: str,
    to_code: str,
    override: Any,
    data: Mapping[str, Any],
    user: Any,
    user_id: Any,
    skipped_same: list[int],
    not_found: list[int],
    skipped_as: Optional[list] = None,
    route: str = "orders.bulk_stage_override",
    audit_sink: Optional[Callable[..., Any]] = None,
):
    """확장 목표 일괄 요청을 처리한다 — 한 건이라도 실패하면 전체 롤백(부분 반영 0).

    ``audit_sink`` 는 라우트가 주입하는 ``foms.web.auth.log_access`` 다(삭제 목표 접근 로그).
    """
    blocked = reason_missing_response(data)
    if blocked is not None:
        return blocked
    if to_code != "COMPLETED" and override is None:
        return OverrideTargetError(
            OVERRIDE_TARGET_MESSAGE, status=400, code=GATE_OVERRIDE_TARGET
        ).response()
    results: list[dict[str, Any]] = []
    for order in orders:
        if to_code == "COMPLETED":
            summary, failed = complete_via_cs(
                db, order, user=user, user_id=user_id, data=data, override=override,
                expected_version=None, route=route, bulk=True,
            )
            if failed is not None:
                db.rollback()
                return failed
        else:
            try:
                summary = run_extended_target(
                    db, order, kind=kind, to_code=to_code, override=override,
                    expected_version=None, data=data, route=route, bulk=True,
                    audit_sink=audit_sink,
                )
            except Exception as exc:
                db.rollback()
                mapped = map_target_exception(exc)
                if mapped is None:
                    raise
                # 일괄은 한 건이라도 거부되면 전체 롤백이다 — 어느 건이었는지 남긴다.
                logger.warning(
                    "일괄 확장 목표 강제 변경 거부: order=%s to=%s",
                    getattr(order, "id", None), to_code, exc_info=True,
                )
                return mapped
        results.append(summary)
    db.commit()
    if kind == KIND_DELETE:
        invalidate_trash_caches("stage_override_delete")
    return jsonify({
        "success": True,
        "data": {
            "updated": len(results),
            "to": to_code,
            "reason": override.reason if override is not None else str(data.get("reason") or "").strip(),
            "results": results,
            "skipped_same": skipped_same,
            "skipped_as": list(skipped_as or []),
            "not_found": not_found,
            "mutation_receipt": None,
            **({"warning": AS_OVERLAY_BLOCK_MESSAGE} if skipped_as else {}),
        },
    })


__all__ = [
    "REASON_REQUIRED_MESSAGE",
    "SAME_STAGE_MESSAGE",
    "extended_bulk_response",
    "parse_if_match",
    "extended_single_response",
    "reason_missing_response",
]
