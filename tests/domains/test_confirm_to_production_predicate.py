"""고객컨펌 승인 판정 SSOT 진리표 — ``check_quest_approvals_complete`` 와 소비자 3곳(2026-09-17).

이다은 주문(운영 제보)은 담당자 승인이 끝나 quest 가 COMPLETED 였는데 생산 API 게이트가
``team_approvals`` 만 봐서 409(missing CS·SALES)를 냈다. 판정을 한 함수에 모으고, 그 함수가
(status × approval_mode × 승인 상태 × 단계 표기) 조합마다 무엇을 답하는지 표로 고정한다.
소비자(전이 서비스·생산 시작 게이트·CS 완료 게이트)는 같은 답을 내야 한다.
"""
from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.orders.erp_policy_quests import (
    ASSIGNEE_MISSING_TOKEN,
    check_quest_approvals_complete,
)
from foms.services.orders.quest_transition_service import _stage_quest_complete
from models import Order, User

_CONFIRM_TEAMS = ["CS", "SALES"]


def _assignee_quest(*, status: str, approved: bool, stage: str = "CONFIRM") -> dict:
    return {
        "stage": stage,
        "title": "고객 컨펌",
        "status": status,
        "approval_mode": "assignee",
        "required_approvals": list(_CONFIRM_TEAMS),
        "team_approvals": {},
        "assignee_approval": {
            "approved": approved,
            "approved_by": 12 if approved else None,
            "approved_by_name": "담당" if approved else None,
            "approved_at": "2026-09-16T10:00:00" if approved else None,
        },
    }


def _team_quest(*, status: str, approved_teams: list[str], stage: str = "CONFIRM") -> dict:
    return {
        "stage": stage,
        "title": "고객 컨펌",
        "status": status,
        "approval_mode": "team",
        "required_approvals": list(_CONFIRM_TEAMS),
        "team_approvals": {
            t: {"approved": True, "approved_by": 1, "approved_at": "2026-09-16T10:00:00"}
            for t in approved_teams
        },
        "assignee_approval": None,
    }


def _sd(*quests: dict) -> dict:
    return {"workflow": {"stage": "CONFIRM"}, "quests": list(quests)}


# --------------------------------------------------------------------------- #
# 1. 진리표 — status × assignee 승인 × stage 표기
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("stored_stage", ["CONFIRM", "고객컨펌"])
@pytest.mark.parametrize("call_stage", ["CONFIRM", "고객컨펌"])
@pytest.mark.parametrize("status", ["OPEN", "IN_PROGRESS", "COMPLETED"])
@pytest.mark.parametrize("approved", [True, False])
def test_assignee_mode_truth_table(stored_stage, call_stage, status, approved):
    """assignee 모드: COMPLETED 는 무조건 (True, []); 아니면 assignee 승인 여부가 답.

    미승인이면 missing 은 팀 코드가 아니라 ``ASSIGNEE`` 토큰 하나다.
    """
    sd = _sd(_assignee_quest(status=status, approved=approved, stage=stored_stage))
    got = check_quest_approvals_complete(sd, call_stage)
    if status == "COMPLETED" or approved:
        assert got == (True, [])
    else:
        assert got == (False, [ASSIGNEE_MISSING_TOKEN])
        assert ASSIGNEE_MISSING_TOKEN == "ASSIGNEE"


@pytest.mark.parametrize("stored_stage", ["CONFIRM", "고객컨펌"])
@pytest.mark.parametrize("call_stage", ["CONFIRM", "고객컨펌"])
@pytest.mark.parametrize("status", ["OPEN", "IN_PROGRESS", "COMPLETED"])
@pytest.mark.parametrize(
    "approved_teams, expected_missing",
    [(["CS", "SALES"], []), (["CS"], ["SALES"]), ([], ["CS", "SALES"])],
)
def test_team_mode_truth_table(stored_stage, call_stage, status, approved_teams, expected_missing):
    """team 모드: COMPLETED 는 무조건 (True, []); 아니면 전원 승인만 True, 나머지는 빠진 팀 목록."""
    sd = _sd(_team_quest(status=status, approved_teams=approved_teams, stage=stored_stage))
    got = check_quest_approvals_complete(sd, call_stage)
    if status == "COMPLETED":
        assert got == (True, [])
    else:
        assert got == (not expected_missing, expected_missing)


@pytest.mark.parametrize("call_stage", ["CONFIRM", "고객컨펌"])
def test_no_quest_returns_template_teams(call_stage):
    """quest 가 없으면 (False, 템플릿 필수 팀) — 고객컨펌은 CS·SALES."""
    assert check_quest_approvals_complete({"quests": []}, call_stage) == (False, ["CS", "SALES"])
    assert check_quest_approvals_complete({}, call_stage) == (False, ["CS", "SALES"])


def test_first_matching_quest_wins():
    """같은 단계 quest 가 둘이면 리스트 순서상 첫 매칭이 답이다(find_stage_quest 와 같은 규칙)."""
    sd = _sd(
        _assignee_quest(status="OPEN", approved=False, stage="고객컨펌"),
        _assignee_quest(status="COMPLETED", approved=True, stage="CONFIRM"),
    )
    assert check_quest_approvals_complete(sd, "CONFIRM") == (False, [ASSIGNEE_MISSING_TOKEN])


def test_stale_other_stage_quest_is_not_matched():
    """옛 단계(MEASURE) quest 만 있으면 CONFIRM 판정은 quest 없음과 같다."""
    sd = _sd(_assignee_quest(status="COMPLETED", approved=True, stage="MEASURE"))
    assert check_quest_approvals_complete(sd, "CONFIRM") == (False, ["CS", "SALES"])


# --------------------------------------------------------------------------- #
# 2. 소비자 1 — 전이 서비스 ``_stage_quest_complete`` (quest 없음 → True)
# --------------------------------------------------------------------------- #
def test_transition_service_predicate_agrees():
    """전이 서비스는 quest 없음만 True 로 더하고, 나머지는 SSOT 의 [0] 을 그대로 쓴다."""
    assert _stage_quest_complete({"quests": []}, "고객컨펌", "CONFIRM") is True
    assert _stage_quest_complete(
        _sd(_assignee_quest(status="COMPLETED", approved=True, stage="고객컨펌")), "고객컨펌", "CONFIRM"
    ) is True
    assert _stage_quest_complete(
        _sd(_assignee_quest(status="OPEN", approved=False)), "고객컨펌", "CONFIRM"
    ) is False
    assert _stage_quest_complete(
        _sd(_team_quest(status="IN_PROGRESS", approved_teams=["CS"])), "고객컨펌", "CONFIRM"
    ) is False
    # 한글 저장형 quest 를 코드로 찾는 경우 — 별칭이 어긋나면 '없음 → True' 로 새어 나간다(CEO P2).
    assert _stage_quest_complete(
        _sd(_assignee_quest(status="OPEN", approved=False, stage="고객컨펌")), "CONFIRM", "CONFIRM"
    ) is False
    assert _stage_quest_complete(
        _sd(_assignee_quest(status="OPEN", approved=False, stage="CONFIRM")), "고객컨펌", "고객컨펌"
    ) is False


# --------------------------------------------------------------------------- #
# 3. 소비자 2·3 — HTTP 게이트(생산 시작·CS 완료)
# --------------------------------------------------------------------------- #
def _make_user(username: str, *, team: str) -> User:
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role="ADMIN",
        team=team,
        name=f"{username} 이름",
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


def _make_order(stage_code: str, quests: list[dict]) -> Order:
    order = Order(
        received_date="2026-09-16",
        customer_name="판정 고객",
        phone="010-0000-0000",
        address="Seoul",
        product="붙박이장",
        status=stage_code,
        manager_name="Bob",
        is_erp_order=True,
        structured_data={"workflow": {"stage": stage_code}, "quests": quests},
        erp_stage_code=stage_code,
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_production_start_gate_reports_assignee_token(client):
    """CONFIRM + assignee 미승인 → production/start 409 QUEST_INCOMPLETE, missing_teams == ['ASSIGNEE']."""
    _login(client, _make_user("pred_start_block", team="PRODUCTION"))
    order_id = _make_order("CONFIRM", [_assignee_quest(status="OPEN", approved=False, stage="고객컨펌")]).id

    resp = client.post(f"/api/orders/{order_id}/production/start", json={})
    assert resp.status_code == 409, resp.get_json()
    body = resp.get_json()
    assert body["code"] == "QUEST_INCOMPLETE"
    assert body["missing_teams"] == [ASSIGNEE_MISSING_TOKEN]

    db_session.expire_all()
    assert db_session.get(Order, order_id).erp_stage_code == "CONFIRM"


def test_production_start_gate_passes_completed_assignee_quest(client):
    """CONFIRM + quest COMPLETED(담당자 승인, 한글 stage 저장) → production/start 200(호환 경로)."""
    _login(client, _make_user("pred_start_ok", team="PRODUCTION"))
    order_id = _make_order("CONFIRM", [_assignee_quest(status="COMPLETED", approved=True, stage="고객컨펌")]).id

    resp = client.post(f"/api/orders/{order_id}/production/start", json={})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["new_status"] == "PRODUCTION"

    db_session.expire_all()
    assert db_session.get(Order, order_id).erp_stage_code == "PRODUCTION"


def _cs_quest(*, status: str, approved: bool) -> dict:
    return {
        "stage": "CS", "status": status, "approval_mode": "team", "required_approvals": ["CS"],
        "team_approvals": {"CS": {"approved": approved, "approved_by": None, "approved_at": None}},
    }


def test_cs_complete_gate_agrees_with_predicate(client):
    """cs/complete: CS team quest OPEN 미승인 → 409 QUEST_INCOMPLETE(missing ['CS']); COMPLETED → 200."""
    _login(client, _make_user("pred_cs", team="CS"))
    blocked_id = _make_order("CS", [_cs_quest(status="OPEN", approved=False)]).id
    resp = client.post(f"/api/orders/{blocked_id}/cs/complete", json={})
    assert resp.status_code == 409, resp.get_json()
    assert resp.get_json()["code"] == "QUEST_INCOMPLETE"
    assert resp.get_json()["missing_teams"] == ["CS"]

    done_id = _make_order("CS", [_cs_quest(status="COMPLETED", approved=False)]).id
    resp = client.post(f"/api/orders/{done_id}/cs/complete", json={})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["new_status"] == "COMPLETED"
