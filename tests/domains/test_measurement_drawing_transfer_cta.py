"""STATE-CONTROLS-04 — 도면 전달 CTA 판정 계약(T1~T7).

권한 술어 추출·CTA visible/enabled·role 축·쿼리 수. 마크업·라우트·JS 계약은
tests/domains/test_measurement_drawing_transfer_button.py 에 있다.
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
CTA_KEYS = {"visible", "enabled", "label", "confirm", "blocked_reason"}

from tests.domains.drawing_transfer_helpers import (
    _make_user,
    _login,
    _measure_assignee_quest,
    _legacy_team_quest,
    _create_order,
    _ctas,
    _cta,
)

# --------------------------------------------------------------------------- #
# T1 심볼 위치-고정 — 권한 술어를 옮겨도 옛 import 경로가 살아 있다.
# --------------------------------------------------------------------------- #
def test_quest_module_reexports_authz_predicates() -> None:
    """tests/domains/test_measure_approval_teams.py 가 쓰는 import 경로를 못박는다."""
    import foms.api.quest as q
    import foms.services.orders.quest_approve_authz as authz

    assert q._authorize_quest_approve is authz.authorize_quest_approve
    assert q._required_teams_for_stage is authz.required_teams_for_stage
    assert q._find_stage_quest is authz.find_stage_quest


def test_authz_module_exposes_role_tuple() -> None:
    """QUEST_APPROVE_ROLES 는 라우트 데코레이터의 문자열 집합 그대로다."""
    from foms.services.orders.quest_approve_authz import QUEST_APPROVE_ROLES

    assert QUEST_APPROVE_ROLES == ("ADMIN", "MANAGER", "STAFF")


# --------------------------------------------------------------------------- #
# T2 추출 순수성 — 권한 진리표(DB 없이).
# --------------------------------------------------------------------------- #
_MEASURE_QUEST = {
    "stage": "MEASURE",
    "required_approvals": ["CS", "SALES"],
    "approval_mode": "assignee",
}


@pytest.mark.parametrize(
    "role,team,expected",
    [
        ("ADMIN", "DELIVERY", True),   # role bypass
        ("STAFF", "SALES", True),      # 방문 실측 주관
        ("STAFF", "CS", True),         # 자가 실측 주관
        ("STAFF", "DELIVERY", False),
        ("STAFF", None, False),
    ],
)
def test_authorize_quest_approve_truth_table(role, team, expected) -> None:
    from foms.services.orders.quest_approve_authz import authorize_quest_approve

    user = SimpleNamespace(id=1, role=role, team=team)
    order = SimpleNamespace(id=1)

    allowed, status, message = authorize_quest_approve(
        None, user, order, "MEASURE", _MEASURE_QUEST
    )

    assert allowed is expected
    if expected:
        assert (status, message) == (200, "")
    else:
        assert status == 403
        assert message.strip() != "", "거부에는 사람이 읽을 사유가 있어야 한다"


def test_authorize_quest_approve_override_axis() -> None:
    """override 는 관리자 전용 + 사유 필수 — 추출 뒤에도 그대로다."""
    from foms.services.orders.quest_approve_authz import authorize_quest_approve

    order = SimpleNamespace(id=1)

    staff = SimpleNamespace(id=1, role="STAFF", team="SALES")
    allowed, status, _msg = authorize_quest_approve(
        None, staff, order, "MEASURE", _MEASURE_QUEST,
        emergency_override=True, override_reason="사유",
    )
    assert (allowed, status) == (False, 403)

    manager = SimpleNamespace(id=2, role="MANAGER", team="DELIVERY")
    allowed, status, _msg = authorize_quest_approve(
        None, manager, order, "MEASURE", _MEASURE_QUEST,
        emergency_override=True, override_reason="",
    )
    assert (allowed, status) == (False, 422)


def test_authorize_quest_approve_override_kwargs_are_optional() -> None:
    """두 키워드 인자에 기본값이 붙었다(추가적·후방호환)."""
    from foms.services.orders.quest_approve_authz import authorize_quest_approve

    allowed, status, message = authorize_quest_approve(
        None,
        SimpleNamespace(id=1, role="ADMIN", team="DELIVERY"),
        SimpleNamespace(id=1),
        "MEASURE",
        _MEASURE_QUEST,
    )
    assert (allowed, status, message) == (True, 200, "")


def test_required_teams_for_stage_widens_legacy_narrow_quest() -> None:
    """2026-09-13 라홈 사고 축: ["CS"] 로 저장된 quest 를 정책이 넓힌다."""
    from foms.services.orders.quest_approve_authz import required_teams_for_stage

    teams = set(required_teams_for_stage({"required_approvals": ["CS"]}, "MEASURE"))

    assert {"CS", "SALES"} <= teams


def test_find_stage_quest_matches_name_or_code() -> None:
    from foms.services.orders.quest_approve_authz import find_stage_quest

    sd = {"quests": ["문자열은 무시", {"stage": "MEASURE", "title": "실측"}]}

    quest, index = find_stage_quest(sd, "실측", "MEASURE")
    assert index == 1 and quest["title"] == "실측"

    assert find_stage_quest({"quests": []}, "실측", "MEASURE") == (None, -1)
    assert find_stage_quest({}, "도면", "DRAWING") == (None, -1)


# --------------------------------------------------------------------------- #
# T3 visible 게이트 — 양성 1 + 음성 5 (+ 한글 stage 정규화).
# --------------------------------------------------------------------------- #
def test_cta_visible_for_measure_stage(app) -> None:
    from foms.services.measurement.drawing_transfer_cta import DRAWING_TRANSFER_LABEL

    user = _make_user(role="STAFF", team="SALES", username="cta-visible-staff")
    order = _create_order(quests=[_measure_assignee_quest()])

    cta = _cta(order, user)

    assert set(cta) == CTA_KEYS
    assert cta["visible"] is True
    assert cta["label"] == DRAWING_TRANSFER_LABEL == "도면 전달"
    assert cta["confirm"].strip() != ""


@pytest.mark.parametrize(
    "stage",
    [
        None,           # (a) workflow.stage 없음 — 라우트는 400
        "RECEIVED",     # (b)
        "DRAWING",      # (c) 라우트는 409 COMMAND_REQUIRED
        "PRODUCTION",   # (d)
        "COMPLETED",    # (e)
    ],
)
def test_cta_hidden_for_non_measure_stage(app, stage) -> None:
    user = _make_user(role="STAFF", team="SALES", username=f"cta-hidden-{stage}")
    order = _create_order(stage=stage, quests=[_measure_assignee_quest()])

    cta = _cta(order, user)

    assert cta == {
        "visible": False,
        "enabled": False,
        "label": "",
        "confirm": "",
        "blocked_reason": "",
    }


@pytest.mark.parametrize(
    "as_status,legacy_status",
    [
        ("RECEIVED", "AS_RECEIVED"),      # (f) AS 접수 — 상차 예정 알림 버킷이 다시 담는 행
        ("IN_PROGRESS", "AS"),            # (g) AS 진행 중
    ],
)
def test_cta_hidden_while_as_is_open(app, as_status, legacy_status) -> None:
    """AS 전이는 workflow.stage 를 건드리지 않아 stage 가 MEASURE 로 남는다.

    AS 접수/진행 중인 주문에 되돌리기 어려운 도면 전이 버튼을 내밀면 안 된다.
    ``as_lifecycle`` 가 있는 주문과 legacy ``order.status`` 만 있는 주문 둘 다 막힌다.
    """
    user = _make_user(role="STAFF", team="SALES", username=f"cta-as-{as_status}")

    # (1) legacy 축만 있는 주문(as_lifecycle 없음).
    legacy_order = _create_order(quests=[_measure_assignee_quest()], status=legacy_status)
    assert read_main_stage(legacy_order) == "MEASURE"
    assert _cta(legacy_order, user)["visible"] is False, legacy_status

    # (2) as_lifecycle 이 있는 주문.
    lifecycle_order = _create_order(quests=[_measure_assignee_quest()], status="MEASURE")
    sd = copy.deepcopy(lifecycle_order.structured_data or {})
    sd["as_lifecycle"] = {
        "current_cycle_id": "as-1",
        "cycles": [
            {
                "cycle_id": "as-1",
                # canonical 값은 transitions 의 마지막 to 로 읽힌다(state_axes:166-185).
                "transitions": [{"to": as_status}],
            }
        ],
    }
    lifecycle_order.structured_data = sd
    flag_modified(lifecycle_order, "structured_data")
    db_session.commit()

    assert read_main_stage(lifecycle_order) == "MEASURE"
    assert _cta(lifecycle_order, user)["visible"] is False, as_status


def test_cta_visible_after_as_completed(app) -> None:
    """음성 대조군 — AS 가 끝난(COMPLETED) 주문은 다시 보인다(과잉 차단 방지)."""
    user = _make_user(role="STAFF", team="SALES", username="cta-as-completed")
    order = _create_order(quests=[_measure_assignee_quest()], status="AS_COMPLETED")

    assert read_main_stage(order) == "MEASURE"
    assert _cta(order, user)["visible"] is True


def test_cta_visible_for_korean_stage_label(app) -> None:
    """stage 를 한글 '실측' 으로 저장한 주문도 STAGE_NAME_TO_CODE 로 정규화된다."""
    user = _make_user(role="STAFF", team="SALES", username="cta-korean-stage")
    order = _create_order(stage="실측", quests=None, status="MEASURE")

    cta = _cta(order, user)

    assert cta["visible"] is True


# --------------------------------------------------------------------------- #
# T4 enabled == 서버 판정 (핵심). 음성 대조군은 모집단 안에서 고른다.
# --------------------------------------------------------------------------- #
_MATRIX = [
    ("ADMIN", "DELIVERY"),
    ("MANAGER", "SALES"),
    ("STAFF", "CS"),
    ("STAFF", "SALES"),
    ("STAFF", "DELIVERY"),
    ("STAFF", "PRODUCTION"),
]


def test_cta_enabled_matches_server_authorization(client) -> None:
    """CTA 를 CTA 가 부르는 함수가 아니라 **실제 라우트**와 대조한다.

    케이스마다 새 주문을 만들어 ``POST /api/orders/<id>/quest/approve`` 를 진짜로 태우고
    ``cta['enabled'] == (status_code == 200)`` 을 못박는다. 허용이면 stage 가 실제로
    DRAWING 으로 넘어가고, 거부면 403 + stage 가 MEASURE 로 남는다.
    """
    results: dict[tuple[str, str], bool] = {}
    for role, team in _MATRIX:
        user = _make_user(role=role, team=team, username=f"matrix-{role}-{team}")
        order = _create_order(
            quests=[_measure_assignee_quest()],
            status="MEASURE",
            is_self_measurement=True,
            customer_name=f"매트릭스 {role}-{team}",
        )
        order_id = order.id

        cta = _cta(order, user)
        assert cta["visible"] is True, (role, team)
        if not cta["enabled"]:
            assert cta["blocked_reason"].strip() != "", (role, team)

        _login(client, user)
        resp = client.post(f"/api/orders/{order_id}/quest/approve", json={})
        body = resp.get_data(as_text=True)

        assert cta["enabled"] == (resp.status_code == 200), (
            role, team, resp.status_code, body,
        )

        db_session.expire_all()
        after = db_session.query(Order).filter(Order.id == order_id).one()
        if cta["enabled"]:
            assert read_main_stage(after) == "DRAWING", (role, team, body)
        else:
            assert resp.status_code == 403, (role, team, resp.status_code, body)
            assert read_main_stage(after) == "MEASURE", (role, team)

        results[(role, team)] = cta["enabled"]

    # 음성 대조군이 모집단 안에 있어야 이 테스트가 무언가를 증명한다.
    denied = [k for k, v in results.items() if v is False]
    assert len(denied) >= 2, f"음성 대조군 부족: {results}"


# --------------------------------------------------------------------------- #
# T5 팀 승인 방식 레거시 quest → 노출하되 비활성.
# --------------------------------------------------------------------------- #
def test_team_mode_quest_is_visible_but_disabled(app) -> None:
    """1인 승인으로 stage 가 안 넘어가는데 '도면 전달' 이라 쓰면 거짓말이 된다."""
    from foms.services.measurement.drawing_transfer_cta import TEAM_MODE_BLOCKED_REASON

    user = _make_user(role="STAFF", team="SALES", username="team-mode-staff")
    order = _create_order(quests=[_legacy_team_quest()])

    cta = _cta(order, user)

    assert cta["visible"] is True
    assert cta["enabled"] is False
    assert cta["blocked_reason"] == TEAM_MODE_BLOCKED_REASON
    assert TEAM_MODE_BLOCKED_REASON.strip() != ""


# --------------------------------------------------------------------------- #
# T6 role 축.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("role", ["ADMIN", "MANAGER", "STAFF"])
def test_cta_visible_for_approve_roles(app, role) -> None:
    user = _make_user(role=role, team="DELIVERY", username=f"role-{role}")
    order = _create_order(quests=[_measure_assignee_quest()])

    cta = _cta(order, user)

    assert cta["visible"] is True
    if role != "ADMIN":
        # 권한 없는 팀이면 보이되 비활성(서버와 같은 답).
        assert cta["enabled"] is False


@pytest.mark.parametrize("role", ["VIEWER", "", "staff"])
def test_cta_hidden_for_non_approve_roles(app, role) -> None:
    """role_required(foms/web/auth/routes.py:284)는 JSON 403 이 아니라 302 redirect 를
    낸다. JS 가 응답을 해석할 수 없으니 애초에 버튼을 그리지 않는다.
    비교는 대소문자 정규화 없이 원문 in 튜플 — 'staff' 는 통과하지 못한다."""
    user = _make_user(role=role or "NONE", team="SALES", username=f"role-x-{role or 'none'}")
    user.role = role  # 빈 role 도 그대로 판정 대상
    order = _create_order(quests=[_measure_assignee_quest()])

    cta = _cta(order, user)

    assert cta["visible"] is False
    assert cta["enabled"] is False


def test_cta_hidden_for_anonymous(app) -> None:
    order = _create_order(quests=[_measure_assignee_quest()])

    assert _cta(order, None)["visible"] is False


# --------------------------------------------------------------------------- #
# T7 쿼리 수 — N+1 회귀 가드.
# --------------------------------------------------------------------------- #
def test_build_ctas_issues_no_extra_queries(app) -> None:
    user = _make_user(role="STAFF", team="SALES", username="query-count-staff")
    orders = [
        _create_order(quests=[_measure_assignee_quest()], customer_name=f"주문{i}")
        for i in range(6)
    ]

    # 이미 로드된 객체를 넘긴다는 전제 — commit 으로 만료된 속성을 먼저 되살린다.
    # (여기서 되살리지 않으면 ORM refresh SELECT 가 카운터에 섞여 N+1 판정이 흐려진다.)
    _ = (user.id, user.role, user.team)
    for order in orders:
        _ = (order.id, order.status, order.structured_data)

    counter = {"n": 0}

    def _count(conn, cursor, statement, parameters, context, executemany):
        counter["n"] += 1

    event.listen(engine, "before_cursor_execute", _count)
    try:
        ctas = _ctas(orders, user)
    finally:
        event.remove(engine, "before_cursor_execute", _count)

    assert len(ctas) == len(orders)
    assert all(c["visible"] and c["enabled"] for c in ctas.values())
    assert counter["n"] == 0, f"추가 SQL {counter['n']}회 — 주문 수만큼 쿼리가 돈다"
