"""Status mutation handlers for the legacy orders blueprint.

STATE-LEGACY-01: generic status write(단건/벌크)의 **순수 메인 파이프라인 전이**를
canonical 전이 엔진(:func:`transition_order`, command ``SET_MAIN_STAGE``)으로 이관한다.
직접 ``order.status``/``workflow.stage`` 배정 대신 엔진이 row lock + actual-before + expected-from
+ mutation_version++ + idempotency receipt + legacy ``OrderEvent`` parity(``STAGE_CHANGED``)
+ 같은 tx outbox 를 원자 기록하고, ``order.status`` 는 canonical projection 으로 파생된다.

물류 보드 타깃(``COMPLETED``/``SCHEDULED``/``AS_*``/``ON_HOLD``/``DELETED`` 등 물류·AS·삭제
overlay)과 비ERP/overlay 혼재 주문은 **canonical 대상이 아니다** — 그 축은 STATE-OVERLAY-01/
STATE-AS-01/DELETE-CORE-00 소관이라 이 배치는 무접근이고, legacy_status_projection 이 overlay 를
우선 파생하므로 main 축으로 강제 이관하면 status 가 어긋난다. 그런 write 는 기존 legacy 경로
(:func:`_sync_erp_stage`)를 그대로 보존한다. 의도적 단계 역행·건너뛰기는 여전히 403 으로 차단해
「단계 강제 변경」(emergency override, reason+STAGE_OVERRIDE event) 경로로 몰아준다.
"""

from __future__ import annotations

import datetime
import hashlib
import json
from typing import Any, Callable

from flask import current_app, jsonify, request, session
from sqlalchemy.orm.attributes import flag_modified

from foms.web.auth import log_access
from foms.services.orders.status_constants import (
    BULK_ACTION_STATUS,
    STATUS,
    is_logistics_board_status,
)
from foms.services.orders.stage_override import (
    MAIN_PIPELINE_CODES,
    OVERRIDE_BLOCK_MESSAGE,
    current_stage_for_order,
    normalize_main_stage,
    requires_privileged_override,
)
from foms.services.orders.order_transition_service import (
    COMMAND_REGISTRY,
    StageConflictError,
    TransitionCommand,
    TransitionError,
    transition_order,
)
from foms.services.orders.revision import RevisionError
from foms.services.orders.state_axes import AXIS_MAIN, read_main_stage, read_state_axes
from foms.services.erp_order_flags import is_erp_order_record
from db import get_db
from foms.services.datetime_kst import now_kst, now_utc_naive
from foms.services.erp_display import get_today_kst
from foms.services.erp_sync_columns import sync_erp_flat_columns
from models import Order, OrderEvent


# --- STATE-LEGACY-01: generic 메인 파이프라인 전이 canonical command 등록 -------------
# ``SET_MAIN_STAGE`` 는 generic status 라우트(단건 update_order_status / 벌크
# bulk_update_order_status / field_update field=status)의 **순수 메인 파이프라인** 전이를
# 담는 canonical command 다. STATE-PROD-01 과 동일하게 registry 에 additive 로 등록한다
# (엔진 파일은 import 만 — 무편집). event_type=STAGE_CHANGED 로 두어 기존 소비자
# (production_change_alerts / order_timeline_v3 / order_event_display: payload from/to 사용)를
# 무회귀로 보존한다. policy_id 는 REV-00 receipt idempotency scope 문자열일 뿐이며
# POLICY_REGISTRY 와 무관하다(STATE-PROD 관례; auth 게이트는 STAFF_MUTATION before_request).
_POLICY_SET_MAIN_STAGE = "STATE_SET_MAIN_STAGE"

COMMAND_REGISTRY.setdefault(
    "SET_MAIN_STAGE",
    TransitionCommand(
        command_id="SET_MAIN_STAGE",
        policy_id=_POLICY_SET_MAIN_STAGE,
        axis=AXIS_MAIN,
        from_values=MAIN_PIPELINE_CODES,
        to_values=MAIN_PIPELINE_CODES,
        event_type="STAGE_CHANGED",
        effect_type="STAGE_NOTIFICATION",
    ),
)


def _idempotency_key(body: dict[str, Any]) -> str | None:
    """요청 idempotency key(헤더 우선, body fallback, ≤64자). 없으면 None(중복제거 안 함)."""
    key = request.headers.get("Idempotency-Key") or body.get("idempotency_key")
    key = str(key).strip() if key is not None else ""
    return key[:64] if key else None


def _scope_hash(command_id: str, order_id: int) -> str:
    """전이 scope 의 sha256 hex(receipt 저장용)."""
    return hashlib.sha256(f"{command_id}:{order_id}".encode("utf-8")).hexdigest()


def _request_hash(body: dict[str, Any]) -> str:
    """요청 payload 의 sha256 hex(same-key/different-hash 감지용)."""
    canonical = json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _transition_error_response(exc: Exception):
    """전이 엔진/REV helper 예외를 route JSON 오류로 매핑(stage 불일치는 INVALID_STAGE)."""
    code = (
        "INVALID_STAGE"
        if isinstance(exc, StageConflictError)
        else getattr(exc, "error_code", "TRANSITION_ERROR")
    )
    status = getattr(exc, "status_code", 409)
    return jsonify({"success": False, "code": code, "message": str(exc)}), status


def should_canonicalize_main_status(order: Order, new_status: str) -> bool:
    """generic status write 를 canonical ``SET_MAIN_STAGE`` 전이로 보낼지 판정한다.

    canonical 대상은 **순수 메인 파이프라인 전이**뿐이다: ERP 주문이고, 타깃이 물류 보드
    코드(``COMPLETED``/``SCHEDULED``/``AS_*``/``ON_HOLD``/``DELETED``)가 아닌 메인 파이프라인
    코드이며, 주문의 canonical 축이 overlay(logistics/hold/AS/delete) 없이 메인에 깨끗이
    올라와 있어야 한다. overlay 가 있으면 :func:`legacy_status_projection` 이 overlay 를
    우선 파생하므로 main 축으로 이관 시 ``order.status`` 가 타깃과 어긋난다 — 그 경우 legacy
    경로를 보존한다(overlay 축은 STATE-OVERLAY/STATE-AS/DELETE 소관).

    Args:
        order: 대상 주문(ORM).
        new_status: 목표 상태 코드(``STATUS`` 키).

    Returns:
        canonical 전이 대상이면 True.
    """
    if not is_erp_order_record(order):
        return False
    if is_logistics_board_status(new_status):
        return False
    if normalize_main_stage(new_status) not in MAIN_PIPELINE_CODES:
        return False
    axes = read_state_axes(order)
    return (
        axes.main in MAIN_PIPELINE_CODES
        and axes.logistics == "NONE"
        and axes.hold == "NONE"
        and axes.as_status == "NONE"
        and axes.deleted == "NONE"
    )


def apply_canonical_main_stage(
    db: Any,
    order: Order,
    target_main: str,
    *,
    actor_user_id: Any,
    body: dict[str, Any],
    idempotency_key: str | None = None,
):
    """``SET_MAIN_STAGE`` canonical 전이를 실행한다(commit 은 호출부 소유).

    성공 시 ``None`` 을 반환하고, 전이/REV 계약 위반 시 세션을 rollback 하고 오류 JSON
    응답 튜플을 반환한다. ``order.status``/``workflow.stage`` 직접 배정 없이 엔진이 canonical
    write + projection + version++ + receipt + ``STAGE_CHANGED`` event + outbox 를 기록한다.

    Args:
        db: business 트랜잭션 세션(호출부가 commit 소유).
        order: 대상 주문(actual-before 는 엔진이 row lock 아래 재확인).
        target_main: 목표 메인 파이프라인 코드(``SET_MAIN_STAGE.to_values`` 안).
        actor_user_id: 요청 actor(receipt 소유자·event author).
        body: 요청 payload(request_hash 계산).
        idempotency_key: 명시 시 그 값 사용(벌크는 None 강제 — batch 공유 key 는 cross-order
            replay 를 유발). 미지정이면 헤더/body 에서 추출.

    Returns:
        성공이면 ``None``, 실패면 ``(json_response, status_code)`` 튜플.
    """
    key = idempotency_key if idempotency_key is not None else _idempotency_key(body)
    try:
        transition_order(
            db,
            command_id="SET_MAIN_STAGE",
            order_id=order.id,
            actor_user_id=actor_user_id,
            expected_from=read_main_stage(order),
            target_value=target_main,
            scope_hash=_scope_hash("SET_MAIN_STAGE", order.id),
            request_hash=_request_hash(body),
            idempotency_key=key,
        )
    except (TransitionError, RevisionError) as exc:
        db.rollback()
        return _transition_error_response(exc)
    return None


def _sync_erp_stage(order: Order, new_status: str, user_id: Any, db: Any, *, bulk: bool) -> None:
    """ERP 주문의 workflow.stage 동기화 + STAGE_CHANGED 이벤트 기록 (단건/벌크 legacy 공용).

    비ERP 주문이나 structured_data 가 dict 가 아니면 아무것도 하지 않는다.
    STATE-LEGACY-01 이후 이 경로는 물류 보드/overlay 타깃(canonical 대상 아님) 전용이다
    (순수 메인 파이프라인 전이는 :func:`apply_canonical_main_stage` 가 담당). workflow 는
    dict() 셸 복사 패턴을 유지한다(기존 동작 보존).

    :param order: status 가 이미 갱신된 주문 ORM 객체.
    :param new_status: 새 상태 코드(STATUS 키).
    :param user_id: STAGE_CHANGED 기록용 사용자 id(없으면 None).
    :param db: 활성 DB 세션(commit 은 호출부 소관).
    :param bulk: STAGE_CHANGED payload 의 bulk 플래그(단건 False, 벌크 True).
    """
    structured_data = getattr(order, "structured_data", None)
    if not (is_erp_order_record(order) and isinstance(structured_data, dict) and structured_data):
        return
    workflow = structured_data.get("workflow") or {}
    old_stage = (workflow.get("stage") or "").strip()
    if new_status in STATUS:
        workflow = dict(workflow)
        workflow["stage"] = new_status
        workflow["stage_updated_at"] = now_utc_naive().isoformat()
        structured_data["workflow"] = workflow
        setattr(order, "structured_data", structured_data)
        flag_modified(order, "structured_data")
        sync_erp_flat_columns(order, structured_data)
    db.add(
        OrderEvent(
            order_id=order.id,
            event_type="STAGE_CHANGED",
            payload={
                "from": old_stage,
                "to": new_status,
                "manual": True,
                "bulk": bulk,
            },
            created_by_user_id=user_id,
        )
    )


def update_order_status_response(
    *,
    get_today_kst_func: Callable[[], Any] = get_today_kst,
):
    """Handle the single-order status mutation."""
    db = get_db()
    try:
        data = request.get_json() or {}
        order_id = data.get("order_id")
        new_status = data.get("status")

        if not order_id or not new_status:
            return jsonify({"success": False, "message": "필수 파라미터가 누락되었습니다."}), 400
        if new_status not in STATUS:
            return jsonify({"success": False, "message": "유효하지 않은 상태입니다."}), 400

        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404

        old_status = getattr(order, "status", None) or ""
        from_stage = current_stage_for_order(order)
        if is_erp_order_record(order) and requires_privileged_override(from_stage, new_status):
            return jsonify({"success": False, "message": OVERRIDE_BLOCK_MESSAGE}), 403

        user_id = session.get("user_id")

        if should_canonicalize_main_status(order, new_status):
            # 순수 메인 파이프라인 전이 → canonical 엔진 경유(direct stage 배정 없음).
            err = apply_canonical_main_stage(
                db, order, normalize_main_stage(new_status),
                actor_user_id=user_id, body=data,
            )
            if err is not None:
                return err
        else:
            # 물류/AS/overlay 타깃 또는 overlay 혼재 주문: legacy writer 보존(무접근 축 소관).
            order.status = new_status
            if new_status == "AS_RECEIVED" and not getattr(order, "as_received_date", None):
                setattr(order, "as_received_date", get_today_kst_func().strftime("%Y-%m-%d"))
            _sync_erp_stage(order, new_status, user_id, db, bulk=False)

        db.commit()

        old_status_name = STATUS.get(old_status, old_status)
        new_status_name = STATUS.get(new_status, new_status)
        log_access(f"주문 #{order_id} 상태 변경: {old_status_name} → {new_status_name}", user_id)

        return jsonify(
            {
                "success": True,
                "old_status": old_status,
                "new_status": new_status,
                "status_display": STATUS.get(new_status, new_status),
            }
        )
    except Exception as exc:
        db.rollback()
        current_app.logger.error(f"주문 상태 업데이트 실패: {str(exc)}")
        return (
            jsonify({"success": False, "message": f"오류 발생: {str(exc)}"}),
            500,
        )


def bulk_update_order_status_response(
    *,
    get_today_kst_func: Callable[[], Any] = get_today_kst,
):
    """Handle the bulk order-status mutation and ERP Beta workflow sync."""
    try:
        data = request.get_json() or {}
        order_ids = data.get("order_ids")
        new_status = (data.get("status") or "").strip()

        if not order_ids or not isinstance(order_ids, list):
            return jsonify({"success": False, "message": "order_ids(배열)가 필요합니다."}), 400
        if not new_status:
            return jsonify({"success": False, "message": "status가 필요합니다."}), 400

        is_delete = new_status == "DELETED"
        if not is_delete and new_status not in BULK_ACTION_STATUS:
            return jsonify({"success": False, "message": "유효한 status가 필요합니다."}), 400

        db = get_db()
        user_id = session.get("user_id")
        updated = 0
        blocked_override_required: list[int] = []
        deleted_at_str = now_kst().strftime("%Y-%m-%d %H:%M:%S")

        valid_ids = []
        for order_id in order_ids:
            try:
                valid_ids.append(int(order_id))
            except (TypeError, ValueError):
                continue
        if not valid_ids:
            return jsonify({"success": False, "message": "유효한 주문 ID가 없습니다."}), 400

        orders = db.query(Order).filter(Order.id.in_(valid_ids)).all()  # perf-ok: request bulk order id batch
        for order in orders:
            old_status = getattr(order, "status", None) or ""
            if is_delete:
                setattr(order, "status", "DELETED")
                setattr(order, "original_status", old_status or "RECEIVED")
                setattr(order, "deleted_at", deleted_at_str)
                log_access(
                    f"주문 #{order.id} 휴지통 이동 (bulk): {old_status} → DELETED",
                    user_id,
                    auto_commit=False,
                )
                updated += 1
                continue

            from_stage = current_stage_for_order(order)
            if is_erp_order_record(order) and requires_privileged_override(from_stage, new_status):
                blocked_override_required.append(int(order.id))
                continue

            if should_canonicalize_main_status(order, new_status):
                # 순수 메인 파이프라인 전이 → canonical 엔진 경유(벌크는 batch 공유 key 금지 →
                # idempotency_key=None; scope_hash 는 order_id 별로 distinct).
                err = apply_canonical_main_stage(
                    db, order, normalize_main_stage(new_status),
                    actor_user_id=user_id,
                    body={"order_id": order.id, "status": new_status},
                    idempotency_key=None,
                )
                if err is not None:
                    return err
                log_access(
                    f"주문 #{order.id} 상태 변경: {old_status} → {new_status}",
                    user_id,
                    auto_commit=False,
                )
                updated += 1
                continue

            setattr(order, "status", new_status)
            if new_status == "AS_RECEIVED" and not getattr(order, "as_received_date", None):
                setattr(order, "as_received_date", get_today_kst_func().strftime("%Y-%m-%d"))

            # 기존 동작 보존: ERP 주문의 dict 아닌 truthy sd 는 집계/로그 제외(continue).
            structured_data = getattr(order, "structured_data", None)
            if is_erp_order_record(order) and structured_data and not isinstance(structured_data, dict):
                continue
            _sync_erp_stage(order, new_status, user_id, db, bulk=True)

            log_access(
                f"주문 #{order.id} 상태 변경: {old_status} → {new_status}",
                user_id,
                auto_commit=False,
            )
            updated += 1

        db.commit()
        success = updated > 0 or not blocked_override_required
        message = None
        if blocked_override_required and updated == 0:
            success = False
            message = OVERRIDE_BLOCK_MESSAGE
        elif blocked_override_required:
            message = (
                f"{len(blocked_override_required)}건은 역행/건너뛰기로 차단됨. "
                "「단계 강제 변경」을 사용하세요."
            )
        payload: dict[str, Any] = {
            "success": success,
            "updated": updated,
            "new_status": new_status,
            "status_display": STATUS.get(new_status, new_status),
            "blocked_override_required": blocked_override_required,
        }
        if message:
            payload["message"] = message
        status_code = 200 if success else 403
        return jsonify(payload), status_code
    except Exception as exc:
        db = get_db()
        if db:
            db.rollback()
        current_app.logger.error(f"bulk_update_order_status 실패: {str(exc)}")
        return (
            jsonify({"success": False, "message": f"오류 발생: {str(exc)}"}),
            500,
        )


__all__ = [
    "apply_canonical_main_stage",
    "bulk_update_order_status_response",
    "should_canonicalize_main_status",
    "update_order_status_response",
]
