"""FOMS 공지사항 서비스(설계서 docs/specs/2026-11-02-foms-notices_SPEC.md §2 · §3).

받는 사람 판정(본사 전체/팀 · 협력사 전체/회사 · 둘 다), 꺼진 계정 · 꺼진 협력사 제외, 게시 기간, 나중에 생긴 계정,
읽음 · 확인, 창 공지, 확인 현황, 받는 쪽 이름, 입력 검증, 감사 한 줄. 대조군: 받는 쪽이 아닌 사람은 같은 공지를 못 본다.
"""
from __future__ import annotations

import datetime

import pytest

from db import db_session
from foms.services.datetime_kst import now_utc_naive
from foms.services.notices.audience import audience_label, recipients, user_matches
from foms.services.notices.payload import NoticeInputError, parse_notice_payload
from foms.services.notices.service import (
    ack_notice,
    ack_status,
    admin_notice_rows,
    audience_options,
    create_notice,
    delete_notice,
    mark_read,
    notice_summary,
    pending_popups,
    unread_count,
    update_notice,
    visible_notices,
)
from models import Notice, NoticeAck, PartnerOrg, SecurityLog, User
from tests.security.partner_fixtures import _user


@pytest.fixture
def people(app):
    org_a = PartnerOrg(name="라운즈")
    org_b = PartnerOrg(name="다라가구")
    org_off = PartnerOrg(name="꺼진가구", is_active=False)
    db_session.add_all([org_a, org_b, org_off])
    db_session.commit()
    return {
        "admin": _user(role="ADMIN", team=None, name="관리자"),
        "sales": _user(team="SALES", name="영업김"),
        "measure": _user(team="MEASURE", name="실측이"),
        "drawing": _user(team="DRAWING", name="도면박"),
        "cs": _user(team="CS", name="상담최"),
        "staff_off": _user(team="SALES", name="퇴사자", is_active=False),
        "pa": _user(role="PARTNER", team=None, org=org_a, name="라운즈 직원"),
        "pa_off": _user(role="PARTNER", team=None, org=org_a, name="라운즈 꺼짐", is_active=False),
        "pb": _user(role="PARTNER", team=None, org=org_b, name="다라 직원"),
        "p_orgoff": _user(role="PARTNER", team=None, org=org_off, name="꺼진회사 직원"),
        "org_a": org_a,
        "org_b": org_b,
        "org_off": org_off,
    }


def _make(people, *, staff_all=False, teams=(), partner_all=False, orgs=(), mode="LIST", pinned=False,
          starts_at="", ends_at="", title="공지") -> Notice:
    payload = {
        "title": title,
        "body": "본문 첫 줄\n둘째 줄",
        "audience": {"staff_all": staff_all, "staff_teams": list(teams), "partner_all": partner_all,
                     "partner_org_ids": [people[o].id for o in orgs]},
        "display_mode": mode,
        "pinned": pinned,
        "starts_at": starts_at,
        "ends_at": ends_at,
    }
    notice = create_notice(db_session, people["admin"], payload)
    db_session.commit()
    return notice


def _sees(people, notice) -> set[str]:
    keys = ["admin", "sales", "measure", "drawing", "cs", "staff_off", "pa", "pa_off", "pb", "p_orgoff"]
    return {k for k in keys if any(i["id"] == notice.id for i in visible_notices(db_session, people[k]))}


def test_staff_all_reaches_every_active_staff_only(people):
    notice = _make(people, staff_all=True)
    assert _sees(people, notice) == {"admin", "sales", "measure", "drawing", "cs"}


def test_staff_team_uses_normalized_team(people):
    notice = _make(people, teams=["SALES", "DRAWING"])
    # 실측팀(MEASURE)은 영업팀으로 묶인다. 상담(CS) · 관리자(팀 없음) · 협력사는 못 본다.
    assert _sees(people, notice) == {"sales", "measure", "drawing"}
    assert audience_label(notice) == "본사: 영업 · 도면"


def test_partner_all_skips_off_accounts_and_off_orgs(people):
    notice = _make(people, partner_all=True)
    assert _sees(people, notice) == {"pa", "pb"}
    assert audience_label(notice) == "협력사 전체"


def test_partner_org_only_that_company(people):
    notice = _make(people, orgs=["org_a"])
    assert _sees(people, notice) == {"pa"}
    assert audience_label(notice) == "협력사: 라운즈"


def test_both_sides_in_one_notice(people):
    notice = _make(people, teams=["CS"], orgs=["org_b"])
    assert _sees(people, notice) == {"cs", "pb"}
    assert audience_label(notice) == "본사: CS + 협력사: 다라가구"
    assert audience_label(_make(people, staff_all=True, partner_all=True)) == "본사 전체 + 협력사 전체"


def test_recipients_and_user_matches(people):
    notice = _make(people, staff_all=True, orgs=["org_a"])
    names = [u.name for u in recipients(db_session, notice)]
    assert set(names) == {"관리자", "영업김", "실측이", "도면박", "상담최", "라운즈 직원"}
    assert names[-1] == "라운즈 직원"  # 본사 먼저
    assert user_matches(notice, people["pa"], False) is False  # 꺼진 협력사로 보면 못 받는다


def test_publish_window_and_soft_delete(people):
    now = now_utc_naive()
    future = (now + datetime.timedelta(hours=10)).strftime("%Y-%m-%dT%H:%M")
    past_start = (now - datetime.timedelta(hours=30)).strftime("%Y-%m-%dT%H:%M")
    past_end = (now - datetime.timedelta(hours=20)).strftime("%Y-%m-%dT%H:%M")
    later = _make(people, staff_all=True, starts_at=future, title="나중")
    expired = _make(people, staff_all=True, starts_at=past_start, ends_at=past_end, title="지남")
    live = _make(people, staff_all=True, title="지금")
    titles = {i["title"] for i in visible_notices(db_session, people["sales"])}
    assert titles == {"지금"}
    assert ack_notice(db_session, people["sales"], later.id) is False
    assert ack_notice(db_session, people["sales"], expired.id) is False
    assert delete_notice(db_session, people["admin"], live.id) is True
    db_session.commit()
    assert visible_notices(db_session, people["sales"]) == []
    assert delete_notice(db_session, people["admin"], live.id) is False


def test_kst_input_is_stored_as_utc(people):
    notice = _make(people, staff_all=True, starts_at="2026-11-02T09:00", ends_at="2026-11-03T09:00")
    assert notice.starts_at == datetime.datetime(2026, 11, 2, 0, 0)
    assert notice.ends_at == datetime.datetime(2026, 11, 3, 0, 0)
    row = next(r for r in admin_notice_rows(db_session) if r["id"] == notice.id)
    assert row["starts_at"] == "2026-11-02T09:00" and row["ends_at"] == "2026-11-03T09:00"


def test_account_created_later_also_sees_notice(people):
    notice = _make(people, teams=["PRODUCTION"], orgs=["org_b"])
    newbie = _user(team="PRODUCTION", name="새 생산")
    new_partner = _user(role="PARTNER", team=None, org=people["org_b"], name="새 다라")
    assert [i["id"] for i in visible_notices(db_session, newbie)] == [notice.id]
    assert [i["id"] for i in visible_notices(db_session, new_partner)] == [notice.id]


def test_read_ack_unread_and_popups(people):
    first = _make(people, staff_all=True, mode="POPUP", title="창 하나")
    second = _make(people, staff_all=True, mode="POPUP", title="창 둘")
    listed = _make(people, staff_all=True, mode="LIST", pinned=True, title="목록만")
    user = people["sales"]
    items = visible_notices(db_session, user)
    assert items[0]["id"] == listed.id  # 고정 먼저
    assert unread_count(db_session, user) == 3
    assert [p["id"] for p in pending_popups(db_session, user)] == [first.id, second.id]

    assert mark_read(db_session, user, listed.id) is True
    db_session.commit()
    assert unread_count(db_session, user) == 2
    assert [p["id"] for p in pending_popups(db_session, user)] == [first.id, second.id]  # 읽음 ≠ 확인

    assert ack_notice(db_session, user, first.id) is True
    db_session.commit()
    row = db_session.query(NoticeAck).filter_by(notice_id=first.id, user_id=user.id).one()
    first_ack = row.ack_at
    assert row.ack_at is not None and row.read_at is not None
    assert [p["id"] for p in pending_popups(db_session, user)] == [second.id]
    assert ack_notice(db_session, user, first.id) is True  # 두 번 눌러도 그대로
    db_session.commit()
    assert db_session.query(NoticeAck).filter_by(notice_id=first.id, user_id=user.id).one().ack_at == first_ack
    state = {i["id"]: (i["read"], i["acked"]) for i in visible_notices(db_session, user)}
    assert state == {listed.id: (True, False), first.id: (True, True), second.id: (False, False)}
    # 다른 사람 기록과 섞이지 않는다.
    assert unread_count(db_session, people["cs"]) == 3


def test_non_recipient_cannot_ack_or_read(people):
    notice = _make(people, teams=["DRAWING"], mode="POPUP")
    assert ack_notice(db_session, people["cs"], notice.id) is False
    assert mark_read(db_session, people["pa"], notice.id) is False
    assert ack_notice(db_session, people["drawing"], 999999) is False
    assert db_session.query(NoticeAck).count() == 0


def test_ack_status_counts_current_recipients(people):
    notice = _make(people, teams=["SALES"], orgs=["org_a", "org_b"], mode="POPUP")
    ack_notice(db_session, people["sales"], notice.id)
    ack_notice(db_session, people["pb"], notice.id)
    mark_read(db_session, people["pa"], notice.id)
    db_session.commit()
    status = ack_status(db_session, notice.id)
    assert (status["total"], status["acked"]) == (4, 2)
    assert (status["staff"]["total"], status["staff"]["acked"]) == (2, 1)
    assert (status["partner"]["total"], status["partner"]["acked"]) == (2, 1)
    staff = {p["name"]: p for p in status["staff"]["people"]}
    assert staff["실측이"]["team_label"] == "영업팀" and staff["실측이"]["acked_at"] == ""
    assert status["staff"]["people"][0]["name"] == "실측이"  # 안 한 사람 먼저
    partner = {p["name"]: p for p in status["partner"]["people"]}
    assert partner["라운즈 직원"]["org_name"] == "라운즈"
    assert partner["라운즈 직원"]["read_at"] and not partner["라운즈 직원"]["acked_at"]
    row = next(r for r in admin_notice_rows(db_session) if r["id"] == notice.id)
    assert row["ack"] == {"total": 4, "acked": 2}
    assert ack_status(db_session, 999999) is None


def test_audience_options_counts(people):
    opts = audience_options(db_session)
    assert {"code": "SALES", "label": "영업팀"} in opts["teams"]
    assert [p["name"] for p in opts["partners"]] == ["다라가구", "라운즈"]  # 꺼진 협력사 없음
    counts = opts["counts"]
    assert counts["by_team"]["SALES"] == 2  # 영업 + 실측(퇴사자 제외)
    assert counts["partner_all"] == 2
    assert counts["by_org"][str(people["org_a"].id)] == 1
    assert counts["staff_all"] >= 5


def test_update_writes_audit_and_changes_audience(people):
    notice = _make(people, teams=["CS"])
    payload = {"title": "고친 제목", "body": "", "audience": {"partner_all": True}, "display_mode": "POPUP"}
    assert update_notice(db_session, people["admin"], notice.id, payload) is not None
    db_session.commit()
    assert _sees(people, notice) == {"pa", "pb"}
    actions = [r.action for r in db_session.query(SecurityLog).filter(SecurityLog.target_type == "notice",
                                                                      SecurityLog.target_id == notice.id)]
    assert actions == ["NOTICE_CREATED", "NOTICE_UPDATED"]
    assert update_notice(db_session, people["admin"], 999999, payload) is None


@pytest.mark.parametrize("payload, message", [
    ({"title": "", "audience": {"staff_all": True}, "display_mode": "LIST"}, "제목"),
    ({"title": "가" * 201, "audience": {"staff_all": True}, "display_mode": "LIST"}, "200자"),
    ({"title": "t", "audience": {}, "display_mode": "LIST"}, "받는 사람"),
    ({"title": "t", "audience": {"staff_teams": ["NOPE"]}, "display_mode": "LIST"}, "팀"),
    ({"title": "t", "audience": {"partner_org_ids": [987654]}, "display_mode": "LIST"}, "협력사"),
    ({"title": "t", "audience": {"staff_all": True}, "display_mode": "BANNER"}, "보이는 방식"),
    ({"title": "t", "audience": {"staff_all": True}, "display_mode": "LIST",
      "starts_at": "2026-11-03T09:00", "ends_at": "2026-11-03T09:00"}, "게시 끝"),
    ({"title": "t", "audience": {"staff_all": True}, "display_mode": "LIST", "starts_at": "내일"}, "모양"),
])
def test_validation_errors(people, payload, message):
    with pytest.raises(NoticeInputError) as err:
        parse_notice_payload(db_session, payload)
    assert message in str(err.value)


def test_created_by_and_kst_text(people):
    notice = _make(people, staff_all=True)
    item = visible_notices(db_session, people["cs"])[0]
    assert item["created_by_name"] == "관리자"
    assert len(item["created_at"]) == 16 and item["audience_label"] == "본사 전체"
    assert db_session.get(User, people["admin"].id).id == notice.created_by_user_id


def test_partner_viewer_label_hides_other_companies_and_staff_teams(people):
    """라운즈 직원이 보는 받는 쪽 이름에는 다른 회사(다라가구) · 본사 팀이 없다. 본사 직원은 전체 라벨."""
    both = _make(people, teams=["SALES", "DRAWING"], orgs=["org_a", "org_b"], title="같이")
    only = _make(people, orgs=["org_a", "org_b"], title="협력사만")
    every = _make(people, staff_all=True, partner_all=True, title="모두")
    labels = {i["id"]: i["audience_label"] for i in visible_notices(db_session, people["pa"])}
    assert labels == {both.id: "본사 · 협력사 공지", only.id: "협력사 공지", every.id: "본사 · 협력사 공지"}
    assert not any("다라가구" in v or "영업" in v for v in labels.values())
    staff = {i["id"]: i["audience_label"] for i in visible_notices(db_session, people["sales"])}
    assert staff[both.id] == "본사: 영업 · 도면 + 협력사: 라운즈 · 다라가구"


def test_summary_matches_full_list(people):
    """창 요약(본문 없이 센 것)과 전체 목록 판정이 같다 — 안 읽음 수 · 창 차례."""
    popups = [_make(people, staff_all=True, mode="POPUP", title=f"창 {i}") for i in range(7)]
    _make(people, teams=["SALES"], mode="LIST", title="영업 목록")
    _make(people, teams=["CS"], mode="POPUP", title="상담만 창")
    user = people["measure"]  # MEASURE → SALES 로 묶인다
    mark_read(db_session, user, popups[0].id)
    ack_notice(db_session, user, popups[1].id)
    db_session.commit()
    items = visible_notices(db_session, user)
    summary = notice_summary(db_session, user)
    assert summary["unread"] == sum(1 for i in items if not i["read"]) == 6
    assert [p["id"] for p in summary["pending"]] == [p.id for p in popups if p.id != popups[1].id][:5]
    assert summary["pending"][0]["body"] == "본문 첫 줄\n둘째 줄"
    assert unread_count(db_session, user) == 6 and pending_popups(db_session, user) == summary["pending"]
