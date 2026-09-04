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

from foms.web.auth import get_user_by_id, log_access
from foms.services.audit_message_display import describe_field_change
from foms.services.orders.audit_order_context import order_audit_context
from foms.services.orders.status_constants import (
    BULK_ACTION_STATUS,
    STATUS,
    is_logistics_board_status,
)
from foms.services.orders.state_axes import as_overlay_outranks_status_write
from foms.services.orders.status_constants import AS_OVERLAY_PRESERVE_WORKFLOW_STAGE
from foms.services.orders.stage_override import (
    AS_OVERLAY_BLOCK_MESSAGE,
    AS_OVERLAY_STATUSES,
    MAIN_PIPELINE_CODES,
    OVERRIDE_BLOCK_MESSAGE,
    as_overlay_status,
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
from foms.services.orders.soft_delete import soft_delete_order
from foms.services.orders.order_mutation_policy import user_can
from foms.services.orders.state_axes import AXIS_MAIN, read_main_stage, read_state_axes
from foms.services.erp_order_flags import is_erp_order_record
from db import get_db
from foms.services.datetime_kst import now_utc_naive
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



def _bulk_audit(order, old_status, new_status, user_id) -> None:
    """벌크 상태 변경 1건을 구조화 감사로 남긴다(문장은 표시 SSOT 가 만든다).

    벌크 경로는 커밋을 한 번에 하므로 ``auto_commit=False`` 로 같은 트랜잭션에 싣는다.

    :param order: 대상 :class:`~models.Order`.
    :param old_status: 변경 전 상태 코드.
    :param new_status: 변경 후 상태 코드.
    :param user_id: 행위자 user id.
    """
    context = order_audit_context(order)
    log_access(
        describe_field_change(
            order_id=order.id, field="status", before=old_status, after=new_status,
            has_before=True, **context,
        ) + " (일괄 작업)",
        user_id,
        auto_commit=False,
        action="ORDER_STATUS_CHANGED", target_type="order", target_id=int(order.id),
        detail={"field": "status", "before": old_status, "after": new_status,
                "bulk": True, **context},
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
    # AS overlay 는 본공정 stage 를 덮지 않는다(STATE-AS-01). AS 완료 전이가 stage 를
    # 되돌리지 않아 한 번 덮이면 고착하고, 그 주문이 도면·생산·시공 큐에서 빠진다
    # (2026-09-04 운영 실측 62건). 이벤트는 그대로 남기되 write 만 건너뛴다.
    stage_write_skipped = new_status in AS_OVERLAY_PRESERVE_WORKFLOW_STAGE
    if new_status in STATUS and not stage_write_skipped:
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
                "stage_write_skipped": stage_write_skipped,
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

        # STATE-AS-01: 열린 AS 건이면 물류 축 목표는 status 를 덮지 않는다
        # (field_update 경로와 대칭 — 2026-09-03 운영 #4796·#4816).
        if as_overlay_outranks_status_write(order, new_status):
            return jsonify({
                "success": True,
                "old_status": old_status,
                "new_status": old_status,
                "message": "AS 접수 중인 주문이라 상태를 유지했습니다.",
            })
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

        audit_context = order_audit_context(order)
        log_access(
            describe_field_change(
                order_id=order_id, field="status", before=old_status, after=new_status,
                has_before=True, **audit_context,
            ),
            user_id,
            action="ORDER_STATUS_CHANGED", target_type="order", target_id=order_id,
            detail={"field": "status", "before": old_status, "after": new_status,
                    **audit_context},
        )

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


def _parse_expected_versions(data: dict[str, Any]) -> dict[int, int]:
    """요청 body 의 per-order If-Match version 맵을 파싱한다({order_id: expected_version}).

    JSON 객체 키는 문자열이므로 int 로 정규화한다. int 로 해석되지 않는 항목은 건너뛴다
    (해당 주문은 precondition 없이 삭제 — 하위호환: ``versions`` 미지정이면 전부 무검증).

    Args:
        data: 요청 JSON body. ``versions`` 키(dict)를 읽는다.

    Returns:
        order_id(int) → expected ``mutation_version``(int) 매핑(없으면 빈 dict).
    """
    raw = data.get("versions")
    if not isinstance(raw, dict):
        return {}
    parsed: dict[int, int] = {}
    for key, value in raw.items():
        try:
            parsed[int(key)] = int(value)
        except (TypeError, ValueError):
            continue
    return parsed


def _bulk_soft_delete_response(
    db: Any,
    order_ids: list[int],
    expected_versions: dict[int, int],
    *,
    actor_user_id: Any,
    actor_user: Any,
):
    """주문 대량 삭제를 canonical soft-delete + all-or-none 로 처리한다.

    각 주문에 :func:`soft_delete_order` 를 적용해 delete projection(``deleted_at``) set +
    ``mutation_version`` bump + ``ORDER_SOFT_DELETED`` event 를 기록하고(hard delete 없음),
    **하나라도** 권한/version/존재 실패면 전체 롤백한다(부분 삭제 0·단일 tx). 삭제 권한은
    AUTH-01 ``MANAGER_MUTATION`` 정책(ADMIN/MANAGER 전용; STAFF/VIEWER 403)을 재사용한다.

    **전이기(transitional) dual-write**: trash 서브시스템(:mod:`foms.web.orders.trash` 의
    list/restore/purge)이 아직 ``status=='DELETED'`` 술어에 의존하므로, canonical
    ``deleted_at`` 과 함께 legacy ``status='DELETED'`` + ``original_status`` 를 같은 tx 에서
    미러해 trash 가시성·restore 를 무회귀로 보존한다. 완전 canonical화(trash 술어→
    ``deleted_at``, restore→:func:`restore_order`, 이 status 미러 제거)는 DELETE-TRASH-01 소관.

    Args:
        db: 활성 DB 세션(이 함수가 commit/rollback 소유).
        order_ids: 삭제 대상 order id(정규화된 int 목록).
        expected_versions: order_id → If-Match ``mutation_version``(없으면 precondition 없음).
        actor_user_id: 삭제 actor user id(event/receipt 소유자).
        actor_user: 권한 판정용 User 객체(``MANAGER_MUTATION`` 평가; None 이면 거부).

    Returns:
        Flask ``(json, status_code)`` 응답 튜플. 권한 실패 403, version 충돌 409, 미존재 404,
        성공 200.
    """
    if not user_can("MANAGER_MUTATION", actor_user):
        return (
            jsonify({
                "success": False,
                "code": "FORBIDDEN",
                "message": "대량 삭제는 관리자(ADMIN/MANAGER) 권한이 필요합니다.",
            }),
            403,
        )
    try:
        deleted = 0
        for order_id in order_ids:
            result = soft_delete_order(
                db,
                order_id=order_id,
                actor_user_id=actor_user_id,
                expected_version=expected_versions.get(order_id),
            )
            if result is not None:  # None = 이미 삭제됨(멱등 no-op)
                deleted += 1
            # 전이기 dual-write: canonical deleted_at 과 함께 legacy status/original_status 를
            # 같은 tx 에 미러(trash 호환). status 를 덮기 전 원상태를 original_status 로 보존한다.
            order = db.get(Order, order_id)
            if order is not None and getattr(order, "status", None) != "DELETED":
                order.original_status = order.status or "RECEIVED"
                order.status = "DELETED"
            # original_status 에 방금 보존한 값이 곧 '이전 상태'다(덮어쓰기 전 값).
            trash_context = order_audit_context(order)
            previous_status = getattr(order, "original_status", None)
            log_access(
                describe_field_change(
                    order_id=order_id, field="status", before=previous_status,
                    after="DELETED", has_before=True, **trash_context,
                ),
                actor_user_id,
                auto_commit=False,
                action="ORDER_SOFT_DELETED", target_type="order", target_id=order_id,
                detail={"field": "status", "before": previous_status, "after": "DELETED",
                        "bulk": True, **trash_context},
            )
        db.commit()
        # 삭제 즉시 반영: 대시보드 read-slice 캐시(TTL 최대 300초) 무효화가 없으면 삭제한
        # 주문이 실측 날짜별 집계 등에 최대 5분 잔존한다(2026-08-10 운영 사고). commit 뒤에만.
        try:
            from foms.services.common.dashboard_cache import (
                invalidate_dashboard_caches_after_delete_transition,
            )

            invalidate_dashboard_caches_after_delete_transition("order_bulk_delete")
        except Exception:
            current_app.logger.warning(
                "post bulk delete dashboard cache invalidate failed", exc_info=True
            )
    except RevisionError as exc:
        # version 충돌/미존재 등 → 전체 롤백(부분 삭제 0). exc.status_code 로 HTTP 매핑.
        db.rollback()
        return (
            jsonify({
                "success": False,
                "code": exc.error_code,
                "message": str(exc),
            }),
            exc.status_code,
        )
    return (
        jsonify({
            "success": True,
            "updated": deleted,
            "new_status": "DELETED",
            "status_display": STATUS.get("DELETED", "DELETED"),
        }),
        200,
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
        blocked_as_orders: list[dict[str, Any]] = []

        valid_ids = []
        for order_id in order_ids:
            try:
                valid_ids.append(int(order_id))
            except (TypeError, ValueError):
                continue
        if not valid_ids:
            return jsonify({"success": False, "message": "유효한 주문 ID가 없습니다."}), 400

        if is_delete:
            # 대량 삭제 = canonical soft-delete + all-or-none(권한/version/존재 실패→전체 롤백).
            # trash route(status='DELETED' 직접 저장·original_status)와 혼합하지 않는다.
            return _bulk_soft_delete_response(
                db,
                valid_ids,
                _parse_expected_versions(data),
                actor_user_id=user_id,
                actor_user=get_user_by_id(user_id),
            )

        include_as = data.get("include_as") is True
        orders = db.query(Order).filter(Order.id.in_(valid_ids)).all()  # perf-ok: request bulk order id batch
        for order in orders:
            old_status = getattr(order, "status", None) or ""
            overlay = as_overlay_status(order)
            if overlay and not include_as and new_status not in AS_OVERLAY_STATUSES:
                # AS 접수/완료를 비AS 상태로 일괄 변경하면 AS 대시보드에서 통째로 사라진다
                # (2026-08-14 사고). 일괄 경로는 기본 제외하고 include_as 로만 명시 포함.
                blocked_as_orders.append({"order_id": int(order.id), "status": overlay})
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
                _bulk_audit(order, old_status, new_status, user_id)
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

            _bulk_audit(order, old_status, new_status, user_id)
            updated += 1

        db.commit()
        success = updated > 0 or not (blocked_override_required or blocked_as_orders)
        message = None
        if blocked_override_required and updated == 0:
            success = False
            message = OVERRIDE_BLOCK_MESSAGE
        elif blocked_override_required:
            message = (
                f"{len(blocked_override_required)}건은 역행/건너뛰기로 차단됨. "
                "「단계 강제 변경」을 사용하세요."
            )
        if blocked_as_orders:
            as_note = f"AS 상태 {len(blocked_as_orders)}건 제외 — " + AS_OVERLAY_BLOCK_MESSAGE
            message = f"{message} {as_note}" if message else as_note
        payload: dict[str, Any] = {
            "success": success,
            "updated": updated,
            "new_status": new_status,
            "status_display": STATUS.get(new_status, new_status),
            "blocked_override_required": blocked_override_required,
            "blocked_as_orders": blocked_as_orders,
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
