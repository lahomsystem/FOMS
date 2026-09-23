"""STATE-CONTROLS-04 도면 전달 계약 테스트 공용 헬퍼.

본문은 test_measurement_drawing_transfer_cta.py(T1~T7) 와
test_measurement_drawing_transfer_button.py(T8~T12) 로 나뉜다 —
파일 크기 래칫(500줄)이 한 파일에 다 담는 것을 막는다.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import event
from sqlalchemy.orm.attributes import flag_modified
from werkzeug.security import generate_password_hash

from db import db_session, engine
from foms.services.orders.state_axes import read_main_stage
from models import Order, User

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "templates"
STATIC = ROOT / "static"
SELF_TEMPLATE = TEMPLATES / "measurement/self_measurement_dashboard.html"
REGIONAL_TEMPLATE = TEMPLATES / "measurement/regional_dashboard.html"
TRANSFER_JS = STATIC / "js/measurement/drawing-transfer-btn.js"
CTA_SERVICE = ROOT / "foms/services/measurement/drawing_transfer_cta.py"
ASSET_PIN = "?v=20260923a"

# --------------------------------------------------------------------------- #
# 공용 헬퍼
# --------------------------------------------------------------------------- #
def _make_user(*, role: str, team: str, username: str) -> User:
    """대시보드/라우트 테스트용 사용자 1명."""
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team=team,
        name=username,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user: User) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _measure_assignee_quest(stage: str = "MEASURE") -> dict:
    """MEASURE 정본 quest(담당자 1인 승인 = 전이가 실제로 일어나는 모드)."""
    return {
        "stage": stage,
        "title": "실측 quest",
        "status": "OPEN",
        "owner_team": "SALES",
        "required_approvals": ["CS", "SALES"],
        "team_approvals": {},
        "approval_mode": "assignee",
        "assignee_approval": {
            "approved": False,
            "approved_by": None,
            "approved_by_name": None,
            "approved_at": None,
        },
    }


def _legacy_team_quest(stage: str = "MEASURE") -> dict:
    """approval_mode 키가 없는 옛 quest — 라우트 기본값이 'team' 이다."""
    return {"stage": stage, "required_approvals": ["CS", "SALES"]}


def _create_order(
    *,
    stage: str | None = "MEASURE",
    quests: list[dict] | None = None,
    status: str = "MEASURE",
    **overrides,
) -> Order:
    """stage 는 structured_data.workflow.stage 로만 심는다(order.status 는 레거시 축)."""
    workflow = {"workflow": {"stage": stage}} if stage else {}
    sd = dict(workflow)
    if quests is not None:
        sd["quests"] = quests
    payload = {
        "received_date": "2026-09-14",
        "customer_name": "도면전달 테스터",
        "phone": "010-4444-5555",
        "address": "부산 해운대구 1",
        "product": "붙박이장",
        "status": status,
        "is_erp_order": True,
        "erp_stage_code": stage or "",
        "structured_data": sd,
    }
    payload.update(overrides)
    order = Order(**payload)
    db_session.add(order)
    db_session.commit()
    return order


def _set_stage(order_id: int, stage: str) -> Order:
    """JSONB 수정 규약: deepcopy → 수정 → 재대입 → flag_modified → commit.

    요청 teardown(``close_db``)이 세션을 닫으면 테스트가 들고 있던 Order 는 detached 가
    되어 수정이 DB 에 남지 않는다. 그래서 항상 id 로 다시 붙여서 고친다.
    """
    order = db_session.query(Order).filter(Order.id == order_id).one()
    sd = copy.deepcopy(order.structured_data or {})
    sd.setdefault("workflow", {})["stage"] = stage
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()
    return order


def _ctas(orders, user) -> dict:
    from foms.services.measurement.drawing_transfer_cta import build_drawing_transfer_ctas

    return build_drawing_transfer_ctas(db_session, orders, user)


def _cta(order: Order, user) -> dict:
    return _ctas([order], user)[order.id]


CTA_KEYS = {"visible", "enabled", "label", "confirm", "blocked_reason"}
