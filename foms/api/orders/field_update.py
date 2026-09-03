"""Field update handlers for the legacy orders blueprint."""

from __future__ import annotations

import copy
import datetime
import uuid
from foms.services.datetime_kst import now_utc_naive
from typing import Any, Callable

from flask import current_app, jsonify, request, session
from sqlalchemy.orm.attributes import flag_modified

from foms.web.auth import get_user_by_id, log_access
from foms.services.audit_message_display import describe_field_change
from foms.services.orders.audit_order_context import order_audit_context
from foms.services.orders.status_constants import STATUS
from db import get_db
from foms.services.as_content_safety import load_structured_data_dict_or_raise
from foms.services.erp_order_flags import is_erp_order_record
from foms.services.orders.state_axes import as_overlay_outranks_status_write
from foms.services.erp_permissions import can_edit_erp
from foms.services.erp_display import _normalize_date_to_yyyymmdd
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.orders.as_log import append_system_log
from foms.services.orders.construction_type import normalize_regional_construction_type
from foms.services.orders.order_field_change_writer import record_field_changes
from foms.services.orders.structured_diff import diff_structured
from models import Order

ORDER_UPDATE_ALLOWED_FIELDS = [
    "manager_name",
    "scheduled_date",
    "status",
    "shipping_scheduled_date",
    "completion_date",
    "measurement_completed",
    "regional_sales_order_upload",
    "regional_blueprint_sent",
    "regional_order_upload",
    "regional_cargo_sent",
    "regional_construction_info_sent",
    "as_received_date",
    # STATE-AS-01: as_completed_date 의 generic write(order.status/workflow.stage 를
    # AS_COMPLETED 로 덮던 AS main stage 복구 antipattern)는 제거됐다. 다만 AS 대시보드·
    # 태블릿 비교화면의 완료 버튼은 이 필드를 여기로 보내므로(전용 /as/complete 는 UI
    # 호출자 0), 허용은 유지하되 canonical AS cycle command 로 위임한다
    # (:func:`_bridge_as_completed_date`) — 직접 상태 쓰기는 이 파일에 없다.
    "as_completed_date",
    "as_visit_date",
    # AS 방문 가능시간(평일/주말·시간대) — schedule.as_visit.availability (SSOT:
    # foms/services/orders/as_availability.py)
    "as_visit_availability",
    "as_pending",
    "as_blueprint",
    "sales_delivery",
    "measurement_date",
    "regional_memo",
    "construction_type",
    "is_cabinet",
    # cabinet_status·shipping_fee → STORAGE-WRITER-01 typed adapter(storage.py:
    # update_storage_field)로 이관, generic coercion 경로 제거.
    "construction_workers",
]

# as_content/as_content_2 는 쓰기 퇴역(T12) — 신규 AS 기록은 as_log(POST /as/log)만
# 받는다. 두 필드는 legacy 읽기 전용으로 남아 최초 append 때 as_log 로 영구화된다.
STRUCTURED_SYNC_FIELDS = {
    "as_visit_date",
    "as_visit_availability",
    "as_pending",
    "as_blueprint",
    "sales_delivery",
    "construction_workers",
}

# --------------------------------------------------------------------------- #
# AUDIT-GAP-01 — 이 라우트가 바꾸는 값 → 변경 원장(``order_field_changes``) 경로 매핑
#
# 이 화면의 **필드 이름과 원장 경로는 같지 않다.** 예를 들어 ``as_visit_date`` 는
# ``structured_data`` 의 ``schedule.as_visit.date`` 를 쓴다. 필드 이름 그대로 적으면 같은
# 값의 이력이 화면마다 다른 경로로 흩어져 한 축으로 못 읽는다(운영 실측 2026-08-26:
# ``schedule.as_visit.date`` 원장 7행 vs ``ORDER_FIELD_UPDATED`` 보안로그 126행).
#
# | 필드 | 실제 쓰기 대상 | 원장 path | 출처 |
# |---|---|---|---|
# | as_visit_date | sd ``schedule.as_visit.date`` (+ 표시용 인스턴스 속성) | ``schedule.as_visit.date`` | diff_structured |
# | as_pending | sd ``shipment.as_pending`` | ``shipment.as_pending`` | diff_structured |
# | sales_delivery | sd ``shipment.sales_delivery`` | ``shipment.sales_delivery`` | diff_structured |
# | construction_workers | sd ``shipment.construction_workers`` | ``shipment.construction_workers`` | diff_structured |
# | manager_name | 컬럼 + sd ``parties.manager.name`` | sd 경로(비ERP 는 컬럼명) | diff + 평면 폴백 |
# | measurement_date | 컬럼 + sd ``schedule.measurement.date`` | sd 경로(비ERP 는 컬럼명) | diff + 평면 폴백 |
# | scheduled_date | 컬럼 + sd ``schedule.construction.date`` | sd 경로(비ERP 는 컬럼명) | diff + 평면 폴백 |
# | status | 컬럼 + sd ``workflow.stage``(물류 중간상태는 stage 보존) | sd 경로, 없으면 ``status`` | diff + 평면 폴백 |
# | as_completed_date | AS cycle command(컬럼) | ``as_completed_date`` | 브리지 전용 |
# | shipping_scheduled_date · completion_date · as_received_date · regional_memo
#   · construction_type · is_cabinet · measurement_completed · regional_* 5종
#   | 평면 컬럼만 | 같은 이름(점 없음) | ``_ledger_flat_change`` |
# | as_visit_availability | sd ``schedule.as_visit.availability`` | **미기록** | ``SCALAR_PATHS`` 밖(폼 저장이 ``as_visit`` 를 통째로 지우는 선행 결함 때문에 등재 보류 — AUDIT-GAP-01 원장 '범위 밖') |
# | as_blueprint | sd ``shipment.as_blueprint`` | **미기록** | ``SCALAR_PATHS`` 미등재(화이트리스트는 별도 소유) |
# --------------------------------------------------------------------------- #

#: 평면 컬럼을 바꾸는 필드 → 원장 path. 평면 컬럼은 **점 없는 컬럼명**을 쓴다(ORDER-FLAG-01
#: 확정 규약). ``_LEDGER_SD_TWIN`` 에 있는 필드는 같은 저장에서 sd 쌍둥이가 함께 바뀌므로,
#: 그 sd 경로가 diff 에 실렸으면 평면 행을 만들지 않는다 — 한 번의 변경이 경로 2벌로
#: 쪼개지면 감사 화면의 ``path_template`` 필터가 반쪽만 잡는다.
_LEDGER_FLAT_PATHS: dict[str, str] = {
    "status": "status",
    "manager_name": "manager_name",
    "measurement_date": "measurement_date",
    "scheduled_date": "scheduled_date",
    "shipping_scheduled_date": "shipping_scheduled_date",
    "completion_date": "completion_date",
    "as_received_date": "as_received_date",
    "regional_memo": "regional_memo",
    "construction_type": "construction_type",
    "is_cabinet": "is_cabinet",
    "measurement_completed": "measurement_completed",
    "regional_sales_order_upload": "regional_sales_order_upload",
    "regional_blueprint_sent": "regional_blueprint_sent",
    "regional_order_upload": "regional_order_upload",
    "regional_cargo_sent": "regional_cargo_sent",
    "regional_construction_info_sent": "regional_construction_info_sent",
}

#: 같은 저장에서 함께 쓰이는 sd 쌍둥이 경로(중복 억제용). 비ERP 주문은 sd 를 아예 읽지
#: 않으므로 쌍둥이가 없고, 그때만 평면 경로가 유일한 기록이 된다.
_LEDGER_SD_TWIN: dict[str, str] = {
    # ``status`` 는 여기 **없다**(2026-08-26 CEO 판정). ``order.status`` 와 ``workflow.stage``
    # 는 일부러 분리된 두 축이다 — AS 접수 주문은 status 가 AS 로 바뀌어도 workflow.stage 는
    # MEASURE 로 남는다(``stage_override.as_overlay_status`` docstring 이 SSOT). 쌍둥이로
    # 묶어 평면 행을 억제하면 **한 저장에서 함께 바뀐 두 값 중 하나가 통째로 사라진다.**
    "manager_name": "parties.manager.name",
    "measurement_date": "schedule.measurement.date",
    "scheduled_date": "schedule.construction.date",
}

#: 불리언 컬럼 — ``None`` 과 ``False`` 는 같은 뜻이라 op 는 항상 ``set`` 이다.
_LEDGER_BOOL_FIELDS: frozenset[str] = frozenset({
    "is_cabinet",
    "measurement_completed",
    "regional_sales_order_upload",
    "regional_blueprint_sent",
    "regional_order_upload",
    "regional_cargo_sent",
    "regional_construction_info_sent",
})


def _ledger_text_value(value: Any) -> str | None:
    """평면 컬럼의 원장 비교값(빈값은 ``None`` 으로 접는다).

    컬럼마다 빈값이 ``None`` 이기도 하고 ``''`` 이기도 하다. 둘을 같은 뜻으로 접어야
    빈값→빈값 저장이 가짜 변경으로 기록되지 않는다.

    Args:
        value: 컬럼에서 읽은 원시 값.

    Returns:
        문자열, 또는 빈값이면 ``None``.
    """
    if value is None:
        return None
    text_value = value if isinstance(value, str) else str(value)
    return text_value or None


def _ledger_flat_change(order: Order, field: str, before_raw: Any) -> dict[str, Any] | None:
    """평면 컬럼 1개의 원장 change dict 를 만든다(변경 없으면 ``None``).

    Args:
        order: setattr 이 끝난 주문(현재값 출처).
        field: 요청 필드명.
        before_raw: 쓰기 **전에** 떠 둔 컬럼 값.

    Returns:
        ``{'path','before','after','op'}`` 또는 값이 그대로면 ``None``.
    """
    path = _LEDGER_FLAT_PATHS.get(field)
    if not path:
        return None
    after_raw = getattr(order, field, None)
    if field in _LEDGER_BOOL_FIELDS:
        # 요청 값은 아직 flush 전이라 "true"/1 같은 원시 표현일 수 있다. 컬럼 타입에 기대지
        # 않고 요청 해석과 같은 규칙으로 접는다(bool("false") 가 True 인 함정 회피).
        before_bool = _coerce_bool_value(before_raw) if before_raw is not None else False
        after_bool = _coerce_bool_value(after_raw) if after_raw is not None else False
        if before_bool == after_bool:
            return None
        return {"path": path, "before": before_bool, "after": after_bool, "op": "set"}
    before_text = _ledger_text_value(before_raw)
    after_text = _ledger_text_value(after_raw)
    if before_text == after_text:
        return None
    op = "add" if before_text is None else ("clear" if after_text is None else "set")
    return {"path": path, "before": before_text, "after": after_text, "op": op}


def ensure_path(parent: dict[str, Any], key: str) -> dict[str, Any]:
    """Return a mutable child mapping, creating it when missing."""
    if key not in parent or not isinstance(parent.get(key), dict):
        parent[key] = {}
    child = parent[key]
    if not isinstance(child, dict):
        parent[key] = {}
        child = parent[key]
    return child


def _clear_as_pending_if_both_as_dates_empty(order: Order, structured_data: dict[str, Any]) -> bool:
    """접수일과 schedule.as_visit.date가 모두 비면 미결 플래그를 끈다.

    미결 버튼이 방문일 기준이지만, 접수·방문이 모두 소거되면 AS 접수 화면으로
    원상복구해야 하므로 JSONB 진실값(shipment.as_pending)을 직접 정리한다.
    """
    shipment = structured_data.get("shipment") or {}
    if not isinstance(shipment, dict) or shipment.get("as_pending") is not True:
        return False
    received = getattr(order, "as_received_date", None)
    if str(received or "").strip():
        return False
    schedule = structured_data.get("schedule")
    visit_raw = ""
    if isinstance(schedule, dict):
        visit_block = schedule.get("as_visit")
        if isinstance(visit_block, dict):
            visit_raw = visit_block.get("date")
    if str(visit_raw or "").strip():
        return False
    if str(getattr(order, "as_visit_date", None) or "").strip():
        return False
    ensure_path(structured_data, "shipment")["as_pending"] = False
    return True


def _as_date_changed(old_value: Any, new_value: Any) -> bool:
    """AS 날짜 두 값이 실제로 다른지 판정(표기 차이는 무시, 빈 값끼리는 같음).

    Args:
        old_value: 변경 전 값(컬럼 또는 structured_data 스냅샷).
        new_value: 요청이 보낸 값.

    Returns:
        정규화 후 다르면 True.
    """
    return (_normalize_date_to_yyyymmdd(old_value) or "") != (
        _normalize_date_to_yyyymmdd(new_value) or ""
    )


def _coerce_bool_value(value: Any) -> bool:
    """Interpret form and JSON boolean values consistently."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in ("1", "true", "yes", "y", "on")


def _normalize_construction_workers_value(value: Any) -> list[str]:
    """Normalize comma/newline/list construction worker input into unique names."""
    if isinstance(value, list):
        raw_values = value
    else:
        raw_values = str(value or "").replace("\n", ",").split(",")

    workers: list[str] = []
    for item in raw_values:
        if isinstance(item, dict):
            raw_name = item.get("name") or item.get("text") or item.get("value") or ""
        else:
            raw_name = item
        name = str(raw_name or "").strip()
        if name and name not in workers:
            workers.append(name)
    return workers


def _load_order_structured_data_for_update(order: Order) -> dict[str, Any]:
    """Load order.structured_data without silently dropping malformed content."""
    try:
        return load_structured_data_dict_or_raise(getattr(order, "structured_data", None))
    except ValueError as exc:
        raise ValueError(
            f"structured_data를 안전하게 불러올 수 없어 저장을 중단했습니다: {exc}"
        ) from exc


def _build_order_update_response(
    order: Order,
    field: str,
    fallback_value: Any,
    structured_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the legacy response payload for update_order_field."""
    shipment = (structured_data.get("shipment") or {}) if structured_data else {}
    schedule = (structured_data.get("schedule") or {}) if structured_data else {}
    as_visit = (schedule.get("as_visit") or {}) if isinstance(schedule, dict) else {}

    if field == "as_pending":
        normalized_value = shipment.get("as_pending") is True
    elif field == "as_blueprint":
        normalized_value = shipment.get("as_blueprint") is True
    elif field == "sales_delivery":
        normalized_value = shipment.get("sales_delivery") is True
    elif field == "construction_workers":
        normalized_value = _normalize_construction_workers_value(
            shipment.get("construction_workers")
        )
    elif field == "as_visit_date":
        normalized_value = as_visit.get("date") or ""
    else:
        normalized_value = getattr(order, field, fallback_value)

    status = getattr(order, "status", None)
    status_label = STATUS.get(status, status) if isinstance(status, str) else status
    return {
        "success": True,
        "message": "정보가 업데이트되었습니다.",
        "normalized_value": normalized_value if normalized_value is not None else "",
        "status": status,
        "status_label": status_label,
        "as_completed_date": getattr(order, "as_completed_date", None) or "",
        "as_visit_date": getattr(order, "as_visit_date", None) or "",
        "as_pending": shipment.get("as_pending") is True,
        "as_blueprint": shipment.get("as_blueprint") is True,
        "sales_delivery": shipment.get("sales_delivery") is True,
        "construction_workers": _normalize_construction_workers_value(
            shipment.get("construction_workers")
        ),
    }


def _bridge_as_completed_date(db, order: Order, user: Any, value: Any, body: dict[str, Any]):
    """AS 완료/완료 취소를 canonical AS cycle command 로 위임한다(STATE-AS-01 브리지).

    AS 대시보드·태블릿 비교화면의 완료 버튼은 이 필드를 generic field_update 로 보낸다.
    generic 경로가 ``order.status``/``workflow.stage`` 를 직접 덮던 main stage 복구
    antipattern 을 없애면서 그 버튼을 살리는 방법은, 이 필드만 canonical command 로
    위임하는 것이다. 타임라인 system 이벤트는 command 와 **같은 tx** 안에서 append 된다
    (별도 commit 금지 — 전이 실패 시 기록만 남는 구멍을 막는다).

    Args:
        db: 요청 세션(commit 은 이 함수 소유). order: 대상 주문. user: actor.
        value: 요청 값(빈 값이면 완료 취소). body: 원본 payload(hash·idempotency 계산용).

    Returns:
        Flask 응답. 형식 오류 400, cycle 계약 위반 409, 성공은 generic 응답과 같은 형태.
    """
    from foms.api.cs.as_orders import (
        _as_error_response,
        _idempotency_key,
        _invalidate_shipment_asrec_caches,
        _request_hash,
        _scope_hash,
    )
    from foms.services.orders.as_cycle_service import (
        AS_IN_PROGRESS,
        AS_RECEIVED,
        clear_as_completed_date,
        complete_as_cycle,
        current_cycle,
        cycle_status,
        reopen_as_cycle,
    )

    trimmed = str(value or "").strip()
    normalized = _normalize_date_to_yyyymmdd(trimmed) if trimmed else None
    if trimmed and not normalized:
        return jsonify(
            {"success": False, "message": "완료일 형식이 올바르지 않습니다. (YYYY-MM-DD)"}
        ), 400
    structured_data = getattr(order, "structured_data", None) or {}
    before_completed = _normalize_date_to_yyyymmdd(getattr(order, "as_completed_date", None))
    if not _as_date_changed(getattr(order, "as_completed_date", None), normalized):
        # 같은 값 재저장은 무기록 — append-only 타임라인이 중복으로 차면 안 된다.
        return jsonify(_build_order_update_response(order, "as_completed_date", value, structured_data))

    actor_user_id = getattr(user, "id", None)
    try:
        if normalized:
            complete_as_cycle(
                db, order_id=order.id, actor_user_id=actor_user_id,
                note=str(body.get("note") or ""), completed_date=normalized,
                # AS 대시보드는 RECEIVED cycle 을 곧바로 완료 처리한다(별도 시작 버튼 없음).
                allow_from=(AS_RECEIVED, AS_IN_PROGRESS),
                sd_hook=lambda sd: append_system_log(sd, text="AS 완료"),
                legacy_bridge=True,
                scope_hash=_scope_hash("AS_COMPLETE", order.id),
                request_hash=_request_hash(body), idempotency_key=_idempotency_key(body),
            )
        else:
            open_status = cycle_status(current_cycle(getattr(order, "structured_data", None) or {}))
            if open_status in (AS_RECEIVED, AS_IN_PROGRESS):
                # 이미 열린 cycle 인데 완료일만 남은 드리프트(재접수 후 잔존).
                clear_as_completed_date(
                    db, order_id=order.id, actor_user_id=actor_user_id,
                    sd_hook=lambda sd: append_system_log(sd, text="AS 완료 취소"),
                    legacy_bridge=True,
                    scope_hash=_scope_hash("AS_CLEAR_COMPLETED_DATE", order.id),
                    request_hash=_request_hash(body), idempotency_key=_idempotency_key(body),
                )
            else:
                reopen_as_cycle(
                    db, order_id=order.id, actor_user_id=actor_user_id, reason="AS 완료 취소",
                    sd_hook=lambda sd: append_system_log(sd, text="AS 완료 취소"),
                    legacy_bridge=True,
                    scope_hash=_scope_hash("AS_REOPEN", order.id),
                    request_hash=_request_hash(body), idempotency_key=_idempotency_key(body),
                )
    except Exception as exc:  # noqa: BLE001 — 계약 위반은 409, 그 외 500 으로 분기
        return _as_error_response(db, exc)

    _as_audit = order_audit_context(order)
    # AUDIT-GAP-01: 완료일은 여기까지 오면 반드시 바뀐 것이다(위 무변경 게이트 통과). 원장은
    # 평면 컬럼이라 점 없는 컬럼명으로 싣고, 헤더 detail 은 같은 change_set 으로 잇는다.
    as_change_set = str(uuid.uuid4())
    as_recorded = record_field_changes(
        db,
        [{
            "path": "as_completed_date",
            "before": before_completed,
            "after": normalized,
            "op": "add" if before_completed is None else ("clear" if normalized is None else "set"),
        }],
        order_id=int(order.id),
        actor_user_id=session.get("user_id"),
        change_set_id=as_change_set,
    )
    _as_detail = {
        "field": "as_completed_date",
        # 무엇을 지웠는지가 없으면 되돌릴 수도 따질 수도 없다(운영 97건이 잃어버린 정보).
        "before": before_completed,
        "after": value,
        **_as_audit,
    }
    if as_recorded:
        _as_detail["change_set"] = as_change_set
    log_access(
        describe_field_change(
            order_id=order.id, field="as_completed_date", before=before_completed,
            after=value, has_before=True, **_as_audit
        ),
        session["user_id"], auto_commit=False,
        action="ORDER_FIELD_UPDATED", target_type="order", target_id=order.id,
        detail=_as_detail,
    )
    db.commit()
    _invalidate_shipment_asrec_caches("field_update:as_completed_date")
    return jsonify(_build_order_update_response(
        order, "as_completed_date", value, getattr(order, "structured_data", None) or {}))


def update_order_field_response(
    *,
    clean_dict_like_name: Callable[[Any], str],
):
    """Update legacy order fields while keeping the ERP Beta sync contract intact."""
    db = get_db()
    data = request.get_json() or {}

    order_id = data.get("order_id")
    field = data["field"] if "field" in data else data.get("field_name")
    value = data["value"] if "value" in data else data.get("new_value")

    order = db.query(Order).filter_by(id=order_id).first()
    if not order:
        return jsonify({"success": False, "message": "유효하지 않은 주문입니다."}), 404

    status_snapshot = getattr(order, "status", None)

    user = get_user_by_id(session.get("user_id")) if session.get("user_id") else None
    if not user:
        return jsonify({"success": False, "message": "로그인이 필요합니다."}), 401

    date_fields = ("measurement_date", "scheduled_date")
    if field in date_fields:
        if not can_edit_erp(user):
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "실측일/시공일 수정 권한이 없습니다. (영업, 라홈, 하우드, CS팀만 가능)",
                    }
                ),
                403,
            )
    elif user.role not in ("ADMIN", "MANAGER", "STAFF"):
        return jsonify({"success": False, "message": "이 작업을 수행할 권한이 없습니다."}), 403

    if field not in ORDER_UPDATE_ALLOWED_FIELDS:
        return (
            jsonify({"success": False, "message": f"허용되지 않은 필드입니다: {field}"}),
            400,
        )

    # AS 완료/취소는 상태축 전이라 generic 쓰기 경로로 내려보내지 않는다(STATE-AS-01).
    if field == "as_completed_date":
        return _bridge_as_completed_date(db, order, user, value, data)

    # STATE-AS-01: 열린 AS 건이 있으면 물류 축 status 쓰기가 AS 투영을 못 덮는다.
    # 지방 보드 체크리스트 자동 승격이 SCHEDULED/MEASURED 를 쏴서 AS 접수 건이 지방 AS
    # 섹션과 ERP AS 뱃지에서 통째로 사라졌다(2026-09-03 운영 #4796·#4816).
    # 403 이 아니라 무시다 — 실패 배너는 .alert 자동닫힘에 지워져 무음 실패가 되고,
    # 체크리스트 저장 자체는 정상 업무다. 응답에는 실제 저장값(현재 status)을 싣는다.
    if field == "status" and as_overlay_outranks_status_write(order, value):
        return jsonify(_build_order_update_response(
            order, "status", getattr(order, "status", None),
            getattr(order, "structured_data", None) or {},
        ))

    try:
        if field == "construction_type":
            normalized_construction_type = normalize_regional_construction_type(value)
            if str(value or "").strip() and not normalized_construction_type:
                raise ValueError("시공 구분은 하우드 시공 또는 협력사 시공만 가능합니다.")
            if not getattr(order, "is_regional", False) and normalized_construction_type:
                raise ValueError("비지방 주문에는 지방주문 구분을 저장할 수 없습니다.")
            if getattr(order, "is_regional", False) and not normalized_construction_type:
                raise ValueError("지방주문 구분(하우드/협력사)을 선택해주세요.")
            value = normalized_construction_type or None

        is_erp_order = is_erp_order_record(order)
        # AUDIT-GAP-01: canonical 전이는 아래 old_sd_snapshot 보다 **먼저** workflow.stage 를
        # 바꾼다. 원장 비교의 기준은 요청 진입 시점 값이어야 하므로 status 경로만 미리 떠 둔다
        # (다른 필드는 전이가 없어 old_sd_snapshot 과 같다 — 헛 deepcopy 를 하지 않는다).
        ledger_base_sd: dict[str, Any] | None = (
            copy.deepcopy(getattr(order, "structured_data", None) or {})
            if field == "status" and is_erp_order else None
        )
        status_transitioned = False
        if field == "status" and is_erp_order:
            from foms.services.orders.status_constants import is_logistics_board_status
            from foms.services.orders.stage_override import (
                OVERRIDE_BLOCK_MESSAGE,
                current_stage_for_order,
                normalize_main_stage,
                requires_privileged_override,
            )

            # 물류 보드 목표 상태(설치예정·완료·AS 등)는 stage-override 가드 제외.
            if not is_logistics_board_status(value):
                if requires_privileged_override(current_stage_for_order(order), value):
                    return jsonify({"success": False, "message": OVERRIDE_BLOCK_MESSAGE}), 403

            # STATE-LEGACY-01: 순수 메인 파이프라인 전이는 canonical 전이 엔진 경유
            # (direct order.status/workflow.stage 배정 없음). 물류/AS/overlay 타깃과 overlay
            # 혼재 주문은 should_canonicalize_main_status 가 False → 아래 legacy 경로 보존.
            from foms.api.orders.status import (
                apply_canonical_main_stage,
                should_canonicalize_main_status,
            )

            if should_canonicalize_main_status(order, value):
                err = apply_canonical_main_stage(
                    db, order, normalize_main_stage(value),
                    actor_user_id=getattr(user, "id", None), body=data,
                )
                if err is not None:
                    return err
                status_transitioned = True

        structured_data: dict[str, Any] = {}
        structured_changed = False
        old_sd_snapshot: dict[str, Any] = {}
        if is_erp_order or field in STRUCTURED_SYNC_FIELDS:
            structured_data = _load_order_structured_data_for_update(order)
            old_sd_snapshot = copy.deepcopy(structured_data)

        old_value = getattr(order, field, None)
        # AS 타임라인 system 이벤트 문구(있으면 아래에서 1건 append). AS 방문일·완료일의
        # **정본 쓰기 경로가 여기**다 — 전용 /as/schedule·/as/complete 라우트는 UI 호출자가
        # 없어서, 거기에만 배선하면 실사용 타임라인에는 아무 것도 안 남는다.
        as_system_event = ""
        prod_notif = None
        prod_notif_created = False
        _prod_cons_change: tuple[Any, Any] | None = None
        if field == "as_visit_date":
            pass
        elif field in (
            "as_visit_availability",
            "as_pending",
            "as_blueprint",
            "sales_delivery",
            "construction_workers",
        ):
            pass
        else:
            if not status_transitioned:
                setattr(order, field, value)

        if (
            field == "status"
            and is_erp_order
            and isinstance(structured_data, dict)
            and not status_transitioned
        ):
            from foms.services.orders.status_constants import (
                should_sync_workflow_stage_on_status,
            )

            # SCHEDULED 등 물류 중간상태는 workflow.stage를 오염시키지 않는다.
            if should_sync_workflow_stage_on_status(value):
                workflow = ensure_path(structured_data, "workflow")
                workflow["stage"] = value
                workflow["stage_updated_at"] = now_utc_naive().isoformat()
                structured_changed = True

        if is_erp_order or field in (
            "as_visit_date",
            "as_visit_availability",
            "as_pending",
            "as_blueprint",
            "sales_delivery",
        ):
            if field == "as_pending":
                shipment = ensure_path(structured_data, "shipment")
                shipment["as_pending"] = _coerce_bool_value(value)
                structured_changed = True
            elif field == "as_blueprint":
                shipment = ensure_path(structured_data, "shipment")
                shipment["as_blueprint"] = _coerce_bool_value(value)
                structured_changed = True
            elif field == "sales_delivery":
                shipment = ensure_path(structured_data, "shipment")
                shipment["sales_delivery"] = _coerce_bool_value(value)
                structured_changed = True
            elif field == "construction_workers":
                shipment = ensure_path(structured_data, "shipment")
                shipment["construction_workers"] = _normalize_construction_workers_value(value)
                structured_changed = True
            elif field == "manager_name":
                clean_value = clean_dict_like_name(value)
                setattr(order, "manager_name", clean_value)
                parties = ensure_path(structured_data, "parties")
                manager = ensure_path(parties, "manager")
                manager["name"] = clean_value
                structured_changed = True
            elif field == "measurement_date":
                schedule = ensure_path(structured_data, "schedule")
                measurement = ensure_path(schedule, "measurement")
                measurement["date"] = value
                structured_changed = True
            elif field == "scheduled_date":
                schedule = ensure_path(structured_data, "schedule")
                construction = ensure_path(schedule, "construction")
                old_cons = (
                    (old_sd_snapshot.get("schedule") or {}).get("construction") or {}
                ).get("date")
                construction["date"] = value
                structured_changed = True
                # CONSTRUCTION_DATE_CHANGED OrderEvent 는 여기서 남기지 않는다 — 시공일
                # 이벤트 SSOT 는 foms/services/order_date_sync.py 의 전역 before_flush 훅
                # (모든 쓰기 경로가 통과하는 유일 지점). 여기 남은 비교는 생산팀 벨 알림
                # 트리거 전용이다.
                if old_cons != value:
                    _prod_cons_change = (old_cons, value)
            elif field == "as_visit_date":
                trimmed = str(value or "").strip()
                normalized_visit = _normalize_date_to_yyyymmdd(trimmed) if trimmed else None
                # 정규화 실패는 여기서 끊는다(쓰기 전). 통과시키면 as_visit_date 컬럼에 None 이
                # 박히고 「방문일 확정: None」 이 append-only as_log 에 영구히 남는다.
                if trimmed and not normalized_visit:
                    return jsonify(
                        {"success": False, "message": "방문일 형식이 올바르지 않습니다. (YYYY-MM-DD)"}
                    ), 400
                schedule = ensure_path(structured_data, "schedule")
                as_visit = ensure_path(schedule, "as_visit")
                # 이전 값의 정본은 structured_data 스냅샷이다 — as_visit_date 는 ORM 컬럼이
                # 아니라(표시 전용 인스턴스 속성) getattr 로는 항상 None 이 잡힌다.
                old_visit = (
                    (old_sd_snapshot.get("schedule") or {}).get("as_visit") or {}
                ).get("date")
                as_visit["date"] = value
                structured_changed = True
                setattr(order, "as_visit_date", normalized_visit)
                if _as_date_changed(old_visit, value):
                    as_system_event = (
                        f"방문일 확정: {normalized_visit}" if trimmed else "방문일 취소"
                    )
            elif field == "as_visit_availability":
                from foms.services.orders.as_availability import (
                    as_availability_label,
                    normalize_as_availability,
                )
                # 값 오류는 ValueError → 409 경로(쓰기 전 차단)
                normalized_avail = normalize_as_availability(value)
                schedule = ensure_path(structured_data, "schedule")
                as_visit = ensure_path(schedule, "as_visit")
                old_avail = (
                    (old_sd_snapshot.get("schedule") or {}).get("as_visit") or {}
                ).get("availability")
                if normalized_avail is None:
                    as_visit.pop("availability", None)
                else:
                    as_visit["availability"] = normalized_avail
                structured_changed = True
                if (old_avail or None) != normalized_avail:
                    as_system_event = (
                        f"가능시간: {as_availability_label(normalized_avail)}"
                        if normalized_avail else "가능시간 초기화"
                    )
                value = normalized_avail  # 응답/접근로그 에코를 정규화 값으로

        if is_erp_order and field in ("as_received_date", "as_visit_date"):
            if _clear_as_pending_if_both_as_dates_empty(order, structured_data):
                structured_changed = True

        # 값이 실제로 바뀐 경우에만 1건. structured_changed 를 켜야 아래 저장 블록이 돈다
        # (as_completed_date 는 비-ERP 주문에서 이 플래그가 꺼진 채로 올 수 있다).
        if as_system_event and isinstance(structured_data, dict):
            append_system_log(structured_data, text=as_system_event)
            structured_changed = True

        if structured_changed:
            drawing_notif = None
            drawing_notif_created = False
            if field in ("measurement_date", "scheduled_date", "construction_type") or field == "address":
                try:
                    from foms.services.notifications.drawing_order_change import (
                        apply_drawing_order_change_alert,
                    )
                    drawing_notif, drawing_notif_created = apply_drawing_order_change_alert(
                        db,
                        order,
                        old_sd_snapshot,
                        structured_data,
                        actor_user_id=getattr(user, "id", None),
                        actor_name=getattr(user, "name", None) or session.get("username") or "SYSTEM",
                        old_notes=getattr(order, "notes", None),
                        new_notes=getattr(order, "notes", None),
                        old_is_regional=getattr(order, "is_regional", None),
                        new_is_regional=getattr(order, "is_regional", None),
                        old_construction_type=(
                            old_value if field == "construction_type" else getattr(order, "construction_type", None)
                        ),
                        new_construction_type=getattr(order, "construction_type", None),
                    )
                except Exception:
                    current_app.logger.warning(
                        "drawing order-change alert failed on field_update",
                        exc_info=True,
                    )
            if _prod_cons_change is not None:
                try:
                    from foms.services.notifications.production_change import (
                        apply_production_change_alert,
                    )
                    from foms.services.production_change_alerts import _date_to_md

                    _pc_from, _pc_to = _prod_cons_change
                    prod_notif, prod_notif_created = apply_production_change_alert(
                        db,
                        order,
                        "construction_date",
                        f"{_date_to_md(_pc_from)} → {_date_to_md(_pc_to)}",
                        actor_user_id=getattr(user, "id", None),
                        actor_name=getattr(user, "name", None) or session.get("username") or "SYSTEM",
                    )
                except Exception:
                    current_app.logger.warning(
                        "production change alert failed on field_update",
                        exc_info=True,
                    )
            setattr(order, "structured_data", structured_data)
            flag_modified(order, "structured_data")
            sync_erp_flat_columns(order, structured_data)
        else:
            drawing_notif = None
            drawing_notif_created = False

        # AUDIT-GAP-01: 보안로그에만 남던 before/after 를 변경 원장에도 싣는다. sd 를 실제로
        # 바꾼 필드는 diff_structured 를 태워 ERP 폼 저장(PUT)과 **같은 점 경로**로 남기고,
        # 평면 컬럼만 바꾼 필드는 점 없는 컬럼명으로 남긴다(경로 매핑표는 파일 상단).
        # 원장 행은 아래 db.commit() 과 같은 트랜잭션에 실린다.
        ledger_changes: list[dict[str, Any]] = []
        if structured_data:
            ledger_changes.extend(diff_structured(
                ledger_base_sd if ledger_base_sd is not None else old_sd_snapshot,
                structured_data,
                max_changes=-1,
            ).changes)
        flat_change = _ledger_flat_change(
            order, field, status_snapshot if field == "status" else old_value
        )
        if flat_change is not None:
            twin_path = _LEDGER_SD_TWIN.get(field)
            if twin_path is None or twin_path not in {c.get("path") for c in ledger_changes}:
                ledger_changes.append(flat_change)
        change_set_id = str(uuid.uuid4())
        recorded_rows = record_field_changes(
            db, ledger_changes,
            order_id=int(order.id),
            actor_user_id=session.get("user_id"),
            change_set_id=change_set_id,
        )

        # 변경 전 값을 함께 남긴다 — "무엇에서 무엇으로"가 없으면 되돌릴 수도 따질 수도 없다
        # (운영 실측: as_completed_date 를 ''로 바꾼 97건이 '원래 언제였는지' 없이 남았다).
        audit_context = order_audit_context(order)
        audit_detail = {
            "field": field,
            "before": old_value,
            "after": value,
            # 관리자 감사 화면이 detail->>'change_set' 으로 원장과 조인한다. 행이 0건이어도
            # **무조건** 넣는다(2026-08-26 통일) — 조인 키가 있어야 감사 화면에서 원장으로
            # 넘어가는 길이 항상 열리고, "헤더는 있는데 행이 0" 은 변경 없음을 뜻하는
            # 정상 상태다. edit.py·regional.py·settings.py·storage.py 와 같은 규약.
            "change_set": change_set_id,
            "change_count": recorded_rows,
            **audit_context,
        }
        log_access(
            describe_field_change(
                order_id=order.id, field=field, before=old_value, after=value,
                has_before=True, **audit_context,
            ),
            session["user_id"],
            auto_commit=False,
            action="ORDER_STATUS_CHANGED" if field == "status" else "ORDER_FIELD_UPDATED",
            target_type="order", target_id=order.id,
            detail=audit_detail,
        )

        db.commit()

        # 실측 예약 알림톡 자동 발송 — 커밋 성공 이후에만. 여기서 실측 일정을 건드리는
        # 필드는 measurement_date 하나뿐이라 그때만 부른다(다른 필드는 자격 판정이 어차피
        # 거르므로 무해하지만 DB 왕복만 늘린다). 서비스가 내부에서 예외를 흡수한다.
        # import 는 이 파일의 다른 부수효과들과 같은 함수 로컬 방식 — 모듈 상단에 넣으면
        # REV-99 writer 인벤토리가 핀한 EXTERNAL writer 라인번호가 밀린다.
        if field == "measurement_date":
            from foms.services.kakao_alimtalk import maybe_send_measure_alimtalk

            maybe_send_measure_alimtalk(order.id)

        if structured_changed:
            try:
                from foms.services.notifications.drawing_order_change import (
                    finalize_drawing_order_change_alert,
                )
                finalize_drawing_order_change_alert(
                    db, drawing_notif, created_new=drawing_notif_created
                )
            except Exception:
                current_app.logger.warning(
                    "drawing order-change finalize failed on field_update",
                    exc_info=True,
                )
            try:
                from foms.services.notifications.production_change import (
                    finalize_production_change_alert,
                )
                finalize_production_change_alert(
                    db, prod_notif, created_new=prod_notif_created
                )
            except Exception:
                current_app.logger.warning(
                    "production change finalize failed on field_update",
                    exc_info=True,
                )

        inv_fields = {
            "as_visit_date",
            "status",
            "address",
            "manager_name",
            "sales_delivery",
            "construction_workers",
            "construction_type",
            # 날짜 필드: 캐시 DTO가 날짜 기준으로 구성되는 대시보드(실측 main_rows
            # order_ids, 출고/시공 버킷, 히스토리)가 있어 편집 시 무효화 필수.
            "measurement_date",
            "scheduled_date",
            "shipping_scheduled_date",
            "completion_date",
        }
        # AS 관련 상태에서의 편집은 status_snapshot 기준으로도 무효화가 걸린다.
        as_context = status_snapshot in ("AS", "AS_RECEIVED", "AS_COMPLETED")
        if field in inv_fields or as_context:
            try:
                from foms.services.common.dashboard_cache import (
                    DASHBOARD_FAMILY_CONSTRUCTION,
                    DASHBOARD_FAMILY_HISTORY,
                    DASHBOARD_FAMILY_MEASUREMENT,
                    DASHBOARD_FAMILY_SHIPMENT,
                    invalidate_all_dashboard_slice_caches,
                    invalidate_order_dashboard_families,
                )
                from foms.services.shipment_as_recommendation_cache import (
                    invalidate_shipment_as_recommendation_cache,
                )

                # Tier C(단일 필드): status 변경/AS 문맥은 탭 이동을 유발할 수 있어 broad.
                # 그 외 필드는 orders + 주문 현재 단계 family + 필드가 캐시 DTO에
                # 등장하는 family(extra)만 무효화한다(근거: 각 read-model DTO 정독).
                if field == "status" or as_context:
                    invalidate_all_dashboard_slice_caches()
                else:
                    extras_by_field = {
                        # 출고 대시보드 DTO(aggregates·AS 추천 행)가 읽는 필드
                        "as_visit_date": (DASHBOARD_FAMILY_SHIPMENT,),
                        "sales_delivery": (DASHBOARD_FAMILY_SHIPMENT,),
                        "construction_workers": (DASHBOARD_FAMILY_SHIPMENT,),
                        # 날짜 필드 → 날짜 기준 DTO를 가진 family
                        "measurement_date": (DASHBOARD_FAMILY_MEASUREMENT,),
                        "scheduled_date": (
                            DASHBOARD_FAMILY_SHIPMENT,
                            DASHBOARD_FAMILY_CONSTRUCTION,
                        ),
                        "shipping_scheduled_date": (DASHBOARD_FAMILY_SHIPMENT,),
                        "completion_date": (DASHBOARD_FAMILY_HISTORY,),
                    }
                    extra = extras_by_field.get(field, ())
                    invalidate_order_dashboard_families(order, extra=extra)
                invalidate_shipment_as_recommendation_cache(reason=f"field_update:{field}")
            except Exception:
                current_app.logger.warning(
                    "[AS-REC] post field_update cache invalidate failed",
                    exc_info=True,
                )

        return jsonify(_build_order_update_response(order, field, value, structured_data))
    except ValueError as exc:
        db.rollback()
        current_app.logger.warning(f"주문 #{order_id} 필드 업데이트 중단: {str(exc)}")
        return jsonify({"success": False, "message": str(exc)}), 409
    except Exception as exc:
        db.rollback()
        current_app.logger.error(f"주문 #{order_id} 필드 업데이트 실패: {str(exc)}")
        return (
            jsonify({"success": False, "message": f"오류 발생: {str(exc)}"}),
            500,
        )


__all__ = [
    "ORDER_UPDATE_ALLOWED_FIELDS",
    "STRUCTURED_SYNC_FIELDS",
    "ensure_path",
    "update_order_field_response",
]
