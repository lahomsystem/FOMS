"""제작 시작(생산 회차 열기) 곁일 — [제작 시작] 단추와 첫 카드 맡기가 같이 쓴다(설계서 2026-11-23 §4-8 B6).

제작대기 = 생산 단계이면서 지금 회차(``ProductionRun.is_current``)가 없는 주문. 여는 길이 둘이다.

* [제작 시작] — ``POST /api/orders/<id>/production/start``(``foms/api/production/orders.py``)가 정책
  ``STATE_PRODUCTION_START`` 의 ``execute_order_mutation`` 안에서 이 모듈을 부른다(보류 해제 · 감사는 그 라우트 몫).
* **첫 카드 맡기** — 도면 카드 쓰기(take · basic · takeover · 일괄 기본) 뒤 표시가 NONE 이 아닌데 회차가 없으면 같은 tx ·
  같은 정책으로 연다(``foms/services/production/part_mark_write.py``). 단계 기록 "제작 시작 (도면 카드 첫 맡기)" ·
  이벤트 ``PRODUCTION_STARTED`` ``via:'part_marks'`` · 감사 한 줄. 맡기를 취소해도 회차는 그대로다(되돌리기는 [제작 취소]).
  일괄 기본은 주문이 여럿이라 회차 · 이벤트 · 감사 줄을 ``*_values`` 로 모아 표마다 INSERT 한 번(주문 수와 무관)으로 쓴다.

``structured_data`` 는 호출자가 deepcopy 한 사본을 넘기고, 재대입 · ``flag_modified`` 는 여기서 한다(AGENTS.md 규약).
"""

from __future__ import annotations

import copy
import uuid
from typing import Any, Optional

from sqlalchemy.orm.attributes import flag_modified

from foms.services.audit_message_display import describe_order_action
from foms.services.datetime_kst import now_utc_naive
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.orders.audit_order_context import order_audit_context
from models import OrderEvent, ProductionRun

#: 정책 id — [제작 시작] 단추와 같다(``execute_order_mutation`` 영수증 · 매니페스트 ``STATE_PRODUCTION_START``).
PRODUCTION_START_POLICY_ID = "STATE_PRODUCTION_START"
STARTED_EVENT = "PRODUCTION_STARTED"
#: 단계 기록 글 — [제작 시작] 단추 / 첫 카드 맡기.
START_NOTE = "제작 시작"
CARD_START_NOTE = "제작 시작 (도면 카드 첫 맡기)"
#: 이벤트 · 감사 ``via`` — 카드가 연 회차.
VIA_PART_MARKS = "part_marks"


def append_stage_history(sd: dict[str, Any], stage: str, note: str, user: Any) -> None:
    """``workflow.history`` 에 단계 기록 한 줄을 더하고 ``stage_updated_by`` 를 고친다(제자리).

    Args:
        sd: 호출자가 deepcopy 한 structured_data.
        stage: 기록할 단계 코드.
        note: 기록 글.
        user: 누른 사람(없으면 "Unknown").
    """
    wf = sd.setdefault("workflow", {})
    wf["stage_updated_by"] = user.name if user else "Unknown"
    updated_at = wf.get("stage_updated_at") or now_utc_naive().isoformat()
    history = wf.get("history") or []
    history.append({"stage": stage, "updated_at": updated_at,
                    "updated_by": wf["stage_updated_by"], "note": note})
    wf["history"] = history


def new_run_values(order_id: int, sd: dict[str, Any]) -> dict[str, Any]:
    """새 IN_PROGRESS 회차 한 줄의 칸 값(공정 칸 · 불량은 복제 스냅샷).

    Args:
        order_id: 주문 id.
        sd: 복제할 structured_data(읽기만).
    """
    production = sd.get("production") if isinstance(sd.get("production"), dict) else {}
    steps = production.get("steps") if isinstance(production.get("steps"), list) else []
    defects = production.get("defects") if isinstance(production.get("defects"), list) else []
    return {"id": str(uuid.uuid4()), "order_id": int(order_id), "status": "IN_PROGRESS", "started_at": now_utc_naive(),
            "steps": copy.deepcopy(steps), "defects": copy.deepcopy(defects), "is_current": True}


def mint_current_production_run(db: Any, order_id: int, sd: dict[str, Any]) -> None:
    """지금 IN_PROGRESS 회차가 없으면 연다(있으면 건너뜀 — 멱등). 공정 칸 · 불량은 회차에 복제한다.

    Args:
        db: 세션(같은 tx).
        order_id: 주문 id.
        sd: 복제할 structured_data(읽기만).
    """
    exists = (
        db.query(ProductionRun.id)
        .filter(ProductionRun.order_id == order_id, ProductionRun.is_current.is_(True))
        .first()
    )
    if exists is not None:
        return
    db.add(ProductionRun(**new_run_values(order_id, sd)))


def record_start_in_sd(order: Any, sd: dict[str, Any], user: Any, *, note: str) -> None:
    """제작 시작의 주문 쪽 — 단계 기록 · 재대입 · ``flag_modified`` · 납작 칸 맞추기(단계는 생산 그대로, 회차는 따로).

    Args:
        order: 잠근 주문.
        sd: 호출자가 deepcopy · 고친 structured_data(이 함수가 주문에 다시 넣는다).
        user: 누른 사람.
        note: 단계 기록 글(:data:`START_NOTE` · :data:`CARD_START_NOTE`).
    """
    append_stage_history(sd, "PRODUCTION", note, user)
    order.structured_data = sd
    flag_modified(order, "structured_data")
    sync_erp_flat_columns(order, sd)


def start_run_in_sd(db: Any, order: Any, sd: dict[str, Any], user: Any, *, note: str) -> None:
    """제작 시작 곁일 한 주문 — :func:`record_start_in_sd` + 회차 열기(:func:`mint_current_production_run`, 같은 tx)."""
    record_start_in_sd(order, sd, user, note=note)
    mint_current_production_run(db, order.id, sd)


def started_event_values(order_id: int, user_id: Optional[int], *, via: Optional[str] = None) -> dict[str, Any]:
    """``PRODUCTION_STARTED`` 이벤트 한 줄의 칸 값(단계 PRODUCTION → PRODUCTION, 회차 열림). ``via`` 는 카드 길만.

    칸 모양은 공정 칸 이벤트 줄(``part_steps_sync.step_event_rows``)과 같아 한 INSERT 에 같이 실린다.
    """
    payload: dict[str, Any] = {
        "domain": "PRODUCTION_DOMAIN", "action": STARTED_EVENT,
        "target": "production_run", "from": "PRODUCTION", "to": "PRODUCTION",
        "run_started": True, "change_method": "API",
    }
    if via:
        payload["via"] = via
    return {"order_id": int(order_id), "event_type": STARTED_EVENT, "payload": payload, "created_by_user_id": user_id,
            "created_at": now_utc_naive()}


def started_event(order_id: int, user_id: Optional[int], *, via: Optional[str] = None) -> OrderEvent:
    """``PRODUCTION_STARTED`` 이벤트 ORM 한 줄([제작 시작] 단추 길)."""
    return OrderEvent(**started_event_values(order_id, user_id, via=via))


def card_start_audit_values(order: Any, user: Any) -> dict[str, Any]:
    """첫 카드가 연 제작 시작의 감사 한 줄 칸 값([제작 시작] 단추의 감사와 같은 action 이라 같이 찾힌다)."""
    context = order_audit_context(order)
    message = describe_order_action(order_id=order.id, action=STARTED_EVENT, note="도면 카드 첫 맡기", **context)
    return {"user_id": getattr(user, "id", None), "action": STARTED_EVENT, "target_type": "order",
            "target_id": int(order.id), "message": message, "detail": {"via": VIA_PART_MARKS, **context}}
