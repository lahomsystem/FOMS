"""2a-2 C21 도면 게이트 — 전이 엔진 방어선(라우트 게이트를 우회해도 잠금 아래에서 다시 본다).

``order_transition_service.transition_order`` 는 CUSTOMER_CONFIRM·PRODUCTION_START 를 행 잠금 아래
``confirm_exit_block`` 으로 다시 보고, 막히면 ``DrawingGateBlockedError``(409 DRAWING_STATUS)를 던진다.
라우트가 관리자 뚫기(DRAWING_STATUS)를 실제로 했을 때만 ``drawing_gate_waived=True`` 를 넘긴다.
이 방어선은 별도 커밋이라 따로 되돌릴 수 있다(설계서 §4.2 위험·되돌리기).
"""
from __future__ import annotations

import pytest

from db import db_session
from foms.services.orders.order_transition_service import DrawingGateBlockedError
from foms.services.orders.quest_transition_service import advance_stage_on_quest_completion
from tests.support.confirm_seed import confirmed_drawing_sd, reload_order, seed_erp_order, seed_user
from tests.support.quest_seed import confirm_quest_completed


def _pair(tag: str):
    return seed_user(f"ge_s_{tag}", team="SALES"), seed_user(f"ge_d_{tag}", team="DRAWING")


def _engine_call(order_id: int, actor_id: int, **kw):
    return advance_stage_on_quest_completion(
        db_session, order_id=order_id, actor_user_id=actor_id,
        scope_hash="0" * 64, request_hash="1" * 64, reason="방어선 확인", **kw,
    )


def test_engine_defense_blocks_customer_confirm_without_confirmed_drawing(app):
    sales, drafter = _pair("eng")
    oid = seed_erp_order("CONFIRM", sales=sales, drafter=drafter, drawing_status="RETURNED",
                         quests=[confirm_quest_completed()])

    with pytest.raises(DrawingGateBlockedError) as exc:
        _engine_call(oid, sales.id)
    db_session.rollback()

    assert exc.value.error_code == "DRAWING_STATUS" and exc.value.status_code == 409
    assert reload_order(oid).erp_stage_code == "CONFIRM"


def test_engine_defense_waived_only_when_route_punched(app):
    sales, drafter = _pair("engw")
    oid = seed_erp_order("CONFIRM", sales=sales, drafter=drafter, drawing_status="RETURNED",
                         quests=[confirm_quest_completed()])

    result = _engine_call(oid, sales.id, drawing_gate_waived=True)
    db_session.commit()

    assert result is not None and not result.replayed
    assert reload_order(oid).erp_stage_code == "PRODUCTION"


def test_engine_defense_passes_confirmed_drawing(app):
    sales, drafter = _pair("engok")
    oid = seed_erp_order("CONFIRM", sales=sales, drafter=drafter, quests=[confirm_quest_completed()],
                         **confirmed_drawing_sd())

    assert _engine_call(oid, sales.id) is not None
    db_session.commit()
    assert reload_order(oid).erp_stage_code == "PRODUCTION"
