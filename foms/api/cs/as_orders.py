"""ERP 주문 AS(사후관리) API — canonical AS cycle 전이(STATE-AS-01) + AS 타임라인.

erp.py 에서 분리된 as/start·as/complete·as/register·as/schedule 을 canonical
``as_lifecycle`` cycle 상태기계(:mod:`foms.services.orders.as_cycle_service`)로 이관한다.
전이는 orthogonal AS 축(cycle transition history)만 쓰고 ``workflow.stage`` 를 AS_* 로
덮지 않는다(AS main stage 복구/오염 금지). ``order.status`` 는 legacy projection 으로
재계산되는 overlay 이며, version bump·idempotency receipt·``OrderEvent`` parity 는 REV-00
:func:`execute_order_mutation` 이 원자 보장한다(commit 은 이 route 소유).

AS 타임라인(``shipment.as_log`` append-only)·비용 판정(``shipment.as_billing``)은 상태축이
아닌 sd 기록이지만 같은 원자성 요구를 가지므로, 전이에 딸린 기록은 command 의 ``sd_hook``
으로 **같은 tx** 안에서 남기고(2-commit 금지), 독립 기록(as/log·as/billing)은
:func:`_run_sd_mutation` 으로 같은 REV-00 substrate 를 탄다.
"""
import copy
import datetime
import hashlib
import json
import logging
from typing import Any, Callable, Dict, List, Optional

from flask import Blueprint, jsonify, render_template, request, session
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from foms.web.auth import get_user_by_id, log_access, login_required
from foms.services.audit_message_display import describe_order_action
from foms.services.orders.audit_order_context import order_audit_context
from db import get_db
from foms.services.as_content_safety import (
    load_structured_data_dict_or_raise,
    sanitize_as_content_html,
)
from foms.services.datetime_kst import now_utc_naive
from foms.services.erp_display import get_today_kst
from foms.services.erp_permissions import erp_construction_edit_required, erp_edit_required
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.erp_utils import ensure_path
from foms.services.orders.as_cycle_service import (
    AS_IN_PROGRESS,
    AS_RECEIVED,
    ASCycleError,
    complete_as_cycle,
    current_cycle,
    cycle_status,
    register_as_cycle,
    reopen_as_cycle,
    schedule_as_cycle,
    set_as_classification,
    start_as_cycle,
    unschedule_as_cycle,
)
from foms.services.orders.as_log import (
    AS_LOG_TEXT_MAX,
    append_client_log,
    append_system_log,
    append_verdict_log,
    build_as_timeline_view,
    coerce_client_log_type,
    current_as_round,
    decorate_entry,
    migrate_legacy_into_log,
)
from foms.services.orders.as_schedule_link import (
    SOURCE_NEARBY,
    ack_link,
    clear_link,
    evaluate_drift,
    read_as_visit_date,
    read_link,
    relink,
    write_link,
)
from foms.services.orders.revision import RevisionError, execute_order_mutation
from models import Order

logger = logging.getLogger(__name__)

erp_orders_as_bp = Blueprint(
    "erp_orders_as",
    __name__,
    url_prefix="/api/orders",
)

# 상태축을 건드리지 않는 sd 기록의 REV-00 receipt scope 문자열(AS cycle POLICY_* 와 대칭).
POLICY_AS_BILLING = "STATE_AS_BILLING"
POLICY_AS_LOG_APPEND = "STATE_AS_LOG_APPEND"
POLICY_AS_VERDICT = "STATE_AS_VERDICT"
POLICY_AS_LOG_PATCH = "STATE_AS_LOG_PATCH"
POLICY_AS_LOG_DELETE = "STATE_AS_LOG_DELETE"
POLICY_AS_REREGISTER = "STATE_AS_REREGISTER"
POLICY_AS_SCHEDULE_LINK = "STATE_AS_SCHEDULE_LINK"


def _invalidate_shipment_asrec_caches(reason: str) -> None:
    """Dashboard + shipment AS recommendation cache bust (commit-after, best-effort).

    Tier A(broad): AS 전이는 order.status(AS↔CS↔AS_RECEIVED)와 stage projection 을 바꿔
    여러 탭(주문/시공/완료/출고 추천) 사이 이동을 유발하므로 전체 무효화를 유지한다.
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


def _scope_hash(command_id: str, order_id: int) -> str:
    """전이 scope 의 sha256 hex(REV-00 receipt 저장용)."""
    return hashlib.sha256(f"{command_id}:{order_id}".encode("utf-8")).hexdigest()


def _request_hash(body: dict[str, Any]) -> str:
    """요청 payload 의 sha256 hex(same-key/different-hash 감지용)."""
    canonical = json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _idempotency_key(body: dict[str, Any]) -> Optional[str]:
    """요청 idempotency key(헤더 우선, body fallback, ≤64자). 없으면 None."""
    key = request.headers.get("Idempotency-Key") or body.get("idempotency_key")
    key = str(key).strip() if key is not None else ""
    return key[:64] if key else None


def _load_active_order(db, order_id):
    """활성 주문을 로드하고, 없거나 삭제됐으면 404 JSON 튜플을 돌려준다."""
    order = db.get(Order, order_id)
    if not order or order.status == "DELETED" or order.deleted_at is not None:
        return None, (jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404)
    return order, None


def _audit_as(
    order: Order,
    action: str,
    user_id: Any,
    note: str | None = None,
    extra: Dict[str, Any] | None = None,
) -> None:
    """AS 행위 1건을 구조화 감사로 남긴다(문장은 표시 SSOT 가 만든다).

    라우트가 뒤에서 ``db.commit()`` 하므로 같은 트랜잭션에 싣는다(``auto_commit=False``) —
    AS 상태 변경과 감사 기록이 함께 커밋되거나 함께 사라진다.

    :param order: 대상 :class:`~models.Order`.
    :param action: 행위 코드(``AS_STARTED`` 등).
    :param user_id: 행위자 user id.
    :param note: 문장 뒤에 붙일 짧은 부연(사유·판정값 등). 장문은 표시 SSOT 가 요약한다.
    :param extra: ``detail`` 에 추가로 담을 구조화 값.
    """
    context = order_audit_context(order)
    log_access(
        describe_order_action(order_id=order.id, action=action, note=note, **context),
        user_id,
        auto_commit=False,
        action=action, target_type="order", target_id=int(order.id),
        detail={**(extra or {}), **context},
    )


def _as_error_response(db, exc: Exception):
    """AS cycle/REV 계약 위반을 409 로, 그 외는 500 으로 매핑하고 rollback 한다.

    :class:`ASCycleError` 는 ValueError 파생이고, structured_data 무결성 실패도 ValueError
    로 올라온다(둘 다 낙관/무결성 계열 = 409). 그 밖의 예외만 500 이다.
    """
    db.rollback()
    if isinstance(exc, (ValueError, RevisionError)):
        return jsonify({"success": False, "message": str(exc)}), 409
    logger.error("AS command failed", exc_info=True)
    return jsonify({"success": False, "message": str(exc)}), 500


def _run_sd_mutation(
    db: Session, *, order_id: int, actor_user_id: int, policy_id: str, command_id: str,
    apply: Callable[[Dict[str, Any], Order], None], body: Dict[str, Any],
) -> None:
    """AS cycle 전이가 아닌 sd 기록(as_log·as_billing)을 REV-00 원자 mutation 으로 감싼다.

    상태축을 바꾸지 않으므로 transition·``OrderEvent``·legacy status 재계산은 하지 않고,
    row lock(lost update 차단)·version bump·idempotency receipt 만 얻는다. ``apply(sd, order)``
    는 잠긴 row 아래에서 무손실 로드한 sd 사본을 mutate 한다(commit 은 호출자 소유).

    Args:
        db: 요청 세션. order_id: 대상 주문. actor_user_id: actor.
        policy_id: receipt 정책 식별자. command_id: scope hash 구성 문자열.
        apply: 잠긴 sd 를 mutate 하는 콜러블. body: 요청 payload(hash·idempotency).

    Returns:
        None. 계약 위반은 ValueError/RevisionError 로 전파된다(호출부가 409 매핑).
    """
    def _mutate(sess: Session, orders: List[Order]) -> Dict[int, List[str]]:
        order = orders[0]
        sd = _load_order_structured_data_for_update(order)
        apply(sd, order)
        order.structured_data = sd
        flag_modified(order, "structured_data")
        sync_erp_flat_columns(order, sd)
        sess.flush()
        return {order.id: [f"ORDER_DETAIL:{order.id}", "ORDERS_INDEX"]}

    execute_order_mutation(
        db, actor_user_id=actor_user_id, policy_id=policy_id, order_ids=[order_id],
        scope_hash=_scope_hash(command_id, order_id), request_hash=_request_hash(body),
        mutation=_mutate, idempotency_key=_idempotency_key(body),
    )


# --------------------------------------------------------------------------- #
# AS 비용 판정(as_billing) — 무상/유상/미정 상태기계
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# AS 타임라인 본문 가드 · 단건 렌더
# --------------------------------------------------------------------------- #
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


def _resolve_as_log_entry(
    log: list, log_id: str, user, *, verb: str
) -> tuple[dict | None, tuple[str, int] | None]:
    """as_log 단건 조회 + 수정/삭제 공통 권한 판정 (두 라우트가 공유하는 SSOT).

    각 라우트가 따로 판정하면 한쪽만 손봤을 때 권한 매트릭스가 갈린다 — system/legacy/
    verdict 불가와 "작성자 본인 또는 관리자"는 수정·삭제가 같아야 한다. verb 만 문구로 주입한다.

    잠금 **전** 사본으로 미리 거른다(_run_sd_mutation 을 헛돌리지 않기 위해). 잠근 뒤
    항목이 사라지는 경쟁은 apply 안에서 다시 확인한다(patch·delete 공통 계약).

    Args:
        log: ``structured_data.shipment.as_log`` 리스트(호출부가 [] 로 정규화해 넘긴다).
        log_id: 대상 항목 id.
        user: 현재 사용자(None 가능).
        verb: 사용자 문구에 넣을 동작 이름('수정' / '삭제').

    Returns:
        (항목, None) 또는 (None, (사용자 문구, HTTP 상태)).
    """
    target = next((e for e in log if isinstance(e, dict) and e.get("id") == log_id), None)
    if target is None:
        return None, ("항목을 찾을 수 없습니다.", 404)
    if target.get("legacy") is True:
        return None, (f"이전 기록은 {verb}할 수 없습니다.", 400)
    if target.get("type") == "system":
        return None, (f"시스템 기록은 {verb}할 수 없습니다.", 400)
    if target.get("type") == "verdict":
        # 판정 수는 current_as_round 파생의 근거다 — 지우거나 고치면 이미 스탬프된
        # 이후 항목들의 round 와 어긋난다. 정정은 새 판정 append(T15 회차 규약).
        return None, (f"판정 기록은 {verb}할 수 없습니다. 정정은 새 판정으로 남겨주세요.", 400)
    is_admin = bool(user and (user.role or "").upper() == "ADMIN")
    if not is_admin and target.get("by_id") != (user.id if user else None):
        return None, (f"본인 또는 관리자만 {verb}할 수 있습니다.", 403)
    return target, None


def _render_as_timeline_cell(order_id: int, sd: dict) -> str:
    """PC 요약 셀 재렌더(목록과 동일 매크로) — 기록 삭제 응답의 셀 교체용.

    클라가 증분으로 계산하면 방금 지운 기록의 본문이 '최근 1줄'에 그대로 남는다
    (남은 기록 목록을 클라가 갖고 있지 않다). 서버가 다시 그려 통째로 바꾼다.
    """
    from foms.services.as_dashboard_display import apply_timeline_cell_text

    view = build_as_timeline_view(sd)
    apply_timeline_cell_text(view)
    return render_template(
        "cs/partials/as_timeline_cell_partial.html", order_id=order_id, view=view
    ).strip()


@erp_orders_as_bp.route("/<int:order_id>/as/register", methods=["POST"])
@login_required
@erp_construction_edit_required
def api_as_register(order_id):
    """AS 접수 등록: 새 RECEIVED cycle 발급 + 접수일 스탬프 + draft finalize(DRAFT-LIFECYCLE).

    접수 원문은 reception 항목으로, 접수 "사실"은 system 항목으로 타임라인에 남고, 최초
    접수에서만 as_billing 추정값을 시드한다(모두 cycle 전이와 같은 tx).
    """
    db = get_db()
    order, err = _load_active_order(db, order_id)
    if err:
        return err
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
        billing_type = _coerce_billing_type(data.get("billing_type") or "free")
        billing_amount = (
            _coerce_billing_amount(data.get("amount")) if billing_type == "paid" else None
        )
    except ValueError as ve:
        return jsonify({"success": False, "message": str(ve)}), 400
    source_screen = str(data.get("source_screen") or "").strip()
    shipping = str(data.get("shipping_scheduled_date") or "").strip() or None
    if shipping:
        try:
            # 지방주문 AS 재상차 상차일. 재접수 분기는 register_as_cycle 을 타지 않으므로
            # 여기서 걸러 두 경로가 같은 검증을 받게 한다. 상태코드는 409 — 이 필드의 형식
            # 오류는 양측 공통으로 409였고 test_as_received_date_kst 가 핀으로 고정한다
            # (본 파일의 일반 규칙 "검증 실패=400"의 기존 계약 예외).
            datetime.datetime.strptime(shipping, "%Y-%m-%d")
        except ValueError:
            return jsonify({
                "success": False, "message": "상차일 형식이 올바르지 않습니다. (YYYY-MM-DD)"}), 409

    user_id = session.get("user_id")
    user = get_user_by_id(user_id)
    today = get_today_kst().strftime("%Y-%m-%d")
    cw_name = (
        _confirmed_construction_worker_name(user)
        if source_screen == "erp_construction_dashboard"
        else ""
    )
    old_sd = copy.deepcopy(order.structured_data or {})
    # meta['finalized_at']로 JSONB에 남는 값 — naive 타임스탬프는 UTC 규약(전역 규약 2).
    now = now_utc_naive()

    # /add draft 주문은 structured PUT 없이 AS 모달만 완료하므로 draft meta 를 먼저 정리한다
    # (남으면 Order.active_filter 에서 제외돼 AS 탭에 안 보임). 이후 register 의 projection 이
    # order.status 를 AS_RECEIVED overlay 로 최종 확정한다(finalize 의 stage 배정을 덮어씀).
    from foms.api.erp_orders_structured import _finalize_draft_state

    draft_cleared = _finalize_draft_state(order, order.structured_data, now, old_sd)
    if draft_cleared:
        flag_modified(order, "structured_data")

    def _register_side_records(sd: Dict[str, Any]) -> None:
        """cycle 전이와 같은 sd 사본에 접수 기록(reception·system·billing 시드)을 남긴다."""
        shipment = ensure_path(sd, "shipment")
        # 덮어쓰기 전에 이전 원문을 legacy로 굳힌다. append_client_log도 같은 마이그레이션을
        # 하지만 그건 원문이 **있을 때만** 돈다 — 빈 원문 재접수는 append가 없어 register 의
        # as_content 덮어쓰기가 이전 기록을 보존 없이 지웠다(멱등: 이미 as_log가 있으면 no-op).
        migrate_legacy_into_log(sd)
        # 재접수 모달은 기존 as_content 를 프리필한다(erp-order-shared.js) — 무편집 제출이면
        # 같은 본문이 그대로 돌아온다. 그 본문은 직전 reception 또는 방금 굳힌 legacy 로 이미
        # 로그에 있으므로 append 하면 append-only 리스트에 영구 중복이 남는다. "as_content 가
        # 그대로 + 같은 본문이 로그에 이미 존재" 둘 다일 때만 건너뛴다. 접수 "사실"은 아래
        # system 이벤트가 계속 남긴다.
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
        # 최초 접수에서만 billing을 시드한다. 재접수(지방 재상차 등)는 정상 흐름이므로
        # 기존 billing을 덮으면 확정된 유상 금액이 free/미확정으로 되돌아간다.
        # 확정·전환은 전용 API 소관(스펙 §3.2).
        if not isinstance(shipment.get("as_billing"), dict):
            billing = _default_as_billing()
            billing["type"] = billing_type
            billing["amount"] = billing_amount
            shipment["as_billing"] = billing

    def _apply_reregistration(sd: Dict[str, Any], locked: Order) -> None:
        """열린 cycle 이 있는 재접수: 새 cycle 없이 접수 기록만 갱신한다.

        지방주문 AS 재상차는 같은 AS 건을 다시 접수하는 정상 업무 흐름이라, 여기서 새 cycle
        을 열면 한 건이 두 건으로 갈라진다. 상태·cycle 은 그대로 두고 접수 원문·타임라인·
        상차일만 갱신한다(서비스의 "중복 open cycle 거부" 불변식은 유지 — 라우트가 중재).
        """
        _register_side_records(sd)  # as_content 를 덮기 전에 먼저(legacy 영구화 순서 계약)
        shipment = ensure_path(sd, "shipment")
        shipment["as_content"] = as_content
        if cw_name:
            shipment["construction_workers"] = [cw_name]
        locked.as_received_date = today
        if shipping:
            locked.shipping_scheduled_date = shipping

    open_cycle = current_cycle(order.structured_data or {})
    reregistering = open_cycle is not None and cycle_status(open_cycle) in (
        AS_RECEIVED, AS_IN_PROGRESS)
    try:
        if reregistering:
            _run_sd_mutation(
                db, order_id=order_id, actor_user_id=user_id, policy_id=POLICY_AS_REREGISTER,
                command_id="AS_REREGISTER", apply=_apply_reregistration, body=data,
            )
        else:
            register_as_cycle(
                db, order_id=order_id, actor_user_id=user_id, as_content=as_content,
                shipping_scheduled_date=shipping, source_screen=source_screen or None,
                received_date=today, construction_worker_name=cw_name or None,
                scope_hash=_scope_hash("AS_REGISTER", order_id), request_hash=_request_hash(data),
                idempotency_key=_idempotency_key(data), sd_hook=_register_side_records,
            )
    except Exception as exc:  # noqa: BLE001 — 계약 위반은 409, 그 외 500 으로 분기
        return _as_error_response(db, exc)

    _audit_as(order, "AS_RECEIVED", user_id, note=f"접수일 {today}", extra={"received_date": str(today)})
    db.commit()
    _invalidate_shipment_asrec_caches("api_as_register")

    shipment = (order.structured_data or {}).get("shipment") or {}
    return jsonify({
        "success": True,
        "message": "AS 접수가 등록되었습니다.",
        "as_received_date": today,
        "new_status": order.status,
        "shipping_scheduled_date": getattr(order, "shipping_scheduled_date", None) or "",
        "construction_workers": shipment.get("construction_workers") or [],
        "draft_cleared": draft_cleared,
    })


@erp_orders_as_bp.route("/<int:order_id>/as/schedule", methods=["POST"])
@login_required
@erp_edit_required
def api_as_schedule(order_id):
    """AS 방문일 확정: current cycle 에 방문 날짜/시각 transition 기록(빈 날짜는 unschedule)."""
    db = get_db()
    order, err = _load_active_order(db, order_id)
    if err:
        return err
    data = request.get_json() or {}
    visit_date = str(data.get("visit_date") or "").strip()
    visit_time = data.get("visit_time", "")
    user_id = session.get("user_id")

    if visit_date:
        try:
            # 저장 전 형식 검증. 검증 없이 두면 임의 문자열이 schedule.as_visit.date 와
            # 영구(append-only) 타임라인 문구로 함께 굳는다. 형식 오류는 400(409는 낙관/무결성).
            datetime.datetime.strptime(visit_date, "%Y-%m-%d")
        except ValueError:
            return jsonify({
                "success": False, "message": "방문일 형식이 올바르지 않습니다. (YYYY-MM-DD)"}), 400

    try:
        if not visit_date:
            unschedule_as_cycle(
                db, order_id=order_id, actor_user_id=user_id,
                reason=str(data.get("reason") or "방문일 취소"),
                cycle_id=data.get("cycle_id"),
                scope_hash=_scope_hash("AS_UNSCHEDULE", order_id),
                request_hash=_request_hash(data), idempotency_key=_idempotency_key(data),
                legacy_bridge=True,
            )
            message, result_date = "AS 방문일이 취소되었습니다.", ""
        else:
            schedule_as_cycle(
                db, order_id=order_id, actor_user_id=user_id, visit_date=visit_date,
                visit_time=visit_time, cycle_id=data.get("cycle_id"),
                scope_hash=_scope_hash("AS_SCHEDULE", order_id),
                request_hash=_request_hash(data), idempotency_key=_idempotency_key(data),
                sd_hook=lambda sd: append_system_log(sd, text=f"방문일 확정: {visit_date}"),
                legacy_bridge=True,
            )
            message, result_date = f"AS 방문일이 {visit_date}로 확정되었습니다.", visit_date
    except Exception as exc:  # noqa: BLE001
        return _as_error_response(db, exc)

    _audit_as(order, "AS_SCHEDULED" if result_date else "AS_SCHEDULE_CANCELED", user_id,
              note=str(result_date or ""), extra={"visit_date": result_date})
    db.commit()
    _invalidate_shipment_asrec_caches("api_as_schedule")
    return jsonify({"success": True, "message": message, "visit_date": result_date})


@erp_orders_as_bp.route("/<int:order_id>/as/unschedule", methods=["POST"])
@login_required
@erp_edit_required
def api_as_unschedule(order_id):
    """AS 방문일 취소: current cycle 방문 날짜/시각을 명시 transition 으로 clear(상태 불변)."""
    db = get_db()
    order, err = _load_active_order(db, order_id)
    if err:
        return err
    data = request.get_json() or {}
    user_id = session.get("user_id")
    try:
        unschedule_as_cycle(
            db, order_id=order_id, actor_user_id=user_id,
            reason=str(data.get("reason") or "방문일 취소"), cycle_id=data.get("cycle_id"),
            scope_hash=_scope_hash("AS_UNSCHEDULE", order_id),
            request_hash=_request_hash(data), idempotency_key=_idempotency_key(data),
            sd_hook=lambda sd: append_system_log(sd, text="방문일 취소"),
            legacy_bridge=True,
        )
    except Exception as exc:  # noqa: BLE001
        return _as_error_response(db, exc)
    _audit_as(order, "AS_SCHEDULE_CANCELED", user_id)
    db.commit()
    _invalidate_shipment_asrec_caches("api_as_unschedule")
    return jsonify({"success": True, "message": "AS 방문일이 취소되었습니다."})


@erp_orders_as_bp.route("/<int:order_id>/as/start", methods=["POST"])
@login_required
@erp_edit_required
def api_as_start(order_id):
    """AS 시작: current RECEIVED cycle 을 IN_PROGRESS 로 전이(사유/설명 기록)."""
    db = get_db()
    order, err = _load_active_order(db, order_id)
    if err:
        return err
    data = request.get_json() or {}
    user_id = session.get("user_id")
    try:
        start_as_cycle(
            db, order_id=order_id, actor_user_id=user_id,
            reason=str(data.get("reason") or ""), description=str(data.get("description") or ""),
            cycle_id=data.get("cycle_id"), scope_hash=_scope_hash("AS_START", order_id),
            request_hash=_request_hash(data), idempotency_key=_idempotency_key(data),
        )
    except Exception as exc:  # noqa: BLE001
        return _as_error_response(db, exc)
    _audit_as(order, "AS_STARTED", user_id, note=str(data.get("reason") or "") or None,
              extra={"reason": str(data.get("reason") or "") or None})
    db.commit()
    _invalidate_shipment_asrec_caches("api_as_start")
    return jsonify({"success": True, "message": "AS가 시작되었습니다.", "new_status": order.status})


@erp_orders_as_bp.route("/<int:order_id>/as/complete", methods=["POST"])
@login_required
@erp_edit_required
def api_as_complete(order_id):
    """AS 완료: current IN_PROGRESS cycle 을 COMPLETED 로 종결(완료 메모·완료일 기록)."""
    db = get_db()
    order, err = _load_active_order(db, order_id)
    if err:
        return err
    data = request.get_json() or {}
    user_id = session.get("user_id")
    try:
        complete_as_cycle(
            db, order_id=order_id, actor_user_id=user_id, note=str(data.get("note") or ""),
            cycle_id=data.get("cycle_id"), scope_hash=_scope_hash("AS_COMPLETE", order_id),
            request_hash=_request_hash(data), idempotency_key=_idempotency_key(data),
            sd_hook=lambda sd: append_system_log(sd, text="AS 완료"),
            legacy_bridge=True,
        )
    except Exception as exc:  # noqa: BLE001
        return _as_error_response(db, exc)
    _audit_as(order, "AS_COMPLETED", user_id, note=str(data.get("note") or "") or None)
    db.commit()
    _invalidate_shipment_asrec_caches("api_as_complete")
    return jsonify({"success": True, "message": "AS가 완료되었습니다.", "new_status": order.status})


@erp_orders_as_bp.route("/<int:order_id>/as/reopen", methods=["POST"])
@login_required
@erp_edit_required
def api_as_reopen(order_id):
    """AS 재개봉: 오완료된 current COMPLETED cycle 을 같은 cycle 로 RECEIVED 로 되돌린다."""
    db = get_db()
    order, err = _load_active_order(db, order_id)
    if err:
        return err
    data = request.get_json() or {}
    user_id = session.get("user_id")
    try:
        reopen_as_cycle(
            db, order_id=order_id, actor_user_id=user_id,
            reason=str(data.get("reason") or ""), cycle_id=data.get("cycle_id"),
            scope_hash=_scope_hash("AS_REOPEN", order_id),
            request_hash=_request_hash(data), idempotency_key=_idempotency_key(data),
            sd_hook=lambda sd: append_system_log(sd, text="AS 완료 취소"),
        )
    except Exception as exc:  # noqa: BLE001
        return _as_error_response(db, exc)
    _audit_as(order, "AS_REOPENED", user_id, note=str(data.get("reason") or "") or None,
              extra={"reason": str(data.get("reason") or "") or None})
    db.commit()
    _invalidate_shipment_asrec_caches("api_as_reopen")
    return jsonify({"success": True, "message": "AS가 재개봉되었습니다.", "new_status": order.status})


@erp_orders_as_bp.route("/<int:order_id>/as/classification", methods=["POST"])
@login_required
@erp_edit_required
def api_as_classification(order_id):
    """AS 분류 토글: current cycle 의 as_pending/as_blueprint/sales_delivery 를 갱신(상태·main 불변)."""
    db = get_db()
    order, err = _load_active_order(db, order_id)
    if err:
        return err
    data = request.get_json() or {}
    user_id = session.get("user_id")
    field = str(data.get("field") or "")
    value = bool(data.get("value"))
    try:
        set_as_classification(
            db, order_id=order_id, actor_user_id=user_id, field=field, value=value,
            cycle_id=data.get("cycle_id"), scope_hash=_scope_hash("SET_AS_CLASSIFICATION", order_id),
            request_hash=_request_hash(data), idempotency_key=_idempotency_key(data),
        )
    except Exception as exc:  # noqa: BLE001
        return _as_error_response(db, exc)
    _audit_as(order, "AS_CATEGORY_CHANGED", user_id, note=f"{field}: {value}",
              extra={"field": field, "value": value})
    db.commit()
    _invalidate_shipment_asrec_caches("api_as_classification")
    shipment = (order.structured_data or {}).get("shipment") or {}
    return jsonify({
        "success": True,
        "message": "AS 분류가 업데이트되었습니다.",
        "field": field,
        "value": value,
        "as_pending": shipment.get("as_pending") is True,
        "as_blueprint": shipment.get("as_blueprint") is True,
        "sales_delivery": shipment.get("sales_delivery") is True,
    })


def _apply_billing_decision(sd: dict, *, data: dict, new_type: str, reason: str, user) -> dict:
    """잠긴 sd 에 판정을 확정하고 최초확정/전환 system 로그를 남긴다.

    기준은 **확정 여부**다. type 만 보면 register 가 심은 미확정 추정값이 "이전 판정"으로
    둔갑해 첫 확정이 전환으로 기록된다. 확정 상태에서의 동일 유형 재확정(금액만 변경 등)은
    무기록 — 타임라인이 노이즈로 찬다. 사유는 사용자 입력이지만 append_system_log 가
    생성 지점에서 escape·절단한다.

    Args:
        sd: 잠긴 row 의 structured_data 사본. data: 요청 payload. new_type: 확정 유형.
        reason: 판정 사유(빈 값 허용). user: actor.

    Returns:
        ``{"billing": 갱신된 as_billing, "entry": append 된 system 항목 또는 None}``.
    """
    prev = (sd.get("shipment") or {}).get("as_billing")
    prev = prev if isinstance(prev, dict) else {}
    prev_type = str(prev.get("type") or "free")
    # amount 키가 없으면 기존 금액을 보존한다(reason 빈값 보존과 대칭). 금액 없이 재확정하는
    # 요청이 확정된 청구액을 지우면 안 된다. 명시적 {"amount": null}은 의도적 삭제로 허용.
    if new_type != "paid":
        amount = None
    elif "amount" in data:
        amount = _coerce_billing_amount(data["amount"])
    else:
        amount = prev.get("amount")

    billing = _write_as_billing(
        sd, billing_type=new_type, amount=amount, confirmed=True, reason=reason, user=user,
    )
    suffix = f": {reason}" if reason else ""
    if prev.get("confirmed") is not True:
        event = _AS_BILLING_FIRST_EVENTS[new_type]
    elif prev_type != new_type:
        event = (f"{_AS_BILLING_LABELS.get(prev_type, prev_type)}"
                 f"→{_AS_BILLING_LABELS[new_type]} 전환")
    else:
        event = ""
    entry = append_system_log(sd, text=f"{event}{suffix}") if event else None
    return {"billing": billing, "entry": entry}


@erp_orders_as_bp.route("/<int:order_id>/as/billing", methods=["POST"])
@login_required
@erp_edit_required
def api_as_billing(order_id: int):
    """AS 무상/유상 판정 확정·전환. 전환 시 reason 필수."""
    db = get_db()
    order, err = _load_active_order(db, order_id)
    if err:
        return err
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
    prev = ((order.structured_data or {}).get("shipment") or {}).get("as_billing")
    prev = prev if isinstance(prev, dict) else {}
    if prev.get("confirmed") is True and str(prev.get("type") or "free") != new_type and not reason:
        return jsonify({"success": False, "message": "판정 전환 시 사유는 필수입니다."}), 400
    if new_type == "paid" and "amount" in data:
        try:
            # 입력 검증 실패는 400. 409는 낙관/무결성 전용(structured_data 로드 실패 등).
            _coerce_billing_amount(data["amount"])
        except ValueError as e:
            return jsonify({"success": False, "message": str(e)}), 400

    user_id = session.get("user_id")
    user = get_user_by_id(user_id)
    captured: dict[str, Any] = {}

    try:
        _run_sd_mutation(
            db, order_id=order_id, actor_user_id=user_id, policy_id=POLICY_AS_BILLING,
            command_id="AS_BILLING", body=data,
            apply=lambda sd, _order: captured.update(_apply_billing_decision(
                sd, data=data, new_type=new_type, reason=reason, user=user)),
        )
    except Exception as exc:  # noqa: BLE001
        return _as_error_response(db, exc)

    billing = captured["billing"]
    # 응답 html은 낙관적 DOM 삽입용(재조회 금지). 렌더는 commit 앞 — append/patch와 같은 이유.
    entry_html = _render_as_log_entry(captured["entry"]) if captured.get("entry") else ""
    _audit_as(order, "AS_BILLING_DECIDED", user_id, note=new_type,
              extra={"billing_type": new_type, "reason": reason or None})
    db.commit()
    _invalidate_shipment_asrec_caches("api_as_billing")
    return jsonify({
        "success": True,
        "billing": billing,
        "html": entry_html,          # 타임라인 낙관적 삽입용(없으면 빈 문자열)
        "badge_html": _render_as_billing_badge(billing),  # 상태 셀 배지 교체용
        "state_text": _as_billing_state_text(billing),    # 헤더 현재 판정 표기
    })


@erp_orders_as_bp.route("/<int:order_id>/as/log", methods=["POST"])
@login_required
@erp_edit_required
def api_as_log_append(order_id: int):
    """AS 타임라인 항목 append. body {type, text}. ts·작성자는 서버가 정한다."""
    db = get_db()
    order, err = _load_active_order(db, order_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    try:
        log_type = coerce_client_log_type(data.get("type"))
        text = _clean_as_log_text(data.get("text"))
    except ValueError as ve:
        # 검증 실패는 400. 409는 낙관/무결성 전용(structured_data 로드 실패 등).
        return jsonify({"success": False, "message": str(ve)}), 400

    user_id = session.get("user_id")
    user = get_user_by_id(user_id)
    captured: dict[str, Any] = {}

    def _append(sd: Dict[str, Any], _order: Order) -> None:
        """append_client_log 는 최초 append 시 legacy(as_content)를 as_log 로 영구화한다."""
        captured["entry"] = append_client_log(
            sd, log_type=log_type, text=text,
            by=(user.name if user else ""), by_id=(user.id if user else None))

    try:
        _run_sd_mutation(
            db, order_id=order_id, actor_user_id=user_id, policy_id=POLICY_AS_LOG_APPEND,
            command_id="AS_LOG_APPEND", apply=_append, body=data,
        )
    except Exception as exc:  # noqa: BLE001
        return _as_error_response(db, exc)

    _audit_as(order, "AS_LOG_ADDED", user_id, extra={"log_type": log_type})
    # 렌더는 commit 앞에서 — 템플릿 오류가 "저장은 됐는데 500"이 되면
    # 클라 재시도가 append-only 리스트에 중복 항목을 남긴다.
    entry = captured["entry"]
    html = _render_as_log_entry(entry)
    db.commit()
    _invalidate_shipment_asrec_caches("api_as_log_append")
    return jsonify({"success": True, "entry": entry, "html": html})


@erp_orders_as_bp.route("/<int:order_id>/as/verdict", methods=["POST"])
@login_required
@erp_edit_required
def api_as_verdict(order_id: int):
    """회차 판정(완결/미결) append. body {verdict, text?}.

    T15 회차 규약 — 판정은 quick-add 가 아니라 이 전용 경로만 만든다(coerce 가 verdict
    유형을 400 으로 거부). 미결 판정이 저장되는 순간 current_as_round 파생값이 1 올라
    이후 기록이 자동으로 다음 회차 스탬프를 받는다(round+1, 별도 상태 없음). 판정의
    정정은 수정/삭제가 아니라 새 판정 append 다(_resolve_as_log_entry 가드와 대칭).

    Args:
        order_id: 대상 주문 PK.

    Returns:
        200 ``{'success', 'entry', 'html', 'current_round'}`` /
        400 검증 실패(verdict 값·본문 캡) / 404 주문 없음 / 409 낙관·무결성.
    """
    db = get_db()
    order, err = _load_active_order(db, order_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    verdict = str(data.get("verdict") or "").strip().lower()
    try:
        # 사유는 선택 — 빈 값 허용이라 _clean_as_log_text(빈 값 400)를 그대로 못 쓴다.
        _guard_as_log_raw_size(data.get("text"))
        text = sanitize_as_content_html(data.get("text"))
        if text and len(text) > AS_LOG_TEXT_MAX:
            raise ValueError("내용이 너무 깁니다.")
        if verdict not in ("resolved", "unresolved"):
            raise ValueError("판정은 완결(resolved)/미결(unresolved)만 허용됩니다.")
    except ValueError as ve:
        return jsonify({"success": False, "message": str(ve)}), 400

    user_id = session.get("user_id")
    user = get_user_by_id(user_id)
    captured: dict[str, Any] = {}

    def _append(sd: Dict[str, Any], _order: Order) -> None:
        """append_verdict_log 가 판정 대상 회차 스탬프·값 검증을 소유한다."""
        captured["entry"] = append_verdict_log(
            sd, verdict=verdict, text=text,
            by=(user.name if user else ""), by_id=(user.id if user else None))
        captured["current_round"] = current_as_round(sd)

    try:
        _run_sd_mutation(
            db, order_id=order_id, actor_user_id=user_id, policy_id=POLICY_AS_VERDICT,
            command_id="AS_VERDICT", apply=_append, body=data,
        )
    except Exception as exc:  # noqa: BLE001
        return _as_error_response(db, exc)

    _audit_as(order, "AS_ROUND_VERDICT", user_id, note=verdict, extra={"verdict": verdict})
    entry = captured["entry"]
    html = _render_as_log_entry(entry)  # commit 앞 렌더(append 와 동일 이유)
    db.commit()
    _invalidate_shipment_asrec_caches("api_as_verdict")
    return jsonify({
        "success": True, "entry": entry, "html": html,
        "current_round": captured["current_round"],
    })


@erp_orders_as_bp.route("/<int:order_id>/as/log/<log_id>", methods=["PATCH"])
@login_required
@erp_edit_required
def api_as_log_patch(order_id: int, log_id: str):
    """AS 타임라인 항목 본문 수정. 작성자 본인 또는 관리자만."""
    db = get_db()
    order, err = _load_active_order(db, order_id)
    if err:
        return err
    # legacy는 읽기 전용. 영구화 전(lazy) 항목도 같은 id로 노출되므로 조회 전에 막는다.
    if log_id.startswith("al_legacy_"):
        return jsonify({"success": False, "message": "이전 기록은 수정할 수 없습니다."}), 400

    data = request.get_json(silent=True) or {}
    try:
        text = _clean_as_log_text(data.get("text"))
    except ValueError as ve:
        return jsonify({"success": False, "message": str(ve)}), 400

    user_id = session.get("user_id")
    user = get_user_by_id(user_id)
    log = ((order.structured_data or {}).get("shipment") or {}).get("as_log") or []
    _target, perm_err = _resolve_as_log_entry(log, log_id, user, verb="수정")
    if perm_err:
        return jsonify({"success": False, "message": perm_err[0]}), perm_err[1]

    captured: dict[str, Any] = {}

    def _patch(sd: Dict[str, Any], _order: Order) -> None:
        """잠긴 사본에서 항목을 다시 찾아 본문·수정자를 갱신한다(위 검증과 같은 계약)."""
        entries = (sd.get("shipment") or {}).get("as_log") or []
        locked = next((e for e in entries if isinstance(e, dict) and e.get("id") == log_id), None)
        if locked is None:
            raise ValueError("항목을 찾을 수 없습니다.")
        locked["text"] = text
        locked["edited_at"] = now_utc_naive().isoformat()
        locked["edited_by"] = user.name if user else ""
        captured["entry"] = locked

    try:
        _run_sd_mutation(
            db, order_id=order_id, actor_user_id=user_id, policy_id=POLICY_AS_LOG_PATCH,
            command_id=f"AS_LOG_PATCH:{log_id}", apply=_patch, body=data,
        )
    except Exception as exc:  # noqa: BLE001
        return _as_error_response(db, exc)

    _audit_as(order, "AS_LOG_UPDATED", user_id, extra={"log_id": str(log_id)})
    entry = captured["entry"]
    html = _render_as_log_entry(entry)  # commit 앞 렌더(append와 동일 이유)
    db.commit()
    _invalidate_shipment_asrec_caches("api_as_log_patch")
    return jsonify({"success": True, "entry": entry, "html": html})


@erp_orders_as_bp.route("/<int:order_id>/as/log/<log_id>/delete", methods=["POST"])
@login_required
@erp_edit_required
def api_as_log_delete(order_id: int, log_id: str):
    """AS 타임라인 항목 소프트 삭제. 작성자 본인 또는 관리자만.

    DELETE 메서드·물리 삭제를 쓰지 않는 이유 — as_log 는 AS 분쟁 시 "언제 누가 뭘 했는지"의
    증거라 append-only 가 원칙이다(스펙 §8). 화면과 집계에서만 감추고 원문·작성자·시각은
    sd 에 그대로 남긴다. 감추기는 build_as_timeline_view 한 곳이 담당한다.

    상태축을 건드리지 않으므로 cycle 전이가 아니라 _run_sd_mutation(REV-00)으로 감싼다
    — append·patch 와 같은 계층이다. text 를 만지지 않으므로 sanitize 대상도 아니다.

    Args:
        order_id: 대상 주문 PK.
        log_id: 삭제할 as_log 항목 id.

    Returns:
        {'success': True, 'cell_html': PC 요약 셀 재렌더 HTML}.
    """
    db = get_db()
    order, err = _load_active_order(db, order_id)
    if err:
        return err
    # legacy 는 영구화 전(lazy) 항목도 같은 id 로 노출되므로 조회 전에 막는다(PATCH 와 동일).
    if log_id.startswith("al_legacy_"):
        return jsonify({"success": False, "message": "이전 기록은 삭제할 수 없습니다."}), 400

    user_id = session.get("user_id")
    user = get_user_by_id(user_id)
    log = ((order.structured_data or {}).get("shipment") or {}).get("as_log") or []
    target, perm_err = _resolve_as_log_entry(log, log_id, user, verb="삭제")
    if perm_err:
        return jsonify({"success": False, "message": perm_err[0]}), perm_err[1]
    if target.get("deleted") is True:
        # 멱등: 이미 지운 항목 재요청(연타·뒤늦은 재시도)은 성공으로 흘리고 셀만 다시 준다.
        # mutation 을 돌리지 않으므로 무변경에 REV bump·receipt 를 남기지 않는다.
        return jsonify({
            "success": True,
            "cell_html": _render_as_timeline_cell(order_id, order.structured_data or {}),
        })

    body = request.get_json(silent=True) or {}
    captured: dict[str, Any] = {}

    def _delete(sd: Dict[str, Any], _order: Order) -> None:
        """잠긴 사본에서 항목을 다시 찾아 삭제 플래그만 세운다(위 검증과 같은 계약)."""
        entries = (sd.get("shipment") or {}).get("as_log") or []
        locked = next((e for e in entries if isinstance(e, dict) and e.get("id") == log_id), None)
        if locked is None:
            raise ValueError("항목을 찾을 수 없습니다.")
        locked["deleted"] = True
        locked["deleted_at"] = now_utc_naive().isoformat()
        locked["deleted_by"] = user.name if user else ""
        captured["sd"] = sd

    try:
        _run_sd_mutation(
            db, order_id=order_id, actor_user_id=user_id, policy_id=POLICY_AS_LOG_DELETE,
            command_id=f"AS_LOG_DELETE:{log_id}", apply=_delete, body=body,
        )
    except Exception as exc:  # noqa: BLE001
        return _as_error_response(db, exc)

    _audit_as(order, "AS_LOG_DELETED", user_id, extra={"log_id": str(log_id)})
    cell_html = _render_as_timeline_cell(order_id, captured["sd"])  # commit 앞 렌더
    db.commit()
    _invalidate_shipment_asrec_caches("api_as_log_delete")
    return jsonify({"success": True, "cell_html": cell_html})


# --------------------------------------------------------------------------- #
# AS 기준 일정 매칭 링크(schedule_link) — 매칭 / 재적용 / 무시 / 해제
# --------------------------------------------------------------------------- #
# 스펙: docs/specs/2026-07-30-as-schedule-link-drift-design.md §3·§4·§6.
# 판정·스키마는 순수 서비스(foms/services/orders/as_schedule_link.py)가 SSOT 고,
# 여기서는 검증·기준 주문 재조회·mutation 배선만 한다.
_SCHEDULE_LINK_ACTIONS = ("link", "relink", "ack", "unlink")
_SCHEDULE_LINK_ACTION_LABELS = {
    "link": "매칭", "relink": "재적용", "ack": "무시", "unlink": "해제",
}


def _ref_construction_date(ref: Order) -> str:
    """기준 주문의 **현재** 시공일(Ds). ``erp_construction_date`` 우선, 없으면 ``scheduled_date``.

    Args:
        ref: 기준 주문(활성 확인 완료).

    Returns:
        비어 있지 않은 날짜 문자열.

    Raises:
        ValueError: 두 값 모두 비어 있을 때 — 비교 기준선(D0)이 없으면 드리프트 판정
            자체가 성립하지 않으므로 링크를 만들지 않는다(호출부에서 400).
    """
    for value in (ref.erp_construction_date, ref.scheduled_date):
        text = str(value or "").strip()
        if text:
            return text
    raise ValueError("기준 주문에 시공일이 없어 일정을 매칭할 수 없습니다.")


def _resolve_schedule_link_ref(db: Session, raw_ref_id: object, *, as_order_id: int):
    """기준 주문 id 를 검증·로드하고 서버 기준의 현재 시공일까지 확정한다.

    클라이언트가 보낸 ``ref_date`` 는 채택하지 않는다 — 모달을 열어둔 사이 기준 주문의
    시공일이 바뀌었을 수 있어(stale) 링크의 D0 가 처음부터 틀어진다(스펙 §6).

    Args:
        db: 요청 세션.
        raw_ref_id: 기준 주문 id 원본(요청 body 또는 기존 링크에서 온 값).
        as_order_id: 요청 대상 AS 주문 id(자기 자신 매칭 차단용).

    Returns:
        ``((ref_order_id, ref_date), None)`` 또는 ``(None, (응답, 상태코드))``.
    """
    try:
        ref_id = int(raw_ref_id)
    except (TypeError, ValueError):
        return None, (jsonify({"success": False, "message": "기준 주문 id가 필요합니다."}), 400)
    if ref_id == as_order_id:
        return None, (
            jsonify({"success": False, "message": "자기 자신을 기준으로 매칭할 수 없습니다."}), 400)
    ref, err = _load_active_order(db, ref_id)
    if err:
        return None, (jsonify({"success": False, "message": "기준 주문을 찾을 수 없습니다."}), 404)
    try:
        return (ref_id, _ref_construction_date(ref)), None
    except ValueError as ve:
        return None, (jsonify({"success": False, "message": str(ve)}), 400)


def _plan_schedule_link(db: Session, order: Order, data: Dict[str, Any]):
    """요청을 검증해 실행 계획을 확정한다(쓰기 전 단계 — 잠금 없이 판단 가능한 것만).

    Args:
        db: 요청 세션. order: 대상 AS 주문. data: 요청 body.

    Returns:
        ``((action, ref_order_id, ref_date, 기존 링크), None)`` 또는 ``(None, (응답, 상태코드))``.
        ``unlink`` 는 기준 주문을 조회하지 않으므로 ref 두 값이 None 이다.
    """
    action = str(data.get("action") or "").strip()
    if action not in _SCHEDULE_LINK_ACTIONS:
        return None, (jsonify({"success": False, "message": "지원하지 않는 action 입니다."}), 400)
    existing = read_link(order.structured_data or {})
    if action in ("relink", "ack") and existing is None:
        return None, (jsonify({"success": False, "message": "연결된 기준 일정이 없습니다."}), 409)
    if action == "unlink":
        return (action, None, None, existing), None
    raw_ref = data.get("ref_order_id") if action == "link" else existing.get("ref_order_id")
    resolved, err = _resolve_schedule_link_ref(db, raw_ref, as_order_id=order.id)
    if err:
        return None, err
    return (action, resolved[0], resolved[1], existing), None


def _apply_schedule_link(
    sd: Dict[str, Any], *, action: str, ref_order_id: Optional[int], ref_date: Optional[str],
    user_id: Optional[int], user_name: str,
) -> Dict[str, Any]:
    """잠긴 sd 에 링크 액션을 적용한다(``_run_sd_mutation`` 의 apply 본체).

    ``link``/``unlink`` 만 AS 타임라인에 system 항목을 남긴다 — ``relink``/``ack`` 은
    날짜 자체를 바꾸지 않고(방문일 쓰기는 update_order_field 소관) 노이즈만 늘린다.

    Args:
        sd: 잠긴 주문 structured_data 사본.
        action: ``link``|``relink``|``ack``|``unlink``.
        ref_order_id: 기준 주문 id(unlink 는 None).
        ref_date: 서버가 재조회한 기준 주문 현재 시공일(unlink 는 None).
        user_id: 링크에 남길 actor id. user_name: 링크에 남길 actor 표시명.

    Returns:
        ``{'link': 갱신된 링크 or None, 'cleared': bool, 'as_visit_date': str|None}``.

    Raises:
        ValueError: relink/ack 인데 잠근 뒤 링크가 사라진 경우(경쟁) → 호출부에서 409.
    """
    cleared = False
    if action == "link":
        write_link(sd, ref_order_id=ref_order_id, ref_date=ref_date, source=SOURCE_NEARBY,
                   user_id=user_id, user_name=user_name, now=now_utc_naive())
        append_system_log(sd, text=f"기준 일정 매칭: 주문 #{ref_order_id} ({ref_date})")
    elif action == "relink":
        if not relink(sd, ref_date):
            raise ValueError("연결된 기준 일정이 없습니다.")
    elif action == "ack":
        if not ack_link(sd, ref_date):
            raise ValueError("연결된 기준 일정이 없습니다.")
    else:
        cleared = clear_link(sd)
        if cleared:
            append_system_log(sd, text="기준 일정 매칭 해제")
    return {"link": read_link(sd), "cleared": cleared, "as_visit_date": read_as_visit_date(sd)}


def _schedule_link_payload(
    *, action: str, link: Optional[dict], cleared: bool, ref_date: Optional[str],
    as_visit_date: Optional[str],
) -> Dict[str, Any]:
    """성공 응답 조립 — 링크 + 방금 확정한 기준일 기준의 드리프트 판정.

    Args:
        action: 수행한 액션. link: 갱신 후 링크(없으면 None). cleared: unlink 성사 여부.
        ref_date: 기준 주문의 현재 시공일(Ds). as_visit_date: AS 현재 방문일(Da).

    Returns:
        ``{'success', 'link', 'drift'}`` (+ unlink 는 ``'cleared'``).
    """
    payload: Dict[str, Any] = {
        "success": True,
        "link": link,
        "drift": evaluate_drift(link, ref_current_date=ref_date,
                                as_visit_date=as_visit_date, ref_missing=False),
    }
    if action == "unlink":
        payload["cleared"] = cleared
    return payload


@erp_orders_as_bp.route("/<int:order_id>/as/schedule-link", methods=["POST"])
@login_required
@erp_edit_required
def api_as_schedule_link(order_id: int):
    """AS 기준 일정 링크 쓰기. body ``{action, ref_order_id?, ref_date?}``.

    기준일(D0)은 서버가 기준 주문에서 다시 읽는다 — 클라이언트 ``ref_date`` 는 참고도
    하지 않는다(스펙 §6, stale 방지).

    Args:
        order_id: 대상 AS 주문 PK.

    Returns:
        200 ``{'success', 'link', 'drift'}`` (unlink 는 ``'cleared'`` 포함) /
        400 검증 실패 / 404 기준 주문 없음·삭제됨 / 409 링크 없음·무결성.
    """
    db = get_db()
    order, err = _load_active_order(db, order_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    plan, plan_err = _plan_schedule_link(db, order, data)
    if plan_err:
        return plan_err
    action, ref_id, ref_date, existing = plan
    if action == "unlink" and existing is None:
        # 멱등: 이미 해제된 링크의 재요청에 REV bump·receipt·system 로그를 남기지 않는다
        # (as/log delete 선례 — 무변경에 mutation 을 돌리지 않는다).
        return jsonify(_schedule_link_payload(
            action=action, link=None, cleared=False, ref_date=None,
            as_visit_date=read_as_visit_date(order.structured_data)))
    user_id = session.get("user_id")
    user = get_user_by_id(user_id)
    captured: Dict[str, Any] = {}
    try:
        _run_sd_mutation(
            db, order_id=order_id, actor_user_id=user_id,
            policy_id=POLICY_AS_SCHEDULE_LINK, command_id="AS_SCHEDULE_LINK", body=data,
            apply=lambda sd, _order: captured.update(_apply_schedule_link(
                sd, action=action, ref_order_id=ref_id, ref_date=ref_date,
                user_id=user_id, user_name=(user.name if user else ""))),
        )
    except Exception as exc:  # noqa: BLE001
        return _as_error_response(db, exc)

    _audit_as(order, "AS_SCHEDULE_LINK_CHANGED", user_id,
              note=_SCHEDULE_LINK_ACTION_LABELS[action],
              extra={"link_action": action, "ref_order_id": ref_id, "ref_date": ref_date})
    db.commit()
    _invalidate_shipment_asrec_caches("api_as_schedule_link")
    return jsonify(_schedule_link_payload(
        action=action, link=captured["link"], cleared=captured["cleared"],
        ref_date=ref_date, as_visit_date=captured["as_visit_date"]))


__all__ = [
    "erp_orders_as_bp",
    "api_as_start",
    "api_as_complete",
    "api_as_register",
    "api_as_schedule",
    "api_as_unschedule",
    "api_as_reopen",
    "api_as_classification",
    "api_as_billing",
    "api_as_log_append",
    "api_as_verdict",
    "api_as_log_patch",
    "api_as_log_delete",
    "api_as_schedule_link",
    "get_today_kst",
]
