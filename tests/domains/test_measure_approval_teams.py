"""실측·고객컨펌 승인 팀 계약 (2026-09-13).

운영 신고: 영업팀(`team=SALES`)이 모바일에서 라홈 발주 주문의 **실측 완료**를 누르자
서버가 403 "현재 단계 승인 권한이 없는 팀입니다" 를 냈다. 운영 DB 확인 결과 그 주문의
실측 quest 가 `required_approvals=['CS']` 로 저장돼 있었다(실측 단계 라홈 344건, 그중
`['CS']` 저장 84건).

두 가지가 동시에 틀려 있었다.

1. **업무 규칙이 달랐다.** 실측·고객컨펌의 주관 팀은 CS 와 영업 **둘 다**다
   (사용자 확인 2026-09-13: CS 자가실측, 영업 방문실측). 그런데 템플릿 기본값은
   `["SALES"]` 라 CS 를 배제했고, 라홈 분기는 `["CS"]` 로 덮어써 영업을 배제했다.
2. **화면과 서버가 다른 잣대를 썼다.** 서버는 `required_approvals` 로 판정하는데 화면은
   `can_edit_erp`/도메인 권한만 봐서, **서버가 거부할 버튼을 화면이 내밀었다.**

여기서 못박는 것: 두 단계의 승인 팀은 발주사와 무관하게 CS+영업이고, 화면 판정과 서버
판정이 **같은 답**을 낸다(음성 대조군: 그 밖의 팀은 여전히 거부).
"""
from __future__ import annotations

from types import SimpleNamespace

from foms.services.orders.erp_policy_quests import (
    create_quest_from_template,
    resolve_required_approval_teams,
)

LAHOM_SD = {"parties": {"orderer": {"name": "라홈"}}}
OTHER_SD = {"parties": {"orderer": {"name": "하우드"}}}


def test_measure_and_confirm_are_owned_by_cs_and_sales() -> None:
    """실측·고객컨펌 승인 팀 = CS + 영업. 어느 한 팀도 배제하지 않는다."""
    for stage in ("MEASURE", "CONFIRM"):
        teams = set(resolve_required_approval_teams(stage))
        assert teams == {"CS", "SALES"}, f"{stage}: {teams}"


def test_lahom_does_not_narrow_the_approval_axis() -> None:
    """라홈 발주사여도 승인 팀은 그대로다 — 좁히면 영업이 방문실측을 못 누른다."""
    for sd in (LAHOM_SD, OTHER_SD):
        quest = create_quest_from_template("MEASURE", "홍길동", sd)
        assert set(quest["required_approvals"]) == {"CS", "SALES"}


def test_lahom_still_marks_cs_as_the_owner_team() -> None:
    """주관 팀 표시(owner_team)는 라홈이면 CS 그대로 — 승인 축과 다른 축이다."""
    lahom = create_quest_from_template("MEASURE", "홍길동", LAHOM_SD)
    other = create_quest_from_template("MEASURE", "홍길동", OTHER_SD)
    assert lahom["owner_team"] == "CS"
    assert other["owner_team"] == "SALES"


def test_saved_quest_narrower_than_policy_is_overridden() -> None:
    """옛 규칙으로 좁게 저장된 quest 는 정책이 이긴다 — 마이그레이션 없이 오늘 풀리게."""
    saved = {"required_approvals": ["CS"]}  # 운영 84건의 모양
    assert set(resolve_required_approval_teams("MEASURE", saved)) == {"CS", "SALES"}


def test_saved_quest_wider_than_policy_is_respected() -> None:
    """수동으로 넓혀 둔 값은 보존한다(정책이 좁힌다고 덮지 않는다)."""
    saved = {"required_approvals": ["CS", "SALES", "DRAWING"]}
    assert set(resolve_required_approval_teams("MEASURE", saved)) == {"CS", "SALES", "DRAWING"}


def _server_allows(team: str, role: str, quest: dict) -> bool:
    """서버 권한 게이트가 허용하는가(`_authorize_quest_approve` 와 같은 술어)."""
    from foms.api.quest import _required_teams_for_stage
    from foms.services.orders.order_mutation_policy import team_has_capability

    if role.upper() == "ADMIN":
        return True
    required = _required_teams_for_stage(quest, "MEASURE")
    return bool(required) and team_has_capability(team, required)


def _screen_shows(team: str, role: str, sd: dict, quest: dict) -> bool:
    """화면이 승인 버튼을 보여주는가(`can_assignee_approve`)."""
    from foms.services.erp_quest_display import build_current_quest_payload

    user = SimpleNamespace(id=7, role=role, team=team, name="테스터", username="tester")
    full_sd = dict(sd, workflow={"stage": "MEASURE"}, quests=[quest])
    order = SimpleNamespace(id=1, customer_name="김태우", manager_name="테스터",
                            structured_data=full_sd, is_erp_order=True)
    payload = build_current_quest_payload(
        sd=full_sd,
        stage="실측", stage_code="MEASURE", order=order,
        current_user=user, user_map={},
    )
    return bool(payload and payload["can_assignee_approve"])


def test_screen_and_server_give_the_same_answer() -> None:
    """화면이 보여주는 것 == 서버가 허용하는 것. 어긋나면 눌렀는데 403 이 난다."""
    quest = {"stage": "MEASURE", "title": "실측", "status": "OPEN",
             "approval_mode": "assignee", "required_approvals": ["CS"]}  # 운영의 옛 저장값
    for sd_label, sd in (("라홈", LAHOM_SD), ("하우드", OTHER_SD)):
        for team, role in (("SALES", "MANAGER"), ("CS", "STAFF"),
                           ("PRODUCTION", "STAFF"), ("DRAWING", "STAFF")):
            server = _server_allows(team, role, dict(quest))
            screen = _screen_shows(team, role, sd, dict(quest))
            assert screen == server, f"{sd_label}/{team}/{role}: 화면={screen} 서버={server}"


def test_sales_can_now_approve_lahom_measure() -> None:
    """운영 재현 케이스 — 영업팀 강민경(SALES/MANAGER)이 라홈 실측을 누를 수 있어야 한다."""
    quest = {"stage": "MEASURE", "title": "실측", "status": "OPEN",
             "approval_mode": "assignee", "required_approvals": ["CS"]}
    assert _server_allows("SALES", "MANAGER", dict(quest)) is True
    assert _screen_shows("SALES", "MANAGER", LAHOM_SD, dict(quest)) is True


def test_unrelated_team_is_still_denied() -> None:
    """음성 대조군 — 넓히는 변경이 '아무나 누른다'가 되지 않았는지."""
    quest = {"stage": "MEASURE", "title": "실측", "status": "OPEN",
             "approval_mode": "assignee", "required_approvals": ["CS", "SALES"]}
    assert _server_allows("PRODUCTION", "STAFF", dict(quest)) is False
    assert _screen_shows("PRODUCTION", "STAFF", LAHOM_SD, dict(quest)) is False
