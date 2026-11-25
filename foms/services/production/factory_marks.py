"""공장 완료 표지 지우기 — 아래층 한 곳(설계서 2026-11-23 §4-14 '되돌리기', 3단계 ⑥).

``structured_data.production.factory_done`` 의 표지를 지우는 함수만 둔다. 완료 취소 · 재제작 · 제작 취소(생산 API —
:mod:`foms.services.production.complete_order` 가 다시 내보냄)와 관리자 강제 단계 되돌리기(:mod:`foms.services.orders.stage_override`)가
같이 쓴다. 단계 모듈은 import 그래프 아래쪽이라(``drawing_factory`` 가 단계 모듈을 읽는다) 이 모듈은 도면 · 생산 규칙 모듈을 읽지 않는다 —
칸 이름은 :data:`foms.services.orders.drawing_factory.FACTORY_DONE_KEY` 와 같은 글자로 둔다(시험이 둘이 같은지 본다).
'살아 있음' 판정은 여기 없다 — :func:`foms.services.orders.drawing_factory.factory_done_entry` 한 곳.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from foms.services.production.factory_constants import FACTORIES

#: ``production`` 안 칸 이름(``drawing_factory.FACTORY_DONE_KEY`` 와 같은 값).
FACTORY_DONE_KEY = "factory_done"


def done_table(sd: Any) -> dict[str, Any]:
    """표지 표의 사본(없거나 모양이 다르면 빈 사전)."""
    production = sd.get("production") if isinstance(sd, dict) and isinstance(sd.get("production"), dict) else {}
    table = production.get(FACTORY_DONE_KEY)
    return dict(table) if isinstance(table, dict) else {}


def clear_factory_marks(sd: dict[str, Any], factories: Optional[Iterable[int]] = None) -> list[int]:
    """표지를 지운다(제자리 — ``production`` 은 사본으로 바꿔 끼운다) — ``factories`` 가 None 이면 모두, 아니면 그 공장만.

    Returns:
        지운 공장 번호들(표지가 없던 공장은 빠진다).
    """
    table = done_table(sd)
    if not table:
        return []
    keys = [str(f) for f in (FACTORIES if factories is None else factories)]
    removed = [int(k) for k in keys if table.pop(k, None) is not None]
    if removed:
        production = dict(sd["production"])  # 셸 복사 — 부르는 쪽이 얕게 복사한 sd 여도 원래 값을 건드리지 않는다
        if table:
            production[FACTORY_DONE_KEY] = table
        else:
            production.pop(FACTORY_DONE_KEY, None)
        sd["production"] = production
    return removed


__all__ = ["FACTORY_DONE_KEY", "clear_factory_marks", "done_table"]
