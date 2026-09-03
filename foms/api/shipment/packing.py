"""ERP 출고 패킹 체크리스트 API. (B6)

스키마: ``sd['shipment']['packing']`` =
``{items:[{key, label, qty, checked, at, by_name, issue, issue_at, issue_by_name}],
updated_at, departed_at, departed_by_name}``. ``issue``는 누락 신고 사유
(``missing``/``damaged``/``short`` 또는 ``None`` 해제)로, 화이트리스트 검증을 거친다.
``departed_at``/``departed_by_name``은 "상차 완료 → 출발 보고"(POST ``{departed: true}``)
로 기록되며, 전 항목 체크가 아니면 서버가 400으로 차단한다(멱등: 재보고 시 갱신).

최초 GET 시 저장된 packing이 없으면 ``sd['items']``에서 파생한다(제품별
"본체 패널 / 도어 / 철물" 3항). 파생 결과는 읽기 시 메모리에만 존재하며,
실제 저장은 첫 POST 때 이뤄진다(JSONB 오염 방지).

JSONB 쓰기는 ``copy.deepcopy`` + ``flag_modified`` + ``db.commit()`` 규약을 따르고,
저장 시 OrderEvent ``PACKING_UPDATED``(출발 보고는 ``PACKING_DEPARTED``)를 남긴다.
"""

from __future__ import annotations

import copy
import datetime
import hashlib
import json
import logging
from functools import wraps
from typing import Any, Callable, List, Mapping, Optional

from flask import jsonify, request, session
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from db import get_db
from foms.api.shipment.settings import erp_shipment_bp
from foms.services.orders.order_mutation_policy import (
    POLICY_REGISTRY,
    evaluate_policy,
    team_has_capability,
)
from foms.services.orders.revision import RevisionError, execute_order_mutation
from foms.web.auth import get_user_by_id, log_access
from foms.services.audit_message_display import describe_order_action
from foms.services.orders.audit_order_context import order_audit_context
from models import Order, OrderEvent

logger = logging.getLogger(__name__)

#: §2.1 canonical packing write 정책(AUTH-01). route manifest·UI 은닉·이 핸들러가 공유한다
#: (CS/SALES/SHIPMENT/CONSTRUCTION team-wide 또는 ADMIN/MANAGER; VIEWER hard deny).
PACKING_WRITE_POLICY_ID = "PACKING_WRITE"


class _PackingGateError(Exception):
    """출발 보고 전제(전 항목 체크) 위반 — mutation 내부에서 raise, 호출부가 400 으로 매핑."""

# 통합 후보: 아래 팀 권한은 향후 erp_permissions.py의 표준 헬퍼/데코레이터로
# 승격할 예정이다. B6 범위에서는 erp_permissions.py를 무터치로 두고 출고 패킹
# 전용 로컬 데코레이터로만 유지한다.
_PACKING_EDIT_ALLOWED_TEAMS = ("CS", "SALES", "SHIPMENT", "CONSTRUCTION")

# 파생 기본 항목: (key 접미사, 라벨 접미사).
_DERIVED_PART_SUFFIXES = (
    ("body", "본체 패널"),
    ("door", "도어"),
    ("hardware", "철물"),
)

# 누락 신고 사유 화이트리스트(허용 값 외 요청은 400). None/"" 는 해제로 취급.
_ALLOWED_ISSUES = frozenset({"missing", "damaged", "short"})


def _can_edit_packing(user: Any) -> bool:
    """출고 패킹 체크리스트를 수정할 수 있는 사용자인지 판정한다.

    Args:
        user: 현재 사용자(``None`` 허용).

    Returns:
        ADMIN 또는 team이 CS/SALES/SHIPMENT/CONSTRUCTION이면 ``True``.
    """
    if not user:
        return False
    if (getattr(user, "role", None) or "").strip().upper() == "ADMIN":
        return True
    return team_has_capability(getattr(user, "team", None), _PACKING_EDIT_ALLOWED_TEAMS)


def _packing_edit_required(f: Callable[..., Any]) -> Callable[..., Any]:
    """출고 패킹 read/write 권한 데코레이터(모듈 로컬 — 통합 후보).

    로그인 세션이 없으면 401, 권한 팀이 아니면 403 JSON을 반환한다.
    """

    @wraps(f)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        user = get_user_by_id(session.get("user_id"))
        if not user:
            return jsonify({"success": False, "error": "로그인이 필요합니다."}), 401
        if not _can_edit_packing(user):
            return jsonify({"success": False, "error": "출고 패킹 수정 권한이 없습니다."}), 403
        return f(*args, **kwargs)

    return wrapped


def _derive_packing_items(sd: dict[str, Any]) -> list[dict[str, Any]]:
    """``sd['items']``에서 기본 패킹 항목을 파생한다(제품별 3항).

    Args:
        sd: 주문 structured_data.

    Returns:
        제품마다 "본체 패널 / 도어 / 철물" 3개 행을 담은 리스트. items가
        없으면 빈 리스트.
    """
    items = sd.get("items")
    derived: list[dict[str, Any]] = []
    if not isinstance(items, list):
        return derived
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        name = (item.get("product_name") or item.get("name") or "").strip() or f"제품 {idx + 1}"
        for suffix_key, suffix_label in _DERIVED_PART_SUFFIXES:
            derived.append(
                {
                    "key": f"item{idx}_{suffix_key}",
                    "label": f"{name} {suffix_label}",
                    "qty": 1,
                    "checked": False,
                    "at": None,
                    "by_name": None,
                    "issue": None,
                }
            )
    return derived


def _load_packing_items(sd: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    """저장된 패킹 items를 반환한다. 없으면 파생(저장 안 함).

    Returns:
        ``(items, persisted)`` — persisted가 ``False``면 파생 결과.
    """
    shipment = sd.get("shipment")
    if isinstance(shipment, dict):
        packing = shipment.get("packing")
        if isinstance(packing, dict) and isinstance(packing.get("items"), list):
            return packing["items"], True
    return _derive_packing_items(sd), False


def _packing_payload(
    items: list[dict[str, Any]],
    persisted: bool,
    departed_at: str | None = None,
    departed_by_name: str | None = None,
) -> dict[str, Any]:
    """API 응답 data 블록을 구성한다(출발 보고 상태 departed_* 포함)."""
    checked = sum(1 for it in items if isinstance(it, dict) and it.get("checked"))
    issues = sum(1 for it in items if isinstance(it, dict) and it.get("issue"))
    return {
        "items": items,
        "checked_count": checked,
        "issues_count": issues,
        "total": len(items),
        "persisted": persisted,
        "departed_at": departed_at,
        "departed_by_name": departed_by_name,
    }


@erp_shipment_bp.route("/api/erp/shipment/packing/<int:order_id>", methods=["GET"])
@_packing_edit_required
def api_shipment_packing_get(order_id: int):
    """출고 패킹 체크리스트 조회(없으면 items[]에서 파생, 저장하지 않음)."""
    db = get_db()
    order = db.query(Order).filter(Order.id == order_id, Order.active_filter()).first()
    if not order:
        return jsonify({"success": False, "error": "주문을 찾을 수 없습니다."}), 404
    sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    items, persisted = _load_packing_items(sd)
    shipment = sd.get("shipment") if isinstance(sd, dict) else None
    packing = shipment.get("packing") if isinstance(shipment, dict) else None
    departed_at = packing.get("departed_at") if isinstance(packing, dict) else None
    departed_by_name = packing.get("departed_by_name") if isinstance(packing, dict) else None
    return jsonify(
        {"success": True, "data": _packing_payload(items, persisted, departed_at, departed_by_name)}
    )


def _mutation_hashes(
    order_id: int, updates: Any, add: Any, departed_flag: bool
) -> tuple[str, str]:
    """(scope_hash, request_hash) — receipt 저장·same-key/different-hash 감지용 sha256."""
    scope = hashlib.sha256(f"{PACKING_WRITE_POLICY_ID}:{order_id}".encode()).hexdigest()
    request_payload = json.dumps(
        {"updates": updates, "add": add, "departed": departed_flag},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return scope, hashlib.sha256(request_payload.encode()).hexdigest()


@erp_shipment_bp.route("/api/erp/shipment/packing/<int:order_id>", methods=["POST"])
def api_shipment_packing_save(order_id: int):
    """패킹 제출을 정본 command 로 원자 기록한다(REV-00 one-tx).

    packing 갱신(체크/항목 추가/출발 보고)을 REV-00 :func:`execute_order_mutation` 경유로
    §2.1 policy(``PACKING_WRITE``) + If-Match(mutation_version 낙관 잠금) + version bump +
    idempotency receipt + OrderEvent 를 **한 transaction** 에 묶는다. 같은 ``Idempotency-Key``
    재요청은 replay(중복 제출 0)로 수렴한다.

    Body: ``{updates?, add?, departed?}``. optional 헤더 ``If-Match``·``Idempotency-Key``.
    반환: ``{success, data:{...packing payload, mutation_receipt}}`` + ``Cache-Control: no-store``.
    """
    db: Session = get_db()

    # 1) §2.1 canonical 권한 — PACKING_WRITE. AUTH-01 before_request 가드가 꺼진 컨텍스트
    #    (TESTING 등)에서도 payload 파싱 전에 항상 enforce 한다(우회 차단).
    user = get_user_by_id(session.get("user_id"))
    decision = evaluate_policy(POLICY_REGISTRY[PACKING_WRITE_POLICY_ID], user)
    if not decision.allowed:
        return jsonify({
            "success": False,
            "data": None,
            "error": decision.reason,
            "message": decision.reason,
            "code": decision.code,
        }), decision.status

    # 2) payload 검증(기존 계약 유지).
    payload = request.get_json(silent=True) or {}
    updates = payload.get("updates")
    add = payload.get("add")
    departed_flag = bool(payload.get("departed"))
    if updates is None and add is None and not departed_flag:
        return jsonify({"success": False, "error": "updates·add·departed 중 하나가 필요합니다."}), 400
    if updates is not None and not isinstance(updates, list):
        return jsonify({"success": False, "error": "updates는 배열이어야 합니다."}), 400
    if add is not None and not isinstance(add, dict):
        return jsonify({"success": False, "error": "add는 객체여야 합니다."}), 400

    # 누락 사유(issue) 화이트리스트 검증(허용: missing/damaged/short, 또는 해제용 null/"").
    for upd in updates or []:
        if isinstance(upd, dict) and "issue" in upd:
            issue_val = upd.get("issue")
            if issue_val not in (None, "") and issue_val not in _ALLOWED_ISSUES:
                return jsonify({"success": False, "error": "허용되지 않은 issue 값입니다."}), 400

    add_label = ""
    add_qty = 1
    if add is not None:
        add_label = str(add.get("label") or "").strip()
        if not add_label:
            return jsonify({"success": False, "error": "추가 항목 label이 필요합니다."}), 400
        try:
            add_qty = int(add.get("qty") or 1)
        except (TypeError, ValueError):
            add_qty = 1
        if add_qty <= 0:
            add_qty = 1

    order = db.query(Order).filter(Order.id == order_id, Order.active_filter()).first()
    if not order:
        return jsonify({"success": False, "error": "주문을 찾을 수 없습니다."}), 404

    # 3) optional If-Match(mutation_version) — 형식 오류는 삼키지 않고 400.
    if_match_raw = (request.headers.get("If-Match") or "").strip().strip('"')
    expected_versions: Optional[Mapping[int, int]] = None
    if if_match_raw:
        try:
            expected_versions = {order_id: int(if_match_raw)}
        except ValueError:
            return jsonify({"success": False, "error": "If-Match 형식이 올바르지 않습니다."}), 400
    idempotency_key = (request.headers.get("Idempotency-Key") or "").strip() or None

    user_id = getattr(user, "id", None)
    by_name = (getattr(user, "name", None) or getattr(user, "username", None) or "").strip()
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    scope_hash, request_hash = _mutation_hashes(order_id, updates, add, departed_flag)
    captured: dict[str, Any] = {}

    def _mutate(sess: Session, orders: List[Order]) -> Mapping[int, List[str]]:
        """row lock 아래에서 packing JSONB 갱신 + OrderEvent parity(다른 축 불변)."""
        o = orders[0]
        sd = copy.deepcopy(o.structured_data if isinstance(o.structured_data, dict) else {})
        shipment = sd.get("shipment")
        if not isinstance(shipment, dict):
            shipment = {}
            sd["shipment"] = shipment
        packing = shipment.get("packing")
        if not isinstance(packing, dict) or not isinstance(packing.get("items"), list):
            packing = {"items": _derive_packing_items(sd), "updated_at": None}
            shipment["packing"] = packing
        items = packing["items"]
        by_key = {it.get("key"): it for it in items if isinstance(it, dict)}

        for upd in updates or []:
            if not isinstance(upd, dict):
                continue
            row = by_key.get(upd.get("key"))
            if row is None:
                continue
            # checked 와 issue 는 독립 필드 — 있는 키만 갱신(부분 업데이트로 서로 덮어쓰지 않음).
            if "checked" in upd:
                checked = bool(upd.get("checked"))
                row["checked"] = checked
                row["at"] = now_iso if checked else None
                row["by_name"] = by_name if checked else None
            if "issue" in upd:
                issue_val = upd.get("issue")
                if issue_val in (None, ""):
                    row["issue"] = None
                    row["issue_at"] = None
                    row["issue_by_name"] = None
                else:
                    row["issue"] = issue_val
                    row["issue_at"] = now_iso
                    row["issue_by_name"] = by_name

        if add_label:
            new_key = f"custom_{int(datetime.datetime.now().timestamp() * 1000)}_{len(items)}"
            items.append(
                {
                    "key": new_key,
                    "label": add_label,
                    "qty": add_qty,
                    "checked": False,
                    "at": None,
                    "by_name": None,
                    "issue": None,
                }
            )

        packing["updated_at"] = now_iso
        checked_count = sum(1 for it in items if it.get("checked"))
        issues_count = sum(1 for it in items if it.get("issue"))
        total = len(items)

        event_type = "PACKING_UPDATED"
        if departed_flag:
            # 서버 게이트: 전 항목 체크 없이는 출발 보고 불가(클라 disabled 우회 차단).
            # lock 아래에서 판정 → 호출부가 rollback 후 400(상태 미저장).
            if total == 0 or checked_count < total:
                raise _PackingGateError("전 항목 체크 후 출발 보고")
            # 멱등: 이미 departed여도 타임스탬프·담당을 재기록(재보고=갱신).
            packing["departed_at"] = now_iso
            packing["departed_by_name"] = by_name
            event_type = "PACKING_DEPARTED"

        o.structured_data = sd
        flag_modified(o, "structured_data")
        sess.add(
            OrderEvent(
                order_id=o.id,
                event_type=event_type,
                payload={
                    "checked_count": checked_count,
                    "total": total,
                    "issues_count": issues_count,
                },
                created_by_user_id=user_id,
            )
        )
        captured["items"] = items
        captured["departed_at"] = packing.get("departed_at")
        captured["departed_by_name"] = packing.get("departed_by_name")
        return {o.id: [f"ORDER_DETAIL:{o.id}", "ORDERS_INDEX"]}

    # 4) REV-00 one-tx: policy(위)+If-Match+FOR UPDATE+version bump+idempotency+receipt+event.
    try:
        outcome = execute_order_mutation(
            db,
            actor_user_id=user_id,
            policy_id=PACKING_WRITE_POLICY_ID,
            order_ids=[order_id],
            expected_versions=expected_versions,
            idempotency_key=idempotency_key,
            scope_hash=scope_hash,
            request_hash=request_hash,
            mutation=_mutate,
        )
        packing_context = order_audit_context(order)
        log_access(
            describe_order_action(order_id=order_id, action="SHIPMENT_PACKING_SAVED",
                                  **packing_context),
            getattr(user, "id", None),
            auto_commit=False,
            action="SHIPMENT_PACKING_SAVED", target_type="order", target_id=int(order_id),
            detail=packing_context,
        )
        db.commit()
    except _PackingGateError as gate:
        db.rollback()
        return jsonify({"success": False, "error": str(gate)}), 400
    except RevisionError as rev:
        db.rollback()
        return jsonify({"success": False, "error": str(rev), "code": rev.error_code}), rev.status_code
    except Exception as exc:  # noqa: BLE001 - 상위에서 롤백 후 500 반환
        db.rollback()
        logger.exception("[SHIPMENT_PACKING] save error: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 500

    if outcome.replayed:  # same-key replay: 저장된 write 를 재조회해 응답 재구성(중복 제출 0).
        fresh = db.query(Order).filter(Order.id == order_id).first()
        sd = fresh.structured_data if isinstance(fresh.structured_data, dict) else {}
        items, _ = _load_packing_items(sd)
        packing = (sd.get("shipment") or {}).get("packing") or {}
        data = _packing_payload(
            items, True, packing.get("departed_at"), packing.get("departed_by_name")
        )
    else:
        data = _packing_payload(
            captured["items"], True, captured.get("departed_at"), captured.get("departed_by_name")
        )
    data["mutation_receipt"] = outcome.read_receipt_id

    resp = jsonify({"success": True, "data": data})
    for header, value in outcome.headers.items():
        resp.headers[header] = value
    return resp
