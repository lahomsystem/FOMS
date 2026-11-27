"""공정 판정 묶음 — 옛 공정 읽기 GET(``GET /api/orders/<id>/production/steps``, 2026-11-27 지움)이 싣던 판정 값을 같은 서버 함수로 바로 센다.

지운 것은 라우트(포장)뿐이다. 값을 내는 함수(:func:`complete_ready` · :func:`step_api_extras` · :func:`factory_step_fields` ·
:func:`confirm_extras` · :func:`steps_lock` · :func:`steps_factory_note`)는 작업 시트 · 공정 POST 응답 · PC 도면 창이 그대로 쓴다.
그 GET 으로 이 함수들의 답을 지키던 시험이 같은 함수를 바로 부르게 한다(단언은 그대로). ``locked`` · ``locked_note`` 는 작업 시트
(:mod:`foms.services.production_sheet_view`)와 같은 조합이다.
"""
from __future__ import annotations

from typing import Any

from db import db_session
from foms.services.orders.drawing_fix import confirm_extras
from foms.services.production.factory_home import factory_step_fields
from foms.services.production.factory_scope import steps_factory_note
from foms.services.production.part_access import steps_lock
from foms.services.production.part_marks_query import order_marks
from foms.services.production.part_progress import complete_ready, step_api_extras
from models import Order, User


def steps_read(client: Any, order_id: int) -> dict[str, Any]:
    """그 시험 손님(``client`` 세션의 사용자)이 보는 공정 판정 — ``complete_ready`` · ``locked`` · ``locked_note`` · ``sheets`` ·
    ``parts`` · ``per_sheet`` · ``factories``(섞인 주문만) · ``fix``(막힌 도면이 있을 때만)."""
    with client.session_transaction() as sess:
        user_id = sess.get("user_id")
    db_session.expire_all()
    user = db_session.get(User, user_id) if user_id else None
    order = db_session.get(Order, order_id)
    sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    marks = order_marks(db_session, order_id)
    lock = steps_lock(user)
    note = lock.message if lock else steps_factory_note(user, sd)
    return {
        "complete_ready": complete_ready(sd, marks),
        "locked": note is not None,
        "locked_note": note,
        **step_api_extras(sd, marks),
        **factory_step_fields(sd, marks),
        **confirm_extras(sd),
    }
