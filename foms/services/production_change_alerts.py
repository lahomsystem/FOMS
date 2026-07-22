"""생산 파이프라인 변경 감지·묘비 수집 (태블릿 칸반 변경 가시성).

생산(제작대기/제작중/제작완료) 단계 주문 중 "생산 파이프라인 진입 이후"에 발생한, 일정에
영향을 주는 변경(시공일 변경·도면 재전달/수정요청)을 감지해 카드/시트에 노출한다. 팀
확인(ack)으로 감지 윈도를 리셋하고, 취소(soft delete)된 주문은 최근 14일간 묘비 카드로
잔류시킨다.

시간 비교 규약(중요):
    라이브 카드 변경 감지(윈도 vs 도면/시공일 이벤트)는 naive-to-naive 시계 비교다.
    ``OrderEvent.created_at``·``Order.created_at``·``erp_stage_updated_at`` 은 모두 DB
    naive datetime(서버 로컬 wall-clock)이고, ``drawing_transfer_history`` 의
    ``at``/``transferred_at`` 은 ``now_utc_naive()`` 로 기록된 naive 문자열이다. 운영(UTC
    서버)에서는 둘 다 UTC naive 라 직접 비교가 정확하다(tz-aware 변환·혼입 금지).

    단, **묘비 ack 판정은 시계 비교를 쓰지 않는다.** ``deleted_at`` 은 ``now_kst()`` KST
    wall-clock 이고 ``created_at`` 은 서버 로컬(운영=UTC)이라 삭제 직후 최대 9h 동안 ack가
    "과거"로 보이는 skew가 있다. 그래서 ack API가 payload에 ``deleted_at`` 마커를 심고,
    묘비는 그 마커 문자열 동등성으로만 확인 여부를 판정한다.
"""
from __future__ import annotations

import datetime
from typing import Any

from models import Order, OrderEvent
from foms.services.datetime_kst import get_today_kst
from foms.services.erp_display import _ensure_dict, _normalize_date_to_yyyymmdd
from foms.services.production_dashboard_display import (
    _production_first_item,
    _production_product_label,
    _production_stage_label_from_stage,
)

__all__ = [
    "PROD_STAGES",
    "collect_production_change_alerts",
    "collect_production_tombstones",
    "compute_window_start",
]

PROD_STAGES: frozenset[str] = frozenset(
    {"고객컨펌", "CONFIRM", "생산", "PRODUCTION", "시공", "CONSTRUCTION"}
)

_TOMBSTONE_DAYS = 14
_DRAWING_TS_FMT = "%Y-%m-%d %H:%M:%S"
_RELEVANT_EVENT_TYPES = (
    "PRODUCTION_CHANGE_ACK",
    "STAGE_CHANGED",
    "CONSTRUCTION_DATE_CHANGED",
)


def _date_to_md(value: Any) -> str:
    """YYYY-MM-DD(또는 정규화 가능한 날짜) → 'M/D'. 비거나 파싱 실패 시 '미정'."""
    norm = _normalize_date_to_yyyymmdd(value)
    if not norm:
        return "미정"
    try:
        d = datetime.datetime.strptime(norm, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return "미정"
    return f"{d.month}/{d.day}"


def _parse_drawing_entry_time(entry: dict[str, Any]) -> datetime.datetime | None:
    """도면 이력 entry 의 기록 시각(naive) 파싱.

    TRANSFER 는 ``transferred_at``, REQUEST_REVISION 은 ``at`` 키를 쓰며 둘 다
    ``'%Y-%m-%d %H:%M:%S'`` 포맷의 naive 문자열이다(now_utc_naive 기록).

    Args:
        entry: ``drawing_transfer_history`` 의 단일 항목 dict.

    Returns:
        파싱된 naive ``datetime`` 또는 파싱 불가 시 ``None``.
    """
    if not isinstance(entry, dict):
        return None
    raw = entry.get("at") or entry.get("transferred_at")
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return datetime.datetime.strptime(raw.strip()[:19], _DRAWING_TS_FMT)
    except ValueError:
        return None


def compute_window_start(
    order: Order, events: list[OrderEvent]
) -> datetime.datetime | None:
    """주문의 변경 감지 윈도 시작 시각(naive) 계산.

    우선순위: 최근 ``PRODUCTION_CHANGE_ACK`` → 최근 생산 진입 ``STAGE_CHANGED``
    (payload.to ∈ PROD_STAGES 이고 from ∉ PROD_STAGES) → ``erp_stage_updated_at`` →
    ``created_at``.

    Args:
        order: 대상 주문(ORM). ``erp_stage_updated_at``/``created_at`` 폴백에 사용.
        events: 해당 주문의 ``OrderEvent`` 리스트(정렬 무관).

    Returns:
        윈도 시작 naive ``datetime`` 또는 폴백도 없으면 ``None``.
    """
    ack_times = [
        e.created_at
        for e in events
        if e.event_type == "PRODUCTION_CHANGE_ACK" and e.created_at is not None
    ]
    if ack_times:
        return max(ack_times)

    entry_times: list[datetime.datetime] = []
    for e in events:
        if e.event_type != "STAGE_CHANGED" or e.created_at is None:
            continue
        payload = e.payload if isinstance(e.payload, dict) else {}
        if payload.get("to") in PROD_STAGES and payload.get("from") not in PROD_STAGES:
            entry_times.append(e.created_at)
    if entry_times:
        return max(entry_times)

    if getattr(order, "erp_stage_updated_at", None) is not None:
        return order.erp_stage_updated_at
    return getattr(order, "created_at", None)


def _build_alerts_for_order(
    events: list[OrderEvent],
    sd: dict[str, Any],
    window_start: datetime.datetime | None,
) -> list[dict[str, str]]:
    """단일 주문의 변경 alert 목록(윈도 이후만)."""
    alerts: list[dict[str, str]] = []
    for e in events:
        if e.event_type != "CONSTRUCTION_DATE_CHANGED" or e.created_at is None:
            continue
        if window_start is not None and e.created_at <= window_start:
            continue
        payload = e.payload if isinstance(e.payload, dict) else {}
        _from_md = _date_to_md(payload.get("from"))
        _to_md = _date_to_md(payload.get("to"))
        alerts.append(
            {
                "kind": "construction_date",
                "label": "시공일 변경",
                "detail": f"{_from_md} → {_to_md}",
                "from_md": _from_md,
                "to_md": _to_md,
            }
        )

    history = sd.get("drawing_transfer_history")
    for entry in history if isinstance(history, list) else []:
        ts = _parse_drawing_entry_time(entry)
        if ts is None:
            continue
        if window_start is not None and ts <= window_start:
            continue
        action = str((entry.get("action") or "")).strip().upper()
        if action == "TRANSFER":
            label = "도면 재전달"
        elif action == "REQUEST_REVISION":
            label = "도면 수정요청"
        else:
            continue
        note = entry.get("note")
        alerts.append(
            {
                "kind": "drawing",
                "label": label,
                "detail": note.strip() if isinstance(note, str) and note.strip() else "",
            }
        )
    return alerts


def collect_production_change_alerts(
    db: Any, orders: list[Order]
) -> dict[int, list[dict[str, str]]]:
    """페이지 주문들에 대해 ``order_id -> 변경 alert 목록`` 을 배치 계산한다.

    ``OrderEvent`` 는 ``order_id.in_(ids)`` 단일 쿼리로 로드하고(N+1 금지), 도면 이력은
    이미 로드된 ``structured_data`` 에서 파생한다. alert 없는 주문은 빈 리스트가 된다.

    Args:
        db: 활성 DB 세션.
        orders: 대상 주문 ORM 리스트(``id``·``structured_data`` 로드 상태여야 함).

    Returns:
        ``{order_id: [{'kind','label','detail'}, ...]}``.
    """
    result: dict[int, list[dict[str, str]]] = {}
    ids = [o.id for o in orders if getattr(o, "id", None) is not None]
    if not ids:
        return result

    events_by_order: dict[int, list[OrderEvent]] = {}
    rows = (
        db.query(OrderEvent)
        .filter(
            OrderEvent.order_id.in_(ids),
            OrderEvent.event_type.in_(_RELEVANT_EVENT_TYPES),
        )
        .all()
    )
    for ev in rows:
        events_by_order.setdefault(ev.order_id, []).append(ev)

    for o in orders:
        if getattr(o, "id", None) is None:
            continue
        events = events_by_order.get(o.id, [])
        window_start = compute_window_start(o, events)
        sd = _ensure_dict(getattr(o, "structured_data", None))
        result[o.id] = _build_alerts_for_order(events, sd, window_start)
    return result


def collect_production_tombstones(
    db: Any, user: Any, erp_mine_only: bool
) -> list[dict[str, Any]]:
    """최근 14일 내 취소(soft delete)된 생산 파이프라인 주문의 묘비 카드 목록.

    조건: ``status='DELETED'`` + ``deleted_at`` not null + ``is_erp_order`` +
    ``erp_stage_code`` ∈ PROD_STAGES + ``deleted_at`` 이 최근 14일 이내. 단, 삭제 후
    ``PRODUCTION_CHANGE_ACK`` 이 있으면(팀이 이미 확인) 제외한다. ``erp_mine_only`` 면
    ``is_order_related_to_user`` 로 내 주문만 남긴다.

    Args:
        db: 활성 DB 세션.
        user: 현재 사용자(mine 필터·None 허용).
        erp_mine_only: 내 주문만 볼지 여부.

    Returns:
        ``[{'id','customer_name','bucket','deleted_md','product_label'}, ...]``.
    """
    cutoff = (get_today_kst() - datetime.timedelta(days=_TOMBSTONE_DAYS)).isoformat()
    candidates = (
        db.query(Order)
        .filter(
            Order.status == "DELETED",
            Order.deleted_at.isnot(None),
            Order.deleted_at >= cutoff,
            Order.is_erp_order.is_(True),
            Order.erp_stage_code.in_(list(PROD_STAGES)),
        )
        .all()
    )
    if erp_mine_only and user:
        from foms.services.erp_permissions import is_order_related_to_user

        candidates = [o for o in candidates if is_order_related_to_user(o, user)]
    if not candidates:
        return []

    ids = [o.id for o in candidates]
    ack_markers_by_order: dict[int, set[str]] = {}
    ack_rows = (
        db.query(OrderEvent)
        .filter(
            OrderEvent.order_id.in_(ids),
            OrderEvent.event_type == "PRODUCTION_CHANGE_ACK",
        )
        .all()
    )
    for ev in ack_rows:
        payload = ev.payload if isinstance(ev.payload, dict) else {}
        marker = payload.get("deleted_at")
        if isinstance(marker, str):
            ack_markers_by_order.setdefault(ev.order_id, set()).add(marker)

    tombstones: list[dict[str, Any]] = []
    for o in candidates:
        # 이 삭제 시점을 고정한 ack 마커가 있으면(=묘비 확인함) 제외. 시계 비교 없음.
        if str(o.deleted_at) in ack_markers_by_order.get(o.id, ()):
            continue
        sd = _ensure_dict(o.structured_data)
        _first, items = _production_first_item(sd)
        tombstones.append(
            {
                "id": o.id,
                "customer_name": (((sd.get("parties") or {}).get("customer") or {}).get("name")) or "-",
                "bucket": _production_stage_label_from_stage(o.erp_stage_code or ""),
                "deleted_md": _date_to_md((o.deleted_at or "")[:10]),
                "product_label": _production_product_label(items),
            }
        )
    return tombstones
