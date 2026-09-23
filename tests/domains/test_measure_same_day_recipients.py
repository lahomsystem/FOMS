"""영업(SALES) 팀 알림 수신자 — legacy 표기 ``MEASURE`` 계정도 받는다.

권한 판정은 ``MEASURE`` 를 ``SALES`` 로 정규화한다(order_mutation_policy). 수신자 조회가
``team == 'SALES'`` 로만 찾으면 MEASURE 표기 영업이 당일 실측 긴급 알림을 조용히 못 받는다.
"""

from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.notifications.recipients import (
    expand_team_codes,
    fan_out_new_notification,
    resolve_recipients_for_notification,
)
from models import Notification, NotificationRecipientSource, User


def _user(username: str, team: str | None, *, active: bool = True) -> int:
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role="STAFF",
        team=team,
        name=username,
        is_active=active,
    )
    db_session.add(user)
    db_session.commit()
    return user.id


def _team_notification(team: str) -> Notification:
    notif = Notification(
        notification_type="MEASURE_SAME_DAY_ADDED",
        target_type="TEAM",
        target_team=team,
        title="t",
    )
    db_session.add(notif)
    db_session.flush()
    return notif


def test_expand_team_codes_reads_policy_normalization():
    assert expand_team_codes("SALES") == ("SALES", "MEASURE")
    assert expand_team_codes(" sales ") == ("SALES", "MEASURE")
    assert expand_team_codes("MEASURE") == ("SALES", "MEASURE")
    assert expand_team_codes("CS") == ("CS",)
    assert expand_team_codes("") == ()


def test_sales_team_includes_measure_alias_and_excludes_inactive(app):
    sales = _user("r_sales", "SALES")
    measure = _user("r_measure", "MEASURE")
    lower = _user("r_lower", "sales")
    inactive = _user("r_inactive", "SALES", active=False)
    cs = _user("r_cs", "CS")

    recipients = dict(resolve_recipients_for_notification(db_session, _team_notification("SALES")))
    assert set(recipients) == {sales, measure, lower}
    assert inactive not in recipients and cs not in recipients
    assert set(recipients.values()) == {NotificationRecipientSource.TARGET_TEAM}


def test_fan_out_creates_state_for_measure_alias(app):
    measure = _user("r_measure2", "MEASURE")
    notif = _team_notification("SALES")
    states = fan_out_new_notification(db_session, notif)
    assert {s.user_id for s in states} == {measure}


def test_other_teams_unchanged(app):
    """음성 대조군: 정규화 표에 없는 팀은 종전처럼 자기 팀만."""
    cs = _user("r_cs2", "CS")
    _user("r_sales2", "SALES")
    recipients = dict(resolve_recipients_for_notification(db_session, _team_notification("CS")))
    assert set(recipients) == {cs}
