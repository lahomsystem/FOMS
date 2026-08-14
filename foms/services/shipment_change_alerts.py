"""출고 대시보드 시공일 변경 알림 수집 (T2).

출고 대시보드는 특정 날짜의 시공 건을 보고 상차·팀 배정·차량을 준비한다. 그 주문의
시공일이 **다른 화면에서** 바뀌면 준비해 둔 상차 목록과 팀 부하가 조용히 어긋나므로,
변경 사실을 행 배지와 상단 배너로 노출한다.

읽는 이벤트는 두 종뿐이다 — T1 이 SSOT 로 통합한 ``CONSTRUCTION_DATE_CHANGED``
(`foms/services/order_date_sync.py` 의 전역 ``before_flush``, 모든 쓰기 경로 공통)와 본
도메인 전용 확인 마커 ``SHIPMENT_CHANGE_ACK``. 둘을 **배치 1쿼리**
(``order_id.in_(ids)`` + ``event_type.in_(...)``)로 읽는다(N+1 금지 — 스펙 §6, `/erp/shipment`
fragment TTFB 예산 291ms).

확인(ack) 모델 — 생산 칸반(``production_change_alerts.py``)과 **의도적으로 다른 점**:

* **개인별**: 본인이 낸 ``SHIPMENT_CHANGE_ACK`` 이후의 변경만 ``alerts`` 다. 동료가 확인해도
  내 화면은 그대로다(``created_by_user_id`` 로 구분).
* **시간 상한 없음**: 생산 선례에는 생산 진입(entry) 윈도와 묘비 14일 컷오프가 있지만 출고는
  두지 않는다(사용자 결정). 미확인 변경은 **확인할 때까지** 계속 보인다 — 오래됐다고 사라지지
  않는다.
* ``history`` 는 ack 와 무관한 전체 변경 이력(향후 펼침 뷰용)이라 ``alerts ⊆ history`` 다.

시간 비교 규약: ``OrderEvent.created_at`` 기본값이 ``now_utc_naive`` 라 naive-to-naive 직접
비교가 정확하다(tz-aware 변환·혼입 금지). dev DB 의 **기존** 행만 옛 서버-로컬(KST) 기록이
섞일 수 있고 운영은 전부 UTC 라 무영향.

날짜 표기 규약: payload ``from``/``to`` 는 T1 이 **정규화 + 안정 정렬 후 콤마 연결**한
문자열이다(``"2026-07-20,2026-07-28"``). 표시용으로는 토큰마다 ``M/D`` 로 바꿔 ``", "`` 로
잇고, :data:`_MULTI_DATE_DISPLAY_CAP` 개를 넘으면 ``"7/20, 7/22, 7/25 외 2"`` 로 줄인다.
**손상·레거시 payload 에 절대 예외를 던지지 않는다** — dict 가 아니거나 키가 없거나 정규화
안 된 ``2026/07/20`` 이 와도 살릴 수 있는 만큼만 표시하고(전부 실패 시 ``미정``) 사유는
debug 로그로 남긴다. **이전 시공일을 읽지 못하면(표시상 ``미정``) 최초 지정**이므로
표시에서 제외한다 — ``미정 → 8/14`` 는 정상 배정이고, ``8/12 → 8/14`` 만 변경 알림이다.
양쪽이 모두 ``미정`` 인 이벤트도 정보가 0이라 제외한다.

배너 요약은 :func:`build_shipment_change_banner` 가 **추가 쿼리 없이**
:func:`collect_shipment_change_alerts` 결과에서 파생한다(AS 배너 선례
``as_dashboard_display._drift_banner_chip`` 와 같은 ``{count, chips, overflow}`` 계약).
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from foms.services.erp_display import _ensure_dict, _normalize_date_to_yyyymmdd
from models import Order, OrderEvent

logger = logging.getLogger(__name__)

__all__ = [
    "SHIPMENT_ACK_EVENT",
    "SHIPMENT_CHANGE_EVENT",
    "SHIPMENT_RELEVANT_EVENT_TYPES",
    "build_shipment_change_banner",
    "collect_shipment_change_alerts",
    "compute_shipment_ack_window",
]

#: 출고 전용 개인별 확인 마커(ack API 가 쓴다). 생산의 ``PRODUCTION_CHANGE_ACK`` 과 별개다.
SHIPMENT_ACK_EVENT = "SHIPMENT_CHANGE_ACK"
#: T1 SSOT 가 남기는 시공일 변경 이벤트(생산 칸반과 공유하는 소비 대상).
SHIPMENT_CHANGE_EVENT = "CONSTRUCTION_DATE_CHANGED"
#: 배치 1쿼리가 읽는 event_type 집합.
SHIPMENT_RELEVANT_EVENT_TYPES: tuple[str, str] = (SHIPMENT_ACK_EVENT, SHIPMENT_CHANGE_EVENT)

#: 배너 칩 상한(초과분은 ``overflow`` 로 센다) — AS 배너와 동일 값.
BANNER_CHIP_LIMIT = 5
#: 다중 시공일 표기 시 그대로 나열할 최대 개수(나머지는 ``외 N``).
_MULTI_DATE_DISPLAY_CAP = 3
#: 날짜를 하나도 못 읽었을 때의 표시 문자열.
_UNKNOWN_DATE = "미정"


def _split_date_tokens(value: Any) -> list[str]:
    """payload 의 날짜 값을 토큰 리스트로 만든다(콤마 연결·리스트·단일값 모두 허용).

    Args:
        value: payload ``from``/``to`` 원본. 문자열·리스트·튜플·기타 스칼라 허용.

    Returns:
        공백 제거된 비어 있지 않은 토큰 리스트. 값이 없으면 빈 리스트.
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        raw_tokens = [str(v) for v in value]
    else:
        raw_tokens = str(value).split(",")
    return [tok.strip() for tok in raw_tokens if str(tok).strip()]


def _token_to_md(token: str) -> str | None:
    """단일 날짜 토큰 → ``M/D``. 못 읽으면 ``None``(호출부가 조용히 건너뛴다).

    T1 이후 payload 는 ``YYYY-MM-DD`` 로 정규화되지만, 그 이전에 쌓인 행은 ``2026/07/20``
    같은 raw 표기일 수 있어 구분자만 바꿔 한 번 더 시도한다.

    Args:
        token: 날짜 문자열 1개.

    Returns:
        ``"7/20"`` 형태 문자열 또는 파싱 불가 시 ``None``.
    """
    normalized = _normalize_date_to_yyyymmdd(token)
    if not normalized:
        normalized = _normalize_date_to_yyyymmdd(token.replace("/", "-").replace(".", "-"))
    if not normalized:
        return None
    try:
        parsed = datetime.datetime.strptime(normalized, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    return f"{parsed.month}/{parsed.day}"


def _is_initial_date_assignment(from_value: Any) -> bool:
    """이전 시공일이 없으면 최초 지정이다(배지·벨 알림 대상 아님).

    빈 값·파싱 불가(표시상 ``미정``)는 "아직 날짜가 없었다"와 같다. 이미 잡힌 날짜를
    지우는 경우(``8/14 → 미정``)는 ``from`` 이 읽히므로 여기 해당하지 않는다.

    Args:
        from_value: 이벤트 payload ``from`` 원본.

    Returns:
        최초 지정이면 True.
    """
    return _dates_to_md(from_value) == _UNKNOWN_DATE


def _dates_to_md(value: Any) -> str:
    """콤마 연결 다중 시공일 → 읽을 수 있는 ``M/D`` 표기(상한 초과분은 ``외 N``).

    예: ``"2026-07-20,2026-07-22"`` → ``"7/20, 7/22"``,
    4개 이상이면 ``"7/20, 7/22, 7/25 외 1"``. 하나도 못 읽으면 ``"미정"``.

    Args:
        value: payload ``from``/``to`` 원본(형식 불문 — 예외를 던지지 않는다).

    Returns:
        표시용 문자열(항상 비어 있지 않다).
    """
    labels: list[str] = []
    for token in _split_date_tokens(value):
        md = _token_to_md(token)
        if md is None:
            logger.debug("[SHIPMENT_ALERT] 시공일 토큰 파싱 실패(건너뜀): %r", token)
            continue
        labels.append(md)
    if not labels:
        return _UNKNOWN_DATE
    if len(labels) <= _MULTI_DATE_DISPLAY_CAP:
        return ", ".join(labels)
    head = ", ".join(labels[:_MULTI_DATE_DISPLAY_CAP])
    return f"{head} 외 {len(labels) - _MULTI_DATE_DISPLAY_CAP}"


def _build_change_item(payload: Any) -> dict[str, str] | None:
    """``CONSTRUCTION_DATE_CHANGED`` payload → 표시 항목 1건(손상 payload 내성).

    Args:
        payload: 이벤트 payload(dict 가 아니어도 죽지 않는다).

    Returns:
        ``{"kind", "label", "from_md", "to_md", "detail"}``. 최초 지정(``미정 → 날짜``)이거나
        이전 시공일을 못 읽은 이벤트는 ``None``(표시 제외).
    """
    if payload is not None and not isinstance(payload, dict):
        logger.debug("[SHIPMENT_ALERT] dict 아닌 payload 무시: %s", type(payload).__name__)
    data = payload if isinstance(payload, dict) else {}
    from_raw = data.get("from")
    if _is_initial_date_assignment(from_raw):
        logger.debug("[SHIPMENT_ALERT] 최초 시공일 지정(또는 날짜 없음) 제외: %r", data)
        return None
    from_md = _dates_to_md(from_raw)
    to_md = _dates_to_md(data.get("to"))
    return {
        "kind": "construction_date",
        "label": "시공일 변경",
        "from_md": from_md,
        "to_md": to_md,
        # 생산 선례와 같은 하위호환 표시 문자열(공유 매크로가 그대로 쓴다).
        "detail": f"{from_md} → {to_md}",
    }


def compute_shipment_ack_window(
    events: list[OrderEvent], user_id: int | None
) -> datetime.datetime | None:
    """이 사용자의 미확인 판정 기준 시각(naive) — 본인 최근 ``SHIPMENT_CHANGE_ACK``.

    생산 선례와 달리 **폴백 윈도가 없다**. 확인한 적이 없으면 ``None`` 을 돌려주고, 그러면
    아무리 오래된 변경도 계속 ``alerts`` 로 남는다(시간 상한 없음 — 사용자 결정).

    Args:
        events: 해당 주문의 ``OrderEvent`` 리스트(정렬 무관, 두 event_type 혼재).
        user_id: 현재 사용자 id. ``None`` 이면 개인 ack 가 없는 것으로 본다.

    Returns:
        본인 최근 ack 시각 또는 ``None``(확인 이력 없음).
    """
    if user_id is None:
        return None
    ack_times = [
        e.created_at
        for e in events
        if e.event_type == SHIPMENT_ACK_EVENT
        and e.created_at is not None
        and e.created_by_user_id == user_id
    ]
    return max(ack_times) if ack_times else None


def _split_alerts_history(
    events: list[OrderEvent], ack_window: datetime.datetime | None
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """단일 주문의 변경 이벤트를 한 번만 파싱해 ``(alerts, history)`` 로 나눈다.

    ``history`` 는 전체 변경(ack 무관), ``alerts`` 는 ``ack_window`` 이후 미확인 변경이다.
    같은 dict 를 두 리스트가 공유한다(읽기 전용 사용 전제).

    Args:
        events: 해당 주문의 ``OrderEvent`` 리스트.
        ack_window: 본인 최근 ack 시각(``None`` 이면 전부 미확인).

    Returns:
        ``(alerts, history)`` — 둘 다 시간 오름차순.
    """
    alerts: list[dict[str, str]] = []
    history: list[dict[str, str]] = []
    changes = [
        e for e in events if e.event_type == SHIPMENT_CHANGE_EVENT and e.created_at is not None
    ]
    for event in sorted(changes, key=lambda e: (e.created_at, e.id or 0)):
        item = _build_change_item(event.payload)
        if item is None:
            continue
        history.append(item)
        if ack_window is None or event.created_at > ack_window:
            alerts.append(item)
    return alerts, history


def collect_shipment_change_alerts(
    db: Any, orders: list[Order], user_id: int | None
) -> dict[int, dict[str, list[dict[str, str]]]]:
    """페이지 주문들의 시공일 변경을 개인별로 배치 계산한다(쿼리 1회).

    ``OrderEvent`` 를 ``order_id.in_(ids)`` + ``event_type.in_(...)`` 단일 쿼리로 읽고
    (N+1 금지), 주문별로 ``alerts``(본인 미확인)와 ``history``(전체 이력)를 만든다.
    **대시보드 슬라이스 캐시 밖**에서 호출해야 한다(TTL 300s stale 경고 방지 — 스펙 §4.1).

    Args:
        db: 활성 DB 세션.
        orders: 대상 주문 ORM 리스트(``id`` 가 로드된 상태여야 한다).
        user_id: 현재 사용자 id(개인별 ack 판정). ``None`` 이면 ack 없음(alerts == history).

    Returns:
        ``{order_id: {'alerts': [...], 'history': [...]}}``. 주문이 없으면 빈 dict.
    """
    result: dict[int, dict[str, list[dict[str, str]]]] = {}
    ids = [o.id for o in orders if getattr(o, "id", None) is not None]
    if not ids:
        return result

    rows = (
        db.query(OrderEvent)
        .filter(
            OrderEvent.order_id.in_(ids),
            OrderEvent.event_type.in_(SHIPMENT_RELEVANT_EVENT_TYPES),
        )
        .all()
    )
    events_by_order: dict[int, list[OrderEvent]] = {}
    for event in rows:
        events_by_order.setdefault(event.order_id, []).append(event)

    for order in orders:
        order_id = getattr(order, "id", None)
        if order_id is None:
            continue
        events = events_by_order.get(order_id, [])
        alerts, history = _split_alerts_history(
            events, compute_shipment_ack_window(events, user_id)
        )
        result[order_id] = {"alerts": alerts, "history": history}
    return result


def _chip_customer_name(order: Order) -> str:
    """칩에 쓸 고객명(flat 컬럼 우선, 비면 structured_data 폴백, 없으면 빈 문자열)."""
    name = str(getattr(order, "customer_name", "") or "").strip()
    if name:
        return name
    sd = _ensure_dict(getattr(order, "structured_data", None))
    customer = (sd.get("parties") or {}).get("customer") if isinstance(sd, dict) else None
    if isinstance(customer, dict):
        return str(customer.get("name") or "").strip()
    return ""


def _banner_chip(order: Order, alerts: list[dict[str, str]]) -> dict[str, Any]:
    """미확인 변경이 있는 주문 1건 → 배너 점프 칩(고객명 · #id · ``8/5 → 8/12``).

    변경이 여러 번이면 **최초 from 과 최신 to** 로 이동 폭 전체를 한 줄로 보여준다
    (중간 경유 날짜는 행 배지·펼침 이력이 담당한다).

    Args:
        order: 대상 주문(고객명·id 소유).
        alerts: 그 주문의 미확인 변경 목록(시간 오름차순, 비어 있지 않음).

    Returns:
        템플릿이 그대로 배치하는 dict — ``order_id``/``customer_name``/``from_md``/
        ``to_md``/``count``.
    """
    return {
        "order_id": int(order.id),
        "customer_name": _chip_customer_name(order),
        "from_md": alerts[0]["from_md"],
        "to_md": alerts[-1]["to_md"],
        "count": len(alerts),
    }


def build_shipment_change_banner(
    orders: list[Order], alerts_by_order: dict[int, dict[str, list[dict[str, str]]]]
) -> dict[str, Any]:
    """상단 배너 요약을 만든다 — **추가 쿼리 0**(collect 결과에서만 파생).

    AS 배너 선례(``as_dashboard_display.apply_schedule_link_drift_fields``)와 같은
    ``{count, chips, overflow}`` 계약이라 두 배너가 한 체계로 유지된다. ``count`` 는
    "미확인 변경이 있는 **주문 수**"이지 변경 건수가 아니다(배너 문구 `현재 목록에서 시공일이
    변경된 건 N건`).

    Args:
        orders: 현재 페이지 주문 리스트(칩 순서 = 목록 순서).
        alerts_by_order: :func:`collect_shipment_change_alerts` 반환값.

    Returns:
        ``{"count": 대상 주문 수, "chips": 상한 5까지의 칩, "overflow": 칩으로 못 낸 나머지}``.
    """
    chips: list[dict[str, Any]] = []
    for order in orders:
        order_id = getattr(order, "id", None)
        if order_id is None:
            continue
        alerts = (alerts_by_order.get(order_id) or {}).get("alerts") or []
        if alerts:
            chips.append(_banner_chip(order, alerts))
    return {
        "count": len(chips),
        "chips": chips[:BANNER_CHIP_LIMIT],
        "overflow": max(len(chips) - BANNER_CHIP_LIMIT, 0),
    }
