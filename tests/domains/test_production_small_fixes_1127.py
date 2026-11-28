"""생산 화면 작은 고침 셋(사장님 2026-11-27) — 파트 계정 판의 내 작업 맨 앞 · 낱말("재단 작업 중" · "미정") · 글("생산 파트 작업" · "보류 중인 주문이에요.")."""
from __future__ import annotations

import re

from db import db_session

from foms.services.audit_message_display import action_label
from foms.services.production.pc_sheet import state_word
from foms.services.production_home_read_model import production_home_stage, production_home_steps
from tests.domains.test_production_selfclaim_screens import HOME, _get, _login, _mark, _order, _user, cohort  # noqa: F401
from tests.domains.test_production_transition_guard_api import _login as _guard_login
from tests.domains.test_production_transition_guard_api import _make_order_with_hold, _make_user


def _keys(html: str, name: str) -> list[str]:
    return re.findall(rf'data-pp-card[^>]*data-key="{name}/d(\d)\.png"', html)


def test_파트_계정_판은_내_작업을_빼고_반장_판은_그대로(client, cohort) -> None:
    me, park = _user("김민준", "cut"), _user("박재단", "cut")
    order = _order("새집", 5)
    _mark(order, 2, "cut", "NEED", me)  # 내 작업
    _mark(order, 3, "cut", "NEED", park)  # 남의 작업
    _mark(order, 4, "cut", "DONE", me)  # 완료
    _login(client, me)
    # 내 작업(2)은 판 밖 '내 공정' 탭(2026-11-28 흐름 — 11-27 '맨 앞'을 대신함) → 미정 → 남의 작업 → 완료
    assert _keys(_get(client, HOME), "새집") == ["0", "1", "3", "4"]
    boss = _user("박반장")
    boss.production_lead = True
    db_session.commit()
    _login(client, boss)
    assert _keys(_get(client, f"{HOME}?tab=parts&part=cut"), "새집") == ["0", "1", "2", "3", "4"]  # 반장 판: 미정 → 담당(번호 순) → 완료, 내 작업 앞세우기 없음


def test_단계_글은_재단_작업_중_PC_창_상태는_미정() -> None:
    steps = production_home_steps({"production": {"steps": []}}, mark_now=True)
    assert production_home_stage("PRODUCTION", True, steps, False)[0] == "재단 작업 중"
    assert production_home_stage("PRODUCTION", False, steps, False)[0] == "제작 대기"
    for part in ("cut", "edge", "assemble", "inspect"):
        assert state_word(part, "none", None) == "미정"


def test_기록_머리말은_생산_파트_작업() -> None:
    assert action_label("PRODUCTION_PART_MARKED") == "생산 파트 작업"


def test_보류_주문_거절_글은_이에요(client) -> None:
    _guard_login(client, _make_user("small1127_h"))
    order_id = _make_order_with_hold("CONFIRM").id
    resp = client.post(f"/api/orders/{order_id}/production/start", json={})
    assert resp.status_code == 409
    data = resp.get_json()
    assert data["code"] == "HOLD_ACTIVE" and data["message"].startswith("보류 중인 주문이에요.")
