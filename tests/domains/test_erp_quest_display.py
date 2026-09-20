"""ERP quest display SSOT — resolve, approval state, assignee gate."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from foms.services import erp_quest_display as qd
from foms.services.orders import quest_approve_cta as cta_mod

ROOT = Path(__file__).resolve().parents[2]


def test_resolve_synthesizes_template_when_no_persisted_quest() -> None:
    sd = {"workflow": {"stage": "MEASURE"}, "quests": []}
    quest = qd.resolve_current_quest(sd, "실측", "MEASURE")
    assert quest is not None
    assert quest.get("title")
    assert quest.get("status") == "OPEN"


def test_resolve_skips_completed_when_only_stale_measure_quest() -> None:
    sd = {
        "workflow": {"stage": "DRAWING"},
        "quests": [
            {
                "stage": "실측",
                "title": "실측",
                "status": "COMPLETED",
                "approval_mode": "assignee",
                "assignee_approval": {"approved": True},
            },
            {"stage": "도면", "title": "도면", "status": "OPEN", "approval_mode": "assignee"},
        ],
    }
    quest = qd.resolve_current_quest(sd, "도면", "DRAWING")
    assert quest is None


def test_resolve_picks_open_stage_matched_quest() -> None:
    sd = {
        "workflow": {"stage": "MEASURE"},
        "quests": [
            {"stage": "실측", "title": "실측", "status": "COMPLETED"},
            {"stage": "실측", "title": "실측", "status": "OPEN", "approval_mode": "assignee"},
        ],
    }
    quest = qd.resolve_current_quest(sd, "실측", "MEASURE")
    assert quest is not None
    assert quest.get("status") == "OPEN"


def test_all_approved_assignee_mode_when_approved() -> None:
    quest = {
        "approval_mode": "assignee",
        "assignee_approval": {"approved": True},
        "status": "IN_PROGRESS",
    }
    all_ok, missing, _, _ = qd._compute_approval_state(quest, "실측", {})
    assert all_ok is True
    assert missing == []


def test_build_payload_sets_can_assignee_for_manager_name_match() -> None:
    sd = {
        "workflow": {"stage": "MEASURE"},
        "parties": {"manager": {"name": "Manager Kim"}},
        "quests": [
            {
                "stage": "실측",
                "title": "실측",
                "status": "OPEN",
                "approval_mode": "assignee",
                "assignee_approval": {"approved": False},
            }
        ],
    }
    # 2026-09-13: 팀은 실측 승인 팀(CS·영업) 중 하나여야 한다. 예전에는 CONSTRUCTION 으로도
    # True 가 나왔는데, 서버(`_authorize_quest_approve`)는 그 팀을 403 으로 거부했다 —
    # 화면만 "누를 수 있다"고 말하던 거짓말이었다. 음성 대조군은 아래 테스트가 맡는다.
    user = SimpleNamespace(
        id=9,
        name="Manager Kim",
        username="mkim",
        role="STAFF",
        team="SALES",
    )
    order = SimpleNamespace(id=1, manager_name="Manager Kim", structured_data=sd)
    payload = qd.build_current_quest_payload(
        sd=sd,
        stage="실측",
        stage_code="MEASURE",
        order=order,
        current_user=user,
        user_map={},
    )
    assert payload is not None
    assert payload["can_assignee_approve"] is True
    assert payload["all_approved"] is False


def test_mobile_detail_template_allows_assignee_gate() -> None:
    partial = (
        ROOT / "templates" / "orders" / "partials" / "order_detail_mobile_v2.html"
    ).read_text(encoding="utf-8")
    assert "can_approve_quest" in partial
    assert "can_assignee_approve" in partial
    # 승인 CTA 동작은 큐 카드와 공용인 erp-quest-approve.js 로 이관됐다.
    approve_js = (ROOT / "static" / "js" / "foms" / "erp-quest-approve.js").read_text(
        encoding="utf-8"
    )
    assert "invalidatePrimaryNavFragmentCache" in approve_js
    # 승인 성공 뒤 문서를 실제로 다시 읽어야 한다 — 해시만 바꾸는 location.href 는
    # 같은 URL 에서 아무 일도 하지 않아 버튼이 disabled 로 굳는다(회귀 가드).
    assert "window.location.reload()" in approve_js
    assert "location.href = location.pathname" not in partial


def test_resolve_order_role_assignees_from_structured_data() -> None:
    sd = {
        "parties": {"manager": {"name": "안중훈"}},
        "assignments": {
            "sales_assignee_user_ids": [7],
            "drawing_assignee_user_ids": [41],
        },
        "drawing_assignees": [{"id": 41, "name": "최상용"}],
        "shipment": {
            "construction_workers": ["김시공", "박시공"],
            "drawing_manager": "레거시도면",
        },
    }
    order = SimpleNamespace(manager_name="안중훈")
    roles = qd.resolve_order_role_assignees(sd, order=order, user_map={7: "한용희", 41: "최상용"})
    assert roles["measurement_assignee"] == "한용희"
    assert roles["drawing_assignee"] == "최상용"
    assert roles["construction_assignee"] == "김시공, 박시공"


def test_resolve_order_role_assignees_from_id_only_drawing_assignees() -> None:
    sd = {
        "drawing_assignees": [{"id": 41}],
        "assignments": {"drawing_assignee_user_ids": [41]},
        "shipment": {},
    }
    roles = qd.resolve_order_role_assignees(sd, user_map={41: "최상용"})
    assert roles["drawing_assignee"] == "최상용"


def test_resolve_order_role_assignees_normalizes_numeric_manager_id() -> None:
    sd = {
        "parties": {"manager": {"name": 99}},
    }
    order = SimpleNamespace(manager_name="Alice")
    roles = qd.resolve_order_role_assignees(sd, order=order, user_map={99: "Resolved Manager"})
    assert roles["measurement_assignee"] == "Resolved Manager"


def test_mobile_order_detail_renders_role_assignee_section() -> None:
    partial = (
        ROOT / "templates" / "orders" / "partials" / "order_detail_mobile_v2.html"
    ).read_text(encoding="utf-8")
    assert "foms-detail-assignee-title" in partial
    assert "measurement_assignee" in partial
    assert "drawing_assignee" in partial
    assert "construction_assignee" in partial
    assert "{'label': '담당', 'value': order.manager_name" not in partial


def test_build_payload_none_for_drawing_stage() -> None:
    sd = {
        "workflow": {"stage": "DRAWING"},
        "quests": [
            {
                "stage": "실측",
                "title": "실측",
                "status": "COMPLETED",
                "approval_mode": "assignee",
                "assignee_approval": {"approved": True},
            }
        ],
    }
    order = SimpleNamespace(id=2761, manager_name="Test", structured_data=sd)
    payload = qd.build_current_quest_payload(
        sd=sd,
        stage="도면",
        stage_code="DRAWING",
        order=order,
        current_user=None,
        user_map={},
    )
    assert payload is None


def test_erp_shell_exports_fragment_cache_invalidation() -> None:
    shell_js = (ROOT / "static" / "js" / "runtime" / "erp-shell.js").read_text(encoding="utf-8")
    assert "invalidatePrimaryNavFragmentCache" in shell_js
    assert "invalidateFragmentCache" in shell_js


def test_measurement_mobile_list_does_not_force_measure_badge() -> None:
    listing = (
        ROOT / "templates" / "measurement" / "partials" / "mobile_list.html"
    ).read_text(encoding="utf-8")
    assert "badge_text='실측'" not in listing
    assert "'--measure'" not in listing


def test_assignee_user_ids_accepts_scalar_manager():
    """parties.manager 가 문자열이어도 터지지 않는다(대시보드 전체 500 방지).

    실측 대시보드·AS 전달 배정은 담당자를 dict/스칼라 두 모양으로 다 읽는다. 여기서 dict 를
    가정하면 스칼라 주문 한 건이 모바일 큐 배치 조회를 통째로 깨뜨린다(2026-09-09 로컬 재현).
    """
    from foms.services.erp_quest_display import assignee_user_ids_from_sd

    assert assignee_user_ids_from_sd({"parties": {"manager": "이정민"}}) == set()
    assert assignee_user_ids_from_sd({"parties": {"manager": "42"}}) == {42}
    assert assignee_user_ids_from_sd({"parties": {"manager": 7}}) == {7}
    assert assignee_user_ids_from_sd({"parties": {"manager": {"name": "9"}}}) == {9}
    assert assignee_user_ids_from_sd({"parties": {"manager": None}}) == set()


def _payload_for_stage(stage: str, stage_code: str) -> dict:
    """해당 stage 의 current_quest payload 를 만든다(승인 CTA 문구 검증용)."""
    sd = {
        "workflow": {"stage": stage_code},
        "quests": [{"stage": stage_code, "title": stage, "status": "OPEN"}],
    }
    order = SimpleNamespace(id=4385, customer_name="홍길동", manager_name="안중훈")
    return qd.build_current_quest_payload(
        sd=sd, stage=stage, stage_code=stage_code, order=order, current_user=None, user_map={}
    )


def test_approve_cta_names_the_stage_and_promises_the_move() -> None:
    """단계를 실제로 옮기는 stage 는 다음 단계까지 문구가 말한다(승인 문구 SSOT)."""
    measure = _payload_for_stage("실측", "MEASURE")
    assert measure["approve_label"] == "실측 완료"
    assert measure["advances_stage"] is True
    assert measure["next_stage_label"] == "도면"
    assert "도면 단계로 넘길까요?" in measure["approve_confirm"]
    # 오탭 방지용 대상 표기(고객명/주문번호).
    assert "홍길동 / #4385" in measure["approve_confirm"]

    received = _payload_for_stage("주문접수", "RECEIVED")
    assert received["approve_label"] == "접수 확인"
    assert received["advances_stage"] is True
    assert received["next_stage_label"] == "실측"


def test_approve_cta_does_not_promise_a_move_that_never_happens() -> None:
    """생산·CS 는 승인해도 stage 가 그대로다 — 문구가 이동을 약속하면 안 된다."""
    for stage, stage_code, label in [
        ("생산", "PRODUCTION", "생산 확인"),
        ("CS", "CS", "CS 확인"),
    ]:
        payload = _payload_for_stage(stage, stage_code)
        assert payload["approve_label"] == label
        assert payload["advances_stage"] is False
        assert "그대로 유지됩니다" in payload["approve_confirm"]
        assert "넘길까요" not in payload["approve_confirm"]


def test_command_required_stage_exposes_no_approve_button() -> None:
    """도면만 quest approve API 가 409 로 거부한다 — 버튼 자체를 주면 막다른 길이다.

    고객컨펌은 2026-09-17 부터 승인 API 가 생산 단계로 넘기므로 버튼 문구가 있다.
    """
    order = SimpleNamespace(id=1, customer_name="홍길동")
    drawing = cta_mod.build_approve_cta("DRAWING", order)
    assert drawing["approve_label"] is None
    assert drawing["command_required"] is True

    confirm = cta_mod.build_approve_cta("CONFIRM", order)
    assert confirm["approve_label"] == "고객 컨펌 완료"
    assert confirm["advances_stage"] is True
    assert confirm["next_stage_label"] == "생산"
    assert confirm["command_required"] is False
    assert "생산 단계로 넘길까요" in confirm["approve_confirm"]
    assert confirm["done_label"] == "고객 컨펌 완료"
    # 완료 단계는 다음 stage 가 없어 승인이 아무것도 바꾸지 않는다 — 역시 버튼 없음.
    assert cta_mod.build_approve_cta("COMPLETED", SimpleNamespace(id=1))["approve_label"] is None


def test_done_label_always_ends_with_wanryo() -> None:
    """완료 배지 문구는 단계마다 '… 완료' 꼴 — 이미 '완료' 로 끝나는 라벨은 그대로 쓴다."""
    order = SimpleNamespace(id=1, customer_name="홍길동")
    expected = {
        "CONFIRM": "고객 컨펌 완료",
        "MEASURE": "실측 완료",
        "RECEIVED": "접수 확인 완료",
        "PRODUCTION": "생산 확인 완료",
        "CONSTRUCTION": "시공 확인 완료",
        "CS": "CS 확인 완료",
    }
    for stage_code, label in expected.items():
        assert cta_mod.build_approve_cta(stage_code, order)["done_label"] == label, stage_code
    # 조기 반환(라벨 없는 단계)도 done_label 을 준다.
    assert "done_label" in cta_mod.build_approve_cta("DRAWING", order)


def test_queue_card_hides_approve_when_server_gives_no_label() -> None:
    """카드의 승인 CTA 노출은 approve_label 이 SSOT — 도면 카드가 '도면 창구'를 되찾는다.

    고객컨펌 전용 링크(confirm_actionable)는 사라졌다 — 이제 승인 버튼이 직접 그려지고,
    끝난 quest 는 완료 배지(erp-queue-card__quest-done)를 단다.
    """
    card = (
        ROOT / "templates" / "partials" / "shared" / "erp_mobile_queue_card_v2.html"
    ).read_text(encoding="utf-8")
    assert "and quest.approve_label" in card
    assert "quest_inline_approve = quest_actionable and quest.advances_stage" in card
    assert "confirm_actionable" not in card
    assert "erp-queue-card__confirm-open" not in card
    assert "quest.is_done" in card
    assert "erp-queue-card__quest-done" in card


def test_resolve_synthesizes_open_when_only_stale_measure_completed_on_confirm() -> None:
    """CONFIRM 단계에 옛 MEASURE COMPLETED 만 있으면 합성 OPEN quest(is_done 없음)."""
    sd = {
        "workflow": {"stage": "CONFIRM"},
        "quests": [{
            "stage": "실측", "title": "실측", "status": "COMPLETED",
            "approval_mode": "assignee", "assignee_approval": {"approved": True},
        }],
    }
    quest = qd.resolve_current_quest(sd, "고객컨펌", "CONFIRM")
    assert quest is not None
    assert quest.get("status") == "OPEN"
    assert not quest.get("is_done")


def test_resolve_returns_completed_confirm_quest_as_done() -> None:
    """CONFIRM COMPLETED 만 있으면 그 quest 를 is_done=True 얕은 복사로 돌려준다(원본 무변경)."""
    done_quest = {
        "stage": "고객컨펌", "title": "고객 컨펌", "status": "COMPLETED",
        "approval_mode": "assignee", "assignee_approval": {"approved": True},
        "completed_at": "2026-09-16T10:00:00",
    }
    sd = {"workflow": {"stage": "CONFIRM"}, "quests": [done_quest]}
    quest = qd.resolve_current_quest(sd, "고객컨펌", "CONFIRM")
    assert quest is not None
    assert quest["is_done"] is True
    assert quest["title"] == "고객 컨펌"
    assert "is_done" not in done_quest, "원본 sd dict 를 건드리면 안 된다"


def test_resolve_prefers_open_over_completed_on_same_stage() -> None:
    """같은 단계에 OPEN 과 COMPLETED 가 같이 있으면 OPEN(활성)이 이긴다."""
    sd = {
        "workflow": {"stage": "CONFIRM"},
        "quests": [
            {"stage": "CONFIRM", "title": "옛 컨펌", "status": "COMPLETED",
             "completed_at": "2026-09-16T10:00:00"},
            {"stage": "고객컨펌", "title": "새 컨펌", "status": "OPEN", "approval_mode": "assignee"},
        ],
    }
    quest = qd.resolve_current_quest(sd, "고객컨펌", "CONFIRM")
    assert quest is not None
    assert quest.get("status") == "OPEN"
    assert not quest.get("is_done")


def test_build_payload_exposes_is_done_and_done_label() -> None:
    """payload 에 is_done·done_label 키가 실려 세 표면(큐 카드·모바일 상세·PC 그리드)이 같은 답을 본다."""
    sd = {
        "workflow": {"stage": "CONFIRM"},
        "quests": [{
            "stage": "고객컨펌", "title": "고객 컨펌", "status": "COMPLETED",
            "approval_mode": "assignee", "assignee_approval": {"approved": True},
        }],
    }
    order = SimpleNamespace(id=5193, customer_name="이다은", manager_name="이다은담당")
    payload = qd.build_current_quest_payload(
        sd=sd, stage="고객컨펌", stage_code="CONFIRM", order=order, current_user=None, user_map={}
    )
    assert payload is not None
    assert payload["is_done"] is True
    assert payload["done_label"] == "고객 컨펌 완료"
    assert payload["all_approved"] is True
    # current_user 없이 만든 payload 는 재전이 버튼을 내밀지 않는다(권한 주체가 없다).
    assert payload["can_retransition"] is False
    assert payload["retransition_label"] == "생산 단계로 넘기기"

    open_payload = _payload_for_stage("고객컨펌", "CONFIRM")
    assert open_payload["is_done"] is False
    assert open_payload["done_label"] == "고객 컨펌 완료"


def test_list_approve_restores_place_instead_of_removing_the_card() -> None:
    """목록 승인은 카드를 지우지 않는다 — 승인해도 그 주문은 목록에서 빠지지 않기 때문이다.

    실측 큐는 실측일 기준이라 승인 뒤에도 '실측 완료' 배지를 달고 남고, 메인 대시보드는
    단계별 섹션이라 다음 단계 섹션으로 옮겨 갈 뿐이다. 카드를 지우면 '사라졌다'는 거짓이 된다.
    대신 스크롤 자리를 기억했다가 다시 읽은 뒤 그 카드로 돌아가 잠깐 강조한다.
    """
    js = (ROOT / "static" / "js" / "foms" / "erp-quest-approve.js").read_text(
        encoding="utf-8"
    )
    assert "rememberPlace" in js
    assert "restorePlace" in js
    assert "is-foms-just-approved" in js
    # 카드를 DOM 에서 제거하는 경로가 없어야 한다(회귀 가드).
    assert ".remove()" not in js
    # 강조 스타일과 자산 핀이 함께 있어야 실기기에서 구버전 CSS 가 남지 않는다.
    css = (ROOT / "static" / "css" / "components" / "foms-queue-card-v2.css").read_text(
        encoding="utf-8"
    )
    assert ".foms-queue-card-v2.is-foms-just-approved" in css
    surfaces = (
        ROOT / "static" / "css" / "foundation" / "foms-mobile-surfaces.css"
    ).read_text(encoding="utf-8")
    assert "foms-queue-card-v2.css?v=20260910a" in surfaces


def test_manager_name_fallback_does_not_beat_the_team_gate() -> None:
    """음성 대조군 — 담당자 이름이 같아도 승인 팀이 아니면 화면도 버튼을 안 준다.

    서버는 팀으로만 판정한다(`_authorize_quest_approve`). 이름 일치 폴백이 그 위를
    덮으면 화면이 "누를 수 있다"고 말한 버튼을 서버가 403 으로 거부한다.
    """
    sd = {
        "workflow": {"stage": "MEASURE"},
        "parties": {"manager": {"name": "Manager Kim"}},
        "quests": [{
            "stage": "실측", "title": "실측", "status": "OPEN",
            "approval_mode": "assignee", "assignee_approval": {"approved": False},
        }],
    }
    user = SimpleNamespace(id=9, name="Manager Kim", username="mkim",
                           role="STAFF", team="CONSTRUCTION")
    order = SimpleNamespace(id=1, manager_name="Manager Kim", structured_data=sd)
    payload = qd.build_current_quest_payload(
        sd=sd, stage="실측", stage_code="MEASURE", order=order,
        current_user=user, user_map={},
    )
    assert payload is not None
    assert payload["can_assignee_approve"] is False
