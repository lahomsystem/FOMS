"""출고 대시보드 AS 추천 apply/cancel 오케스트레이터 (SHIPMENT-WRITER-01, B1).

출고건(construction date · active crew)을 기준으로 AS 건의 방문일정을 canonical AS
cycle command(schedule/unschedule)과 crew replace command 로 반영/취소하는 **얇은
오케스트레이터**다:

* **as_cycle_service 는 import 만**(무편집): 방문일정은 :func:`schedule_as_cycle`/
  :func:`unschedule_as_cycle` 로만 쓴다(AS info/visit direct write 없음, version/receipt/
  event 는 REV-00 가 한 tx 에 기록).
* **crew IDs via command**: 담당 작업자는 :func:`replace_workers` (ID command)로만
  바꾼다(``construction_workers`` name-array direct write 없음).
* **두 Order 를 ID 순 FOR UPDATE** 로 잠그고 **If-Match(version)을 직접 검사**해 blind
  overwrite 를 막는다. ``force`` 는 기존 수동 방문일을 덮되, 덮인 값을 snapshot 에
  보존한다(현재 값 무시 통째 덮어쓰기 0).
* 추천 snapshot(force 시 덮인 값 · cancel 복원용)은 **출고 Order structured_data
  ``sd['shipment']['recommendations']`` (as_order_id keyed list)** 에 보존한다 — 출고건은
  여러 AS 를 참조할 수 있어 list 다. AS Order 에는 직접 쓰지 않는다.

``session.commit()`` 은 호출자(endpoint) 소유다(REV-00 규약). models·마이그레이션은
건드리지 않는다.
"""
from __future__ import annotations

import copy
import datetime
import hashlib
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from foms.services.crew.assignments import active_worker_ids, replace_workers
from foms.services.datetime_kst import now_utc_naive
from foms.services.order_date_sync import _normalize_date_str
from foms.services.orders.as_cycle_service import (
    AS_COMPLETED,
    project_current_as_cycle,
    schedule_as_cycle,
    unschedule_as_cycle,
)
from foms.services.orders.revision import execute_order_mutation
from models import InstallationWorker, Order, OrderEvent

_AS_ROW_STATUSES = ("AS", "AS_RECEIVED", "AS_COMPLETED")


class ASRecommendationError(RuntimeError):
    """AS 추천 orchestration 계약 위반. ``status_code`` 로 HTTP 매핑(404/409)."""

    def __init__(self, message: str, status_code: int = 409, code: str = "AS_RECOMMENDATION_ERROR"):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = code


def _hash(text: str) -> str:
    """REV-00 scope/request hash 용 sha256 hex."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _lock_pair(session: Session, ship_id: int, as_id: int) -> Tuple[Order, Order]:
    """출고·AS Order 를 **ID 순** ``FOR UPDATE`` 로 잠가 돌려준다(교착 방지·둘 다 필수)."""
    if int(ship_id) == int(as_id):
        raise ASRecommendationError("출고건과 AS건이 동일합니다.", 400, "SAME_ORDER")
    ids = sorted({int(ship_id), int(as_id)})
    rows = (
        session.query(Order).filter(Order.id.in_(ids))
        .order_by(Order.id.asc()).with_for_update().all()
    )
    by_id = {o.id: o for o in rows}
    ship, as_order = by_id.get(int(ship_id)), by_id.get(int(as_id))
    if ship is None or as_order is None:
        raise ASRecommendationError("주문을 찾을 수 없습니다.", 404, "ORDER_NOT_FOUND")
    return ship, as_order


def _check_version(order: Order, expected: Optional[int]) -> None:
    """If-Match(mutation_version) 검사. 지정됐고 불일치면 409(blind overwrite 방지)."""
    if expected is None:
        return
    if int(getattr(order, "mutation_version", 0) or 0) != int(expected):
        raise ASRecommendationError(
            "다른 사용자가 먼저 수정했습니다. 새로고침 후 다시 시도하세요.",
            409, "REVISION_CONFLICT",
        )


def _validate_shipment_target(ship: Order) -> None:
    """기준 출고건이 유효한지 검사(삭제/AS 상태가 아님)."""
    if ship.status == "DELETED" or ship.deleted_at is not None:
        raise ASRecommendationError("기준 출고건이 유효하지 않습니다.", 409, "INVALID_SHIPMENT")
    if ship.status in _AS_ROW_STATUSES:
        raise ASRecommendationError("기준 출고건이 유효하지 않습니다.", 409, "INVALID_SHIPMENT")


def _ship_construction_date(order: Order) -> str:
    """출고건의 시공일(``schedule.construction.date`` 우선, 없으면 ``scheduled_date``)."""
    sd = getattr(order, "structured_data", None) or {}
    if isinstance(sd, dict):
        d = str(((sd.get("schedule") or {}).get("construction") or {}).get("date") or "").strip()
        if d:
            return d
    sched = getattr(order, "scheduled_date", None)
    return str(sched) if sched else ""


def _require_ship_date(ship: Order) -> str:
    """출고 시공일을 ``YYYY-MM-DD`` 로 정규화해 돌려준다(없으면 409)."""
    raw = _ship_construction_date(ship)
    norm = str(_normalize_date_str(raw) or "").strip() if raw else ""
    if not norm:
        raise ASRecommendationError("기준 출고건의 시공일을 찾을 수 없습니다.", 409, "NO_SHIP_DATE")
    return norm


def _require_open_cycle(as_order: Order, cycle_id: Optional[str]) -> Dict[str, Any]:
    """AS 현재 cycle projection 을 돌려주되 완료/부재/cycle 불일치면 409."""
    proj = project_current_as_cycle(as_order)
    if proj is None:
        raise ASRecommendationError("AS 접수 cycle이 없습니다.", 409, "NO_AS_CYCLE")
    if proj["status"] == AS_COMPLETED:
        raise ASRecommendationError("완료된 AS 건은 처리할 수 없습니다.", 409, "AS_COMPLETED")
    if cycle_id is not None and str(cycle_id) != str(proj["cycle_id"]):
        raise ASRecommendationError("현재 AS cycle과 일치하지 않습니다.", 409, "AS_CYCLE_MISMATCH")
    return proj


def _resolve_worker_names(session: Session, worker_ids: List[int]) -> List[str]:
    """worker_id 목록을 활성·비활성 무관 display_name 으로 해석(표시용)."""
    if not worker_ids:
        return []
    rows = session.query(InstallationWorker).filter(InstallationWorker.id.in_(worker_ids)).all()
    name_by_id = {w.id: w.display_name for w in rows}
    return [name_by_id[i] for i in worker_ids if i in name_by_id]


def _read_snapshots(ship: Order) -> List[Dict[str, Any]]:
    """출고 Order 의 추천 snapshot 목록(``sd.shipment.recommendations``)."""
    sd = getattr(ship, "structured_data", None) or {}
    if not isinstance(sd, dict):
        return []
    recs = (sd.get("shipment") or {}).get("recommendations")
    return [r for r in recs if isinstance(r, dict)] if isinstance(recs, list) else []


def _last_transition_seq(as_order: Order) -> Optional[int]:
    """AS 현재 cycle 의 마지막 transition seq(방금 append 한 SCHEDULE 식별자)."""
    from foms.services.orders.as_cycle_service import current_cycle

    sd = getattr(as_order, "structured_data", None) or {}
    cyc = current_cycle(sd) if isinstance(sd, dict) else None
    trs = (cyc or {}).get("transitions") or []
    return trs[-1]["seq"] if trs else None


def _write_ship_recommendations(
    session: Session, ship_id: int, as_id: int, snapshot: Optional[Dict[str, Any]],
    *, actor_user_id: int, event_type: str, payload: Dict[str, Any],
    now: datetime.datetime,
) -> Order:
    """출고 Order 의 추천 snapshot list 를 갱신한다(REV-00: version/receipt/event 한 tx).

    ``snapshot`` 이 있으면 해당 as_id 항목을 upsert, ``None`` 이면 제거한다. 출고 Order
    를 이미 잠근 상태에서 :func:`execute_order_mutation` 로 version bump + receipt +
    ``event_type`` OrderEvent 를 기록한다.
    """
    def _mutate(sess: Session, orders: List[Order]) -> Dict[int, List[str]]:
        target = orders[0]
        sd = copy.deepcopy(target.structured_data or {})
        shipment = sd.setdefault("shipment", {})
        if not isinstance(shipment, dict):
            shipment = {}
            sd["shipment"] = shipment
        existing = [r for r in (shipment.get("recommendations") or [])
                    if isinstance(r, dict) and int(r.get("as_order_id") or 0) != int(as_id)]
        if snapshot is not None:
            existing.append(snapshot)
        shipment["recommendations"] = existing
        target.structured_data = sd
        flag_modified(target, "structured_data")
        sess.add(OrderEvent(
            order_id=target.id, event_type=event_type, payload=payload,
            created_by_user_id=actor_user_id, created_at=now,
        ))
        return {target.id: [f"ORDER_DETAIL:{target.id}", "ORDERS_INDEX"]}

    execute_order_mutation(
        session, actor_user_id=actor_user_id, policy_id="SHIPMENT_AS_RECOMMENDATION",
        order_ids=[ship_id], scope_hash=_hash(f"asrec:{ship_id}:{as_id}"),
        request_hash=_hash(f"asrec:{event_type}:{now.isoformat()}"),
        mutation=_mutate, now=now,
    )
    return session.get(Order, ship_id)


def apply_as_recommendation(
    session: Session, *, shipment_order_id: int, as_order_id: int, actor_user_id: int,
    cycle_id: Optional[str] = None, shipment_version: Optional[int] = None,
    as_version: Optional[int] = None, force: bool = False,
    source_screen: Optional[str] = None, now: Optional[datetime.datetime] = None,
) -> Dict[str, Any]:
    """출고 시공일/작업자를 AS 건에 canonical command 로 반영한다(한 tx).

    두 Order 를 ID 순 잠그고 If-Match 검사 후, AS 현재 cycle 에 출고 시공일을
    :func:`schedule_as_cycle` 로 기록하고 출고 active crew 를 :func:`replace_workers` 로
    AS 에 복제한다. 이전 값 snapshot 은 출고 Order 에 보존한다(cancel 복원용). 기존 수동
    방문일이 다르고 ``force`` 가 아니면 409.

    Returns:
        ``{as_order_id, applied_date, applied_workers, applied_worker_ids, as_visit_date,
        recommendation_transition_id, shipment_version, as_version}``.
    """
    now = now or now_utc_naive()
    ship, as_order = _lock_pair(session, shipment_order_id, as_order_id)
    _validate_shipment_target(ship)
    _check_version(ship, shipment_version)
    _check_version(as_order, as_version)

    ship_date = _require_ship_date(ship)
    ship_crew_ids = active_worker_ids(session, ship.id)
    proj = _require_open_cycle(as_order, cycle_id)
    cycle_id_eff = proj["cycle_id"]

    prev_visit_date = str(proj["visit_date"] or "")
    prev_visit_time = str(proj["visit_time"] or "")
    if prev_visit_date and prev_visit_date != ship_date and not force:
        raise ASRecommendationError(
            "이미 다른 AS 방문일이 있습니다. 덮어쓰려면 force=true로 요청하세요.",
            409, "AS_VISIT_CONFLICT",
        )
    prev_crew_ids = active_worker_ids(session, as_order.id)

    schedule_as_cycle(
        session, order_id=as_order.id, visit_date=ship_date,
        visit_time=(prev_visit_time or None), cycle_id=cycle_id_eff,
        actor_user_id=actor_user_id, scope_hash=_hash(f"asrec:sched:{ship.id}:{as_order.id}"),
        request_hash=_hash(f"asrec:sched:{ship_date}:{cycle_id_eff}"), now=now,
    )
    rec_transition_id = _last_transition_seq(as_order)
    replace_workers(
        session, order_id=as_order.id, worker_ids=ship_crew_ids,
        reason="AS 추천 적용", actor_user_id=actor_user_id, now=now,
    )

    snapshot = {
        "as_order_id": as_order.id, "as_cycle_id": cycle_id_eff,
        "applied_visit_date": ship_date, "applied_visit_time": prev_visit_time,
        "previous_visit_date": prev_visit_date, "previous_visit_time": prev_visit_time,
        "previous_crew_ids": list(prev_crew_ids), "applied_crew_ids": list(ship_crew_ids),
        "recommendation_transition_id": rec_transition_id,
        "forced": bool(force and prev_visit_date and prev_visit_date != ship_date),
        "applied_by_user_id": actor_user_id, "applied_at": now.isoformat(),
    }
    _write_ship_recommendations(
        session, ship.id, as_order.id, snapshot, actor_user_id=actor_user_id,
        event_type="AS_RECOMMENDATION_APPLIED",
        payload={
            "domain": "SHIPMENT_DOMAIN", "action": "AS_RECOMMENDATION_APPLIED",
            "shipment_order_id": ship.id, "as_order_id": as_order.id,
            "applied_date": ship_date, "forced": snapshot["forced"],
            "change_method": "API", "source_screen": source_screen or "erp_shipment_dashboard",
        },
        now=now,
    )
    return {
        "as_order_id": as_order.id, "applied_date": ship_date,
        "applied_workers": _resolve_worker_names(session, ship_crew_ids),
        "applied_worker_ids": list(ship_crew_ids), "as_visit_date": ship_date,
        "recommendation_transition_id": rec_transition_id,
        "shipment_version": ship.mutation_version, "as_version": as_order.mutation_version,
    }


def cancel_as_recommendation(
    session: Session, *, shipment_order_id: int, as_order_id: int, actor_user_id: int,
    cycle_id: Optional[str] = None, recommendation_transition_id: Optional[int] = None,
    shipment_version: Optional[int] = None, as_version: Optional[int] = None,
    now: Optional[datetime.datetime] = None,
) -> Dict[str, Any]:
    """추천으로 반영한 AS 방문일/작업자를 이전 snapshot 으로 복원한다(한 tx).

    출고 Order snapshot 을 찾아, 추천 이후 방문일/작업자에 **수동 변경이 없을 때만**
    이전 schedule/crew 를 typed compensation(:func:`schedule_as_cycle`/
    :func:`unschedule_as_cycle` + :func:`replace_workers`)으로 복원하고 snapshot 을
    제거한다. 후속 변경이 있으면 409(불변).

    Returns:
        ``{as_order_id, cleared_visit_date, restored_visit_date, shipment_version,
        as_version}``.
    """
    now = now or now_utc_naive()
    ship, as_order = _lock_pair(session, shipment_order_id, as_order_id)
    _check_version(ship, shipment_version)
    _check_version(as_order, as_version)

    rec = next((r for r in _read_snapshots(ship)
                if int(r.get("as_order_id") or 0) == as_order.id), None)
    if rec is None:
        raise ASRecommendationError("추천으로 연결된 AS 일정이 아닙니다.", 409, "NO_RECOMMENDATION")
    if (recommendation_transition_id is not None
            and str(rec.get("recommendation_transition_id")) != str(recommendation_transition_id)):
        raise ASRecommendationError("추천 정보가 일치하지 않습니다.", 409, "RECOMMENDATION_MISMATCH")

    proj = _require_open_cycle(as_order, cycle_id)
    applied_date = str(rec.get("applied_visit_date") or "")
    if str(proj["visit_date"] or "") != applied_date:
        raise ASRecommendationError(
            "방문일이 수동으로 변경되어 취소할 수 없습니다.", 409, "MANUAL_VISIT_CHANGE")
    applied_crew = sorted(int(x) for x in (rec.get("applied_crew_ids") or []))
    if active_worker_ids(session, as_order.id) != applied_crew:
        raise ASRecommendationError(
            "담당 작업자가 수동으로 변경되어 취소할 수 없습니다.", 409, "MANUAL_CREW_CHANGE")

    prev_date = str(rec.get("previous_visit_date") or "")
    prev_time = str(rec.get("previous_visit_time") or "")
    prev_crew = [int(x) for x in (rec.get("previous_crew_ids") or [])]
    cycle_id_eff = proj["cycle_id"]

    if prev_date:
        schedule_as_cycle(
            session, order_id=as_order.id, visit_date=prev_date,
            visit_time=(prev_time or None), cycle_id=cycle_id_eff,
            actor_user_id=actor_user_id, scope_hash=_hash(f"asrec:restore:{ship.id}:{as_order.id}"),
            request_hash=_hash(f"asrec:restore:{prev_date}:{cycle_id_eff}"), now=now,
        )
    else:
        unschedule_as_cycle(
            session, order_id=as_order.id, reason="AS 추천 취소", cycle_id=cycle_id_eff,
            actor_user_id=actor_user_id, scope_hash=_hash(f"asrec:unsched:{ship.id}:{as_order.id}"),
            request_hash=_hash(f"asrec:unsched:{cycle_id_eff}:{now.isoformat()}"), now=now,
        )
    replace_workers(
        session, order_id=as_order.id, worker_ids=prev_crew,
        reason="AS 추천 취소", actor_user_id=actor_user_id, now=now,
    )
    _write_ship_recommendations(
        session, ship.id, as_order.id, None, actor_user_id=actor_user_id,
        event_type="AS_RECOMMENDATION_CANCELLED",
        payload={
            "domain": "SHIPMENT_DOMAIN", "action": "AS_RECOMMENDATION_CANCELLED",
            "shipment_order_id": ship.id, "as_order_id": as_order.id,
            "restored_visit_date": prev_date, "change_method": "API",
            "source_screen": "erp_shipment_dashboard",
        },
        now=now,
    )
    return {
        "as_order_id": as_order.id, "cleared_visit_date": applied_date,
        "restored_visit_date": prev_date,
        "shipment_version": ship.mutation_version, "as_version": as_order.mutation_version,
    }


__all__ = ["ASRecommendationError", "apply_as_recommendation", "cancel_as_recommendation"]
