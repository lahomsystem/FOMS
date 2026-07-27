"""
ERP 주문 AS(설치) API. (Phase 4-5h)
erp.py에서 분리: as/start, as/complete, as/schedule.
"""
import copy
import datetime
from foms.services.datetime_kst import now_utc_naive
import logging

from flask import Blueprint, jsonify, render_template, request, session
from sqlalchemy.orm.attributes import flag_modified

from foms.web.auth import get_user_by_id, login_required
from db import get_db
from foms.services.as_content_safety import (
    load_structured_data_dict_or_raise,
    sanitize_as_content_html,
)
from foms.services.erp_display import get_today_kst
from foms.services.erp_permissions import erp_construction_edit_required, erp_edit_required
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.erp_utils import ensure_path
from foms.services.orders.as_log import (
    AS_LOG_TEXT_MAX,
    append_client_log,
    append_system_log,
    coerce_client_log_type,
    decorate_entry,
    migrate_legacy_into_log,
)
from models import Order, OrderEvent, SecurityLog

logger = logging.getLogger(__name__)

erp_orders_as_bp = Blueprint(
    "erp_orders_as",
    __name__,
    url_prefix="/api/orders",
)


def _invalidate_shipment_asrec_caches(reason: str) -> None:
    """Dashboard + shipment AS recommendation cache bust (commit-after, best-effort).

    Tier A(broad): AS start/complete/register 는 order.status(AS↔CS↔AS_RECEIVED)와
    workflow.stage_updated_at 를 바꿔 여러 탭(주문/시공/완료/출고 추천) 사이 이동을
    유발하므로 전체 무효화를 유지한다.
    """
    try:
        from foms.services.common.dashboard_cache import invalidate_all_dashboard_slice_caches

        invalidate_all_dashboard_slice_caches()
    except Exception:
        logger.warning("[AS-REC] dashboard cache invalidate failed (%s)", reason, exc_info=True)
    try:
        from foms.services.shipment_as_recommendation_cache import (
            invalidate_shipment_as_recommendation_cache,
        )

        invalidate_shipment_as_recommendation_cache(reason=reason)
    except Exception:
        logger.warning("[AS-REC] shipment asrec cache invalidate failed (%s)", reason, exc_info=True)


def _load_order_structured_data_for_update(order):
    """structured_data가 안전할 때만 AS 쓰기 작업 진행."""
    try:
        return load_structured_data_dict_or_raise(getattr(order, "structured_data", None))
    except ValueError as exc:
        raise ValueError(
            f"structured_data를 안전하게 불러올 수 없어 저장을 중단했습니다: {exc}"
        ) from exc


def _confirmed_construction_worker_name(user) -> str:
    """Return the construction worker name confirmed by the AS register actor."""
    if not user:
        return ""
    return str(
        getattr(user, "name", None) or getattr(user, "username", None) or ""
    ).strip()


_AS_BILLING_TYPES = ("free", "paid", "undecided")
# 타임라인 system 문구용 표기. 최초 판정과 전환은 **다른 사건**이라 어휘를 분리한다
# (기본값 free 를 이전 판정으로 읽어 첫 유상 확정을 "무상→유상 전환"으로 남기면 감사 기록 오기).
_AS_BILLING_LABELS = {"free": "무상", "paid": "유상", "undecided": "미정"}
_AS_BILLING_FIRST_EVENTS = {"free": "무상 확정", "paid": "유상 확정", "undecided": "미정 처리"}


def _default_as_billing() -> dict[str, object]:
    """as_billing 기본값(무상 추정·미확정)."""
    return {
        "type": "free",
        "confirmed": False,
        "amount": None,
        "reason": "",
        "decided_by": "",
        "decided_at": "",
    }


def _coerce_billing_type(raw: object) -> str:
    """billing 유형을 허용 enum으로 정규화. 미허용/빈값은 'free'."""
    value = str(raw or "").strip().lower()
    return value if value in _AS_BILLING_TYPES else "free"


def _coerce_billing_amount(raw: object) -> int | None:
    """금액을 0 이상 정수 또는 None으로 정규화. 음수/비정수는 ValueError."""
    if raw in (None, ""):
        return None
    try:
        amount = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("금액은 정수여야 합니다.") from exc
    if amount < 0:
        raise ValueError("금액은 0 이상이어야 합니다.")
    return amount


def _write_as_billing(sd: dict, *, billing_type: str, amount: int | None,
                      confirmed: bool, reason: str, user) -> dict:
    """sd['shipment']['as_billing']를 기존값 병합 후 갱신하고 반환."""
    shipment = ensure_path(sd, "shipment")
    billing = _default_as_billing()
    existing = shipment.get("as_billing")
    if isinstance(existing, dict):
        billing.update(existing)
    billing["type"] = billing_type
    billing["amount"] = amount
    billing["confirmed"] = bool(confirmed)
    if reason:
        billing["reason"] = reason
    billing["decided_by"] = (user.name if user else "") or ""
    billing["decided_at"] = now_utc_naive().isoformat()
    shipment["as_billing"] = billing
    return billing


@erp_orders_as_bp.route("/<int:order_id>/as/start", methods=["POST"])
@login_required
@erp_edit_required
def api_as_start(order_id):
    """AS 시작 (CS 단계에서 AS가 필요한 경우)"""
    db = get_db()
    try:
        order = db.get(Order, order_id)
        if not order or order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404

        data = request.get_json() or {}
        as_reason = data.get("reason", "")
        as_description = data.get("description", "")

        user_id = session.get("user_id")
        user = get_user_by_id(user_id)

        sd = _load_order_structured_data_for_update(order)
        wf = sd.get("workflow") or {}

        as_info = sd.get("as_info") or []
        as_entry = {
            "id": len(as_info) + 1,
            "started_at": now_utc_naive().isoformat(),
            "started_by": user.name if user else "Unknown",
            "reason": as_reason,
            "description": as_description,
            "status": "OPEN",
            "visit_date": None,
            "completed_at": None,
        }
        as_info.append(as_entry)
        sd["as_info"] = as_info

        wf["stage"] = "AS"
        wf["stage_updated_at"] = now_utc_naive().isoformat()
        wf["stage_updated_by"] = user.name if user else "Unknown"

        hist = wf.get("history") or []
        hist.append({
            "stage": "AS",
            "updated_at": wf["stage_updated_at"],
            "updated_by": wf["stage_updated_by"],
            "note": f"AS 시작: {as_reason}",
        })
        wf["history"] = hist
        sd["workflow"] = wf

        order.structured_data = sd
        flag_modified(order, "structured_data")
        order.status = "AS"
        sync_erp_flat_columns(order, sd)

        event_payload = {
            "domain": "AS_DOMAIN",
            "action": "AS_STARTED",
            "target": "workflow.stage",
            "before": "CS",
            "after": "AS",
            "change_method": "API",
            "source_screen": "erp_cs_dashboard",
            "reason": f"AS 시작: {as_reason}",
            "as_id": as_entry["id"],
            "as_description": as_description,
        }
        db.add(OrderEvent(
            order_id=order_id,
            event_type="AS_STARTED",
            payload=event_payload,
            created_by_user_id=user_id,
        ))
        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} AS 시작: {as_reason}"))
        db.commit()
        _invalidate_shipment_asrec_caches("api_as_start")

        return jsonify({
            "success": True,
            "message": "AS가 시작되었습니다.",
            "new_status": "AS",
            "as_id": as_entry["id"],
        })
    except ValueError as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)}), 409
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


@erp_orders_as_bp.route("/<int:order_id>/as/complete", methods=["POST"])
@login_required
@erp_edit_required
def api_as_complete(order_id):
    """AS 완료 -> CS 복귀"""
    db = get_db()
    try:
        order = db.get(Order, order_id)
        if not order or order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404

        data = request.get_json() or {}
        as_id = data.get("as_id")
        completion_note = data.get("note", "")

        user_id = session.get("user_id")
        user = get_user_by_id(user_id)

        sd = _load_order_structured_data_for_update(order)
        wf = sd.get("workflow") or {}

        as_info = sd.get("as_info") or []
        for entry in as_info:
            if isinstance(entry, dict) and (entry.get("id") == as_id or as_id is None):
                if entry.get("status") == "OPEN":
                    entry["status"] = "COMPLETED"
                    entry["completed_at"] = datetime.datetime.now().isoformat()
                    entry["completed_by"] = user.name if user else "Unknown"
                    entry["completion_note"] = completion_note
                    break
        sd["as_info"] = as_info

        wf["stage"] = "CS"
        wf["stage_updated_at"] = now_utc_naive().isoformat()
        wf["stage_updated_by"] = user.name if user else "Unknown"

        hist = wf.get("history") or []
        hist.append({
            "stage": "CS",
            "updated_at": wf["stage_updated_at"],
            "updated_by": wf["stage_updated_by"],
            "note": "AS 완료 -> CS 복귀",
        })
        wf["history"] = hist
        sd["workflow"] = wf

        append_system_log(sd, text="AS 완료")

        order.structured_data = sd
        flag_modified(order, "structured_data")
        order.status = "CS"
        sync_erp_flat_columns(order, sd)

        event_payload = {
            "domain": "AS_DOMAIN",
            "action": "AS_COMPLETED",
            "target": "workflow.stage",
            "before": "AS",
            "after": "CS",
            "change_method": "API",
            "source_screen": "erp_as_dashboard",
            "reason": "AS 완료 -> CS 복귀",
            "as_id": as_id,
            "completion_note": completion_note,
        }
        db.add(OrderEvent(
            order_id=order_id,
            event_type="AS_COMPLETED",
            payload=event_payload,
            created_by_user_id=user_id,
        ))
        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} AS 완료 -> CS 복귀"))
        db.commit()
        _invalidate_shipment_asrec_caches("api_as_complete")

        return jsonify({"success": True, "message": "AS가 완료되었습니다.", "new_status": "CS"})
    except ValueError as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)}), 409
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


@erp_orders_as_bp.route("/<int:order_id>/as/register", methods=["POST"])
@login_required
@erp_construction_edit_required
def api_as_register(order_id):
    """AS 접수 등록: 시공 대시보드에서 AS 이미지 업로드 후 호출. as_content 저장, 접수일=오늘, status=AS_RECEIVED."""
    db = get_db()
    try:
        order = db.get(Order, order_id)
        if not order or order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404

        data = request.get_json(silent=True) or {}
        try:
            # 파싱 전 원문 크기 선가드. register 는 자체 sanitize 가 먼저라 _clean_as_log_text
            # 안의 선가드만으로는 거대 페이로드가 이미 한 번 파싱된 뒤다.
            _guard_as_log_raw_size(data.get("as_content"))
            as_content = sanitize_as_content_html(data.get("as_content"))
            if as_content:
                # 접수 원문도 reception 로그가 되므로 quick-add와 같은 본문 캡을 지나야 한다
                # (안 그러면 register가 AS_LOG_TEXT_MAX 우회로가 된다). 빈 값은 register 계약상 허용.
                as_content = _clean_as_log_text(as_content)
        except ValueError as ve:
            return jsonify({"success": False, "message": str(ve)}), 400
        source_screen = str(data.get("source_screen") or "").strip()

        # 지방주문 AS 재상차용 상차일(optional). 값이 있으면 YYYY-MM-DD 검증 후 컬럼에 저장.
        # 지방주문 + 미래 상차일이면 지방 대시보드가 자동으로 "상차 예정 알림"으로 승격한다
        # (foms/web/measurement/dashboard.py shipping_alerts 버킷 + AS 뱃지).
        raw_shipping_scheduled_date = str(data.get("shipping_scheduled_date") or "").strip()
        if raw_shipping_scheduled_date:
            try:
                datetime.datetime.strptime(raw_shipping_scheduled_date, "%Y-%m-%d")
            except ValueError:
                raise ValueError("상차일 형식이 올바르지 않습니다. (YYYY-MM-DD)")

        today = get_today_kst().strftime("%Y-%m-%d")
        user_id = session.get("user_id")
        user = get_user_by_id(user_id)
        sd = _load_order_structured_data_for_update(order)
        old_sd = copy.deepcopy(sd)
        shipment = ensure_path(sd, "shipment")
        # 덮어쓰기 전에 이전 원문을 legacy로 굳힌다. append_client_log도 같은 마이그레이션을
        # 하지만 그건 원문이 **있을 때만** 돈다 — 빈 원문 재접수는 append가 없어 아래
        # `shipment["as_content"] = ""`가 이전 기록을 보존 없이 지웠다(멱등: 이미 as_log가
        # 있으면 no-op).
        migrate_legacy_into_log(sd)
        # 접수 원문을 첫 reception 항목으로 남긴다. as_content 덮어쓰기보다 **앞**이어야 한다 —
        # 위 마이그레이션이 shipment["as_content"]를 legacy로 굳히므로, 뒤에 두면 방금 쓴
        # 접수 원문이 legacy(이전 기록)로 중복 시드된다.
        #
        # 재접수 모달은 기존 as_content 를 프리필한다(erp-order-shared.js) — 무편집 제출이면
        # 같은 본문이 그대로 돌아온다. 그 본문은 직전 reception 또는 방금 굳힌 legacy 로 이미
        # 로그에 있으므로 append 하면 append-only 리스트에 영구 중복이 남는다. "as_content 가
        # 그대로 + 같은 본문이 로그에 이미 존재" 둘 다일 때만 건너뛴다(내용을 실제로 고쳤거나
        # 로그에 없는 원문이면 정상 append). 접수 "사실"은 아래 system 이벤트가 계속 남긴다.
        already_logged = bool(as_content) and as_content == shipment.get("as_content") and any(
            isinstance(e, dict) and e.get("text") == as_content
            for e in (shipment.get("as_log") or [])
        )
        if as_content and not already_logged:
            append_client_log(
                sd, log_type="reception", text=as_content,
                by=(user.name if user else ""), by_id=(user.id if user else None))
        # 접수 원문(수기 reception)과 별개로 접수 "사실"을 이벤트로 남긴다 — 원문 없이
        # 접수만 하는 흐름에서도 타임라인 첫 줄이 비지 않는다.
        append_system_log(sd, text="AS 접수됨")
        shipment["as_content"] = as_content
        # 최초 접수에서만 billing을 시드한다. 재접수(지방 재상차 등)는 정상 흐름이므로
        # 기존 billing을 덮으면 확정된 유상 금액이 free/미확정으로 되돌아간다.
        # 확정·전환은 전용 API 소관(스펙 §3.2).
        if not isinstance(shipment.get("as_billing"), dict):
            billing_type = _coerce_billing_type(data.get("billing_type") or "free")
            billing_amount = _coerce_billing_amount(data.get("amount")) if billing_type == "paid" else None
            billing = _default_as_billing()
            billing["type"] = billing_type
            billing["amount"] = billing_amount
            shipment["as_billing"] = billing
        construction_worker_name = _confirmed_construction_worker_name(user)
        if source_screen == "erp_construction_dashboard" and construction_worker_name:
            shipment["construction_workers"] = [construction_worker_name]
        wf = sd.get("workflow") or {}
        wf["stage"] = "AS_RECEIVED"
        wf["stage_updated_at"] = now_utc_naive().isoformat()
        wf["stage_updated_by"] = user.name if user else "Unknown"
        sd["workflow"] = wf

        order.as_received_date = today
        order.status = "AS_RECEIVED"
        # 상차일이 제공되면(지방주문 AS 재상차) 컬럼에 반영. 빈 값/미제공이면 기존값 보존.
        if raw_shipping_scheduled_date:
            order.shipping_scheduled_date = raw_shipping_scheduled_date

        # /add draft 주문은 structured PUT 없이 AS 모달만 완료하는 경우가 많다.
        # draft meta가 남으면 Order.active_filter()에서 제외되어 AS 탭에 보이지 않는다.
        from foms.api.erp_orders_structured import _finalize_draft_state

        # meta['finalized_at']로 JSONB에 남는 값 — naive 타임스탬프는 UTC 규약(전역 규약 2).
        now = now_utc_naive()
        draft_cleared = _finalize_draft_state(order, sd, now, old_sd)
        order.structured_data = sd
        flag_modified(order, "structured_data")
        sync_erp_flat_columns(order, sd)

        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} AS 접수 등록 (접수일: {today})"))
        db.commit()
        _invalidate_shipment_asrec_caches("api_as_register")

        return jsonify({
            "success": True,
            "message": "AS 접수가 등록되었습니다.",
            "as_received_date": today,
            "new_status": "AS_RECEIVED",
            "shipping_scheduled_date": getattr(order, "shipping_scheduled_date", None) or "",
            "construction_workers": shipment.get("construction_workers") or [],
            "draft_cleared": draft_cleared,
        })
    except ValueError as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)}), 409
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


@erp_orders_as_bp.route("/<int:order_id>/as/schedule", methods=["POST"])
@login_required
@erp_edit_required
def api_as_schedule(order_id):
    """AS 방문일 확정"""
    db = get_db()
    try:
        order = db.get(Order, order_id)
        if not order or order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404

        data = request.get_json() or {}
        as_id = data.get("as_id")
        visit_date = data.get("visit_date")
        visit_time = data.get("visit_time", "")

        if not visit_date:
            return jsonify({"success": False, "message": "방문일을 입력해주세요."}), 400
        try:
            # 저장 전 형식 검증(register의 shipping_scheduled_date와 동일 패턴). 검증 없이
            # 두면 임의 문자열이 schedule.as_visit.date와 영구 타임라인 문구로 함께 굳는다.
            datetime.datetime.strptime(str(visit_date), "%Y-%m-%d")
        except ValueError:
            return jsonify({
                "success": False, "message": "방문일 형식이 올바르지 않습니다. (YYYY-MM-DD)"}), 400

        user_id = session.get("user_id")
        user = get_user_by_id(user_id)

        sd = _load_order_structured_data_for_update(order)

        as_info = sd.get("as_info") or []
        for entry in as_info:
            if isinstance(entry, dict) and (entry.get("id") == as_id or as_id is None):
                if entry.get("status") == "OPEN":
                    entry["visit_date"] = visit_date
                    entry["visit_time"] = visit_time
                    entry["scheduled_by"] = user.name if user else "Unknown"
                    entry["scheduled_at"] = datetime.datetime.now().isoformat()
                    break
        sd["as_info"] = as_info

        schedule = sd.get("schedule") or {}
        as_visit = schedule.get("as_visit") or {}
        as_visit["date"] = visit_date
        as_visit["time"] = visit_time
        as_visit["type"] = "AS"
        schedule["as_visit"] = as_visit
        sd["schedule"] = schedule

        wf = sd.get("workflow") or {}
        hist = wf.get("history") or []
        hist.append({
            "stage": "AS",
            "updated_at": datetime.datetime.now().isoformat(),
            "updated_by": user.name if user else "Unknown",
            "note": f"AS 방문일 확정: {visit_date}",
        })
        wf["history"] = hist
        sd["workflow"] = wf

        append_system_log(sd, text=f"방문일 확정: {visit_date}")

        order.structured_data = sd
        flag_modified(order, "structured_data")

        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} AS 방문일 확정: {visit_date}"))
        db.commit()
        _invalidate_shipment_asrec_caches("api_as_schedule")

        return jsonify({
            "success": True,
            "message": f"AS 방문일이 {visit_date}로 확정되었습니다.",
            "visit_date": visit_date,
        })
    except ValueError as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)}), 409
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


@erp_orders_as_bp.route("/<int:order_id>/as/billing", methods=["POST"])
@login_required
@erp_edit_required
def api_as_billing(order_id: int):
    """AS 무상/유상 판정 확정·전환. 전환 시 reason 필수."""
    db = get_db()
    try:
        order = db.get(Order, order_id)
        if not order or order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404

        data = request.get_json(silent=True) or {}
        # 확정 API는 관대한 폴백(_coerce_billing_type의 free 강등)을 쓰지 않는다.
        # 오타 하나가 조용히 "무상 확정"으로 굳으면 매출 판정이 바뀐다.
        new_type = str(data.get("type") or "").strip().lower()
        if new_type not in _AS_BILLING_TYPES:
            return jsonify({
                "success": False,
                "message": f"판정 유형이 올바르지 않습니다. ({'/'.join(_AS_BILLING_TYPES)} 중 하나)",
            }), 400
        reason = str(data.get("reason") or "").strip()

        user = get_user_by_id(session.get("user_id"))
        sd = _load_order_structured_data_for_update(order)
        prev = (sd.get("shipment") or {}).get("as_billing")
        prev = prev if isinstance(prev, dict) else {}
        prev_type = str(prev.get("type") or "free")
        if prev.get("confirmed") is True and prev_type != new_type and not reason:
            return jsonify({"success": False, "message": "판정 전환 시 사유는 필수입니다."}), 400

        # amount 키가 없으면 기존 금액을 보존한다(reason 빈값 보존과 대칭).
        # 금액 없이 재확정하는 요청이 확정된 청구액을 지우면 안 된다.
        # 명시적 {"amount": null}은 의도적 삭제 경로로 허용한다.
        if new_type != "paid":
            amount = None
        elif "amount" in data:
            try:
                # 입력 검증 실패는 400. 409는 낙관/무결성 전용(structured_data 로드 실패 등).
                amount = _coerce_billing_amount(data["amount"])
            except ValueError as e:
                return jsonify({"success": False, "message": str(e)}), 400
        else:
            amount = prev.get("amount")

        billing = _write_as_billing(
            sd, billing_type=new_type, amount=amount,
            confirmed=True, reason=reason, user=user,
        )
        # 기준은 **확정 여부**다. type 만 보면 register 가 심은 미확정 추정값이 "이전 판정"으로
        # 둔갑해 첫 확정이 전환으로 기록된다. 확정 상태에서의 동일 유형 재확정(금액만 변경 등)은
        # 무기록 — 타임라인이 노이즈로 찬다. 사유는 사용자 입력이지만 append_system_log가
        # 생성 지점에서 escape·절단한다.
        suffix = f": {reason}" if reason else ""
        if prev.get("confirmed") is not True:
            event = _AS_BILLING_FIRST_EVENTS[new_type]
        elif prev_type != new_type:
            event = (f"{_AS_BILLING_LABELS.get(prev_type, prev_type)}"
                     f"→{_AS_BILLING_LABELS[new_type]} 전환")
        else:
            event = ""
        # 응답 html은 낙관적 DOM 삽입용(재조회 금지). 렌더는 commit 앞 — append/patch와 같은 이유.
        entry_html = _render_as_log_entry(append_system_log(sd, text=f"{event}{suffix}")) if event else ""
        order.structured_data = sd
        flag_modified(order, "structured_data")
        sync_erp_flat_columns(order, sd)
        db.add(SecurityLog(
            user_id=session.get("user_id"),
            message=f"주문 #{order_id} AS 비용 판정: {new_type}"))
        db.commit()
        _invalidate_shipment_asrec_caches("api_as_billing")
        return jsonify({
            "success": True,
            "billing": billing,
            "html": entry_html,          # 타임라인 낙관적 삽입용(없으면 빈 문자열)
            "badge_html": _render_as_billing_badge(billing),  # 상태 셀 배지 교체용
            "state_text": _as_billing_state_text(billing),    # 헤더 현재 판정 표기
        })
    except ValueError as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)}), 409
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


def _render_as_billing_badge(billing: dict) -> str:
    """상태 셀 비용 배지 단건 렌더(목록과 동일 매크로) — 판정 변경 응답의 낙관적 교체용."""
    from foms.services.as_dashboard_display import as_billing_badge_kind

    return render_template(
        "cs/partials/as_billing_badge_partial.html", kind=as_billing_badge_kind(billing)
    ).strip()


def _as_billing_state_text(billing: dict) -> str:
    """타임라인 헤더의 현재 판정 표기(서버 렌더와 같은 SSOT를 응답으로 되돌려준다)."""
    from foms.services.as_dashboard_display import as_billing_state_text

    return as_billing_state_text(billing)


def _render_as_log_entry(entry: dict) -> str:
    """as_log 항목 1건을 목록과 동일한 매크로로 렌더(낙관적 DOM 삽입용)."""
    return render_template(
        "cs/partials/as_timeline_entry_partial.html", entry=decorate_entry(entry)
    )


# AS_LOG_TEXT_MAX(sanitize 통과 **결과**의 상한)는 여기서 import만 한다. as_log는 append-only라
# 항목당 상한이 없으면 sd가 무한히 커지는데(도면 위저드 64KB 캡 선례), 값의 SSOT는 생성 지점인
# as_log 모듈이다 — 사본을 두면 한쪽만 올렸을 때 라우트는 통과시키고 build_as_log_entry가
# 조용히 잘라 사용자가 유실을 모른다.

# AS_LOG_RAW_MAX: 원문(sanitize 전) 상한. 위 결과 상한만 있으면 그때까지 수 MB 페이로드를
# BeautifulSoup 이 전부 파싱한다 — 파싱 자체가 비용이라 진입부에서 먼저 자른다.
# 태그·엔티티 오버헤드를 넉넉히 잡아 결과 상한의 10배.
AS_LOG_RAW_MAX = 100_000


def _guard_as_log_raw_size(raw: object) -> None:
    """sanitize 파싱 **앞**에서 원문 크기를 자른다. 초과는 ValueError(호출부에서 400)."""
    if len(str(raw or "")) > AS_LOG_RAW_MAX:
        raise ValueError("내용이 너무 깁니다.")


def _clean_as_log_text(raw: object) -> str:
    """AS 기록 본문 sanitize + 길이 검증. 위반은 ValueError(호출부에서 400)."""
    _guard_as_log_raw_size(raw)
    text = sanitize_as_content_html(raw)
    if not text:
        raise ValueError("내용을 입력해주세요.")
    if len(text) > AS_LOG_TEXT_MAX:
        raise ValueError("내용이 너무 깁니다.")
    return text


@erp_orders_as_bp.route("/<int:order_id>/as/log", methods=["POST"])
@login_required
@erp_edit_required
def api_as_log_append(order_id: int):
    """AS 타임라인 항목 append. body {type, text}. ts·작성자는 서버가 정한다."""
    db = get_db()
    try:
        order = db.get(Order, order_id)
        if not order or order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404

        data = request.get_json(silent=True) or {}
        try:
            log_type = coerce_client_log_type(data.get("type"))
            text = _clean_as_log_text(data.get("text"))
        except ValueError as ve:
            # 검증 실패는 400. 409는 낙관/무결성 전용(structured_data 로드 실패 등).
            return jsonify({"success": False, "message": str(ve)}), 400

        user = get_user_by_id(session.get("user_id"))
        sd = _load_order_structured_data_for_update(order)
        # append_client_log는 최초 append 시 legacy(as_content)를 as_log로 영구화한다.
        # sd는 무손실 로드가 돌려준 사본이라 반환값과 무관하게 재대입 + flag_modified 필수.
        entry = append_client_log(
            sd, log_type=log_type, text=text,
            by=(user.name if user else ""), by_id=(user.id if user else None))
        order.structured_data = sd
        flag_modified(order, "structured_data")
        sync_erp_flat_columns(order, sd)
        db.add(SecurityLog(
            user_id=session.get("user_id"), message=f"주문 #{order_id} AS 기록 추가"))
        # 렌더는 commit 앞에서 — 템플릿 오류가 "저장은 됐는데 500"이 되면
        # 클라 재시도가 append-only 리스트에 중복 항목을 남긴다.
        html = _render_as_log_entry(entry)
        db.commit()
        _invalidate_shipment_asrec_caches("api_as_log_append")
        return jsonify({"success": True, "entry": entry, "html": html})
    except ValueError as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)}), 409
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


@erp_orders_as_bp.route("/<int:order_id>/as/log/<log_id>", methods=["PATCH"])
@login_required
@erp_edit_required
def api_as_log_patch(order_id: int, log_id: str):
    """AS 타임라인 항목 본문 수정. 작성자 본인 또는 관리자만."""
    db = get_db()
    try:
        order = db.get(Order, order_id)
        if not order or order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404
        # legacy는 읽기 전용. 영구화 전(lazy) 항목도 같은 id로 노출되므로 조회 전에 막는다.
        if log_id.startswith("al_legacy_"):
            return jsonify({"success": False, "message": "이전 기록은 수정할 수 없습니다."}), 400

        try:
            text = _clean_as_log_text((request.get_json(silent=True) or {}).get("text"))
        except ValueError as ve:
            return jsonify({"success": False, "message": str(ve)}), 400

        user = get_user_by_id(session.get("user_id"))
        is_admin = bool(user and (user.role or "").upper() == "ADMIN")
        sd = _load_order_structured_data_for_update(order)
        log = (sd.get("shipment") or {}).get("as_log") or []
        target = next((e for e in log if isinstance(e, dict) and e.get("id") == log_id), None)
        if target is None:
            return jsonify({"success": False, "message": "항목을 찾을 수 없습니다."}), 404
        if target.get("legacy") is True:
            return jsonify({"success": False, "message": "이전 기록은 수정할 수 없습니다."}), 400
        if target.get("type") == "system":
            return jsonify({"success": False, "message": "시스템 기록은 수정할 수 없습니다."}), 400
        if not is_admin and target.get("by_id") != (user.id if user else None):
            return jsonify({"success": False, "message": "본인 또는 관리자만 수정할 수 있습니다."}), 403

        target["text"] = text
        target["edited_at"] = now_utc_naive().isoformat()
        target["edited_by"] = user.name if user else ""
        order.structured_data = sd
        flag_modified(order, "structured_data")
        db.add(SecurityLog(
            user_id=session.get("user_id"),
            message=f"주문 #{order_id} AS 기록 수정({log_id})"))
        html = _render_as_log_entry(target)  # commit 앞 렌더(append와 동일 이유)
        db.commit()
        _invalidate_shipment_asrec_caches("api_as_log_patch")
        return jsonify({"success": True, "entry": target, "html": html})
    except ValueError as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)}), 409
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


__all__ = [
    "erp_orders_as_bp",
    "api_as_start",
    "api_as_complete",
    "api_as_register",
    "api_as_schedule",
    "api_as_billing",
    "api_as_log_append",
    "api_as_log_patch",
    "get_today_kst",
]
