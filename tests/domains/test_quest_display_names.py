"""현재 작업 이름·넘기기 버튼·팀 이름 표시 계약."""

from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

from foms.services.erp_quest_display import build_current_quest_payload
from foms.services.orders.erp_policy_quests import create_quest_from_template, get_quest_template_for_stage
from foms.services.orders.quest_approve_cta import _QUEST_TASK_LABELS, build_approve_cta, display_quest_title
from foms.services.orders.team_labels import team_label


def test_payload_title_uses_name_tag_and_keeps_stored_title() -> None:
    sd = {
        "workflow": {"stage": "RECEIVED"},
        "quests": [{"stage": "RECEIVED", "title": "주문 정보 확인", "status": "OPEN", "approval_mode": "team"}],
    }
    before = copy.deepcopy(sd)
    order = SimpleNamespace(id=1, customer_name="홍", manager_name="")
    payload = build_current_quest_payload(
        sd=sd, stage="접수", stage_code="RECEIVED", order=order, current_user=None, user_map={}
    )
    assert payload["title"] == "접수 확인"
    assert sd == before


@pytest.mark.parametrize(
    ("code", "task", "approve", "retransition", "done"),
    [
        ("RECEIVED", "접수 확인", "실측 단계로 넘기기", "실측 단계로 넘기기", "접수 확인 완료"),
        ("MEASURE", "실측 완료", "도면 단계로 넘기기", "도면 단계로 넘기기", "실측 완료"),
        ("CONFIRM", "고객 컨펌 완료", "생산 단계로 넘기기", "생산 단계로 넘기기", "고객 컨펌 완료"),
        ("CS", "CS 확인", "CS 확인", "", "CS 확인 완료"),
        ("PRODUCTION", "생산 확인", "생산 확인", "", "생산 확인 완료"),
        ("CONSTRUCTION", None, None, "", "시공 완료"),
        ("AS", "AS 확인", "AS 확인", "", "AS 확인 완료"),
        ("DRAWING", None, None, "", None),
    ],
)
def test_cta_labels_per_stage(code, task, approve, retransition, done) -> None:
    cta = build_approve_cta(code, SimpleNamespace(id=1, customer_name="홍"))
    assert cta["task_label"] == task
    assert cta["approve_label"] == approve
    assert cta["retransition_label"] == retransition
    if done is not None:
        assert cta["done_label"] == done


def test_display_quest_title_falls_back_to_stored_title() -> None:
    assert display_quest_title("AS_RECEIVED", "AS 접수") == "AS 접수"
    assert display_quest_title("NOPE", None) == ""
    assert display_quest_title("MEASURE", "옛 이름") == "실측 완료"


def test_team_label() -> None:
    assert team_label("CS") == "CS팀"
    assert team_label("ZZ") == "ZZ"
    assert team_label(None) == ""


@pytest.mark.parametrize(
    "code", ["RECEIVED", "MEASURE", "DRAWING", "CONFIRM", "PRODUCTION", "CONSTRUCTION", "CS", "COMPLETED", "AS"]
)
def test_quest_template_keys_and_title_match_name_tag(code) -> None:
    tpl = get_quest_template_for_stage(code)
    assert tpl is not None
    assert set(tpl) <= {"title", "description", "owner_team", "required_approvals", "next_stage"}
    if code in _QUEST_TASK_LABELS:
        assert tpl["title"] == _QUEST_TASK_LABELS[code]


def test_new_received_quest_stores_name_tag_title() -> None:
    assert create_quest_from_template("RECEIVED", "", {})["title"] == "접수 확인"
