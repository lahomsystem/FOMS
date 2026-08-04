"""Order schedule-date normalization and synchronization helpers."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from db import get_db
from foms.services.erp_order_flags import is_erp_order_record

logger = logging.getLogger(__name__)
from models import OrderEvent, OrderScheduleDate

__all__ = [
    "collect_order_schedule_date_specs",
    "sync_order_dates",
    "register_date_sync_listener",
]

#: 시공일 변경 이벤트 재진입 가드 키(``Session.info``).
_CONSTRUCTION_EVENT_GUARD = "foms_construction_date_event_in_flush"
#: 트랜잭션 단위 시공일 이벤트 합치기 상태 키(``Session.info``).
_CONSTRUCTION_EVENT_STATE = "foms_construction_date_event_state"


def _normalize_date_str(s: Any) -> Any:
    """Normalize a date-like string into ``YYYY-MM-DD`` when possible."""
    if not s or not isinstance(s, str):
        return s
    s = s.strip()
    if not s:
        return s

    m = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y}-{mo:02d}-{d:02d}"

    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            dt = datetime.strptime(s[:19], fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s


def collect_order_schedule_date_specs(order: Any) -> list[dict[str, Any]]:
    """Build the normalized schedule-date payloads for a single order."""
    specs: list[dict[str, Any]] = []

    m_dates = set()
    is_erp_order = is_erp_order_record(order)
    sd = (
        order.structured_data
        if is_erp_order and isinstance(getattr(order, "structured_data", None), dict)
        else {}
    )
    beta_m = (sd.get("schedule") or {}).get("measurement") or {}
    beta_measurement_raw = beta_m.get("date") if isinstance(beta_m, dict) else None

    def _looks_like_yyyymmdd(raw: Any) -> bool:
        normalized = _normalize_date_str(str(raw or "").strip())
        return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", str(normalized or "")))

    has_beta_measurement_date = any(
        _looks_like_yyyymmdd(d)
        for d in str(beta_measurement_raw or "").split(",")
    )

    legacy_m = getattr(order, "measurement_date", None)
    if legacy_m and not (is_erp_order and has_beta_measurement_date):
        for d in str(legacy_m).split(","):
            if d.strip():
                nd = _normalize_date_str(d.strip())
                specs.append(
                    {
                        "kind": "measurement",
                        "date": nd,
                        "source": "legacy_column",
                        "item_index": None,
                    }
                )
                m_dates.add(nd)

    if is_erp_order and sd:
        if isinstance(beta_m, dict):
            bmd = beta_m.get("date")
            if bmd:
                for d in str(bmd).split(","):
                    if d.strip():
                        nd = _normalize_date_str(d.strip())
                        if nd not in m_dates:
                            specs.append(
                                {
                                    "kind": "measurement",
                                    "date": nd,
                                    "source": "beta_schedule",
                                    "item_index": None,
                                }
                            )
                            m_dates.add(nd)

        for idx, it in enumerate(sd.get("items") or []):
            if isinstance(it, dict):
                imd = it.get("measurement_date")
                if imd:
                    for d in str(imd).split(","):
                        if d.strip():
                            nd = _normalize_date_str(d.strip())
                            if nd not in m_dates:
                                specs.append(
                                    {
                                        "kind": "measurement",
                                        "date": nd,
                                        "source": "beta_item",
                                        "item_index": idx,
                                    }
                                )
                                m_dates.add(nd)

    as_visit_dates = set()
    if isinstance(getattr(order, "structured_data", None), dict):
        sd = order.structured_data
        schedule = sd.get("schedule") or {}
        as_visit = schedule.get("as_visit") or {}
        visit_date = (as_visit.get("date") or "").strip() if isinstance(as_visit, dict) else ""
        if visit_date:
            for d in visit_date.split(","):
                if d.strip():
                    nd = _normalize_date_str(d.strip())
                    if nd not in as_visit_dates:
                        specs.append(
                            {
                                "kind": "as_visit",
                                "date": nd,
                                "source": "structured_schedule",
                                "item_index": None,
                            }
                        )
                        as_visit_dates.add(nd)

    c_dates = set()
    legacy_c = getattr(order, "scheduled_date", None)
    if legacy_c:
        for d in str(legacy_c).split(","):
            if d.strip():
                nd = _normalize_date_str(d.strip())
                specs.append(
                    {
                        "kind": "construction",
                        "date": nd,
                        "source": "legacy_column",
                        "item_index": None,
                    }
                )
                c_dates.add(nd)

    if is_erp_order and sd:
        s_date = None
        sc = sd.get("schedule") or {}
        if isinstance(sc, dict):
            cd = sc.get("construction") or {}
            if isinstance(cd, dict):
                s_date = (cd.get("date") or "").strip() or None

        if s_date:
            for d in s_date.split(","):
                if d.strip():
                    nd = _normalize_date_str(d.strip())
                    if nd not in c_dates:
                        specs.append(
                            {
                                "kind": "construction",
                                "date": nd,
                                "source": "beta_schedule",
                                "item_index": None,
                            }
                        )
                        c_dates.add(nd)

        for idx, it in enumerate(sd.get("items") or []):
            if isinstance(it, dict):
                icd = it.get("construction_date")
                if icd:
                    for d in str(icd).split(","):
                        if d.strip():
                            nd = _normalize_date_str(d.strip())
                            if nd not in c_dates:
                                specs.append(
                                    {
                                        "kind": "construction",
                                        "date": nd,
                                        "source": "beta_item",
                                        "item_index": idx,
                                    }
                                )
                                c_dates.add(nd)

    return specs


def _schedule_date_signature(rows: Any) -> tuple[tuple[str, str, str, Any], ...]:
    """Return the comparable schedule-date relationship signature."""
    return tuple(
        sorted(
            (
                str(getattr(row, "kind", "") or ""),
                str(getattr(row, "date", "") or ""),
                str(getattr(row, "source", "") or ""),
                getattr(row, "item_index", None),
            )
            for row in (rows or [])
        )
    )


def _spec_signature(specs: list[dict[str, Any]]) -> tuple[tuple[str, str, str, Any], ...]:
    return tuple(
        sorted(
            (
                str(spec.get("kind") or ""),
                str(spec.get("date") or ""),
                str(spec.get("source") or ""),
                spec.get("item_index"),
            )
            for spec in specs
        )
    )


def _resolve_item_id_map(order: Any, db_session: Any, specs: list[dict[str, Any]]) -> dict[int, Any]:
    """Resolve ``{item_index: active identity UUID}`` for item-scoped schedule specs.

    ITEM-ID-00: schedule rows carry a stable ``item_id`` UUID, not the positional
    ``item_index``. Since ``sync_order_dates`` wholesale-replaces ``schedule_dates``,
    it must repopulate ``item_id`` from :class:`~models.OrderItemIdentity` on rebuild,
    otherwise a backfilled link would be lost on the next order edit. Returns an empty
    map for a not-yet-persisted order (no id → no registry rows yet) or when no spec is
    item-scoped. Uses ``no_autoflush`` so the read cannot re-enter this before_flush.
    """
    order_id = getattr(order, "id", None)
    if order_id is None:
        return {}
    indices = {s["item_index"] for s in specs if s.get("item_index") is not None}
    if not indices:
        return {}
    from foms.services.orders.item_identity import resolve_active_item_id

    resolved: dict[int, Any] = {}
    with db_session.no_autoflush:
        for idx in indices:
            resolved[idx] = resolve_active_item_id(db_session, order_id, idx)
    return resolved


def sync_order_dates(order: Any, db_session: Any = None) -> bool:
    """Extract dates from an order and refresh ``schedule_dates`` only when changed."""
    if db_session is None:
        db_session = get_db()

    specs = collect_order_schedule_date_specs(order)
    if _schedule_date_signature(getattr(order, "schedule_dates", [])) == _spec_signature(specs):
        return False

    item_id_map = _resolve_item_id_map(order, db_session, specs)
    order.schedule_dates = [
        OrderScheduleDate(
            kind=spec["kind"],
            date=spec["date"],
            source=spec["source"],
            item_index=spec["item_index"],
            item_id=(
                item_id_map.get(spec["item_index"])
                if spec["item_index"] is not None
                else None
            ),
        )
        for spec in specs
    ]
    return True


def _construction_dates_from_rows(rows: Any) -> set[str]:
    """일정 row 목록에서 정규화된 시공일 집합을 뽑는다.

    Args:
        rows: ``OrderScheduleDate`` 유사 객체 목록(``kind``·``date`` 속성 필요).

    Returns:
        정규화된 시공일 문자열 집합. 시공일이 없으면 빈 집합.
    """
    dates: set[str] = set()
    for row in rows or []:
        if str(getattr(row, "kind", "") or "") != "construction":
            continue
        normalized = _normalize_date_str(str(getattr(row, "date", "") or "").strip())
        if normalized:
            dates.add(str(normalized))
    return dates


def _join_construction_dates(dates: set[str]) -> str:
    """시공일 집합을 안정 정렬 콤마 문자열로 만든다.

    정렬을 고정해 **순서만 다른 저장이 허위 변경으로 보이지 않게** 한다.

    Args:
        dates: 정규화된 시공일 집합.

    Returns:
        ``"2026-07-20,2026-07-28"`` 형태 문자열(빈 집합이면 빈 문자열).
    """
    return ",".join(sorted(dates))


def _resolve_event_actor_and_source() -> tuple[int | None, str]:
    """이벤트 기록자(actor)와 쓰기 경로 힌트를 구한다.

    요청 컨텍스트가 있으면 세션 사용자 id 와 Flask endpoint 를, 없으면(부팅 백필·스크립트·
    워커) ``(None, "system")`` 을 돌려준다. 요청 밖 flush 에서 절대 예외를 던지지 않는다.

    Args:
        없음.

    Returns:
        ``(actor_user_id, source)`` — actor 는 미확인 시 ``None``.
    """
    try:
        from flask import has_request_context, request
        from flask import session as flask_session

        if not has_request_context():
            return None, "system"
        raw_user_id = flask_session.get("user_id")
        actor = int(raw_user_id) if str(raw_user_id or "").strip().isdigit() else None
        source = str(request.endpoint or request.path or "request")[:80]
        return actor, source
    except (RuntimeError, ImportError, ValueError, TypeError) as exc:
        logger.debug("[DateSync] actor resolve skipped outside request: %s", exc)
        return None, "system"


def _pending_event_state(session: Any) -> dict[Any, dict[str, Any]]:
    """트랜잭션 동안 주문별 시공일 이벤트를 **1건으로 합치기** 위한 상태 맵.

    한 요청이 여러 번 flush 하면(레거시 컬럼 먼저 → JSONB 나중 같은 2단 쓰기) 중간 상태마다
    diff 가 잡혀 이벤트가 2건 이상 난다. 그래서 트랜잭션 최초 값(origin)을 기억해 두고 이후
    flush 는 같은 이벤트의 ``to`` 만 갱신한다. 커밋/롤백 시 비운다.

    Args:
        session: 현재 SQLAlchemy 세션.

    Returns:
        ``{order_id: {"origin": set[str], "event": OrderEvent}}`` (없으면 새로 만들어 반환).
    """
    state = session.info.get(_CONSTRUCTION_EVENT_STATE)
    if not isinstance(state, dict):
        state = {}
        session.info[_CONSTRUCTION_EVENT_STATE] = state
    return state


def _discard_pending_event(session: Any, event: Any) -> None:
    """트랜잭션 중 값이 원래대로 되돌아왔을 때 이미 만든 이벤트를 취소한다.

    Args:
        session: 현재 SQLAlchemy 세션.
        event: 취소할 ``OrderEvent``(아직 flush 전이면 expunge, 이미 INSERT 됐으면 delete).

    Returns:
        None.
    """
    from sqlalchemy import inspect as sa_inspect

    if sa_inspect(event).persistent:
        session.delete(event)
    else:
        session.expunge(event)


def _emit_construction_date_event(
    session: Any, order: Any, before: set[str], after: set[str]
) -> None:
    """시공일 집합이 달라졌으면 ``CONSTRUCTION_DATE_CHANGED`` 를 같은 flush 에 반영한다.

    같은 트랜잭션에서 이미 이벤트를 만들었다면 새로 추가하지 않고 그 이벤트의 ``to`` 만
    갱신한다(경로당 정확히 1건). 값이 트랜잭션 최초값으로 되돌아오면 이벤트를 취소한다.

    Args:
        session: 현재 flush 중인 SQLAlchemy 세션.
        order: 대상 주문(영속 상태, ``id`` 필요).
        before: 재빌드 이전 시공일 집합(정규화됨).
        after: 재빌드 이후 시공일 집합(정규화됨).

    Returns:
        None.
    """
    if before == after:
        return
    state = _pending_event_state(session)
    entry = state.get(order.id)
    actor_id, source = _resolve_event_actor_and_source()
    if entry is None:
        event = OrderEvent(
            order_id=order.id,
            event_type="CONSTRUCTION_DATE_CHANGED",
            payload={
                "from": _join_construction_dates(before),
                "to": _join_construction_dates(after),
                "source": source,
            },
            created_by_user_id=actor_id,
        )
        session.add(event)
        state[order.id] = {"origin": set(before), "event": event}
        return

    origin, event = entry["origin"], entry["event"]
    if origin == after:
        _discard_pending_event(session, event)
        state.pop(order.id, None)
        return
    event.payload = {
        "from": _join_construction_dates(origin),
        "to": _join_construction_dates(after),
        "source": source,
    }


def _sync_order_and_emit_event(session: Any, order: Any, *, allow_event: bool) -> bool:
    """주문 1건의 일정 row 를 재빌드하고 필요 시 시공일 변경 이벤트를 남긴다.

    Args:
        session: 현재 flush 중인 SQLAlchemy 세션.
        order: 대상 주문.
        allow_event: 이벤트 emit 허용 여부(신규 생성·훅 재진입이면 False).

    Returns:
        일정 row 가 실제로 재빌드됐으면 True.
    """
    before = (
        _construction_dates_from_rows(getattr(order, "schedule_dates", []))
        if allow_event
        else set()
    )
    changed = bool(sync_order_dates(order, session))
    if changed and allow_event:
        after = _construction_dates_from_rows(getattr(order, "schedule_dates", []))
        _emit_construction_date_event(session, order, before, after)
    return changed


def _run_date_sync_flush(session: Any, order_cls: Any) -> None:
    """flush 대상 주문의 일정 row 재빌드 + 시공일 이벤트 emit 을 수행한다.

    Args:
        session: 현재 flush 중인 SQLAlchemy 세션.
        order_cls: ``Order`` 모델 클래스(모듈 최상위 import 순환 회피용 주입).

    Returns:
        None. 재빌드가 있었으면 dashcache 무효화 플래그를 ``session.info`` 에 남긴다.
    """
    changed_orders = [
        obj for obj in session.new.union(session.dirty) if isinstance(obj, order_cls)
    ]
    # 재진입 가드: 이 훅 안에서 다시 flush 가 돌더라도 같은 변경을 두 번 기록하지 않는다.
    reentrant = bool(session.info.get(_CONSTRUCTION_EVENT_GUARD))
    session.info[_CONSTRUCTION_EVENT_GUARD] = True
    try:
        schedule_changed = False
        for order in changed_orders:
            # 생성(신규·미영속)은 "이전 값"이 없으므로 이벤트 대상이 아니다.
            allow_event = (
                not reentrant
                and order not in session.new
                and getattr(order, "id", None) is not None
            )
            schedule_changed = (
                _sync_order_and_emit_event(session, order, allow_event=allow_event)
                or schedule_changed
            )
    finally:
        session.info[_CONSTRUCTION_EVENT_GUARD] = reentrant

    if schedule_changed or any(order in session.new for order in changed_orders):
        session.info["foms_dashcache_order_dates"] = True


def register_date_sync_listener() -> None:
    """Register the SQLAlchemy ``before_flush`` listener used for date sync.

    이 훅은 **모든 쓰기가 통과하는 유일 지점**이라, 시공일 변경 이벤트
    (``CONSTRUCTION_DATE_CHANGED``)의 SSOT 도 여기다. 라우트/서비스별 emit 은 두지 않는다
    (경로가 늘어날 때마다 구멍이 생기고 중복 기록이 난다).
    """
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    from models import Order

    @event.listens_for(Session, "before_flush")
    def before_flush(session, flush_context, instances):
        _run_date_sync_flush(session, Order)

    @event.listens_for(Session, "after_soft_rollback")
    def _reset_construction_event_state(session, previous_transaction):
        # 롤백된 트랜잭션의 이벤트 참조는 무효다 — 다음 트랜잭션으로 새어가면 안 된다.
        session.info.pop(_CONSTRUCTION_EVENT_STATE, None)

    @event.listens_for(Session, "after_commit")
    def _dashcache_after_commit_schedule_sync(session):
        session.info.pop(_CONSTRUCTION_EVENT_STATE, None)
        if not session.info.pop("foms_dashcache_order_dates", None):
            return
        try:
            from foms.services.common.dashboard_cache import invalidate_dashboard_family

            invalidate_dashboard_family("measurement")
            invalidate_dashboard_family("shipment")
        except Exception as exc:
            logger.warning(
                "[DashCache] after_commit invalidate failed (non-fatal): %s",
                exc,
                exc_info=True,
            )
