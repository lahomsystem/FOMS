"""모바일 홈 달력 — 시공 금액별 칸 색 기준(회사 공통, 관리자·팀장 수정) 계약 테스트.

근거: docs/specs/2026-10-14-mobile-calendar-amount-colors_SPEC.md
"""

import datetime
import uuid

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.orders import calendar_amount_colors as cc
from foms.services.orders import dashboard_control_tower as ct
from models import Order, SecurityLog, SystemSetting, User

PATH = "/erp/dashboard/calendar-colors"


@pytest.fixture(autouse=True)
def _clean_setting(app):
    db_session.query(SystemSetting).filter(SystemSetting.setting_key == cc.CALENDAR_COLORS_KEY).delete()
    db_session.commit()
    yield
    db_session.rollback()
    db_session.query(SystemSetting).filter(SystemSetting.setting_key == cc.CALENDAR_COLORS_KEY).delete()
    db_session.commit()


def _login(client, *, role: str) -> User:
    user = User(username=f"calcol_{role.lower()}_{uuid.uuid4().hex[:8]}",
                password=generate_password_hash("pw"), role=role, team="CS",
                name=f"{role} 사용자", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


# --------------------------------------------------------------------------- #
# 판정
# --------------------------------------------------------------------------- #

def test_tone_boundaries_follow_the_shown_man_amount():
    colors = {"enabled": True, "yellow_from": 2500, "pink_from": 3000}
    assert cc.tone_for(24_990_000, colors) == ""        # 2,499만
    assert cc.tone_for(24_996_000, colors) == "yellow"  # 칸에는 2,500만으로 보인다
    assert cc.tone_for(25_000_000, colors) == "yellow"
    assert cc.tone_for(30_000_000, colors) == "pink"    # 분홍 우선
    assert cc.tone_for(0, colors) == ""


def test_tone_off_or_single_step():
    assert cc.tone_for(40_000_000, {"enabled": False, "yellow_from": 2500, "pink_from": 3000}) == ""
    only_pink = {"enabled": True, "yellow_from": None, "pink_from": 3000}
    assert cc.tone_for(28_000_000, only_pink) == ""
    assert cc.tone_for(31_000_000, only_pink) == "pink"


def test_sanitize_rejects_bad_values():
    for bad in ({"yellow_from": "-1"}, {"yellow_from": "abc"}, {"yellow_from": 100_001},
                {"yellow_from": 3000, "pink_from": 3000}, {"yellow_from": True}, "x"):
        with pytest.raises(cc.CalendarColorsError):
            cc.sanitize_colors(bad)
    assert cc.sanitize_colors({"enabled": True, "yellow_from": "2,500", "pink_from": ""}) == {
        "enabled": True, "yellow_from": 2500, "pink_from": None,
    }


def test_defaults_until_someone_saves():
    assert cc.load_colors(db_session) == cc.DEFAULT_COLORS
    assert cc.colors_version(db_session) == 0


def test_calendar_cells_carry_tone(app):
    """달력 칸에 서버가 판정한 tone 이 실린다 — 화면이 금액 글자를 다시 읽지 않는다."""
    today = datetime.date(2026, 6, 10)
    for name, total in (("CLAUDE-TEST 색A", 26_000_000), ("CLAUDE-TEST 색B", 8_000_000)):
        db_session.add(Order(
            received_date=today.isoformat(), customer_name=name, phone="010-0000-0000",
            address="서울", product="붙박이장", status="CONSTRUCTION", erp_stage_code="CONSTRUCTION",
            is_erp_order=True,
            structured_data={"parties": {"customer": {"name": name}},
                             "schedule": {"construction": {"date": "2026-06-12"}},
                             "totals": {"items_total": total}},
        ))
    db_session.commit()

    base = ct._tower_base_query(db_session, None)
    cal = ct._month_calendar(base, today, today.replace(day=1), cc.load_colors(db_session))
    by_iso = {c["iso"]: c for w in cal["weeks"] for c in w}
    assert by_iso["2026-06-12"]["tone"] == "pink"   # 3,400만
    assert by_iso["2026-06-13"]["tone"] == ""
    assert cal["yellow_label"] == "2,500만" and cal["pink_label"] == "3,000만"


# --------------------------------------------------------------------------- #
# 저장 라우트
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("role", ["ADMIN", "MANAGER"])
def test_admin_and_manager_save_for_everyone(client, role):
    user_id = _login(client, role=role).id
    body = {"enabled": True, "yellow_from": 2000, "pink_from": 2800, "settings_version": 0}

    res = client.post(PATH, json=body)

    assert res.status_code == 200, res.get_data(as_text=True)
    assert res.get_json()["data"] == {
        "colors": {"enabled": True, "yellow_from": 2000, "pink_from": 2800}, "version": 1,
    }
    db_session.expire_all()
    assert cc.load_colors(db_session)["pink_from"] == 2800
    assert db_session.query(SecurityLog).filter(
        SecurityLog.user_id == user_id, SecurityLog.action == "MOBILE_CALENDAR_COLORS_SAVE").count() == 1


def test_staff_cannot_change_colors(client):
    _login(client, role="STAFF")

    res = client.post(PATH, json={"enabled": True, "yellow_from": 1, "pink_from": 2, "settings_version": 0})

    assert res.status_code in (302, 403)
    db_session.expire_all()
    assert cc.colors_version(db_session) == 0


def test_second_save_with_stale_version_is_refused(client):
    _login(client, role="ADMIN")
    client.post(PATH, json={"enabled": True, "yellow_from": 2000, "pink_from": 3000, "settings_version": 0})

    stale = client.post(PATH, json={"enabled": False, "yellow_from": 1000, "pink_from": 2000,
                                    "settings_version": 0})

    assert stale.status_code == 409
    assert stale.get_json()["data"]["version"] == 1


def test_bad_input_is_400_and_nothing_saved(client):
    _login(client, role="ADMIN")

    res = client.post(PATH, json={"enabled": True, "yellow_from": 3000, "pink_from": 2000,
                                  "settings_version": 0})

    assert res.status_code == 400
    assert "분홍" in res.get_json()["error"]
    db_session.expire_all()
    assert cc.colors_version(db_session) == 0


def test_get_returns_colors_and_version(client):
    _login(client, role="STAFF")

    data = client.get(PATH).get_json()["data"]

    assert data == {"colors": cc.DEFAULT_COLORS, "version": 0}


def test_gear_only_for_admin_and_manager(client):
    """톱니 버튼·설정 시트는 관리자·팀장 화면에만 그린다."""
    from flask import render_template

    cal = ct._month_calendar(ct._tower_base_query(db_session, None), datetime.date(2026, 10, 14),
                             datetime.date(2026, 10, 1), dict(cc.DEFAULT_COLORS))
    with client.application.test_request_context():
        shown = render_template("orders/partials/dashboard_mobile_tower_calendar.html",
                                cal=cal, calendar_colors_editable=True)
        hidden = render_template("orders/partials/dashboard_mobile_tower_calendar.html",
                                 cal=cal, calendar_colors_editable=False)
    assert "data-foms-colors-open" in shown
    assert "data-foms-colors-open" not in hidden
