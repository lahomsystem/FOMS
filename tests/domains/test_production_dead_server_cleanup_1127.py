"""생산 쪽 안 타는 서버 길 지움(설계서 2026-11-27-production-legacy-board-removal §6-3 · 원장 2026-11-09 "뒤에 할 것").

지운 것 · 남는 것:

* ``GET /api/orders/<id>/production/steps``(공정 읽기) — 부르던 화면(옛 생산 보드 · 옛 옆 시트)이 없다. 같은 주소의 쓰기(POST)는 그대로
  (내 공정 [완료] · 작업 시트 · PC 창이 부른다).
* 공정 칸 POST 의 '막힌 도면만 빼고 풀어 쓰기' 갈래(응답 ``expanded``) — 도면이 1장이라도 있으면 그 앞 문(409 ``STEP_PER_SHEET``)이
  먼저 막아 닿는 주문이 없었다. 풀어 쓰기 함수 :func:`expand_hand_step`(도면 고쳐 보냄 길 ②)은 남는다.
* '내 공정' 줄의 ``step_confirm``(누르기 전 확인 창 자료) — 도면 있는 줄은 [끝]을 그리는 사람에게 늘 ``step_block`` 이 먼저였다.
* ``build_production_enriched_rows``(옛 보드 행) — 시험만 불렀다. 행 변환은 첫 화면 함수가 그대로 쓴다.

되돌리면 실패: GET 이 다시 200 · POST 가 사라짐 · 지운 이름이 다시 생김 · 도면 있는 줄에 ``step_confirm`` 이 실림.
대조군: 같은 주소 POST 는 도면 0장 주문에서 200(응답에 ``expanded`` 없음), 도면 있는 주문 켜기는 지금처럼 409.
이름 · 번호는 지어낸 값이다.
"""
from __future__ import annotations

import pytest

from foms.services import production_dashboard_display as display
from foms.services.production import step_expand
from foms.services.production.home_step_panel import attach_step_confirm
from foms.services.production.part_mark_gates import STEP_PER_SHEET
from foms.services.production.part_progress import WHOLE_STEP_MAX_SHEETS
from tests.support.production_part_claim_seed import check_step, code, fresh, login, make_order, make_user

STEPS = "/api/orders/{}/production/steps"


def _steps_rules(app) -> list:
    return [rule for rule in app.url_map.iter_rules() if rule.rule == "/api/orders/<int:order_id>/production/steps"]


def test_steps_read_route_is_gone_and_only_the_write_route_is_left(app):
    rules = _steps_rules(app)
    assert [rule.endpoint for rule in rules] == ["erp_orders_production.api_production_steps"]
    assert rules[0].methods - {"HEAD", "OPTIONS"} == {"POST"}
    assert "erp_orders_production.api_production_steps_get" not in app.view_functions


@pytest.mark.parametrize("who", ["lead", "admin"])
def test_get_on_the_steps_address_now_answers_405_without_any_step_data(client, who):
    seed = make_order(2)
    login(client, make_user("가짜반장", lead=True) if who == "lead" else make_user("가짜관리", role="ADMIN", team="CS"))
    for order_id in (seed.id, 999999):  # 있는 주문 · 없는 주문 모두 길이 없다(404 '주문 없음' 이 아니라 405)
        resp = client.get(STEPS.format(order_id))
        assert resp.status_code == 405, resp.status_code
        body = resp.get_json(silent=True) or {}
        assert "steps" not in (body.get("data") or {}) and body.get("success") is not True


def test_control_post_on_the_same_address_still_writes(client):
    """대조군: 도면 0장 주문은 지금처럼 켜지고(응답에 풀어 쓰기 칸 없음), 도면 있는 주문 켜기는 지금처럼 409 STEP_PER_SHEET."""
    login(client, make_user("가짜반장", lead=True))
    plain = make_order(0)
    before = fresh(plain.id).mutation_version
    res = check_step(client, plain.id, "cut", True)
    assert res.status_code == 200, res.get_json()
    data = res.get_json()["data"]
    assert "expanded" not in data and [s["key"] for s in data["steps"] if s["done"]] == ["cut"]
    assert fresh(plain.id).mutation_version == before + 1
    drawn = make_order(1)
    assert code(check_step(client, drawn.id, "cut", True)) == STEP_PER_SHEET


def test_expand_path_is_unreachable_because_any_drawing_blocks_turning_on():
    """풀어 쓰기 갈래를 지운 전제 — 도면이 1장이라도 있으면 켜기가 막힌다(문턱 0장). 이 값이 다시 오르면 막힌 도면 빼기를 새로 짜야 한다."""
    assert WHOLE_STEP_MAX_SHEETS == 0


def test_removed_names_are_gone_and_the_live_ones_stay():
    for name in ("step_expand_plan", "apply_step_expand", "with_written_marks", "_check_inspect_ready"):
        assert not hasattr(step_expand, name), name
    assert callable(step_expand.expand_hand_step)  # 도면 고쳐 보냄 길(②)이 부른다
    assert not hasattr(display, "build_production_enriched_rows")
    assert callable(display.build_production_home_enriched_rows)


@pytest.mark.parametrize("confirm", [True, False])
def test_drawn_row_never_carries_the_old_confirm_data(app, confirm):
    seed = make_order(1)
    row = {"id": seed.id, "structured_data": fresh(seed.id).structured_data, "hold_active": False, "revise_block": None}
    queues = {"queues": [{"key": "cut", "rows": [row]}]}
    attach_step_confirm(queues, {seed.id: []}, confirm=confirm)
    assert "step_confirm" not in row
    if confirm:  # [끝]을 그리는 사람 — 도면 있는 줄은 [끝] 대신 남은 장(공정 API 409 와 같은 판정)
        assert row["step_block"]["code"] == STEP_PER_SHEET and row["step_block"]["text"] == "재단 0/1 · 1장 미완료"
    else:
        assert "step_block" not in row
