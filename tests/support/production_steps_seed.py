"""테스트용 공정 칸 시드 — [제작 완료]는 검수까지(공정 4칸) 끝나야 한다(사용자 결정 2026-11-21).

서버가 ``POST /api/orders/<id>/production/complete`` 와 일반 단계 쓰기(생산 → 시공)를
:func:`foms.services.production.steps.production_complete_ready` 로 막는다 — 공정 칸을 쓴 주문만(한 칸이라도 켬,
11-21 사용자 "공정 칸을 쓴 주문만 막기"). 완료를 부르는 시험은 이 헬퍼로 "재단 · 엣지 · 조립 · 검수 모두 끝" 을,
막힘 시험은 ``upto`` 로 "일부만 켬" 을 얹는다. 모양은 실제 공정 API
(:func:`foms.services.production.steps.set_production_step`)가 남기는 칸과 같다.
"""
from __future__ import annotations

import copy
from typing import Any

from foms.services.production.steps import PRODUCTION_STEP_DEFS

_DONE_AT = "2026-11-21T01:00:00+00:00"


def inspected_steps(*, by_name: str = "시험 작업자", upto: str | None = None) -> list[dict[str, Any]]:
    """공정 4칸 — 기본은 모두 끝(검수까지). ``upto`` 를 주면 그 칸까지만 켠다(예: ``'cut'`` = 재단만)."""
    steps: list[dict[str, Any]] = []
    on = True
    for key, label in PRODUCTION_STEP_DEFS:
        steps.append({"key": key, "label": label, "done": on,
                      "at": _DONE_AT if on else None, "by_name": by_name if on else None})
        if upto is not None and key == upto:
            on = False
    return steps


def with_inspected_steps(sd: dict[str, Any] | None, **kwargs: Any) -> dict[str, Any]:
    """``sd`` 사본에 ``production.steps`` 를 얹어 돌려준다(``production`` 의 다른 키 — 보류 · 재제작 — 는 그대로)."""
    out = copy.deepcopy(sd) if isinstance(sd, dict) else {}
    production = out.get("production") if isinstance(out.get("production"), dict) else {}
    production["steps"] = inspected_steps(**kwargs)
    out["production"] = production
    return out


def mark_order_inspected(order_id: int, **kwargs: Any) -> None:
    """이미 만든 주문의 공정 칸을 모두 켠다(deepcopy → 재대입 → flag_modified → commit)."""
    from sqlalchemy.orm.attributes import flag_modified

    from db import db_session
    from models import Order

    order = db_session.get(Order, order_id)
    order.structured_data = with_inspected_steps(order.structured_data, **kwargs)
    flag_modified(order, "structured_data")
    db_session.commit()
