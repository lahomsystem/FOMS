"""Order schedule-date normalization and synchronization helpers."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from db import get_db
from foms.services.common.dashboard_cache import (
    ALL_DASHBOARD_FAMILIES,
    dashboard_families_for_schedule_change,
    invalidate_all_dashboard_slice_caches,
    invalidate_dashboard_families,
)
from foms.services.erp_order_flags import (
    is_erp_draft_structured_data,
    is_erp_order_draft,
    is_erp_order_record,
)

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
#: 커밋 뒤 비울 대시보드 family 모음(``Session.info``). 값은 family 문자열 집합, ``"*"`` 는 전부.
_DASHCACHE_DATES_KEY = "foms_dashcache_order_dates"
#: 이번 트랜잭션에서 주문의 탭 소속 축(status·삭제·ERP·단계·초안)이 바뀌었는가(``Session.info``).
_DASHCACHE_MEMBERSHIP_KEY = "foms_dashcache_order_membership_changed"
_DASHCACHE_ALL = "*"
#: 탭 소속을 가르는 평면 컬럼 — 모든 family 기준 쿼리의 active/draft 필터와 단계 범위.
_MEMBERSHIP_COLUMNS = ("status", "deleted_at", "is_erp_order", "erp_stage_code")


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


def _dates_from_rows(rows: Any, kind: str) -> set[str]:
    """일정 row 목록에서 ``kind`` 가 같은 정규화 날짜 집합을 뽑는다.

    Args:
        rows: ``OrderScheduleDate`` 유사 객체 목록(``kind``·``date`` 속성 필요).
        kind: ``"construction"``·``"measurement"`` 등 일정 종류.

    Returns:
        정규화된 날짜 문자열 집합. 해당 종류가 없으면 빈 집합.
    """
    dates: set[str] = set()
    for row in rows or []:
        if str(getattr(row, "kind", "") or "") != kind:
            continue
        normalized = _normalize_date_str(str(getattr(row, "date", "") or "").strip())
        if normalized:
            dates.add(str(normalized))
    return dates


def _construction_dates_from_rows(rows: Any) -> set[str]:
    """일정 row 목록에서 정규화된 시공일 집합을 뽑는다(:func:`_dates_from_rows` 래퍼).

    Args:
        rows: ``OrderScheduleDate`` 유사 객체 목록(``kind``·``date`` 속성 필요).

    Returns:
        정규화된 시공일 문자열 집합. 시공일이 없으면 빈 집합.
    """
    return _dates_from_rows(rows, "construction")


def _committed_is_draft(order: Any) -> bool:
    """이번 flush **직전**(마지막 flush/로드 시점) 주문이 ERP 드래프트였는지 본다.

    드래프트 승격(PUT 이 ``status='DRAFT'`` → 단계 코드로 바꾸는 경로)은 실측일 집합이
    그대로라 날짜 비교로는 안 보인다. 그래서 SQLAlchemy 속성 기록에서 옛 값을 읽는다.

    Args:
        order: flush 대상 주문(영속 상태).

    Returns:
        옛 ``status`` 가 ``'DRAFT'`` 이거나 옛 ``structured_data.meta.draft`` 가 True 면 True.
        ERP 주문이 아니거나 신규 주문이면 False.
    """
    if not is_erp_order_record(order) or getattr(order, "id", None) is None:
        return False
    from sqlalchemy import inspect as sa_inspect

    attrs = sa_inspect(order).attrs
    status_hist = attrs.status.history
    old_status = (list(status_hist.deleted) or list(status_hist.unchanged) or [None])[0]
    if str(old_status or "").upper() == "DRAFT":
        return True
    sd_hist = attrs.structured_data.history
    old_sd = (list(sd_hist.deleted) or list(sd_hist.unchanged) or [None])[0]
    return is_erp_draft_structured_data(old_sd)


def _workflow_stage(structured_data: Any) -> str:
    """structured_data 의 ``workflow.stage`` 원문(없으면 빈 문자열)."""
    if not isinstance(structured_data, dict):
        return ""
    workflow = structured_data.get("workflow")
    return str((workflow or {}).get("stage") or "") if isinstance(workflow, dict) else ""


def _order_membership_changed(order: Any) -> bool:
    """이번 flush 에서 주문의 탭 소속을 가르는 값이 바뀌었는가(SQLAlchemy 속성 기록으로 본다).

    status·삭제·ERP 여부·단계 코드·초안 표식·``workflow.stage`` 중 하나라도 바뀌면 True.
    이런 전이와 날짜 변경이 한 트랜잭션에 섞이면 주문이 어느 탭에 새로 나타나거나
    사라지는지 날짜만으로는 모른다 — 커밋 뒤 전부 비운다(예전 동작 그대로).

    Args:
        order: flush 대상 주문(영속 상태).

    Returns:
        소속 축이 바뀌었으면 True. 신규(미영속) 주문이면 False(호출자가 따로 다룬다).
    """
    if getattr(order, "id", None) is None:
        return False
    from sqlalchemy import inspect as sa_inspect

    attrs = sa_inspect(order).attrs
    for name in _MEMBERSHIP_COLUMNS:
        if getattr(attrs, name).history.has_changes():
            return True
    if _committed_is_draft(order) != is_erp_order_draft(order):
        return True
    sd_hist = attrs.structured_data.history
    old_values = list(sd_hist.deleted) or list(sd_hist.unchanged)
    if not sd_hist.has_changes() or not old_values:
        # 옛 값을 기록에서 못 읽으면(만료 뒤 재대입) 단계 비교를 하지 않는다 — 단계 전이는
        # 단계 코드 컬럼(sync_erp_flat_columns)과 MUT-CACHE-01 리스너가 따로 잡는다.
        return False
    return _workflow_stage(old_values[0]) != _workflow_stage(getattr(order, "structured_data", None))


def _collect_dashcache_scope(
    session: Any,
    order: Any,
    *,
    is_new: bool,
    schedule_changed: bool,
    before_signature: tuple[tuple[str, str, str, Any], ...],
) -> None:
    """커밋 뒤 비울 대시보드 범위를 이 주문 몫만큼 ``session.info`` 에 모은다(P1-2).

    예전에는 일정 행이 하나라도 바뀌거나 새 주문이 생기면 7 family 를 전부 비웠다. 지금은
    바뀐 일정 **종류**가 읽히는 family 만 모은다(``dashboard_families_for_schedule_change``).
    전부 비우는 경우는 그대로 둔다 — 새 비초안 주문(모든 탭에 새로 나타날 수 있다), 같은
    트랜잭션의 소속 축 변화(:func:`_order_membership_changed`), 모르는 일정 종류.
    초안은 어느 대시보드에도 없으므로(모든 family 기준 쿼리가 ``active_filter`` 로 뺀다)
    새 초안·초안끼리의 날짜 변경은 아무것도 모으지 않는다.

    Args:
        session: 현재 flush 중인 세션.
        order: 대상 주문.
        is_new: 이번 flush 에서 처음 영속되는 주문인가.
        schedule_changed: 이번 flush 에서 일정 행이 재빌드됐는가.
        before_signature: 재빌드 전 일정 행 서명(:func:`_schedule_date_signature`).
    """
    if is_new:
        if not is_erp_order_draft(order):
            session.info.setdefault(_DASHCACHE_DATES_KEY, set()).add(_DASHCACHE_ALL)
        return
    if _order_membership_changed(order):
        session.info[_DASHCACHE_MEMBERSHIP_KEY] = True
    if not schedule_changed:
        return
    if is_erp_order_draft(order) and _committed_is_draft(order):
        return
    # 출처(source)만 바뀐 행(평면 컬럼 동기화로 legacy_column ↔ beta_schedule)은 날짜가 같아
    # 어느 캐시 DTO 도 바꾸지 않는다 — (종류, 날짜, 품목 위치)로만 비교한다.
    def _dated(signature):
        return {(kind, date, item_index) for kind, date, _source, item_index in signature}

    changed_rows = _dated(before_signature) ^ _dated(
        _schedule_date_signature(getattr(order, "schedule_dates", []))
    )
    if not changed_rows:
        return
    kinds = {row[0] for row in changed_rows}
    item_level = any(row[2] is not None for row in changed_rows)
    families = dashboard_families_for_schedule_change(kinds, item_level=item_level)
    session.info.setdefault(_DASHCACHE_DATES_KEY, set()).update(families)


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


def pending_construction_date_changes(session: Any) -> dict[int, dict[str, str]]:
    """이번 트랜잭션에서 **아직 커밋되지 않은** 주문별 시공일 변경을 읽기 전용으로 노출한다.

    :data:`_CONSTRUCTION_EVENT_STATE` 의 뷰다. 소비자(출고 벨 알림 등)가 내부 상태 구조나
    아직 flush 중일 수 있는 ``OrderEvent`` 객체에 직접 손대지 않게 하려고 값만 복사해 준다.
    ``__all__`` 에는 넣지 않는다 — 공개 계약은 네임스페이스 표면 테스트가 3개로 고정한다.

    Args:
        session: 현재 세션.

    Returns:
        ``{order_id: {"from": "...", "to": "..."}}``. 변경이 없으면 빈 dict.
    """
    changes: dict[int, dict[str, str]] = {}
    for order_id, entry in (session.info.get(_CONSTRUCTION_EVENT_STATE) or {}).items():
        payload = getattr(entry.get("event"), "payload", None)
        if not isinstance(payload, dict):
            continue
        changes[int(order_id)] = {
            "from": str(payload.get("from") or ""),
            "to": str(payload.get("to") or ""),
        }
    return changes


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


def _detect_measure_same_day(
    session: Any, order: Any, before: set[str], was_draft: bool
) -> None:
    """sync 뒤 실측일 집합을 구해 당일 실측 긴급 알림 판정기에 넘긴다(DB I/O 없음).

    Args:
        session: 현재 flush 중인 세션.
        order: 대상 주문.
        before: sync 전 실측일 집합(신규 주문이면 빈 집합).
        was_draft: 이번 flush 직전 드래프트였는지.

    Returns:
        None. 판정 상태는 ``session.info`` 에 쌓인다(발송은 커밋 뒤).
    """
    from foms.services.notifications.measure_same_day import detect_same_day_additions

    after = _dates_from_rows(getattr(order, "schedule_dates", []), "measurement")
    detect_same_day_additions(
        session,
        order,
        before_dates=before,
        after_dates=after,
        was_draft=was_draft,
        is_draft=is_erp_order_draft(order),
    )


def _run_date_sync_flush(session: Any, order_cls: Any) -> None:
    """flush 대상 주문의 일정 row 재빌드 + 시공일 이벤트 emit 을 수행한다.

    Args:
        session: 현재 flush 중인 SQLAlchemy 세션.
        order_cls: ``Order`` 모델 클래스(모듈 최상위 import 순환 회피용 주입).

    Returns:
        None. 커밋 뒤 비울 대시보드 범위를 ``session.info`` 에 모은다(:func:`_collect_dashcache_scope`).
    """
    changed_orders = [
        obj for obj in session.new.union(session.dirty) if isinstance(obj, order_cls)
    ]
    # 재진입 가드: 이 훅 안에서 다시 flush 가 돌더라도 같은 변경을 두 번 기록하지 않는다.
    reentrant = bool(session.info.get(_CONSTRUCTION_EVENT_GUARD))
    session.info[_CONSTRUCTION_EVENT_GUARD] = True
    try:
        for order in changed_orders:
            is_new = order in session.new or getattr(order, "id", None) is None
            # 생성(신규·미영속)은 "이전 값"이 없으므로 시공일 이벤트 대상이 아니다.
            allow_event = not reentrant and not is_new
            # 당일 실측 긴급 알림은 신규 주문도 본다(이전 = 빈 집합). 재진입 flush 만 제외.
            allow_measure = not reentrant
            measure_before: set[str] = (
                _dates_from_rows(getattr(order, "schedule_dates", []), "measurement")
                if allow_measure and not is_new
                else set()
            )
            was_draft = _committed_is_draft(order) if allow_measure and not is_new else False
            before_signature = (
                () if is_new else _schedule_date_signature(getattr(order, "schedule_dates", []))
            )
            order_schedule_changed = _sync_order_and_emit_event(
                session, order, allow_event=allow_event
            )
            if allow_measure:
                _detect_measure_same_day(session, order, measure_before, was_draft)
            _collect_dashcache_scope(
                session,
                order,
                is_new=is_new,
                schedule_changed=order_schedule_changed,
                before_signature=before_signature,
            )
    finally:
        session.info[_CONSTRUCTION_EVENT_GUARD] = reentrant


def register_date_sync_listener() -> None:
    """Register the SQLAlchemy ``before_flush`` listener used for date sync.

    이 훅은 **모든 쓰기가 통과하는 유일 지점**이라, 시공일 변경 이벤트
    (``CONSTRUCTION_DATE_CHANGED``)의 SSOT 도 여기다. 라우트/서비스별 emit 은 두지 않는다
    (경로가 늘어날 때마다 구멍이 생기고 중복 기록이 난다).

    같은 이유로 그 이벤트의 소비자인 **출고 벨 알림 리스너도 여기서 함께 등록**한다
    (:func:`foms.services.notifications.shipment_change.register_shipment_change_alert_listener`).
    등록 지점이 갈리면 "이벤트는 나는데 알림만 안 오는" 반쪽 배선이 생긴다.
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
        scope = session.info.pop(_DASHCACHE_DATES_KEY, None)
        membership_changed = session.info.pop(_DASHCACHE_MEMBERSHIP_KEY, None)
        if not scope:
            return
        try:
            # 날짜는 실측/출고만의 축이 아니다(2026-08-10 조사): 시공일은 시공 D-3·생산 D-2
            # 숫자판, 실측일은 orders·생산 D-4 숫자판도 흔든다 — 종류별 범위가 그걸 담는다
            # (dashboard_cache._SCHEDULE_KIND_FAMILIES). 도면 큐(접수순 id)·이력(검색·접수일)
            # 캐시는 일정 날짜를 담지 않는다. 단계 이동·삭제·초안 승격 같은 소속 변화가 같은
            # 트랜잭션에 섞이면 어느 탭이 바뀔지 모르므로 예전처럼 전부 비운다.
            families = tuple(f for f in ALL_DASHBOARD_FAMILIES if f in scope)
            if _DASHCACHE_ALL in scope or membership_changed or families == ALL_DASHBOARD_FAMILIES:
                invalidate_all_dashboard_slice_caches()
            else:
                invalidate_dashboard_families(*families)
        except Exception as exc:
            logger.warning(
                "[DashCache] after_commit invalidate failed (non-fatal): %s",
                exc,
                exc_info=True,
            )

    # 소비자 배선: 시공일 변경 이벤트를 벨/푸시로 내보내는 before_commit·after_commit 리스너.
    # (자체 중복 등록 가드가 있어 이 함수가 여러 번 불려도 알림이 2배로 나지 않는다.)
    from foms.services.notifications.shipment_change import (
        register_shipment_change_alert_listener,
    )

    register_shipment_change_alert_listener()

    # 소비자 배선: 실측일에 오늘(KST)이 새로 들어온 주문을 커밋 뒤 영업에게 알린다.
    # 판정 입력은 위 before_flush 가 모은다(자체 중복 등록 가드가 있다).
    from foms.services.notifications.measure_same_day import (
        register_measure_same_day_listener,
    )

    register_measure_same_day_listener()
