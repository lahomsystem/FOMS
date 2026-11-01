"""협력사 주문이 도면을 요청할 수 있는가 — '실측 예정'과 '도면 요청'을 가르는 한 곳(사용자 결정 2026-11-01).

협력사는 실측 전에도 고객 · 시공일 자리를 잡으려고 주문을 미리 올린다. 그런 주문이 도면 단계로 들어가 도면팀
큐 · 영발방에 빈 채로 나가지 않게, 조건이 맞을 때만 도면 단계로 보낸다:

* 실측일이 있고 오늘이거나 그 전이다(``partner_intake.measured_on``).
* 제품마다 가로 치수(``spec_rows[].spec_width``)가 1칸 이상 있다.

사진 · 초안 도면은 조건이 아니다(사진이 필요 없는 경우도 있다 — 사용자). 속성 '상담'은 그대로 받는다.
등록(``orders.create_partner_order``)과 도면 요청(``drawing_request``)이 같은 판정을 쓴다.
스펙: docs/specs/2026-11-01-partner-measure-pending_SPEC.md
"""
from __future__ import annotations

from typing import Any

from foms.services.datetime_kst import get_today_kst

#: 도면 요청 전 단계 — 영발 PUSH 를 열지 않는다.
PRE_DRAWING_STAGES = frozenset({"RECEIVED", "MEASURE"})


def _today() -> str:
    return get_today_kst().strftime("%Y-%m-%d")


def _has_width(item: Any) -> bool:
    rows = item.get("spec_rows") if isinstance(item, dict) else None
    return any(isinstance(r, dict) and str(r.get("spec_width") or "").strip() for r in (rows or []))


def drawing_request_missing(measured_on: Any, items: Any, today: str | None = None) -> list[str]:
    """도면을 요청하려면 더 넣어야 할 것(화면에 그대로 보일 문장). 다 있으면 빈 목록.

    Args:
        measured_on: 협력사 실측일('YYYY-MM-DD' 또는 빈 값).
        items: 품목 목록(``product_name`` · ``spec_rows``).
        today: 시험용 오늘(기본 한국 날짜).
    """
    missing: list[str] = []
    day = str(measured_on or "").strip()[:10]
    if not day:
        missing.append("실측일을 넣어 주세요.")
    elif day > (today or _today()):
        missing.append(f"실측일({day})이 아직 오지 않았습니다.")
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict) and not _has_width(item):
            missing.append(f"{item.get('product_name') or '제품'}의 가로 치수를 넣어 주세요.")
    return missing


def order_drawing_missing(order: Any) -> list[str]:
    """저장된 주문으로 :func:`drawing_request_missing` — 실측일은 협력사 원문 사본, 품목은 지금 품목."""
    sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    intake = sd.get("partner_intake") if isinstance(sd.get("partner_intake"), dict) else {}
    return drawing_request_missing(intake.get("measured_on"), sd.get("items"))


def drawing_request_state(order: Any) -> dict[str, Any]:
    """협력사 주문 화면 "실측 끝 · 도면 요청" 단추 — {open: 실측 예정인가, missing: 빠진 것}."""
    stage = (getattr(order, "erp_stage_code", None) or "").upper()
    if stage not in PRE_DRAWING_STAGES:
        return {"open": False, "missing": []}
    return {"open": True, "missing": order_drawing_missing(order)}
