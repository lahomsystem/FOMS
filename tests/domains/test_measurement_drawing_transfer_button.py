"""STATE-CONTROLS-04 — 실측 대시보드 '도면 전달' 버튼 계약.

이 버튼은 본공정 stage 를 MEASURE → DRAWING 으로 옮긴다(기존
``POST /api/orders/<id>/quest/approve`` 재사용, 새 API 없음). 식별자는 전부
``drawing_transfer`` 축이며, ``foms/api/drawing/erp_orders_drawing.py`` 의 도면 **파일**
전달(``drawing_status`` 축, stage 를 바꾸지 않는다)과 절대 섞지 않는다.

고정하는 계약:

* T1  권한 술어 추출 뒤에도 ``foms.api.quest`` 의 옛 이름이 같은 객체를 가리킨다.
* T2  추출이 순수 리팩터다(권한 진리표 무변경).
* T3  CTA ``visible`` 게이트(양성 1 + 음성 5 + 한글 stage 정규화).
* T4  CTA ``enabled`` 가 서버 판정과 **같은 답**을 낸다(음성 대조군 포함).
* T5  팀 승인 방식 레거시 quest 는 노출하되 비활성(거짓말 방지).
* T6  role 축(ADMIN/MANAGER/STAFF 만 노출).
* T7  주문 수가 늘어도 추가 쿼리 0회.
* T8  매크로 출력 문자열.
* T9  템플릿 배선(호출 수·import·JS/CSS 핀·기존 컨트롤 회귀).
* T10 두 대시보드 라우트 end-to-end 렌더.
* T11 API 왕복 — 화면이 비활성으로 그린 것 = 서버가 거부하는 것.
* T12 이름 축 분리(JS·서비스가 drawing_status 축을 건드리지 않는다).
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

ASSET_PIN = "?v=20260914a"


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


# --------------------------------------------------------------------------- #
# T8 매크로 출력 문자열.
# --------------------------------------------------------------------------- #
def _render_transfer_control(cta) -> str:
    import app as app_module

    tmpl = app_module.app.jinja_env.get_template("partials/shared/status_select_options.html")
    return str(tmpl.module.drawing_transfer_control(4552, cta))


def _cta_dict(**overrides) -> dict:
    base = {
        "visible": True,
        "enabled": True,
        "label": "도면 전달",
        "confirm": "실측을 완료하고 도면 단계로 넘길까요?",
        "blocked_reason": "",
    }
    base.update(overrides)
    return base


def test_macro_renders_nothing_without_cta() -> None:
    assert _render_transfer_control(None).strip() == ""


def test_macro_renders_nothing_when_hidden() -> None:
    hidden = _cta_dict(visible=False, enabled=False, label="", confirm="")
    assert _render_transfer_control(hidden).strip() == ""


def test_macro_renders_enabled_button() -> None:
    html = _render_transfer_control(_cta_dict())

    assert "js-drawing-transfer" in html
    assert "btn btn-sm btn-outline-primary" in html
    assert 'data-order-id="4552"' in html
    assert "data-confirm=" in html
    assert "도면 전달" in html
    assert "disabled" not in html
    assert "<div" not in html, "버튼 하나뿐 — 새 div 래퍼는 버킷 정규식을 깬다"


def test_macro_button_is_visually_distinct_from_drawing_file_viewer() -> None:
    """같은 행의 도면 **파일** 뷰어 버튼과 눈으로 갈려야 한다(오클릭 = stage 전이).

    뷰어는 ``btn-outline-info`` + ``fa-drafting-compass`` 다. 이 버튼은 둘 다 쓰지 않는다.
    """
    html = _render_transfer_control(_cta_dict())

    assert "btn-outline-info" not in html, "도면 파일 뷰어와 같은 톤이다"
    assert "fa-drafting-compass" not in html, "도면 파일 뷰어와 같은 아이콘이다"
    assert "fa-arrow-right" in html, "단계 이동을 뜻하는 아이콘이어야 한다"

    # 색은 CSS 가 못박는다(인라인 스타일 금지).
    css = (STATIC / "css/measurement/complete-order-btn.css").read_text(encoding="utf-8")
    assert ".js-drawing-transfer.btn" in css
    assert "#3949ab" in css, "전용 색이 CSS 에 없다"
    assert "style=" not in html, "인라인 스타일 금지"


def test_transfer_button_margin_matches_status_stack_gap() -> None:
    """.foms-board-status-stack 은 gap 4px 를 준다 — 그 안에서는 margin-top 을 겹치지 않는다."""
    css = (STATIC / "css/measurement/complete-order-btn.css").read_text(encoding="utf-8")

    block = re.search(
        r"\.foms-board-status-stack \.js-drawing-transfer\.btn\s*\{[^}]*\}", css
    )
    assert block, "스택 안 margin 상쇄 규칙이 없다"
    assert re.search(r"margin-top:\s*0", block.group(0)), block.group(0)


def test_macro_renders_disabled_button_with_reason() -> None:
    html = _render_transfer_control(_cta_dict(enabled=False, blocked_reason="권한 없음"))

    assert "disabled" in html
    assert 'title="권한 없음"' in html
    assert "js-drawing-transfer" in html


def test_macro_escapes_confirm_attribute() -> None:
    """confirm 에 큰따옴표가 들어가도 속성이 깨지거나 스크립트가 새지 않는다."""
    html = _render_transfer_control(_cta_dict(confirm='"><script>alert(1)</script>'))

    assert "<script>" not in html
    assert "&#34;" in html or "&quot;" in html


# --------------------------------------------------------------------------- #
# T9 템플릿 배선.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "path,expected_sites",
    [(SELF_TEMPLATE, 2), (REGIONAL_TEMPLATE, 3)],
)
def test_templates_wire_drawing_transfer_control(path: Path, expected_sites: int) -> None:
    src = path.read_text(encoding="utf-8")

    sites = src.count("drawing_transfer_control(order.id")
    assert sites == expected_sites, f"{path.name}: 호출 {sites} != {expected_sites}"

    import_lines = [
        line
        for line in src.splitlines()
        if "status_select_options.html' import" in line
    ]
    assert import_lines, f"{path.name}: 공용 매크로 import 줄이 없다"
    assert any("drawing_transfer_control" in line for line in import_lines), (
        f"{path.name}: import 줄에 drawing_transfer_control 이 없다"
    )


@pytest.mark.parametrize("path", [SELF_TEMPLATE, REGIONAL_TEMPLATE])
def test_templates_pin_transfer_assets(path: Path) -> None:
    src = path.read_text(encoding="utf-8")
    lines = src.splitlines()

    js_lines = [line for line in lines if "drawing-transfer-btn.js" in line]
    assert len(js_lines) == 1, f"{path.name}: 새 JS script 태그 {len(js_lines)}개"
    assert ASSET_PIN in js_lines[0], f"{path.name}: 새 JS 핀이 {ASSET_PIN} 가 아니다"

    css_lines = [line for line in lines if "complete-order-btn.css" in line]
    assert len(css_lines) == 1, f"{path.name}: CSS 링크 {len(css_lines)}개"
    assert ASSET_PIN in css_lines[0], f"{path.name}: CSS 핀이 {ASSET_PIN} 가 아니다"

    # 기존 complete-order-btn.js 핀은 건드리지 않는다.
    assert "complete-order-btn.js') }}?v=20260807b" in src


@pytest.mark.parametrize("path", [SELF_TEMPLATE, REGIONAL_TEMPLATE])
def test_complete_order_control_site_count_unchanged(path: Path) -> None:
    """STATE-CONTROLS-02 회귀 가드 — 완료 버튼은 여전히 1곳뿐이다."""
    src = path.read_text(encoding="utf-8")
    assert src.count("complete_order_control(order.id") == 1


def test_regional_template_has_no_status_select() -> None:
    """지방 보드 행에는 status 드롭다운이 없다(2026-08-07 개편 계약)."""
    src = REGIONAL_TEMPLATE.read_text(encoding="utf-8")
    for match in re.finditer(r"<select[^>]*>", src):
        assert 'data-field="status"' not in match.group(0), match.group(0)


# --------------------------------------------------------------------------- #
# T10 라우트 end-to-end 렌더.
# --------------------------------------------------------------------------- #
def _button_for(html: str, order_id: int) -> bool:
    """해당 주문 id 를 단 도면 전달 버튼이 렌더됐는지."""
    for match in re.finditer(r"<button[^>]*js-drawing-transfer[^>]*>", html):
        if f'data-order-id="{order_id}"' in match.group(0):
            return True
    return False


def test_self_dashboard_renders_transfer_button(client) -> None:
    user = _make_user(role="STAFF", team="SALES", username="self-board-staff")
    _login(client, user)
    order = _create_order(
        quests=[_measure_assignee_quest()],
        status="MEASURE",           # pending 버킷
        is_self_measurement=True,
    )

    resp = client.get("/self_measurement_dashboard")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert _button_for(body, order.id), "자가실측 pending 행에 도면 전달 버튼이 없다"

    order_id = order.id
    _set_stage(order_id, "PRODUCTION")
    body2 = client.get("/self_measurement_dashboard").get_data(as_text=True)
    assert not _button_for(body2, order_id), "PRODUCTION 인데 버튼이 남아 있다"


def test_regional_dashboard_renders_transfer_button(client) -> None:
    user = _make_user(role="STAFF", team="SALES", username="regional-board-staff")
    _login(client, user)
    order = _create_order(
        quests=[_measure_assignee_quest()],
        status="MEASURE",           # 진행 중 버킷(상차일 없음)
        is_regional=True,
        measurement_completed=True,
    )

    resp = client.get("/regional_dashboard")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert _button_for(body, order.id), "지방 진행 중 행에 도면 전달 버튼이 없다"

    order_id = order.id
    _set_stage(order_id, "PRODUCTION")
    body2 = client.get("/regional_dashboard").get_data(as_text=True)
    assert not _button_for(body2, order_id), "PRODUCTION 인데 버튼이 남아 있다"


def test_shipping_alert_card_div_depth_unchanged(client) -> None:
    """버튼 때문에 상차 예정 알림 카드의 div 층이 늘면 버킷 테스트가 깨진다.

    test_regional_dashboard_buckets.py:90-95 와 **같은 정규식**으로 카드를 잘라
    order id 가 여전히 잡히는지로 확인한다.
    """
    from datetime import timedelta

    from foms.services.erp_display import get_today_kst

    user = _make_user(role="STAFF", team="SALES", username="regional-alert-staff")
    _login(client, user)
    future = (get_today_kst() + timedelta(days=3)).strftime("%Y-%m-%d")
    order = _create_order(
        quests=[_measure_assignee_quest()],
        status="MEASURE",
        is_regional=True,
        measurement_completed=True,
        shipping_scheduled_date=future,
    )

    body = client.get("/regional_dashboard").get_data(as_text=True)
    match = re.search(
        r'<div class="card shadow shipping-alert-card".*?</div>\s*</div>\s*</div>',
        body,
        re.S,
    )
    assert match, "상차 예정 알림 카드를 정규식으로 잘라내지 못했다"
    assert str(order.id) in set(re.findall(r'data-order-id="(\d+)"', match.group(0)))


# --------------------------------------------------------------------------- #
# T11 API 왕복 — 화면 판정 = 서버 판정.
# --------------------------------------------------------------------------- #
def test_disabled_user_is_rejected_and_enabled_user_transitions(client) -> None:
    order = _create_order(
        quests=[_measure_assignee_quest()],
        status="MEASURE",
        is_self_measurement=True,
    )
    order_id = order.id

    denied_user = _make_user(role="STAFF", team="PRODUCTION", username="transfer-denied")
    allowed_user = _make_user(role="STAFF", team="SALES", username="transfer-allowed")

    assert _cta(order, denied_user)["enabled"] is False
    assert _cta(order, allowed_user)["enabled"] is True

    # (b) 화면이 비활성으로 그린 사용자는 서버가 실제로 거부한다.
    _login(client, denied_user)
    denied = client.post(f"/api/orders/{order.id}/quest/approve", json={})
    assert denied.status_code == 403, denied.get_data(as_text=True)

    db_session.expire_all()
    assert read_main_stage(db_session.query(Order).filter(Order.id == order_id).one()) == "MEASURE"

    # (a) 활성으로 그린 사용자는 실제로 도면 단계로 넘어간다.
    _login(client, allowed_user)
    ok = client.post(f"/api/orders/{order.id}/quest/approve", json={})
    assert ok.status_code == 200, ok.get_data(as_text=True)
    data = ok.get_json()
    assert data["success"] is True
    assert data["auto_transitioned"] is True

    db_session.expire_all()
    moved = db_session.query(Order).filter(Order.id == order_id).one()
    assert read_main_stage(moved) == "DRAWING"

    # 전이 뒤에는 버튼이 사라진다(DRAWING 은 command-required).
    assert _cta(moved, allowed_user)["visible"] is False


# --------------------------------------------------------------------------- #
# T12 이름 축 분리 — drawing_status 축을 건드리지 않는다.
# --------------------------------------------------------------------------- #
def _js_code_only(src: str) -> str:
    """주석을 걷어낸 JS 본문. 축 구분을 설명하는 주석까지 금칙어로 잡지 않기 위해서다."""
    without_blocks = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    kept = [
        line
        for line in without_blocks.splitlines()
        if not line.strip().startswith("//")
    ]
    return "\n".join(re.sub(r"//.*$", "", line) for line in kept)


def _python_code_only(src: str) -> str:
    """주석과 docstring 을 걷어낸 파이썬 본문(문자열 리터럴은 남긴다)."""
    import io
    import tokenize

    pieces: list[str] = []
    prev_type = tokenize.INDENT
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            continue
        if tok.type == tokenize.STRING and prev_type in (
            tokenize.INDENT,
            tokenize.DEDENT,
            tokenize.NEWLINE,
            tokenize.NL,
            tokenize.ENCODING,
        ):
            # 논리 행 첫 토큰인 문자열 = docstring.
            prev_type = tok.type
            continue
        if tok.type not in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT):
            pieces.append(tok.string)
        prev_type = tok.type
    return "\n".join(pieces)


def test_transfer_js_calls_quest_approve_only() -> None:
    src = TRANSFER_JS.read_text(encoding="utf-8")
    code = _js_code_only(src)

    assert "'/api/orders/' + orderId + '/quest/approve'" in src
    assert "__FOMS_DRAWING_TRANSFER_BTN_BOUND" in src
    assert "drawing_status" not in code, "도면 파일 전달(drawing_status) 축과 섞였다"
    assert "emergency_override" not in code
    assert "override_reason" not in code
    assert "jQuery" not in code
    assert "$(" not in code


def test_transfer_js_guards_non_json_response() -> None:
    """세션 만료 시 role_required 는 로그인 페이지로 redirect 한다 — HTML 을 json() 하면
    사용자에게 "Unexpected token '<'" 가 뜬다. 파싱을 감싸고 한글 문장으로 바꾼다."""
    code = _js_code_only(TRANSFER_JS.read_text(encoding="utf-8"))

    assert "res.json()" in code
    assert re.search(r"try\s*\{\s*data\s*=\s*await\s+res\.json\(\)", code), (
        "res.json() 이 try 로 감싸여 있지 않다"
    )
    assert "res.redirected" in code
    assert "로그인이 만료되었습니다" in code
    assert "HTTP " in code, "상태코드를 사람이 볼 수 있게 남겨야 한다"


def test_cta_service_does_not_touch_drawing_status_axis() -> None:
    code = _python_code_only(CTA_SERVICE.read_text(encoding="utf-8"))

    assert "drawing_status" not in code
    assert "erp_orders_drawing" not in code
