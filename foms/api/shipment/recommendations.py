"""Shipment dashboard AS schedule recommendation batch + apply/cancel APIs."""

from __future__ import annotations

import copy
import datetime as dt
import logging
from typing import Any

from flask import g, jsonify, request, session
from sqlalchemy.orm import load_only
from sqlalchemy.orm.attributes import flag_modified

from db import get_db
from foms.api.shipment.settings import erp_shipment_bp
from foms.services.common.address_converter import FOMSAddressConverter
from foms.services.as_content_safety import load_structured_data_dict_or_raise
from foms.services.erp_permissions import erp_edit_required
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.order_date_sync import _normalize_date_str
from foms.services.geocode_helpers import get_order_display_address
from foms.services.schedule_recommendations import (
    get_order_display_customer_name,
    recommend_nearby_schedules_for_targets,
)
from foms.web.auth import login_required, role_required
from models import Order, OrderEvent, SecurityLog

logger = logging.getLogger(__name__)

SHREC_SOURCE = "shipment_dashboard_as_recommendation"
AS_STATUSES = ("AS", "AS_RECEIVED")
SHIPMENT_AS_ROW_STATUSES = ("AS", "AS_RECEIVED", "AS_COMPLETED")


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


def _build_linked_schedules_for_targets(
    db,
    shipment_ids: list[int],
    link_map: dict[int, int],
) -> dict[int, list[dict[str, Any]]]:
    as_ids = [aid for aid, sid in link_map.items() if sid in shipment_ids]
    if not as_ids:
        return {sid: [] for sid in shipment_ids}
    orders = _load_orders_map(db, as_ids)
    by_shipment: dict[int, list[dict[str, Any]]] = {sid: [] for sid in shipment_ids}
    for aid, sid in link_map.items():
        if sid not in by_shipment:
            continue
        order = orders.get(aid)
        if not order:
            continue
        sd = order.structured_data if isinstance(order.structured_data, dict) else {}
        meta = _shipment_rec_meta(sd) or {}
        if meta.get("source") != SHREC_SOURCE:
            continue
        av = (sd.get("schedule") or {}).get("as_visit") or {}
        applied_workers = list((sd.get("shipment") or {}).get("construction_workers") or [])
        if not isinstance(applied_workers, list):
            applied_workers = []
        applied_workers = [str(w).strip() for w in applied_workers if str(w).strip()]
        info_id = meta.get("as_info_id")
        by_shipment[sid].append(
            {
                "as_order_id": aid,
                "customer_name": get_order_display_customer_name(order),
                "as_info_id": int(info_id) if info_id is not None else None,
                "applied_date": str(av.get("date") or meta.get("applied_date") or ""),
                "applied_workers": applied_workers,
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

    cand_query = (
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
            )
        )
        .filter(
            Order.status.in_(AS_STATUSES),
            Order.active_filter(),
        )
        .order_by(Order.id.desc())
        .limit(800)
    )
    candidates_in: list[dict[str, Any]] = []
    link_as_to_shipment: dict[int, int] = {}
    for order in cand_query:
        sd = order.structured_data if isinstance(order.structured_data, dict) else {}
        addr = get_order_display_address(order)
        if not addr.strip():
            continue
        meta = _shipment_rec_meta(sd)
        if meta and meta.get("source") == SHREC_SOURCE:
            sid = meta.get("shipment_order_id")
            if sid is not None:
                try:
                    link_as_to_shipment[order.id] = int(sid)
                except (TypeError, ValueError):
                    pass
        info_id, ambiguous = _candidate_as_info_id(sd)
        candidates_in.append(
            {
                "order_id": order.id,
                "customer_name": get_order_display_customer_name(order),
                "address": addr,
                "current_visit_date": _visit_date_str(order, sd),
                "status": order.status,
                "sort_date": _as_sort_date(order, sd),
                "as_info_id": None if ambiguous else info_id,
                "as_info_ambiguous": ambiguous,
                **(
                    {
                        "cached_lat": float(order.lat),
                        "cached_lng": float(order.lng),
                    }
                    if order.lat and order.lng and order.geocode_status == "success"
                    else {}
                ),
            }
        )

    converter = FOMSAddressConverter()
    batch = recommend_nearby_schedules_for_targets(
        converter=converter,
        targets=targets_in,
        candidates=candidates_in,
        reference_date=selected_date,
        include_workers=True,
        log_warning=logger.warning,
    )
    targets_out = batch["targets"]
    _enrich_recommendations(targets_out, link_as_to_shipment)
    linked_by = _build_linked_schedules_for_targets(db, order_ids, link_as_to_shipment)
    for tgt in targets_out:
        tgt["linked_as_schedules"] = linked_by.get(int(tgt["order_id"]), [])

    return jsonify(
        {
            "success": True,
            "per_target_limit": 2,
            "duration_limit_min": 30,
            "partial": batch["partial"],
            "warnings": batch["warnings"],
            "targets": targets_out,
        }
    )


def _load_sd_for_write(order: Order) -> dict[str, Any]:
    return load_structured_data_dict_or_raise(getattr(order, "structured_data", None))


def _norm_date(value: Any) -> str:
    return str(_normalize_date_str(str(value or "").strip()) or "").strip()


@erp_shipment_bp.route("/api/erp/shipment/as-recommendations/apply", methods=["POST"])
@login_required
@erp_edit_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def api_shipment_as_recommendations_apply():
    blocked = _construction_team_forbidden()
    if blocked:
        return blocked
    data = request.get_json(silent=True) or {}
    try:
        shipment_order_id = int(data.get("shipment_order_id"))
        as_order_id = int(data.get("as_order_id"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "요청 본문이 올바르지 않습니다."}), 400
    as_info_id = data.get("as_info_id")
    if as_info_id is not None:
        try:
            as_info_id = int(as_info_id)
        except (TypeError, ValueError):
            return jsonify({"success": False, "message": "as_info_id가 올바르지 않습니다."}), 400
    force = bool(data.get("force"))

    db = get_db()
    ship = db.get(Order, shipment_order_id)
    as_order = db.get(Order, as_order_id)
    if not ship or not as_order:
        return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404
    if not _is_valid_shipment_target(ship):
        return jsonify({"success": False, "message": "기준 출고건이 유효하지 않습니다."}), 409
    if as_order.status not in AS_STATUSES or as_order.deleted_at is not None:
        return jsonify({"success": False, "message": "AS 건이 유효하지 않습니다."}), 409

    shipment_date = _norm_date(_shipment_construction_date(ship))
    if not shipment_date:
        return jsonify({"success": False, "message": "기준 출고건의 시공일을 찾을 수 없습니다."}), 409
    workers = _shipment_workers(ship)

    user_id = session.get("user_id")
    user = getattr(g, "current_user", None)
    actor_name = getattr(user, "name", None) or getattr(user, "username", None) or "Unknown"

    try:
        sd_as = _load_sd_for_write(as_order)
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 409

    try:
        schedule = sd_as.setdefault("schedule", {})
        as_visit = schedule.setdefault("as_visit", {})
        prev_date = _norm_date(as_visit.get("date"))
        prev_time = str(as_visit.get("time") or "").strip()
        prev_workers = [
            str(w).strip()
            for w in (sd_as.get("shipment") or {}).get("construction_workers") or []
            if str(w).strip()
        ]

        open_entries = _open_as_entries(sd_as)
        if as_info_id is None:
            if len(open_entries) > 1:
                return jsonify(
                    {
                        "success": False,
                        "message": "열린 AS 항목이 여러 개입니다. as_info_id를 지정하세요.",
                    }
                ), 409
        matched: dict[str, Any] | None = None
        if as_info_id is not None:
            for entry in open_entries:
                if entry.get("id") == as_info_id:
                    matched = entry
                    break
            if not matched:
                return jsonify({"success": False, "message": "해당 AS 항목을 찾을 수 없습니다."}), 409
        elif len(open_entries) == 1:
            matched = open_entries[0]

        if prev_date and prev_date != shipment_date and not force:
            return jsonify(
                {
                    "success": False,
                    "message": "이미 다른 AS 방문일이 있습니다. 덮어쓰려면 force=true로 요청하세요.",
                }
            ), 409

        now_iso = dt.datetime.now().isoformat()
        as_visit["date"] = shipment_date
        as_visit["time"] = prev_time or ""
        as_visit["type"] = "AS"
        shipment_block = sd_as.setdefault("shipment", {})
        shipment_block["construction_workers"] = list(workers)

        if matched:
            matched["visit_date"] = shipment_date
            matched["visit_time"] = prev_time or ""
            matched["scheduled_by"] = actor_name
            matched["scheduled_at"] = now_iso

        meta_as_info = as_info_id
        if meta_as_info is None and matched:
            meta_as_info = matched.get("id")

        as_visit["shipment_recommendation"] = {
            "source": SHREC_SOURCE,
            "shipment_order_id": shipment_order_id,
            "as_info_id": meta_as_info,
            "applied_date": shipment_date,
            "applied_workers_snapshot": list(workers),
            "previous_visit_date": prev_date or "",
            "previous_visit_time": prev_time,
            "previous_workers_snapshot": list(prev_workers),
            "applied_at": now_iso,
            "applied_by_user_id": user_id,
        }

        as_order.structured_data = sd_as
        flag_modified(as_order, "structured_data")
        sync_erp_flat_columns(as_order, sd_as)

        event_payload = {
            "domain": "SHIPMENT_DOMAIN",
            "action": "AS_RECOMMENDATION_APPLIED",
            "shipment_order_id": shipment_order_id,
            "as_order_id": as_order_id,
            "applied_date": shipment_date,
            "change_method": "API",
            "source_screen": "erp_shipment_dashboard",
        }
        db.add(
            OrderEvent(
                order_id=as_order_id,
                event_type="AS_RECOMMENDATION_APPLIED",
                payload=event_payload,
                created_by_user_id=user_id,
            )
        )
        db.add(
            SecurityLog(
                user_id=user_id,
                message=f"출고 대시보드 AS 추천 적용: 출고 #{shipment_order_id} → AS #{as_order_id} ({shipment_date})",
            )
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("[AS-REC] apply 실패: %s", exc)
        return jsonify({"success": False, "message": str(exc)}), 500

    return jsonify(
        {
            "success": True,
            "as_order_id": as_order_id,
            "applied_date": shipment_date,
            "applied_workers": workers,
            "message": "AS 일정이 출고 일정에 추가되었습니다.",
        }
    )


@erp_shipment_bp.route("/api/erp/shipment/as-recommendations/cancel", methods=["POST"])
@login_required
@erp_edit_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def api_shipment_as_recommendations_cancel():
    blocked = _construction_team_forbidden()
    if blocked:
        return blocked
    data = request.get_json(silent=True) or {}
    try:
        shipment_order_id = int(data.get("shipment_order_id"))
        as_order_id = int(data.get("as_order_id"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "요청 본문이 올바르지 않습니다."}), 400
    as_info_id = data.get("as_info_id")
    if as_info_id is not None:
        try:
            as_info_id = int(as_info_id)
        except (TypeError, ValueError):
            return jsonify({"success": False, "message": "as_info_id가 올바르지 않습니다."}), 400

    db = get_db()
    as_order = db.get(Order, as_order_id)
    if not as_order:
        return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404
    if as_order.status == "AS_COMPLETED":
        return jsonify({"success": False, "message": "완료된 AS 건은 취소할 수 없습니다."}), 409

    user_id = session.get("user_id")
    user = getattr(g, "current_user", None)
    actor_name = getattr(user, "name", None) or getattr(user, "username", None) or "Unknown"

    try:
        sd_as = _load_sd_for_write(as_order)
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 409

    meta = _shipment_rec_meta(sd_as)
    if not meta or meta.get("source") != SHREC_SOURCE:
        return jsonify({"success": False, "message": "추천으로 연결된 AS 일정이 아닙니다."}), 409
    if int(meta.get("shipment_order_id") or 0) != shipment_order_id:
        return jsonify({"success": False, "message": "연결된 출고건이 일치하지 않습니다."}), 409
    meta_info = meta.get("as_info_id")
    if as_info_id is not None and meta_info is not None and int(meta_info) != as_info_id:
        return jsonify({"success": False, "message": "AS 항목 정보가 일치하지 않습니다."}), 409

    schedule = sd_as.setdefault("schedule", {})
    as_visit = schedule.setdefault("as_visit", {})
    applied_date = _norm_date(meta.get("applied_date") or "")
    current_date = _norm_date(as_visit.get("date"))
    if applied_date and current_date != applied_date:
        return jsonify(
            {
                "success": False,
                "message": "방문일이 수동으로 변경되어 있습니다. 데이터 보존을 위해 취소할 수 없습니다.",
            }
        ), 409

    prev_date = str(meta.get("previous_visit_date") or "").strip()
    prev_time = str(meta.get("previous_visit_time") or "").strip()
    prev_workers = meta.get("previous_workers_snapshot")
    if not isinstance(prev_workers, list):
        prev_workers = []
    prev_workers = [str(w).strip() for w in prev_workers if str(w).strip()]
    applied_snap = meta.get("applied_workers_snapshot")
    if not isinstance(applied_snap, list):
        applied_snap = []
    applied_snap = [str(w).strip() for w in applied_snap if str(w).strip()]

    shipment_block = sd_as.setdefault("shipment", {})
    cur_workers = [
        str(w).strip()
        for w in (shipment_block.get("construction_workers") or [])
        if str(w).strip()
    ]

    target_info_id = meta.get("as_info_id")
    if target_info_id is not None:
        target_info_id = int(target_info_id)
    open_entries = _open_as_entries(sd_as)

    def sync_as_info_visit(clear: bool) -> None:
        if target_info_id is not None:
            for entry in open_entries:
                if entry.get("id") == target_info_id:
                    if clear:
                        entry["visit_date"] = None
                        entry["visit_time"] = None
                    else:
                        entry["visit_date"] = prev_date or None
                        entry["visit_time"] = prev_time or None
                    entry["scheduled_by"] = actor_name
                    entry["scheduled_at"] = dt.datetime.now().isoformat()
                    break
            return
        matches = [
            e
            for e in open_entries
            if isinstance(e, dict)
            and _norm_date(e.get("visit_date")) == applied_date
        ]
        if len(matches) > 1:
            raise ValueError("AS 항목 매칭이 모호합니다.")
        if len(matches) == 1:
            if clear:
                matches[0]["visit_date"] = None
                matches[0]["visit_time"] = None
            else:
                matches[0]["visit_date"] = prev_date or None
                matches[0]["visit_time"] = prev_time or None

    workers_cleared_flag = cur_workers == applied_snap

    try:
        if prev_date:
            as_visit["date"] = prev_date
            as_visit["time"] = prev_time
            sync_as_info_visit(clear=False)
        else:
            as_visit["date"] = ""
            as_visit["time"] = ""
            sync_as_info_visit(clear=True)
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 409

    try:
        if workers_cleared_flag:
            shipment_block["construction_workers"] = list(prev_workers)

        as_visit.pop("shipment_recommendation", None)
        as_order.structured_data = sd_as
        flag_modified(as_order, "structured_data")
        sync_erp_flat_columns(as_order, sd_as)

        cleared = applied_date or current_date
        db.add(
            OrderEvent(
                order_id=as_order_id,
                event_type="AS_RECOMMENDATION_CANCELLED",
                payload={
                    "domain": "SHIPMENT_DOMAIN",
                    "action": "AS_RECOMMENDATION_CANCELLED",
                    "shipment_order_id": shipment_order_id,
                    "as_order_id": as_order_id,
                    "cleared_visit_date": cleared,
                    "change_method": "API",
                    "source_screen": "erp_shipment_dashboard",
                },
                created_by_user_id=user_id,
            )
        )
        db.add(
            SecurityLog(
                user_id=user_id,
                message=f"출고 대시보드 AS 추천 취소: 출고 #{shipment_order_id} → AS #{as_order_id}",
            )
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("[AS-REC] cancel 실패: %s", exc)
        return jsonify({"success": False, "message": str(exc)}), 500

    workers_cleared = workers_cleared_flag
    cleared_display = applied_date or current_date
    return jsonify(
        {
            "success": True,
            "as_order_id": as_order_id,
            "cleared_visit_date": cleared_display,
            "workers_cleared": workers_cleared,
            "message": "AS 일정이 출고 일정에서 삭제되었습니다.",
        }
    )
