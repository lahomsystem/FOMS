"""완료 quest 재전이 버튼·팀 승인 버튼 — 3표면(PC 그리드·모바일 카드·모바일 상세)이 서버와 같은 답을 낸다.

배경(2026-09-20): 관리자가 강제 단계 변경(regress)으로 DRAWING→MEASURE 로 되돌리면 MEASURE quest 는
COMPLETED 그대로라, 화면이 완료 배지만 그리고 승인 버튼을 감춰 막다른 길이 됐다(스테이징 4건·운영 5건).
표시 SSOT(``build_current_quest_payload``)가 ``can_retransition``·``retransition_label``·
``retransition_confirm``·``approvable_teams``·``is_synthesized`` 를 실어 주고, 그 판정은 서버 권한
게이트와 같은 순수 함수(``quest_approve_authz``)를 쓴다.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from foms.services.erp_quest_display import build_current_quest_payload
from foms.services.orders.quest_approve_authz import (
    actor_teams_for,
    approvable_teams_for,
    authorize_quest_approve,
    quest_approve_allowed,
)

ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _user(team: str | None, role: str = "STAFF", uid: int = 7) -> SimpleNamespace:
    return SimpleNamespace(id=uid, role=role, team=team, name="테스터", username="tester")


def _order(sd: dict, order_id: int = 4382, customer_name: str = "이영아") -> SimpleNamespace:
    return SimpleNamespace(
        id=order_id, customer_name=customer_name, manager_name="담당", structured_data=sd, is_erp_order=True
    )


def _measure_completed_quest() -> dict:
    """스테이징 #4382 모양 — 실측 COMPLETED(담당자 승인 58) 인데 단계는 MEASURE 그대로."""
    return {
        "stage": "MEASURE", "title": "실측", "status": "COMPLETED", "approval_mode": "assignee",
        "required_approvals": ["CS", "SALES"], "team_approvals": {},
        "assignee_approval": {"approved": True, "approved_by": 58, "approved_by_name": "claude_master",
                              "approved_at": "2026-09-14T14:39:39"},
        "completed_at": "2026-09-14T14:39:39", "updated_at": "2026-09-14T14:39:39",
    }


def _payload(sd: dict, stage: str, stage_code: str, user, order=None) -> dict | None:
    return build_current_quest_payload(
        sd=sd, stage=stage, stage_code=stage_code, order=order or _order(sd), current_user=user, user_map={}
    )


# --------------------------------------------------------------------------- #
# 1. 재전이 가능 여부 — 서버 권한 술어와 같은 답
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "team,role,expected",
    [
        ("SALES", "STAFF", True),
        ("CS", "STAFF", True),
        ("ACCOUNTING", "STAFF", True),   # 회계팀은 CS 권한 별칭
        ("SALES", "ADMIN", True),
        ("DRAWING", "STAFF", False),
        ("PRODUCTION", "STAFF", False),
        ("SALES", "VIEWER", False),
    ],
)
def test_measure_completed_quest_offers_retransition_only_to_teams_the_server_allows(team, role, expected):
    """실측 완료 quest(단계 MEASURE 그대로): CS·영업·ADMIN 만 재전이 버튼, 도면·생산·VIEWER 는 없음."""
    sd = {"workflow": {"stage": "MEASURE"}, "quests": [_measure_completed_quest()]}
    user = _user(team, role)
    payload = _payload(sd, "실측", "MEASURE", user)
    assert payload is not None
    assert payload["is_done"] is True
    assert payload["can_retransition"] is expected, f"{team}/{role}"
    # 서버 술어와 나란히 — 화면이 True 인데 서버가 403 이면 막다른 길이 되돌아온다.
    assert quest_approve_allowed(user, _order(sd), "MEASURE", payload_quest := sd["quests"][0]) is expected
    if role != "VIEWER":  # VIEWER 는 데코레이터가 먼저 403 — authorize 까지 오지 않는다.
        allowed, status, _ = authorize_quest_approve(None, user, _order(sd), "MEASURE", payload_quest)
        assert allowed is expected and (status == 200) is expected


def test_retransition_label_and_confirm_name_the_next_stage_and_the_order():
    """버튼 문구는 다음 단계를, 확인창은 완료 사실·다음 단계·고객명/주문번호를 말한다."""
    sd = {"workflow": {"stage": "MEASURE"}, "quests": [_measure_completed_quest()]}
    payload = _payload(sd, "실측", "MEASURE", _user("SALES"))
    assert payload["retransition_label"] == "도면 단계로 넘기기"
    assert "이미 완료된 실측 완료 입니다." in payload["retransition_confirm"]
    assert "도면 단계로 다시 넘길까요?" in payload["retransition_confirm"]
    assert "이영아 / #4382" in payload["retransition_confirm"]


def test_no_user_means_no_retransition():
    """current_user 없이 만든 payload(배치 렌더 등)는 재전이 버튼을 내밀지 않는다."""
    sd = {"workflow": {"stage": "MEASURE"}, "quests": [_measure_completed_quest()]}
    assert _payload(sd, "실측", "MEASURE", None)["can_retransition"] is False


def test_already_advanced_order_has_no_quest_payload_at_all():
    """stage DRAWING + COMPLETED MEASURE quest(정상 전이 뒤)는 payload None — 재전이 축 자체가 없다."""
    sd = {"workflow": {"stage": "DRAWING"}, "quests": [_measure_completed_quest()]}
    assert _payload(sd, "도면", "DRAWING", _user("SALES", "ADMIN")) is None


def test_confirm_completed_in_korean_storage_offers_production_retransition():
    """한글 저장형(고객컨펌) COMPLETED 도 재전이 대상 — '생산 단계로 넘기기'."""
    quest = {"stage": "고객컨펌", "title": "고객 컨펌", "status": "COMPLETED", "approval_mode": "assignee",
             "assignee_approval": {"approved": True}, "completed_at": "2026-09-16T10:00:00"}
    sd = {"workflow": {"stage": "CONFIRM"}, "quests": [quest]}
    payload = _payload(sd, "고객컨펌", "CONFIRM", _user("CS"))
    assert payload["can_retransition"] is True
    assert payload["retransition_label"] == "생산 단계로 넘기기"


def test_production_completed_team_quest_does_not_retransition():
    """단계를 옮기지 않는 stage(생산)의 완료 quest 는 재전이가 없다 — 문구도 빈 문자열."""
    quest = {"stage": "PRODUCTION", "title": "생산", "status": "COMPLETED", "approval_mode": "team",
             "required_approvals": ["PRODUCTION"], "team_approvals": {"PRODUCTION": {"approved": True}}}
    sd = {"workflow": {"stage": "PRODUCTION"}, "quests": [quest]}
    payload = _payload(sd, "생산", "PRODUCTION", _user("PRODUCTION", "ADMIN"))
    assert payload["is_done"] is True
    assert payload["advances_stage"] is False
    assert payload["can_retransition"] is False
    assert payload["retransition_label"] == ""
    assert payload["retransition_confirm"] == ""
    assert payload["approvable_teams"] == []


# --------------------------------------------------------------------------- #
# 2. approvable_teams — 팀 모드에서 눌러 200 을 받을 팀만
# --------------------------------------------------------------------------- #
def _received_open_quest(team_approvals: dict | None = None) -> dict:
    return {"stage": "RECEIVED", "title": "주문 접수", "status": "OPEN", "approval_mode": "team",
            "required_approvals": ["CS"], "team_approvals": team_approvals or {}}


@pytest.mark.parametrize(
    "team,role,expected",
    [("CS", "STAFF", ["CS"]), ("ACCOUNTING", "STAFF", ["CS"]), ("SALES", "STAFF", []),
     ("CS", "ADMIN", ["CS"]), ("PRODUCTION", "ADMIN", ["CS"]), ("CS", "VIEWER", [])],
)
def test_received_open_quest_lists_only_teams_the_user_can_press(team, role, expected):
    """접수 OPEN(필수 CS): CS·회계(별칭)·ADMIN 만 ['CS'], 영업·VIEWER 는 빈 목록."""
    sd = {"workflow": {"stage": "RECEIVED"}, "quests": [_received_open_quest()]}
    payload = _payload(sd, "주문접수", "RECEIVED", _user(team, role))
    assert payload["approvable_teams"] == expected, f"{team}/{role}"
    assert payload["is_synthesized"] is False


def test_already_approved_team_is_not_listed_again():
    """CS 가 이미 승인한 접수 quest 에는 CS 버튼이 다시 안 뜬다."""
    sd = {"workflow": {"stage": "RECEIVED"},
          "quests": [_received_open_quest({"CS": {"approved": True, "approved_by": 3}})]}
    payload = _payload(sd, "주문접수", "RECEIVED", _user("CS"))
    assert payload["approvable_teams"] == []


def test_synthesized_received_quest_still_gets_cs_button():
    """접수 단계인데 저장된 quest 가 없으면 합성 quest(is_synthesized) 로도 CS 버튼을 준다 — 전이 단계라서."""
    sd = {"workflow": {"stage": "RECEIVED"}, "quests": []}
    payload = _payload(sd, "주문접수", "RECEIVED", _user("CS"))
    assert payload is not None
    assert payload["is_synthesized"] is True
    assert payload["approvable_teams"] == ["CS"]


def test_synthesized_cs_quest_gets_cs_button():
    """CS 단계 합성 quest 도 CS 버튼 — cs/complete 게이트가 CS quest 를 읽고 한 팀 승인으로 끝난다."""
    sd = {"workflow": {"stage": "CS"}, "quests": []}
    payload = _payload(sd, "CS", "CS", _user("CS"))
    assert payload["is_synthesized"] is True
    assert payload["approvable_teams"] == ["CS"]


def test_synthesized_production_quest_gets_no_team_button():
    """대조군 — 생산 단계 합성 quest 는 팀 버튼 없음(PRODUCTION quest 는 만들지 않는다는 규칙)."""
    sd = {"workflow": {"stage": "PRODUCTION"}, "quests": []}
    payload = _payload(sd, "생산", "PRODUCTION", _user("PRODUCTION"))
    assert payload is not None
    assert payload["is_synthesized"] is True
    assert payload["approvable_teams"] == []


def _db_user(username: str, *, role: str, team: str | None):
    from werkzeug.security import generate_password_hash

    from db import db_session
    from models import User

    user = User(username=username, password=generate_password_hash("pw"), role=role, team=team,
                name=f"{username} 이름", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _db_order(stage_code: str, customer_name: str):
    from db import db_session
    from foms.services.erp_display import get_today_kst
    from models import Order

    order = Order(
        received_date=get_today_kst().isoformat(), customer_name=customer_name, phone="010-1234-5678",
        address="서울 테헤란로 123", product="붙박이장", status=stage_code, manager_name="담당",
        is_erp_order=True, structured_data={"workflow": {"stage": stage_code}, "quests": []},
        erp_stage_code=stage_code,
    )
    db_session.add(order)
    db_session.commit()
    return order


def _grid_html(client, user, stage_label: str) -> str:
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    resp = client.get("/erp/dashboard", query_string={"stage": stage_label})
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


def _db_order_with_assignee_quest(stage_code: str, customer_name: str, required: list[str]):
    """담당자 모드 quest 를 실은 주문 1건(승인 팀은 인자로 고정).

    structured_data 규약대로 새 dict 를 만들어 통째로 넣는다(생성 직후라 deepcopy 불필요).
    """
    from db import db_session

    order = _db_order(stage_code, customer_name)
    order.structured_data = {
        "workflow": {"stage": stage_code},
        "quests": [{
            "stage": stage_code,
            "title": f"{stage_code} quest",
            "status": "OPEN",
            "approval_mode": "assignee",
            "required_approvals": list(required),
            "assignee_approval": {"approved": False},
        }],
    }
    db_session.commit()
    return order


def test_대조군_수정권한만_있고_담당자_승인권한이_없으면_승인_버튼이_없다(client):
    """PC 그리드 — can_edit_erp=True·can_assignee_approve=False 는 버튼 0 + '(승인 권한 없음)'.

    승인 팀이 생산팀인 담당자 quest 는 CS 팀이 눌러도 서버가 403 을 준다. 예전 술어
    (``can_edit_erp or can_assignee_approve``)는 이 사람에게 버튼을 그려 줬다.
    """
    user = _db_user("grid_assignee_cs", role="STAFF", team="CS")
    order = _db_order_with_assignee_quest("CONFIRM", "담당자 승인 음성", ["PRODUCTION"])
    order_id = order.id

    html = _grid_html(client, user, "고객컨펌")
    assert f"quest-collapse-{order_id}" in html
    assert html.count("erp-btn-approve-assignee") == 0
    assert "(승인 권한 없음)" in html


def test_대조군_담당자_승인권한만_있으면_수정권한이_없어도_승인_버튼이_있다(client):
    """PC 그리드 — can_edit_erp=False·can_assignee_approve=True 는 버튼 1개(막다른 길 0)."""
    user = _db_user("grid_assignee_prod", role="STAFF", team="PRODUCTION")
    order = _db_order_with_assignee_quest("CONFIRM", "담당자 승인 양성", ["PRODUCTION"])
    order_id = order.id

    html = _grid_html(client, user, "고객컨펌")
    assert f"quest-collapse-{order_id}" in html
    assert html.count("erp-btn-approve-assignee") == 1
    assert "(승인 권한 없음)" not in html


def test_pc_grid_says_board_not_permission_for_synthesized_production_quest(client):
    """PC 그리드 — 생산 합성 quest 는 ADMIN 에게도 '(승인 권한 없음)' 이 아니라 '(보드에서 진행)' 을 보인다."""
    user = _db_user("grid_synth_admin", role="ADMIN", team="SALES")
    order = _db_order("PRODUCTION", "합성 생산")

    html = _grid_html(client, user, "생산")
    assert f'quest-collapse-{order.id}' in html
    assert html.count("(승인 권한 없음)") == 0
    assert html.count("(보드에서 진행)") >= 1


def test_pc_grid_keeps_permission_note_for_synthesized_received_quest_without_rights(client):
    """대조군 — 접수 합성 quest 에 도면팀 STAFF 는 여전히 '(승인 권한 없음)' 이다(전이 단계라 버튼 축)."""
    user = _db_user("grid_synth_drawing", role="STAFF", team="DRAWING")
    order = _db_order("RECEIVED", "합성 접수")

    html = _grid_html(client, user, "주문접수")
    assert f'quest-collapse-{order.id}' in html
    assert "(승인 권한 없음)" in html
    assert "(보드에서 진행)" not in html


def test_persisted_production_open_quest_gets_production_button():
    """저장된 생산 OPEN quest 는 단계 무관 계산 — 생산팀에 ['PRODUCTION']."""
    quest = {"stage": "생산", "title": "생산", "status": "OPEN", "approval_mode": "team",
             "required_approvals": ["PRODUCTION"], "team_approvals": {}}
    sd = {"workflow": {"stage": "PRODUCTION"}, "quests": [quest]}
    payload = _payload(sd, "생산", "PRODUCTION", _user("PRODUCTION"))
    assert payload["is_synthesized"] is False
    assert payload["approvable_teams"] == ["PRODUCTION"]
    assert _payload(sd, "생산", "PRODUCTION", _user("SALES"))["approvable_teams"] == []


def test_assignee_mode_quest_never_lists_teams():
    """담당자 모드(실측·고객컨펌)는 팀 버튼 축이 아니다 — 항상 빈 목록."""
    quest = {"stage": "MEASURE", "title": "실측", "status": "OPEN", "approval_mode": "assignee",
             "required_approvals": ["CS", "SALES"]}
    sd = {"workflow": {"stage": "MEASURE"}, "quests": [quest]}
    payload = _payload(sd, "실측", "MEASURE", _user("CS", "ADMIN"))
    assert payload["approvable_teams"] == []
    assert approvable_teams_for(_user("CS", "ADMIN"), _order(sd), "MEASURE", quest) == []


def test_done_quest_lists_no_teams():
    """완료된 팀 quest 는 승인 버튼이 아니라 배지(+재전이) 축이다."""
    quest = {"stage": "RECEIVED", "title": "주문 접수", "status": "COMPLETED", "approval_mode": "team",
             "required_approvals": ["CS"], "team_approvals": {"CS": {"approved": True}}}
    sd = {"workflow": {"stage": "RECEIVED"}, "quests": [quest]}
    payload = _payload(sd, "주문접수", "RECEIVED", _user("CS", "ADMIN"))
    assert payload["is_done"] is True
    assert payload["approvable_teams"] == []
    assert payload["can_retransition"] is True  # 접수 완료 quest 인데 단계 RECEIVED 그대로 → 실측으로 재전이


# --------------------------------------------------------------------------- #
# 3. 순수 함수 — 시공 배정 규칙·서버 게이트 문구 유지
# --------------------------------------------------------------------------- #
def test_construction_actor_teams_follow_assignment_rows_then_team_fallback():
    """시공: 배정 행이 있으면 배정된 사람만, 없으면 CS·영업·시공 팀 폴백, ADMIN 은 항상."""
    order = _order({})
    assert actor_teams_for(_user("DRAWING", uid=5), order, "CONSTRUCTION", None,
                           construction_assignee_ids=[5]) == ["CONSTRUCTION"]
    assert actor_teams_for(_user("CONSTRUCTION", uid=9), order, "CONSTRUCTION", None,
                           construction_assignee_ids=[5]) == []
    assert actor_teams_for(_user("CONSTRUCTION", uid=9), order, "CONSTRUCTION", None,
                           construction_assignee_ids=[]) == ["CONSTRUCTION"]
    assert actor_teams_for(_user("DRAWING", uid=9), order, "CONSTRUCTION", None,
                           construction_assignee_ids=[]) == []
    assert actor_teams_for(_user("DRAWING", "ADMIN", uid=9), order, "CONSTRUCTION", None,
                           construction_assignee_ids=[5]) == ["CONSTRUCTION"]


def test_construction_gate_keeps_both_denial_messages(monkeypatch):
    """리팩터 뒤에도 시공 403 문구 두 가지(배정 있음/없음)가 그대로다."""
    import foms.services.orders.quest_approve_authz as authz

    order = _order({})
    monkeypatch.setattr(authz, "active_assignee_ids", lambda db, oid, domain: [5])
    allowed, status, msg = authorize_quest_approve(None, _user("CONSTRUCTION", uid=9), order, "CONSTRUCTION", None)
    assert (allowed, status, msg) == (False, 403, "이 주문에 배정된 시공 담당자만 승인할 수 있습니다.")
    assert authorize_quest_approve(None, _user("DRAWING", uid=5), order, "CONSTRUCTION", None)[0] is True

    monkeypatch.setattr(authz, "active_assignee_ids", lambda db, oid, domain: [])
    allowed, status, msg = authorize_quest_approve(None, _user("DRAWING", uid=9), order, "CONSTRUCTION", None)
    assert (allowed, status, msg) == (False, 403, "시공 승인 권한이 없는 팀입니다.")
    assert authorize_quest_approve(None, _user("SALES", uid=9), order, "CONSTRUCTION", None)[0] is True


def test_general_gate_message_is_unchanged():
    """일반 단계 403 문구 유지 + ADMIN bypass 유지."""
    order = _order({})
    allowed, status, msg = authorize_quest_approve(None, _user("DRAWING"), order, "MEASURE", None)
    assert (allowed, status) == (False, 403)
    assert msg == "현재 단계 승인 권한이 없는 팀입니다. (오버라이드가 필요합니다.)"
    assert authorize_quest_approve(None, _user("DRAWING", "ADMIN"), order, "MEASURE", None) == (True, 200, "")


# --------------------------------------------------------------------------- #
# 4. 템플릿·JS·핀 문자열 계약
# --------------------------------------------------------------------------- #
def test_pc_grid_has_retransition_button_and_team_gate_uses_approvable_teams():
    grid = _read("templates/orders/partials/dashboard_grid.html")
    assert grid.count("erp-btn-retransition erp-btn-approve-assignee") == 2, "셀·collapse 카드 둘 다"
    assert "o.current_quest.can_retransition" in grid
    assert "o.current_quest.retransition_confirm" in grid
    assert "team in (o.current_quest.approvable_teams or [])" in grid
    # 옛 팀 버튼 게이트(can_edit_erp 단독)가 남아 있으면 서버가 403 을 줄 버튼이 다시 뜬다.
    assert "can_edit_erp|default(false) %}\n                  {% set order_id_approve" not in grid.replace("\r\n", "\n")
    assert "(승인 권한 없음)" in grid


def test_mobile_card_has_retransition_button_and_team_axis():
    card = _read("templates/partials/shared/erp_mobile_queue_card_v2.html")
    assert "erp-queue-card__quest-retransition" in card
    assert "quest.can_retransition" in card
    assert "quest.retransition_confirm" in card
    assert "(quest.can_assignee_approve or quest.approvable_teams)" in card
    assert 'data-team="{{ quest.approvable_teams[0] }}"' in card
    assert "quest_inline_approve = quest_actionable and quest.advances_stage" in card


def test_mobile_detail_has_retransition_button_and_team_buttons_reachable():
    detail = _read("templates/orders/partials/order_detail_mobile_v2.html")
    assert "erp-mobile-quest-retransition" in detail
    assert 'data-refresh-anchor="#foms-detail-quest"' in detail
    assert "order.current_quest.can_assignee_approve or approvable_teams" in detail
    assert "team not in approvable_teams" in detail
    assert "{{ team }} 대기" in detail


def test_js_handles_retransition_buttons_and_response_key():
    mobile = _read("static/js/foms/erp-quest-approve.js")
    assert ".erp-queue-card__quest-retransition" in mobile
    assert ".erp-mobile-quest-retransition" in mobile
    assert "data.retransitioned" in mobile
    pc = _read("static/js/orders/dashboard/erp-dashboard-quest.js")
    assert "data.retransitioned" in pc
    # 재전이 토스트 분기가 auto_transitioned 분기보다 앞에 있어야 '승인 완료' 로 잘못 말하지 않는다.
    assignee_fn = pc.index("async function approveQuestAssignee")
    assert pc.index("data.retransitioned", assignee_fn) < pc.index("data.auto_transitioned", assignee_fn)


def test_asset_pins_bumped_to_20260920b():
    """JS·CSS 를 바꿨으니 핀을 올린다 — 안 올리면 SW 캐시로 옛 파일이 산다.

    erp-quest-approve.js·erp-dashboard-quest.js 는 ADMIN-OVERRIDE-01(관리자 강제 진행 재시도
    배선)로 다시 바뀌어 핀이 20260921a 로 올라갔다. 모듈 핀을 품은 erp-dashboard-entry.js 도
    함께 바뀌었으므로 그 핀도 올린다 — 안 올리면 옛 entry 가 옛 모듈 핀을 계속 부른다.
    나머지 자산은 그때 안 바뀌었으니 20260920b 그대로다.
    """
    assert "erp-quest-approve.js') }}?v=20260921a" in _read("templates/partials/shared/layout_scripts.html")
    assert "erp-dashboard-entry.js') }}?v=20260921a" in _read("templates/partials/shared/layout_scripts.html")
    assert "erp-pro.css') }}?v=20260920b" in _read("templates/partials/shared/layout_head.html")
    assert "04-filter-table-badges-buttons.css?v=20260920b" in _read("static/css/foundation/erp-pro.css")
    entry = _read("static/js/orders/erp-dashboard-entry.js")
    assert "erp-dashboard-quest.js?v=20260921a" in entry
    assert "erp-dashboard-detail-dom.js?v=20260920b" in entry
    for rel in ("templates/orders/dashboard.html", "templates/orders/partials/dashboard_main.html"):
        assert "foms-v2-cs-hero.css') }}?v=20260920b" in _read(rel)
    assert ".erp-btn-retransition" in _read("static/css/foundation/erp-pro/04-filter-table-badges-buttons.css")
