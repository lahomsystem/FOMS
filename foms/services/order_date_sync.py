"""Order schedule-date normalization and synchronization helpers."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from db import get_db
from foms.services.erp_order_flags import is_erp_order_record

logger = logging.getLogger(__name__)
from models import OrderScheduleDate

__all__ = [
    "collect_order_schedule_date_specs",
    "sync_order_dates",
    "register_date_sync_listener",
]


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


def sync_order_dates(order: Any, db_session: Any = None) -> bool:
    """Extract dates from an order and refresh ``schedule_dates`` only when changed."""
    if db_session is None:
        db_session = get_db()

    specs = collect_order_schedule_date_specs(order)
    if _schedule_date_signature(getattr(order, "schedule_dates", [])) == _spec_signature(specs):
        return False

    order.schedule_dates = [
        OrderScheduleDate(
            kind=spec["kind"],
            date=spec["date"],
            source=spec["source"],
            item_index=spec["item_index"],
        )
        for spec in specs
    ]
    return True


def register_date_sync_listener() -> None:
    """Register the SQLAlchemy ``before_flush`` listener used for date sync."""
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    from models import Order

    @event.listens_for(Session, "before_flush")
    def before_flush(session, flush_context, instances):
        changed_orders = [
            obj for obj in session.new.union(session.dirty) if isinstance(obj, Order)
        ]

        schedule_changed = False
        for order in changed_orders:
            schedule_changed = sync_order_dates(order, session) or schedule_changed

        if schedule_changed or any(order in session.new for order in changed_orders):
            session.info["foms_dashcache_order_dates"] = True

    @event.listens_for(Session, "after_commit")
    def _dashcache_after_commit_schedule_sync(session):
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
