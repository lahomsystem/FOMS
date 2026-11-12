"""출고 대시보드 AS 추천 apply/cancel 오케스트레이터 (SHIPMENT-WRITER-01, B1).

출고건(construction date · active crew)을 기준으로 AS 건의 방문일정을 canonical AS
cycle command(schedule/unschedule)과 crew replace command 로 반영/취소하는 **얇은
오케스트레이터**다:

* **as_cycle_service 는 import 만**(무편집): 방문일정은 :func:`schedule_as_cycle`/
  :func:`unschedule_as_cycle` 로만 쓴다(AS info/visit direct write 없음, version/receipt/
  event 는 REV-00 가 한 tx 에 기록).
* **crew IDs via command**: 담당 작업자 번호 배정은 :func:`replace_workers` (ID command)로
  바꾼다.
* **시공자 이름 배열(설계서 §14.9, D35)**: 출고 줄 시공자는 실제로는 이름 배열
  ``sd['shipment']['construction_workers']`` (이름판 · PC · ``/api/erp/shipment/update``)로만
  저장되고 번호 배정은 비어 있다. 그래서 넣기 때 출고 이름 배열이 비어 있지 않으면 AS 주문
  이름 배열을 그 이름들로 바꾼다(출고 설정 정본 :func:`apply_shipment_settings` 를 거쳐 같은
  AS 쓰기 · 같은 tx 에서). 취소는 AS 이름이 넣은 그대로일 때만 넣기 전 이름으로 되돌린다.
  이름이 실제로 바뀌면 AS 주문 변경 원장(``OrderFieldChange``)에 이름판 저장과 같은 점 경로
  ``shipment.construction_workers`` 행을 같은 mutation 안에서 남긴다(D35-b).
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
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

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
from foms.services.orders.as_schedule_link import SOURCE_SHIPMENT, clear_link, read_link, write_link
from foms.services.orders.order_field_change_writer import record_field_changes
from foms.services.orders.revision import execute_order_mutation
from foms.services.orders.structured_diff import diff_structured
from foms.services.shipment.writer import apply_shipment_settings, build_shipment_settings_patch
from models import InstallationWorker, Order, OrderEvent

_AS_ROW_STATUSES = ("AS", "AS_RECEIVED", "AS_COMPLETED")

#: 넣기 · 취소가 변경 원장에 남기는 유일한 경로(D35-b). 같은 AS 쓰기 안의 schedule_link 등
#: 다른 sd 변화는 원장 대상이 아니다 — 이름판 저장(``/api/erp/shipment/update``)과 같은 경로다.
_AS_NAMES_LEDGER_PATH = "shipment.construction_workers"


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


def _shipment_names(order: Order) -> Optional[List[Any]]:
    """주문의 시공자 이름 배열(``sd.shipment.construction_workers``) 원본. 키가 없으면 None."""
    sd = getattr(order, "structured_data", None) or {}
    shipment = sd.get("shipment") if isinstance(sd, dict) else None
    if not isinstance(shipment, dict) or "construction_workers" not in shipment:
        return None
    raw = shipment.get("construction_workers")
    return copy.deepcopy(raw) if isinstance(raw, list) else None


def _normalized_ship_names(ship: Order) -> List[str]:
    """출고 줄 시공자 이름을 출고 설정 writer 의 정규화 그대로 돌려준다(없으면 빈 목록)."""
    patch = build_shipment_settings_patch({"construction_workers": _shipment_names(ship) or []})
    return list(patch.get("construction_workers") or [])


def _write_as_names(sd: dict, names: Optional[List[Any]]) -> None:
    """AS structured_data(이미 deepcopy 된 것)의 시공자 이름 배열을 바꾼다(제자리 변형).

    ``names`` 가 None 이면 키를 지우고, 목록이면 출고 설정 정본 :func:`apply_shipment_settings`
    로 기록한다(다른 shipment 키 보존).
    """
    if names is None:
        shipment = sd.get("shipment")
        if isinstance(shipment, dict):
            shipment.pop("construction_workers", None)
        return
    sd["shipment"] = apply_shipment_settings(sd, {"construction_workers": list(names)})["shipment"]


def _write_ship_recommendations(
    session: Session, ship_id: int, as_id: int, snapshot: Optional[Dict[str, Any]],
    *, actor_user_id: int, event_type: str, payload: Dict[str, Any],
    now: datetime.datetime, as_sd_mutator: Optional[Callable[[dict], Any]] = None,
    change_set_id: Optional[str] = None,
) -> int:
    """출고 Order 의 추천 snapshot list 를 갱신한다(REV-00: version/receipt/event 한 tx).

    ``snapshot`` 이 있으면 해당 as_id 항목을 upsert, ``None`` 이면 제거한다. ``as_sd_mutator``
    가 주어지면 **같은 mutation·같은 tx** 안에서 AS Order 의 structured_data 도 함께
    ``copy.deepcopy`` + `flag_modified` 로 변형한다(§3.2 schedule_link · §14.9 시공자 이름,
    추가 command/커밋 없음). ``None`` 이면 AS Order 는 잠그지도 건드리지도 않는다.

    ``change_set_id`` 가 있으면 AS 이름 배열(:data:`_AS_NAMES_LEDGER_PATH`)이 실제로 바뀐
    경우에만 그 경로 변경 행을 :func:`record_field_changes` 로 **같은 mutation 안** 에 싣는다
    (D35-b). 바깥에서 쓰면 receipt backstop rollback 뒤 원장 행만 남는 유령 행이 생긴다
    (``foms/api/shipment/settings.py`` AUDIT-GAP-01 주석과 같은 이유).

    Returns:
        AS 주문에 실린 변경 원장 행 수(이름이 안 바뀌었거나 AS 를 안 건드리면 0).
    """
    captured: Dict[str, int] = {"rows": 0}

    def _mutate(sess: Session, orders: List[Order]) -> Dict[int, List[str]]:
        by_id = {o.id: o for o in orders}
        target = by_id[ship_id]
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
        families = {target.id: [f"ORDER_DETAIL:{target.id}", "ORDERS_INDEX"]}

        if as_sd_mutator is not None:
            as_order = by_id[as_id]
            old_as_sd = as_order.structured_data or {}
            as_sd = copy.deepcopy(old_as_sd)
            as_sd_mutator(as_sd)
            if change_set_id:
                name_changes = [
                    c for c in diff_structured(old_as_sd, as_sd, max_changes=-1).changes
                    if c.get("path") == _AS_NAMES_LEDGER_PATH
                ]
                captured["rows"] = record_field_changes(
                    sess, name_changes, order_id=int(as_order.id),
                    actor_user_id=actor_user_id, change_set_id=change_set_id,
                )
            as_order.structured_data = as_sd
            flag_modified(as_order, "structured_data")
            families[as_order.id] = [f"ORDER_DETAIL:{as_order.id}"]

        sess.add(OrderEvent(
            order_id=target.id, event_type=event_type, payload=payload,
            created_by_user_id=actor_user_id, created_at=now,
        ))
        return families

    order_ids = [ship_id, as_id] if as_sd_mutator is not None else [ship_id]
    execute_order_mutation(
        session, actor_user_id=actor_user_id, policy_id="SHIPMENT_AS_RECOMMENDATION",
        order_ids=order_ids, scope_hash=_hash(f"asrec:{ship_id}:{as_id}"),
        request_hash=_hash(f"asrec:{event_type}:{now.isoformat()}"),
        mutation=_mutate, now=now,
    )
    return captured["rows"]


def _safe_int(value: Any) -> Optional[int]:
    """느슨한 int 변환(실패 시 None) — 링크 ``ref_order_id`` 비교 전용."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def apply_as_recommendation(
    session: Session, *, shipment_order_id: int, as_order_id: int, actor_user_id: int,
    cycle_id: Optional[str] = None, shipment_version: Optional[int] = None,
    as_version: Optional[int] = None, force: bool = False,
    source_screen: Optional[str] = None, now: Optional[datetime.datetime] = None,
    change_set_id: Optional[str] = None,
) -> Dict[str, Any]:
    """출고 시공일/작업자를 AS 건에 canonical command 로 반영한다(한 tx).

    두 Order 를 ID 순 잠그고 If-Match 검사 후, AS 현재 cycle 에 출고 시공일을
    :func:`schedule_as_cycle` 로 기록하고 출고 active crew 를 :func:`replace_workers` 로
    AS 에 복제한다. 출고 시공자 이름 배열이 비어 있지 않으면 AS 이름 배열도 그 이름들로
    바꾼다(§14.9 — 비어 있으면 AS 이름은 그대로). 이전 값 snapshot(``previous_names`` ·
    ``applied_names`` 포함)은 출고 Order 에 보존한다(cancel 복원용). 기존 수동 방문일이
    다르고 ``force`` 가 아니면 409. AS 이름이 실제로 바뀌면 ``change_set_id``(없으면 새로
    만든다)로 AS 주문 변경 원장 행을 남긴다(D35-b).

    Returns:
        ``{as_order_id, applied_date, applied_workers, applied_worker_ids, as_visit_date,
        recommendation_transition_id, shipment_version, as_version, change_set,
        change_count}``.
    """
    now = now or now_utc_naive()
    change_set_id = change_set_id or str(uuid.uuid4())
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
    ship_names = _normalized_ship_names(ship)
    prev_names = _shipment_names(as_order)
    applied_names: Optional[List[str]] = list(ship_names) if ship_names else None

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
        "previous_names": prev_names, "applied_names": applied_names,
        "recommendation_transition_id": rec_transition_id,
        "forced": bool(force and prev_visit_date and prev_visit_date != ship_date),
        "applied_by_user_id": actor_user_id, "applied_at": now.isoformat(),
    }

    def _apply_as_mutator(sd: dict) -> None:
        write_link(
            sd, ref_order_id=ship.id, ref_date=ship_date, source=SOURCE_SHIPMENT,
            user_id=actor_user_id, user_name="", now=now,
        )
        if applied_names:
            _write_as_names(sd, applied_names)

    change_count = _write_ship_recommendations(
        session, ship.id, as_order.id, snapshot, actor_user_id=actor_user_id,
        event_type="AS_RECOMMENDATION_APPLIED",
        payload={
            "domain": "SHIPMENT_DOMAIN", "action": "AS_RECOMMENDATION_APPLIED",
            "shipment_order_id": ship.id, "as_order_id": as_order.id,
            "applied_date": ship_date, "forced": snapshot["forced"],
            "change_method": "API", "source_screen": source_screen or "erp_shipment_dashboard",
        },
        now=now,
        as_sd_mutator=_apply_as_mutator, change_set_id=change_set_id,
    )
    return {
        "as_order_id": as_order.id, "applied_date": ship_date,
        "applied_workers": (list(applied_names) if applied_names
                            else _resolve_worker_names(session, ship_crew_ids)),
        "applied_worker_ids": list(ship_crew_ids), "as_visit_date": ship_date,
        "recommendation_transition_id": rec_transition_id,
        "shipment_version": ship.mutation_version, "as_version": as_order.mutation_version,
        "change_set": change_set_id, "change_count": change_count,
    }


def cancel_as_recommendation(
    session: Session, *, shipment_order_id: int, as_order_id: int, actor_user_id: int,
    cycle_id: Optional[str] = None, recommendation_transition_id: Optional[int] = None,
    shipment_version: Optional[int] = None, as_version: Optional[int] = None,
    now: Optional[datetime.datetime] = None, change_set_id: Optional[str] = None,
) -> Dict[str, Any]:
    """추천으로 반영한 AS 방문일/작업자를 이전 snapshot 으로 복원한다(한 tx).

    출고 Order snapshot 을 찾아, 추천 이후 방문일/작업자에 **수동 변경이 없을 때만**
    이전 schedule/crew 를 typed compensation(:func:`schedule_as_cycle`/
    :func:`unschedule_as_cycle` + :func:`replace_workers`)으로 복원하고 snapshot 을
    제거한다. 후속 변경이 있으면 409(불변). 시공자 이름 배열은 snapshot ``applied_names``
    가 있고 AS 지금 이름이 그것과 같을 때만 ``previous_names`` 로 되돌린다(null 이면 키
    삭제). 그 사이 손으로 바꿨으면 이름은 두고 취소는 계속한다(이름 때문에 409 없음,
    §14.9). ``applied_names`` 키가 없는 옛 snapshot 은 이름을 건드리지 않는다. 이름을
    되돌리면 ``change_set_id``(없으면 새로 만든다)로 AS 주문 변경 원장 행을 남긴다(D35-b).

    Returns:
        ``{as_order_id, cleared_visit_date, restored_visit_date, shipment_version,
        as_version, change_set, change_count}``.
    """
    now = now or now_utc_naive()
    change_set_id = change_set_id or str(uuid.uuid4())
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
    as_link = read_link(as_order.structured_data or {})
    owns_link = (
        as_link is not None
        and as_link.get("source") == SOURCE_SHIPMENT
        and _safe_int(as_link.get("ref_order_id")) == ship.id
    )
    rec_applied_names = rec.get("applied_names")
    restore_names = bool(rec_applied_names) and _shipment_names(as_order) == list(rec_applied_names)
    prev_names = rec.get("previous_names")
    prev_names = list(prev_names) if isinstance(prev_names, list) else None

    def _cancel_as_mutator(sd: dict) -> None:
        # 사용자가 이후 다른 기준 주문에 손으로 재매칭했을 수 있다 — 이 출고건이 만든
        # 링크일 때만 해제한다(클로버 방지, 스펙 §3.2/플랜 T6).
        if owns_link:
            clear_link(sd)
        if restore_names:
            _write_as_names(sd, prev_names)

    change_count = _write_ship_recommendations(
        session, ship.id, as_order.id, None, actor_user_id=actor_user_id,
        event_type="AS_RECOMMENDATION_CANCELLED",
        payload={
            "domain": "SHIPMENT_DOMAIN", "action": "AS_RECOMMENDATION_CANCELLED",
            "shipment_order_id": ship.id, "as_order_id": as_order.id,
            "restored_visit_date": prev_date, "change_method": "API",
            "source_screen": "erp_shipment_dashboard",
        },
        now=now,
        as_sd_mutator=_cancel_as_mutator if (owns_link or restore_names) else None,
        change_set_id=change_set_id,
    )
    return {
        "as_order_id": as_order.id, "cleared_visit_date": applied_date,
        "restored_visit_date": prev_date,
        "shipment_version": ship.mutation_version, "as_version": as_order.mutation_version,
        "change_set": change_set_id, "change_count": change_count,
    }


__all__ = ["ASRecommendationError", "apply_as_recommendation", "cancel_as_recommendation"]
