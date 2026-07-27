"""Shipment dashboard AS schedule recommendation batch + apply/cancel APIs."""

from __future__ import annotations

import logging
from typing import Any

from copy import deepcopy

from flask import g, jsonify, request, session
from sqlalchemy.orm import load_only

from db import get_db
from foms.api.shipment.settings import erp_shipment_bp
from foms.services.common.address_converter import FOMSAddressConverter
from foms.services.erp_permissions import erp_edit_required
from foms.services.geocode_helpers import get_order_display_address
from foms.services.schedule_recommendations import (
    get_order_display_customer_name,
    recommend_nearby_schedules_for_targets,
)
from foms.services.shipment_as_recommendation_cache import (
    build_target_cache_key,
    get_cached_target,
    get_or_compute_candidate_pool,
    invalidate_shipment_as_recommendation_cache,
    make_route_provider,
    set_cached_target,
)
from foms.services.common.dashboard_cache import (
    DASHBOARD_FAMILY_ORDERS,
    DASHBOARD_FAMILY_SHIPMENT,
    invalidate_dashboard_families,
)
from foms.services.orders.as_cycle_service import ASCycleError
from foms.services.orders.order_mutation_policy import POLICY_REGISTRY, evaluate_policy
from foms.services.shipment.as_recommendation import (
    ASRecommendationError,
    apply_as_recommendation,
    cancel_as_recommendation,
)
from foms.web.auth import get_user_by_id, login_required, role_required
from models import InstallationWorker, Order, SecurityLog

logger = logging.getLogger(__name__)

SHREC_SOURCE = "shipment_dashboard_as_recommendation"
AS_STATUSES = ("AS", "AS_RECEIVED")
SHIPMENT_AS_ROW_STATUSES = ("AS", "AS_RECEIVED", "AS_COMPLETED")

RULE_VERSION = "shipment_asrec_target_v3:duration30:limit2:route10:unscheduled-only:map-coords"


def _invalidate_asrec_after_commit(reason: str) -> None:
    """Best-effort AS recommendation cache bust after DB writes."""
    try:
        invalidate_shipment_as_recommendation_cache(reason=reason)
    except Exception:
        logger.warning("[AS-REC] shipment recommendation cache invalidate failed", exc_info=True)


def _invalidate_dashboard_after_commit() -> None:
    # 도메인-스코프: AS 추천 적용/취소는 schedule.as_visit.shipment_recommendation만
    # 기록하고 workflow.stage는 바꾸지 않는다 → 출고 대시보드(추천 행)와 주문 목록만
    # 무효화한다.
    try:
        invalidate_dashboard_families(DASHBOARD_FAMILY_SHIPMENT, DASHBOARD_FAMILY_ORDERS)
    except Exception:
        logger.warning("[AS-REC] dashboard slice cache invalidate failed", exc_info=True)


def _build_targets_for_order_ids(db, order_ids: list[int]) -> list[dict[str, Any]]:
    """Build shipment target rows for recommendation (same shape as legacy API)."""
    shipment_orders = _load_orders_map(db, order_ids)
    targets_in: list[dict[str, Any]] = []
    for oid in order_ids:
        order = shipment_orders.get(oid)
        if not order or not _is_valid_shipment_target(order):
            continue
        cdate = _shipment_construction_date(order)
        workers = _shipment_workers(order)
        row: dict[str, Any] = {
            "order_id": oid,
            "customer_name": get_order_display_customer_name(order),
            "address": get_order_display_address(order),
            "target_date": cdate,
            "workers": workers,
        }
        if order.lat and order.lng and order.geocode_status == "success":
            row["cached_lat"] = float(order.lat)
            row["cached_lng"] = float(order.lng)
        targets_in.append(row)
    return targets_in


def _compute_recommendation_payload(
    *,
    db,
    order_ids: list[int],
    selected_date: str | None,
    return_targets: bool,
) -> dict[str, Any]:
    """
    Shared core for GET-like recommendation + prewarm.
    Candidate pool cache + per-target cache + route_provider injection.
    """
    converter = FOMSAddressConverter()
    pool, pool_stats = get_or_compute_candidate_pool(
        db,
        converter,
        source_value=SHREC_SOURCE,
        as_statuses=AS_STATUSES,
        log_warning=logger.warning,
    )
    link_as_to_shipment = {}
    raw_link = pool.get("link_as_to_shipment") or {}
    for k, v in raw_link.items():
        try:
            link_as_to_shipment[int(k)] = int(v)
        except (TypeError, ValueError):
            continue

    candidates_in = pool.get("candidates") or []
    pool_version = str(pool.get("pool_version") or "")

    targets_in = _build_targets_for_order_ids(db, order_ids)
    cache_meta: dict[str, Any] = {
        "candidate_pool_hit": bool(pool_stats.get("candidate_pool_hit")),
        "candidate_count": int(pool_stats.get("candidate_count") or 0),
        "target_hits": 0,
        "target_misses": 0,
        "route_hits": 0,
        "route_misses": 0,
        "prewarmed": False,
    }

    route_stats: dict[str, Any] = {"route_hits": 0, "route_misses": 0}
    route_provider = make_route_provider(converter, route_stats, log_warning=logger.warning)

    hits: dict[int, dict[str, Any]] = {}
    miss_list: list[dict[str, Any]] = []
    for tgt in targets_in:
        oid = int(tgt["order_id"])
        ck = build_target_cache_key(tgt, pool_version, RULE_VERSION)
        cached = get_cached_target(ck)
        if cached:
            hits[oid] = deepcopy(cached)
            cache_meta["target_hits"] += 1
        else:
            miss_list.append(tgt)
            cache_meta["target_misses"] += 1

    merged_miss: dict[int, dict[str, Any]] = {}
    partial_all = False
    warnings_all: list[str] = []

    if miss_list:
        chunk_size = 5
        for i in range(0, len(miss_list), chunk_size):
            chunk = miss_list[i : i + chunk_size]
            batch = recommend_nearby_schedules_for_targets(
                converter=converter,
                targets=chunk,
                candidates=candidates_in,
                route_provider=route_provider,
                reference_date=selected_date,
                include_workers=True,
                log_warning=logger.warning,
            )
            partial_all = partial_all or bool(batch.get("partial"))
            warnings_all.extend(list(batch.get("warnings") or []))
            for src_tgt, tgt_row in zip(chunk, batch.get("targets") or []):
                oid = int(tgt_row["order_id"])
                merged_miss[oid] = tgt_row
                ck = build_target_cache_key(src_tgt, pool_version, RULE_VERSION)
                to_store = deepcopy(tgt_row)
                to_store.pop("linked_as_schedules", None)
                set_cached_target(ck, to_store)

    cache_meta["route_hits"] = int(route_stats.get("route_hits") or 0)
    cache_meta["route_misses"] = int(route_stats.get("route_misses") or 0)

    final_targets: list[dict[str, Any]] = []
    for tgt in targets_in:
        oid = int(tgt["order_id"])
        row = hits.get(oid) or merged_miss.get(oid)
        if row is None:
            final_targets.append(
                {
                    "order_id": oid,
                    "customer_name": tgt.get("customer_name") or "",
                    "address": (tgt.get("address") or "").strip(),
                    "target_date": tgt.get("target_date") or "",
                    "workers": list(tgt.get("workers") or []),
                    "recommendations": [],
                    "linked_as_schedules": [],
                    "message": "추천 결과를 만들 수 없습니다.",
                }
            )
            continue
        final_targets.append(deepcopy(row))

    for tgt in final_targets:
        tgt.pop("linked_as_schedules", None)

    _enrich_recommendations(final_targets, link_as_to_shipment)
    linked_by = _build_linked_schedules_for_targets(db, order_ids, link_as_to_shipment)
    for tgt in final_targets:
        tgt["linked_as_schedules"] = linked_by.get(int(tgt["order_id"]), [])

    out_targets = final_targets if return_targets else []
    return {
        "targets": out_targets,
        "targets_len": len(final_targets),
        "partial": partial_all,
        "warnings": warnings_all,
        "cache": cache_meta,
    }


def _construction_team_forbidden() -> Any | None:
    user = getattr(g, "current_user", None)
    if user and getattr(user, "team", None) == "CONSTRUCTION":
        return jsonify(
            {"success": False, "message": "시공팀은 출고 데이터를 수정할 수 없습니다."}
        ), 403
    return None


def _shipment_construction_date(order: Order) -> str:
    sd = getattr(order, "structured_data", None) or {}
    if order.is_erp_order and isinstance(sd, dict):
        cons = (sd.get("schedule") or {}).get("construction") or {}
        d = (cons.get("date") or "").strip()
        if d:
            return str(d)
    if getattr(order, "scheduled_date", None):
        return str(order.scheduled_date)
    return ""


def _shipment_workers(order: Order) -> list[str]:
    sd = getattr(order, "structured_data", None) or {}
    if not isinstance(sd, dict):
        return []
    workers = (sd.get("shipment") or {}).get("construction_workers") or []
    if not isinstance(workers, list):
        return []
    return [str(w).strip() for w in workers if str(w).strip()]


def _open_as_entries(sd: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for entry in sd.get("as_info") or []:
        if isinstance(entry, dict) and entry.get("status") == "OPEN":
            out.append(entry)
    return out


def _candidate_as_info_id(sd: dict[str, Any]) -> tuple[int | None, bool]:
    open_ = _open_as_entries(sd)
    if len(open_) == 1:
        rid = open_[0].get("id")
        return (int(rid) if rid is not None else None, False)
    if len(open_) > 1:
        return (None, True)
    return (None, False)


def _as_sort_date(order: Order, sd: dict[str, Any]) -> str:
    open_ = _open_as_entries(sd)
    if open_:
        started = open_[0].get("started_at") or ""
        if started:
            return str(started)[:10]
    su = getattr(order, "structured_updated_at", None)
    if su is not None:
        return str(su)[:10]
    ca = getattr(order, "created_at", None)
    if ca is not None:
        return str(ca)[:10]
    return "9999-99-99"


def _visit_date_str(order: Order, sd: dict[str, Any]) -> str:
    av = (sd.get("schedule") or {}).get("as_visit") or {}
    if isinstance(av, dict):
        return str(av.get("date") or "").strip()
    return ""


def _shipment_rec_meta(sd: dict[str, Any]) -> dict[str, Any] | None:
    av = (sd.get("schedule") or {}).get("as_visit") or {}
    if not isinstance(av, dict):
        return None
    meta = av.get("shipment_recommendation")
    return meta if isinstance(meta, dict) else None


def _is_valid_shipment_target(order: Order) -> bool:
    if order.status == "DELETED" or order.deleted_at is not None:
        return False
    if order.status in SHIPMENT_AS_ROW_STATUSES:
        return False
    return True


def _load_orders_map(db, ids: list[int]) -> dict[int, Order]:
    if not ids:
        return {}
    rows = (
        db.query(Order)
        .options(
            load_only(
                Order.id,
                Order.status,
                Order.deleted_at,
                Order.address,
                Order.is_erp_order,
                Order.structured_data,
                Order.customer_name,
                Order.lat,
                Order.lng,
                Order.geocode_status,
                Order.scheduled_date,
            )
        )
        .filter(Order.id.in_(ids), Order.active_filter())
        .all()
    )
    return {o.id: o for o in rows}


def _enrich_recommendations(
    targets_payload: list[dict[str, Any]],
    link_as_to_shipment: dict[int, int],
) -> None:
    for tgt in targets_payload:
        sid = int(tgt["order_id"])
        for rec in tgt.get("recommendations") or []:
            aid = int(rec["as_order_id"])
            linked = link_as_to_shipment.get(aid)
            rec["linked_from_shipment_order_id"] = (
                linked if linked is not None and linked != sid else None
            )
            rec["can_cancel_link"] = bool(linked is not None and linked == sid)


def _worker_names(db, worker_ids: list) -> list[str]:
    """crew worker_id 목록을 display_name 으로 해석한다(연결 표시용)."""
    ids = [int(w) for w in worker_ids if w is not None]
    if not ids:
        return []
    rows = db.query(InstallationWorker).filter(InstallationWorker.id.in_(ids)).all()
    name_by_id = {w.id: w.display_name for w in rows}
    return [name_by_id[i] for i in ids if i in name_by_id]


def _build_linked_schedules_for_targets(
    db,
    shipment_ids: list[int],
    link_map: dict[int, int],
) -> dict[int, list[dict[str, Any]]]:
    """각 출고 target 의 연결된 AS 추천 목록을 출고 Order snapshot 에서 만든다.

    추천 snapshot 은 canonical 하게 출고 Order ``sd.shipment.recommendations``(as_order_id
    keyed list)에 보존되므로, 각 출고건의 snapshot 을 읽어 연결 AS 표시 정보를 만든다.
    ``link_map`` 은 하위호환 시그니처 유지용(미사용).

    Args:
        db: DB 세션.
        shipment_ids: 출고 대상 주문 id 목록.
        link_map: (미사용) AS→출고 역인덱스.

    Returns:
        ``{shipment_id: [{as_order_id, customer_name, applied_date, applied_workers, ...}]}``.
    """
    ships = _load_orders_map(db, shipment_ids)
    per_ship_recs: dict[int, list[dict[str, Any]]] = {}
    as_ids: list[int] = []
    for sid in shipment_ids:
        ship = ships.get(sid)
        sd = ship.structured_data if ship and isinstance(ship.structured_data, dict) else {}
        recs = [
            r for r in ((sd.get("shipment") or {}).get("recommendations") or [])
            if isinstance(r, dict) and r.get("as_order_id") is not None
        ]
        per_ship_recs[sid] = recs
        as_ids.extend(int(r["as_order_id"]) for r in recs)
    as_orders = _load_orders_map(db, as_ids)
    by_shipment: dict[int, list[dict[str, Any]]] = {sid: [] for sid in shipment_ids}
    for sid in shipment_ids:
        for rec in per_ship_recs.get(sid, []):
            aid = int(rec["as_order_id"])
            as_order = as_orders.get(aid)
            if not as_order:
                continue
            by_shipment[sid].append(
                {
                    "as_order_id": aid,
                    "customer_name": get_order_display_customer_name(as_order),
                    "as_info_id": rec.get("as_cycle_id"),
                    "applied_date": str(rec.get("applied_visit_date") or ""),
                    "applied_workers": _worker_names(db, rec.get("applied_crew_ids") or []),
                    "can_cancel_link": True,
                }
            )
    return by_shipment


@erp_shipment_bp.route("/api/erp/shipment/as-recommendations", methods=["POST"])
@login_required
@erp_edit_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def api_shipment_as_recommendations():
    blocked = _construction_team_forbidden()
    if blocked:
        return blocked
    payload = request.get_json(silent=True) or {}
    raw_ids = payload.get("order_ids") or []
    selected_raw = payload.get("selected_date")
    selected_date: str | None = None
    if selected_raw is not None and str(selected_raw).strip():
        selected_date = str(selected_raw).strip()
    if not isinstance(raw_ids, list) or not raw_ids:
        return jsonify({"success": False, "message": "order_ids가 필요합니다."}), 400
    try:
        order_ids = sorted({int(x) for x in raw_ids})
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "order_ids 형식이 올바르지 않습니다."}), 400

    db = get_db()
    body = _compute_recommendation_payload(
        db=db,
        order_ids=order_ids,
        selected_date=selected_date,
        return_targets=True,
    )
    return jsonify(
        {
            "success": True,
            "per_target_limit": 2,
            "duration_limit_min": 30,
            "partial": body["partial"],
            "warnings": body["warnings"],
            "cache": body["cache"],
            "targets": body["targets"],
        }
    )


@erp_shipment_bp.route("/api/erp/shipment/as-recommendations/prewarm", methods=["POST"])
@login_required
@erp_edit_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def api_shipment_as_recommendations_prewarm():
    blocked = _construction_team_forbidden()
    if blocked:
        return blocked
    payload = request.get_json(silent=True) or {}
    raw_ids = payload.get("order_ids") or []
    selected_raw = payload.get("selected_date")
    selected_date: str | None = None
    if selected_raw is not None and str(selected_raw).strip():
        selected_date = str(selected_raw).strip()
    if not isinstance(raw_ids, list) or not raw_ids:
        return jsonify({"success": False, "message": "order_ids가 필요합니다."}), 400
    try:
        order_ids = sorted({int(x) for x in raw_ids})
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "order_ids 형식이 올바르지 않습니다."}), 400

    db = get_db()
    body = _compute_recommendation_payload(
        db=db,
        order_ids=order_ids,
        selected_date=selected_date,
        return_targets=False,
    )
    warmed = int(body.get("targets_len") or 0)
    cache = dict(body["cache"])
    cache["prewarmed"] = True
    return jsonify({"success": True, "warmed_targets": warmed, **cache})


def _shipment_edit_decision() -> tuple[Any, Any]:
    """SHIPMENT_EDIT(per-order 출고 쓰기) 권한을 in-handler 로 강제한다(가드 off 우회 차단)."""
    user = get_user_by_id(session.get("user_id"))
    return user, evaluate_policy(POLICY_REGISTRY["SHIPMENT_EDIT"], user)


def _policy_denied(decision: Any):
    """정책 거부 응답(JSON 401/403)."""
    return jsonify({
        "success": False, "data": None,
        "error": decision.reason, "message": decision.reason, "code": decision.code,
    }), decision.status


def _opt_int(value: Any) -> int | None:
    """optional 정수 파싱(None/빈 값/형식오류 → None)."""
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@erp_shipment_bp.route("/api/erp/shipment/as-recommendations/apply", methods=["POST"])
@login_required
@erp_edit_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def api_shipment_as_recommendations_apply():
    """출고 시공일/작업자를 AS 건에 canonical command 로 반영한다(SHIPMENT-WRITER-01).

    권한(SHIPMENT_EDIT)·시공팀 차단 후 :func:`apply_as_recommendation` 오케스트레이터에
    위임한다: 두 Order ID 순 lock·If-Match·as_cycle_service schedule·crew replace·출고
    snapshot 을 한 tx 에 처리한다(name-array/AS info direct write·blind overwrite 없음).
    """
    blocked = _construction_team_forbidden()
    if blocked:
        return blocked
    _, decision = _shipment_edit_decision()
    if not decision.allowed:
        return _policy_denied(decision)
    data = request.get_json(silent=True) or {}
    try:
        shipment_order_id = int(data.get("shipment_order_id"))
        as_order_id = int(data.get("as_order_id"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "요청 본문이 올바르지 않습니다."}), 400

    db = get_db()
    try:
        result = apply_as_recommendation(
            db, shipment_order_id=shipment_order_id, as_order_id=as_order_id,
            actor_user_id=session.get("user_id"), cycle_id=(data.get("cycle_id") or None),
            shipment_version=_opt_int(data.get("shipment_version")),
            as_version=_opt_int(data.get("as_version")), force=bool(data.get("force")),
            source_screen="erp_shipment_dashboard",
        )
        db.add(SecurityLog(
            user_id=session.get("user_id"),
            message=(
                f"출고 대시보드 AS 추천 적용: 출고 #{shipment_order_id} → "
                f"AS #{as_order_id} ({result['applied_date']})"
            ),
        ))
        db.commit()
    except (ASRecommendationError, ASCycleError) as err:
        db.rollback()
        return jsonify({"success": False, "message": str(err)}), getattr(err, "status_code", 409)
    except Exception as exc:
        db.rollback()
        logger.exception("[AS-REC] apply 실패: %s", exc)
        return jsonify({"success": False, "message": str(exc)}), 500

    _invalidate_dashboard_after_commit()
    _invalidate_asrec_after_commit("shipment_as_recommendations_apply")
    return jsonify({"success": True, "message": "AS 일정이 출고 일정에 추가되었습니다.", **result})


@erp_shipment_bp.route("/api/erp/shipment/as-recommendations/cancel", methods=["POST"])
@login_required
@erp_edit_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def api_shipment_as_recommendations_cancel():
    """추천으로 반영한 AS 방문일/작업자를 이전 snapshot 으로 복원한다(SHIPMENT-WRITER-01).

    권한(SHIPMENT_EDIT)·시공팀 차단 후 :func:`cancel_as_recommendation` 오케스트레이터에
    위임한다: 출고 snapshot 을 찾아 후속 수동 변경이 없을 때만 typed compensation
    (as_cycle_service + crew replace)으로 복원하고 snapshot 을 제거한다.
    """
    blocked = _construction_team_forbidden()
    if blocked:
        return blocked
    _, decision = _shipment_edit_decision()
    if not decision.allowed:
        return _policy_denied(decision)
    data = request.get_json(silent=True) or {}
    try:
        shipment_order_id = int(data.get("shipment_order_id"))
        as_order_id = int(data.get("as_order_id"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "요청 본문이 올바르지 않습니다."}), 400

    db = get_db()
    try:
        result = cancel_as_recommendation(
            db, shipment_order_id=shipment_order_id, as_order_id=as_order_id,
            actor_user_id=session.get("user_id"), cycle_id=(data.get("cycle_id") or None),
            recommendation_transition_id=_opt_int(data.get("recommendation_transition_id")),
            shipment_version=_opt_int(data.get("shipment_version")),
            as_version=_opt_int(data.get("as_version")),
        )
        db.add(SecurityLog(
            user_id=session.get("user_id"),
            message=f"출고 대시보드 AS 추천 취소: 출고 #{shipment_order_id} → AS #{as_order_id}",
        ))
        db.commit()
    except (ASRecommendationError, ASCycleError) as err:
        db.rollback()
        return jsonify({"success": False, "message": str(err)}), getattr(err, "status_code", 409)
    except Exception as exc:
        db.rollback()
        logger.exception("[AS-REC] cancel 실패: %s", exc)
        return jsonify({"success": False, "message": str(exc)}), 500

    _invalidate_dashboard_after_commit()
    _invalidate_asrec_after_commit("shipment_as_recommendations_cancel")
    return jsonify({"success": True, "message": "AS 일정이 출고 일정에서 삭제되었습니다.", **result})
