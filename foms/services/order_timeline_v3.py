"""주문 360° 8단계 타임라인 데이터 빌더 (FOMS Field OS v3 · 읽기 전용).

structured_data['workflow']와 OrderEvent 스트림(STAGE_CHANGED)을 병합해
표준 8단계(RECEIVED→MEASURE→DRAWING→CONFIRM→PRODUCTION→CONSTRUCTION→CS→
COMPLETED)의 도달 여부·일시·담당·산출물 요약을 만든다.

이 모듈은 순수 파생/병합 함수만 담당한다. DB 조회는 호출부(엔드포인트)가
단일 OrderEvent 쿼리 + 배치 User 쿼리로 이미 끝낸 결과를 인자로 받는다
(N+1 없음). 쓰기·상태 변경은 하지 않는다(v3.0 표시 전용).
"""

from __future__ import annotations

from typing import Any

from foms.services.datetime_kst import format_datetime_kst

# (표준 status code, 한글 라벨, CSS 스테이지 토큰) — 순서가 진행 순서다.
STAGE_SEQUENCE: list[tuple[str, str, str]] = [
    ("RECEIVED", "접수", "received"),
    ("MEASURE", "실측", "measure"),
    ("DRAWING", "도면", "drawing"),
    ("CONFIRM", "고객컨펌", "confirm"),
    ("PRODUCTION", "생산", "production"),
    ("CONSTRUCTION", "시공", "construction"),
    ("CS", "CS / AS", "cs"),
    ("COMPLETED", "완료", "completed"),
]

_STAGE_INDEX: dict[str, int] = {code: i for i, (code, _, _) in enumerate(STAGE_SEQUENCE)}
_STAGE_LABEL: dict[str, str] = {code: label for code, label, _ in STAGE_SEQUENCE}

# 실제 status 값(레거시·서브상태 포함)을 8단계 표준 코드로 접는다.
STATUS_TO_STAGE: dict[str, str] = {
    "RECEIVED": "RECEIVED",
    "ON_HOLD": "RECEIVED",
    "RECHECK": "RECEIVED",
    "MEASURE": "MEASURE",
    "MEASURED": "MEASURE",
    "REGIONAL_MEASURED": "MEASURE",
    "DRAWING": "DRAWING",
    "CONFIRM": "CONFIRM",
    "PRODUCTION": "PRODUCTION",
    "CONSTRUCTION": "CONSTRUCTION",
    "SCHEDULED": "CONSTRUCTION",
    "SHIPPED_PENDING": "CONSTRUCTION",
    "CS": "CS",
    "AS": "CS",
    "AS_RECEIVED": "CS",
    "AS_COMPLETED": "CS",
    "COMPLETED": "COMPLETED",
}


def _canonical_stage(status: Any) -> str:
    """임의 status 문자열을 표준 8단계 코드로 매핑(미상은 RECEIVED)."""
    return STATUS_TO_STAGE.get((status or "").strip().upper(), "RECEIVED")


def _sd(order: Any) -> dict[str, Any]:
    """order.structured_data를 dict로 안전 반환."""
    data = getattr(order, "structured_data", None)
    return data if isinstance(data, dict) else {}


def _current_stage_code(order: Any) -> str:
    """workflow.stage(우선) 또는 order.status로부터 현재 표준 단계 산출."""
    sd = _sd(order)
    wf = sd.get("workflow") if isinstance(sd.get("workflow"), dict) else {}
    status = wf.get("stage") or getattr(order, "status", None)
    return _canonical_stage(status)


def _stage_reach_events(events: Any) -> dict[str, Any]:
    """STAGE_CHANGED payload['to']를 표준 단계로 접어 최초 도달 이벤트를 기록.

    Args:
        events: created_at 오름차순 정렬된 OrderEvent 목록.

    Returns:
        {표준 단계 코드: 최초 도달 OrderEvent} 매핑.
    """
    reached: dict[str, Any] = {}
    for ev in events:
        if getattr(ev, "event_type", None) != "STAGE_CHANGED":
            continue
        payload = ev.payload if isinstance(getattr(ev, "payload", None), dict) else {}
        to_stage = _canonical_stage(payload.get("to"))
        reached.setdefault(to_stage, ev)
    return reached


def _stage_notes(sd: dict[str, Any]) -> dict[str, str]:
    """structured_data에서 단계별 산출물 요약(있는 데이터만)."""
    schedule = sd.get("schedule") if isinstance(sd.get("schedule"), dict) else {}
    notes: dict[str, str] = {}
    meas = (schedule.get("measurement") or {}).get("date") if isinstance(schedule.get("measurement"), dict) else None
    if meas:
        notes["MEASURE"] = f"실측일 {meas}"
    cons = (schedule.get("construction") or {}).get("date") if isinstance(schedule.get("construction"), dict) else None
    if cons:
        notes["CONSTRUCTION"] = f"시공일 {cons}"
    history = sd.get("drawing_transfer_history")
    if isinstance(history, list) and history:
        notes["DRAWING"] = f"도면 전달 {len(history)}회"
    return notes


def _customer_name(sd: dict[str, Any], order: Any) -> str:
    """타임라인 헤더용 고객명(파생 우선, 없으면 flat/폴백)."""
    parties = sd.get("parties") if isinstance(sd.get("parties"), dict) else {}
    customer = parties.get("customer") if isinstance(parties.get("customer"), dict) else {}
    name = (customer.get("name") or "").strip()
    if name:
        return name
    return (getattr(order, "customer_name", None) or f"주문 #{order.id}").strip()


def build_order_timeline(order: Any, events: Any, users_map: dict[int, str]) -> dict[str, Any]:
    """주문 1건의 8단계 타임라인 뷰 데이터를 조립한다.

    Args:
        order: Order ORM 인스턴스.
        events: created_at 오름차순 OrderEvent 목록(단일 쿼리 결과).
        users_map: {user_id: 이름} — 이벤트 생성자 배치 조회 결과.

    Returns:
        템플릿(persona_order360.html)이 소비하는 dict:
        order_id, customer_name, current_code, current_label, stages[].
    """
    sd = _sd(order)
    current_code = _current_stage_code(order)
    current_idx = _STAGE_INDEX.get(current_code, 0)
    reached = _stage_reach_events(events)
    notes = _stage_notes(sd)
    schedule = sd.get("schedule") if isinstance(sd.get("schedule"), dict) else {}
    received = (schedule.get("received") or {}).get("date") if isinstance(schedule.get("received"), dict) else None
    received = received or getattr(order, "received_date", None)

    stages: list[dict[str, Any]] = []
    for idx, (code, label, sc) in enumerate(STAGE_SEQUENCE):
        if idx < current_idx:
            state = "done"
        elif idx == current_idx:
            state = "current"
        else:
            state = "pending"
        ev = reached.get(code)
        when = format_datetime_kst(ev.created_at) if ev is not None and ev.created_at else None
        who = users_map.get(ev.created_by_user_id) if ev is not None else None
        if code == "RECEIVED" and not when and received:
            when = str(received)
        stages.append(
            {
                "code": code,
                "label": label,
                "sc": sc,
                "state": state,
                "when": when,
                "who": who,
                "note": notes.get(code),
            }
        )

    return {
        "order_id": order.id,
        "customer_name": _customer_name(sd, order),
        "current_code": current_code,
        "current_label": _STAGE_LABEL.get(current_code, ""),
        "stages": stages,
    }


def load_order_timeline(db: Any, order: Any) -> dict[str, Any]:
    """주문 1건의 OrderEvent 스트림+생성자 이름을 배치 조회해 타임라인을 조립한다.

    fragment 엔드포인트(order_timeline_fragment)와 v2 모바일 상세 페이지가
    공유하는 유일한 로딩 경로다. OrderEvent는 단일 쿼리(오름차순), 생성자
    이름은 in_ 배치 조회로 해소한다(N+1 없음).

    Args:
        db: SQLAlchemy 세션.
        order: Order ORM 인스턴스.

    Returns:
        build_order_timeline 결과 dict (order_id, customer_name,
        current_code, current_label, stages[]).
    """
    from models import OrderEvent, User  # 지역 import — 본 모듈 파생 함수의 DB 의존 격리

    events = (
        db.query(OrderEvent)
        .filter(OrderEvent.order_id == order.id)
        .order_by(OrderEvent.created_at.asc())
        .all()
    )
    creator_ids = {ev.created_by_user_id for ev in events if ev.created_by_user_id}
    users_map: dict[int, str] = {}
    if creator_ids:
        users = db.query(User).filter(User.id.in_(creator_ids)).all()  # perf-ok: creator ids from single order event set
        users_map = {u.id: u.name for u in users}
    return build_order_timeline(order, events, users_map)
