"""AI 직원 수준 표 고치기(설계서 2026-11-14-foms-graft 3.10 · D214) — ADMIN 만 · 상한 · 3 · 모르는 이름 거절 · 감사 줄.

완료 기준: 처음 값(표 없음 = 판 0 · 운영 AI 단계 넘기기 0) · 바꿀 수 있는 칸은 제안하는 할 일뿐 · 저장하면 그 칸만 바뀌고 판이
오르고 감사 한 줄(열쇠와 앞뒤 수만) · 같은 값은 감사 없음 · ADMIN 이 아니면 거절 · 꼴이 하나라도 틀리면 통째로 거절(표 그대로).
합성 계정만. 바깥 호출 없음.
"""

from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.ai_staff import registry
from foms.services.ai_staff.levels import AUDIT_LEVELS_SAVED, LevelError, levels_view, save_levels
from models import SecurityLog, SystemSetting, User


def _user(name: str, role: str, team=None, active=True) -> User:
    user = User(username=name, password=generate_password_hash("pw"), role=role, team=team, name=f"{name}-이름",
                is_active=active)
    db_session.add(user)
    db_session.commit()
    return user


def _row(view, agent, action):
    return next(item for item in view["agents"][agent] if item["action"] == action)


def test_first_values_without_a_table(app):
    view = levels_view(db_session)
    assert view["version"] == 0
    stage = _row(view, "ops", "advance_stage")  # D214 — 단계 넘기기 규칙은 처음 수준 0
    assert stage["level"] == 0 and stage["editable"] is True
    assert [c["value"] for c in stage["choices"]] == [0, 1, 2]  # 할 일 상한 2(T14 — run)
    assert [c["value"] for c in _row(view, "schedule", "schedule_construction")["choices"]] == [0, 1, 2]
    draft = _row(view, "cs", "cs_draft")
    assert draft["editable"] is False and draft["choices"] == []  # 직원만의 일은 표로 바꾸지 않는다
    never = _row(view, "cs", "send_measure_alimtalk")
    assert never["level"] is None and never["level_label"] == "못 함" and never["editable"] is False
    assert registry.level_of(db_session, "ops", "advance_stage") == 0


def test_admin_saves_one_cell_and_leaves_an_audit_line(app):
    admin = _user("lv_admin", "ADMIN")
    view = save_levels(db_session, admin, {"levels": {"ops": {"advance_stage": 1}}})
    db_session.commit()
    assert _row(view, "ops", "advance_stage")["level"] == 1 and view["version"] >= 1
    assert registry.level_of(db_session, "ops", "advance_stage") == 1
    assert registry.level_of(db_session, "ops", "send_measure_alimtalk") == 1  # 다른 칸은 처음 값 그대로
    logs = db_session.query(SecurityLog).filter(SecurityLog.action == AUDIT_LEVELS_SAVED).all()
    assert len(logs) == 1 and logs[0].user_id == admin.id
    assert logs[0].detail == {"changes": {"ops.advance_stage": [0, 1]}}

    first_version = levels_view(db_session)["version"]
    save_levels(db_session, admin, {"levels": {"ops": {"advance_stage": 1}}})  # 같은 값 — 감사 · 판 그대로
    db_session.commit()
    assert db_session.query(SecurityLog).filter(SecurityLog.action == AUDIT_LEVELS_SAVED).count() == 1
    assert levels_view(db_session)["version"] == first_version

    save_levels(db_session, admin, {"levels": {"schedule": {"schedule_construction": 0}}})
    db_session.commit()
    assert registry.level_of(db_session, "schedule", "schedule_construction") == 0
    assert registry.level_of(db_session, "ops", "advance_stage") == 1  # 앞에 저장한 칸이 남는다


@pytest.mark.parametrize("who", ["manager", "staff", "off_admin", "nobody"])
def test_only_an_active_admin_can_save(app, who):
    users = {"manager": lambda: _user("lv_mgr", "MANAGER", "CS"), "staff": lambda: _user("lv_staff", "STAFF", "CS"),
             "off_admin": lambda: _user("lv_off", "ADMIN", active=False), "nobody": lambda: None}
    with pytest.raises(LevelError) as caught:
        save_levels(db_session, users[who](), {"levels": {"ops": {"advance_stage": 1}}})
    assert caught.value.code == "LEVEL_FORBIDDEN"
    db_session.rollback()
    assert db_session.get(SystemSetting, registry.SETTINGS_KEY) is None


@pytest.mark.parametrize("body,field", [
    ({"levels": {"ops": {"advance_stage": 3}}}, "ops.advance_stage"),  # 3 은 없다
    ({"levels": {"ops": {"send_measure_alimtalk": 2}}}, "ops.send_measure_alimtalk"),  # 상한 1 넘음
    ({"levels": {"schedule": {"schedule_construction": 3}}}, "schedule.schedule_construction"),
    ({"levels": {"ops": {"advance_stage": True}}}, "ops.advance_stage"),
    ({"levels": {"ops": {"advance_stage": "1"}}}, "ops.advance_stage"),
    ({"levels": {"ops": {"advance_stage": -1}}}, "ops.advance_stage"),
    ({"levels": {"nope": {"advance_stage": 1}}}, "nope"),
    ({"levels": {"ops": {"nope": 1}}}, "ops.nope"),
    ({"levels": {"cs": {"cs_draft": 0}}}, "cs.cs_draft"),  # 직원만의 일
    ({"levels": {"cs": {"send_measure_alimtalk": 1}}}, "cs.send_measure_alimtalk"),  # 못 함
    ({"levels": {"ops": {"schedule_construction": 1}}}, "ops.schedule_construction"),  # 그 직원에게 없는 할 일
    ({"levels": {}}, "levels"), ({}, "levels"), ({"levels": [1]}, "levels"),
])
def test_bad_shapes_are_rejected_whole(app, body, field):
    admin = _user("lv_admin2", "ADMIN")
    if "levels" in body and isinstance(body["levels"], dict) and body["levels"]:
        body = {"levels": {**body["levels"], "schedule": {"schedule_construction": 1}}} if "schedule" not in body[
            "levels"] else body  # 바른 칸이 섞여 있어도 통째로 거절
    with pytest.raises(LevelError) as caught:
        save_levels(db_session, admin, body)
    assert caught.value.code == "LEVEL_SHAPE" and field in caught.value.fields
    assert caught.value.message and "3" not in caught.value.message
    db_session.rollback()
    assert db_session.get(SystemSetting, registry.SETTINGS_KEY) is None
    assert db_session.query(SecurityLog).filter(SecurityLog.action == AUDIT_LEVELS_SAVED).count() == 0
